"""Unitat de venda efectiva d'un article: el granel sempre es diu "GRA".

El motor (RF1) i les consultes reconeixen el granel per la unitat de venda
"GRA". A la BD de produccio el granel te `SalUnitMsr = 'KGS'` (i no "GRA"), i
el criteri de SAP es la propietat 5 de l'article ("Es Granel", `OITM.QryGroup5`,
`Items.Properties5` al Service Layer). Per no haver de tocar el motor ni les
regles, la unitat es normalitza on es llegeix:

    granel = unitat GRA / KG / KGS
             o propietat 5, SEMPRE QUE la unitat no sigui de sacs (S05, S25...)

Si la unitat es de sacs, mana la unitat: el 32090 MEULE T80 COLAGNE es S25 i
te la propietat 5 (error de dades a SAP, decisio de l'Oscar del 10-11-2026), i
ha de continuar anant en palets.

L'app d'agrupacio de carregues fa servir el mateix criteri
(`dades/sql/carregues.py`, `dades/sql/pistolejat.py`, `dades/sl/pistolejat.py`).
"""
from __future__ import annotations

import re

UNITATS_GRANEL = ("GRA", "KG", "KGS")
_SACS = re.compile(r"^S\d+$")


def es_granel(unitat: str | None, propietat5) -> bool:
    """`propietat5`: 'Y' (SQL), 'tYES' (Service Layer) o un booleà."""
    u = (unitat or "").strip().upper()
    if u in UNITATS_GRANEL:
        return True
    p5 = propietat5 is True or propietat5 in ("Y", "tYES")
    return p5 and not _SACS.match(u)


def tunitat_efectiva(unitat: str | None, propietat5) -> str:
    """La unitat de venda tal com l'esperen el motor i les regles."""
    return "GRA" if es_granel(unitat, propietat5) else (unitat or "").strip()


def sql_es_granel(alias: str = "i", unitat: str | None = None) -> str:
    """El mateix en T-SQL per a un OITM amb l'alias `alias`. `unitat`: una
    altra columna d'unitat (per exemple la de la linia), si cal."""
    u = f"UPPER(RTRIM(ISNULL({unitat or alias + '.SalUnitMsr'}, '')))"
    return (f"({u} IN ('GRA', 'KG', 'KGS') "
            f"OR ({alias}.QryGroup5 = 'Y' AND {u} NOT LIKE 'S[0-9]%'))")


def sql_tunitat(alias: str = "i") -> str:
    return (f"CASE WHEN {sql_es_granel(alias)} THEN 'GRA' "
            f"ELSE RTRIM({alias}.SalUnitMsr) END")
