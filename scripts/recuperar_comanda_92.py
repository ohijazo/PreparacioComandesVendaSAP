"""Diagnòstic + intent de restaurar comanda 92 des de l'històric SAP."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))
import _bootstrap  # noqa
import consultes

conn = consultes.connectar()

print("=== 1. Estat ACTUAL de RDR1 per DocEntry=92 ===")
rows = conn.execute("""
    SELECT LineNum, RTRIM(ItemCode) AS ItemCode, RTRIM(Dscription) AS Descrip,
           Quantity, PackQty, Price, LineTotal, U_FCAfegit
      FROM RDR1 WHERE DocEntry = 92 ORDER BY LineNum
""").fetchall()
print(f"  {len(rows)} línies actualment:")
for r in rows:
    print(f"    L{r.LineNum} {r.ItemCode} ({r.Descrip})  Qty={r.Quantity} "
          f"PackQty={r.PackQty} Price={r.Price} U_FCAfegit={r.U_FCAfegit!r}")

print("\n=== 2. Històric ADO1 per DocEntry=92 (versions anteriors) ===")
try:
    hist = conn.execute("""
        SELECT LogInstanc, LineNum, RTRIM(ItemCode) AS ItemCode,
               RTRIM(Dscription) AS Descrip,
               Quantity, PackQty, Price, LineTotal
          FROM ADO1 WHERE DocEntry = 92
         ORDER BY LogInstanc DESC, LineNum
    """).fetchall()
    print(f"  {len(hist)} entrades històriques:")
    for r in hist:
        print(f"    Log{r.LogInstanc} L{r.LineNum} {r.ItemCode} ({r.Descrip})  "
              f"Qty={r.Quantity} PackQty={r.PackQty} Price={r.Price}")
except Exception as e:
    print(f"  ADO1 no accessible: {e}")

print("\n=== 3. Instàncies històriques a ADOC ===")
try:
    docs = conn.execute("""
        SELECT LogInstanc, UpdateDate, UpdateTS, UserSign
          FROM ADOC WHERE DocEntry = 92 AND ObjType = '17'
         ORDER BY LogInstanc DESC
    """).fetchall()
    print(f"  {len(docs)} versions:")
    for d in docs:
        print(f"    Log{d.LogInstanc}  UpdateDate={d.UpdateDate} TS={d.UpdateTS} User={d.UserSign}")
except Exception as e:
    print(f"  ADOC no accessible: {e}")

conn.close()
