"""Tests d'invalidació de caches de `consultes.py`.

El botó SAP ("Calcular embalatges") invalida abans de calcular perquè el
recàlcul vegi sempre les línies reals de la comanda. Com que la primera
vegada la comanda encara no és al cache, la direcció i el palet del client
només es poden localitzar si es passen `cli_codi`/`adr_codi`.
"""
import time

import consultes
from tests.conftest import fer_comanda


def _reset_caches():
    consultes._comanda_cache.clear()
    consultes._linies_cache.clear()
    consultes._direccio_cache.clear()
    consultes._palet_comanda_cache.clear()
    consultes._palet_client_cache.clear()


def test_invalida_direccio_i_palet_client_amb_cli_adr():
    _reset_caches()
    ara = time.time()
    consultes._direccio_cache[("C211304", "000-DESCAMPS-BESALU")] = (ara, object())
    consultes._palet_client_cache[("C211304", "000-DESCAMPS-BESALU")] = (ara, None)
    consultes._linies_cache[("", "268", "26600209")] = (ara, [])

    consultes.invalidar_caches_comanda(
        "268", "26600209",
        cli_codi="C211304", adr_codi="000-DESCAMPS-BESALU",
    )

    assert ("C211304", "000-DESCAMPS-BESALU") not in consultes._direccio_cache
    assert ("C211304", "000-DESCAMPS-BESALU") not in consultes._palet_client_cache
    assert ("", "268", "26600209") not in consultes._linies_cache


def test_invalida_direccio_via_cache_de_comanda():
    """Comportament previ (sense cli_codi/adr_codi): la direcció es localitza
    a través de la comanda cachejada."""
    _reset_caches()
    ara = time.time()
    cmd = fer_comanda(cli_codi="C299062", pedi_dire="000-MASDEVALL-SANTA PAU")
    consultes._comanda_cache[("268", "26600207", "")] = (ara, cmd)
    consultes._direccio_cache[("C299062", "000-MASDEVALL-SANTA PAU")] = (ara, object())

    consultes.invalidar_caches_comanda("268", "26600207")

    assert ("C299062", "000-MASDEVALL-SANTA PAU") not in consultes._direccio_cache
    assert ("268", "26600207", "") not in consultes._comanda_cache


def test_palet_client_cache_nomes_purga_la_clau_demanada():
    _reset_caches()
    ara = time.time()
    consultes._palet_client_cache[("C211304", "000-A")] = (ara, None)
    consultes._palet_client_cache[("C999999", "000-B")] = (ara, None)

    consultes.invalidar_caches_comanda("268", "1", cli_codi="C211304", adr_codi="000-A")

    assert ("C211304", "000-A") not in consultes._palet_client_cache
    assert ("C999999", "000-B") in consultes._palet_client_cache


def test_sense_adr_codi_purga_la_clau_amb_cadena_buida():
    """`obtenir_palet_client` indexa amb `adr_codi or ''`."""
    _reset_caches()
    consultes._palet_client_cache[("C211304", "")] = (time.time(), None)

    consultes.invalidar_caches_comanda("268", "1", cli_codi="C211304", adr_codi=None)

    assert ("C211304", "") not in consultes._palet_client_cache
