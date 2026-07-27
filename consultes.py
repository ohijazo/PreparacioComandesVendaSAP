"""Capa de dades SAP B1 (SQL Server) del motor de preparació de comandes.

Substitueix el `consultes.py` de la variant Kais. Manté les mateixes firmes
públiques que consumeix `motor.py` per garantir zero canvis al motor de regles.

Mapeig taules Kais → SAP B1:
- `ek_Pedido`/`CPALBARA` → `ORDR` (Sales Orders)
- `ek_PedidoLineas`/`ALBLINIA` → `RDR1` (Sales Order Lines)
- `ARTICLES` → `OITM` (Items)
- `CLIENTS` → `OCRD` (Business Partners)
- `CLIENVIO` → `CRD1` (BP Addresses)
- `INF_ARTICULO` (pivot dinàmic) → UDFs sobre `OITM` (`U_SEI*`)
- `inf_clienvio` (pivot dinàmic) → UDFs sobre `CRD1` (`U_SEI*`)
- `SERIEALB` → `NNM1` (Series catalog)
- `Almac` → `OWHS` (Warehouses)
- `PREUSCLIENTS.xlsx` (Excel) → `@SEITARIFACAB` + `@SEITARIFADET` (UDT tarifes per BP)
- `INFOANEX` → **no aplica** (UDFs són estàtics)

UDFs / camps SAP mapejats:

Articles (OITM):
- SalUnitMsr → tunitat (S05/S10/.../S25/GRA/UNI)  [standard SAP]
- SalPackUn → kg per sac  [standard SAP]
- U_SEIUnitatsApilables → cantidadapilable  [UDF]
- U_SEIUnitatsPalet → uxc  [UDF]
- U_SEIPaletProd → palet_producte_estoc ('-' i '' = sense palet)  [UDF]
- QryGroup2 → dimensio_especial (4 articles marcats post-fix VBA)  [Query Group]
- QryGroup3 → sac_25_especial (13 articles marcats)  [Query Group]

Direccions client (CRD1):
- U_SEITIPOD → tipus_descarrega ('P'=PALET, 'M'=MANUAL, '-'=no definit)  [UDF]
  (NOTA: `U_SEIDESCARGA` NO és el tipus de descàrrega — és el nombre de
  descarregadors: '1' o '2' persones.)
- U_SEISACOSB → sacs_x_base (nvarchar → int)
- U_SEIMAXSP → max_sacs_palet
- U_SEIPEDIDOM → sacs_comanda_minima
- U_SEIPREVAL → preval_direccio ('S'=Sí, 'N'=No)

Concepte `sac_colagne_normal` — derivat de la família comercial:
- OITM.U_SEIFamCialCat = 'MOULIN DE COLAGNE' → sac_colagne_normal=True.
  Font actualment usada; QryGroup4 (Sac Colagne Especial) també conté els 11
  articles autoritatius de Kais però el motor manté el proxy per compatibilitat.

Regles del motor a SAP (estat 2026-07-27):
- ✅ RF1, RF2, RF5-RF14: totes actives amb dades reals.
- ✅ RF4 (dimensio_especial): activa via QryGroup2 post-fix Kais BUG #2.
- ✅ RF6 (sac_25_especial): activa via QryGroup3 (13 articles migrats).
- ⏸️ RF3 (comanda_minima_produccio): DESACTIVADA a SAP — Kais tampoc l'aplica
  actualment. Es podria activar creant un UDF nou a OITM (ex. U_FCComandaMinKg)
  i migrant els 32 valors de Kais. No bloquejant.

Detalls del recorregut de descoberta i validació: `tasks/validacio_sap.md` §1.
"""
import _bootstrap  # noqa: F401 — insereix KAIS_APP_PATH a sys.path per als models compartits
import logging
import os
import threading as _threading
import time as _time
from collections import OrderedDict as _OrderedDict
from collections import deque as _deque
from datetime import date, datetime

import pyodbc

from models import Comanda, Direccio, Linia  # compartits via _bootstrap

logger = logging.getLogger("motor_sap")

# ============================================================
# Config des de .env
# ============================================================
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env_path):
    with open(_env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip())

SERVER = os.environ.get("SAP_SQL_SERVER", "")
DATABASE = os.environ.get("SAP_SQL_DATABASE", "DB_FARINERA_TEST")
USER = os.environ.get("SAP_SQL_USER", "sa")
PASSWORD = os.environ.get("SAP_SQL_PASSWORD", "")

_CONN_STR = (
    f"DRIVER={{ODBC Driver 18 for SQL Server}};"
    f"SERVER={SERVER};"
    f"DATABASE={DATABASE};"
    f"UID={USER};"
    f"PWD={PASSWORD};"
    f"TrustServerCertificate=yes;"
    f"APP=MotorComandes_SAP;"
    f"ApplicationIntent=ReadOnly;"
)

# Desactivar pooling ODBC natiu — gestionem la concurrència nosaltres.
pyodbc.pooling = False


# ============================================================
# Monitorització SQL: comptabilitza queries, temps i errors
# ============================================================
_sql_stats_lock = _threading.Lock()
_sql_stats = {
    "total_queries": 0,
    "total_time_ms": 0.0,
    "errors": 0,
    "recent": _deque(maxlen=50),
}

# Semàfor: màxim 1 connexió simultània (mateixa estratègia que Kais).
_MAX_CONNECTIONS = 1
_conn_semaphore = _threading.Semaphore(_MAX_CONNECTIONS)


def get_sql_stats() -> dict:
    with _sql_stats_lock:
        n = _sql_stats["total_queries"]
        avg = (_sql_stats["total_time_ms"] / n) if n > 0 else 0.0
        active = _MAX_CONNECTIONS - _conn_semaphore._value
        return {
            "total_queries": n,
            "total_time_ms": round(_sql_stats["total_time_ms"], 1),
            "avg_time_ms": round(avg, 1),
            "errors": _sql_stats["errors"],
            "max_connections": _MAX_CONNECTIONS,
            "active_connections": active,
            "recent": list(_sql_stats["recent"]),
        }


def reset_sql_stats():
    with _sql_stats_lock:
        _sql_stats["total_queries"] = 0
        _sql_stats["total_time_ms"] = 0.0
        _sql_stats["errors"] = 0
        _sql_stats["recent"].clear()


class _MonitoredConnection:
    """Wrapper de conexió pyodbc que mesura cada query."""

    _QUERY_PATTERNS = [
        ("FROM ORDR", "obtenir_comanda_ordr"),
        ("FROM RDR1", "obtenir_linies_rdr1"),
        ("FROM CRD1", "obtenir_direccio_crd1"),
        ("FROM OCRD", "obtenir_client_ocrd"),
        ("FROM OITM", "obtenir_article_oitm"),
        ("FROM OWHS", "obtenir_magatzems_owhs"),
        ("FROM NNM1", "obtenir_series_nnm1"),
        ("[@SEITARIFADET]", "obtenir_palet_client_tarifa"),
        ("CHECKSUM_AGG", "fingerprint"),
    ]

    def __init__(self, conn):
        self._conn = conn
        self._closed = False

    @staticmethod
    def _identify_query(sql):
        for pattern, name in _MonitoredConnection._QUERY_PATTERNS:
            if pattern in sql:
                return name
        return sql.strip().replace("\n", " ")[:60]

    def execute(self, sql, *args, **kwargs):
        label = self._identify_query(sql)
        t0 = _time.time()
        try:
            result = self._conn.execute(sql, *args, **kwargs)
            elapsed_ms = (_time.time() - t0) * 1000
            with _sql_stats_lock:
                _sql_stats["total_queries"] += 1
                _sql_stats["total_time_ms"] += elapsed_ms
                _sql_stats["recent"].append({
                    "ts": _time.time(),
                    "ms": round(elapsed_ms, 1),
                    "sql": label,
                })
            if elapsed_ms > 1000:
                logger.warning("SQL LENTA (%.0fms): %s", elapsed_ms, label)
            return result
        except Exception as e:
            elapsed_ms = (_time.time() - t0) * 1000
            with _sql_stats_lock:
                _sql_stats["errors"] += 1
                _sql_stats["recent"].append({
                    "ts": _time.time(),
                    "ms": round(elapsed_ms, 1),
                    "sql": label,
                    "error": str(e)[:100],
                })
            raise

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            self._conn.close()
        except Exception:
            pass
        _conn_semaphore.release()

    def __getattr__(self, name):
        return getattr(self._conn, name)


def connectar():
    """Obre una conexió SQL a SAP B1 (màxim 1 simultània via semàfor).

    La conexió es tanca realment al `close()` — no queda sleeping.
    """
    _conn_semaphore.acquire()
    try:
        conn = pyodbc.connect(_CONN_STR, timeout=10, autocommit=True)
        conn.timeout = 15
        conn.execute("SET NOCOUNT ON")
        return _MonitoredConnection(conn)
    except Exception:
        _conn_semaphore.release()
        raise


# ============================================================
# INFOANEX shims — a SAP els UDFs són estàtics, no cal cap lookup dinàmic.
# ============================================================
def obtenir_titols_infoanex(conn) -> dict:
    return {}


def obtenir_titols_infoanex_clienvio(conn) -> dict:
    return {}


# ============================================================
# Conversió de valors SAP → dominis del motor
# ============================================================
def _sap_tipus_descarrega(valor: str | None) -> str | None:
    """SAP `U_SEITIPOD`: 'P'=PALET, 'M'=MANUAL, '-'=no definit."""
    if valor is None:
        return None
    v = str(valor).strip().upper()
    if v == "P":
        return "PALET"
    if v == "M":
        return "MANUAL"
    if v in ("PALET", "MANUAL"):
        return v
    # '-' o qualsevol altre → no definit (el motor autodetecta via PREUSCLIENTS/TARIFA).
    return None


def _sap_preval(valor: str | None) -> bool | None:
    """SAP U_SEIPREVAL: 'S'=Sí, 'N'=No."""
    if valor is None:
        return None
    v = str(valor).strip().upper()
    if v in ("S", "SI", "Y", "YES"):
        return True
    if v in ("N", "NO"):
        return False
    return None


def _sap_int(valor) -> int | None:
    if valor is None:
        return None
    try:
        s = str(valor).strip()
        return int(s) if s else None
    except (ValueError, TypeError):
        return None


def _pes_per_tunitat(tunitat: str, sal_pack_un: float | None = None) -> float:
    """Kg per sac. Prioritza SAP `SalPackUn` (numèric), fallback al codi `S<n>`."""
    if sal_pack_un is not None and sal_pack_un > 0:
        return float(sal_pack_un)
    if tunitat and tunitat.startswith("S"):
        try:
            return float(tunitat[1:])
        except ValueError:
            pass
    return 0.0


def _palet_estoc_val(raw: str | None) -> str | None:
    """`U_SEIPaletProd`: normalitza '', '-' → None (sense palet estoc)."""
    if raw is None:
        return None
    v = str(raw).strip()
    if v == "" or v == "-":
        return None
    return v


# ============================================================
# Caches (mateixa política LRU/TTL que Kais)
# ============================================================
_comanda_cache: dict = {}
_COMANDA_CACHE_TTL = 600
_COMANDA_CACHE_MAX = 500

_linies_cache: _OrderedDict = _OrderedDict()
_LINIES_CACHE_TTL = 600
_LINIES_CACHE_MAX = 200

_direccio_cache: _OrderedDict = _OrderedDict()
_DIRECCIO_CACHE_MAX = 500

_descrip_cache: dict = {}
_DESCRIP_CACHE_MAX = 5000

_palet_client_cache: _OrderedDict = _OrderedDict()
_PALET_CLIENT_CACHE_TTL = 600
_PALET_CLIENT_CACHE_MAX = 500

_palet_comanda_cache: dict = {}
_PALET_COMANDA_CACHE_TTL = 600

_noms_magatzems_cache: dict | None = None


def invalidar_caches_comanda(sal_codigo: str, cpa_albara: str) -> None:
    """Buida tots els caches relacionats amb una comanda."""
    sal = sal_codigo.strip()
    alb = cpa_albara.strip()

    # Direcció → cal el cli_codi/adr_codi que està al cache de comanda
    for key, (_, cmd) in list(_comanda_cache.items()):
        if key[0] == sal and key[1] == alb:
            dir_key = (cmd.cli_codi, cmd.pedi_dire)
            if dir_key in _direccio_cache:
                del _direccio_cache[dir_key]
            break

    for k in [k for k in _comanda_cache if k[0] == sal and k[1] == alb]:
        del _comanda_cache[k]
    for k in [k for k in _linies_cache if k[1] == sal and k[2] == alb]:
        del _linies_cache[k]
    for k in [k for k in _palet_comanda_cache if k[1] == sal and k[2] == alb]:
        del _palet_comanda_cache[k]


# ============================================================
# obtenir_comanda(): ORDR + OCRD
# ============================================================
def obtenir_comanda(conn, sal_codigo: str, cpa_albara: str,
                    eje_ejercicio: str | None = None,
                    tra_codi_carrega: str | None = None,
                    data_carrega: str | date | datetime | None = None) -> Comanda:
    """Cerca una comanda a SAP `ORDR` per `(Series, DocNum)`.

    Els paràmetres `eje_ejercicio`, `tra_codi_carrega` i `data_carrega`
    s'accepten per compatibilitat amb la interfície Kais però no s'apliquen
    a SAP (les comandes SAP no es reparteixen per any/tra/càrrega).
    """
    sal = sal_codigo.strip()
    alb = cpa_albara.strip()

    if not data_carrega:
        data_key = ""
    elif isinstance(data_carrega, str):
        data_key = data_carrega
    else:
        data_key = data_carrega.isoformat()
    cache_key = (sal, alb, eje_ejercicio or "", (tra_codi_carrega or "").strip(), data_key)
    if cache_key in _comanda_cache:
        ts, cached = _comanda_cache[cache_key]
        if (_time.time() - ts) < _COMANDA_CACHE_TTL:
            return cached

    # SAP: Series i DocNum són enters. Kais els passa com a string amb zeros.
    try:
        series = int(sal)
    except ValueError:
        raise ValueError(f"sal_codigo '{sal}' no és un enter (Series SAP)")
    try:
        docnum = int(alb)
    except ValueError:
        raise ValueError(f"cpa_albara '{alb}' no és un enter (DocNum SAP)")

    sql = """
        SELECT TOP 1
            h.DocEntry, h.DocNum, h.Series, h.CardCode, h.ShipToCode,
            h.DocDate, h.DocDueDate, h.DocStatus, h.NumAtCard, h.UpdateDate,
            RTRIM(bp.CardName) AS cli_nom,
            RTRIM(ns.SeriesName) AS series_name
        FROM ORDR h WITH (NOLOCK)
        LEFT JOIN OCRD bp WITH (NOLOCK) ON bp.CardCode = h.CardCode
        LEFT JOIN NNM1 ns WITH (NOLOCK) ON ns.Series = h.Series AND ns.ObjectCode = '17'
        WHERE h.Series = ? AND h.DocNum = ?
    """
    row = conn.execute(sql, series, docnum).fetchone()
    if not row:
        raise ValueError(f"Comanda {sal_codigo}/{cpa_albara} no trobada a SAP")

    comanda = Comanda(
        pedi_num=int(row.DocEntry),
        cli_codi=(row.CardCode or "").strip(),
        pedi_dire=(row.ShipToCode or "").strip(),
        pedi_fech=row.DocDate,
        pedi_numero=str(row.DocNum),
        pedi_serie=str(row.Series),
        pedi_ejercicio=row.DocDate.year if row.DocDate else None,
        cli_nom=(row.cli_nom or "") if row.cli_nom else "",
        num_pedido_kais=(row.NumAtCard or "").strip() or None,
        data_comanda=row.DocDate,
        data_servir=row.DocDueDate,
    )

    if len(_comanda_cache) >= _COMANDA_CACHE_MAX:
        _comanda_cache.clear()
    _comanda_cache[cache_key] = (_time.time(), comanda)
    return comanda


def obtenir_comanda_per_numero(conn, sal_codigo: str, cpa_albara: str) -> Comanda:
    """Compat: cerca per (Series, DocNum). Alies de `obtenir_comanda`."""
    return obtenir_comanda(conn, sal_codigo, cpa_albara)


# ============================================================
# obtenir_linies(): RDR1 + OITM (amb UDFs)
# ============================================================
_LINIES_SELECT = """
    SELECT
        l.LineNum AS linea_num,
        RTRIM(l.ItemCode) AS art_codi,
        RTRIM(l.Dscription) AS art_descrip,
        l.Quantity AS linea_unidades,
        RTRIM(i.SalUnitMsr) AS tunitat,
        i.SalPackUn AS sal_pack_un,
        i.U_SEIUnitatsPalet AS uxc,
        i.SWeight1 AS pes,
        i.U_SEIUnitatsApilables AS cantidadapilable,
        RTRIM(i.U_SEIPaletProd) AS palet_producte_estoc_raw,
        RTRIM(i.U_SEIFamCialCat) AS fam_cial_cat,
        i.QryGroup2 AS dimensio_especial_flag,
        i.QryGroup3 AS sac_25_especial_flag,
        RTRIM(l.WhsCode) AS magatzem,
        h.Series AS series, h.DocNum AS docnum
    FROM ORDR h WITH (NOLOCK)
    INNER JOIN RDR1 l WITH (NOLOCK) ON l.DocEntry = h.DocEntry
    INNER JOIN OITM i WITH (NOLOCK) ON i.ItemCode = l.ItemCode
"""

# Família comercial → flag `sac_colagne_normal`
_FAM_COLAGNE = "MOULIN DE COLAGNE"


def _row_to_linia(r) -> Linia:
    tunitat = r.tunitat or ""
    unidades = float(r.linea_unidades or 0)
    pes_sac = _pes_per_tunitat(tunitat, float(r.sal_pack_un) if r.sal_pack_un else None)
    linea_cantidad = unidades * pes_sac
    palet_estoc = _palet_estoc_val(r.palet_producte_estoc_raw)
    fam = (r.fam_cial_cat or "").strip().upper()
    return Linia(
        linea_num=int(r.linea_num) if r.linea_num is not None else 0,
        art_codi=(r.art_codi or "").strip(),
        art_descrip=(r.art_descrip or "").strip(),
        linea_unidades=unidades,
        linea_cantidad=linea_cantidad,
        tunitat=tunitat,
        uxc=float(r.uxc) if r.uxc is not None else None,
        pes=float(r.pes) if r.pes is not None else None,
        cantidadapilable=int(r.cantidadapilable) if r.cantidadapilable is not None else None,
        # RF3 (comanda_minima_produccio): DESACTIVADA a SAP fins que es creï un UDF
        # nou per aquest valor numèric (kg). A Kais els 32 articles amb mínim
        # comencen a aplicar RF3 des del fix de 2026-07-24 (§1.12); a SAP mantenim
        # None fins que hi hagi un camp equivalent a OITM.
        comanda_minima_produccio=None,
        # RF4 (dimensio_especial): REACTIVADA 2026-07-24 (§1.12). Els bugs INF_CONCEPTO
        # i apilament de RF4 s'han corregit a la variant Kais i el motor compartit
        # `regles.py` — reactivem la lectura de QryGroup2 aquí.
        dimensio_especial=(r.dimensio_especial_flag == 'Y'),
        # RF6 sac_25_especial: OITM.QryGroup3 (13 articles migrats des de Kais).
        sac_25_especial=(r.sac_25_especial_flag == 'Y'),
        # `sac_colagne_normal` derivat de la família comercial fins que hi hagi UDF explícit.
        sac_colagne_normal=(fam == _FAM_COLAGNE.upper()),
        aprovisionament_estoc=palet_estoc is not None,
        palet_producte_estoc=palet_estoc,
        magatzem=(r.magatzem or "").strip() or None,
    )


def obtenir_linies(conn, sal_codigo: str, cpa_albara: str, eje_ejercicio: str | None = None) -> list[Linia]:
    """Retorna les línies (`RDR1`) d'una comanda SAP identificada per (Series, DocNum).

    L'argument `eje_ejercicio` s'accepta per compatibilitat i s'ignora (SAP no
    particiona ORDR per exercici; el DocEntry és clau global).
    """
    sal = sal_codigo.strip()
    alb = cpa_albara.strip()
    cache_key = (eje_ejercicio or "", sal, alb)
    if cache_key in _linies_cache:
        ts, cached = _linies_cache[cache_key]
        if (_time.time() - ts) < _LINIES_CACHE_TTL:
            _linies_cache.move_to_end(cache_key)
            from copy import deepcopy
            return deepcopy(cached)  # el motor modifica in-place; protegim el cache

    try:
        series = int(sal)
        docnum = int(alb)
    except ValueError:
        raise ValueError(f"sal_codigo/cpa_albara no numèric: {sal_codigo}/{cpa_albara}")

    sql = _LINIES_SELECT + " WHERE h.Series = ? AND h.DocNum = ? ORDER BY l.LineNum"
    rows = conn.execute(sql, series, docnum).fetchall()
    linies = [_row_to_linia(r) for r in rows]

    if cache_key in _linies_cache:
        _linies_cache.move_to_end(cache_key)
    elif len(_linies_cache) >= _LINIES_CACHE_MAX:
        _linies_cache.popitem(last=False)
    _linies_cache[cache_key] = (_time.time(), linies)
    return linies


def obtenir_linies_batch(conn, pedi_keys: list[tuple]) -> list[Linia]:
    """Retorna les línies de múltiples comandes SAP en una sola query.

    `pedi_keys`: llista de `(sal_codigo, cpa_albara[, eje_ejercicio])`.
    """
    if not pedi_keys:
        return []

    parsed = []
    for k in pedi_keys:
        sal, alb = str(k[0]).strip(), str(k[1]).strip()
        try:
            parsed.append((int(sal), int(alb)))
        except ValueError:
            raise ValueError(f"clau no numèrica: {k}")

    conditions = " OR ".join(["(h.Series = ? AND h.DocNum = ?)"] * len(parsed))
    params: list = []
    for series, docnum in parsed:
        params.extend([series, docnum])

    sql = _LINIES_SELECT + f" WHERE {conditions} ORDER BY h.DocNum, l.LineNum"
    rows = conn.execute(sql, *params).fetchall()
    return [_row_to_linia(r) for r in rows]


# ============================================================
# obtenir_direccio(): CRD1 + UDFs
# ============================================================
def obtenir_direccio(conn, cli_codi: str, adr_codi: str) -> Direccio:
    cache_key = (cli_codi, adr_codi)
    if cache_key in _direccio_cache:
        ts, cached = _direccio_cache[cache_key]
        if (_time.time() - ts) < 600:
            _direccio_cache.move_to_end(cache_key)
            return cached

    sql = """
        SELECT TOP 1
            RTRIM(a.Address) AS adr_codi,
            RTRIM(a.Street) AS street,
            RTRIM(a.City) AS city,
            a.U_SEITIPOD,
            a.U_SEISACOSB,
            a.U_SEIMAXSP,
            a.U_SEIPEDIDOM,
            a.U_SEIPREVAL
        FROM CRD1 a WITH (NOLOCK)
        WHERE a.CardCode = ? AND a.Address = ? AND a.AdresType = 'S'
    """
    r = conn.execute(sql, cli_codi, adr_codi).fetchone()
    if r is None:
        # Fallback sense filtrar per tipus adreça (les d'entrega de vegades no tenen AdresType='S').
        sql2 = """
            SELECT TOP 1
                RTRIM(a.Address) AS adr_codi,
                RTRIM(a.Street) AS street,
                RTRIM(a.City) AS city,
                a.U_SEITIPOD,
                a.U_SEISACOSB,
                a.U_SEIMAXSP,
                a.U_SEIPEDIDOM,
                a.U_SEIPREVAL
            FROM CRD1 a WITH (NOLOCK)
            WHERE a.CardCode = ? AND a.Address = ?
        """
        r = conn.execute(sql2, cli_codi, adr_codi).fetchone()

    if r is None:
        # Sense direcció definida — retornem estructura buida (el motor autodetecta).
        direccio = Direccio(cli_codi=cli_codi, adr_codi=adr_codi)
    else:
        nom_parts = [p for p in ((r.street or "").strip(), (r.city or "").strip()) if p]
        adr_nom = " · ".join(nom_parts) if nom_parts else None
        direccio = Direccio(
            cli_codi=cli_codi,
            adr_codi=adr_codi,
            adr_nom=adr_nom,
            tipus_descarrega=_sap_tipus_descarrega(r.U_SEITIPOD),
            sacs_x_base=_sap_int(r.U_SEISACOSB),
            max_sacs_palet=_sap_int(r.U_SEIMAXSP),
            sacs_comanda_minima=_sap_int(r.U_SEIPEDIDOM),
            preval_direccio_explicit=_sap_preval(r.U_SEIPREVAL),
        )

    if cache_key in _direccio_cache:
        _direccio_cache.move_to_end(cache_key)
    elif len(_direccio_cache) >= _DIRECCIO_CACHE_MAX:
        _direccio_cache.popitem(last=False)
    _direccio_cache[cache_key] = (_time.time(), direccio)
    return direccio


# ============================================================
# obtenir_palet_client(): @SEITARIFACAB + @SEITARIFADET
# ============================================================
def obtenir_palet_client(cli_codi: str, adr_codi: str | None = None, conn=None) -> dict | None:
    """Cerca el tipus de palet negociat pel client a `@SEITARIFACAB/DET`.

    Substitueix el lookup del `PREUSCLIENTS.xlsx` de Kais.

    Si `conn` es passa, es reutilitza (evita deadlock quan el motor ja té una
    connexió oberta i el semàfor només permet 1 connexió simultània). Si no,
    n'obre i tanca una de nova.

    Estrategia:
    - Filtra tarifes actives (U_SEIActivo='Y') del CardCode.
    - Prioritza tarifa que coincideixi amb la direcció exacta (`U_SEIDireccion`
      conté `<adr_codi>-<nom>`).
    - Dins la tarifa triada, agafa la primera línia amb ItemName que comença per 'PALET'.
    """
    cache_key = (cli_codi, adr_codi or "")
    if cache_key in _palet_client_cache:
        ts, cached = _palet_client_cache[cache_key]
        if (_time.time() - ts) < _PALET_CLIENT_CACHE_TTL:
            _palet_client_cache.move_to_end(cache_key)
            return cached

    _own_conn = conn is None
    if _own_conn:
        conn = connectar()
    try:
        sql = """
            SELECT TOP 1
                RTRIM(d.U_SEIItemCode) AS art_codi,
                RTRIM(d.U_SEIItemName) AS art_descrip
            FROM [@SEITARIFACAB] c WITH (NOLOCK)
            INNER JOIN [@SEITARIFADET] d WITH (NOLOCK) ON d.DocEntry = c.DocEntry
            WHERE c.U_SEICardCode = ?
              AND c.U_SEIActivo = 'Y'
              AND c.Canceled <> 'Y'
              AND UPPER(RTRIM(d.U_SEIItemName)) LIKE 'PALET%'
              AND (d.U_SEIFechaFin IS NULL OR d.U_SEIFechaFin >= GETDATE())
            ORDER BY
                CASE WHEN ? IS NOT NULL AND c.U_SEIDireccion LIKE ? THEN 0 ELSE 1 END,
                c.DocEntry DESC
        """
        adr_pattern = f"{adr_codi}-%" if adr_codi else None
        r = conn.execute(sql, cli_codi, adr_codi, adr_pattern).fetchone()
    finally:
        if _own_conn:
            conn.close()

    result = None
    if r and r.art_codi:
        result = {"art_codi": r.art_codi.strip(), "art_descrip": (r.art_descrip or "").strip()}

    if cache_key in _palet_client_cache:
        _palet_client_cache.move_to_end(cache_key)
    elif len(_palet_client_cache) >= _PALET_CLIENT_CACHE_MAX:
        _palet_client_cache.popitem(last=False)
    _palet_client_cache[cache_key] = (_time.time(), result)
    return result


# ============================================================
# obtenir_palet_comanda(): línia de palet inclosa a la comanda
# ============================================================
def obtenir_palet_comanda(conn, sal_codigo: str, cpa_albara: str, eje_ejercicio: str | None = None) -> dict | None:
    """Detecta la línia de palet (UoM='UNI' amb nom que conté 'PALET') dins la comanda."""
    sal = sal_codigo.strip()
    alb = cpa_albara.strip()
    cache_key = (eje_ejercicio or "", sal, alb)
    if cache_key in _palet_comanda_cache:
        ts, cached = _palet_comanda_cache[cache_key]
        if (_time.time() - ts) < _PALET_COMANDA_CACHE_TTL:
            return cached

    try:
        series = int(sal)
        docnum = int(alb)
    except ValueError:
        return None

    sql = """
        SELECT TOP 1
            RTRIM(l.ItemCode) AS art_codi,
            RTRIM(l.Dscription) AS art_descrip
        FROM ORDR h WITH (NOLOCK)
        INNER JOIN RDR1 l WITH (NOLOCK) ON l.DocEntry = h.DocEntry
        INNER JOIN OITM i WITH (NOLOCK) ON i.ItemCode = l.ItemCode
        WHERE h.Series = ? AND h.DocNum = ?
          AND i.SalUnitMsr = 'UNI'
          AND UPPER(RTRIM(l.Dscription)) LIKE '%PALET%'
    """
    row = conn.execute(sql, series, docnum).fetchone()
    result = {"art_codi": row.art_codi, "art_descrip": row.art_descrip} if row else None

    if len(_palet_comanda_cache) >= 500:
        _palet_comanda_cache.clear()
    _palet_comanda_cache[cache_key] = (_time.time(), result)
    return result


# ============================================================
# obtenir_descrip_article(): OITM
# ============================================================
def obtenir_descrip_article(conn, art_codi: str) -> str:
    if art_codi in _descrip_cache:
        return _descrip_cache[art_codi]
    sql = "SELECT TOP 1 RTRIM(ItemName) AS art_descrip FROM OITM WITH (NOLOCK) WHERE ItemCode = ?"
    row = conn.execute(sql, art_codi).fetchone()
    result = (row.art_descrip or art_codi) if row else art_codi
    if len(_descrip_cache) >= _DESCRIP_CACHE_MAX:
        _descrip_cache.clear()
    _descrip_cache[art_codi] = result
    return result


# ============================================================
# obtenir_ultimes_comandes(): ORDR obertes
# ============================================================
def obtenir_ultimes_comandes(conn, limit: int = 1000) -> list[dict]:
    """Comandes obertes (`ORDR.DocStatus='O'`) de l'any actual, excloent
    aquelles que només contenen articles GRA (granel)."""
    sql = """
        SELECT TOP (?)
            CAST(h.Series AS NVARCHAR(10)) AS pedi_serie,
            CAST(h.Series AS NVARCHAR(10)) AS sal_codigo,
            CAST(h.DocNum AS NVARCHAR(20)) AS pedi_numero,
            RTRIM(h.CardCode) AS cli_codi,
            RTRIM(bp.CardName) AS cli_nom,
            RTRIM(h.ShipToCode) AS pedi_dire,
            h.DocDate AS pedi_fech,
            h.DocDate AS data_comanda,
            h.DocDueDate AS data_servir,
            (SELECT COUNT(*) FROM RDR1 l WITH (NOLOCK) WHERE l.DocEntry = h.DocEntry) AS num_linies,
            (SELECT COALESCE(SUM(CASE WHEN i.SalUnitMsr LIKE 'S%' THEN l.Quantity ELSE 0 END), 0)
                FROM RDR1 l WITH (NOLOCK)
                INNER JOIN OITM i WITH (NOLOCK) ON i.ItemCode = l.ItemCode
                WHERE l.DocEntry = h.DocEntry) AS total_unitats,
            RTRIM((SELECT TOP 1 l2.WhsCode FROM RDR1 l2 WITH (NOLOCK) WHERE l2.DocEntry = h.DocEntry ORDER BY l2.LineNum)) AS almacen,
            RTRIM(sp.SlpName) AS agent,
            RTRIM(h.NumAtCard) AS num_pedido_kais
        FROM ORDR h WITH (NOLOCK)
        LEFT JOIN OCRD bp WITH (NOLOCK) ON bp.CardCode = h.CardCode
        LEFT JOIN OSLP sp WITH (NOLOCK) ON sp.SlpCode = h.SlpCode
        WHERE h.DocStatus = 'O'
          AND YEAR(h.DocDate) = YEAR(GETDATE())
          AND NOT EXISTS (
              SELECT 1 FROM RDR1 lg WITH (NOLOCK)
              INNER JOIN OITM ig WITH (NOLOCK) ON ig.ItemCode = lg.ItemCode
              WHERE lg.DocEntry = h.DocEntry
                AND ig.SalUnitMsr = 'GRA'
                AND NOT EXISTS (
                    SELECT 1 FROM RDR1 lp WITH (NOLOCK)
                    INNER JOIN OITM ip WITH (NOLOCK) ON ip.ItemCode = lp.ItemCode
                    WHERE lp.DocEntry = h.DocEntry AND ip.SalUnitMsr LIKE 'S%'
                )
          )
        ORDER BY h.DocDate DESC, h.DocNum DESC
    """
    rows = conn.execute(sql, limit).fetchall()
    return [
        {
            "pedi_numero": r.pedi_numero or "",
            "pedi_serie": r.pedi_serie or "",
            "sal_codigo": r.sal_codigo or "",
            "cli_codi": (r.cli_codi or "").strip(),
            "cli_nom": r.cli_nom or "",
            "pedi_dire": r.pedi_dire or "",
            "pedi_fech": r.data_comanda.strftime("%d/%m/%Y") if r.data_comanda else
                         (r.pedi_fech.strftime("%d/%m/%Y") if r.pedi_fech else ""),
            "data_servir": r.data_servir.strftime("%d/%m/%Y") if r.data_servir else "",
            "num_linies": int(r.num_linies or 0),
            "total_unitats": int(r.total_unitats or 0),
            "almacen": (r.almacen or "").strip(),
            "agent": (r.agent or "").strip(),
            "num_pedido_kais": (r.num_pedido_kais or "").strip(),
        }
        for r in rows
    ]


# ============================================================
# obtenir_recompte_comandes(): fingerprint per polling
# ============================================================
def obtenir_recompte_comandes(conn) -> dict:
    sql = """
        SELECT
            COUNT(*) AS total,
            CHECKSUM_AGG(BINARY_CHECKSUM(Series, DocNum, CardCode, ShipToCode, UpdateDate)) AS fingerprint
        FROM ORDR WITH (NOLOCK)
        WHERE DocStatus = 'O'
          AND YEAR(DocDate) = YEAR(GETDATE())
    """
    r = conn.execute(sql).fetchone()
    return {
        "total": int(r.total or 0),
        "fingerprint": int(r.fingerprint or 0),
    }


# ============================================================
# obtenir_noms_magatzems(): OWHS
# ============================================================
def obtenir_noms_magatzems(conn) -> dict:
    global _noms_magatzems_cache
    if _noms_magatzems_cache is not None:
        return _noms_magatzems_cache
    sql = "SELECT RTRIM(WhsCode) AS codi, RTRIM(WhsName) AS nom FROM OWHS WITH (NOLOCK)"
    rows = conn.execute(sql).fetchall()
    _noms_magatzems_cache = {r.codi.strip(): (r.nom.strip() if r.nom else "") for r in rows}
    return _noms_magatzems_cache


def obtenir_magatzems_from_comandes(conn, comandes: list[dict]) -> list[dict]:
    noms = obtenir_noms_magatzems(conn)
    seen = set()
    result = []
    for c in comandes:
        alm = (c.get("almacen") or "").strip()
        if alm and alm not in seen:
            seen.add(alm)
            result.append({"almacen": alm, "nom": noms.get(alm, "")})
    return sorted(result, key=lambda x: x["almacen"])


# ============================================================
# obtenir_comandes_a_calcular(): trigger UDF U_FCCalcular='S'
# ============================================================
# Cache d'existència del UDF U_FCCalcular a ORDR — perquè el pendent que
# el consultor el creï, cada crida no repeteixi la comprovació INFORMATION_SCHEMA.
_udf_calcular_existeix_cache: bool | None = None


def _udf_calcular_exists(conn) -> bool:
    """Retorna True si el UDF `ORDR.U_FCCalcular` existeix a la BD SAP.

    Cachejat en memòria després de la primera comprovació (l'existència
    d'un UDF és un canvi molt puntual d'entorn).
    """
    global _udf_calcular_existeix_cache
    if _udf_calcular_existeix_cache is not None:
        return _udf_calcular_existeix_cache
    row = conn.execute(
        "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_NAME='ORDR' AND COLUMN_NAME='U_FCCalcular'"
    ).fetchone()
    _udf_calcular_existeix_cache = bool(row and row[0] > 0)
    if not _udf_calcular_existeix_cache:
        logger.warning(
            "UDF ORDR.U_FCCalcular NO existeix — obtenir_comandes_a_calcular "
            "retornarà [] fins que el consultor SAP el creï."
        )
    return _udf_calcular_existeix_cache


def obtenir_comandes_a_calcular(conn) -> list[dict]:
    """Retorna les comandes obertes marcades per l'usuari com "a calcular".

    Trigger: l'usuari edita la comanda al formulari Sales Order de SAP, marca
    `U_FCCalcular='S'` i desa. El worker de sync polleja aquesta funció
    periòdicament, calcula, escriu el resum als altres UDFs `U_FCEmbalatge*`
    i posa `U_FCCalcular='N'` (via Service Layer).

    Retorna: lista de dicts amb `doc_entry`, `series`, `docnum`, `card_code`.
    Si el UDF encara no existeix a SAP (consultor pendent), retorna [].
    """
    if not _udf_calcular_exists(conn):
        return []

    sql = """
        SELECT h.DocEntry, h.Series, h.DocNum, RTRIM(h.CardCode) AS CardCode
        FROM ORDR h WITH (NOLOCK)
        WHERE h.DocStatus = 'O'
          AND h.U_FCCalcular = 'S'
        ORDER BY h.DocEntry
    """
    rows = conn.execute(sql).fetchall()
    return [
        {
            "doc_entry": int(r.DocEntry),
            "series": int(r.Series),
            "docnum": int(r.DocNum),
            "card_code": r.CardCode or "",
        }
        for r in rows
    ]
