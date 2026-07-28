"""Descobreix camps de quantitat de RDR1 (robust: comprova quins existeixen)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))
import _bootstrap  # noqa
import consultes

conn = consultes.connectar()

# 1. Llistar totes les columnes de RDR1 que semblen relacionades amb quantitats
cols = conn.execute("""
    SELECT COLUMN_NAME, DATA_TYPE
      FROM INFORMATION_SCHEMA.COLUMNS
     WHERE TABLE_NAME = 'RDR1'
       AND (COLUMN_NAME LIKE '%Qty%'
            OR COLUMN_NAME LIKE '%Quantity%'
            OR COLUMN_NAME LIKE '%Pack%'
            OR COLUMN_NAME LIKE '%Num%'
            OR COLUMN_NAME LIKE '%Msr%'
            OR COLUMN_NAME LIKE '%Uom%'
            OR COLUMN_NAME LIKE 'U_%')
     ORDER BY COLUMN_NAME
""").fetchall()
print(f"=== Columnes candidates de RDR1 ({len(cols)}) ===")
for c in cols:
    print(f"  {c.COLUMN_NAME:<30} {c.DATA_TYPE}")

# 2. Mateixa cosa per OITM
print(f"\n=== Columnes candidates de OITM ===")
oitm_cols = conn.execute("""
    SELECT COLUMN_NAME, DATA_TYPE
      FROM INFORMATION_SCHEMA.COLUMNS
     WHERE TABLE_NAME = 'OITM'
       AND (COLUMN_NAME LIKE '%Qty%'
            OR COLUMN_NAME LIKE '%Pack%'
            OR COLUMN_NAME LIKE '%Num%'
            OR COLUMN_NAME LIKE '%Msr%'
            OR COLUMN_NAME LIKE '%Uom%'
            OR COLUMN_NAME LIKE '%UoM%'
            OR COLUMN_NAME LIKE 'SW%'
            OR COLUMN_NAME LIKE '%Sale%'
            OR COLUMN_NAME LIKE '%Sal%')
     ORDER BY COLUMN_NAME
""").fetchall()
for c in oitm_cols:
    print(f"  {c.COLUMN_NAME:<30} {c.DATA_TYPE}")

# 3. Ara dumpejar tots els valors d'aquestes columnes per la línia de la comanda 94
rdr1_col_names = [c.COLUMN_NAME for c in cols]
# Descarta ntext (no compatible amb algunes queries)
rdr1_col_names = [c for c, dt in [(c.COLUMN_NAME, c.DATA_TYPE) for c in cols]
                  if dt != 'ntext']

select_list = ", ".join(f"l.[{c}]" for c in rdr1_col_names)
sql = f"""
    SELECT l.LineNum, RTRIM(l.ItemCode) AS ItemCode, RTRIM(l.Dscription) AS Descrip,
           {select_list}
      FROM RDR1 l WITH (NOLOCK)
     WHERE l.DocEntry = 94
     ORDER BY l.LineNum
"""
rows = conn.execute(sql).fetchall()
print(f"\n=== Valors RDR1 per DocEntry=94 ({len(rows)} línies) ===\n")
for r in rows:
    print(f"--- Línia {r.LineNum}: {r.ItemCode} ({r.Descrip}) ---")
    for c in rdr1_col_names:
        v = getattr(r, c, None)
        if v is not None and v != 0 and v != '':
            print(f"  {c:<30} = {v}")
    print()
conn.close()
