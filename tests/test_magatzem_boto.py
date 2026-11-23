"""El botó B1UP només calcula embalatges per a les línies del magatzem 01.

- `motor.calcular_embalatges(..., magatzems=...)` filtra les línies.
- `/api/afegir-palets/<doc_entry>` no toca les comandes sense cap línia del 01
  i posa les línies palet al 01.
"""
from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

import consultes
import motor
from tests.conftest import fer_linia, fer_direccio, fer_comanda


def _mock_motor(monkeypatch, linies, direccio):
    monkeypatch.setattr(motor, "connectar", lambda: SimpleNamespace(close=lambda: None))
    monkeypatch.setattr(motor, "obtenir_comanda", lambda *a, **k: fer_comanda())
    monkeypatch.setattr(motor, "obtenir_linies", lambda *a, **k: list(linies))
    monkeypatch.setattr(motor, "obtenir_direccio", lambda *a, **k: direccio)
    monkeypatch.setattr(motor, "obtenir_palet_client", lambda *a, **k: None)
    monkeypatch.setattr(motor, "obtenir_palet_comanda", lambda *a, **k: None)
    monkeypatch.setattr(motor, "obtenir_descrip_article", lambda conn, art: f"DESC {art}")


LINIES_MIXTES = [
    fer_linia(linea_num=0, art_codi="30001", linea_unidades=40.0, magatzem="01"),
    fer_linia(linea_num=1, art_codi="30002", linea_unidades=40.0, magatzem="05"),
]


def test_motor_filtra_linies_d_altres_magatzems(monkeypatch):
    _mock_motor(monkeypatch, LINIES_MIXTES, fer_direccio(tipus_descarrega="MANUAL"))

    r = motor.calcular_embalatges("268", "1", magatzems={"01"})

    assert [l.art_codi for l in r.linies] == ["30001"]
    assert sum(e.total_sacs for e in r.embalatges) == 40
    assert r.trazabilitat[0].startswith("MAGATZEM: 1 línies excloses")
    assert "30002 [05]" in r.trazabilitat[0]


def test_motor_sense_magatzems_calcula_totes_les_linies(monkeypatch):
    _mock_motor(monkeypatch, LINIES_MIXTES, fer_direccio(tipus_descarrega="MANUAL"))

    r = motor.calcular_embalatges("268", "1")

    assert len(r.linies) == 2
    assert sum(e.total_sacs for e in r.embalatges) == 80
    assert not any(t.startswith("MAGATZEM") for t in r.trazabilitat)


# ============================================================
# Endpoint
# ============================================================

@pytest.fixture
def app_mod(monkeypatch):
    """Importa `app` sense que el warmup obri una connexió real."""
    if "app" not in sys.modules:
        def _sense_bd():
            raise RuntimeError("sense BD als tests")
        monkeypatch.setattr(consultes, "connectar", _sense_bd)
    import app as app_mod
    monkeypatch.setattr(app_mod, "connectar", lambda: SimpleNamespace(close=lambda: None))
    monkeypatch.setattr(app_mod, "obtenir_preus_palets_client", lambda *a, **k: {})
    monkeypatch.setattr(app_mod, "obtenir_articles_palet", lambda conn: set())
    monkeypatch.setattr(app_mod, "invalidar_caches_comanda", lambda *a, **k: None)
    return app_mod


def _meta(magatzems):
    return {
        "series": "268", "docnum": "26600099", "card_code": "C281241",
        "addr": None, "doc_status": "O", "whs_code": "05", "magatzems": magatzems,
    }


def test_endpoint_comanda_d_altre_magatzem_no_es_toca(app_mod, monkeypatch):
    monkeypatch.setattr(app_mod, "obtenir_metadata_ordr_per_doc_entry",
                        lambda conn, de: _meta({"05"}))

    def _no_cridar(*a, **k):
        raise AssertionError("no s'ha de cridar")
    monkeypatch.setattr(app_mod, "calcular_embalatges", _no_cridar)
    monkeypatch.setattr(app_mod, "_sl_client", _no_cridar)

    resp = app_mod.app.test_client().post("/api/afegir-palets/99")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["estat"] == "NO_APLICA"
    assert body["linies_afegides"] == 0
    assert "magatzem 01" in body["missatges"][0]
    assert "magatzem 05" in body["missatges"][0]


def test_endpoint_comanda_01_calcula_i_posa_palets_al_01(app_mod, monkeypatch):
    # Primera línia del 05 (whs_code) però amb línies del 01: els palets van al 01.
    monkeypatch.setattr(app_mod, "obtenir_metadata_ordr_per_doc_entry",
                        lambda conn, de: _meta({"01", "05"}))

    crides = {}

    def _calcular(series, docnum, forcar=False, magatzems=None):
        crides["magatzems"] = magatzems
        return SimpleNamespace(
            estat=app_mod.Estat.CALCULAT,
            palets=[SimpleNamespace(art_codi="01030", quantitat=1, es_fisic=True)],
            embalatges=[SimpleNamespace(total_sacs=40)],
            trazabilitat=[], missatges=[],
        )
    monkeypatch.setattr(app_mod, "calcular_embalatges", _calcular)

    class _SL:
        def replace_marked_lines(self, doc_entry, field, value, new_lines, **kw):
            crides["linies"] = new_lines
            return {"added": len(new_lines), "updated": 0, "removed": 0, "kept": 0}
    monkeypatch.setattr(app_mod, "_sl_client", lambda: _SL())

    resp = app_mod.app.test_client().post("/api/afegir-palets/99")

    assert resp.status_code == 200
    assert resp.get_json()["estat"] == "CALCULAT"
    assert crides["magatzems"] == {"01"}
    assert [l["WarehouseCode"] for l in crides["linies"]] == ["01"]
