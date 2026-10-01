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
from datetime import datetime
from types import SimpleNamespace

from sl_lectura import cache_articles
from sl_lectura import odata as od
from sl_lectura.client import client

logger = logging.getLogger(__name__)


def _data_hora(valor):
    """`2026-09-18T00:00:00Z` del Service Layer -> `datetime` naive.

    Dues raons per fer-ho aixi i no amb `fromisoformat` i zona:

    - El codi de `consultes.py` fa `row.DocDate.year` i desa l'objecte al model
      `Comanda`, aixi que ha de ser el mateix tipus que torna pyodbc: un
      `datetime` sense zona.
    - La `Z` que posa el Service Layer es FALSA. Son dates locals sense zona, i
      convertir-les desplaçaria el dia respecte del que llegeix el SQL.
    """
    if not valor:
        return None
    text = str(valor)[:19]
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        try:
            return datetime.strptime(text[:10], "%Y-%m-%d")
        except ValueError:
            logger.warning("data del Service Layer no interpretable: %r", valor)
            return None


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


def _comandes_amb_linies(series: int, docnum: int) -> list[dict]:
    return client().tot(
        COMANDES, select=_CAMPS_COMANDA_LINIES,
        filtre=f"Series eq {int(series)} and DocNum eq {int(docnum)}",
    )


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


# ============================================================
# Interlocutors: nom i adreces, en una sola lectura cachejada
# ============================================================
# `obtenir_comanda` necessita el nom del client (OCRD.CardName) i
# `obtenir_direccio` les adreces amb els seus UDF (CRD1). Al Service Layer les
# adreces venen inline amb l'interlocutor, aixi que una sola crida serveix les
# dues coses. Es cachegen per no repetir-la a cada comanda del mateix client.
INTERLOCUTORS = "BusinessPartners"
_CAMPS_BP = "CardCode,CardName,BPAddresses"
_TTL_BP = 600.0

_bps: dict[str, dict | None] = {}
_bps_a: dict[str, float] = {}
_bps_lock = threading.Lock()


def _bp(cli_codi: str) -> dict | None:
    """Interlocutor amb les seves adreces, o None si no existeix."""
    codi = (cli_codi or "").strip()
    if not codi:
        return None
    with _bps_lock:
        if codi in _bps and (time.monotonic() - _bps_a.get(codi, 0.0)) < _TTL_BP:
            return _bps[codi]
    files = client().tot(INTERLOCUTORS, select=_CAMPS_BP,
                         filtre=f"CardCode eq {od.text(codi)}")
    valor = files[0] if files else None
    with _bps_lock:
        if len(_bps) > 2000:
            _bps.clear()
            _bps_a.clear()
        _bps[codi] = valor
        _bps_a[codi] = time.monotonic()
    return valor


# ============================================================
# obtenir_comanda(): ORDR + OCRD
# ============================================================
_CAMPS_CAPCALERA = ("DocEntry,DocNum,Series,CardCode,ShipToCode,DocDate,"
                    "DocDueDate,DocumentStatus,NumAtCard,UpdateDate")

# ORDR.DocStatus -> Orders.DocumentStatus, i amb valors diferents:
# 'bost_Open'/'bost_Close' en lloc de 'O'/'C'.
_ESTAT_DOC = {"bost_Open": "O", "bost_Close": "C"}


def capcalera_comanda(series: int, docnum: int):
    """Capcalera d'una comanda per (Series, DocNum), o None si no hi es.

    El SQL fa tambe un LEFT JOIN amb NNM1 per treure `series_name`, pero aquell
    camp NO s'usa en cap lloc del projecte: es pes mort de la consulta i aqui
    no es reprodueix. (Si algun dia es necessita, el Service Layer el dona per
    SeriesService_GetDocumentSeries amb Document='17'.)
    """
    files = client().tot(
        COMANDES, select=_CAMPS_CAPCALERA,
        filtre=f"Series eq {int(series)} and DocNum eq {int(docnum)}",
    )
    if not files:
        return None
    h = files[0]
    bp = _bp(h.get("CardCode") or "")
    return SimpleNamespace(
        DocEntry=h.get("DocEntry"),
        DocNum=h.get("DocNum"),
        Series=h.get("Series"),
        CardCode=h.get("CardCode"),
        ShipToCode=h.get("ShipToCode"),
        # Dates com a datetime naive, igual que les torna pyodbc: el codi de
        # consultes.py fa `row.DocDate.year`, aixi que una cadena no hi val.
        DocDate=_data_hora(h.get("DocDate")),
        DocDueDate=_data_hora(h.get("DocDueDate")),
        # DocStatus i UpdateDate no els fa servir ningu avui (com `series_name`),
        # pero es mapegen igualment: si algun dia algu els llegeix, val mes que
        # hi siguin amb el valor correcte que no que peti nomes per Service Layer.
        DocStatus=_ESTAT_DOC.get(h.get("DocumentStatus"), h.get("DocumentStatus")),
        NumAtCard=h.get("NumAtCard"),
        UpdateDate=_data_hora(h.get("UpdateDate")),
        cli_nom=((bp or {}).get("CardName") or "").strip(),
    )


# ============================================================
# obtenir_direccio(): CRD1 + UDFs
# ============================================================
def direccio(cli_codi: str, adr_codi: str):
    """Adreca d'enviament amb els seus UDF, o None si no es troba.

    El SQL fa dues consultes: primera amb `AdresType = 'S'` i, si no troba res,
    una segona sense filtrar per tipus (hi ha adreces d'entrega que no el
    tenen). Aqui les adreces venen totes inline amb l'interlocutor, aixi que es
    resol amb una sola lectura i la mateixa precedencia en Python.
    """
    bp = _bp(cli_codi)
    if bp is None:
        return None
    adr = (adr_codi or "").strip()
    coincidencies = [a for a in (bp.get("BPAddresses") or [])
                     if (a.get("AddressName") or "").strip() == adr]
    if not coincidencies:
        return None
    # Precedencia: primer les d'enviament, com fa la primera consulta del SQL.
    enviament = [a for a in coincidencies if a.get("AddressType") == "bo_ShipTo"]
    a = (enviament or coincidencies)[0]
    return SimpleNamespace(
        adr_codi=(a.get("AddressName") or "").strip(),
        street=(a.get("Street") or "").strip(),
        city=(a.get("City") or "").strip(),
        U_SEITIPOD=a.get("U_SEITIPOD"),
        U_SEISACOSB=a.get("U_SEISACOSB"),
        U_SEIMAXSP=a.get("U_SEIMAXSP"),
        U_SEIPEDIDOM=a.get("U_SEIPEDIDOM"),
        U_SEIPREVAL=a.get("U_SEIPREVAL"),
    )


# ============================================================
# obtenir_palet_comanda(): linia de palet dins la comanda
# ============================================================
def palet_comanda(series: int, docnum: int):
    """Primera linia de palet de la comanda, o None.

    Condicions del SQL que es replican: unitat de venda de l'article 'UNI', la
    descripcio de la LINIA conte 'PALET', i s'exclouen les linies que hi ha
    afegit el propi motor (U_FCAfegit = 'S') — si no, la segona execucio del
    boto llegiria com a palet demanat pel client el que ell mateix va inserir.
    """
    art = articles()
    candidats = []
    for o in _comandes_amb_linies(series, docnum):
        for l in o.get("DocumentLines") or []:
            codi = (l.get("ItemCode") or "").strip()
            dades = art.get(codi)
            if dades is None:                       # INNER JOIN amb OITM
                continue
            if (dades.get("tunitat") or "").strip() != "UNI":
                continue
            descrip = (l.get("ItemDescription") or "").strip()
            if "PALET" not in descrip.upper():
                continue
            if l.get("U_FCAfegit") == "S":
                continue
            candidats.append((l.get("LineNum") or 0, codi, descrip))
    if not candidats:
        return None
    candidats.sort(key=lambda x: x[0])              # ORDER BY l.LineNum
    _, codi, descrip = candidats[0]
    return SimpleNamespace(art_codi=codi, art_descrip=descrip)


# ============================================================
# obtenir_palet_client(): @SEITARIFACAB + @SEITARIFADET
# ============================================================
# Les dues UDT de tarifes son l'UDO `SEITARIFA`, i el detall arriba INLINE com
# a `SEITARIFADETCollection`. Verificat: 3.912 capceleres i 20.416 linies, les
# mateixes que tenen les taules al SQL. (Les taules filles d'UDO no existeixen
# com a entitat propia al Service Layer, pero si com a col·leccio del pare: es
# per aixo que aixo es viable.)
# Avis d'una sola vegada si algu activa aquesta funcio per Service Layer. Un
# comentari al codi no el veu qui edita el .env; una linia al log, si.
_avisat_palet_client = False


def _avisa_palet_client() -> None:
    global _avisat_palet_client
    _avisat_palet_client = True
    logger.warning(
        "obtenir_palet_client esta llegint pel Service Layer. Aixo canvia el "
        "tipus de palet de ~119 dels 436 clients amb palet negociat, perque el "
        "SQL original no es determinista. Vegeu "
        "docs/bug_palet_tarifa_no_determinista.md. Si no era intencionat, "
        "treu SAP_BACKEND_OBTENIR_PALET_CLIENT del .env."
    )


TARIFES = "SEITARIFA"
_CAMPS_TARIFA = ("DocEntry,U_SEICardCode,U_SEIDireccion,U_SEIActivo,Canceled,"
                 "SEITARIFADETCollection")


def palet_client(cli_codi: str, adr_codi: str | None):
    """Tipus de palet negociat pel client, o None.

    NO ACTIVAR sense decisio de negoci. Vegeu
    docs/bug_palet_tarifa_no_determinista.md.

    El motiu: el SQL original fa TOP 1 amb ORDER BY nomes sobre la capcalera
    (direccio i DocEntry), i CAP ordre sobre la linia. Quan una tarifa te mes
    d'una linia de palet — 120 de 429 tarifes actives — quina guanya la
    decideix el pla d'execucio, no la consulta. Ni LineId ni VisOrder expliquen
    el que torna avui.

    Aquesta implementacio agafa la primera linia per LineId, que es el que diu
    el docstring de `consultes.obtenir_palet_client`. Es determinista, pero
    mesurat contra la base sencera canvia el tipus de palet a **119 dels 436
    clients** que en tenen un negociat. Es un canvi de resultat de negoci
    (quin palet fisic rep un client), no una questio tecnica.

    Mentre no hi hagi decisio, aquesta funcio es queda per SQL.
    """
    if not _avisat_palet_client:
        _avisa_palet_client()
    codi = (cli_codi or "").strip()
    if not codi:
        return None
    capceleres = client().tot(
        TARIFES, select=_CAMPS_TARIFA,
        filtre=od.i(f"U_SEICardCode eq {od.text(codi)}",
                    "U_SEIActivo eq " + od.text("Y"),
                    "Canceled ne " + od.text("Y")),
    )
    if not capceleres:
        return None

    adr = (adr_codi or "").strip() or None
    ara = datetime.now()

    def prioritat(c: dict) -> tuple:
        mateixa_adr = (adr is not None
                       and (c.get("U_SEIDireccion") or "").strip() == adr)
        return (0 if mateixa_adr else 1, -int(c.get("DocEntry") or 0))

    for c in sorted(capceleres, key=prioritat):
        linies = sorted((c.get("SEITARIFADETCollection") or []),
                        key=lambda d: (d.get("LineId") or 0))
        for d in linies:
            nom = (d.get("U_SEIItemName") or "").strip()
            if not nom.upper().startswith("PALET"):
                continue
            fi = _data_hora(d.get("U_SEIFechaFin"))
            if fi is not None and fi < ara:          # U_SEIFechaFin >= GETDATE()
                continue
            art_codi = (d.get("U_SEIItemCode") or "").strip()
            if not art_codi:
                continue
            return SimpleNamespace(art_codi=art_codi, art_descrip=nom)
    return None
