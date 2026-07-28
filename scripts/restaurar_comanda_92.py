"""Restaura la comanda 92 a l'estat original (5 línies, sense palets).

Basat en l'històric ADO1 (Log1-3, estat original abans dels tests).
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))
import _bootstrap  # noqa
import consultes
from sap_service_layer import SLClient

# Línies originals (exactament com estaven a Log1-3 de ADO1)
# LineNum, ItemCode, Quantity, PackQty, Price
ORIGINAL = [
    ("30150", 1000.0, 40.0, 0.70),
    ("30370", 1000.0, 40.0, 0.57),
    ("33010", 825.0,  33.0, 1.92),
    ("34082", 2000.0, 80.0, 1.31),
    ("32090", 2250.0, 90.0, 0.97),
]

sl = SLClient(
    os.environ["SAP_SL_URL"],
    os.environ["SAP_SL_COMPANY"],
    os.environ["SAP_SL_USER"],
    os.environ["SAP_SL_PASSWORD"],
    verify=False, timeout=15,
)

with sl:
    print("=== Estat abans (via SL) ===")
    resp = sl._request("GET", "Orders(92)?$select=DocEntry,DocumentLines")
    for l in resp.json().get("DocumentLines", []):
        print(f"  L{l['LineNum']} {l['ItemCode']} Qty={l['Quantity']}")

    # Construeix payload: 5 línies noves SENSE LineNum (SAP auto-numera).
    # Deixem que SL agafi WarehouseCode, TaxCode, etc. per defecte de l'article.
    new_lines = [
        {
            "ItemCode": ic,
            "Quantity": qty,
            "UnitPrice": price,
            "WarehouseCode": "01",
        }
        for ic, qty, packqty, price in ORIGINAL
    ]

    print(f"\n=== PATCH: substituir per les 5 línies originals ===")
    for l in new_lines:
        print(f"  {l}")

    try:
        sl._request("PATCH", "Orders(92)",
                    json_body={"DocumentLines": new_lines})
        print("\n✅ PATCH OK")
    except Exception as e:
        print(f"\n❌ FAIL {getattr(e,'status_code','?')}: {getattr(e,'body',str(e))}")
        sys.exit(1)

    # Verificació post-restauració
    print("\n=== Estat després ===")
    resp = sl._request("GET", "Orders(92)?$select=DocEntry,DocumentLines")
    for l in resp.json().get("DocumentLines", []):
        print(f"  L{l['LineNum']} {l['ItemCode']} Qty={l['Quantity']} "
              f"Price={l.get('Price')} PackQty={l.get('PackQty')}")
