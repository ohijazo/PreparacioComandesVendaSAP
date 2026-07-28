"""Tests per _palet_estoc_val de consultes.py (normalització d'ItemCode palet)."""
import consultes


def test_none_retorna_none():
    assert consultes._palet_estoc_val(None) is None


def test_string_buit_retorna_none():
    assert consultes._palet_estoc_val("") is None
    assert consultes._palet_estoc_val("   ") is None


def test_guio_retorna_none():
    assert consultes._palet_estoc_val("-") is None


def test_codi_normal_no_es_modifica():
    assert consultes._palet_estoc_val("01030") == "01030"
    assert consultes._palet_estoc_val("30150") == "30150"


def test_padding_defensiu_articles_palet_sense_zero():
    """Alguns articles a SAP tenen U_SEIPaletProd sense el zero inicial
    (ex: '1030' en lloc de '01030'). Cal afegir el zero perquè SAP el
    reconegui com a ItemCode vàlid a OITM."""
    assert consultes._palet_estoc_val("1030") == "01030"
    assert consultes._palet_estoc_val("1010") == "01010"
    assert consultes._palet_estoc_val("1060") == "01060"


def test_padding_nomes_si_comenca_per_1_i_4_digits():
    """No modifiquem valors que no siguin del patró palet fusta (1xxx)."""
    assert consultes._palet_estoc_val("2030") == "2030"    # no comença per 1
    assert consultes._palet_estoc_val("103") == "103"      # 3 dígits
    assert consultes._palet_estoc_val("10300") == "10300"  # 5 dígits, ja té zero al final
    assert consultes._palet_estoc_val("1A30") == "1A30"    # no numèric
