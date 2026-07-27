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
