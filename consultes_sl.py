"""Lectures del motor d'embalatges pel Service Layer de SAP B1.

Company de `consultes.py`, que es el que llegeix per SQL Server directe. La
migracio es fa funcio a funcio i es commuta amb `SAP_BACKEND` (vegeu
`sl_lectura/backend.py`).

FORMA D'AQUEST MODUL, que no es la obvia i te motiu
---------------------------------------------------
Aqui NO es reimplementen les funcions de `consultes.py` senceres. Nomes la
part que llegeix les files. Les caches amb TTL, les validacions,
`invalidar_caches_comanda` i la construccio dels models (`Comanda`, `Linia`,
`Direccio`) es queden alla, compartides pels dos backends.

Per aixo les funcions d'aqui tornen objectes que imiten una fila de pyodbc
(`SimpleNamespace` amb els mateixos noms de camp): aixi el codi de
`consultes.py` que ve despres del `conn.execute(...)` no s'ha de tocar gens, i
no hi ha cap regla de negoci duplicada entre els dos camins. Es la diferencia
entre un diff de tres linies per funcio i un de cinquanta en codi que esta en
produccio servint el boto de B1UP.

Limitacions del Service Layer que condicionen el que es pot fer aqui (provades
contra la instal·lacio real, B1 10.0 / OData v3):

  - Cap JOIN: 0 navigation properties en 436 entitats.
  - No es pot agregar ni filtrar sobre linies de document, ni retallar-les amb
    $select: venen senceres o no venen.
  - `$orderby` no accepta funcions, i no hi ha `toupper` ni `trim`.
"""
from __future__ import annotations

import logging
from types import SimpleNamespace

from sl_lectura import cache_articles

logger = logging.getLogger(__name__)


# ============================================================
# obtenir_descrip_article(): OITM.ItemName
# ============================================================
def descrip_article(art_codi: str):
    """Fila amb `art_descrip`, o None si l'article no existeix.

    Equival a `SELECT TOP 1 RTRIM(ItemName) FROM OITM WHERE ItemCode = ?`.

    Ve de la cache del mestre d'articles, que ja la carrega sencera (~2.000
    articles, 3 crides) i que consulta en viu els codis que no hi son. Per
    tant el cas normal son 0 crides al Service Layer.
    """
    dades = cache_articles.consulta([art_codi]).get(art_codi)
    if dades is None:
        return None
    return SimpleNamespace(art_descrip=dades.get("art_descrip") or "")
