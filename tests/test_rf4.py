"""Tests per RF4: Validacio articles especials."""
from regles import rf4_validar_articles_especials
from tests.conftest import fer_linia


def test_rf4_no_aplica_sense_especials():
    """Si no hi ha articles especials, no aplica."""
    linies = [fer_linia(dimensio_especial=False)]
    msgs, propis, apilables, normals, stop = rf4_validar_articles_especials(linies)
    assert stop is False
    assert len(normals) == 1
    assert len(propis) == 0
    assert len(apilables) == 0


def test_rf4_condicio_b_embalatge_propi():
    """Quantitat == UxC -> embalatge propi."""
    linies = [fer_linia(dimensio_especial=True, linea_unidades=20, uxc=20, cantidadapilable=5)]
    msgs, propis, apilables, normals, stop = rf4_validar_articles_especials(linies)
    assert stop is False
    assert len(propis) == 1
    assert len(apilables) == 0


def test_rf4_condicio_a_apilable():
    """Total sacs <= cantidadapilable -> apilable."""
    linies = [fer_linia(dimensio_especial=True, linea_unidades=3, uxc=20, cantidadapilable=5)]
    msgs, propis, apilables, normals, stop = rf4_validar_articles_especials(linies)
    assert stop is False
    assert len(propis) == 0
    assert len(apilables) == 1


def test_rf4_apilable_repartit():
    """Sacs > cantidadapilable pero cantidadapilable > 0 -> apilable (repartit)."""
    linies = [fer_linia(dimensio_especial=True, linea_unidades=10, uxc=20, cantidadapilable=5)]
    msgs, propis, apilables, normals, stop = rf4_validar_articles_especials(linies)
    assert stop is False
    assert len(apilables) == 1


def test_rf4_cap_condicio_stop():
    """cantidadapilable=0 i sacs != UxC -> STOP."""
    linies = [fer_linia(dimensio_especial=True, linea_unidades=10, uxc=20, cantidadapilable=0)]
    msgs, propis, apilables, normals, stop = rf4_validar_articles_especials(linies)
    assert stop is True


def test_rf4_mix_normal_i_especial():
    """Articles normals i especials es separen correctament."""
    linies = [
        fer_linia(linea_num=10, dimensio_especial=False, linea_unidades=40),
        fer_linia(linea_num=20, dimensio_especial=True, linea_unidades=20, uxc=20, cantidadapilable=5),
    ]
    msgs, propis, apilables, normals, stop = rf4_validar_articles_especials(linies)
    assert stop is False
    assert len(normals) == 1
    assert len(propis) == 1
    assert normals[0].linea_num == 10
