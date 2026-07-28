"""Dump complet del SBO_SP_TransactionNotification per veure exactament
què s'executa i què està comentat. Guardem a fitxer per revisar-lo tranquils."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

import _bootstrap  # noqa: F401
import consultes

conn = consultes.connectar()
cur = conn.cursor()

# 1. SBO_SP_TransactionNotification complet
cur.execute("""
    SELECT definition
      FROM sys.sql_modules m
      JOIN sys.objects o ON m.object_id = o.object_id
     WHERE o.name = 'SBO_SP_TransactionNotification'
""")
sp = cur.fetchone().definition

out_path = os.path.join("scripts", "_dump_sbo_sp_tn.sql")
with open(out_path, "w", encoding="utf-8") as f:
    f.write(sp)
print(f"Escrit {out_path} ({len(sp)} chars)")

# 2. Cerca de línies NO comentades que criden EXEC a SEI_*
print("\n=== Línies EXEC/SEI_* NO comentades ===")
for i, line in enumerate(sp.splitlines(), 1):
    stripped = line.strip()
    if stripped.startswith("--"):
        continue
    up = stripped.upper()
    if "EXEC" in up and "SEI_" in up:
        print(f"  L{i}: {line}")
    elif "SEI_VALIDACIONES" in up:
        print(f"  L{i}: {line}")

# 3. Cerca de la paraula 'GAP001' — indica on hi ha (o no) la crida
print("\n=== Totes les línies amb 'GAP001' (per veure si estan comentades) ===")
for i, line in enumerate(sp.splitlines(), 1):
    if "GAP001" in line.upper():
        marker = "COMMENT" if line.strip().startswith("--") else "*ACTIVE*"
        print(f"  L{i} [{marker}]: {line}")

# 4. Dimensió i marcadors de SEI_VALIDACIONES_SII
print("\n=== SEI_VALIDACIONES_SII: mida i primeres línies (per veure si crida coses interessants) ===")
cur.execute("""
    SELECT definition
      FROM sys.sql_modules m
      JOIN sys.objects o ON m.object_id = o.object_id
     WHERE o.name = 'SEI_VALIDACIONES_SII'
""")
sii = cur.fetchone().definition
print(f"  len = {len(sii)} chars")
# Buscar EXEC dins SII
count_exec = 0
for i, line in enumerate(sii.splitlines(), 1):
    stripped = line.strip()
    if stripped.startswith("--"):
        continue
    if "EXEC " in stripped.upper():
        count_exec += 1
        if count_exec <= 20:
            print(f"    L{i}: {line[:200]}")
print(f"  EXEC no comentats: {count_exec}")

# 5. Dins SII, quin object_type filtra?
print("\n=== Object types que gestiona SEI_VALIDACIONES_SII ===")
import re
matches = re.findall(r"@object_type\s*=\s*'(\d+)'", sii)
print(f"  object_types trobats: {sorted(set(matches))}")

conn.close()
