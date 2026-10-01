# El palet negociat d'un client no és determinista

**Estat:** obert, pendent de decisió de negoci.
**Trobat:** 1 d'octubre de 2026, migrant les lectures del motor a Service Layer.
**Afecta:** `consultes.obtenir_palet_client()` → el tipus de palet físic que rep un client.

## El problema

La consulta que decideix quin palet té negociat un client acaba així:

```sql
SELECT TOP 1 ...
FROM [@SEITARIFACAB] c
INNER JOIN [@SEITARIFADET] d ON d.DocEntry = c.DocEntry
WHERE c.U_SEICardCode = ? AND c.U_SEIActivo = 'Y' AND c.Canceled <> 'Y'
  AND UPPER(RTRIM(d.U_SEIItemName)) LIKE 'PALET%'
  AND (d.U_SEIFechaFin IS NULL OR d.U_SEIFechaFin >= GETDATE())
ORDER BY
    CASE WHEN ? IS NOT NULL AND RTRIM(c.U_SEIDireccion) = ? THEN 0 ELSE 1 END,
    c.DocEntry DESC
```

L'`ORDER BY` ordena **només per capçalera** (direcció i DocEntry). No hi ha cap
ordre sobre la **línia** de la tarifa. Per tant, quan una tarifa té més d'una
línia de palet, quina de les tres guanya no ho decideix la consulta: ho decideix
el pla d'execució de SQL Server.

El docstring de la funció diu «la primera línia amb ItemName que comença per
PALET», però «primera» no està definit enlloc de la consulta.

## Fins a quin punt passa

Mesurat contra `DB_FARIN_TEST` l'1-10-2026:

| | |
|---|---|
| Tarifes actives amb línies de palet | 429 |
| **Amb més d'una línia de palet** | **120** |
| Màxim de línies de palet en una tarifa | 3 |
| Clients amb palet negociat | 436 |
| **Clients on el resultat canviaria si es fes determinista** | **119 (27%)** |

Canvis més freqüents: `01030`↔`01110` (91 casos), `01030`→`01022` (9),
`01022`→`01110` (8).

### Exemple concret

Client `C301004`, tarifa `DocEntry 17427`:

| LineId | VisOrder | Article | Nom |
|---|---|---|---|
| 1 | 0 | `01060` | PALET FUSTA AMERICA 120x100 |
| 2 | 1 | `30000` | FARINA *(no és palet)* |
| 3 | 2 | `01000` | PALET PLASTIC EUROPEU 120X80 |
| 4 | 3 | `01030` | PALET FUSTA EUROPEU 120X80 |

La consulta actual retorna **`01000`** (LineId 3). Ni `LineId` ni `VisOrder`
expliquen aquesta tria: no és la primera ni la última.

## Per què importa més del que sembla

No és un problema que hagi creat la migració. **Ja hi és avui**: una
reconstrucció d'índexs, un canvi d'estadístiques o una actualització de SQL
Server poden fer que un client passi a rebre un altre tipus de palet sense que
ningú hagi tocat cap dada ni cap línia de codi. Simplement, ningú ho havia
mirat.

El que ha fet la migració és obligar a triar: qualsevol implementació que no
sigui SQL Server ha de decidir un ordre, i aleshores el canvi es fa visible de
cop per a 119 clients.

## Situació actual al codi

`obtenir_palet_client` **es queda llegint per SQL**. La implementació de Service
Layer existeix (`consultes_sl.palet_client`, agafa la primera línia per
`LineId`) però no està activada, i si algú posa
`SAP_BACKEND_OBTENIR_PALET_CLIENT=sl` al `.env` deixa un avís al log.

Les altres sis funcions del motor sí que estan migrades i donen resultat
idèntic.

## Opcions

1. **Netejar les dades a SAP** perquè cap tarifa tingui més d'una línia de
   palet. Soluciona la causa i deixa el codi determinista sol, sense cap canvi
   de comportament a decidir. Són 120 tarifes a revisar.
2. **Primera línia per `LineId`.** És el que ja diu el docstring. Determinista i
   gratis, però canvia el palet de 119 clients d'una tarda.
3. **Una regla de negoci explícita**, per exemple el preu (`U_SEIPrecio` és al
   detall de la tarifa). Determinista i defensable, però és una regla nova que
   fins ara no existia.

## Què cal preguntar

- Quan una tarifa llista diversos palets, és un error de dades o és
  intencionat? Si és intencionat, què vol dir?
- Dels 119 clients afectats, el palet que reben avui és el correcte o fa temps
  que és el que no toca?

## Com reproduir-ho

```bash
# Divergència mesurada sobre tots els clients
python scripts/paritat_motor.py --backend sl --detall

# El cas concret
python -c "
import consultes
conn = consultes.connectar()
print(consultes.obtenir_palet_client('C301004', None, conn=conn))
conn.close()"
```
