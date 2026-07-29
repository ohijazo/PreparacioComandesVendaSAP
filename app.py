import _bootstrap  # noqa: F401 — insereix KAIS_APP_PATH a sys.path abans de qualsevol altre import
import csv
import hmac
import io
import logging
import os
import subprocess
import time
import threading
from flask import Flask, render_template, jsonify, request, Response
from motor import calcular_embalatges, calcular_embalatges_agrupats, validar_dades_mestres
from consultes import connectar, obtenir_ultimes_comandes, obtenir_comanda_per_numero, obtenir_recompte_comandes, obtenir_magatzems_from_comandes, obtenir_noms_magatzems, obtenir_titols_infoanex, obtenir_titols_infoanex_clienvio, obtenir_metadata_ordr_per_doc_entry
from models import Estat  # compartit via _bootstrap
from mailer import enviar_correu_autoritzacio, LLINDAR_KG_AUTORITZACIO, obtenir_defaults_destinataris  # compartit via _bootstrap
from sap_service_layer import SLClient, SLError
from sap_line_builder import (
    generar_linies_palet_sap,
    MARCADOR_LINIA_PALET_UDF,
    MARCADOR_LINIA_PALET_VALOR,
)

# ============================================================
# Cache amb TTL + single-flight per endpoints de polling
# ============================================================
_cache_lock = threading.Lock()
_cache = {}  # clau -> {"data": ..., "ts": time.time()}

# Single-flight: un Lock per clau evita queries SQL concurrents duplicades.
# Si 2 requests arriben alhora amb cache expirat, només 1 executa la query.
_query_locks = {
    "ultimes_comandes": threading.Lock(),
    "comandes_check": threading.Lock(),
    "magatzems": threading.Lock(),
}

_CACHE_TTL = {
    "comandes_check": 55,       # 55 segons (frontend fa polling cada 60-75s)
    "ultimes_comandes": 55,     # 55 segons (refresca quan el frontend ho demana)
    "magatzems": 300,           # 5 minuts (dades estables)
}


def _cache_get(key):
    """Retorna dades cachejades si no han expirat, o None."""
    with _cache_lock:
        entry = _cache.get(key)
        if entry and (time.time() - entry["ts"]) < _CACHE_TTL.get(key, 10):
            return entry["data"]
    return None


def _cache_set(key, data):
    """Guarda dades al cache."""
    with _cache_lock:
        _cache[key] = {"data": data, "ts": time.time()}


def _cached_query(key, compute_fn):
    """Cache amb single-flight: evita queries SQL concurrents duplicades.

    Si el cache és vàlid, retorna directament.
    Si no, adquireix el lock (1 sol thread executa la query),
    comprova el cache de nou (l'altre thread pot haver-lo omplert),
    i només llavors executa compute_fn.
    """
    cached = _cache_get(key)
    if cached is not None:
        return cached
    lock = _query_locks.get(key)
    if lock is None:
        return compute_fn()
    with lock:
        # Double-check: un altre thread pot haver omplert el cache
        cached = _cache_get(key)
        if cached is not None:
            return cached
        result = compute_fn()
        _cache_set(key, result)
        return result

# ============================================================
# Logging
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("motor.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("motor")

app = Flask(__name__)


# ============================================================
# Helper: serialitzar resultat
# ============================================================
def _calcular_pes_per_sac(resultat):
    """Retorna {art_codi: kg/sac} a partir de les línies de la comanda."""
    pes_per_sac = {}
    for l in resultat.linies:
        if l.linea_unidades and l.linea_unidades > 0 and l.linea_cantidad:
            pes_per_sac[l.art_codi] = l.linea_cantidad / l.linea_unidades
    return pes_per_sac


def _calcular_pes_total(resultat):
    """Suma del pes (kg) de totes les línies de la comanda."""
    return sum(l.linea_cantidad for l in resultat.linies if l.linea_cantidad)


def _serialitzar_resultat(resultat):
    """Converteix un Resultat del motor a dict JSON-serialitzable."""
    comanda = None
    if resultat.comanda:
        comanda = {
            "pedi_num": resultat.comanda.pedi_num,
            "pedi_numero": resultat.comanda.pedi_numero,
            "pedi_serie": resultat.comanda.pedi_serie,
            "pedi_ejercicio": resultat.comanda.pedi_ejercicio,
            "cli_codi": resultat.comanda.cli_codi,
            "cli_nom": resultat.comanda.cli_nom or "",
            "num_pedido_kais": resultat.comanda.num_pedido_kais or "",
            "pedi_dire": resultat.comanda.pedi_dire,
            "pedi_fech": resultat.comanda.pedi_fech.strftime("%d/%m/%Y")
                if resultat.comanda.pedi_fech else None,
            "data_comanda": resultat.comanda.data_comanda.strftime("%d/%m/%Y")
                if resultat.comanda.data_comanda else None,
            "data_servir": resultat.comanda.data_servir.strftime("%d/%m/%Y")
                if resultat.comanda.data_servir else None,
        }

    direccio = None
    if resultat.direccio:
        d = resultat.direccio
        direccio = {
            "cli_codi": d.cli_codi,
            "adr_codi": d.adr_codi,
            "adr_nom": d.adr_nom,
            "tipus_descarrega": d.tipus_descarrega,
            "sacs_x_base": d.sacs_x_base,
            "max_sacs_palet": d.max_sacs_palet,
            "sacs_comanda_minima": d.sacs_comanda_minima,
            "preval_direccio": d.preval_direccio,
        }

    linies = []
    for l in resultat.linies:
        linies.append({
            "linea_num": l.linea_num,
            "art_codi": l.art_codi,
            "art_descrip": l.art_descrip,
            "linea_unidades": int(l.linea_unidades),
            "tunitat": l.tunitat,
        })

    # Lookup pes per sac (kg) per article
    pes_per_sac = {}
    for l in resultat.linies:
        if l.linea_unidades and l.linea_unidades > 0 and l.linea_cantidad:
            pes_per_sac[l.art_codi] = l.linea_cantidad / l.linea_unidades

    # Construir lookup de descripcions de palets
    palet_descrip = {}
    for p in resultat.palets:
        palet_descrip[p.art_codi] = p.art_descrip

    # Trobar el tipus palet resolt per embalatges sense tipus explícit
    tipus_palet_defecte = None
    tipus_palet_defecte_descrip = None
    for p in resultat.palets:
        if p.art_codi not in {e.tipus_palet for e in resultat.embalatges if e.tipus_palet}:
            tipus_palet_defecte = p.art_codi
            tipus_palet_defecte_descrip = p.art_descrip
            break

    embalatges = []
    for e in resultat.embalatges:
        tp = e.tipus_palet or tipus_palet_defecte
        tp_descrip = palet_descrip.get(tp, tipus_palet_defecte_descrip) if tp else None
        embalatges.append({
            "palet_num": e.palet_num,
            "contingut": [
                {
                    "art_codi": c.art_codi,
                    "art_descrip": c.art_descrip,
                    "sacs": c.sacs,
                    "sacs_x_base": c.sacs_x_base,
                    "pes_kg": round(c.sacs * pes_per_sac.get(c.art_codi, 0), 1),
                }
                for c in e.contingut
            ],
            "total_sacs": e.total_sacs,
            "sacs_x_base": e.sacs_x_base,
            "max_sacs": e.max_sacs,
            "es_embalatge_propi": e.es_embalatge_propi,
            "tipus_palet": tp,
            "tipus_palet_descrip": tp_descrip,
        })

    palets = []
    for p in resultat.palets:
        palets.append({
            "art_codi": p.art_codi,
            "art_descrip": p.art_descrip,
            "quantitat": p.quantitat,
            "es_fisic": p.es_fisic,
        })

    total_sacs = sum(e.total_sacs for e in resultat.embalatges)

    # Validació de dades mestres
    avisos_dades = []
    if resultat.comanda:
        try:
            avisos_dades = validar_dades_mestres(
                resultat.comanda.pedi_serie, resultat.comanda.pedi_numero,
                linies=resultat.linies, direccio=resultat.direccio,
            )
        except Exception as e:
            logger.warning("validar_dades_mestres(%s/%s): %s",
                           resultat.comanda.pedi_serie, resultat.comanda.pedi_numero, e)

    return {
        "estat": resultat.estat.value,
        "comanda": comanda,
        "direccio": direccio,
        "linies": linies,
        "embalatges": embalatges,
        "palets": palets,
        "missatges": resultat.missatges,
        "trazabilitat": resultat.trazabilitat,
        "avisos_dades": avisos_dades,
        "resum": {
            "total_sacs": total_sacs,
            "total_palets": len(resultat.embalatges),
            "total_palets_tipus": sum(p.quantitat for p in resultat.palets),
        },
        "mail_defaults": obtenir_defaults_destinataris(),
    }, pes_per_sac


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/ajuda")
def ajuda():
    return render_template("ajuda.html")


@app.route("/calendari")
def calendari():
    calendari_url = os.environ.get(
        "CALENDARI_URL", "http://agrupacions.agrienergia.local/calendari"
    )
    return render_template("calendari.html", calendari_url=calendari_url)


@app.route("/api/buscar/<path:serie_numero>")
def api_buscar(serie_numero):
    """Cerca comanda per sal_codigo/cpa_albara i retorna la clau.
    Format esperat: SERIE/NUMERO (ex: 51/0002456)."""
    try:
        if "/" in serie_numero:
            parts = serie_numero.split("/", 1)
            sal_codigo = parts[0]
            cpa_albara = parts[1]
        else:
            return jsonify({"ok": False, "error": f"Format invàlid. Usa Sèrie/Número (ex: 51/0002456)"}), 400
        conn = connectar()
        try:
            comanda = obtenir_comanda_per_numero(conn, sal_codigo, cpa_albara)
            logger.info("Buscar %s/%s -> trobada", sal_codigo, cpa_albara)
            return jsonify({
                "ok": True,
                "pedi_serie": comanda.pedi_serie,
                "pedi_numero": comanda.pedi_numero,
            })
        finally:
            conn.close()
    except ValueError as e:
        logger.warning("Buscar %s: %s", serie_numero, e)
        return jsonify({"ok": False, "error": str(e)}), 404
    except Exception as e:
        logger.error("Buscar %s: %s", serie_numero, e, exc_info=True)
        return jsonify({"ok": False, "error": f"Error intern: {str(e)}"}), 500


@app.route("/api/calcular/<path:serie_numero>")
def api_calcular(serie_numero):
    """Calcula embalatges per una comanda. Format: sal_codigo/cpa_albara."""
    t0 = time.time()
    try:
        if "/" not in serie_numero:
            return jsonify({"ok": False, "error": "Format invàlid. Usa Sèrie/Número"}), 400

        parts = serie_numero.split("/", 1)
        sal_codigo = parts[0]
        cpa_albara = parts[1]
        forcar = request.args.get("forcar", "0") == "1"

        resultat = calcular_embalatges(sal_codigo, cpa_albara, forcar=forcar)
        elapsed = time.time() - t0

        serie = resultat.comanda.pedi_serie if resultat.comanda else "?"
        numero = resultat.comanda.pedi_numero if resultat.comanda else "?"
        logger.info(
            "Calcular %s/%s -> %s, %d embalatges, %.2fs%s",
            serie, numero,
            resultat.estat.value,
            len(resultat.embalatges),
            elapsed,
            " [FORÇAT]" if forcar else "",
        )

        data, _ = _serialitzar_resultat(resultat)
        data["ok"] = True
        data["forcat"] = forcar
        return jsonify(data)

    except ValueError as e:
        logger.warning("Calcular %s: %s", serie_numero, e)
        return jsonify({"ok": False, "error": str(e)}), 404
    except Exception as e:
        logger.error("Calcular %s: %s", serie_numero, e, exc_info=True)
        return jsonify({"ok": False, "error": f"Error intern: {str(e)}"}), 500


@app.route("/api/calcular-batch", methods=["POST"])
def api_calcular_batch():
    """Calcula embalatges per múltiples comandes en un sol request.

    Body JSON: {"keys": ["serie/numero", ...]}
    Retorna: {"ok": true, "resultats": {"serie/numero": {...}, ...}}
    """
    t0 = time.time()
    try:
        data = request.get_json()
        keys = data.get("keys", [])
        if not keys or not isinstance(keys, list):
            return jsonify({"ok": False, "error": "Cal una llista de keys"}), 400
        if len(keys) > 50:
            return jsonify({"ok": False, "error": "Màxim 50 comandes per batch"}), 400

        # Connexió compartida per tot el batch (1 connexió en lloc de N×2)
        resultats = {}
        conn = connectar()
        try:
            for key in keys:
                if "/" not in key:
                    resultats[key] = {"ok": False, "error": "Format invàlid"}
                    continue
                parts = key.split("/", 1)
                try:
                    resultat = calcular_embalatges(parts[0], parts[1],
                                                   conn_compartida=conn)
                    r, _ = _serialitzar_resultat(resultat)
                    r["ok"] = True
                    resultats[key] = r
                except ValueError as e:
                    resultats[key] = {"ok": False, "error": str(e)}
                except Exception as e:
                    resultats[key] = {"ok": False, "error": f"Error: {str(e)}"}
        finally:
            conn.close()

        elapsed = time.time() - t0
        logger.info("Calcular-batch %d comandes, %.2fs", len(keys), elapsed)
        return jsonify({"ok": True, "resultats": resultats})

    except Exception as e:
        logger.error("Calcular-batch: %s", e, exc_info=True)
        return jsonify({"ok": False, "error": f"Error intern: {str(e)}"}), 500


@app.route("/api/ultimes-comandes")
def api_ultimes_comandes():
    try:
        def _fetch():
            conn = connectar()
            try:
                return obtenir_ultimes_comandes(conn)
            finally:
                conn.close()
        comandes = _cached_query("ultimes_comandes", _fetch)
        return jsonify({"ok": True, "comandes": comandes})
    except Exception as e:
        logger.error("Ultimes comandes: %s", e, exc_info=True)
        return jsonify({"ok": False, "error": f"Error intern: {str(e)}"}), 500


@app.route("/api/magatzems")
def api_magatzems():
    try:
        def _fetch():
            # Derivar magatzems des de les comandes ja carregades (sense query GRA)
            comandes = _cache_get("ultimes_comandes")
            conn = connectar()
            try:
                if comandes is None:
                    comandes = obtenir_ultimes_comandes(conn)
                    _cache_set("ultimes_comandes", comandes)
                return obtenir_magatzems_from_comandes(conn, comandes)
            finally:
                conn.close()
        magatzems = _cached_query("magatzems", _fetch)
        return jsonify({"ok": True, "magatzems": magatzems})
    except Exception as e:
        logger.error("Magatzems: %s", e, exc_info=True)
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/comandes-check")
def api_comandes_check():
    """Endpoint lleuger per polling: retorna recompte i fingerprint."""
    try:
        def _fetch():
            conn = connectar()
            try:
                return obtenir_recompte_comandes(conn)
            finally:
                conn.close()
        data = _cached_query("comandes_check", _fetch)
        return jsonify({"ok": True, **data})
    except Exception as e:
        return jsonify({"ok": False}), 500


@app.route("/api/calcular-agrupat", methods=["POST"])
def api_calcular_agrupat():
    """Calcula embalatges agrupant múltiples comandes del mateix client."""
    t0 = time.time()
    try:
        data = request.get_json()
        pedi_keys = data.get("pedi_keys", [])
        forcar = data.get("forcar", False)

        if not pedi_keys or not isinstance(pedi_keys, list):
            return jsonify({"ok": False, "error": "Cal una llista de pedi_keys [{serie, numero}]"}), 400

        keys = []
        for k in pedi_keys:
            if isinstance(k, dict) and "serie" in k and "numero" in k:
                keys.append((k["serie"], k["numero"]))
            else:
                return jsonify({"ok": False, "error": "Cada clau ha de tenir 'serie' i 'numero'"}), 400

        resultat = calcular_embalatges_agrupats(keys, forcar=forcar)
        elapsed = time.time() - t0

        logger.info(
            "Calcular agrupat %s -> %s, %d embalatges, %.2fs",
            keys, resultat.estat.value, len(resultat.embalatges), elapsed,
        )

        resp, _ = _serialitzar_resultat(resultat)
        resp["ok"] = True
        resp["forcat"] = forcar
        resp["agrupat"] = True
        resp["pedi_keys"] = [{"serie": s, "numero": n} for s, n in keys]
        return jsonify(resp)

    except ValueError as e:
        logger.warning("Calcular agrupat: %s", e)
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:
        logger.error("Calcular agrupat: %s", e, exc_info=True)
        return jsonify({"ok": False, "error": f"Error intern: {str(e)}"}), 500


# ============================================================
# /api/afegir-palets — Botó B1UP al Sales Order de SAP
# ============================================================
def _sl_client() -> SLClient:
    """Crea un SLClient a partir de les variables d'entorn SAP_SL_*.

    Requereix .env amb: SAP_SL_URL, SAP_SL_COMPANY, SAP_SL_USER,
    SAP_SL_PASSWORD, opcional SAP_SL_VERIFY_SSL, SAP_SL_TIMEOUT.
    """
    url = os.environ["SAP_SL_URL"]
    company = os.environ["SAP_SL_COMPANY"]
    user = os.environ["SAP_SL_USER"]
    pwd = os.environ["SAP_SL_PASSWORD"]
    verify = os.environ.get("SAP_SL_VERIFY_SSL", "true").lower() not in ("false", "0", "no")
    timeout = int(os.environ.get("SAP_SL_TIMEOUT", "15"))
    return SLClient(url, company, user, pwd, verify=verify, timeout=timeout)


@app.route("/api/afegir-palets/<int:doc_entry>", methods=["POST"])
def api_afegir_palets(doc_entry: int):
    """Calcula embalatges i afegeix línies palet físiques a la comanda SAP.

    Invocat pel botó B1UP al formulari Sales Order (form 139). El botó
    passa el DocEntry actual i aquest endpoint:
      1. Cerca (Series, DocNum, WhsCode) a ORDR/RDR1.
      2. Executa el motor RF1-RF14 amb dades de SAP.
      3. Filtra els palets físics (`es_fisic=True`) i genera línies OData.
      4. Substitueix netament les línies palet velles (marcades amb
         U_FCAfegit='Y') per les noves (patró GET-modify-PATCH via SL).

    Query params:
      forcar=1  → invalidar cache del motor abans de calcular.

    Retorna JSON amb estructura:
      { ok, doc_entry, estat, linies_afegides, linies_actualitzades,
        linies_esborrades, resum:{total_palets,total_sacs}, missatges }
    """
    t0 = time.time()
    conn = None
    try:
        # 1. Metadades comanda a partir del DocEntry
        conn = connectar()
        meta = obtenir_metadata_ordr_per_doc_entry(conn, doc_entry)
        conn.close()
        conn = None

        if meta["doc_status"] != "O":
            return jsonify({
                "ok": False,
                "error": f"La comanda {doc_entry} no està oberta (DocStatus={meta['doc_status']!r})",
            }), 400

        # 2. Càlcul del motor
        forcar = request.args.get("forcar", "0") == "1"
        resultat = calcular_embalatges(meta["series"], meta["docnum"], forcar=forcar)

        if resultat.estat == Estat.NO_CALCULABLE:
            return jsonify({
                "ok": False,
                "doc_entry": doc_entry,
                "estat": resultat.estat.value,
                "missatges": resultat.missatges,
                "error": f"Comanda no processable ({resultat.estat.value})",
            }), 400
        # SOTA_MINIM: el motor calcula igualment la proposta d'embalatge (com
        # a Kais). S'afegeixen les línies palet perquè l'operari les vegi;
        # els missatges de RF2 STOP viatgen al camp `missatges` per avís.

        # 3. Generar línies palet físiques
        linies_noves = generar_linies_palet_sap(resultat.palets, meta["whs_code"])

        # 4. Substituir línies velles via SL (o esborrar si no n'hi ha de noves)
        with _sl_client() as sl:
            stats = sl.replace_marked_lines(
                doc_entry,
                MARCADOR_LINIA_PALET_UDF,
                MARCADOR_LINIA_PALET_VALOR,
                linies_noves,
            )

        elapsed = time.time() - t0
        logger.info(
            "afegir-palets DocEntry=%d Series=%s/DocNum=%s → +%d ~%d -%d (%.2fs)",
            doc_entry, meta["series"], meta["docnum"],
            stats["added"], stats.get("updated", 0), stats["removed"], elapsed,
        )

        return jsonify({
            "ok": True,
            "doc_entry": doc_entry,
            "estat": resultat.estat.value,
            "linies_afegides": stats["added"],
            "linies_actualitzades": stats.get("updated", 0),
            "linies_esborrades": stats["removed"],
            "resum": {
                "total_palets": len(resultat.embalatges),
                "total_sacs": sum(e.total_sacs for e in resultat.embalatges),
            },
            "missatges": resultat.missatges,
        })

    except ValueError as e:
        # Comanda no trobada, DocEntry invàlid…
        logger.warning("afegir-palets(%d): %s", doc_entry, e)
        return jsonify({"ok": False, "error": str(e)}), 404
    except SLError as e:
        logger.error("afegir-palets(%d) SL error: %s", doc_entry, e)
        return jsonify({
            "ok": False,
            "error": f"Service Layer: {e}",
            "sap_code": getattr(e, "status_code", None),
        }), 502
    except Exception as e:
        logger.exception("afegir-palets(%d) error intern", doc_entry)
        return jsonify({"ok": False, "error": f"Error intern: {e}"}), 500
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


@app.route("/api/exportar-csv/<path:serie_numero>")
def api_exportar_csv(serie_numero):
    """Exporta el resultat del càlcul en format CSV."""
    try:
        if "/" not in serie_numero:
            return jsonify({"ok": False, "error": "Format invàlid"}), 400

        parts = serie_numero.split("/", 1)
        sal_codigo = parts[0]
        cpa_albara = parts[1]

        resultat = calcular_embalatges(sal_codigo, cpa_albara)
        output = io.StringIO()
        writer = csv.writer(output, delimiter=';')

        # Capçalera comanda
        serie = resultat.comanda.pedi_serie if resultat.comanda else sal_codigo
        numero = resultat.comanda.pedi_numero if resultat.comanda else cpa_albara
        writer.writerow(["Comanda", f"{serie}/{numero}"])
        if resultat.comanda:
            writer.writerow(["Client", resultat.comanda.cli_codi])
            writer.writerow(["Data", resultat.comanda.pedi_fech.strftime("%d/%m/%Y") if resultat.comanda.pedi_fech else ""])
        writer.writerow(["Estat", resultat.estat.value])
        writer.writerow([])

        # Embalatges
        writer.writerow(["Palet", "Article", "Descripcio", "Sacs", "Pes_kg", "Base", "Max", "Tipus_Palet"])
        _, pes_per_sac = _serialitzar_resultat(resultat)

        for e in resultat.embalatges:
            for c in e.contingut:
                pes = round(c.sacs * pes_per_sac.get(c.art_codi, 0), 1)
                writer.writerow([
                    e.palet_num, c.art_codi, c.art_descrip, c.sacs,
                    pes, e.sacs_x_base, e.max_sacs, e.tipus_palet or ""
                ])

        writer.writerow([])
        writer.writerow(["Total Sacs", sum(e.total_sacs for e in resultat.embalatges)])
        writer.writerow(["Total Palets", len(resultat.embalatges)])

        filename = f"comanda_{serie}_{numero}.csv".replace("/", "_")
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        logger.error("Exportar CSV %s: %s", serie_numero, e, exc_info=True)
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/sol-licitar-autoritzacio/<path:serie_numero>", methods=["POST"])
def api_sol_licitar_autoritzacio(serie_numero):
    """Envia un correu de sol·licitud d'autorització per comandes < 500 kg.

    El llindar es revalida al backend per evitar bypass via DevTools.
    El destinatari real depèn de MAIL_MODE (test/prod) al .env.
    """
    try:
        if "/" not in serie_numero:
            return jsonify({"ok": False, "error": "Format invàlid"}), 400
        sal_codigo, cpa_albara = serie_numero.split("/", 1)

        resultat = calcular_embalatges(sal_codigo, cpa_albara, forcar=True)
        if resultat.comanda is None:
            return jsonify({"ok": False, "error": "Comanda no trobada"}), 404

        pes_total = _calcular_pes_total(resultat)
        if pes_total <= 0:
            return jsonify({
                "ok": False,
                "error": "No es pot determinar el pes de la comanda (sense dades de pes per sac)."
            }), 400
        if pes_total >= LLINDAR_KG_AUTORITZACIO:
            return jsonify({
                "ok": False,
                "error": f"La comanda té {pes_total:.0f} kg, supera el llindar de {LLINDAR_KG_AUTORITZACIO} kg."
            }), 400

        pes_per_sac = _calcular_pes_per_sac(resultat)

        # Overrides opcionals de To/CC des de la UI (modal editable)
        body = request.get_json(silent=True) or {}
        to_override = body.get("to")
        cc_override = body.get("cc")

        result = enviar_correu_autoritzacio(
            resultat, pes_total, pes_per_sac,
            to_override=to_override, cc_override=cc_override,
        )
        status = 200 if result.get("ok") else 502
        return jsonify(result), status
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 404
    except Exception as e:
        logger.error("Sol·licitud autorització %s: %s", serie_numero, e, exc_info=True)
        return jsonify({"ok": False, "error": "Error intern enviant el correu"}), 500


@app.route("/api/validar-dades/<path:serie_numero>")
def api_validar_dades(serie_numero):
    try:
        if "/" not in serie_numero:
            return jsonify({"ok": False, "error": "Format invàlid"}), 400
        parts = serie_numero.split("/", 1)
        avisos = validar_dades_mestres(parts[0], parts[1])
        return jsonify({"ok": True, "avisos": avisos})
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 404
    except Exception as e:
        logger.error("Validar dades %s: %s", serie_numero, e, exc_info=True)
        return jsonify({"ok": False, "error": f"Error intern: {str(e)}"}), 500


# Rate limiting bàsic per l'endpoint admin
_admin_intents = {}  # IP -> (comptador, timestamp primer intent)
_ADMIN_MAX_INTENTS = 5
_ADMIN_FINESTRA_SEGONS = 300  # 5 minuts


def _admin_rate_limit_ok(ip):
    """Retorna True si la IP no ha superat el límit d'intents."""
    ara = time.time()
    if ip in _admin_intents:
        comptador, primer = _admin_intents[ip]
        if ara - primer > _ADMIN_FINESTRA_SEGONS:
            _admin_intents[ip] = (1, ara)
            return True
        if comptador >= _ADMIN_MAX_INTENTS:
            return False
        _admin_intents[ip] = (comptador + 1, primer)
    else:
        _admin_intents[ip] = (1, ara)
    return True


@app.route("/api/admin/actualitzar", methods=["POST"])
def api_admin_actualitzar():
    """Actualitza l'aplicació fent git pull i reiniciant el servei."""
    try:
        ip = request.remote_addr or "unknown"

        if not _admin_rate_limit_ok(ip):
            logger.warning("Rate limit superat per %s a /api/admin/actualitzar", ip)
            return jsonify({"ok": False, "error": "Massa intents. Torna-ho a provar més tard."}), 429

        data = request.get_json() or {}
        clau = data.get("clau", "")
        clau_correcta = os.environ.get("ADMIN_KEY", "")

        if not clau_correcta:
            return jsonify({"ok": False, "error": "ADMIN_KEY no configurada"}), 500
        if not hmac.compare_digest(clau, clau_correcta):
            logger.warning("Intent d'actualització amb clau incorrecta des de %s", ip)
            return jsonify({"ok": False, "error": "Clau incorrecta"}), 403

        # Autenticació correcta: reset comptador
        _admin_intents.pop(ip, None)

        logger.info("Actualització iniciada per l'administrador des de %s", ip)
        app_dir = os.path.dirname(os.path.abspath(__file__))

        # git pull
        pull = subprocess.run(
            ["git", "pull", "origin", "main"],
            cwd=app_dir, capture_output=True, text=True, timeout=30,
        )
        if pull.returncode != 0:
            stderr = (pull.stderr or "").strip()
            stdout = (pull.stdout or "").strip()
            logger.error("git pull ha fallat: %s | stdout: %s", stderr, stdout)
            detall = stderr or stdout or "(sense detall)"
            return jsonify({
                "ok": False,
                "error": f"git pull ha fallat: {detall}",
            }), 500

        git_output = pull.stdout.strip()
        logger.info("git pull: %s", git_output)

        # pip install si requirements.txt ha canviat
        pip_ok = True
        if "requirements.txt" in git_output:
            venv_pip = os.path.join(app_dir, "venv", "bin", "pip")
            if os.path.exists(venv_pip):
                pip = subprocess.run(
                    [venv_pip, "install", "-r", "requirements.txt", "-q"],
                    cwd=app_dir, capture_output=True, text=True, timeout=60,
                )
                pip_ok = pip.returncode == 0

        # Reiniciar servei
        restart_ok = False
        try:
            restart = subprocess.run(
                ["sudo", "systemctl", "restart", "comandes-venda"],
                capture_output=True, text=True, timeout=10,
            )
            restart_ok = restart.returncode == 0
        except Exception as e:
            logger.warning("No s'ha pogut reiniciar el servei: %s", e)

        return jsonify({
            "ok": True,
            "git": git_output,
            "pip": "ok" if pip_ok else "error",
            "restart": "ok" if restart_ok else "error",
        })
    except subprocess.TimeoutExpired:
        return jsonify({"ok": False, "error": "Timeout executant l'actualització"}), 500
    except Exception as e:
        logger.error("Actualització fallada: %s", e, exc_info=True)
        return jsonify({"ok": False, "error": "Error intern durant l'actualització"}), 500


@app.route("/api/admin/versio")
def api_admin_versio():
    """Retorna la versió actual (commit hash i data)."""
    try:
        app_dir = os.path.dirname(os.path.abspath(__file__))
        result = subprocess.run(
            ["git", "log", "-1", "--format=%h %s (%ci)"],
            cwd=app_dir, capture_output=True, text=True, timeout=5,
        )
        return jsonify({"ok": True, "versio": result.stdout.strip()})
    except Exception:
        return jsonify({"ok": True, "versio": "desconeguda"})


@app.route("/admin/sql-stats")
def admin_sql_stats_page():
    """Pàgina visual de monitorització SQL."""
    return render_template("sql-stats.html")


@app.route("/api/admin/sql-stats")
def api_admin_sql_stats():
    """Monitorització SQL: queries, temps mitjà, errors i últimes 50 queries."""
    from consultes import get_sql_stats
    return jsonify({"ok": True, **get_sql_stats()})


@app.route("/api/admin/sql-stats/reset", methods=["POST"])
def api_admin_sql_stats_reset():
    """Reinicia comptadors SQL."""
    from consultes import reset_sql_stats
    reset_sql_stats()
    return jsonify({"ok": True, "message": "Estadístiques reiniciades"})


@app.route("/api/admin/sync-status")
def api_admin_sync_status():
    """Estat del worker de sync SAP.

    Llegeix `logs/sync_status.json` que el worker actualitza a cada passada.
    Retorna informació sobre l'inici del worker, comptadors acumulats,
    últimes 20 passades i configuració.

    Si el fitxer no existeix, retorna estat 'not_running' (el worker no ha
    fet cap passada encara, o no està engegat).
    """
    import json as _json
    status_path = os.environ.get(
        "SYNC_STATUS_FILE",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "sync_status.json"),
    )
    if not os.path.exists(status_path):
        return jsonify({
            "ok": True,
            "state": "not_running",
            "message": "El worker de sync no ha executat cap passada encara "
                       "(fitxer sync_status.json no existeix).",
            "status_file": status_path,
        })
    try:
        with open(status_path, "r", encoding="utf-8") as f:
            snapshot = _json.load(f)
    except (OSError, ValueError) as e:
        return jsonify({
            "ok": False,
            "state": "error_reading_status",
            "error": str(e),
            "status_file": status_path,
        }), 500

    return jsonify({"ok": True, "state": "running", **snapshot})


@app.route("/api/admin/clients")
def api_admin_clients():
    """Mostra els clients actius (IP, últim request, fa quant)."""
    now = time.time()
    with _active_clients_lock:
        clients = []
        for ip, info in _active_clients.items():
            age = now - info["last_seen"]
            if age < _ACTIVE_CLIENT_TTL:
                clients.append({
                    "ip": ip,
                    "last_path": info["last_path"],
                    "seconds_ago": round(age),
                    "active": age < 60,
                })
    return jsonify({
        "ok": True,
        "clients": sorted(clients, key=lambda c: c["seconds_ago"]),
        "total_active": sum(1 for c in clients if c["active"]),
    })


# ============================================================
# Tracking d'activitat per monitorització
# ============================================================

# Connexions actives: registra IP i últim request
_active_clients_lock = threading.Lock()
_active_clients = {}  # ip -> {"last_seen": time, "last_path": str}
_ACTIVE_CLIENT_TTL = 120  # 2 minuts sense activitat → considerat inactiu


@app.before_request
def _track_activity():
    """Registra l'últim request per monitorització."""
    ip = request.remote_addr
    with _active_clients_lock:
        _active_clients[ip] = {"last_seen": time.time(), "last_path": request.path}


def _warmup_cache():
    """Precarrega dades quasi-estàtiques al arrencar (noms magatzems).
    Les dades dinàmiques (comandes, fingerprint) es carreguen
    sota demanda quan el frontend les demana (cache + single-flight)."""
    try:
        conn = connectar()
        try:
            obtenir_noms_magatzems(conn)
            obtenir_titols_infoanex(conn)
            obtenir_titols_infoanex_clienvio(conn)
        finally:
            conn.close()
        logger.info("Cache inicial carregada (noms magatzems, titols INFOANEX)")
    except Exception as e:
        logger.warning("Cache inicial fallida: %s", e)


# Precarregar dades estàtiques al arrencar
_warmup_cache()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5002"))
    logger.info("Iniciant Motor de Preparació de Comandes (SAP) al port %d", port)
    app.run(debug=False, host="0.0.0.0", port=port)
