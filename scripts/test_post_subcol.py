"""Prova d'afegir línia via POST /Orders(N)/DocumentLines (add subcollection)."""
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
    # Estat inicial
    print("=== Estat inicial ===")
    lines = sl._request("GET", "Orders(92)?$select=DocEntry,DocumentLines").json()["DocumentLines"]
    for l in lines:
        print(f"  L{l['LineNum']} {l['ItemCode']} Qty={l['Quantity']} LS={l.get('LineStatus')}")

    # Prova POST subcollection
    payload = {
        "ItemCode": "01010",
        "Quantity": 1,
        "UnitPrice": 0,
        "WarehouseCode": "01",
        "U_FCAfegit": "S",
    }
    print(f"\n=== POST /Orders(92)/DocumentLines amb {payload} ===")
    try:
        r = sl._request("POST", "Orders(92)/DocumentLines", json_body=payload)
        print(f"  ✅ HTTP {r.status_code}")
    except Exception as e:
        print(f"  FAIL {getattr(e,'status_code','?')}: {getattr(e,'body',str(e))}")

    # Estat final
    print("\n=== Estat final ===")
    lines = sl._request("GET", "Orders(92)?$select=DocEntry,DocumentLines").json()["DocumentLines"]
    for l in lines:
        print(f"  L{l['LineNum']} {l['ItemCode']} Qty={l['Quantity']} LS={l.get('LineStatus')}")
