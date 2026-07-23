"""Bootstrap: afegeix el path de l'aplicació Kais canònica a sys.path.

Motiu: aquesta aplicació SAP comparteix els mòduls purs (`models.py`,
`regles.py`, `mailer.py`) amb l'aplicació Kais original per garantir
que les regles de negoci evolucionen a la vegada.

Ordre d'import Python:
  1. Directori d'aquesta app SAP (no té els mòduls compartits).
  2. `KAIS_APP_PATH` (aquest bootstrap) → resol regles/models/mailer.

Sobreescriure amb la variable d'entorn `KAIS_APP_PATH` si l'app Kais no
es troba a `..\\preparacioComandesVenda\\`.

Aquest mòdul ha de ser importat com a PRIMERA línia de cada punt d'entrada
de la app (app.py, motor.py, consultes.py, tests/conftest.py).
"""
from __future__ import annotations

import os
import sys

_DEFAULT_KAIS_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "preparacioComandesVenda")
)
KAIS_APP_PATH = os.environ.get("KAIS_APP_PATH", _DEFAULT_KAIS_PATH)


def ensure_kais_path() -> None:
    """Insereix `KAIS_APP_PATH` a sys.path si encara no hi és."""
    if not os.path.isdir(KAIS_APP_PATH):
        raise RuntimeError(
            f"KAIS_APP_PATH no existeix: {KAIS_APP_PATH!r}. "
            f"Comprova la variable d'entorn KAIS_APP_PATH."
        )
    if KAIS_APP_PATH not in sys.path:
        # append (no insert 0): els mòduls locals prevalen sobre els compartits.
        sys.path.append(KAIS_APP_PATH)


ensure_kais_path()


def _apply_sap_overrides() -> None:
    """Afegeix a `regles.OVERRIDES_PALET_CLIENT` els equivalents en format SAP.

    Els codis client a SAP són el codi Kais sense els zeros inicials i amb prefix 'C'
    (ex: Kais `00301614` = SAP `C301614`). Per no duplicar la lista a `regles.py`
    (compartit amb Kais canònic — intocable des d'aquesta variant), aquí traduïm
    dinàmicament cada entrada Kais al seu equivalent SAP i les injectem al set.
    """
    import regles  # noqa: E402
    kais_to_sap: dict[str, str] = {
        "00301614": "C301614",  # ACID CAFE BERLIN GMBH
    }
    sap_extras = set()
    for cli_kais, art in regles.OVERRIDES_PALET_CLIENT:
        cli_sap = kais_to_sap.get(cli_kais)
        if cli_sap:
            sap_extras.add((cli_sap, art))
    if sap_extras:
        regles.OVERRIDES_PALET_CLIENT = regles.OVERRIDES_PALET_CLIENT | sap_extras


_apply_sap_overrides()
