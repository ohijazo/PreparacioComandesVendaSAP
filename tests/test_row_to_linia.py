"""Tests per _row_to_linia de consultes.py — mapping de flags OITM a Linia.

Cobreix específicament la lectura dels QryGroup2/3/4 que ha canviat al fix
del 2026-07-29 (L6): `sac_colagne_normal` ara ve de QryGroup4 (llista
autoritativa 11 articles) i no del proxy per família comercial.
"""
from types import SimpleNamespace

import consultes


def _mock_row(**overrides):
    """Construeix una fila mock amb tots els camps que la SELECT retorna."""
    defaults = dict(
        linea_num=0,
        art_codi="30150",
        art_descrip="FARINA Nº1",
        linea_unidades=40,
        tunitat="S25",
        sal_pack_un=25,
        uxc=45,
        pes=25,
        cantidadapilable=5,
        palet_producte_estoc_raw=None,
        dimensio_especial_flag="N",
        sac_25_especial_flag="N",
        sac_colagne_flag="N",
        magatzem="01",
        series=1,
        docnum=1,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# ============================================================
# sac_colagne_normal via QryGroup4 (fix L6)
# ============================================================

def test_sac_colagne_normal_true_quan_qg4_es_Y():
    """Article amb OITM.QryGroup4='Y' → sac_colagne_normal=True."""
    row = _mock_row(art_codi="30270", sac_colagne_flag="Y")
    linia = consultes._row_to_linia(row)
    assert linia.sac_colagne_normal is True


def test_sac_colagne_normal_false_quan_qg4_es_N():
    """Article amb OITM.QryGroup4='N' → sac_colagne_normal=False."""
    row = _mock_row(art_codi="30820", sac_colagne_flag="N")
    linia = consultes._row_to_linia(row)
    assert linia.sac_colagne_normal is False


def test_sac_colagne_normal_false_quan_qg4_es_none():
    """QryGroup4 NULL/None → sac_colagne_normal=False (defensiu)."""
    row = _mock_row(sac_colagne_flag=None)
    linia = consultes._row_to_linia(row)
    assert linia.sac_colagne_normal is False


# ============================================================
# QryGroup2/3 (dimensio_especial + sac_25_especial) — mateix patró
# ============================================================

def test_dimensio_especial_via_qg2():
    row_y = _mock_row(dimensio_especial_flag="Y")
    row_n = _mock_row(dimensio_especial_flag="N")
    assert consultes._row_to_linia(row_y).dimensio_especial is True
    assert consultes._row_to_linia(row_n).dimensio_especial is False


def test_sac_25_especial_via_qg3():
    row_y = _mock_row(sac_25_especial_flag="Y")
    row_n = _mock_row(sac_25_especial_flag="N")
    assert consultes._row_to_linia(row_y).sac_25_especial is True
    assert consultes._row_to_linia(row_n).sac_25_especial is False
