"""Prova PATCH amb diferents combinacions de camps per aïllar quin causa -1116.

Cada test és independent. Al final imprimeix un resum.

Ús:
    python scripts/test_patch_isolat.py 28    # DocEntry a provar
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

import _bootstrap  # noqa: F401
import consultes  # noqa: F401 — carrega .env al import
from sap_service_layer import SLClient

DOC_ENTRY = int(sys.argv[1]) if len(sys.argv) > 1 else 28

url = os.environ["SAP_SL_URL"]
company = os.environ["SAP_SL_COMPANY"]
user = os.environ["SAP_SL_USER"]
pwd = os.environ["SAP_SL_PASSWORD"]
verify = os.environ.get("SAP_SL_VERIFY_SSL", "true").lower() not in ("false", "0", "no")

sl = SLClient(url, company, user, pwd, verify=verify, timeout=15)
sl.login()
print(f"Login OK. Provant PATCH sobre Orders({DOC_ENTRY})...\n")

tests = [
    ("A. PATCH Orders(N) — Comments",                                    "PATCH", f"Orders({DOC_ENTRY})",         {"Comments": "test motor embalatges"}),
    ("B. PATCH Orders(N) — Només U_FCCalcular=N",                        "PATCH", f"Orders({DOC_ENTRY})",         {"U_FCCalcular": "N"}),
    ("C. PATCH Orders(N) — Només U_FCEmbalatgeResum",                    "PATCH", f"Orders({DOC_ENTRY})",         {"U_FCEmbalatgeResum": "test"}),
    ("D. PATCH Orders(N) — Només U_FCEmbalatgeEstat",                    "PATCH", f"Orders({DOC_ENTRY})",         {"U_FCEmbalatgeEstat": "CALCULAT"}),
    ("E. PATCH Orders(N) — 3 UDFs junts (worker)",                       "PATCH", f"Orders({DOC_ENTRY})",         {"U_FCCalcular": "N", "U_FCEmbalatgeResum": "test", "U_FCEmbalatgeEstat": "CALCULAT"}),
    ("F. POST Orders(N)/Update — 3 UDFs junts (mètode alternatiu)",      "POST",  f"Orders({DOC_ENTRY})/Update",  {"U_FCCalcular": "N", "U_FCEmbalatgeResum": "test", "U_FCEmbalatgeEstat": "CALCULAT"}),
    ("G. GET Orders(N)?$select=DocEntry,DocNum (lectura control)",       "GET",   f"Orders({DOC_ENTRY})?$select=DocEntry,DocNum", None),
    ("H. PATCH BusinessPartners('C001024') — Notes (test global escriptura)", "PATCH", "BusinessPartners('C001024')", {"Notes": "test motor embalatges"}),
]

resultats = []
for descr, method, path, payload in tests:
    print(f"--- {descr}")
    if payload is not None:
        print(f"    payload: {payload}")
    try:
        resp = sl._request(method, path, json_body=payload)
        # Per GET/PATCH mostrar breu
        try:
            body = resp.json()
        except Exception:
            body = resp.text[:120]
        print(f"    ✅ {resp.status_code}  body: {body}\n")
        resultats.append((descr, f"OK {resp.status_code}"))
    except Exception as e:
        body = getattr(e, "body", None)
        code = getattr(e, "status_code", None)
        print(f"    ❌ {code}: {body}\n")
        resultats.append((descr, f"FAIL {code}"))

sl.logout()

print("\n=== RESUM ===")
for descr, r in resultats:
    print(f"  {r:<10} {descr}")
