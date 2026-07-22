"""Tests per RF1: Filtre articles computables."""
from regles import rf1_filtrar_linies
from tests.conftest import fer_linia


def test_rf1_exclou_granel():
    """GRA ha de fer STOP."""
    linies = [fer_linia(tunitat="GRA")]
    computables, msgs, stop = rf1_filtrar_linies(linies)
    assert stop is True
    assert len(computables) == 0
    assert any("STOP" in m for m in msgs)


def test_rf1_exclou_unitari():
    """UNI s'exclou del calcul pero no fa STOP."""
    linies = [fer_linia(tunitat="UNI")]
    computables, msgs, stop = rf1_filtrar_linies(linies)
    assert stop is False
    assert len(computables) == 0


def test_rf1_inclou_sacs():
    """S05, S10, S15, S20, S25 son computables."""
    for tunitat in ("S05", "S10", "S15", "S20", "S25"):
        linies = [fer_linia(tunitat=tunitat)]
        computables, msgs, stop = rf1_filtrar_linies(linies)
        assert stop is False
        assert len(computables) == 1


def test_rf1_mix_granel_i_sacs():
    """Si hi ha GRA barrejat amb sacs, STOP."""
    linies = [
        fer_linia(linea_num=10, tunitat="S25"),
        fer_linia(linea_num=20, tunitat="GRA"),
    ]
    computables, msgs, stop = rf1_filtrar_linies(linies)
    assert stop is True


def test_rf1_compta_sacs_correctament():
    """El resum de sacs es correcte."""
    linies = [
        fer_linia(linea_num=10, linea_unidades=40),
        fer_linia(linea_num=20, linea_unidades=60),
    ]
    computables, msgs, stop = rf1_filtrar_linies(linies)
    assert len(computables) == 2
    assert any("total 100 sacs" in m for m in msgs)
