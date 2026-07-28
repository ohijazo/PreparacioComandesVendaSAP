"""Verifica si SAP SL veu DocEntry 92 (GET aïllat)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))
import _bootstrap  # noqa
import consultes  # carrega .env

# 1. Verifica a la BD directament
conn = consultes.connectar()
row = conn.execute("""
    SELECT DocEntry, DocNum, Series, DocStatus, RTRIM(CardCode) AS CardCode
      FROM ORDR WHERE DocEntry = 92
""").fetchone()
print(f"BD  : {row}")
conn.close()

# 2. Prova GET via SL amb els mateixos $select que fa replace_marked_lines
from sap_service_layer import SLClient

sl = SLClient(
    os.environ["SAP_SL_URL"],
    os.environ["SAP_SL_COMPANY"],
    os.environ["SAP_SL_USER"],
    os.environ["SAP_SL_PASSWORD"],
    verify=False, timeout=15,
)
with sl:
    for path in [
        "Orders(92)?$select=DocEntry,DocNum,DocStatus,CardCode",
        "Orders(92)?$select=DocEntry,DocumentLines",
    ]:
        print(f"\n--- GET {path}")
        try:
            resp = sl._request("GET", path)
            b = resp.json()
            if "DocumentLines" in b:
                print(f"  OK, {len(b['DocumentLines'])} línies")
                for l in b["DocumentLines"][:2]:
                    print(f"    LineNum={l.get('LineNum')} ItemCode={l.get('ItemCode')} "
                          f"Quantity={l.get('Quantity')} U_FCAfegit={l.get('U_FCAfegit')!r}")
            else:
                print(f"  OK: {b}")
        except Exception as e:
            print(f"  FAIL: {getattr(e, 'status_code', '?')} — {getattr(e, 'body', str(e))}")
