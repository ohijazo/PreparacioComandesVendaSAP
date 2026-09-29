"""Tests per RF4: Validacio articles especials."""
from regles import rf4_validar_articles_especials, aplicar_regles
from tests.conftest import fer_linia, fer_direccio


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


def test_rf4_apilament_no_perd_sacs_amb_overflow():
    """Regressio BUG #2: quan els palets base no basten per apilar tots els sacs
    respectant cantidadapilable, els sacs restants han de formar palets propis.
    Cas real: article B amb dimensio_especial=True, cantidadapilable=3 i 1200
    sacs sobre 50 palets d'article A perdia 900 sacs abans del fix."""
    linies = [
        fer_linia(linea_num=10, art_codi="A", art_descrip="ARTICLE A",
                  linea_unidades=1200, uxc=45, cantidadapilable=4,
                  aprovisionament_estoc=True),
        fer_linia(linea_num=20, art_codi="B", art_descrip="ARTICLE B",
                  linea_unidades=1200, uxc=45, cantidadapilable=3,
                  dimensio_especial=True, aprovisionament_estoc=True),
    ]
    direccio = fer_direccio(
        tipus_descarrega="PALET",
        sacs_x_base=4,
        max_sacs_palet=24,
        preval_direccio_explicit=True,
    )
    resultat = aplicar_regles(linies, direccio)

    sacs_a = sum(c.sacs for e in resultat.embalatges
                 for c in e.contingut if c.art_codi == "A")
    sacs_b = sum(c.sacs for e in resultat.embalatges
                 for c in e.contingut if c.art_codi == "B")
    assert sacs_a == 1200, f"Article A: {sacs_a} != 1200"
    assert sacs_b == 1200, f"Article B: {sacs_b} != 1200 (bug: se'n perden 900)"

    # Cap PaletContingut de B en palet mixt pot superar cantidadapilable=3
    for e in resultat.embalatges:
        for c in e.contingut:
            if c.art_codi == "B" and len(e.contingut) > 1:
                assert c.sacs <= 3, (
                    f"Palet {e.palet_num} té {c.sacs} sacs de B apilats "
                    f"(cantidadapilable=3 violat)"
                )


def test_rf4_apilament_sense_overflow_respecta_cantidadapilable():
    """Cas normal: hi ha prou palets base per apilar tots els sacs sense overflow.
    Cap palet mixt no ha de superar cantidadapilable per l'article apilat."""
    linies = [
        fer_linia(linea_num=10, art_codi="A", linea_unidades=1200, uxc=45,
                  cantidadapilable=4, aprovisionament_estoc=True),
        fer_linia(linea_num=20, art_codi="B", linea_unidades=100, uxc=45,
                  cantidadapilable=3, dimensio_especial=True,
                  aprovisionament_estoc=True),
    ]
    direccio = fer_direccio(
        tipus_descarrega="PALET",
        sacs_x_base=4,
        max_sacs_palet=24,
        preval_direccio_explicit=True,
    )
    resultat = aplicar_regles(linies, direccio)

    sacs_b = sum(c.sacs for e in resultat.embalatges
                 for c in e.contingut if c.art_codi == "B")
    assert sacs_b == 100

    for e in resultat.embalatges:
        for c in e.contingut:
            if c.art_codi == "B" and len(e.contingut) > 1:
                assert c.sacs <= 3


def test_rf4_apilament_no_supera_el_maxim_del_palet_receptor():
    """Regressio: els sacs apilats no poden desbordar el palet que els rep.

    Cas reportat per un usuari el 29-09-2026 (comanda del client C321531): 440
    sacs normals omplien exactament 11 palets de 40 (el maxim de la direccio) i
    els 15 sacs d'un article de dimensio especial s'apilaven igualment a sobre
    dels tres primers, que quedaven amb 45 sacs i max_sacs=40. El recompte donava
    11 palets en comptes de 12.
    """
    linies = [
        fer_linia(linea_num=10, art_codi="A", art_descrip="ARTICLE A",
                  linea_unidades=80, uxc=45, cantidadapilable=5),
        fer_linia(linea_num=20, art_codi="ESP", art_descrip="ARTICLE ESPECIAL",
                  linea_unidades=10, uxc=20, cantidadapilable=5,
                  dimensio_especial=True),
    ]
    direccio = fer_direccio(
        tipus_descarrega="PALET",
        sacs_x_base=5,
        max_sacs_palet=40,
        preval_direccio_explicit=True,
    )
    resultat = aplicar_regles(linies, direccio)

    # La invariant que es va trencar
    for e in resultat.embalatges:
        assert e.total_sacs <= e.max_sacs, (
            f"Palet {e.palet_num}: {e.total_sacs} sacs amb max={e.max_sacs}"
        )

    # 80 sacs d'A omplen 2 palets exactes; l'especial necessita un tercer palet
    assert len(resultat.embalatges) == 3, [
        (e.palet_num, e.total_sacs) for e in resultat.embalatges
    ]

    # Els 10 sacs especials van tots junts al palet nou, no repartits
    # sobre els palets plens
    palets_amb_esp = [e for e in resultat.embalatges
                      if any(c.art_codi == "ESP" for c in e.contingut)]
    assert len(palets_amb_esp) == 1
    assert palets_amb_esp[0].total_sacs == 10
    assert sum(c.sacs for e in resultat.embalatges
               for c in e.contingut if c.art_codi == "ESP") == 10


def test_rf4_apilament_omple_nomes_l_espai_lliure():
    """Si un palet te espai pero no per a tot, s'hi apila nomes el que hi cap.

    Complementa el test anterior: alla cap palet tenia espai, aqui n'hi ha un de
    mig buit. Verifica que el limit que mana es el menor entre cantidadapilable i
    l'espai lliure, i que la resta va a palets propis.
    """
    linies = [
        fer_linia(linea_num=10, art_codi="A", art_descrip="ARTICLE A",
                  linea_unidades=70, uxc=45, cantidadapilable=5),
        fer_linia(linea_num=20, art_codi="ESP", art_descrip="ARTICLE ESPECIAL",
                  linea_unidades=15, uxc=20, cantidadapilable=5,
                  dimensio_especial=True),
    ]
    direccio = fer_direccio(
        tipus_descarrega="PALET",
        sacs_x_base=5,
        max_sacs_palet=40,
        preval_direccio_explicit=True,
    )
    resultat = aplicar_regles(linies, direccio)

    for e in resultat.embalatges:
        assert e.total_sacs <= e.max_sacs, (
            f"Palet {e.palet_num}: {e.total_sacs} sacs amb max={e.max_sacs}"
        )

    # Cap sac especial no es perd pel cami
    assert sum(c.sacs for e in resultat.embalatges
               for c in e.contingut if c.art_codi == "ESP") == 15

    # En un palet mixt, l'article apilat no pot superar cantidadapilable
    for e in resultat.embalatges:
        if len(e.contingut) > 1:
            for c in e.contingut:
                if c.art_codi == "ESP":
                    assert c.sacs <= 5
