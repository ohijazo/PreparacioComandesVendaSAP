"""Codi complet de SEI_VALIDACIONES_GAP001 + verifica quins UDFs U_FC* existeixen realment a ORDR."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

import _bootstrap  # noqa: F401
import consultes

conn = consultes.connectar()
cur = conn.cursor()

# 1. Quins UDFs U_FC* existeixen a ORDR?
print("=== 1. UDFs U_FC* existents a ORDR ===")
cur.execute("""
    SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH
      FROM INFORMATION_SCHEMA.COLUMNS
     WHERE TABLE_NAME = 'ORDR'
       AND COLUMN_NAME LIKE 'U[_]FC%'
     ORDER BY COLUMN_NAME
""")
for r in cur.fetchall():
    print(f"    {r.COLUMN_NAME:<40} {r.DATA_TYPE}({r.CHARACTER_MAXIMUM_LENGTH})")

# 2. Codi complet de SEI_VALIDACIONES_GAP001 (dividit en trossos)
print("\n=== 2. Codi complet de SEI_VALIDACIONES_GAP001 ===")
cur.execute("""
    SELECT definition
      FROM sys.sql_modules m
      JOIN sys.objects o ON m.object_id = o.object_id
     WHERE o.name = 'SEI_VALIDACIONES_GAP001'
""")
d = cur.fetchone().definition
print(d)

# 3. Existeix GAP001_ValidarRiscClient?
print("\n=== 3. GAP001_ValidarRiscClient existeix? ===")
cur.execute("""
    SELECT COUNT(*) AS n
      FROM sys.objects
     WHERE name = 'GAP001_ValidarRiscClient'
""")
print(f"    n={cur.fetchone().n}")

# 4. Existeix [@FC_GAP001_OVRDUSR]?
print("\n=== 4. Taula [@FC_GAP001_OVRDUSR] existeix? ===")
cur.execute("""
    SELECT COUNT(*) AS n
      FROM sys.tables
     WHERE name = '@FC_GAP001_OVRDUSR'
""")
print(f"    n={cur.fetchone().n}")

conn.close()
