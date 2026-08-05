"""Diagnòstic: per què les comandes 26600132-26600147 no surten a /api/ultimes-comandes.

Comprova per cada DocNum:
- Existeix a ORDR? Amb quin DocStatus i DocDate?
- Quantes línies té? Quins SalUnitMsr?
- La subquery NOT EXISTS...GRA de obtenir_ultimes_comandes l'excluiria?
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))
import _bootstrap  # noqa
import consultes

DOCNUMS = [f"266001{n:02d}" for n in range(32, 48)]  # 26600132..26600147

conn = consultes.connectar()

print(f"Buscant DocNums: {DOCNUMS}\n")

for docnum in DOCNUMS:
    row = conn.execute("""
        SELECT h.DocEntry, h.Series, h.DocNum, h.DocStatus, h.DocDate,
               h.DocDueDate, RTRIM(h.CardCode) AS CardCode, RTRIM(h.CardName) AS CardName
          FROM ORDR h WITH (NOLOCK)
         WHERE h.DocNum = ?
    """, int(docnum)).fetchone()

    if not row:
        print(f"[NO EXISTEIX] {docnum}")
        continue

    linies = conn.execute("""
        SELECT l.LineNum, RTRIM(l.ItemCode) AS ItemCode, l.Quantity,
               RTRIM(i.SalUnitMsr) AS SalUnitMsr
          FROM RDR1 l WITH (NOLOCK)
          LEFT JOIN OITM i WITH (NOLOCK) ON i.ItemCode = l.ItemCode
         WHERE l.DocEntry = ?
      ORDER BY l.LineNum
    """, row.DocEntry).fetchall()

    tunitats = [l.SalUnitMsr for l in linies]
    te_gra = any(u == 'GRA' for u in tunitats)
    te_sacs = any(u and u.startswith('S') for u in tunitats)
    exclos_per_filtre = te_gra and not te_sacs  # la subquery NOT EXISTS...GRA...NOT EXISTS...S%

    tag = "OK APAREIX"
    if row.DocStatus != 'O':
        tag = f"EXCLOS: DocStatus={row.DocStatus}"
    elif row.DocDate.year != 2026:
        tag = f"EXCLOS: DocDate.year={row.DocDate.year}"
    elif exclos_per_filtre:
        tag = "EXCLOS: NOMES GRANEL (RF1)"

    print(f"[{tag}] {row.Series}/{row.DocNum} · {row.CardCode} {row.CardName[:30]:<30} · "
          f"DocDate={row.DocDate.strftime('%d/%m/%Y')} DocStatus={row.DocStatus} · "
          f"{len(linies)} línies TUnitats={tunitats}")

conn.close()
