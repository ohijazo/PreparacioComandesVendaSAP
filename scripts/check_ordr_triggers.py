"""Llista triggers SQL sobre la taula ORDR (i altres candidats)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

import _bootstrap  # noqa: F401
import consultes

conn = consultes.connectar()
cur = conn.cursor()

for tabla in ("ORDR", "RDR1", "OCRD"):
    cur.execute("""
        SELECT t.name AS trigger_name,
               t.is_disabled,
               t.is_instead_of_trigger,
               LEN(m.definition) AS def_len
          FROM sys.triggers t
          JOIN sys.objects  o ON t.parent_id = o.object_id
          LEFT JOIN sys.sql_modules m ON t.object_id = m.object_id
         WHERE o.name = ?
    """, tabla)
    rows = cur.fetchall()
    print(f"\n=== Triggers sobre {tabla}: {len(rows)} ===")
    for r in rows:
        flag = "[DISABLED]" if r.is_disabled else "[ACTIVE]"
        kind = "INSTEAD OF" if r.is_instead_of_trigger else "AFTER"
        print(f"  {flag} {kind}  {r.trigger_name}  (def {r.def_len} chars)")

# Bonus: procediments SEIDOR relacionats amb Orders
print("\n=== SPs/Funcions amb 'ORDR' o 'ORDER' al codi ===")
cur.execute("""
    SELECT o.name, o.type_desc, LEN(m.definition) AS def_len
      FROM sys.sql_modules m
      JOIN sys.objects o ON m.object_id = o.object_id
     WHERE (m.definition LIKE '%ORDR%' OR m.definition LIKE '%SBO_SP_Transaction%')
       AND o.name LIKE 'SEI%'
""")
for r in cur.fetchall():
    print(f"  {r.type_desc:16} {r.name}  ({r.def_len} chars)")

conn.close()
