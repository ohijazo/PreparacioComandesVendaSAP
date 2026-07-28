"""Reprodueix el pipeline complet de /api/afegir-palets/92 amb logs detallats."""
import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))
import _bootstrap  # noqa
import consultes
from motor import calcular_embalatges
from sap_line_builder import generar_linies_palet_sap, MARCADOR_LINIA_PALET_UDF, MARCADOR_LINIA_PALET_VALOR
from sap_service_layer import SLClient

DOC_ENTRY = 92

# 1. Metadata
conn = consultes.connectar()
meta = consultes.obtenir_metadata_ordr_per_doc_entry(conn, DOC_ENTRY)
conn.close()
print(f"Metadata: {meta}\n")

# 2. Motor
resultat = calcular_embalatges(meta["series"], meta["docnum"], forcar=True)
print(f"Estat motor: {resultat.estat.value}")
print(f"Palets resum ({len(resultat.palets)}):")
for p in resultat.palets:
    print(f"  {p.art_codi} × {p.quantitat}  es_fisic={p.es_fisic}")
print()

# 3. Generar línies
linies_noves = generar_linies_palet_sap(resultat.palets, meta["whs_code"])
print(f"Línies noves generades: {len(linies_noves)}")
for l in linies_noves:
    print(f"  {l}")
print()

# 4. SL: GET + inspeccionar què identificaria com "a tancar"
sl = SLClient(
    os.environ["SAP_SL_URL"],
    os.environ["SAP_SL_COMPANY"],
    os.environ["SAP_SL_USER"],
    os.environ["SAP_SL_PASSWORD"],
    verify=False, timeout=15,
)
with sl:
    resp = sl._request("GET", f"Orders({DOC_ENTRY})?$select=DocEntry,DocumentLines")
    current = resp.json().get("DocumentLines", [])
    print(f"GET: {len(current)} línies:")
    for l in current:
        print(f"  L{l['LineNum']} {l['ItemCode']} Qty={l['Quantity']} "
              f"U_FCAfegit={l.get('U_FCAfegit')!r} LineStatus={l.get('LineStatus')!r}")
    print()

    to_close = [
        l for l in current
        if l.get(MARCADOR_LINIA_PALET_UDF) == MARCADOR_LINIA_PALET_VALOR
        and l.get("LineStatus") != "bost_Close"
    ]
    print(f"A tancar: {len(to_close)}")

    # Composició payload
    patch_lines = []
    for l in to_close:
        patch_lines.append({
            "LineNum": l["LineNum"],
            "LineStatus": "bost_Close",
            MARCADOR_LINIA_PALET_UDF: "",
        })
    for nl in linies_noves:
        patch_lines.append({k: v for k, v in nl.items() if k != "LineNum"})

    patch_body = {"DocumentLines": patch_lines}
    print(f"\nPAYLOAD PATCH:\n{json.dumps(patch_body, indent=2, ensure_ascii=False)}\n")

    # PATCH
    try:
        sl._request("PATCH", f"Orders({DOC_ENTRY})", json_body=patch_body)
        print("✅ PATCH OK")
    except Exception as e:
        print(f"❌ {getattr(e,'status_code','?')}: {getattr(e,'body',str(e))}")
