"""Verifica U_FC_OrderStatus i risc de client per la 126, i busca alternatives 'REVISION'."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

import _bootstrap  # noqa: F401
import consultes

conn = consultes.connectar()
cur = conn.cursor()

# 1. Estat de la 126
print("=== 1. Estat de la comanda 126 ===")
cur.execute("""
    SELECT DocEntry, DocNum, CardCode,
           ISNULL(U_FC_OrderStatus, 'REVISION') AS OrderStatus,
           ISNULL(U_FC_RiskOverride, 'N') AS RiskOverride,
           DocStatus
      FROM ORDR
     WHERE DocEntry = 126
""")
r = cur.fetchone()
if r:
    print(f"  DocEntry={r.DocEntry}  DocNum={r.DocNum}  CardCode={r.CardCode}")
    print(f"  U_FC_OrderStatus = {r.OrderStatus!r}")
    print(f"  U_FC_RiskOverride= {r.RiskOverride!r}")
    print(f"  DocStatus        = {r.DocStatus!r}")
else:
    print("  (no trobada)")

# 2. Executar GAP001_ValidarRiscClient per veure què retorna
print("\n=== 2. Risc del client C001024 ===")
try:
    cur.execute("""
        DECLARE @nr INT, @m NVARCHAR(500), @d NVARCHAR(MAX)
        EXEC GAP001_ValidarRiscClient 'C001024', 0, @nr OUTPUT, @m OUTPUT, @d OUTPUT
        SELECT @nr AS nivell_risc, @m AS missatge, @d AS detall
    """)
    r = cur.fetchone()
    print(f"  nivell_risc = {r.nivell_risc}")
    print(f"  missatge    = {r.missatge!r}")
    print(f"  detall      = {(r.detall or '')[:400]!r}")
except Exception as e:
    print(f"  ERROR executant GAP001_ValidarRiscClient: {e}")

# 3. Buscar comandes en 'REVISION' (o NULL) recents per provar PATCH
print("\n=== 3. Comandes recents en REVISION (candidates per test) ===")
cur.execute("""
    SELECT TOP 10 DocEntry, DocNum, CardCode,
           ISNULL(U_FC_OrderStatus, 'REVISION') AS OrderStatus,
           DocStatus, DocDate
      FROM ORDR
     WHERE DocStatus = 'O'
       AND (U_FC_OrderStatus IS NULL OR U_FC_OrderStatus <> 'CONFIRMADO')
     ORDER BY DocDate DESC, DocEntry DESC
""")
rows = cur.fetchall()
print(f"  {len(rows)} candidates:")
for r in rows:
    print(f"    DocEntry={r.DocEntry:>6}  DocNum={r.DocNum}  CC={r.CardCode:<10} status={r.OrderStatus!r:<12} DocDate={r.DocDate}")

# 4. Distribució global d'estats
print("\n=== 4. Distribució U_FC_OrderStatus (comandes obertes) ===")
cur.execute("""
    SELECT ISNULL(U_FC_OrderStatus, '(NULL)') AS status, COUNT(*) AS n
      FROM ORDR
     WHERE DocStatus = 'O'
  GROUP BY U_FC_OrderStatus
  ORDER BY n DESC
""")
for r in cur.fetchall():
    print(f"    {r.status!r:<15} : {r.n}")

conn.close()
