import _bootstrap  # noqa: F401 — insereix KAIS_APP_PATH a sys.path
from collections import defaultdict
from copy import deepcopy
from datetime import date, datetime
from consultes import (
    connectar, obtenir_comanda, obtenir_linies, obtenir_linies_batch,
    obtenir_direccio, invalidar_caches_comanda,
    obtenir_palet_comanda, obtenir_palet_client,
    obtenir_descrip_article,
)
from regles import aplicar_regles, ART_BASE_PALET, TUNITATS_COMPUTABLES  # compartit via _bootstrap
from models import Estat, PaletResum  # compartit via _bootstrap


def calcular_embalatges(sal_codigo: str, cpa_albara: str, forcar: bool = False,
                        conn_compartida=None, tra_codi_carrega: str | None = None,
                        eje_ejercicio: str | None = None,
                        data_carrega: str | date | datetime | None = None):
    """Calcula embalatges per una comanda.

    conn_compartida: si es passa, reutilitza la connexió (per batch).
    tra_codi_carrega: codi de transportista de la càrrega d'origen.
    eje_ejercicio: any de l'exercici de la comanda. Imprescindible quan el
        número d'albarà es repeteix entre anys.
    data_carrega: datetime de referència de la càrrega (car_fecllegada o
        car_fecsalida). Criteri principal per discriminar entre dos pending
        amb mateix tra_codi (cassos URBAN, RYMOT, BOIX COMAS).
    """
    if forcar:
        invalidar_caches_comanda(sal_codigo, cpa_albara)

    # Fase 1: totes les consultes SQL — connexió oberta el mínim temps
    conn = conn_compartida or connectar()
    try:
        comanda = obtenir_comanda(conn, sal_codigo, cpa_albara,
                                  eje_ejercicio=eje_ejercicio,
                                  tra_codi_carrega=tra_codi_carrega,
                                  data_carrega=data_carrega)
        sal = comanda.pedi_serie
        alb = comanda.pedi_numero
        eje = str(comanda.pedi_ejercicio) if comanda.pedi_ejercicio else None
        linies = obtenir_linies(conn, sal, alb, eje)  # type: ignore[arg-type]
        direccio = obtenir_direccio(conn, comanda.cli_codi, comanda.pedi_dire)
    finally:
        if not conn_compartida:
            conn.close()

    # Fase 2: lògica Python sense connexió oberta
    tipus_desc_origen = None
    if not direccio.tipus_descarrega:
        palet_client = obtenir_palet_client(direccio.cli_codi, direccio.adr_codi)
        if palet_client:
            direccio.tipus_descarrega = "PALET"
            tipus_desc_origen = f"PALET (detectat de PREUSCLIENTS: {palet_client['art_codi']})"
        else:
            direccio.tipus_descarrega = "MANUAL"
            tipus_desc_origen = "MANUAL (cap palet trobat a PREUSCLIENTS)"

    resultat = aplicar_regles(linies, direccio, forcar=forcar)
    resultat.linies = linies
    resultat.comanda = comanda
    resultat.direccio = direccio

    if tipus_desc_origen:
        resultat.trazabilitat.insert(0,
            f"Tipus descàrrega no definit a la direcció → assignat: {tipus_desc_origen}"
        )

    # Fase 3: consultes de palets — reutilitzar connexió compartida si disponible
    if resultat.embalatges:
        conn = conn_compartida or connectar()
        try:
            resultat.palets = _calcular_palets(
                conn, sal, alb, resultat, direccio, eje
            )
        finally:
            if not conn_compartida:
                conn.close()

    return resultat


def _calcular_palets(conn, sal_codigo, cpa_albara, resultat, direccio, eje=None):
    """Calcula quants palets i de quin tipus necessita la comanda.

    Cada embalatge pot tenir el seu propi tipus_palet assignat per les regles.
    Embalatges sense tipus_palet explícit busquen: comanda -> PREUSCLIENTS -> estoc.
    """
    palets = []

    # 1. Despaletitzat: tot BasePalet (logic, no fisic)
    if direccio.es_despaletitzat:
        total = len(resultat.embalatges)
        descrip = obtenir_descrip_article(conn, ART_BASE_PALET)
        palets.append(PaletResum(
            art_codi=ART_BASE_PALET,
            art_descrip=descrip,
            quantitat=total,
            es_fisic=False,
        ))
        resultat.trazabilitat.append(
            f"PALETS: Despaletitzat -> {total} BasePalet "
            f"({ART_BASE_PALET} - {descrip}) [lògic, no s'entrega al client]"
        )
        return palets

    # 2. Agrupar embalatges per tipus_palet
    # - tipus_palet != None -> assignat explícitament per regla (RF6/RF7/RF8)
    # - tipus_palet == None -> necessita resolució (condicions direcció)
    emb_amb_tipus = defaultdict(int)  # art_codi -> count
    emb_sense_tipus = 0

    for e in resultat.embalatges:
        if e.tipus_palet:
            emb_amb_tipus[e.tipus_palet] += 1
        else:
            emb_sense_tipus += 1

    # 3. Embalatges amb tipus explícit (RF6/RF7/RF8)
    for tp_codi, count in emb_amb_tipus.items():
        descrip = obtenir_descrip_article(conn, tp_codi)
        es_fisic = tp_codi != ART_BASE_PALET
        palets.append(PaletResum(
            art_codi=tp_codi,
            art_descrip=descrip,
            quantitat=count,
            es_fisic=es_fisic,
        ))
        resultat.trazabilitat.append(
            f"PALETS: {count} x {tp_codi} ({descrip}) "
            f"[{'físic' if es_fisic else 'lògic'}, assignat per regles]"
        )

    # 4. Embalatges sense tipus explícit -> buscar per ordre de prioritat
    if emb_sense_tipus > 0:
        tipus_resolt, origen, es_fisic = _resolver_tipus_palet(
            conn, sal_codigo, cpa_albara, resultat, direccio, eje
        )

        # Assignar el tipus resolt als embalatges que no en tenien
        for e in resultat.embalatges:
            if not e.tipus_palet:
                e.tipus_palet = tipus_resolt["art_codi"]

        _afegir_palet_resum(
            palets, resultat, tipus_resolt, emb_sense_tipus, es_fisic, origen
        )

    return palets


def calcular_embalatges_agrupats(pedi_keys: list[tuple], forcar: bool = False):
    """Calcula embalatges agrupant múltiples comandes com si fossin una sola.

    pedi_keys: llista de tuples (sal_codigo, cpa_albara).
    Totes les comandes han de ser del mateix client i direcció.
    Les línies amb el mateix article se sumen.
    """
    if not pedi_keys:
        raise ValueError("Cal almenys una comanda")
    if len(pedi_keys) == 1:
        return calcular_embalatges(pedi_keys[0][0], pedi_keys[0][1], forcar=forcar)

    # Fase 1: totes les consultes SQL — connexió oberta el mínim temps
    conn = connectar()
    try:
        comandes = []
        for sal, alb in pedi_keys:
            comandes.append(obtenir_comanda(conn, sal, alb))

        cli_codi = comandes[0].cli_codi
        pedi_dire = comandes[0].pedi_dire
        for c in comandes[1:]:
            if c.cli_codi != cli_codi or c.pedi_dire != pedi_dire:
                raise ValueError(
                    f"Totes les comandes han de ser del mateix client i direcció. "
                    f"Comanda {c.pedi_serie}/{c.pedi_numero}: client={c.cli_codi}, dir={c.pedi_dire} "
                    f"vs primera: client={cli_codi}, dir={pedi_dire}"
                )

        # Batch: una sola query SQL per totes les comandes
        pedi_keys_sql = [
            (c.pedi_serie, c.pedi_numero, str(c.pedi_ejercicio) if c.pedi_ejercicio else None)
            for c in comandes
        ]
        totes_linies = obtenir_linies_batch(conn, pedi_keys_sql)

        direccio = obtenir_direccio(conn, cli_codi, pedi_dire)
    finally:
        conn.close()

    # Fase 2: lògica Python sense connexió oberta
    agrupat = {}
    for l in totes_linies:
        if l.art_codi in agrupat:
            existing = agrupat[l.art_codi]
            existing.linea_unidades += l.linea_unidades
            existing.linea_cantidad += l.linea_cantidad
        else:
            agrupat[l.art_codi] = deepcopy(l)

    linies_fusionades = []
    for i, l in enumerate(agrupat.values(), 1):
        l.linea_num = i
        linies_fusionades.append(l)

    tipus_desc_origen = None
    if not direccio.tipus_descarrega:
        palet_client = obtenir_palet_client(direccio.cli_codi, direccio.adr_codi)
        if palet_client:
            direccio.tipus_descarrega = "PALET"
            tipus_desc_origen = f"PALET (detectat de PREUSCLIENTS: {palet_client['art_codi']})"
        else:
            direccio.tipus_descarrega = "MANUAL"
            tipus_desc_origen = "MANUAL (cap palet trobat a PREUSCLIENTS)"

    resultat = aplicar_regles(linies_fusionades, direccio, forcar=forcar)
    resultat.linies = linies_fusionades
    resultat.comanda = comandes[0]
    resultat.direccio = direccio

    series_str = ", ".join(
        f"{c.pedi_serie}/{c.pedi_numero}" for c in comandes
    )
    resultat.trazabilitat.insert(0,
        f"AGRUPACIÓ: {len(pedi_keys)} comandes agrupades [{series_str}] "
        f"del client {cli_codi}, direcció {pedi_dire}. "
        f"Articles iguals fusionats (unitats sumades)."
    )

    if tipus_desc_origen:
        resultat.trazabilitat.insert(1,
            f"Tipus descàrrega no definit a la direcció → assignat: {tipus_desc_origen}"
        )

    # Fase 3: consultes de palets — connexió curta separada
    if resultat.embalatges:
        conn = connectar()
        try:
            c0 = comandes[0]
            eje0 = str(c0.pedi_ejercicio) if c0.pedi_ejercicio else None
            resultat.palets = _calcular_palets(
                conn, c0.pedi_serie, c0.pedi_numero, resultat, direccio, eje0
            )
        finally:
            conn.close()

    return resultat


def _resolver_tipus_palet(conn, sal_codigo, cpa_albara, resultat, direccio, eje=None):
    """Resol el tipus de palet per embalatges sense tipus explícit (tipus_palet=None).

    Aquests embalatges són els que les regles RF6/RF7/RF8/RF9 han marcat amb
    tipus_palet=None, que significa "usa el palet de les condicions del client".
    Per tant, la prioritat és: condicions client > palet a la comanda > fallback.
    """

    # 1. Palet del client via PREUSCLIENTS.xlsx (condicions de venda)
    palet_client = obtenir_palet_client(direccio.cli_codi, direccio.adr_codi)
    if palet_client:
        return palet_client, "condicions direcció", True

    # 2. Palet existent a la comanda (si no hi ha condicions de client)
    palet_comanda = obtenir_palet_comanda(conn, sal_codigo, cpa_albara, eje)
    if palet_comanda:
        return palet_comanda, "detectat de la comanda", True

    # 3. Fallback: BasePalet
    return {
        "art_codi": ART_BASE_PALET,
        "art_descrip": obtenir_descrip_article(conn, ART_BASE_PALET),
    }, "fallback BasePalet (sense condicions direcció)", False


def _afegir_palet_resum(palets, resultat, tipus_resolt, count, es_fisic, origen):
    """Afegeix o fusiona un resum de palets a la llista."""
    existent = next((p for p in palets if p.art_codi == tipus_resolt["art_codi"]), None)
    fisic_str = "físic" if es_fisic else "lògic"
    if existent:
        existent.quantitat += count
        resultat.trazabilitat.append(
            f"PALETS: +{count} x {tipus_resolt['art_codi']} "
            f"({tipus_resolt['art_descrip']}) [{fisic_str}, {origen}] "
            f"(fusionat, total {existent.quantitat})"
        )
    else:
        palets.append(PaletResum(
            art_codi=tipus_resolt["art_codi"],
            art_descrip=tipus_resolt["art_descrip"],
            quantitat=count,
            es_fisic=es_fisic,
        ))
        resultat.trazabilitat.append(
            f"PALETS: {count} x {tipus_resolt['art_codi']} "
            f"({tipus_resolt['art_descrip']}) [{fisic_str}, {origen}]"
        )


def validar_dades_mestres(sal_codigo: str, cpa_albara: str,
                          linies=None, direccio=None) -> list[dict]:
    """Valida la qualitat de les dades mestres d'una comanda.

    Retorna llista de avisos amb {tipus: 'error'|'warning', camp, missatge}.
    Si linies/direccio es passen, evita queries SQL duplicades.
    """
    if linies is None or direccio is None:
        conn = connectar()
        try:
            comanda = obtenir_comanda(conn, sal_codigo, cpa_albara)
            sal = comanda.pedi_serie
            alb = comanda.pedi_numero
            eje = str(comanda.pedi_ejercicio) if comanda.pedi_ejercicio else None
            if linies is None:
                linies = obtenir_linies(conn, sal, alb, eje)  # type: ignore[arg-type]
            if direccio is None:
                direccio = obtenir_direccio(conn, comanda.cli_codi, comanda.pedi_dire)
        finally:
            conn.close()

    avisos = []

    # --- Direcció ---
    if not direccio.tipus_descarrega:
        avisos.append({
            "tipus": "warning",
            "camp": "Direcció → Tipus descàrrega",
            "missatge": f"No definit a la direcció {direccio.cli_codi}/{direccio.adr_codi}. "
                        f"S'autodetecta via PREUSCLIENTS.",
        })

    if direccio.preval_direccio:
        if direccio.max_sacs_palet is None:
            avisos.append({
                "tipus": "error",
                "camp": "Direcció → Màxim sacs palet",
                "missatge": f"PrevalDireccio=Sí però Màxim_sacs_x_palet no definit. "
                            f"S'usa el valor per defecte (45).",
            })
        if direccio.sacs_x_base is None:
            avisos.append({
                "tipus": "error",
                "camp": "Direcció → Sacs x base",
                "missatge": f"PrevalDireccio=Sí però Sacs_x_base no definit. "
                            f"S'usa el valor per defecte (5).",
            })
        palet_client = obtenir_palet_client(direccio.cli_codi, direccio.adr_codi)
        if not palet_client:
            avisos.append({
                "tipus": "error",
                "camp": "Direcció → Tipus palet",
                "missatge": f"PrevalDireccio=Sí però no hi ha tipus de palet definit "
                            f"a les condicions (PREUSCLIENTS) per {direccio.cli_codi}/{direccio.adr_codi}.",
            })

    # --- Articles ---
    for l in linies:
        if l.tunitat not in TUNITATS_COMPUTABLES:
            continue

        if l.cantidadapilable is None or l.cantidadapilable == 0:
            avisos.append({
                "tipus": "warning",
                "camp": f"Article {l.art_codi} → Cantidad apilable",
                "missatge": f"{l.art_descrip}: Cantidad_apilable no definida. S'usa base per defecte (5).",
            })

        if l.uxc is None or l.uxc == 0:
            avisos.append({
                "tipus": "warning",
                "camp": f"Article {l.art_codi} → UxC",
                "missatge": f"{l.art_descrip}: Unitats_x_caixa (UxC) no definida. S'usa màxim per defecte (45).",
            })

        if l.aprovisionament_estoc and not l.palet_producte_estoc:
            avisos.append({
                "tipus": "error",
                "camp": f"Article {l.art_codi} → Palet producte estoc",
                "missatge": f"{l.art_descrip}: Article d'aprovisionament d'estoc sense "
                            f"palet producte estoc definit.",
            })

    return avisos
