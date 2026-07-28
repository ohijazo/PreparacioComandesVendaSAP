"""Verifica que RDR1.U_FCAfegit existeix."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

import _bootstrap  # noqa: F401
import consultes

conn = consultes.connectar()
row = conn.execute("""
    SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH
      FROM INFORMATION_SCHEMA.COLUMNS
     WHERE TABLE_NAME='RDR1' AND COLUMN_NAME='U_FCAfegit'
""").fetchone()
conn.close()

if row is None:
    print("❌ U_FCAfegit NO existeix a RDR1")
    sys.exit(1)
print(f"✅ U_FCAfegit existeix: type={row.DATA_TYPE}({row.CHARACTER_MAXIMUM_LENGTH})")
