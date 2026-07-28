# Completar la instal·lació GAP001 — crear els 3 UDFs mancants a ORDR

Aquesta guia acaba una instal·lació de customització (`SEI_VALIDACIONES_GAP001`)
que va quedar a mitges: la SP està activa al `SBO_SP_TransactionNotification`
però els 3 UDFs que llegeix mai es van crear.

## Impacte del bug

- La SP intenta `SELECT ISNULL(U_FC_OrderStatus, 'REVISION'), ISNULL(U_FC_RiskOverride, 'N'), ...`.
- Aquests camps **no existeixen** a `ORDR` → error "Invalid column name".
- Els errors de tipus "invalid column name" **no** els captura el `BEGIN CATCH`
  (falla al compile-time del statement, abans que el CATCH pugui actuar).
- Resultat: **qualsevol PATCH sobre `Orders` via Service Layer / DI-API falla
  amb `-1116 "Could not commit transaction"`**. El client d'escriptori SAP és
  més tolerant i deixa passar l'update; el SL/DI-API no.

## UDFs a crear

Tots 3 a `Marketing Documents → Title` (com els UDFs del motor d'embalatges).

| # | Nom (sense `U_`) | Tipus | Longitud | Descripció |
|---|---|---|---|---|
| 1 | `FC_OrderStatus` | Alphanumeric | 15 | Estat GAP001 del pedido (`REVISION` / `CONFIRMADO`) |
| 2 | `FC_RiskOverride` | Alphanumeric | 1 | Flag override de risc (`Y` / `N`) |
| 3 | `FC_RiskOverrideDate` | Date + Time | — | Data i hora de l'aprovació de l'override |

> **Nota crítica**: els noms **han de portar l'underscore entre `FC` i la
> resta** (`FC_OrderStatus`, no `FCOrderStatus`). La SP els referencia
> literalment. SAP afegirà el prefix `U_` automàticament.

## Pas 1 — Obrir el gestor d'UDFs

1. Menú superior: **Tools** → **Customization Tools** → **User-Defined Fields — Management**.
2. Assegura't que **cap usuari té oberta cap Comanda de venda** (SAP tanca formularis oberts al desar UDFs a ORDR).

## Pas 2 — Navegar a `Marketing Documents → Title`

```
Master Data
  └─ Marketing Documents
     └─ Title           ← aquí crearem els 3 UDFs
```

## Pas 3 — Crear `U_FC_OrderStatus`

1. **Add** (o Data → Add).
2. Omple:

| Camp | Valor |
|---|---|
| **Title** | `FC_OrderStatus` |
| **Description** | `GAP001 — Estat pedido` |
| **Type** | `Alphanumeric` |
| **Length** | `15` |
| **Structure** | `Regular` |

3. **Set Valid Values for Field** (recomanat):
   - Value = `REVISION`, Description = `En revisió`
   - Value = `CONFIRMADO`, Description = `Confirmat`
   - Set Default = `REVISION`.
4. **Add** i confirma.

## Pas 4 — Crear `U_FC_RiskOverride`

1. **Add**.
2. Omple:

| Camp | Valor |
|---|---|
| **Title** | `FC_RiskOverride` |
| **Description** | `GAP001 — Override de risc` |
| **Type** | `Alphanumeric` |
| **Length** | `1` |
| **Structure** | `Regular` |

3. **Set Valid Values**:
   - Value = `Y`, Description = `Sí (override aprovat)`
   - Value = `N`, Description = `No`
   - Set Default = `N`.
4. **Add** i confirma.

## Pas 5 — Crear `U_FC_RiskOverrideDate`

1. **Add**.
2. Omple:

| Camp | Valor |
|---|---|
| **Title** | `FC_RiskOverrideDate` |
| **Description** | `GAP001 — Data override risc` |
| **Type** | `Date/Time` |
| **Structure** | (per defecte) |

> Nota: al UDF Manager, `Date/Time` correspon al tipus `db_Date` amb subtipus
> temps. Si SAP demana escollir només `Date`, tria `Date` — la SP fa
> `DATEADD` amb un `UpdateTS` extern, no depèn del subtipus.

3. **Add** i confirma.

## Pas 6 — Verificació via SQL

```sql
SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH
  FROM INFORMATION_SCHEMA.COLUMNS
 WHERE TABLE_NAME = 'ORDR'
   AND COLUMN_NAME IN ('U_FC_OrderStatus', 'U_FC_RiskOverride', 'U_FC_RiskOverrideDate')
 ORDER BY COLUMN_NAME;
```

Ha de retornar **3 files**.

## Pas 7 — Verificació funcional (el pas important)

Un cop creats, torna a executar:

```bash
python scripts/test_patch_isolat.py 126
```

Comportament esperat:
- **A. PATCH Comments** → ✅ 204
- **B–E. PATCH UDFs FC** → ✅ 204
- **G. GET** → ✅ 200 (com abans)
- **H. PATCH BusinessPartners** → ✅ 204 (com abans)

L'únic que probablement seguirà fallant és **F. POST Orders/Update** amb
`-1029 "Field cannot be updated"` — és una limitació d'aquest endpoint
específic (no permet UDFs directes), no un blocador. El worker usa PATCH,
no POST/Update.

## Comportament un cop creats els UDFs

- Totes les Orders existents tindran els 3 UDFs a `NULL`.
- `ISNULL(U_FC_OrderStatus, 'REVISION')` → `'REVISION'`.
- La SP entra al `IF @g1_order_status = 'CONFIRMADO'`... → fals → **no fa res**.
- El PATCH es completa amb èxit.

Quan (si) SEIDOR o el consultor completin GAP001 (poblant `U_FC_OrderStatus`
amb `'CONFIRMADO'` en algun moment del workflow), la validació de risc
començarà a actuar. Fins llavors, la SP no afectarà cap operació.

---

**Data creació guia**: 2026-07-28.
**Relacionat amb**: Fase 2.6 (integració SAP) del projecte Motor Comandes,
diagnòstic del bloqueig `-1116` a `tasks/fase2_progress.md`.
