"""Granel = propietat 5 ("Es Granel") o unitat GRA/KG/KGS -> unitat "GRA".

A produccio el granel te SalUnitMsr 'KGS' (no 'GRA'); el motor (RF1) el
reconeix per "GRA", aixi que la unitat es normalitza on es llegeix.
"""
from unitats_sap import es_granel, tunitat_efectiva


def test_propietat5_es_granel_encara_que_la_unitat_sigui_kgs():
    assert tunitat_efectiva("KGS", "Y") == "GRA"
    assert tunitat_efectiva("KGS", "tYES") == "GRA"      # Service Layer


def test_unitats_de_granel_sense_propietat5():
    for u in ("GRA", "KG", "KGS", "kgs ", " Kg"):
        assert tunitat_efectiva(u, "N") == "GRA"


def test_sacs_i_unitats_no_canvien():
    assert tunitat_efectiva("S25", "N") == "S25"
    assert tunitat_efectiva("UNI", "tNO") == "UNI"
    assert tunitat_efectiva(None, None) == ""


def test_si_la_unitat_es_de_sacs_mana_la_unitat():
    # 32090 MEULE T80 COLAGNE: S25 + propietat 5 (error de dades a SAP). Va en
    # palets: decisio de l'Oscar del 10-11-2026.
    assert es_granel("S25", "Y") is False
    assert tunitat_efectiva("S25", "tYES") == "S25"


def test_propietat5_sense_unitat_es_granel():
    # ESPECIFICA TURRIS: propietat 5 i sense unitat de venda.
    assert tunitat_efectiva(None, "Y") == "GRA"
