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

La unitat de sacs pot dur "KG" al darrere (S25KG, S10KG, S05KG...; canvi de
dades mestres demanat el 19-11-2026). El motor i les regles (compartides amb
Kais) esperen S25, S10, S05..., aixi que el "KG" es treu on es llegeix.

L'app d'agrupacio de carregues fa servir el mateix criteri
(`dades/sql/carregues.py`, `dades/sql/pistolejat.py`, `dades/sl/pistolejat.py`).
"""
from __future__ import annotations

import re

UNITATS_GRANEL = ("GRA", "KG", "KGS")
_SACS = re.compile(r"^S\d+(KG)?$")


def es_granel(unitat: str | None, propietat5) -> bool:
    """`propietat5`: 'Y' (SQL), 'tYES' (Service Layer) o un booleà."""
    u = (unitat or "").strip().upper()
    if u in UNITATS_GRANEL:
        return True
    p5 = propietat5 is True or propietat5 in ("Y", "tYES")
    return p5 and not _SACS.match(u)


def unitat_sacs(unitat: str | None) -> str:
    """S25KG -> S25 (la resta, igual)."""
    u = (unitat or "").strip()
    return u[:-2] if _SACS.match(u.upper()) and u.upper().endswith("KG") else u


def tunitat_efectiva(unitat: str | None, propietat5) -> str:
    """La unitat de venda tal com l'esperen el motor i les regles."""
    return "GRA" if es_granel(unitat, propietat5) else unitat_sacs(unitat)


def sql_es_granel(alias: str = "i", unitat: str | None = None) -> str:
    """El mateix en T-SQL per a un OITM amb l'alias `alias`. `unitat`: una
    altra columna d'unitat (per exemple la de la linia), si cal."""
    u = f"UPPER(RTRIM(ISNULL({unitat or alias + '.SalUnitMsr'}, '')))"
    return (f"({u} IN ('GRA', 'KG', 'KGS') "
            f"OR ({alias}.QryGroup5 = 'Y' AND {u} NOT LIKE 'S[0-9]%'))")


def sql_unitat_sacs(columna: str) -> str:
    """El mateix que `unitat_sacs` en T-SQL: S25KG -> S25."""
    u = f"RTRIM({columna})"
    return (f"CASE WHEN UPPER({u}) LIKE 'S[0-9]%KG' AND UPPER(LEFT({u}, LEN({u}) - 2)) NOT LIKE 'S%[^0-9]%' "
            f"THEN LEFT({u}, LEN({u}) - 2) ELSE {u} END")


def sql_tunitat(alias: str = "i") -> str:
    return (f"CASE WHEN {sql_es_granel(alias)} THEN 'GRA' "
            f"ELSE {sql_unitat_sacs(alias + '.SalUnitMsr')} END")
