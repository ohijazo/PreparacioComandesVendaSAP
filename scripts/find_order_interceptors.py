"""Enumera TOTS els interceptors possibles per Sales Order (object 17):
- B1 Validation Configurations
- Approval Procedures actives
- User Alerts amb query relacionada a Orders
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))

import _bootstrap  # noqa: F401
import consultes

conn = consultes.connectar()
cur = conn.cursor()

# 1. Approval Templates (WDD1) i stages (WDD2)
print("=== 1. Approval Templates (WDD1) per Sales Order (17) ===")
try:
    cur.execute("""
        SELECT WddCode, Name, ObjType, Active, Instance
          FROM WDD1
         WHERE ObjType = 17
    """)
    for r in cur.fetchall():
        print(f"    WddCode={r.WddCode:>3}  Active={r.Active}  Instance={r.Instance}  Name={r.Name!r}")
except Exception as e:
    print(f"  WDD1 fail: {e}")
    # Fallback: llistar totes les Approval Templates
    try:
        cur.execute("SELECT TOP 5 * FROM WDD1")
        cols = [c[0] for c in cur.description]
        print(f"  WDD1 columnes: {cols}")
    except Exception as e2:
        print(f"  cap WDD1: {e2}")

# 2. OWTQ — Approval Query Templates
print("\n=== 2. Approval Terms Query (OAPT/OWTQ/UDQ) ===")
for candidate in ("OWTQ", "OAPT", "OTRM", "AODC"):
    try:
        cur.execute(f"SELECT TOP 1 * FROM {candidate}")
        cols = [c[0] for c in cur.description]
        print(f"  {candidate}: {cols[:10]}...")
    except Exception:
        pass

# 3. User Alerts (OALR + ALR1)
print("\n=== 3. User Alerts (OALR) actives que menciona ORDR/Order ===")
try:
    cur.execute("""
        SELECT AlertCode, Name, Priority, Active
          FROM OALR
         WHERE Active = 'Y'
    """)
    rows = cur.fetchall()
    print(f"  {len(rows)} alertes actives:")
    for r in rows:
        print(f"    Code={r.AlertCode}  Prio={r.Priority}  Name={r.Name!r}")
except Exception as e:
    print(f"  OALR fail: {e}")

# 4. B1 Validation — buscar taula real
print("\n=== 4. B1 Validation Configurations — buscar taules ===")
try:
    cur.execute("""
        SELECT name FROM sys.tables
         WHERE name LIKE 'CUFD%' OR name LIKE 'OFV%' OR name LIKE 'CUSC%'
            OR name IN ('SVFR', 'SVCR', 'OB1V')
         ORDER BY name
    """)
    for r in cur.fetchall():
        print(f"    {r.name}")
except Exception as e:
    print(f"  fail: {e}")

# 5. Formatted Search / User Query lligats a ORDR
print("\n=== 5. Formatted Searches (CUFD) lligades a ORDR ===")
try:
    cur.execute("""
        SELECT TableID, AliasID, EditType, EditSize, Descr
          FROM CUFD
         WHERE TableID = 'ORDR'
           AND EditType IS NOT NULL AND EditType <> ''
    """)
    rows = cur.fetchall()
    print(f"  {len(rows)} camps ORDR amb FS/edit config:")
    for r in rows[:20]:
        print(f"    {r.AliasID:<25} EditType={r.EditType} Descr={r.Descr!r}")
except Exception as e:
    print(f"  CUFD fail: {e}")

# 6. Cerca de qualsevol taula amb 'Valid' al nom
print("\n=== 6. Taules amb 'Valid' al nom ===")
try:
    cur.execute("""
        SELECT name FROM sys.tables
         WHERE name LIKE '%Valid%' OR name LIKE '%VAL%'
         ORDER BY name
    """)
    for r in cur.fetchall():
        print(f"    {r.name}")
except Exception as e:
    print(f"  fail: {e}")

# 7. SDK Add-ons registrats
print("\n=== 7. Add-ons SDK registrats (SAAO) ===")
try:
    cur.execute("""
        SELECT AddOnName, AddOnDesc, Active, Vendor, Version
          FROM SAAO
    """)
    for r in cur.fetchall():
        act = "ACTIU" if r.Active == "Y" else "inactiu"
        print(f"    [{act:7}] {r.AddOnName:<40} v{r.Version} ({r.Vendor})")
except Exception as e:
    print(f"  SAAO fail: {e}")

conn.close()
