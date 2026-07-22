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
