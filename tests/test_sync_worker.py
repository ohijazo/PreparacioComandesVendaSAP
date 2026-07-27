"""Tests unitaris de sync_worker.SyncWorker amb mocks."""
from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

import pytest

from sync_worker import SyncWorker, PassStats


# ============================================================
# Fixtures
# ============================================================

def _fake_resultat(estat_str="CALCULAT"):
    """Retorna un objecte que sembla un Resultat (usa MagicMock).

    Els tests no necessiten el Resultat real — el formatter està mockejat.
    """
    r = MagicMock()
    r.estat.value = estat_str
    return r


def _mk_worker(**overrides):
    """Crea un SyncWorker amb mocks per defecte, sobreescrivibles."""
    kwargs = dict(
        sl_client=MagicMock(),
        connectar_fn=MagicMock(return_value=MagicMock()),
        obtenir_comandes_fn=MagicMock(return_value=[]),
        calcular_fn=MagicMock(return_value=_fake_resultat()),
        formatar_fn=MagicMock(return_value=("resum test", "CALCULAT")),
        interval_sec=0.05,
        max_per_pass=50,
        dry_run=False,
    )
    kwargs.update(overrides)
    return SyncWorker(**kwargs)


# ============================================================
# Cas trivial: 0 comandes
# ============================================================

def test_cap_comanda_no_fa_res():
    w = _mk_worker(obtenir_comandes_fn=lambda conn: [])
    stats = w.run_one_pass()
    assert stats.trobades == 0
    assert stats.ok == 0
    assert stats.errors == []
    # No patch al SL
    w.sl_client.patch_order.assert_not_called()


# ============================================================
# Cas normal: 1 comanda OK
# ============================================================

def test_una_comanda_ok_fa_patch_amb_payload_correcte():
    comandes = [{"doc_entry": 42, "series": 268, "docnum": 12345, "card_code": "C001"}]
    w = _mk_worker(
        obtenir_comandes_fn=lambda conn: comandes,
        formatar_fn=lambda r: ("3 palets · 60 sacs · CALCULAT", "CALCULAT"),
    )
    stats = w.run_one_pass()

    assert stats.trobades == 1
    assert stats.ok == 1
    assert stats.error_motor == 0
    assert stats.error_patch == 0

    # Verifica el payload
    w.sl_client.patch_order.assert_called_once_with(42, {
        "U_FCCalcular": "N",
        "U_FCEmbalatgeResum": "3 palets · 60 sacs · CALCULAT",
        "U_FCEmbalatgeEstat": "CALCULAT",
    })


def test_multiples_comandes_cada_una_patch():
    comandes = [
        {"doc_entry": 1, "series": 268, "docnum": 1000, "card_code": "C001"},
        {"doc_entry": 2, "series": 268, "docnum": 1001, "card_code": "C002"},
        {"doc_entry": 3, "series": 268, "docnum": 1002, "card_code": "C003"},
    ]
    w = _mk_worker(obtenir_comandes_fn=lambda conn: comandes)
    stats = w.run_one_pass()
    assert stats.ok == 3
    assert w.sl_client.patch_order.call_count == 3


def test_respect_max_per_pass():
    comandes = [{"doc_entry": i, "series": 268, "docnum": i, "card_code": "C"} for i in range(10)]
    w = _mk_worker(obtenir_comandes_fn=lambda conn: comandes, max_per_pass=3)
    stats = w.run_one_pass()
    assert stats.trobades == 10  # totes trobades
    assert stats.ok == 3          # només 3 processades
    assert w.sl_client.patch_order.call_count == 3


# ============================================================
# Errors: motor peta
# ============================================================

def test_error_motor_no_atura_worker_i_marca_error_a_sap():
    comandes = [
        {"doc_entry": 1, "series": 268, "docnum": 1000, "card_code": "C1"},
        {"doc_entry": 2, "series": 268, "docnum": 1001, "card_code": "C2"},
    ]

    def calcular_side_effect(series, docnum, forcar):
        if docnum == "1000":
            raise ValueError("dades corruptes")
        return _fake_resultat()

    w = _mk_worker(
        obtenir_comandes_fn=lambda conn: comandes,
        calcular_fn=MagicMock(side_effect=calcular_side_effect),
    )
    stats = w.run_one_pass()

    assert stats.error_motor == 1
    assert stats.ok == 1
    assert len(stats.errors) == 1
    assert stats.errors[0]["doc_entry"] == 1
    assert "motor" in stats.errors[0]["msg"]

    # 2 patches: 1 d'error (DocEntry=1) + 1 OK (DocEntry=2)
    assert w.sl_client.patch_order.call_count == 2
    # Verifica el payload d'error
    error_call = w.sl_client.patch_order.call_args_list[0]
    assert error_call[0][0] == 1
    payload = error_call[0][1]
    assert payload["U_FCCalcular"] == "N"
    assert payload["U_FCEmbalatgeEstat"] == "ERROR"
    assert "dades corruptes" in payload["U_FCEmbalatgeResum"]


# ============================================================
# Errors: patch peta
# ============================================================

def test_error_patch_es_registra_pero_no_atura():
    comandes = [
        {"doc_entry": 1, "series": 268, "docnum": 1000, "card_code": "C1"},
        {"doc_entry": 2, "series": 268, "docnum": 1001, "card_code": "C2"},
    ]

    call_count = {"n": 0}
    def patch_side_effect(doc_entry, payload):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise ConnectionError("SAP no respon")

    sl = MagicMock()
    sl.patch_order.side_effect = patch_side_effect

    w = _mk_worker(
        obtenir_comandes_fn=lambda conn: comandes,
        sl_client=sl,
    )
    stats = w.run_one_pass()

    assert stats.error_patch == 1
    assert stats.ok == 1  # la 2a comanda sí passa
    assert len(stats.errors) == 1
    assert "patch" in stats.errors[0]["msg"]


def test_error_patch_no_intenta_patch_d_error_recursiu():
    """Si el patch normal peta, NO fem un patch d'error (evita loops)."""
    comandes = [{"doc_entry": 1, "series": 268, "docnum": 1000, "card_code": "C1"}]
    sl = MagicMock()
    sl.patch_order.side_effect = ConnectionError("SAP no respon")

    w = _mk_worker(obtenir_comandes_fn=lambda conn: comandes, sl_client=sl)
    stats = w.run_one_pass()

    assert stats.error_patch == 1
    # 1 sol intent de patch (el que ha petat). No cap patch d'error addicional.
    assert sl.patch_order.call_count == 1


# ============================================================
# dry_run
# ============================================================

def test_dry_run_no_fa_patches():
    comandes = [
        {"doc_entry": 1, "series": 268, "docnum": 1000, "card_code": "C1"},
        {"doc_entry": 2, "series": 268, "docnum": 1001, "card_code": "C2"},
    ]
    w = _mk_worker(obtenir_comandes_fn=lambda conn: comandes, dry_run=True)
    stats = w.run_one_pass()

    assert stats.ok == 2
    assert stats.dry_run is True
    w.sl_client.patch_order.assert_not_called()


def test_dry_run_error_motor_tampoc_patch():
    comandes = [{"doc_entry": 1, "series": 268, "docnum": 1000, "card_code": "C1"}]
    w = _mk_worker(
        obtenir_comandes_fn=lambda conn: comandes,
        calcular_fn=MagicMock(side_effect=RuntimeError("boom")),
        dry_run=True,
    )
    stats = w.run_one_pass()
    assert stats.error_motor == 1
    w.sl_client.patch_order.assert_not_called()


# ============================================================
# Connexió BD tancada correctament
# ============================================================

def test_conn_bd_es_tanca_sempre():
    conn_mock = MagicMock()
    w = _mk_worker(connectar_fn=lambda: conn_mock, obtenir_comandes_fn=lambda c: [])
    w.run_one_pass()
    conn_mock.close.assert_called_once()


def test_conn_bd_es_tanca_encara_que_obtenir_peti():
    conn_mock = MagicMock()
    w = _mk_worker(
        connectar_fn=lambda: conn_mock,
        obtenir_comandes_fn=MagicMock(side_effect=RuntimeError("DB down")),
    )
    with pytest.raises(RuntimeError):
        w.run_one_pass()
    conn_mock.close.assert_called_once()


# ============================================================
# run_forever amb stop_event
# ============================================================

def test_run_forever_s_atura_amb_stop_event():
    stop = threading.Event()
    w = _mk_worker(interval_sec=0.05, obtenir_comandes_fn=lambda c: [])

    th = threading.Thread(target=w.run_forever, kwargs={"stop_event": stop})
    th.start()
    time.sleep(0.15)  # 3 passades màxim
    stop.set()
    th.join(timeout=1.0)
    assert not th.is_alive()


def test_run_forever_continua_despres_de_petada_no_capturada():
    """Si run_one_pass() peta amb excepció, el loop no s'atura."""
    stop = threading.Event()
    calls = {"n": 0}

    def obtenir_side_effect(conn):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("primera passada peta")
        stop.set()  # atura al segon intent
        return []

    w = _mk_worker(interval_sec=0.05, obtenir_comandes_fn=obtenir_side_effect)
    th = threading.Thread(target=w.run_forever, kwargs={"stop_event": stop})
    th.start()
    # Marge: min-wait 0.1s + segona passada + petit buffer
    th.join(timeout=2.0)
    assert not th.is_alive()
    assert calls["n"] >= 2  # el loop va continuar després de la petada
