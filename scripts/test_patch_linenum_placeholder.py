"""Prova si PATCH amb {LineNum: X} (només placeholder) + noves funciona."""
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
    # Obtenir línies OBERTES actuals (excloure bost_Close)
    lines = sl._request("GET", "Orders(92)?$select=DocEntry,DocumentLines").json()["DocumentLines"]
    opens = [l for l in lines if l.get("LineStatus") == "bost_Open"]
    print(f"Obertes: {len(opens)} de {len(lines)}")
    for l in opens:
        print(f"  L{l['LineNum']} {l['ItemCode']} Qty={l['Quantity']}")

    # Payload: {LineNum: X} només + 1 nova palet 01010 sense LineNum
    payload = {
        "DocumentLines":
            [{"LineNum": l["LineNum"]} for l in opens]
            +
            [{"ItemCode": "01010", "Quantity": 1, "UnitPrice": 0,
              "WarehouseCode": "01", "U_FCAfegit": "S"}]
    }
    print(f"\nPAYLOAD (compact):")
    for e in payload["DocumentLines"]:
        print(f"  {e}")

    try:
        sl._request("PATCH", "Orders(92)", json_body=payload)
        print("\nOK")
    except Exception as e:
        print(f"\nFAIL {getattr(e,'status_code','?')}: {getattr(e,'body',str(e))}")

    print("\n=== Estat final ===")
    for l in sl._request("GET", "Orders(92)?$select=DocEntry,DocumentLines").json()["DocumentLines"]:
        print(f"  L{l['LineNum']} {l['ItemCode']} Qty={l['Quantity']} LS={l.get('LineStatus')}")
