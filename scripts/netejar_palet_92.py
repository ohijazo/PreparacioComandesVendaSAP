"""Esborra el palet 01030 residual (L5) de la comanda 92 via DELETE explícit."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))
import _bootstrap  # noqa
import consultes
from sap_service_layer import SLClient

sl = SLClient(
    os.environ["SAP_SL_URL"],
    os.environ["SAP_SL_COMPANY"],
    os.environ["SAP_SL_USER"],
    os.environ["SAP_SL_PASSWORD"],
    verify=False, timeout=15,
)

with sl:
    # Cerca línies palet 01030 a la comanda 92
    resp = sl._request("GET", "Orders(92)?$select=DocEntry,DocumentLines")
    lines = resp.json().get("DocumentLines", [])
    palets = [l for l in lines if l["ItemCode"] == "01030"]
    print(f"Palets 01030 trobats: {len(palets)}")
    for p in palets:
        print(f"  L{p['LineNum']} Qty={p['Quantity']}")

    # DELETE explícit línia per línia
    for p in palets:
        line_num = p["LineNum"]
        print(f"\nDELETE Orders(92)/DocumentLines({line_num})...")
        try:
            sl._request("DELETE", f"Orders(92)/DocumentLines({line_num})")
            print("  ✅ OK")
        except Exception as e:
            print(f"  ❌ {getattr(e,'status_code','?')}: {getattr(e,'body',str(e))}")

    # Verificació
    print("\n=== Estat final ===")
    resp = sl._request("GET", "Orders(92)?$select=DocEntry,DocumentLines")
    for l in resp.json().get("DocumentLines", []):
        print(f"  L{l['LineNum']} {l['ItemCode']} Qty={l['Quantity']}")
