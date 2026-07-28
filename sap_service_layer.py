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
