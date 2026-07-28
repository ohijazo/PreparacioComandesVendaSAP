"""Busca TOT el que referencia els UDFs mancants o la SP SEI_VALIDACIONES_GAP001.
També mira Approval Procedures i B1 Validation configurations a taules SAP."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

import _bootstrap  # noqa: F401
import consultes

conn = consultes.connectar()
cur = conn.cursor()

# 1. Qualsevol SP/funció/vista/trigger que menciona els UDFs mancants
print("=== 1. Objectes SQL que referencien U_FC_OrderStatus / U_FC_RiskOverride* ===")
cur.execute("""
    SELECT o.name, o.type_desc,
           CASE WHEN m.definition LIKE '%U_FC_OrderStatus%' THEN 'Y' ELSE '' END AS ref_status,
           CASE WHEN m.definition LIKE '%U_FC_RiskOverride%' THEN 'Y' ELSE '' END AS ref_override
      FROM sys.sql_modules m
      JOIN sys.objects o ON m.object_id = o.object_id
     WHERE m.definition LIKE '%U_FC_OrderStatus%'
        OR m.definition LIKE '%U_FC_RiskOverride%'
""")
for r in cur.fetchall():
    print(f"    {r.type_desc:24} {r.name:40} status={r.ref_status} override={r.ref_override}")

# 2. Qualsevol SP/funció que crida SEI_VALIDACIONES_GAP001 o GAP001_*
print("\n=== 2. Objectes SQL que criden GAP001* ===")
cur.execute("""
    SELECT o.name, o.type_desc
      FROM sys.sql_modules m
      JOIN sys.objects o ON m.object_id = o.object_id
     WHERE m.definition LIKE '%GAP001%'
""")
for r in cur.fetchall():
    print(f"    {r.type_desc:24} {r.name}")

# 3. Approval Procedures actives per object_type 17 (Order)
print("\n=== 3. Approval Templates per Sales Order (object_type 17) ===")
try:
    cur.execute("""
        SELECT WddCode, Name, DocEntry AS Template, Active
          FROM OWTM
         WHERE ObjType = '17'
    """)
    rows = cur.fetchall()
    print(f"  {len(rows)} template(s):")
    for r in rows:
        print(f"    WddCode={r.WddCode} Name={r.Name!r} Active={r.Active}")
except Exception as e:
    print(f"  (OWTM no accessible: {e})")

# 4. Approval Stages amb query lligada a GAP001
print("\n=== 4. Approval Stages amb queries que mencionen GAP001 o U_FC_* ===")
try:
    cur.execute("""
        SELECT s.WstCode, s.Name, LEFT(s.SqlString, 200) AS sql_prev
          FROM OWST s
         WHERE s.SqlString LIKE '%GAP001%'
            OR s.SqlString LIKE '%U_FC_OrderStatus%'
            OR s.SqlString LIKE '%U_FC_RiskOverride%'
    """)
    for r in cur.fetchall():
        print(f"    WstCode={r.WstCode} Name={r.Name!r}")
        print(f"      SQL: {r.sql_prev}")
except Exception as e:
    print(f"  (OWST no accessible: {e})")

# 5. Approval Templates i les seves stages (visibilitat completa)
print("\n=== 5. Templates aprovacio actius + stages ===")
try:
    cur.execute("""
        SELECT t.WddCode, t.Name AS TemplateName, t.Active,
               t.ObjType, t.ExpandType
          FROM OWTM t
         WHERE t.Active = 'Y'
    """)
    rows = cur.fetchall()
    print(f"  {len(rows)} template(s) actiu(s):")
    for r in rows:
        print(f"    {r.WddCode:6} ObjType={r.ObjType:>4} {r.Name!r}")
except Exception as e:
    print(f"  ERROR: {e}")

# 6. Queries a Query Manager relacionades amb GAP001
print("\n=== 6. Query Manager: queries GAP001* ===")
try:
    cur.execute("""
        SELECT QName, QCategory, LEFT(QString, 200) AS sql_prev
          FROM OUQR
         WHERE QName LIKE '%GAP001%'
            OR QString LIKE '%GAP001%'
            OR QString LIKE '%U_FC_OrderStatus%'
    """)
    for r in cur.fetchall():
        print(f"    {r.QName!r} (categoria {r.QCategory})")
        print(f"      SQL: {r.sql_prev}")
except Exception as e:
    print(f"  ERROR: {e}")

# 7. B1 Validation Configurations (taula CUV*/USR*)
print("\n=== 7. B1 Validation regles (buscant taules relacionades) ===")
try:
    cur.execute("""
        SELECT name FROM sys.tables
         WHERE name LIKE 'CUV%' OR name LIKE 'OUV%' OR name LIKE 'USR%'
         ORDER BY name
    """)
    rows = [r.name for r in cur.fetchall()]
    print(f"  Taules candidates: {rows}")
except Exception as e:
    print(f"  ERROR: {e}")

conn.close()
