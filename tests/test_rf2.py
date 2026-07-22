"""Tests per RF2: Validacio comanda minima."""
from regles import rf2_validar_comanda_minima
from tests.conftest import fer_linia, fer_direccio


def test_rf2_palet_minim_40():
    """Comanda PALET amb menys de 40 sacs -> STOP."""
    linies = [fer_linia(linea_unidades=39)]
    direccio = fer_direccio(tipus_descarrega="PALET")
    msgs, stop = rf2_validar_comanda_minima(linies, direccio)
    assert stop is True


def test_rf2_palet_exacte_40():
    """Comanda PALET amb exactament 40 sacs -> OK."""
    linies = [fer_linia(linea_unidades=40)]
    direccio = fer_direccio(tipus_descarrega="PALET")
    msgs, stop = rf2_validar_comanda_minima(linies, direccio)
    assert stop is False


def test_rf2_manual_minim_20():
    """Comanda MANUAL amb menys de 20 sacs -> STOP."""
    linies = [fer_linia(linea_unidades=19)]
    direccio = fer_direccio(tipus_descarrega="MANUAL")
    msgs, stop = rf2_validar_comanda_minima(linies, direccio)
    assert stop is True


def test_rf2_manual_exacte_20():
    """Comanda MANUAL amb exactament 20 sacs -> OK."""
    linies = [fer_linia(linea_unidades=20)]
    direccio = fer_direccio(tipus_descarrega="MANUAL")
    msgs, stop = rf2_validar_comanda_minima(linies, direccio)
    assert stop is False


def test_rf2_excepcio_direccio():
    """Excepcio de minim a la direccio preval sobre el general."""
    linies = [fer_linia(linea_unidades=10)]
    direccio = fer_direccio(tipus_descarrega="PALET", sacs_comanda_minima=5)
    msgs, stop = rf2_validar_comanda_minima(linies, direccio)
    assert stop is False


def test_rf2_excepcio_direccio_no_arriba():
    """Excepcio de minim a la direccio, pero no arriba."""
    linies = [fer_linia(linea_unidades=3)]
    direccio = fer_direccio(tipus_descarrega="PALET", sacs_comanda_minima=5)
    msgs, stop = rf2_validar_comanda_minima(linies, direccio)
    assert stop is True


def test_rf2_multiples_linies():
    """Suma sacs de totes les linies."""
    linies = [
        fer_linia(linea_num=10, linea_unidades=25),
        fer_linia(linea_num=20, linea_unidades=25),
    ]
    direccio = fer_direccio(tipus_descarrega="PALET")
    msgs, stop = rf2_validar_comanda_minima(linies, direccio)
    assert stop is False  # 50 >= 40
