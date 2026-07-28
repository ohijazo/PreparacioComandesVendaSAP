"""Prova estratègies alternatives per esborrar una línia palet."""
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
    # A) PATCH amb Quantity=0 sobre la línia palet (a nivell subpath)
    print("=== A. PATCH Orders(92)/DocumentLines(5) amb Quantity=0 ===")
    try:
        sl._request("PATCH", "Orders(92)/DocumentLines(5)",
                    json_body={"Quantity": 0})
        print("  ✅ OK")
    except Exception as e:
        print(f"  ❌ {getattr(e,'status_code','?')}: {getattr(e,'body',str(e))}")

    # Comprova estat
    resp = sl._request("GET", "Orders(92)?$select=DocEntry,DocumentLines")
    lines = resp.json().get("DocumentLines", [])
    print(f"  Línies actuals: {len(lines)}")
    for l in lines:
        print(f"    L{l['LineNum']} {l['ItemCode']} Qty={l['Quantity']} LineStatus={l.get('LineStatus')}")

    # Si encara hi és, provem B) PATCH document sencer amb LineStatus="bost_Close" a L5
    palets = [l for l in lines if l["ItemCode"] == "01030"]
    if palets:
        print("\n=== B. PATCH Order sencera amb LineStatus=bost_Close a L5 ===")
        # Enviem TOTES les línies preservant LineNum, marcant L5 com Close
        payload_lines = []
        for l in lines:
            entry = {"LineNum": l["LineNum"]}
            if l["ItemCode"] == "01030":
                entry["LineStatus"] = "bost_Close"
            payload_lines.append(entry)
        try:
            sl._request("PATCH", "Orders(92)",
                        json_body={"DocumentLines": payload_lines})
            print("  ✅ OK")
        except Exception as e:
            print(f"  ❌ {getattr(e,'status_code','?')}: {getattr(e,'body',str(e))}")

        resp = sl._request("GET", "Orders(92)?$select=DocEntry,DocumentLines")
        for l in resp.json().get("DocumentLines", []):
            print(f"    L{l['LineNum']} {l['ItemCode']} Qty={l['Quantity']} LineStatus={l.get('LineStatus')}")
