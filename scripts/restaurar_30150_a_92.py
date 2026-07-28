"""Restaura la línia 30150 perduda a la comanda 92, usant el patró placeholder."""
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
    lines = sl._request("GET", "Orders(92)?$select=DocEntry,DocumentLines").json()["DocumentLines"]
    print(f"Total línies: {len(lines)} — passo TOTES com placeholders")

    # PATCH: placeholders per TOTES (open + close) + nova 30150
    payload = {
        "DocumentLines":
            [{"LineNum": l["LineNum"]} for l in lines]
            + [{
                "ItemCode": "30150",
                "Quantity": 1000.0,
                "UnitPrice": 0.70,
                "WarehouseCode": "01",
            }]
    }
    sl._request("PATCH", "Orders(92)", json_body=payload)
    print("✅ 30150 restaurada")

    print("\n=== Estat final ===")
    for l in sl._request("GET", "Orders(92)?$select=DocEntry,DocumentLines").json()["DocumentLines"]:
        print(f"  L{l['LineNum']} {l['ItemCode']} Qty={l['Quantity']} LS={l.get('LineStatus')}")
