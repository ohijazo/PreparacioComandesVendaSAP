# Crear l'UDF `U_FCAfegit` a RDR1 (línies de comanda de venda)

Aquest UDF permet al motor d'embalatges **identificar les línies palet que
ha inserit ell mateix** i substituir-les netament quan l'operari torna a
clicar el botó "Calcular embalatges" (idempotència del recàlcul).

Sense aquest UDF, el mètode `SLClient.replace_marked_lines` no pot
distingir les línies afegides pel motor de les originals de l'operari, i el
recàlcul acabaria acumulant línies duplicades.

## Especificació

| Propietat | Valor |
|---|---|
| **Ubicació** | `Master Data → Marketing Documents → Rows` (no Title!) |
| **Title (nom)** | `FCAfegit` |
| **Descripció** | `Línia afegida per motor embalatges` |
| **Tipus** | Alphanumeric |
| **Longitud** | 1 |
| **Valid Values from List** | `S` = Sí, `N` = No |
| **Default** | `N` |

> **Molt important**: cal crear-lo a **Rows** (no a Title). L'UDF resultant
> apareix a la taula `RDR1` (línies) i al camp `U_FCAfegit`. Si per error
> es crea a Title, apareix a `ORDR` i no serveix per aquest ús.

## Passos al SAP Business One (Fat Client)

1. Assegura't que **cap altre usuari té oberta cap Comanda de Venda**
   (SAP tanca formularis al desar UDFs a taules Rows).
2. Menú: **Tools → Customization Tools → User-Defined Fields — Management**.
3. Expandeix l'arbre:
   ```
   Master Data
     └─ Marketing Documents
        ├─ Title    ← NO és aquí
        └─ Rows     ← AQUÍ
   ```
4. Selecciona **Rows** i clica **Add**.
5. Ompliu:

| Camp | Valor |
|---|---|
| Title | `FCAfegit` |
| Description | `Línia afegida per motor embalatges` |
| Type | `Alphanumeric` |
| Length | `1` |
| Structure | `Regular` |
| Set Valid Values for Field | (marcar) |

6. A la taula de "Valid Values" afegeix:

| Value | Description |
|---|---|
| `S` | Sí (afegida per motor) |
| `N` | No (línia normal) |

Marca `N` com a **Set Default**.

7. Clica **Add** i confirma. SAP tancarà els formularis oberts si cal.

## Verificació SQL

```sql
SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH
  FROM INFORMATION_SCHEMA.COLUMNS
 WHERE TABLE_NAME = 'RDR1'
   AND COLUMN_NAME = 'U_FCAfegit';
```

Ha de retornar:

| COLUMN_NAME | DATA_TYPE | CHARACTER_MAXIMUM_LENGTH |
|---|---|---|
| `U_FCAfegit` | `nvarchar` | 1 |

## Ús pel motor

Un cop existeix, l'endpoint `POST /api/afegir-palets/<doc_entry>`:

1. **Primer clic** — filtra línies amb `U_FCAfegit='S'` a la comanda
   (n'hi ha 0), afegeix N línies palet noves totes amb `U_FCAfegit='S'`.
2. **Segon clic (recàlcul)** — filtra les N línies existents amb
   `U_FCAfegit='S'` (les esborra), afegeix M línies noves també amb
   `U_FCAfegit='S'`. Les línies **originals de l'operari** amb
   `U_FCAfegit='N'` (o buit) queden intactes.

## Relació amb altres UDFs FC

Els 3 UDFs a `ORDR` (`U_FCCalcular`, `U_FCEmbalatgeResum`, `U_FCEmbalatgeEstat`)
són del **disseny anterior** (worker polling + resum textual). No s'utilitzen
al disseny actual (botó B1UP + línies físiques). Es queden creats per si un
dia es volen reutilitzar; no interfereixen.

Aquest UDF (`U_FCAfegit` a `RDR1`) és **específic** del disseny botó
B1UP i **imprescindible** perquè funcioni el recàlcul.

---

**Data creació guia**: 2026-07-28.
**Relacionat amb**: Fase 2 disseny botó B1UP — `docs/configuracio_b1up_boto_embalatge.md`.
