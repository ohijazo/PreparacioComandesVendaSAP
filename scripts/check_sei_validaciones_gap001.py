"""Investiga SEI_VALIDACIONES_GAP001 i si SBO_SP_TransactionNotification la crida."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

import _bootstrap  # noqa: F401
import consultes

conn = consultes.connectar()
cur = conn.cursor()

# 1. SBO_SP_TransactionNotification menciona GAP001?
print("=== 1. SBO_SP_TransactionNotification crida GAP001? ===")
cur.execute("""
    SELECT CASE WHEN definition LIKE '%SEI_VALIDACIONES_GAP001%' THEN 'SI' ELSE 'NO' END AS crida_gap001,
           CASE WHEN definition LIKE '%SEI_VALIDACIONES_SII%' THEN 'SI' ELSE 'NO' END AS crida_sii,
           LEN(definition) AS len_total
      FROM sys.sql_modules m
      JOIN sys.objects o ON m.object_id = o.object_id
     WHERE o.name = 'SBO_SP_TransactionNotification'
""")
r = cur.fetchone()
print(f"  crida GAP001: {r.crida_gap001}")
print(f"  crida SII   : {r.crida_sii}")
print(f"  len total   : {r.len_total} chars")

# 2. Extreure la línia (i unes quantes al voltant) on es crida GAP001, si hi és
print("\n=== 2. Extractes on SBO_SP_TN crida GAP001 (si aplica) ===")
cur.execute("""
    SELECT definition FROM sys.sql_modules m
      JOIN sys.objects o ON m.object_id = o.object_id
     WHERE o.name = 'SBO_SP_TransactionNotification'
""")
sp_def = cur.fetchone().definition
idx = sp_def.upper().find("SEI_VALIDACIONES_GAP001".upper())
if idx >= 0:
    start = max(0, idx - 400)
    end = min(len(sp_def), idx + 400)
    print(sp_def[start:end])
else:
    print("  (SBO_SP_TN no crida GAP001)")

# 3. Extreure les branques del SBO_SP_TN que fan un UPDATE sobre object_type=17
print("\n=== 3. Branques on SBO_SP_TN toca object_type '17' (Order) ===")
low = sp_def
occurrences = []
i = 0
while True:
    j = low.find("'17'", i)
    if j < 0:
        break
    occurrences.append(j)
    i = j + 1
print(f"  aparicions de '17': {len(occurrences)}")
for k, j in enumerate(occurrences[:5]):
    start = max(0, j - 200)
    end = min(len(low), j + 400)
    print(f"\n--- ocurrència {k+1} (pos {j}):")
    print(low[start:end])

# 4. Codi complet de SEI_VALIDACIONES_GAP001
print("\n\n=== 4. Codi de SEI_VALIDACIONES_GAP001 (primer 3000 chars) ===")
cur.execute("""
    SELECT definition FROM sys.sql_modules m
      JOIN sys.objects o ON m.object_id = o.object_id
     WHERE o.name = 'SEI_VALIDACIONES_GAP001'
""")
gap = cur.fetchone().definition
print(gap[:3000])

conn.close()
