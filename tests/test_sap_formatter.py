"""Tests unitaris de `sap_formatter.formatar_resum`."""
from __future__ import annotations

import pytest

# _bootstrap ho fa conftest.py
from models import Estat, Resultat, Embalatge, PaletResum, PaletContingut

from sap_formatter import formatar_resum


# ============================================================
# Helpers
# ============================================================

def _embalatge(n_sacs=45, art_codi="30001"):
    return Embalatge(
        palet_num=1,
        contingut=[PaletContingut(art_codi=art_codi, art_descrip="X", sacs=n_sacs, sacs_x_base=5)],
        total_sacs=n_sacs,
        sacs_x_base=5,
        max_sacs=45,
    )


def _resultat(estat, embalatges=None, palets=None, missatges=None, trazabilitat=None):
    return Resultat(
        estat=estat,
        embalatges=embalatges or [],
        palets=palets or [],
        missatges=missatges or [],
        trazabilitat=trazabilitat or [],
    )


# ============================================================
# Estat CALCULAT
# ============================================================

def test_calculat_basic():
    r = _resultat(
        Estat.CALCULAT,
        embalatges=[_embalatge(45), _embalatge(45), _embalatge(30)],
        palets=[PaletResum(art_codi="01030", art_descrip="PALET EUROPEU", quantitat=3)],
    )
    resum, estat = formatar_resum(r)
    assert estat == "CALCULAT"
    assert "3 palets" in resum
    assert "120 sacs" in resum
    assert "3×palet europeu" in resum
    assert resum.endswith("· CALCULAT")


def test_calculat_multiples_tipus_palet():
    r = _resultat(
        Estat.CALCULAT,
        embalatges=[_embalatge(40) for _ in range(4)],
        palets=[
            PaletResum(art_codi="01030", art_descrip="PALET EUROPEU", quantitat=3),
            PaletResum(art_codi="01000", art_descrip="PALET NOU", quantitat=1),
        ],
    )
    resum, _ = formatar_resum(r)
    assert "3×palet europeu" in resum
    assert "1×palet nou" in resum


def test_calculat_sense_palets_resum_llista_buida():
    r = _resultat(
        Estat.CALCULAT,
        embalatges=[_embalatge(45)],
        palets=[],  # cap PaletResum
    )
    resum, _ = formatar_resum(r)
    # Sense info de palets, format degradat "N palets · N sacs · CALCULAT"
    assert resum == "1 palets · 45 sacs · CALCULAT"


def test_calculat_ignora_palets_logics():
    """Els palets amb es_fisic=False (BasePalet lògic) no compten al descrip."""
    r = _resultat(
        Estat.CALCULAT,
        embalatges=[_embalatge(20)],
        palets=[
            PaletResum(art_codi="01030", art_descrip="PALET EUROPEU", quantitat=1, es_fisic=True),
            PaletResum(art_codi="BASE", art_descrip="BASE LOGIC", quantitat=1, es_fisic=False),
        ],
    )
    resum, _ = formatar_resum(r)
    assert "1×palet europeu" in resum
    assert "base" not in resum.lower()


# ============================================================
# Estat CALCULAT_AMB_AVISOS
# ============================================================

def test_calculat_amb_avisos_afegeix_comptador():
    r = _resultat(
        Estat.CALCULAT_AMB_AVISOS,
        embalatges=[_embalatge(45)],
        palets=[PaletResum(art_codi="01030", art_descrip="PALET EUROPEU", quantitat=1)],
        trazabilitat=[
            "RF7: AVÍS — article amb aprovisionament sense palet definit",
            "RF12: sense incidències",
            "RF14: AVÍS — fusió no aplicable per capacitat",
        ],
    )
    resum, estat = formatar_resum(r)
    assert estat == "CALCULAT_AMB_AVISOS"
    assert "CALCULAT_AMB_AVISOS" in resum
    assert "2 avisos" in resum


# ============================================================
# Estat SOTA_MINIM
# ============================================================

def test_sota_minim_amb_motiu():
    r = _resultat(
        Estat.SOTA_MINIM,
        embalatges=[_embalatge(10)],
        missatges=["RF2: comanda amb 10 sacs, mínim 20. Falten 10 sacs."],
    )
    resum, estat = formatar_resum(r)
    assert estat == "SOTA_MINIM"
    assert resum.startswith("10 sacs · SOTA_MINIM")
    assert "RF2:" in resum


def test_sota_minim_sense_missatge():
    r = _resultat(
        Estat.SOTA_MINIM,
        embalatges=[_embalatge(5)],
        missatges=[],
    )
    resum, _ = formatar_resum(r)
    assert resum == "5 sacs · SOTA_MINIM"


# ============================================================
# Estat NO_CALCULABLE
# ============================================================

def test_no_calculable_amb_motiu():
    r = _resultat(
        Estat.NO_CALCULABLE,
        missatges=["RF1: comanda amb article granel (GRA), no processable"],
    )
    resum, estat = formatar_resum(r)
    assert estat == "NO_CALCULABLE"
    assert resum.startswith("NO CALCULABLE · ")
    assert "RF1:" in resum


def test_no_calculable_sense_missatge():
    r = _resultat(Estat.NO_CALCULABLE)
    resum, _ = formatar_resum(r)
    assert resum == "NO CALCULABLE"


# ============================================================
# Truncament a 254
# ============================================================

def test_truncament_a_254():
    """Si el resum excedeix 254 chars, es trunca amb el·lipsi."""
    missatge_llarg = "X" * 500
    r = _resultat(
        Estat.NO_CALCULABLE,
        missatges=[missatge_llarg],
    )
    resum, _ = formatar_resum(r)
    assert len(resum) <= 254
    assert resum.endswith("…")


def test_no_truncament_si_curt():
    r = _resultat(
        Estat.CALCULAT,
        embalatges=[_embalatge(45)],
        palets=[PaletResum(art_codi="01030", art_descrip="PALET EUROPEU", quantitat=1)],
    )
    resum, _ = formatar_resum(r)
    assert len(resum) < 100  # cas realista, ni de bon tros a 254
    assert not resum.endswith("…")


# ============================================================
# Missatge amb salts de línia i punts — retallar bé
# ============================================================

def test_primer_missatge_es_talla_al_primer_punt():
    r = _resultat(
        Estat.SOTA_MINIM,
        embalatges=[_embalatge(3)],
        missatges=["Primer motiu. Segon motiu que no volem veure. Tercer motiu."],
    )
    resum, _ = formatar_resum(r)
    assert "Primer motiu" in resum
    assert "Segon motiu" not in resum


def test_primer_missatge_es_talla_al_salt_de_linia():
    r = _resultat(
        Estat.NO_CALCULABLE,
        missatges=["Motiu principal\nDetall que no cal a la capçalera"],
    )
    resum, _ = formatar_resum(r)
    assert "Motiu principal" in resum
    assert "Detall" not in resum
