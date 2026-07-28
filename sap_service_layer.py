"""Client Service Layer per SAP Business One.

Encapsula:
- Login/logout amb gestió de sessió (cookie B1SESSION).
- Renovació proactiva abans que expiri (25 min per defecte, marge sobre 30 min de SAP).
- Reintent automàtic en 401 (relogin + retry 1 cop).
- Reintent amb backoff en 5xx (3 intents totals).
- PATCH sobre `/Orders({DocEntry})` per escriure UDFs `U_FCEmbalatge*`.

Ús típic:
    with SLClient(url, company, user, pwd) as sl:
        sl.patch_order(1234, {
            "U_FCCalcular": "N",
            "U_FCEmbalatgeResum": "3 palets · 120 sacs · CALCULAT",
            "U_FCEmbalatgeEstat": "CALCULAT",
        })

Configuració via `.env` (variables `SAP_SL_*`).
"""
from __future__ import annotations

import logging
import time
from typing import Any

import requests

logger = logging.getLogger("sap_service_layer")

# Timeout de sessió Service Layer per defecte a SAP: 30 min.
# Renovem preventivament als 25 min per marge de seguretat.
_SESSION_MAX_AGE_SEC = 25 * 60


class SLError(Exception):
    """Excepció general del client Service Layer."""

    def __init__(self, message: str, status_code: int | None = None, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class SLLoginError(SLError):
    """Login rebutjat per Service Layer (credencials / companyia invàlids)."""


class SLNotFoundError(SLError):
    """Recurs no trobat (404). Útil per distingir upsert."""


class SLClient:
    """Client REST per SAP Service Layer amb gestió de sessió i reintents."""

    def __init__(
        self,
        url: str,
        company: str,
        user: str,
        pwd: str,
        verify: bool = True,
        timeout: int = 15,
        max_retries_5xx: int = 3,
        backoff_base_sec: float = 2.0,
    ):
        # Normalitzem sense barra final per compondre paths de manera consistent.
        self.url = url.rstrip("/")
        self.company = company
        self.user = user
        self.pwd = pwd
        self.verify = verify
        self.timeout = timeout
        self.max_retries_5xx = max_retries_5xx
        self.backoff_base_sec = backoff_base_sec

        self._session: requests.Session | None = None
        self._session_ts: float | None = None

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------
    def __enter__(self) -> SLClient:
        self.login()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        try:
            self.logout()
        except Exception:
            logger.warning("Ignorat error al logout", exc_info=True)

    # ------------------------------------------------------------------
    # Sessió
    # ------------------------------------------------------------------
    def login(self) -> None:
        """Fa POST /Login i guarda les cookies de sessió."""
        session = requests.Session()
        try:
            resp = session.post(
                f"{self.url}/Login",
                json={"CompanyDB": self.company, "UserName": self.user, "Password": self.pwd},
                verify=self.verify,
                timeout=self.timeout,
            )
        except requests.RequestException as e:
            raise SLLoginError(f"Fallada de xarxa al login: {e}") from e

        if resp.status_code != 200:
            raise SLLoginError(
                f"Login rebutjat ({resp.status_code})",
                status_code=resp.status_code,
                body=self._safe_body(resp),
            )
        self._session = session
        self._session_ts = time.monotonic()
        logger.info("Login OK a Service Layer %s / %s", self.url, self.company)

    def logout(self) -> None:
        """Fa POST /Logout i esborra la sessió local."""
        if self._session is None:
            return
        try:
            self._session.post(
                f"{self.url}/Logout",
                verify=self.verify,
                timeout=self.timeout,
            )
        except requests.RequestException:
            # No propaguem — el servidor descartarà la sessió pel timeout.
            pass
        finally:
            self._session.close()
            self._session = None
            self._session_ts = None

    def _ensure_session(self) -> None:
        """Assegura que hi ha sessió i que no ha expirat (renovació preventiva)."""
        if self._session is None:
            self.login()
            return
        age = time.monotonic() - (self._session_ts or 0.0)
        if age >= _SESSION_MAX_AGE_SEC:
            logger.info("Sessió Service Layer envellida (%d s), renovant", age)
            self.logout()
            self.login()

    # ------------------------------------------------------------------
    # Request wrapper amb reintents
    # ------------------------------------------------------------------
    def _request(self, method: str, path: str, json_body: Any = None) -> requests.Response:
        """Envia request amb reintents automàtics.

        - 401: re-login + retry 1 vegada.
        - 5xx: backoff exponencial fins a `max_retries_5xx` intents totals.
        - Altres 4xx: propaga com a SLError.

        Headers estàndard per PATCH/POST/DELETE:
        - `Prefer: return=minimal` — evita que SL torni el document sencer i
          re-validi tot el contingut al commit. Sense aquest header, PATCH
          sobre Orders sovint falla amb error -1116 "Could not commit
          transaction" perquè SAP intenta commit del document complet.
        """
        self._ensure_session()
        assert self._session is not None
        full_url = f"{self.url}/{path.lstrip('/')}"

        # Headers específics per requests que muten dades
        extra_headers = {}
        if method.upper() in ("PATCH", "POST", "PUT", "DELETE"):
            extra_headers["Prefer"] = "return=minimal"

        # 5xx retry loop
        last_resp: requests.Response | None = None
        for attempt in range(self.max_retries_5xx):
            resp = self._session.request(
                method, full_url,
                json=json_body,
                headers=extra_headers,
                verify=self.verify,
                timeout=self.timeout,
            )

            # 401 → invalidar sessió i reintent (1 cop)
            if resp.status_code == 401 and attempt == 0:
                logger.info("401 rebut, relogin + retry")
                self.login()
                assert self._session is not None
                resp = self._session.request(
                    method, full_url,
                    json=json_body,
                    headers=extra_headers,
                    verify=self.verify,
                    timeout=self.timeout,
                )
                if resp.status_code == 401:
                    raise SLError(
                        f"401 persistent després de relogin ({method} {path})",
                        status_code=401, body=self._safe_body(resp),
                    )

            if 500 <= resp.status_code < 600:
                last_resp = resp
                if attempt + 1 < self.max_retries_5xx:
                    sleep_sec = self.backoff_base_sec * (2 ** attempt)
                    logger.warning(
                        "5xx (%d) a %s %s, reintent %d/%d després de %.1fs",
                        resp.status_code, method, path,
                        attempt + 2, self.max_retries_5xx, sleep_sec,
                    )
                    time.sleep(sleep_sec)
                    continue
                # sense més reintents
                raise SLError(
                    f"Error 5xx persistent ({resp.status_code}) a {method} {path}",
                    status_code=resp.status_code, body=self._safe_body(resp),
                )

            # 404: cas especial (útil per branca "no existeix" en upserts)
            if resp.status_code == 404:
                raise SLNotFoundError(
                    f"Recurs no trobat: {method} {path}",
                    status_code=404, body=self._safe_body(resp),
                )

            # Altres 4xx: propagar
            if 400 <= resp.status_code < 500:
                body = self._safe_body(resp)
                logger.error(
                    "SL %s %s → %d. Body: %s",
                    method, path, resp.status_code, body,
                )
                raise SLError(
                    f"Error {resp.status_code} a {method} {path}: {body}",
                    status_code=resp.status_code, body=body,
                )

            # 2xx OK
            return resp

        # Improbable arribar aquí; si ho fem, propagem l'últim
        assert last_resp is not None
        raise SLError(
            f"Sense èxit després de {self.max_retries_5xx} intents",
            status_code=last_resp.status_code, body=self._safe_body(last_resp),
        )

    # ------------------------------------------------------------------
    # Operacions de negoci
    # ------------------------------------------------------------------
    def patch_order(self, doc_entry: int, fields: dict[str, Any]) -> None:
        """PATCH /Orders({DocEntry}) amb els camps donats.

        Ús principal: escriure els UDFs `U_FCEmbalatgeResum`, `U_FCEmbalatgeEstat`
        i posar `U_FCCalcular='N'` un cop calculat.

        Service Layer respon 204 No Content en un PATCH exitós.
        """
        self._request("PATCH", f"Orders({doc_entry})", json_body=fields)

    def replace_marked_lines(
        self,
        doc_entry: int,
        marker_field: str,
        marker_value: str,
        new_lines: list[dict[str, Any]],
        header_fields: dict[str, Any] | None = None,
    ) -> dict[str, int]:
        """Substitueix les línies "marcades" d'una Order i afegeix noves.

        Important sobre el patró SAP B1 SL:
        - El SL **NO permet** DELETE de línies individuals (retorna -5006).
        - El SL **NO esborra** línies quan el PATCH del document omet una
          línia existent — el PATCH només actualitza les línies presents
          (per LineNum) i preserva la resta.
        - L'única manera "neta" d'invalidar una línia és marcar-la com
          tancada: `LineStatus="bost_Close"`. La línia segueix a RDR1 però
          desapareix del formulari i no compta a albarà/factura.

        Passos:
        1. GET `/Orders({doc_entry})?$select=DocEntry,DocumentLines` —
           obtenir totes les línies actuals.
        2. Identificar línies "obertes" amb `line[marker_field] == marker_value`
           (les que un càlcul anterior va inserir com a palets del motor).
        3. PATCH `/Orders({doc_entry})` amb:
           - Per cada línia a tancar: `{LineNum, LineStatus="bost_Close"}`
             — cap altre camp (SAP rebutja "close + altres canvis" al
             mateix PATCH amb -5002). El filtre de la propera crida ja
             ignorarà les línies tancades, no cal resetejar el marker.
           - Per cada `new_line`: dict SENSE `LineNum` (SAP auto-numera).

        Retorna `{"removed": N (línies tancades), "added": M, "kept": K}`.

        Raises `SLError` si alguna crida falla.
        """
        # 1. GET línies actuals
        resp = self._request(
            "GET",
            f"Orders({doc_entry})?$select=DocEntry,DocumentLines",
        )
        try:
            body = resp.json()
        except Exception as e:
            raise SLError(
                f"Resposta GET /Orders({doc_entry}) no és JSON vàlid",
                status_code=resp.status_code,
            ) from e

        current_lines = body.get("DocumentLines", []) or []

        # 2. Classificar: quines tanquem (marcades i obertes), quines preservem
        #    al placeholder del PATCH #2 (TOTES les que no tanquem, incloent
        #    les ja tancades — sinó SAP les tracta com "no existeixen" i pot
        #    reorganitzar el document destructivament).
        to_close = [
            l for l in current_lines
            if l.get(marker_field) == marker_value
            and l.get("LineStatus") != "bost_Close"
        ]
        to_close_ids = {l["LineNum"] for l in to_close}
        to_preserve = [
            l for l in current_lines
            if l["LineNum"] not in to_close_ids
        ]

        # 3. PATCH #1: tancar línies velles (si n'hi ha).
        #    - SAP no permet "tancar línies + altres modificacions" al mateix
        #      PATCH (`-5002`). El payload de tancament NOMÉS pot dur
        #      `LineNum + LineStatus`; qualsevol altre camp trenca.
        #    - No cal resetejar el marker: el filtre ignora línies
        #      `bost_Close` a la propera crida.
        if to_close:
            close_body: dict[str, Any] = {
                "DocumentLines": [
                    {"LineNum": l["LineNum"], "LineStatus": "bost_Close"}
                    for l in to_close
                ]
            }
            self._request("PATCH", f"Orders({doc_entry})", json_body=close_body)

        # 4. PATCH #2: afegir línies noves + opcional header_fields.
        #    Patró crític per no destruir línies existents: enviem un
        #    "placeholder" `{LineNum: X}` per **cada línia existent** que
        #    NO acabem de tancar (obertes I ja tancades). SAP les
        #    preserva intactes. Les noves van SENSE `LineNum` (SAP els
        #    assigna consecutivament al final).
        #    Sense placeholders, o omitint alguns, SAP pot: (a)
        #    sobreescriure línies existents amb les noves per índex
        #    posicional, (b) rebutjar amb `-1029 Field cannot be updated`
        #    perquè intenta canviar ItemCode d'una línia existent, o
        #    (c) reorganitzar l'ordre. Empíricament, cal enviar
        #    placeholder per TOTES.
        add_body: dict[str, Any] = {}
        if new_lines:
            add_body["DocumentLines"] = (
                [{"LineNum": l["LineNum"]} for l in to_preserve]
                + [
                    {k: v for k, v in nl.items() if k != "LineNum"}
                    for nl in new_lines
                ]
            )
        if header_fields:
            add_body.update(header_fields)

        if add_body:
            self._request("PATCH", f"Orders({doc_entry})", json_body=add_body)

        return {
            "removed": len(to_close),
            "added": len(new_lines),
            "kept": len(current_lines) - len(to_close),
        }

    # ------------------------------------------------------------------
    # Utilitats internes
    # ------------------------------------------------------------------
    @staticmethod
    def _safe_body(resp: requests.Response) -> Any:
        """Retorna el body de la resposta com a dict o text, evitant excepcions."""
        try:
            return resp.json()
        except Exception:
            return resp.text[:500] if resp.text else None
