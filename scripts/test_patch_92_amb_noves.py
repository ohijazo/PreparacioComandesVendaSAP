"""Reprodueix PATCH sobre 92 afegint noves línies palet — bisecta el bug."""
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
    # GET
    resp = sl._request("GET", "Orders(92)?$select=DocEntry,DocumentLines")
    current = resp.json().get("DocumentLines", [])
    print(f"GET OK: {len(current)} línies existents")

    # Noves línies palet — el que genera sap_line_builder
    noves = [
        {
            "ItemCode": "01030",
            "Quantity": 6,
            "UnitPrice": 0,
            "PriceAfterVAT": 0,
            "DiscountPercent": 0,
            "FreeText": "Afegit per motor embalatges",
            "WarehouseCode": "01",
            "U_FCAfegit": "S",
        }
    ]

    # TEST A: existents intactes + noves al final
    print("\n=== A. PATCH: existents intactes + 1 nova palet ===")
    try:
        sl._request("PATCH", "Orders(92)",
                    json_body={"DocumentLines": current + noves})
        print("  ✅ OK")
    except Exception as e:
        print(f"  ❌ {getattr(e, 'status_code', '?')}: {getattr(e, 'body', str(e))}")

    # TEST B: existents minimals + noves
    print("\n=== B. PATCH: existents MINIMALS + 1 nova palet ===")
    minimal = [
        {"LineNum": l["LineNum"], "ItemCode": l["ItemCode"], "Quantity": l["Quantity"]}
        for l in current
    ]
    try:
        sl._request("PATCH", "Orders(92)",
                    json_body={"DocumentLines": minimal + noves})
        print("  ✅ OK")
    except Exception as e:
        print(f"  ❌ {getattr(e, 'status_code', '?')}: {getattr(e, 'body', str(e))}")

    # TEST C: només la nova, sense les existents (no ha de funcionar — SAP esborrarà les altres)
    print("\n=== C. PATCH: NOMÉS la nova palet (perd les existents!) ===")
    try:
        sl._request("PATCH", "Orders(92)",
                    json_body={"DocumentLines": noves})
        print("  ✅ OK (però la comanda ha perdut les línies originals!)")
    except Exception as e:
        print(f"  ❌ {getattr(e, 'status_code', '?')}: {getattr(e, 'body', str(e))}")
