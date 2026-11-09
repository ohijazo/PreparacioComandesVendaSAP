"""Fallback de _resolver_tipus_palet segons el tipus de descàrrega.

Cas 51/0008502 (FORN DE PA LUNA): direcció amb descàrrega PALET, sense palet a
PREUSCLIENTS ni a la comanda → el motor proposava BasePalet (lògic), incoherent
amb una descàrrega paletitzada.
"""
import pytest

import motor
from models import Estat, Resultat
from regles import ART_BASE_PALET, ART_PALET_FUSTA_EU
from tests.conftest import fer_direccio


@pytest.fixture
def sense_palet(monkeypatch):
    monkeypatch.setattr(motor, "obtenir_palet_client", lambda *a, **k: None)
    monkeypatch.setattr(motor, "obtenir_palet_comanda", lambda *a, **k: None)
    monkeypatch.setattr(motor, "obtenir_descrip_article", lambda conn, art: f"DESC {art}")


def test_descarrega_palet_fallback_europeu_amb_avis(sense_palet):
    resultat = Resultat(estat=Estat.CALCULAT)
    tipus, origen, es_fisic = motor._resolver_tipus_palet(
        None, "51", "0008502", resultat, fer_direccio(tipus_descarrega="PALET"))

    assert tipus["art_codi"] == ART_PALET_FUSTA_EU
    assert es_fisic is True
    assert "palet europeu" in origen
    assert resultat.estat == Estat.CALCULAT_AMB_AVISOS
    assert any("palet del client" in m for m in resultat.missatges)


def test_descarrega_manual_fallback_basepalet(sense_palet):
    resultat = Resultat(estat=Estat.CALCULAT)
    tipus, _, es_fisic = motor._resolver_tipus_palet(
        None, "51", "0008502", resultat, fer_direccio(tipus_descarrega="MANUAL"))

    assert tipus["art_codi"] == ART_BASE_PALET
    assert es_fisic is False
    assert resultat.estat == Estat.CALCULAT
    assert resultat.missatges == []
