"""Fixtures compartides per tots els tests."""
import sys
import os
import pytest

# Afegir el directori arrel de la app SAP per importar consultes.py, motor.py locals.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Bootstrap: afegeix KAIS_APP_PATH al sys.path perquè models/regles/mailer
# es resolguin des de l'aplicació Kais canònica.
import _bootstrap  # noqa: F401

from models import Linia, Direccio, Comanda  # compartit via _bootstrap


# ============================================================
# Factories de dades de test
# ============================================================

def fer_linia(**kwargs):
    """Crea una Linia amb valors per defecte raonables."""
    defaults = dict(
        linea_num=10,
        art_codi="30001",
        art_descrip="FARINA TEST",
        linea_unidades=40.0,
        linea_cantidad=1000.0,
        tunitat="S25",
        uxc=45.0,
        pes=1.0,
        cantidadapilable=5,
        comanda_minima_produccio=None,
        dimensio_especial=False,
        sac_25_especial=False,
        sac_colagne_normal=False,
        aprovisionament_estoc=False,
        palet_producte_estoc=None,
        magatzem=None,
    )
    defaults.update(kwargs)
    return Linia(**defaults)


def fer_direccio(**kwargs):
    """Crea una Direccio amb valors per defecte raonables."""
    defaults = dict(
        cli_codi="CLI001",
        adr_codi="001",
        adr_nom="Client Test",
        tipus_descarrega="PALET",
        sacs_x_base=None,
        max_sacs_palet=None,
        sacs_comanda_minima=None,
        preval_direccio_explicit=None,
    )
    defaults.update(kwargs)
    return Direccio(**defaults)


def fer_comanda(**kwargs):
    """Crea una Comanda amb valors per defecte."""
    defaults = dict(
        pedi_num=1,
        cli_codi="CLI001",
        pedi_dire="001",
    )
    defaults.update(kwargs)
    return Comanda(**defaults)


# ============================================================
# Fixtures pytest
# ============================================================

@pytest.fixture
def linia():
    return fer_linia()


@pytest.fixture
def direccio_palet():
    return fer_direccio(tipus_descarrega="PALET")


@pytest.fixture
def direccio_manual():
    return fer_direccio(tipus_descarrega="MANUAL")
