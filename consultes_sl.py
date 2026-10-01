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
import threading
import time
from types import SimpleNamespace

from sl_lectura import cache_articles
from sl_lectura import odata as od
from sl_lectura.client import client

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


# ============================================================
# Mestre d'articles amb els camps que necessita el motor
# ============================================================
# Cache propia i no la de `sl_lectura.cache_articles` perque aquella es
# generica (codi, nom, unitat de venda) i aqui calen nou camps mes, entre ells
# UDFs d'aquesta companyia. El criteri de `sl_lectura` es que alla nomes hi
# vagi el que es generic de SAP.
#
# Els noms dels camps al Service Layer NO son els de les columnes d'OITM i no
# es poden deduir. Aquests estan verificats un per un contra els 2.029 articles
# del mestre:
#
#   OITM.SalUnitMsr             -> SalesUnit
#   OITM.SalPackUn              -> SalesQtyPerPackUnit
#   OITM.SWeight1               -> SalesUnitWeight
#   OITM.U_SEIUnitatsPalet      -> U_SEIUnitatsPalet
#   OITM.U_SEIUnitatsApilables  -> U_SEIUnitatsApilables
#   OITM.U_SEIPaletProd         -> U_SEIPaletProd
#   OITM.QryGroup2/3/4          -> Properties2/3/4
#
# Compte amb dues d'aquestes:
#   - `SalesItemsPerUnit` SEMBLA l'equivalent de SalPackUn i NO HO ES: val 1.0
#     on SalPackUn val 25. Entra al calcul dels kg per sac, aixi que
#     confondre-les corromp els embalatges sense cap error visible.
#   - Els Properties tornen 'tYES'/'tNO' on el SQL torna 'Y'/'N'. Es
#     normalitzen aqui, perque `_row_to_linia` de consultes.py ha de poder
#     comparar amb 'Y' igual que sempre.
ARTICLES = "Items"
_CAMPS_ARTICLE = (
    "ItemCode,ItemName,SalesUnit,SalesQtyPerPackUnit,SalesUnitWeight,"
    "U_SEIUnitatsPalet,U_SEIUnitatsApilables,U_SEIPaletProd,"
    "Properties2,Properties3,Properties4"
)
_TTL_ARTICLES = 900.0

_articles: dict[str, dict] | None = None
_articles_a: float = 0.0
_articles_lock = threading.Lock()


def _flag(valor) -> str | None:
    """'tYES'/'tNO' del Service Layer -> 'Y'/'N' com els torna el SQL."""
    if valor == "tYES":
        return "Y"
    if valor == "tNO":
        return "N"
    return valor


def _normalitza_article(f: dict) -> tuple[str, dict]:
    codi = (f.get("ItemCode") or "").strip()
    return codi, {
        "tunitat": (f.get("SalesUnit") or "").strip(),
        "sal_pack_un": f.get("SalesQtyPerPackUnit"),
        "pes": f.get("SalesUnitWeight"),
        "uxc": f.get("U_SEIUnitatsPalet"),
        "cantidadapilable": f.get("U_SEIUnitatsApilables"),
        "palet_producte_estoc_raw": (f.get("U_SEIPaletProd") or "").strip() or None,
        "dimensio_especial_flag": _flag(f.get("Properties2")),
        "sac_25_especial_flag": _flag(f.get("Properties3")),
        "sac_colagne_flag": _flag(f.get("Properties4")),
    }


def articles(refresca: bool = False) -> dict[str, dict]:
    """Mestre d'articles amb els camps del motor. 3 crides, despres memoria."""
    global _articles, _articles_a
    with _articles_lock:
        caducat = _articles is None or (time.monotonic() - _articles_a) > _TTL_ARTICLES
        if refresca or caducat:
            t = time.monotonic()
            files = client().tot(ARTICLES, select=_CAMPS_ARTICLE, ordre="ItemCode")
            _articles = dict(_normalitza_article(f) for f in files)
            _articles_a = time.monotonic()
            logger.info("cache d'articles del motor: %d articles en %.0f ms",
                        len(_articles), (_articles_a - t) * 1000)
        return _articles


# ============================================================
# obtenir_linies() / obtenir_linies_batch(): RDR1 + OITM
# ============================================================
COMANDES = "Orders"
_CAMPS_COMANDA_LINIES = "DocEntry,Series,DocNum,DocumentLines"


def _files_linies(comandes: list[dict]) -> list[SimpleNamespace]:
    """Converteix comandes amb linies inline a files com les del SQL.

    El `_LINIES_SELECT` de consultes.py fa INNER JOIN amb OITM, de manera que
    una linia amb un article que no es al mestre NO hi surt. Ho repliquem
    descartant-la: si no, el motor veuria linies que avui no veu.
    """
    art = articles()
    files: list[SimpleNamespace] = []
    for o in comandes:
        series, docnum = o.get("Series"), o.get("DocNum")
        for l in o.get("DocumentLines") or []:
            codi = (l.get("ItemCode") or "").strip()
            dades = art.get(codi)
            if dades is None:      # equivalent a l'INNER JOIN amb OITM
                continue
            quan = float(l.get("Quantity") or 0)
            pack = float(l.get("PackageQuantity") or 0)
            files.append(SimpleNamespace(
                linea_num=l.get("LineNum"),
                art_codi=codi,
                art_descrip=(l.get("ItemDescription") or "").strip(),
                # COALESCE(NULLIF(PackQty, 0), Quantity): els SACS, no els kg
                linea_unidades=(pack if pack else quan),
                magatzem=(l.get("WarehouseCode") or "").strip(),
                series=series,
                docnum=docnum,
                **dades,
            ))
    return files


def linies_comanda(series: int, docnum: int) -> list[SimpleNamespace]:
    """Linies d'una comanda, ordenades per LineNum com fa el SQL."""
    comandes = client().tot(
        COMANDES, select=_CAMPS_COMANDA_LINIES,
        filtre=f"Series eq {int(series)} and DocNum eq {int(docnum)}",
    )
    files = _files_linies(comandes)
    files.sort(key=lambda r: (r.linea_num if r.linea_num is not None else 0))
    return files


def linies_batch(claus: list[tuple[int, int]]) -> list[SimpleNamespace]:
    """Linies de diverses comandes. Ordre del SQL: DocNum, despres LineNum."""
    if not claus:
        return []
    c = client()
    comandes: list[dict] = []
    for tros in od.trossos(claus, 20):   # cada clau son dues condicions
        filtre = od.o(*[f"Series eq {int(s)} and DocNum eq {int(d)}" for s, d in tros])
        comandes.extend(c.tot(COMANDES, select=_CAMPS_COMANDA_LINIES, filtre=filtre))
    files = _files_linies(comandes)
    files.sort(key=lambda r: ((r.docnum if r.docnum is not None else 0),
                              (r.linea_num if r.linea_num is not None else 0)))
    return files
