"""Analitza SEI_VALIDACIONES_SII_PERSONAL: object_types que gestiona i
si té alguna cosa específica per Sales Order (17)."""
from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

import _bootstrap  # noqa: F401
import consultes

conn = consultes.connectar()
cur = conn.cursor()

for spname in ("SEI_VALIDACIONES_SII_PERSONAL", "SEI_VALIDACIONES_SII"):
    print(f"\n{'='*70}")
    print(f"=== {spname} ===")
    print('='*70)
    cur.execute(f"""
        SELECT definition
          FROM sys.sql_modules m
          JOIN sys.objects o ON m.object_id = o.object_id
         WHERE o.name = '{spname}'
    """)
    r = cur.fetchone()
    if not r:
        print("  (no existeix)")
        continue

    d = r.definition
    print(f"  len = {len(d)} chars")

    # object_types
    matches = re.findall(r"@object_type\s*=\s*'(\d+)'", d)
    print(f"  object_types trobats: {sorted(set(matches))}")

    if "17" in set(matches):
        print("  ⚠ GESTIONA OBJECT TYPE 17 (Order)")
        # Extreure blocs on toca '17'
        for m in re.finditer(r"@object_type\s*=\s*'17'", d):
            start = max(0, m.start() - 300)
            end = min(len(d), m.start() + 800)
            print("\n  --- Bloc:")
            print("  " + d[start:end].replace("\n", "\n  "))

    # EXEC actius
    lines = d.splitlines()
    execs = []
    for i, l in enumerate(lines, 1):
        s = l.strip()
        if s.startswith("--"):
            continue
        if re.search(r"\bEXEC\s+", s, re.IGNORECASE):
            execs.append((i, l.strip()[:200]))
    print(f"\n  EXECs actius: {len(execs)}")
    for i, l in execs[:15]:
        print(f"    L{i}: {l}")

conn.close()
