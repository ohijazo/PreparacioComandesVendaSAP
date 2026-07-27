"""Worker que sincronitza els càlculs d'embalatges amb SAP via Service Layer.

Loop:
  1. Obté les comandes obertes amb `U_FCCalcular='S'` (via consultes).
  2. Per cada una: calcula amb `motor.calcular_embalatges`, formata el resum
     amb `sap_formatter.formatar_resum`, i escriu a SAP amb `SLClient.patch_order`
     posant `U_FCCalcular='N'` (així no es reprocessa fins que l'usuari torni a marcar-lo).
  3. Si algun pas falla per una comanda concreta: registra error, continua amb la resta.
     Escriu `U_FCEmbalatgeEstat='ERROR'` + missatge a `U_FCEmbalatgeResum` per fer
     visible a l'operari; **també posa `U_FCCalcular='N'`** perquè el worker no
     entre en loop reprocessant la mateixa comanda amb el mateix error.

Sense estat local (SQLite, etc.): el "estat" viu al mateix ORDR.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger("sync_worker")


@dataclass
class PassStats:
    """Estadístiques d'una passada del worker."""
    trobades: int = 0
    ok: int = 0
    error_motor: int = 0
    error_patch: int = 0
    error_altres: int = 0
    dry_run: bool = False
    errors: list[dict[str, Any]] = field(default_factory=list)  # {'doc_entry': int, 'msg': str}
    elapsed_sec: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "trobades": self.trobades,
            "ok": self.ok,
            "error_motor": self.error_motor,
            "error_patch": self.error_patch,
            "error_altres": self.error_altres,
            "dry_run": self.dry_run,
            "elapsed_sec": round(self.elapsed_sec, 3),
            "errors": self.errors,
        }


class SyncWorker:
    """Orquestrador de la sincronització SAP.

    Injeccions per fer-lo testable sense tocar mòduls globals:
    - `sl_client`: instància `SLClient` (ja loggejada) o similar amb `patch_order(doc, dict)`.
    - `connectar_fn`: funció que retorna una nova conn pyodbc.
    - `obtenir_comandes_fn`: funció que rep una conn i retorna list[dict] amb doc_entry/series/docnum.
    - `calcular_fn`: funció (series, docnum, forcar) -> Resultat.
    - `formatar_fn`: funció Resultat -> (text, estat).
    """

    def __init__(
        self,
        sl_client: Any,
        connectar_fn: Callable[[], Any],
        obtenir_comandes_fn: Callable[[Any], list[dict[str, Any]]],
        calcular_fn: Callable[..., Any],
        formatar_fn: Callable[[Any], tuple[str, str]],
        *,
        interval_sec: float = 10.0,
        max_per_pass: int = 50,
        dry_run: bool = False,
    ):
        self.sl_client = sl_client
        self.connectar_fn = connectar_fn
        self.obtenir_comandes_fn = obtenir_comandes_fn
        self.calcular_fn = calcular_fn
        self.formatar_fn = formatar_fn
        self.interval_sec = interval_sec
        self.max_per_pass = max_per_pass
        self.dry_run = dry_run

    # ------------------------------------------------------------------
    # Passada única
    # ------------------------------------------------------------------
    def run_one_pass(self) -> PassStats:
        """Executa una passada. Retorna estadístiques."""
        stats = PassStats(dry_run=self.dry_run)
        t0 = time.monotonic()

        # 1) Obtenir comandes marcades (query lleugera)
        conn = self.connectar_fn()
        try:
            comandes = self.obtenir_comandes_fn(conn)
        finally:
            self._safe_close(conn)

        stats.trobades = len(comandes)
        if not comandes:
            stats.elapsed_sec = time.monotonic() - t0
            return stats

        # 2) Processar cada comanda
        for c in comandes[: self.max_per_pass]:
            self._process_one(c, stats)

        stats.elapsed_sec = time.monotonic() - t0
        return stats

    def _process_one(self, c: dict[str, Any], stats: PassStats) -> None:
        doc_entry = c["doc_entry"]
        series = str(c["series"])
        docnum = str(c["docnum"])

        # 2a) Calcular
        try:
            resultat = self.calcular_fn(series, docnum, forcar=False)
        except Exception as e:
            logger.exception("Motor peta a %s/%s (DocEntry=%s)", series, docnum, doc_entry)
            stats.error_motor += 1
            stats.errors.append({"doc_entry": doc_entry, "msg": f"motor: {e}"})
            self._patch_error(doc_entry, str(e), stats)
            return

        # 2b) Formatar resum
        try:
            text, estat = self.formatar_fn(resultat)
        except Exception as e:
            logger.exception("Formatter peta a %s/%s (DocEntry=%s)", series, docnum, doc_entry)
            stats.error_altres += 1
            stats.errors.append({"doc_entry": doc_entry, "msg": f"formatter: {e}"})
            self._patch_error(doc_entry, str(e), stats)
            return

        # 2c) Escriure a SAP (o simular si dry_run)
        payload = {
            "U_FCCalcular": "N",
            "U_FCEmbalatgeResum": text,
            "U_FCEmbalatgeEstat": estat,
        }
        if self.dry_run:
            logger.info("[DRY-RUN] PATCH Orders(%s) payload=%s", doc_entry, payload)
            stats.ok += 1
            return

        try:
            self.sl_client.patch_order(doc_entry, payload)
            stats.ok += 1
        except Exception as e:
            logger.exception("PATCH peta a DocEntry=%s", doc_entry)
            stats.error_patch += 1
            stats.errors.append({"doc_entry": doc_entry, "msg": f"patch: {e}"})
            # No re-intent aquí: la propera passada tornarà a trobar el flag
            # actiu (perquè no s'ha pogut posar a 'N') i reintentarà.

    def _patch_error(self, doc_entry: int, msg: str, stats: PassStats) -> None:
        """Escriu l'error a SAP + posa el flag a 'N' perquè no torni a processar-se.

        Si el patch d'error també peta, ho registra però no interromp el worker.
        """
        payload = {
            "U_FCCalcular": "N",
            "U_FCEmbalatgeResum": f"ERROR: {msg[:240]}",
            "U_FCEmbalatgeEstat": "ERROR",
        }
        if self.dry_run:
            logger.info("[DRY-RUN] PATCH d'error Orders(%s) payload=%s", doc_entry, payload)
            return
        try:
            self.sl_client.patch_order(doc_entry, payload)
        except Exception:
            logger.exception("PATCH d'error també peta a DocEntry=%s — flag es queda 'S'", doc_entry)
            # Registrat com error_patch però no doblem el comptador
            # (l'error principal ja està a stats).

    # ------------------------------------------------------------------
    # Loop infinit
    # ------------------------------------------------------------------
    def run_forever(self, stop_event: threading.Event | None = None) -> None:
        """Loop indefinit. Aturat quan `stop_event` es setegi.

        Errors globals a una passada no aturen el loop — es logs i continua.
        """
        stop_event = stop_event or threading.Event()
        logger.info(
            "SyncWorker arrencat (interval=%.1fs, max_per_pass=%d, dry_run=%s)",
            self.interval_sec, self.max_per_pass, self.dry_run,
        )
        while not stop_event.is_set():
            t0 = time.monotonic()
            try:
                stats = self.run_one_pass()
                if stats.trobades or stats.errors:
                    logger.info("Passada: %s", stats.to_dict())
            except Exception:
                logger.exception("Passada del worker peta (loop continua)")

            # Espera fins al proper cicle. Trencar aviat si stop_event.
            # `max(0.1, ...)` evita tight loop si `interval_sec` és molt petit
            # o si la passada peta ràpid (ex: BD caiguda).
            elapsed = time.monotonic() - t0
            wait = max(0.1, self.interval_sec - elapsed)
            stop_event.wait(wait)
        logger.info("SyncWorker aturat.")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _safe_close(conn) -> None:
        try:
            conn.close()
        except Exception:
            pass
