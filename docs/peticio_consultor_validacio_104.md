# Petició al consultor SAP — validació 104 (preu zero sense motiu)

**Data**: 2026-10-15

Al `SBO_SP_TransactionNotification` (BD `DB_FARIN_TEST`) hi ha la validació nova:

```sql
-- Impedir guardar una comanda si té articles amb preu 0 i no hi ha motiu informat
IF (@object_type = '17' AND @transaction_type IN ('A','U'))
...
    AND T1.Price=0 AND ISNULL(T1.U_SEIMotiuPreuZero,'')='') >0
    set @error=104
```

Us demanem dues coses:

1. **Valor vàlid nou** a `RDR1.U_SEIMotiuPreuZero`: `EMBALATGE` (descripció
   "EMBALATGE"). El motor d'embalatges l'informa a les línies de palet que
   insereix sense tarifa i a les BASE PALET.

2. **Ignorar les línies tancades** a la validació, afegint
   `AND T1.LineStatus='O'`. Ara mateix una línia tancada a preu 0 sense motiu
   (no es pot modificar) bloqueja per sempre qualsevol desat de la comanda,
   també des del client SAP. A test n'hi ha 12 comandes obertes afectades.

De pas: el missatge diu "preu **zeo**" (falta una r).
