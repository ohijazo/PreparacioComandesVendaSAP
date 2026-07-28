"""Troba comandes obertes amb sacs S05-S25 I direcció amb tipus_descarrega='P' (PALET)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))
import _bootstrap  # noqa
import consultes

conn = consultes.connectar()
rows = conn.execute("""
    SELECT TOP 10
           h.DocEntry, h.Series, h.DocNum, RTRIM(h.CardCode) AS CardCode,
           RTRIM(h.ShipToCode) AS ShipToCode,
           RTRIM(d.U_SEITIPOD) AS tipus_descarrega,
           h.DocDate,
           COUNT(DISTINCT l.LineNum) AS n_linies,
           SUM(l.PackQty) AS total_sacs
      FROM ORDR h WITH (NOLOCK)
      JOIN RDR1 l WITH (NOLOCK) ON l.DocEntry = h.DocEntry
      JOIN OITM i WITH (NOLOCK) ON i.ItemCode = l.ItemCode
      LEFT JOIN CRD1 d WITH (NOLOCK)
        ON d.CardCode = h.CardCode
       AND d.Address = h.ShipToCode
       AND d.AdresType = 'S'
     WHERE h.DocStatus = 'O'
       AND i.SalUnitMsr LIKE 'S%'
       AND SUBSTRING(i.SalUnitMsr, 2, 2) IN ('05','10','15','20','25')
       AND (d.U_SEITIPOD = 'P' OR d.U_SEITIPOD IS NULL)  -- PALET o no definit
  GROUP BY h.DocEntry, h.Series, h.DocNum, h.CardCode, h.ShipToCode, d.U_SEITIPOD, h.DocDate
    HAVING SUM(l.PackQty) >= 40
  ORDER BY h.DocDate DESC, h.DocEntry DESC
""").fetchall()

print(f"{len(rows)} comandes candidates PALET amb ≥ 40 sacs:\n")
for r in rows:
    tip = r.tipus_descarrega or '(no def)'
    print(f"  DocEntry={r.DocEntry:>5}  DocNum={r.DocNum}  {r.CardCode:<10}  "
          f"ShipTo={r.ShipToCode:<8}  tip={tip}  "
          f"{r.n_linies} líns  {int(r.total_sacs or 0)} sacs")
conn.close()
