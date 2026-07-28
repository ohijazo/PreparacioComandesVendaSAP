"""Prova PATCH Comments sobre diverses Orders per veure si el -1116 és
global o específic de certes comandes.

Selecciona 5 orders variades: recent, antic, diferents clients, diferents estats.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

import _bootstrap  # noqa: F401
import consultes
from sap_service_layer import SLClient

# 1. Selecció d'orders variades
conn = consultes.connectar()
cur = conn.cursor()
cur.execute("""
    SELECT TOP 5 DocEntry, DocNum, CardCode, DocStatus, DocDate
      FROM ORDR
     WHERE DocStatus = 'O'
     ORDER BY NEWID()
""")
candidates = cur.fetchall()
conn.close()

print(f"=== Provant PATCH Comments sobre {len(candidates)} orders variades ===\n")
for r in candidates:
    print(f"  DocEntry={r.DocEntry:>6}  DocNum={r.DocNum}  CardCode={r.CardCode:<10}  DocDate={r.DocDate}")

# 2. Login SL + PATCH per cada una
url = os.environ["SAP_SL_URL"]
company = os.environ["SAP_SL_COMPANY"]
user = os.environ["SAP_SL_USER"]
pwd = os.environ["SAP_SL_PASSWORD"]
verify = os.environ.get("SAP_SL_VERIFY_SSL", "true").lower() not in ("false", "0", "no")

sl = SLClient(url, company, user, pwd, verify=verify, timeout=15)
sl.login()
print("\nLogin OK. Provant PATCH Comments…\n")

results = []
for r in candidates:
    try:
        resp = sl._request("PATCH", f"Orders({r.DocEntry})",
                           json_body={"Comments": f"test motor {r.DocEntry}"})
        print(f"  ✅ DocEntry={r.DocEntry:>6}  {resp.status_code}")
        results.append((r.DocEntry, "OK"))
    except Exception as e:
        body = getattr(e, "body", None)
        code = getattr(e, "status_code", None)
        # Extreure només el codi d'error SAP si és disponible
        sap_code = ""
        try:
            sap_code = body.get("error", {}).get("code", "")
        except Exception:
            pass
        print(f"  ❌ DocEntry={r.DocEntry:>6}  {code}  SAP={sap_code}")
        results.append((r.DocEntry, f"FAIL {sap_code}"))

sl.logout()

print("\n=== RESUM ===")
ok_count = sum(1 for _, s in results if s == "OK")
print(f"  OK   : {ok_count}/{len(results)}")
print(f"  FAIL : {len(results)-ok_count}/{len(results)}")
for de, s in results:
    print(f"    DocEntry={de:>6}  {s}")

if ok_count == 0:
    print("\n→ Problema GLOBAL: cap Order es pot fer PATCH via SL.")
elif ok_count == len(results):
    print("\n→ Totes OK! La 126 tenia alguna cosa específica.")
else:
    print("\n→ Problema MIXT: algunes orders es poden i altres no.")
