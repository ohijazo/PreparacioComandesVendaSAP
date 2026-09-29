"""Tests unitaris de sap_service_layer.SLClient amb HTTP mockejat."""
from __future__ import annotations

import time
from unittest.mock import patch

import pytest
import responses

# NOTA: conftest.py fa import _bootstrap que carrega el path Kais.
# Aquí no necessitem models compartits — importem el mòdul local directament.
import sap_service_layer as sl_mod
from sap_service_layer import SLClient, SLError, SLLoginError, SLNotFoundError

URL = "https://sap.test/b1s/v2"
COMPANY = "DB_FARINERA_TEST"
USER = "manager"
PWD = "secret"


def _make_client(**overrides) -> SLClient:
    kwargs = dict(
        url=URL, company=COMPANY, user=USER, pwd=PWD,
        verify=False,          # sense verificar SSL en tests
        timeout=5,
        max_retries_5xx=3,
        backoff_base_sec=0.0,  # sense esperes en tests
    )
    kwargs.update(overrides)
    return SLClient(**kwargs)


# ============================================================
# Login / logout
# ============================================================

@responses.activate
def test_login_ok_guarda_sessio():
    responses.add(responses.POST, f"{URL}/Login", json={"SessionId": "abc"}, status=200)

    c = _make_client()
    assert c._session is None
    c.login()

    assert c._session is not None
    assert c._session_ts is not None
    assert len(responses.calls) == 1
    assert responses.calls[0].request.url == f"{URL}/Login"


@responses.activate
def test_login_fallit_credencials():
    responses.add(responses.POST, f"{URL}/Login", json={"error": "invalid"}, status=401)

    c = _make_client()
    with pytest.raises(SLLoginError) as exc:
        c.login()
    assert exc.value.status_code == 401


@responses.activate
def test_logout_neteja_sessio():
    responses.add(responses.POST, f"{URL}/Login", json={}, status=200)
    responses.add(responses.POST, f"{URL}/Logout", status=204)

    c = _make_client()
    c.login()
    assert c._session is not None
    c.logout()
    assert c._session is None
    assert c._session_ts is None


@responses.activate
def test_context_manager_login_logout():
    responses.add(responses.POST, f"{URL}/Login", json={}, status=200)
    responses.add(responses.POST, f"{URL}/Logout", status=204)
    responses.add(responses.PATCH, f"{URL}/Orders(42)", status=204)

    with _make_client() as c:
        c.patch_order(42, {"U_FCEmbalatgeEstat": "CALCULAT"})

    assert c._session is None  # logout ha netejat
    # 3 crides: Login + PATCH + Logout
    assert len(responses.calls) == 3


# ============================================================
# Renovació de sessió preventiva
# ============================================================

@responses.activate
def test_sessio_no_es_renova_abans_de_max_age():
    responses.add(responses.POST, f"{URL}/Login", json={}, status=200)
    responses.add(responses.PATCH, f"{URL}/Orders(1)", status=204)

    c = _make_client()
    c.login()
    ts_original = c._session_ts

    # Immediatament fem un PATCH — no cal renovar sessió
    c.patch_order(1, {"foo": "bar"})
    assert c._session_ts == ts_original
    # Només 2 crides: 1 Login + 1 PATCH (cap re-login)
    assert len(responses.calls) == 2


@responses.activate
def test_sessio_es_renova_quan_expira():
    responses.add(responses.POST, f"{URL}/Login", json={}, status=200)
    responses.add(responses.POST, f"{URL}/Logout", status=204)
    responses.add(responses.POST, f"{URL}/Login", json={}, status=200)  # 2n login
    responses.add(responses.PATCH, f"{URL}/Orders(1)", status=204)

    c = _make_client()
    c.login()

    # Simulem que la sessió té 30 min (per damunt de 25 min de MAX_AGE)
    c._session_ts = time.monotonic() - (30 * 60)

    c.patch_order(1, {"foo": "bar"})

    # 4 crides: Login + Logout + Login (renovació) + PATCH
    assert len(responses.calls) == 4
    assert responses.calls[0].request.url == f"{URL}/Login"
    assert responses.calls[1].request.url == f"{URL}/Logout"
    assert responses.calls[2].request.url == f"{URL}/Login"
    assert responses.calls[3].request.url == f"{URL}/Orders(1)"


# ============================================================
# Retries: 401 → relogin + retry
# ============================================================

@responses.activate
def test_401_relogin_i_retry_ok():
    responses.add(responses.POST, f"{URL}/Login", json={}, status=200)
    # PATCH 1: 401
    responses.add(responses.PATCH, f"{URL}/Orders(1)", json={"error": "expired"}, status=401)
    # Re-login OK
    responses.add(responses.POST, f"{URL}/Login", json={}, status=200)
    # PATCH 2: OK
    responses.add(responses.PATCH, f"{URL}/Orders(1)", status=204)

    c = _make_client()
    c.patch_order(1, {"foo": "bar"})  # login implícit + PATCH → 401 → relogin + retry OK

    # 4 crides: Login + PATCH(401) + Login + PATCH(204)
    assert len(responses.calls) == 4


@responses.activate
def test_401_persistent_despres_relogin_llenca_error():
    responses.add(responses.POST, f"{URL}/Login", json={}, status=200)
    responses.add(responses.PATCH, f"{URL}/Orders(1)", status=401)
    responses.add(responses.POST, f"{URL}/Login", json={}, status=200)
    responses.add(responses.PATCH, f"{URL}/Orders(1)", status=401)  # 2n 401

    c = _make_client()
    with pytest.raises(SLError) as exc:
        c.patch_order(1, {"foo": "bar"})
    assert exc.value.status_code == 401
    assert "persistent" in str(exc.value).lower()


# ============================================================
# Retries: 5xx amb backoff
# ============================================================

@responses.activate
def test_5xx_reintent_amb_backoff():
    responses.add(responses.POST, f"{URL}/Login", json={}, status=200)
    # 3 PATCH: 500, 502, 204 (èxit al 3r)
    responses.add(responses.PATCH, f"{URL}/Orders(1)", status=500)
    responses.add(responses.PATCH, f"{URL}/Orders(1)", status=502)
    responses.add(responses.PATCH, f"{URL}/Orders(1)", status=204)

    c = _make_client()  # backoff_base_sec=0 en tests, sense esperes reals
    c.patch_order(1, {"foo": "bar"})

    # 4 crides: Login + 3 PATCH (últim OK)
    assert len(responses.calls) == 4


@responses.activate
def test_5xx_persistent_llenca_error():
    responses.add(responses.POST, f"{URL}/Login", json={}, status=200)
    for _ in range(3):
        responses.add(responses.PATCH, f"{URL}/Orders(1)", status=503)

    c = _make_client()
    with pytest.raises(SLError) as exc:
        c.patch_order(1, {"foo": "bar"})
    assert exc.value.status_code == 503


# ============================================================
# 404 → SLNotFoundError
# ============================================================

@responses.activate
def test_404_llenca_slnotfounderror():
    responses.add(responses.POST, f"{URL}/Login", json={}, status=200)
    responses.add(responses.PATCH, f"{URL}/Orders(999)", json={"error": "not found"}, status=404)

    c = _make_client()
    with pytest.raises(SLNotFoundError) as exc:
        c.patch_order(999, {"foo": "bar"})
    assert exc.value.status_code == 404


# ============================================================
# Altres 4xx: propaguen SLError amb status
# ============================================================

@responses.activate
def test_400_propaga_slerror():
    responses.add(responses.POST, f"{URL}/Login", json={}, status=200)
    responses.add(responses.PATCH, f"{URL}/Orders(1)",
                  json={"error": "bad request"}, status=400)

    c = _make_client()
    with pytest.raises(SLError) as exc:
        c.patch_order(1, {"foo": "bar"})
    assert exc.value.status_code == 400
    assert not isinstance(exc.value, SLNotFoundError)


# ============================================================
# patch_order: verificar payload
# ============================================================

@responses.activate
def test_patch_order_envia_payload_correcte():
    responses.add(responses.POST, f"{URL}/Login", json={}, status=200)
    responses.add(responses.PATCH, f"{URL}/Orders(1234)", status=204)

    payload = {
        "U_FCCalcular": "N",
        "U_FCEmbalatgeResum": "3 palets · 120 sacs · CALCULAT",
        "U_FCEmbalatgeEstat": "CALCULAT",
    }
    c = _make_client()
    c.patch_order(1234, payload)

    # Verificar body enviat
    import json
    patch_call = responses.calls[1].request
    assert patch_call.method == "PATCH"
    assert patch_call.url == f"{URL}/Orders(1234)"
    body = json.loads(patch_call.body)
    assert body == payload


# ============================================================
# Reutilització de sessió i seguretat entre fils
# ============================================================
# Context: fins al 29-09-2026 `app.py` creava un SLClient per petició amb
# `with SLClient(...)`, o sigui un login i un logout per cada clic del botó
# B1UP. Amb Gunicorn servint peticions de debò en paral·lel, un smoke test de 8
# concurrents va deixar 5 respostes 502: el Service Layer no aguanta 8 logins
# simultanis i vencien als 15 s. Ara el client és un singleton per procés i
# serialitza el seu ús amb un RLock. Veure `tasks/lessons.md` L13.

@responses.activate
def test_peticions_successives_reutilitzen_la_sessio():
    """Un sol login per moltes peticions: el cas que abans costava un login cada cop."""
    responses.add(responses.POST, f"{URL}/Login", json={}, status=200)
    for _ in range(5):
        responses.add(responses.PATCH, f"{URL}/Orders(1)", status=204)

    c = _make_client()
    for _ in range(5):
        c.patch_order(1, {"U_FCAfegit": "S"})

    logins = [call for call in responses.calls if call.request.url == f"{URL}/Login"]
    assert len(logins) == 1, "s'hauria de fer login una sola vegada"


def test_request_concurrent_fa_un_sol_login():
    """N fils alhora sobre el mateix client → un únic login, no N."""
    import threading

    c = _make_client()
    logins = []
    barrera = threading.Barrier(6)

    def fake_login():
        # Simula la latència real del login per maximitzar la finestra de cursa.
        time.sleep(0.05)
        logins.append(1)
        c._session = object()          # qualsevol cosa no-None
        c._session_ts = time.monotonic()

    def fake_request_locked(method, path, json_body=None):
        c._ensure_session()
        return "ok"

    with patch.object(c, "login", side_effect=fake_login), \
         patch.object(c, "_request_locked", side_effect=fake_request_locked):
        def worker():
            barrera.wait()             # tots els fils surten alhora
            c._request("GET", "Orders(1)")

        fils = [threading.Thread(target=worker) for _ in range(5)]
        for f in fils:
            f.start()
        barrera.wait()
        for f in fils:
            f.join(timeout=5)

    assert len(logins) == 1, f"esperava 1 login, n'hi ha hagut {len(logins)}"


def test_replace_marked_lines_no_interleaving_entre_fils():
    """El read-modify-write de les línies és atòmic per client.

    Sense el lock, dos fils podrien fer el GET abans que cap hagués fet el
    PATCH, llegir el mateix estat i escriure línies duplicades — el bug del
    commit 1b3c6d6.
    """
    import threading

    c = _make_client()
    c._session = object()
    c._session_ts = time.monotonic()

    traça: list[str] = []
    traça_lock = threading.Lock()

    def fake_locked(doc_entry, *a, **kw):
        with traça_lock:
            traça.append(f"inici-{doc_entry}")
        time.sleep(0.05)               # finestra ampla per interleaving
        with traça_lock:
            traça.append(f"fi-{doc_entry}")
        return {"added": 0, "updated": 0, "removed": 0, "kept": 0}

    with patch.object(c, "_replace_marked_lines_locked", side_effect=fake_locked):
        fils = [
            threading.Thread(
                target=c.replace_marked_lines,
                args=(n, "U_FCAfegit", "S", []),
            )
            for n in range(1, 4)
        ]
        for f in fils:
            f.start()
        for f in fils:
            f.join(timeout=5)

    # Cada inici ha d'anar seguit del seu propi fi: cap solapament.
    assert len(traça) == 6, traça
    for i in range(0, 6, 2):
        doc = traça[i].split("-")[1]
        assert traça[i] == f"inici-{doc}", traça
        assert traça[i + 1] == f"fi-{doc}", traça


def test_app_reutilitza_el_mateix_client_entre_peticions():
    """`app._sl_client()` ha de retornar sempre la mateixa instància."""
    import os

    entorn = {
        "SAP_SL_URL": URL,
        "SAP_SL_COMPANY": COMPANY,
        "SAP_SL_USER": USER,
        "SAP_SL_PASSWORD": PWD,
        "SAP_SL_VERIFY_SSL": "false",
        "SAP_SL_TIMEOUT": "5",
    }
    with patch.dict(os.environ, entorn):
        import app as app_mod

        anterior = app_mod._sl_singleton
        app_mod._sl_singleton = None
        try:
            primer = app_mod._sl_client()
            segon = app_mod._sl_client()
            assert primer is segon
            assert isinstance(primer, SLClient)
        finally:
            app_mod._sl_singleton = anterior
