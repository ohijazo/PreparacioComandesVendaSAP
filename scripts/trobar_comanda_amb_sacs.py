"""Troba 5 comandes obertes amb almenys una línia amb TUnitat S05-S25."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))
import _bootstrap  # noqa
import consultes

conn = consultes.connectar()
rows = conn.execute("""
    SELECT TOP 10
           h.DocEntry, h.Series, h.DocNum, RTRIM(h.CardCode) AS CardCode,
           h.DocDate,
           COUNT(l.LineNum) AS n_linies_sacs
      FROM ORDR h WITH (NOLOCK)
      JOIN RDR1 l WITH (NOLOCK) ON l.DocEntry = h.DocEntry
      JOIN OITM i WITH (NOLOCK) ON i.ItemCode = l.ItemCode
     WHERE h.DocStatus = 'O'
       AND i.SalUnitMsr LIKE 'S%'
       AND SUBSTRING(i.SalUnitMsr, 2, 2) IN ('05','10','15','20','25')
  GROUP BY h.DocEntry, h.Series, h.DocNum, h.CardCode, h.DocDate
    HAVING COUNT(l.LineNum) >= 1
  ORDER BY h.DocDate DESC, h.DocEntry DESC
""").fetchall()

print(f"{len(rows)} comandes candidates amb sacs S05-S25:\n")
for r in rows:
    print(f"  DocEntry={r.DocEntry:>5}  DocNum={r.DocNum}  {r.CardCode:<10}  "
          f"{r.DocDate}  ({r.n_linies_sacs} línia/es sacs)")
conn.close()
