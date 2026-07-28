"""Enumera els Service Layer Scripts registrats al SL de SAP B1.
Intenta diverses formes per si l'API canvia entre versions."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

import _bootstrap  # noqa: F401
import consultes  # carrega .env
from sap_service_layer import SLClient

url = os.environ["SAP_SL_URL"]
company = os.environ["SAP_SL_COMPANY"]
user = os.environ["SAP_SL_USER"]
pwd = os.environ["SAP_SL_PASSWORD"]
verify = os.environ.get("SAP_SL_VERIFY_SSL", "true").lower() not in ("false", "0", "no")

sl = SLClient(url, company, user, pwd, verify=verify, timeout=15)
sl.login()
print(f"Login OK a {url}\n")

# Provem diferents endpoints per llistar scripts SL
endpoints = [
    ("GET", "script"),
    ("GET", "Script"),
    ("GET", "script?$select=Path,Type,Description"),
    ("GET", "ScriptList"),
    ("GET", "$metadata"),
]

for method, path in endpoints:
    print(f"--- {method} {path}")
    try:
        resp = sl._request(method, path)
        # per $metadata retorna XML, molt gran
        if path == "$metadata":
            text = resp.text
            print(f"    OK ({resp.status_code}) - metadata {len(text)} chars")
            # cerca 'Script' o 'seidor' al metadata
            lower = text.lower()
            for kw in ("script", "seidor", "handler", "b1if"):
                cnt = lower.count(kw)
                print(f"    kw '{kw}': {cnt} aparicions")
            continue
        try:
            body = resp.json()
        except Exception:
            body = resp.text[:500]
        print(f"    OK ({resp.status_code}): {body}")
    except Exception as e:
        code = getattr(e, "status_code", None)
        body = getattr(e, "body", None)
        print(f"    FAIL {code}: {body}")

sl.logout()
