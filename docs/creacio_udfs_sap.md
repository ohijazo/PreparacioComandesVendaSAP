# Creació dels 3 UDFs a SAP per a la integració del motor d'embalatges

Aquesta guia detalla com crear els 3 UDFs necessaris a la taula `ORDR`
(Sales Orders) directament des del client SAP Business One.

**Prerequisits**:
- Accés al SAP client (Fat Client o Web Client) amb usuari que tingui
  permís per **Customization Tools → User-Defined Fields**.
- Recomanat: **cap usuari amb el formulari Sales Order obert** durant
  la creació (SAP tanca formularis oberts al desar UDFs nous a ORDR).

**Resum dels 3 UDFs a crear** (tots a `Marketing Documents → Title`):

| # | Nom (sense `U_`) | Tipus | Longitud | Descripció |
|---|---|---|---|---|
| 1 | `FCCalcular` | Alphanumeric | 1 | Flag S/N per demanar càlcul d'embalatge |
| 2 | `FCEmbalatgeResum` | Alphanumeric | 254 | Resum textual del càlcul |
| 3 | `FCEmbalatgeEstat` | Alphanumeric | 30 | Estat del càlcul (CALCULAT/ERROR/etc.) |

> **Nota**: SAP afegeix automàticament el prefix `U_` a tots els UDFs.
> Quan al formulari escrius `FCCalcular`, la BD tindrà `U_FCCalcular`.

---

## Pas 1 — Obrir el gestor d'UDFs

**Fat Client** (client d'escriptori):
1. Menú superior: **Tools** → **Customization Tools** → **User-Defined Fields — Management**.
2. S'obre una finestra amb l'arbre de categories.

**Web Client**:
1. Al menú lateral: **Tools** → **Customization Tools** → **User-Defined Fields — Management**.
2. Mateixa vista arbre.

## Pas 2 — Navegar fins a "Marketing Documents → Title"

A l'arbre expandeix:
```
Master Data
  ├─ Marketing Documents
  │   ├─ Title           ← aquí crearem els 3 UDFs
  │   ├─ Rows
  │   └─ ...
```

- **Title** = capçalera de qualsevol document comercial (Sales Orders,
  Purchase Orders, Invoices, etc.). Cada UDF que creem aquí queda visible
  a ORDR (Sales Order), OPOR (Purchase Order), OINV (Invoice), etc.
- Això és exactament el que volem — el UDF només ens interessa a Sales
  Orders, però haver-lo a tot Marketing Documents no fa cap mal (SAP el
  reserva a totes les taules però només l'omplirem a ORDR).

## Pas 3 — Crear `U_FCCalcular`

1. Selecciona **Title** a l'arbre.
2. Fes clic al botó **Add** (o menú Data → Add).
3. Omple el formulari:

| Camp | Valor |
|---|---|
| **Title** | `FCCalcular` |
| **Description** | `Calcular embalatge` |
| **Type** | `Alphanumeric` |
| **Length** | `1` |
| **Structure** | `Regular` (per defecte) |

4. **Set Valid Values for Field** (opcional però recomanat):
   - Marca "Valid Values from List" o similar.
   - Afegeix 2 valors:
     - Value = `S`, Description = `Sí (calcular)`
     - Value = `N`, Description = `No`
   - Set Default = `N`.
5. Fes clic a **Add** i confirma. SAP demanarà tancar totes les finestres
   Sales Order obertes (si n'hi ha).

## Pas 4 — Crear `U_FCEmbalatgeResum`

1. Botó **Add** de nou (o menú Data → Add).
2. Omple:

| Camp | Valor |
|---|---|
| **Title** | `FCEmbalatgeResum` |
| **Description** | `Embalatge — Resum` |
| **Type** | `Alphanumeric` |
| **Length** | `254` |
| **Structure** | `Regular` |

3. **Sense** Valid Values (és text lliure que el worker omplirà).
4. **Add** i confirma.

## Pas 5 — Crear `U_FCEmbalatgeEstat`

1. Botó **Add**.
2. Omple:

| Camp | Valor |
|---|---|
| **Title** | `FCEmbalatgeEstat` |
| **Description** | `Embalatge — Estat` |
| **Type** | `Alphanumeric` |
| **Length** | `30` |
| **Structure** | `Regular` |

3. **Valid Values** (recomanat per colorejat/filtre):
   - `CALCULAT` — Càlcul OK
   - `CALCULAT_AMB_AVISOS` — Càlcul amb avisos
   - `SOTA_MINIM` — Comanda sota mínim
   - `NO_CALCULABLE` — No calculable
   - `ERROR` — Error del pipeline
   - (deixa sense Default o posa buit)
4. **Add** i confirma.

## Pas 6 — Verificació via SQL

Un cop creats, confirma des de qualsevol client SQL (SSMS, DBeaver, etc.):

```sql
SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH
  FROM INFORMATION_SCHEMA.COLUMNS
 WHERE TABLE_NAME = 'ORDR'
   AND COLUMN_NAME IN ('U_FCCalcular', 'U_FCEmbalatgeResum', 'U_FCEmbalatgeEstat')
 ORDER BY COLUMN_NAME;
```

Ha de retornar **3 files**:

| COLUMN_NAME | DATA_TYPE | CHARACTER_MAXIMUM_LENGTH |
|---|---|---|
| U_FCCalcular | nvarchar | 1 |
| U_FCEmbalatgeEstat | nvarchar | 30 |
| U_FCEmbalatgeResum | nvarchar | 254 |

## Pas 7 — Verificació visual al formulari Sales Order

1. Obre qualsevol Comanda de venda a SAP.
2. Prem **Ctrl+U** (o menú View → **User-Defined Fields**) per mostrar el
   panel lateral dret amb els UDFs.
3. Hauries de veure els 3 camps nous:
   - **Calcular embalatge** (checkbox o llista Sí/No).
   - **Embalatge — Resum** (text llarg, buit inicialment).
   - **Embalatge — Estat** (llista d'estats, buit inicialment).

Si els veus, la creació és completa i el pipeline ja pot funcionar.

---

## Alternativa avançada: Service Layer REST

Si prefereixes automatitzar la creació via crida HTTP (útil per replicar
a TEST/PROD), pots usar el Service Layer:

```http
POST https://<sap-host>:50000/b1s/v2/UserFieldsMD
Content-Type: application/json

{
  "TableName": "ORDR",
  "Name": "FCCalcular",
  "Description": "Calcular embalatge",
  "Type": "db_Alpha",
  "Size": 1
}
```

Repeteix amb `FCEmbalatgeResum` (size 254) i `FCEmbalatgeEstat` (size 30).

**Requereix**: usuari SL amb permisos de modificació d'estructura, i login
previ (POST /Login) per obtenir la cookie B1SESSION.

---

## Un cop creats els UDFs

L'aplicació els detectarà automàticament:
- `obtenir_comandes_a_calcular(conn)` deixarà de retornar `[]` amb warning i començarà a llegir les comandes amb `U_FCCalcular='S'`.
- El worker (`run_sync.py` corrent com a servei NSSM) processarà cada
  comanda marcada i escriurà `U_FCEmbalatgeResum` + `U_FCEmbalatgeEstat`.

Per validar-ho al vol (sense esperar al worker):

```bash
# 1. Marca una comanda a SAP amb U_FCCalcular='S' i desa.
# 2. Executa una passada manual:
python run_sync.py --once --dry-run
# → hauria de mostrar 1 comanda "trobada" a l'output.

# 3. Executa la real (necessita credencials SL al .env):
python run_sync.py --once
# → hauria de fer un PATCH al Service Layer i omplir U_FCEmbalatgeResum/Estat.
# 4. Refresca la comanda a SAP i verifica els camps.
```

---

**Data creació guia**: 2026-07-28.
**Rellevant per**: Fase 2.6 (integració SAP) del projecte Motor Comandes.
