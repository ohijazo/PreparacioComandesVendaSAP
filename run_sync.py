"""Entry point del worker de sync SAP.

Uneix els mòduls de la Fase 2:
- `consultes.connectar` + `obtenir_comandes_a_calcular` (BD SAP, read-only).
- `motor.calcular_embalatges` (motor de regles).
- `sap_formatter.formatar_resum` (text + estat).
- `sap_service_layer.SLClient` (PATCH via Service Layer).
- `sync_worker.SyncWorker` (loop + orquestració).

Ús:
    python run_sync.py                    # loop indefinit
    python run_sync.py --once             # una passada i sortir
    python run_sync.py --dry-run          # calcula però no escriu a SAP
    python run_sync.py --interval 5       # cicles de 5s (per defecte 10s)
    python run_sync.py --max-per-pass 20  # màxim 20 comandes per passada

Config via `.env` (variables `SAP_SL_*`) — llegit automàticament pel
`consultes.py` al import.
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import threading

import _bootstrap  # noqa: F401 — insereix KAIS_APP_PATH

# `consultes` importa `.env` al import → les variables `SAP_SL_*` queden a os.environ.
from consultes import connectar, obtenir_comandes_a_calcular
from motor import calcular_embalatges
from sap_formatter import formatar_resum
from sap_service_layer import SLClient
from sync_worker import SyncWorker

logger = logging.getLogger("run_sync")


def _parse_args():
    p = argparse.ArgumentParser(description="Worker de sync SAP per Motor de Comandes")
    p.add_argument("--once", action="store_true",
                   help="Executa una passada i surt (no loop).")
    p.add_argument("--dry-run", action="store_true",
                   help="Calcula però no escriu a SAP (només loggeja).")
    p.add_argument("--interval", type=float, default=None,
                   help="Segons entre passades (default: env SYNC_INTERVAL_SEC o 10).")
    p.add_argument("--max-per-pass", type=int, default=None,
                   help="Màxim comandes per passada (default: env SYNC_MAX_PER_PASS o 50).")
    p.add_argument("--log-level", default="INFO",
                   help="Nivell de log (DEBUG/INFO/WARNING/ERROR).")
    return p.parse_args()


def _setup_logging(level_str: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level_str.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def _build_sl_client() -> SLClient:
    """Instancia SLClient a partir de variables d'entorn SAP_SL_*."""
    url = os.environ.get("SAP_SL_URL")
    company = os.environ.get("SAP_SL_COMPANY")
    user = os.environ.get("SAP_SL_USER")
    pwd = os.environ.get("SAP_SL_PASSWORD")
    verify_str = os.environ.get("SAP_SL_VERIFY_SSL", "true").lower()
    timeout = int(os.environ.get("SAP_SL_TIMEOUT", "15"))

    missing = [k for k, v in (("SAP_SL_URL", url), ("SAP_SL_COMPANY", company),
                              ("SAP_SL_USER", user), ("SAP_SL_PASSWORD", pwd)) if not v]
    if missing:
        raise SystemExit(f"Falten variables .env obligatòries: {', '.join(missing)}")

    return SLClient(
        url=url, company=company, user=user, pwd=pwd,
        verify=(verify_str not in ("false", "0", "no")),
        timeout=timeout,
    )


def _build_worker(sl_client: SLClient, interval: float, max_per_pass: int,
                  dry_run: bool, status_file: str | None) -> SyncWorker:
    return SyncWorker(
        sl_client=sl_client,
        connectar_fn=connectar,
        obtenir_comandes_fn=obtenir_comandes_a_calcular,
        calcular_fn=calcular_embalatges,
        formatar_fn=formatar_resum,
        interval_sec=interval,
        max_per_pass=max_per_pass,
        dry_run=dry_run,
        status_file=status_file,
    )


def _install_signal_handlers(stop_event: threading.Event) -> None:
    """SIGINT / SIGTERM setegen stop_event per graceful shutdown."""
    def _handler(signum, frame):
        logger.info("Senyal %s rebut, aturant worker...", signum)
        stop_event.set()

    signal.signal(signal.SIGINT, _handler)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _handler)


def main():
    args = _parse_args()
    _setup_logging(args.log_level)

    interval = args.interval or float(os.environ.get("SYNC_INTERVAL_SEC", "10"))
    max_per_pass = args.max_per_pass or int(os.environ.get("SYNC_MAX_PER_PASS", "50"))

    # Fitxer JSON amb l'estat del worker per l'endpoint /api/admin/sync-status.
    # Per defecte a logs/sync_status.json (mateix directori que els logs NSSM).
    status_file = os.environ.get("SYNC_STATUS_FILE")
    if not status_file:
        logs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
        os.makedirs(logs_dir, exist_ok=True)
        status_file = os.path.join(logs_dir, "sync_status.json")

    sl = _build_sl_client()

    # Login explícit — així fallem aviat si les credencials són incorrectes.
    try:
        sl.login()
    except Exception:
        logger.exception("Login al Service Layer ha fallat — abortant")
        return 2

    try:
        worker = _build_worker(sl, interval, max_per_pass, args.dry_run, status_file)

        if args.once:
            stats = worker.run_one_pass()
            logger.info("Passada única acabada: %s", stats.to_dict())
        else:
            stop = threading.Event()
            _install_signal_handlers(stop)
            worker.run_forever(stop_event=stop)
    finally:
        try:
            sl.logout()
        except Exception:
            logger.warning("Error al logout (ignorat)", exc_info=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
