"""Tests per RF3: Validacio comanda minima produccio."""
from regles import rf3_validar_comanda_minima_produccio
from tests.conftest import fer_linia


def test_rf3_no_aplica_sense_minim():
    """Si cap article te comanda minima produccio, no aplica."""
    linies = [fer_linia(comanda_minima_produccio=None)]
    msgs, stop = rf3_validar_comanda_minima_produccio(linies)
    assert stop is False
    assert any("No aplica" in m for m in msgs)


def test_rf3_compleix_minim():
    """Article amb minim 500kg i comanda de 600kg -> OK."""
    linies = [fer_linia(comanda_minima_produccio=500, linea_cantidad=600)]
    msgs, stop = rf3_validar_comanda_minima_produccio(linies)
    assert stop is False


def test_rf3_no_compleix_minim():
    """Article amb minim 500kg i comanda de 400kg -> STOP."""
    linies = [fer_linia(comanda_minima_produccio=500, linea_cantidad=400)]
    msgs, stop = rf3_validar_comanda_minima_produccio(linies)
    assert stop is True
    assert any("STOP" in m for m in msgs)


def test_rf3_exacte_minim():
    """Article amb minim 500kg i exactament 500kg -> OK."""
    linies = [fer_linia(comanda_minima_produccio=500, linea_cantidad=500)]
    msgs, stop = rf3_validar_comanda_minima_produccio(linies)
    assert stop is False


def test_rf3_minim_300():
    """Article amb minim 300kg."""
    linies = [fer_linia(comanda_minima_produccio=300, linea_cantidad=250)]
    msgs, stop = rf3_validar_comanda_minima_produccio(linies)
    assert stop is True


def test_rf3_multiples_articles():
    """Cada article es valida individualment."""
    linies = [
        fer_linia(linea_num=10, comanda_minima_produccio=500, linea_cantidad=600),
        fer_linia(linea_num=20, comanda_minima_produccio=300, linea_cantidad=200),
    ]
    msgs, stop = rf3_validar_comanda_minima_produccio(linies)
    assert stop is True  # segon article no compleix
