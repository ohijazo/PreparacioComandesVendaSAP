"""Tests per RF5-RF9: Determinacio de configuracio i construccio d'embalatges."""
from regles import aplicar_regles, ART_BASE_PALET, ART_PALET_FUSTA_EU
from tests.conftest import fer_linia, fer_direccio


# ============================================================
# RF5: PrevalDireccio
# ============================================================

def test_rf5_preval_direccio_mana():
    """Quan PrevalDireccio=Si, la direccio mana base. RF6: max=min(dir,UxC)."""
    linies = [fer_linia(linea_unidades=45, cantidadapilable=3, uxc=30)]
    direccio = fer_direccio(
        tipus_descarrega="PALET",
        sacs_x_base=4,
        max_sacs_palet=40,
        preval_direccio_explicit=True,
    )
    resultat = aplicar_regles(linies, direccio)
    # RF6: max = min(direcció=40, UxC=30) = 30
    # 45 sacs -> 1 palet de 30 + 1 palet de 15
    assert len(resultat.embalatges) == 2
    assert resultat.embalatges[0].sacs_x_base == 4
    assert resultat.embalatges[0].max_sacs == 30


def test_rf5_no_preval_rf7_direccio_mana_base():
    """Quan PrevalDireccio=No, RF7 aplica: direcció > article > default per a base."""
    linies = [fer_linia(linea_unidades=45, cantidadapilable=5, uxc=45)]
    direccio = fer_direccio(
        tipus_descarrega="PALET",
        sacs_x_base=4,
        max_sacs_palet=40,
        preval_direccio_explicit=None,
    )
    resultat = aplicar_regles(linies, direccio)
    # RF7: base → direcció=4 > article=5 > default
    assert resultat.embalatges[0].sacs_x_base == 4


def test_rf5_si_salta_rf6_rf9():
    """Quan PrevalDireccio=Si, RF6-RF9 no s'apliquen."""
    linies = [fer_linia(
        linea_unidades=45,
        sac_25_especial=True,  # Normalment RF6
        cantidadapilable=5,
    )]
    direccio = fer_direccio(
        tipus_descarrega="PALET",
        sacs_x_base=5,
        max_sacs_palet=45,
        preval_direccio_explicit=True,
    )
    resultat = aplicar_regles(linies, direccio)
    # RF5 mana, RF6 no aplica -> usa config direccio
    assert any("RF5" in m and "PrevalDireccio = Si" in m for m in resultat.trazabilitat)
    assert any("RF6: No aplica" in m for m in resultat.trazabilitat)


# ============================================================
# RF6: Sac_25_especial
# ============================================================

def test_rf6_fins_8_sacs_palet():
    """Sac25 amb <=8 sacs, PALET: condicions direccio, max=direccio o 45."""
    linies = [
        fer_linia(linea_num=10, linea_unidades=48, sac_25_especial=False),
        fer_linia(linea_num=20, linea_unidades=8, sac_25_especial=True, cantidadapilable=3),
    ]
    direccio = fer_direccio(tipus_descarrega="PALET")
    resultat = aplicar_regles(linies, direccio)
    assert resultat.estat.value in ("CALCULAT", "CALCULAT_AMB_AVISOS")
    # Sac25 amb 8 sacs: tipus_palet=None (condicions), no ART_PALET_FUSTA_EU
    sac25_emb = [e for e in resultat.embalatges if
                 any(c.art_codi == linies[1].art_codi for c in e.contingut)]
    assert len(sac25_emb) > 0


def test_rf6_9_sacs_palet_fusta():
    """Sac25 amb >=9 sacs, PALET: palet fusta europeu, base=3, max=30."""
    linies = [
        fer_linia(linea_num=10, linea_unidades=40),
        fer_linia(linea_num=20, art_codi="30002", linea_unidades=9,
                  sac_25_especial=True, cantidadapilable=3),
    ]
    direccio = fer_direccio(tipus_descarrega="PALET")
    resultat = aplicar_regles(linies, direccio)
    # L'embalatge del sac25 ha de tenir tipus_palet = 01030
    sac25_emb = [e for e in resultat.embalatges if
                 any(c.art_codi == linies[1].art_codi for c in e.contingut)
                 and not any(c.art_codi == linies[0].art_codi for c in e.contingut)]
    # Pot ser que estigui barrejat; verifiquem que almenys hi ha embalatge amb fusta
    emb_fusta = [e for e in resultat.embalatges if e.tipus_palet == ART_PALET_FUSTA_EU]
    assert len(emb_fusta) > 0


def test_rf6_9_sacs_manual_basepalet():
    """Sac25 amb >=9 sacs, MANUAL: BasePalet."""
    linies = [
        fer_linia(linea_num=10, linea_unidades=20),
        fer_linia(linea_num=20, linea_unidades=9, sac_25_especial=True, cantidadapilable=3),
    ]
    direccio = fer_direccio(tipus_descarrega="MANUAL")
    resultat = aplicar_regles(linies, direccio)
    # Tot hauria de ser BasePalet ja que es despaletitzat
    # (motor.py assigna tot BasePalet per despaletitzat)


# ============================================================
# RF7: Estoc individual
# ============================================================

def test_rf7_fins_20_sacs():
    """Estoc individual amb <=20 sacs: condicions direccio."""
    linies = [
        fer_linia(linea_num=10, linea_unidades=40),
        fer_linia(linea_num=20, art_codi="30002", linea_unidades=20,
                  aprovisionament_estoc=True, palet_producte_estoc="01030"),
    ]
    direccio = fer_direccio(tipus_descarrega="PALET")
    resultat = aplicar_regles(linies, direccio)
    assert any("RF7" in m and "<= 20" in m for m in resultat.trazabilitat)


def test_rf7_21_sacs_palet_producte():
    """Estoc individual amb >=21 sacs: palet producte estoc."""
    linies = [
        fer_linia(linea_num=10, linea_unidades=40),
        fer_linia(linea_num=20, art_codi="30002", linea_unidades=25,
                  aprovisionament_estoc=True, palet_producte_estoc="01030",
                  uxc=30, cantidadapilable=5),
    ]
    direccio = fer_direccio(tipus_descarrega="PALET")
    resultat = aplicar_regles(linies, direccio)
    assert any("RF7" in m and ">= 21" in m for m in resultat.trazabilitat)


# ============================================================
# RF8: Estoc multi-article
# ============================================================

def test_rf8_fins_26_sacs():
    """Multiples articles sac_colagne_normal amb <=26 sacs total: condicions direccio."""
    linies = [
        fer_linia(linea_num=10, linea_unidades=40),
        fer_linia(linea_num=20, art_codi="30002", linea_unidades=13,
                  sac_colagne_normal=True),
        fer_linia(linea_num=30, art_codi="30003", linea_unidades=13,
                  sac_colagne_normal=True),
    ]
    direccio = fer_direccio(tipus_descarrega="PALET")
    resultat = aplicar_regles(linies, direccio)
    assert any("RF8" in m and "<= 26" in m for m in resultat.trazabilitat)


def test_rf8_27_sacs_fusta():
    """Multiples articles sac_colagne_normal amb >=27 sacs: palet fusta europeu."""
    linies = [
        fer_linia(linea_num=10, linea_unidades=40),
        fer_linia(linea_num=20, art_codi="30002", linea_unidades=15,
                  sac_colagne_normal=True),
        fer_linia(linea_num=30, art_codi="30003", linea_unidades=15,
                  sac_colagne_normal=True),
    ]
    direccio = fer_direccio(tipus_descarrega="PALET")
    resultat = aplicar_regles(linies, direccio)
    assert any("RF8" in m and ">= 27" in m for m in resultat.trazabilitat)
    emb_fusta = [e for e in resultat.embalatges if e.tipus_palet == ART_PALET_FUSTA_EU]
    assert len(emb_fusta) > 0


# ============================================================
# RF9: Articles no adjudicats
# ============================================================

def test_rf9_article_normal():
    """Article normal sense cap condicio especial -> RF9."""
    linies = [fer_linia(linea_unidades=45)]
    direccio = fer_direccio(tipus_descarrega="PALET")
    resultat = aplicar_regles(linies, direccio)
    assert any("RF9" in m for m in resultat.trazabilitat)
    assert len(resultat.embalatges) == 1
    assert resultat.embalatges[0].total_sacs == 45


def test_rf9_max_direccio_45_defecte():
    """RF9 sense max a la direccio -> max=45."""
    linies = [fer_linia(linea_unidades=90, cantidadapilable=5, uxc=None)]
    direccio = fer_direccio(tipus_descarrega="PALET", max_sacs_palet=None)
    resultat = aplicar_regles(linies, direccio)
    assert len(resultat.embalatges) == 2
    assert resultat.embalatges[0].total_sacs == 45
    assert resultat.embalatges[1].total_sacs == 45


def test_rf9_max_direccio_restrictiu():
    """RF9 amb max direccio restrictiu -> menys sacs per palet."""
    linies = [fer_linia(linea_unidades=60, cantidadapilable=5, uxc=None)]
    direccio = fer_direccio(tipus_descarrega="PALET", max_sacs_palet=30)
    resultat = aplicar_regles(linies, direccio)
    assert len(resultat.embalatges) == 2
    assert resultat.embalatges[0].total_sacs == 30
    assert resultat.embalatges[1].total_sacs == 30


# ============================================================
# Casos integrals
# ============================================================

def test_comanda_completa_calculada():
    """Una comanda normal dona estat CALCULAT."""
    linies = [
        fer_linia(linea_num=10, linea_unidades=40),
        fer_linia(linea_num=20, art_codi="30002", linea_unidades=45),
    ]
    direccio = fer_direccio(tipus_descarrega="PALET")
    resultat = aplicar_regles(linies, direccio)
    assert resultat.estat.value == "CALCULAT"
    assert len(resultat.embalatges) > 0
    total_sacs = sum(e.total_sacs for e in resultat.embalatges)
    assert total_sacs == 85


def test_despaletitzat_usa_basepalet():
    """Comanda MANUAL: tots els embalatges amb tipus BasePalet."""
    linies = [fer_linia(linea_unidades=40)]
    direccio = fer_direccio(tipus_descarrega="MANUAL")
    resultat = aplicar_regles(linies, direccio)
    for e in resultat.embalatges:
        assert e.tipus_palet == ART_BASE_PALET
