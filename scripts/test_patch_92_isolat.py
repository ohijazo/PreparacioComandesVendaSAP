"""Reprodueix el que fa replace_marked_lines sobre Orders(92) — pas a pas."""
import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))
import _bootstrap  # noqa
import consultes  # carrega .env
from sap_service_layer import SLClient

sl = SLClient(
    os.environ["SAP_SL_URL"],
    os.environ["SAP_SL_COMPANY"],
    os.environ["SAP_SL_USER"],
    os.environ["SAP_SL_PASSWORD"],
    verify=False, timeout=15,
)

with sl:
    # 1. GET (exactament com fa replace_marked_lines)
    print("=== 1. GET línies ===")
    resp = sl._request("GET", "Orders(92)?$select=DocEntry,DocumentLines")
    body = resp.json()
    current = body.get("DocumentLines", [])
    print(f"  {len(current)} línies. Camps de la primera:")
    for k in list(current[0].keys())[:20]:
        print(f"    {k}: {current[0][k]!r}")
    print(f"    ... i {len(current[0]) - 20} camps més")

    # 2. PATCH només amb DocumentLines TAL QUAL sortint del GET (test 1)
    print("\n=== 2. PATCH intacte (com fa el codi actual) ===")
    try:
        sl._request("PATCH", "Orders(92)",
                    json_body={"DocumentLines": current})
        print("  ✅ OK — problema no era el payload complet")
    except Exception as e:
        print(f"  ❌ {getattr(e, 'status_code', '?')}: {getattr(e, 'body', str(e))}")

    # 3. PATCH només amb minimum fields (LineNum + ItemCode + Quantity)
    print("\n=== 3. PATCH minimal (només LineNum, ItemCode, Quantity) ===")
    minimal = [
        {"LineNum": l["LineNum"], "ItemCode": l["ItemCode"], "Quantity": l["Quantity"]}
        for l in current
    ]
    try:
        sl._request("PATCH", "Orders(92)",
                    json_body={"DocumentLines": minimal})
        print("  ✅ OK — el problema eren camps sobrers al payload")
    except Exception as e:
        print(f"  ❌ {getattr(e, 'status_code', '?')}: {getattr(e, 'body', str(e))}")
