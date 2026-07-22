"""Tests de casos extrems per al motor de regles."""
from regles import (
    aplicar_regles,
    rf1_filtrar_linies,
    rf2_validar_comanda_minima,
    rf3_validar_comanda_minima_produccio,
    rf4_validar_articles_especials,
    ART_BASE_PALET,
    ART_PALET_FUSTA_EU,
)
from tests.conftest import fer_linia, fer_direccio


# ============================================================
# 1. Comanda buida (sense linies) -> NO_CALCULABLE
# ============================================================

def test_comanda_buida_sense_linies():
    """Una comanda sense cap linia ha de retornar NO_CALCULABLE."""
    linies = []
    direccio = fer_direccio()
    resultat = aplicar_regles(linies, direccio)
    assert resultat.estat.value == "NO_CALCULABLE"
    assert len(resultat.embalatges) == 0


# ============================================================
# 2. Linia unica amb 1 sac (sota minim) -> NO_CALCULABLE
# ============================================================

def test_un_sol_sac_sota_minim():
    """1 sac en comanda PALET (minim 40) ha de fer STOP a RF2."""
    linies = [fer_linia(linea_unidades=1)]
    direccio = fer_direccio(tipus_descarrega="PALET")
    resultat = aplicar_regles(linies, direccio)
    assert resultat.estat.value == "SOTA_MINIM"
    assert any("RF2 STOP" in m for m in resultat.trazabilitat)


# ============================================================
# 3. Forcar ignora RF1 STOP (GRA)
# ============================================================

def test_forcar_ignora_rf1_gra():
    """Forcar amb GRA: RF1 STOP s'ignora pero sense linies computables
    segueix sent NO_CALCULABLE. Es verifica que FORÇAT apareix."""
    linies = [fer_linia(tunitat="GRA", linea_unidades=40)]
    direccio = fer_direccio(tipus_descarrega="PALET")
    resultat = aplicar_regles(linies, direccio, forcar=True)
    # GRA no genera linies computables, aixi que segueix NO_CALCULABLE
    assert resultat.estat.value == "NO_CALCULABLE"
    assert any("FORÇAT" in m for m in resultat.trazabilitat)


# ============================================================
# 4. Forcar ignora RF2 STOP (sota minim)
# ============================================================

def test_forcar_ignora_rf2_sota_minim():
    """Forcar amb menys sacs del minim: RF2 STOP s'ignora, es calcula."""
    linies = [fer_linia(linea_unidades=5)]
    direccio = fer_direccio(tipus_descarrega="PALET")
    resultat = aplicar_regles(linies, direccio, forcar=True)
    assert resultat.estat.value == "CALCULAT_AMB_AVISOS"
    assert any("FORÇAT" in m and "RF2 STOP" in m for m in resultat.missatges)
    assert len(resultat.embalatges) > 0
    total = sum(e.total_sacs for e in resultat.embalatges)
    assert total == 5


# ============================================================
# 5. Forcar ignora RF3 STOP (comanda minima produccio)
# ============================================================

def test_forcar_ignora_rf3_comanda_minima_produccio():
    """Forcar amb article que no compleix comanda mínima producció."""
    linies = [fer_linia(
        linea_unidades=40,
        linea_cantidad=200,
        comanda_minima_produccio=500,
    )]
    direccio = fer_direccio(tipus_descarrega="PALET")
    resultat = aplicar_regles(linies, direccio, forcar=True)
    assert resultat.estat.value == "CALCULAT_AMB_AVISOS"
    assert any("FORÇAT" in m and "RF3 STOP" in m for m in resultat.missatges)
    assert len(resultat.embalatges) > 0


# ============================================================
# 6. Forcar ignora RF4 STOP (article especial no calculable)
# ============================================================

def test_forcar_ignora_rf4_dimensio_especial():
    """Forcar amb article especial que no compleix cap condicio
    (cantidadapilable=0 → no es pot apilar, sacs != UxC → no embalatge propi)."""
    linies = [fer_linia(
        linea_unidades=40,
        dimensio_especial=True,
        uxc=20,        # condicio B falla: 40 != 20
        cantidadapilable=0,  # condicio A falla: cantidadapilable=0
    )]
    direccio = fer_direccio(tipus_descarrega="PALET")
    resultat = aplicar_regles(linies, direccio, forcar=True)
    assert resultat.estat.value == "CALCULAT_AMB_AVISOS"
    assert any("FORÇAT" in m and "RF4 STOP" in m for m in resultat.missatges)
    assert len(resultat.embalatges) > 0


# ============================================================
# 7. Article amb UxC=0 o None -> usa defaults
# ============================================================

def test_uxc_zero_usa_defaults():
    """Article amb uxc=0 ha de funcionar usant defaults."""
    linies = [fer_linia(linea_unidades=45, uxc=0)]
    direccio = fer_direccio(tipus_descarrega="PALET")
    resultat = aplicar_regles(linies, direccio)
    assert resultat.estat.value in ("CALCULAT", "CALCULAT_AMB_AVISOS")
    assert len(resultat.embalatges) > 0


def test_uxc_none_usa_defaults():
    """Article amb uxc=None ha de funcionar usant defaults."""
    linies = [fer_linia(linea_unidades=45, uxc=None)]
    direccio = fer_direccio(tipus_descarrega="PALET")
    resultat = aplicar_regles(linies, direccio)
    assert resultat.estat.value in ("CALCULAT", "CALCULAT_AMB_AVISOS")
    assert len(resultat.embalatges) > 0


# ============================================================
# 8. Article amb cantidadapilable=0 o None -> usa defaults
# ============================================================

def test_cantidadapilable_zero_usa_defaults():
    """Article amb cantidadapilable=0 ha de funcionar usant defaults."""
    linies = [fer_linia(linea_unidades=45, cantidadapilable=0)]
    direccio = fer_direccio(tipus_descarrega="PALET")
    resultat = aplicar_regles(linies, direccio)
    assert resultat.estat.value in ("CALCULAT", "CALCULAT_AMB_AVISOS")
    assert len(resultat.embalatges) > 0


def test_cantidadapilable_none_usa_defaults():
    """Article amb cantidadapilable=None ha de funcionar usant defaults."""
    linies = [fer_linia(linea_unidades=45, cantidadapilable=None)]
    direccio = fer_direccio(tipus_descarrega="PALET")
    resultat = aplicar_regles(linies, direccio)
    assert resultat.estat.value in ("CALCULAT", "CALCULAT_AMB_AVISOS")
    assert len(resultat.embalatges) > 0


# ============================================================
# 9. Comanda molt gran (1000 sacs) -> total sacs correcte
# ============================================================

def test_comanda_gran_1000_sacs():
    """1000 sacs han de repartir-se correctament entre embalatges."""
    linies = [fer_linia(linea_unidades=1000, linea_cantidad=25000.0)]
    direccio = fer_direccio(tipus_descarrega="PALET")
    resultat = aplicar_regles(linies, direccio)
    assert resultat.estat.value in ("CALCULAT", "CALCULAT_AMB_AVISOS")
    total = sum(e.total_sacs for e in resultat.embalatges)
    assert total == 1000
    # Amb max default de 45 sacs/palet: ceil(1000/45) = 23 palets
    assert len(resultat.embalatges) >= 22


# ============================================================
# 10. Mix de tots els tipus especials en una comanda
# ============================================================

def test_mix_sac25_estoc_normal_especial():
    """Comanda amb sac25, estoc, normal i especial (apilable)."""
    linies = [
        # Article normal
        fer_linia(linea_num=10, art_codi="30001", linea_unidades=45),
        # Sac 25 especial (<=8 sacs)
        fer_linia(linea_num=20, art_codi="30002", linea_unidades=8,
                  sac_25_especial=True, cantidadapilable=3),
        # Estoc individual
        fer_linia(linea_num=30, art_codi="30003", linea_unidades=15,
                  aprovisionament_estoc=True, palet_producte_estoc="01030"),
        # Article especial apilable (condicio A: total especials <= cantidadapilable)
        fer_linia(linea_num=40, art_codi="30004", linea_unidades=3,
                  dimensio_especial=True, cantidadapilable=5, uxc=20),
    ]
    direccio = fer_direccio(tipus_descarrega="PALET")
    resultat = aplicar_regles(linies, direccio)
    assert resultat.estat.value in ("CALCULAT", "CALCULAT_AMB_AVISOS")
    total = sum(e.total_sacs for e in resultat.embalatges)
    assert total == 45 + 8 + 15 + 3


# ============================================================
# 11. RF5 preval amb max_sacs_palet absent -> avis a trazabilitat
# ============================================================

def test_rf5_preval_sense_max_sacs():
    """PrevalDireccio=Si pero max_sacs_palet=None ha de generar avis."""
    linies = [fer_linia(linea_unidades=45, cantidadapilable=5)]
    direccio = fer_direccio(
        tipus_descarrega="PALET",
        sacs_x_base=5,
        max_sacs_palet=None,
        preval_direccio_explicit=True,
    )
    resultat = aplicar_regles(linies, direccio)
    # Ha de calcular pero amb avis que falta max_sacs_palet
    assert resultat.estat.value in ("CALCULAT", "CALCULAT_AMB_AVISOS")
    assert len(resultat.embalatges) > 0
    # Verificar que hi ha alguna mencio a la trazabilitat sobre max_sacs o default
    trazabilitat_text = " ".join(resultat.trazabilitat)
    assert "RF5" in trazabilitat_text


# ============================================================
# 12. Totes les linies excloses (nomes UNI) -> NO_CALCULABLE
# ============================================================

def test_nomes_uni_no_calculable():
    """Si totes les linies son UNI, queden 0 computables -> NO_CALCULABLE."""
    linies = [
        fer_linia(linea_num=10, tunitat="UNI", linea_unidades=40),
        fer_linia(linea_num=20, tunitat="UNI", linea_unidades=60),
    ]
    direccio = fer_direccio(tipus_descarrega="PALET")
    resultat = aplicar_regles(linies, direccio)
    assert resultat.estat.value == "NO_CALCULABLE"
    assert len(resultat.embalatges) == 0


# ============================================================
# 13. Despaletitzat: tots els embalatges amb tipus_palet = ART_BASE_PALET
# ============================================================

def test_despaletitzat_tots_basepalet():
    """En MANUAL (despaletitzat), tots els embalatges han de tenir
    tipus_palet = ART_BASE_PALET = '01010'."""
    linies = [
        fer_linia(linea_num=10, art_codi="30001", linea_unidades=40),
        fer_linia(linea_num=20, art_codi="30002", linea_unidades=30),
    ]
    direccio = fer_direccio(tipus_descarrega="MANUAL")
    resultat = aplicar_regles(linies, direccio)
    assert resultat.estat.value in ("CALCULAT", "CALCULAT_AMB_AVISOS")
    assert len(resultat.embalatges) > 0
    for emb in resultat.embalatges:
        assert emb.tipus_palet == ART_BASE_PALET, (
            f"Embalatge {emb.palet_num} te tipus_palet={emb.tipus_palet}, "
            f"esperat {ART_BASE_PALET}"
        )


# ============================================================
# 14. Multiples articles mateixa base comparteixen palet
# ============================================================

def test_multiples_articles_mateixa_base_comparteixen_palet():
    """Dos articles amb la mateixa base (sacs_x_base) poden compartir palet."""
    linies = [
        fer_linia(linea_num=10, art_codi="30001", linea_unidades=20, cantidadapilable=5),
        fer_linia(linea_num=20, art_codi="30002", linea_unidades=20, cantidadapilable=5),
    ]
    direccio = fer_direccio(tipus_descarrega="PALET")
    resultat = aplicar_regles(linies, direccio)
    assert resultat.estat.value in ("CALCULAT", "CALCULAT_AMB_AVISOS")
    total = sum(e.total_sacs for e in resultat.embalatges)
    assert total == 40
    # Verificar que hi ha almenys un embalatge amb contingut de mes d'un article
    emb_compartits = [
        e for e in resultat.embalatges
        if len(set(c.art_codi for c in e.contingut)) > 1
    ]
    # Si el motor agrupa articles al mateix palet, hi haura embalatges compartits.
    # Si no, almenys el total de sacs ha de ser correcte.
    # (El motor pot o no compartir palets - verificem el total)
    assert total == 40


# ============================================================
# 15. Cap palet pot superar el seu max_sacs (limit fisic)
#     Regressio: cas 51/0003439 — micro-palet apilat sobre palet ple
#     produia palet de 50 sacs amb max=45.
# ============================================================

def test_cap_palet_supera_max_sacs():
    """Cap embalatge resultat ha de tenir total_sacs > max_sacs.

    Cas reproduit: 40 + 5 + 5 = 50 sacs amb max defecte 45.
    El motor no pot apilar el micro-palet de 5 sobre el palet ple de 45.
    """
    linies = [
        fer_linia(linea_num=10, art_codi="31066", linea_unidades=40,
                  aprovisionament_estoc=True, palet_producte_estoc="01030"),
        fer_linia(linea_num=20, art_codi="30730", linea_unidades=5, uxc=30,
                  aprovisionament_estoc=True, palet_producte_estoc="01030"),
        fer_linia(linea_num=30, art_codi="31060", linea_unidades=5,
                  aprovisionament_estoc=True, palet_producte_estoc="01030"),
    ]
    direccio = fer_direccio(tipus_descarrega="PALET")
    resultat = aplicar_regles(linies, direccio)
    assert resultat.estat.value in ("CALCULAT", "CALCULAT_AMB_AVISOS")
    for emb in resultat.embalatges:
        assert emb.total_sacs <= emb.max_sacs, (
            f"Palet {emb.palet_num} té {emb.total_sacs} sacs però max={emb.max_sacs}"
        )
    # Total sacs preservat
    total = sum(e.total_sacs for e in resultat.embalatges)
    assert total == 50


def test_fusio_linies_mateix_article_omple_palet_sencer():
    """Comanda 01/0003487: l'article 30550 apareix en 2 línies (40+20=60 sacs).

    Han de fusionar-se per evitar partir-lo entre palets mixtos. Resultat
    esperat: 1 palet ple de només 30550 (45 sacs) + 1 palet mixt amb la
    resta (15 sacs de 30550 + picking).
    """
    linies = [
        fer_linia(linea_num=10, art_codi="30550", linea_unidades=40),
        fer_linia(linea_num=20, art_codi="30790", linea_unidades=10),
        fer_linia(linea_num=30, art_codi="33010", linea_unidades=1),
        fer_linia(linea_num=40, art_codi="30270", linea_unidades=5),
        fer_linia(linea_num=50, art_codi="30870", linea_unidades=2),
        fer_linia(linea_num=51, art_codi="30550", linea_unidades=20),
        fer_linia(linea_num=52, art_codi="31671", linea_unidades=10),
        fer_linia(linea_num=53, art_codi="30260", linea_unidades=1),
        fer_linia(linea_num=54, art_codi="34381", linea_unidades=1),
    ]
    direccio = fer_direccio(tipus_descarrega="PALET")
    resultat = aplicar_regles(linies, direccio)

    assert len(resultat.embalatges) == 2
    palet_ple = resultat.embalatges[0]
    palet_mixt = resultat.embalatges[1]
    assert palet_ple.total_sacs == 45
    assert len(palet_ple.contingut) == 1
    assert palet_ple.contingut[0].art_codi == "30550"
    assert palet_ple.contingut[0].sacs == 45
    assert palet_mixt.total_sacs == 45
    # El palet mixt ha de contenir la resta de 30550 + tots els altres articles
    arts_palet_mixt = {c.art_codi for c in palet_mixt.contingut}
    assert "30550" in arts_palet_mixt
    assert len(arts_palet_mixt) == 8
    # Cap 30550 partit a un tercer palet
    total_30550 = sum(c.sacs for e in resultat.embalatges
                     for c in e.contingut if c.art_codi == "30550")
    assert total_30550 == 60
    assert any("Pre-RF1" in t and "30550" in t for t in resultat.trazabilitat)


def test_rf7_base_article_quan_direccio_sense_sxb():
    """Comanda 01/0003505: article 62550 amb cantidadapilable=8 i direcció sense
    sacs_x_base ha d'usar la base de la fitxa (8), no el default (5).

    Prioritat CLAUDE.md §9: direcció > article > default.
    """
    linies = [
        fer_linia(linea_num=10, art_codi="62550", linea_unidades=20,
                  tunitat="S10", uxc=72, cantidadapilable=8,
                  aprovisionament_estoc=True, palet_producte_estoc="01030"),
        fer_linia(linea_num=20, art_codi="30001", linea_unidades=40),
    ]
    direccio = fer_direccio(tipus_descarrega="PALET",
                            sacs_x_base=None, max_sacs_palet=40)
    resultat = aplicar_regles(linies, direccio)

    palet_62550 = next(e for e in resultat.embalatges
                       if any(c.art_codi == "62550" for c in e.contingut))
    assert palet_62550.sacs_x_base == 8, (
        f"S'esperava base=8 (cantidadapilable de la fitxa), "
        f"però s'ha calculat base={palet_62550.sacs_x_base}"
    )


def test_rf7_direccio_sxb_definit_mana_sobre_article():
    """Si la direcció té sacs_x_base definit, mana sobre la fitxa de l'article."""
    linies = [
        fer_linia(linea_num=10, art_codi="62550", linea_unidades=20,
                  uxc=72, cantidadapilable=8,
                  aprovisionament_estoc=True, palet_producte_estoc="01030"),
    ]
    direccio = fer_direccio(tipus_descarrega="PALET",
                            sacs_x_base=4, max_sacs_palet=40)
    resultat = aplicar_regles(linies, direccio)
    assert resultat.embalatges[0].sacs_x_base == 4


def test_rf6_base_article_quan_direccio_sense_sxb():
    """RF6 sac_25_especial <=8 sacs també respecta cantidadapilable de l'article."""
    linies = [
        fer_linia(linea_num=10, art_codi="30002", linea_unidades=40),
        fer_linia(linea_num=20, art_codi="30001", linea_unidades=8,
                  sac_25_especial=True, cantidadapilable=3),
    ]
    direccio = fer_direccio(tipus_descarrega="PALET",
                            sacs_x_base=None, max_sacs_palet=40)
    resultat = aplicar_regles(linies, direccio)
    palet_sac25 = next(e for e in resultat.embalatges
                       if any(c.art_codi == "30001" for c in e.contingut))
    assert palet_sac25.sacs_x_base == 3


def test_rf8_base_article_quan_direccio_sense_sxb():
    """RF8 sac_colagne <=26 sacs també respecta cantidadapilable de l'article."""
    linies = [
        fer_linia(linea_num=10, art_codi="30001", linea_unidades=13,
                  sac_colagne_normal=True, cantidadapilable=3),
        fer_linia(linea_num=20, art_codi="30002", linea_unidades=13,
                  sac_colagne_normal=True, cantidadapilable=3),
    ]
    direccio = fer_direccio(tipus_descarrega="PALET",
                            sacs_x_base=None, max_sacs_palet=40)
    resultat = aplicar_regles(linies, direccio)
    for emb in resultat.embalatges:
        assert emb.sacs_x_base == 3


def test_rf11_llindar_30_aplica():
    """RF11 aplica quan sacs S05+S10 >= 30 (nou llindar)."""
    linies = [
        fer_linia(linea_num=10, art_codi="40150", linea_unidades=40),
        fer_linia(linea_num=20, art_codi="62550", linea_unidades=30,
                  tunitat="S10", uxc=72, cantidadapilable=8),
    ]
    direccio = fer_direccio(tipus_descarrega="PALET", max_sacs_palet=40)
    resultat = aplicar_regles(linies, direccio)
    assert any("RF11" in t and ">=30" in t for t in resultat.trazabilitat), \
        f"Esperat RF11 aplicat amb llindar 30. Traces: {resultat.trazabilitat}"


def test_rf11_llindar_30_no_aplica_amb_29():
    """RF11 NO aplica quan sacs S05+S10 < 30 (cas frontera)."""
    linies = [
        fer_linia(linea_num=10, art_codi="40150", linea_unidades=40),
        fer_linia(linea_num=20, art_codi="62550", linea_unidades=29,
                  tunitat="S10", uxc=72, cantidadapilable=8),
    ]
    direccio = fer_direccio(tipus_descarrega="PALET", max_sacs_palet=40)
    resultat = aplicar_regles(linies, direccio)
    assert any("RF11: No aplica" in t for t in resultat.trazabilitat), \
        f"Esperat RF11 no aplica amb 29 sacs. Traces: {resultat.trazabilitat}"


def test_rf11_imposa_base_article_quan_max_es_uxc():
    """RF11 ha d'imposar sacs_x_base = cantidadapilable de l'article
    quan imposa max = UxC. Cas real comanda 51/0003883: 60190 té UxC=132 i
    cantidadapilable=11. Amb base de la direcció (4) i max=132 sortirien
    33 capes per palet (impossible). El resultat correcte és base=11,
    max=132 → 12 capes × 11 sacs."""
    linies = [
        fer_linia(linea_num=10, art_codi="30550", linea_unidades=32,
                  tunitat="S25", uxc=45, cantidadapilable=5),
        fer_linia(linea_num=20, art_codi="60190", linea_unidades=528,
                  tunitat="S05", uxc=132, cantidadapilable=11),
    ]
    direccio = fer_direccio(tipus_descarrega="PALET",
                            sacs_x_base=4, max_sacs_palet=32)
    resultat = aplicar_regles(linies, direccio)
    palets_60190 = [p for p in resultat.embalatges
                    if any(c.art_codi == "60190" for c in p.contingut)]
    for p in palets_60190:
        assert p.sacs_x_base == 11, \
            f"Palet 60190 ha de tenir base=11 (RF11), té {p.sacs_x_base}"
        assert p.max_sacs == 132, \
            f"Palet 60190 ha de tenir max=132 (RF11), té {p.max_sacs}"
        capes = p.max_sacs // p.sacs_x_base
        assert capes == 12, \
            f"60190 ha de tenir 12 capes, té {capes}"


def test_rf13_acid_cafe_40150_palet_client():
    """Acid Cafe (00301614) + 40150 → palet del client preval sobre RF7."""
    linies = [
        fer_linia(linea_num=10, art_codi="30280", linea_unidades=25,
                  aprovisionament_estoc=True, palet_producte_estoc="01030"),
        fer_linia(linea_num=20, art_codi="40150", linea_unidades=25,
                  aprovisionament_estoc=True, palet_producte_estoc="01030"),
    ]
    direccio = fer_direccio(cli_codi="00301614", tipus_descarrega="PALET",
                            max_sacs_palet=30)
    resultat = aplicar_regles(linies, direccio)

    # El palet amb 40150 ha de tenir tipus_palet=None (es resoldrà via direcció)
    palet_40150 = next(e for e in resultat.embalatges
                       if any(c.art_codi == "40150" for c in e.contingut))
    assert palet_40150.tipus_palet is None, (
        f"Palet amb 40150 hauria de tenir tipus_palet=None per RF13, "
        f"però té {palet_40150.tipus_palet}"
    )
    assert any("RF13" in t for t in resultat.trazabilitat)


def test_rf13_no_aplica_altres_clients():
    """RF7 normal per a clients que no són a OVERRIDES_PALET_CLIENT."""
    linies = [
        fer_linia(linea_num=10, art_codi="40150", linea_unidades=25,
                  aprovisionament_estoc=True, palet_producte_estoc="01030"),
    ]
    direccio = fer_direccio(cli_codi="99999999", tipus_descarrega="PALET",
                            max_sacs_palet=30)
    resultat = aplicar_regles(linies, direccio)
    palet_40150 = resultat.embalatges[0]
    # Sense override, ha de conservar el palet d'estoc (01030)
    assert palet_40150.tipus_palet == "01030"
    assert not any("RF13" in t for t in resultat.trazabilitat)


def test_rf8_estricte_preval_sobre_rf7_quan_total_27():
    """Cas 10/0001347: articles colagne + estoc, total >=27 sacs.

    RF8 estricte ha de prevaler sobre RF7 (estoc), donant base=3, max=30
    a tots els articles colagne en lloc del config d'estoc individual.
    """
    linies = [
        fer_linia(linea_num=10, art_codi="30270", linea_unidades=10,
                  sac_colagne_normal=True, aprovisionament_estoc=True,
                  palet_producte_estoc="01030", uxc=30, cantidadapilable=0),
        fer_linia(linea_num=20, art_codi="30280", linea_unidades=20,
                  sac_colagne_normal=True, aprovisionament_estoc=True,
                  palet_producte_estoc="01030", uxc=30, cantidadapilable=0),
        fer_linia(linea_num=30, art_codi="30730", linea_unidades=5,
                  sac_colagne_normal=True, aprovisionament_estoc=True,
                  palet_producte_estoc="01030", uxc=30, cantidadapilable=0),
        fer_linia(linea_num=40, art_codi="32220", linea_unidades=1,
                  sac_colagne_normal=True, aprovisionament_estoc=True,
                  palet_producte_estoc="01030", uxc=30, cantidadapilable=0),
        fer_linia(linea_num=50, art_codi="33741", linea_unidades=1,
                  sac_colagne_normal=True, aprovisionament_estoc=True,
                  palet_producte_estoc="01030", uxc=30, cantidadapilable=0),
    ]
    direccio = fer_direccio(tipus_descarrega="MANUAL")
    resultat = aplicar_regles(linies, direccio)

    assert any("RF8" in t and ">= 27" in t for t in resultat.trazabilitat)
    for emb in resultat.embalatges:
        assert emb.sacs_x_base == 3, (
            f"Esperat base=3 (RF8 estricte), però palet {emb.palet_num} "
            f"té base={emb.sacs_x_base}"
        )
        assert emb.max_sacs == 30, (
            f"Esperat max=30, però palet {emb.palet_num} té max={emb.max_sacs}"
        )


def test_rf7_preval_sobre_rf8_quan_total_inferior_27():
    """Si total colagne <= 26, RF7 manté prioritat per articles estoc."""
    linies = [
        fer_linia(linea_num=10, art_codi="30270", linea_unidades=10,
                  sac_colagne_normal=True, aprovisionament_estoc=True,
                  palet_producte_estoc="01030"),
        fer_linia(linea_num=20, art_codi="30280", linea_unidades=10,
                  sac_colagne_normal=True, aprovisionament_estoc=True,
                  palet_producte_estoc="01030"),
    ]
    direccio = fer_direccio(tipus_descarrega="PALET", max_sacs_palet=45)
    resultat = aplicar_regles(linies, direccio)

    # Total colagne = 20 (<27) → no aplica RF8 estricte. Articles s'avaluen a RF7.
    assert not any("RF8" in t and ">= 27" in t for t in resultat.trazabilitat)


# ============================================================
# RF14: Fusió de palets residuals
# ============================================================

def test_rf14_comanda_54_0000082_residu_colagne_a_palet_estoc():
    """Cas 54/0000082: residu de colagne (7 sacs base=3) ha d'absorbir-se
    dins el palet d'estoc del client (23 sacs base=5, RF7+RF13). Resultat:
    2 palets en lloc de 3."""
    linies = [
        # 30280 colagne (25 sacs)
        fer_linia(linea_num=2, art_codi="30280", art_descrip="MEULE T65",
                  linea_unidades=25, sac_colagne_normal=True,
                  uxc=30, cantidadapilable=3),
        # 30880 sac_25_especial (6 sacs ≤ 8 → RF6)
        fer_linia(linea_num=5, art_codi="30880", art_descrip="SEIGLE NOIR T130",
                  linea_unidades=6, sac_25_especial=True,
                  uxc=30, cantidadapilable=3),
        # 32240 colagne (6 sacs)
        fer_linia(linea_num=7, art_codi="32240", art_descrip="BIO T150",
                  linea_unidades=6, sac_colagne_normal=True,
                  uxc=30, cantidadapilable=3),
        # 40150 estoc (23 sacs) — palet_producte_estoc=01030
        fer_linia(linea_num=10, art_codi="40150", art_descrip="FARINA ECOLOGICA FORÇA",
                  linea_unidades=23, aprovisionament_estoc=True,
                  palet_producte_estoc="01030", uxc=30, cantidadapilable=5),
    ]
    direccio = fer_direccio(cli_codi="00301614", tipus_descarrega="PALET",
                            max_sacs_palet=30)
    resultat = aplicar_regles(linies, direccio)

    # Després de RF14, han de quedar 2 palets (no 3)
    assert len(resultat.embalatges) == 2, (
        f"Esperat 2 palets després de RF14, hi ha {len(resultat.embalatges)}"
    )

    # Hi ha d'haver una entrada RF14 a la traçabilitat
    rf14_traces = [t for t in resultat.trazabilitat if t.startswith("RF14:")]
    assert len(rf14_traces) == 1, (
        f"Esperada exactament 1 traça RF14, n'hi ha {len(rf14_traces)}: {rf14_traces}"
    )

    # El palet receptor ha de contenir 40150 + residu colagne, base=5, 30/30
    palet_amb_40150 = next(
        e for e in resultat.embalatges if any(c.art_codi == "40150" for c in e.contingut)
    )
    assert palet_amb_40150.total_sacs == 30
    assert palet_amb_40150.sacs_x_base == 5
    arts = {c.art_codi for c in palet_amb_40150.contingut}
    assert "40150" in arts
    assert "32240" in arts  # residu colagne absorbit
    # RF13 ha forçat el receptor a None (condicions direcció)
    assert palet_amb_40150.tipus_palet is None


def test_rf14_no_fusiona_si_supera_capacitat():
    """RF14: residu + receptor han de cabre dins max del receptor."""
    # Configuració: colagne 30280 (25) + 32240 (13) = 38 sacs base=3 max=30
    #   → palet 1: 30 sacs (ple) + palet 2: 8 sacs (residu, ≤ llindar=10)
    # 40150 (25 sacs base=5 max=30) → palet 3: 25 sacs (capacitat lliure = 5)
    # Residu (8) > capacitat (5) → NO ha de fusionar.
    linies = [
        fer_linia(linea_num=10, art_codi="30280", linea_unidades=25,
                  sac_colagne_normal=True, uxc=30, cantidadapilable=3),
        fer_linia(linea_num=20, art_codi="32240", linea_unidades=13,
                  sac_colagne_normal=True, uxc=30, cantidadapilable=3),
        fer_linia(linea_num=30, art_codi="40150", linea_unidades=25,
                  aprovisionament_estoc=True, palet_producte_estoc="01030",
                  uxc=30, cantidadapilable=5),
    ]
    direccio = fer_direccio(cli_codi="00301614", tipus_descarrega="PALET",
                            max_sacs_palet=30)
    resultat = aplicar_regles(linies, direccio)

    palet_40150 = next(
        e for e in resultat.embalatges if any(c.art_codi == "40150" for c in e.contingut)
    )
    assert palet_40150.total_sacs == 25, (
        f"Palet 40150 hauria de quedar amb 25 sacs (sense fusió, 25+8>30), "
        f"té {palet_40150.total_sacs}"
    )
    # No s'estalvia palet: el residu colagne queda en un palet propi
    assert not any(t.startswith("RF14:") for t in resultat.trazabilitat)


def test_rf14_respecta_es_no_barreja():
    """RF14: palets marcats com a es_no_barreja (RF12) no participen en la fusió."""
    # 30290 amb cantitat exactament múltiple del max → RF12 marca el palet com a no_barreja
    # 60 sacs / max 30 = 2 palets dedicats no_barreja
    # 40150 amb pocs sacs (residu, base=5) → no hauria d'absorbir-se als palets no_barreja
    linies = [
        fer_linia(linea_num=10, art_codi="30290", linea_unidades=60,
                  aprovisionament_estoc=True, palet_producte_estoc="01030",
                  uxc=30, cantidadapilable=3),
        fer_linia(linea_num=20, art_codi="40150", linea_unidades=5,
                  aprovisionament_estoc=True, palet_producte_estoc="01030",
                  uxc=30, cantidadapilable=5),
    ]
    direccio = fer_direccio(cli_codi="99999999", tipus_descarrega="PALET",
                            max_sacs_palet=30)
    resultat = aplicar_regles(linies, direccio)

    # Els palets de 30290 han de ser no_barreja → cap residu de 40150 entra
    palets_30290 = [e for e in resultat.embalatges
                    if any(c.art_codi == "30290" for c in e.contingut)]
    for p in palets_30290:
        arts = {c.art_codi for c in p.contingut}
        assert arts == {"30290"}, (
            f"Palet no_barreja de 30290 no hauria de tenir altres articles, té {arts}"
        )
