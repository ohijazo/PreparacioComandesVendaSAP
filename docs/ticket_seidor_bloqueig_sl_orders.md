# Ticket a SEIDOR — Service Layer bloqueja PATCH sobre Sales Orders

**Data**: 2026-07-28
**Sistema**: SAP Business One 10.0, BD `DB_FARINERA_TEST`
**Servidor**: `192.168.11.238` (Windows Server 2025)
**Service Layer**: `https://192.168.11.238:50000/b1s/v1` (i `/v2`)
**Usuari SL**: `OHijazo` (administrador)

## Símptoma

Qualsevol `PATCH` via Service Layer sobre `/Orders({DocEntry})` — encara que
sigui un camp estàndard com `Comments` — retorna **HTTP 400** amb:

```json
{
  "error": {
    "code": -1116,
    "message": {
      "lang": "en-us",
      "value": "Could not commit transaction: Error -1 detected during transaction"
    }
  }
}
```

L'`odata.etag` és correcte, la sessió és vàlida, els permisos són d'administrador.

## Comprovacions ja realitzades

1. **`PATCH` sobre `BusinessPartners('C001024')` amb `Notes`**: ✅ **HTTP 204 OK**.
   → El SL i les credencials **funcionen**; el problema és específic d'Orders.

2. **`GET /Orders(126)?$select=DocEntry,DocNum`**: ✅ HTTP 200 (lectura OK).

3. **Provat sobre 5 Orders diferents** (dates, clients, DocEntry variats):
   totes fallen amb el mateix `-1116`. **Problema global d'Orders**, no
   específic d'una comanda.

4. **Provat amb `Prefer: return=minimal`** i sense: mateix error.

5. **Provat amb SL v1 i v2**: mateix error.

6. **`POST /Orders(N)/Update`** (endpoint alternatiu): falla amb `-1029
   "Field cannot be updated"`.

7. **Al client SAP d'escriptori** el mateix usuari **SÍ pot editar
   Comments** de la mateixa comanda sense error.

## Anàlisi de la BD

Buscat exhaustivament què podria interceptar Orders sense èxit:

- **`SBO_SP_TransactionNotification`** té només 2 crides actives:
  `SEI_VALIDACIONES_SII` i `SEI_VALIDACIONES_SII_PERSONAL`. Les línies GAP001
  personalitzades estan **comentades**.
- **`SEI_VALIDACIONES_SII`** (74100 chars): gestiona object_types
  `{2, 13, 14, 18, 19, 30, 203, 204}` — **no** toca 17 (Order).
- **`SEI_VALIDACIONES_SII_PERSONAL`** (3319 chars): gestiona `{13, 14, 18,
  19, 30, 203}` — **no** toca 17 (Order).
- **Triggers a taula**: 0 triggers sobre `ORDR`, `RDR1`, `OCRD`.
- **Approval Procedures**: no s'ha trobat cap actiu per object 17.
- **`SEI_VALIDACIONES_GAP001`** existeix però **ningú la crida** (comentada al TN).

## Hipòtesi

El bloqueig es genera al **backend C++ del Service Layer** (component `B1S`),
probablement per algun **add-on Java o extensió SEIDOR carregada al SL** que
intercepta específicament les operacions Update sobre Sales Orders. Aquest
tipus d'add-on és **invisible via consultes SQL**.

## Preguntes concretes per SEIDOR

1. **Hi ha algun add-on Java o extensió SEIDOR carregada al Service Layer**
   d'aquesta instal·lació que intercepti operacions sobre `Orders`?
2. **Com podem accedir al log del backend SL** (component C++, no Apache)
   per veure el detall exacte del rebuig? Al directori `logs\` de
   `ServiceLayer` només hi ha logs d'Apache que no capturen aquest error.
3. **Hi ha configuració a `SLD-config.json` o similar** que hàgim d'ajustar
   per permetre updates a Orders via SL?
4. **Existeix documentació** de les personalitzacions SEIDOR aplicades a
   aquesta BD (esp. les que afecten Sales Orders o el DI-API/SL)?

## Casos que necessitem desbloquejar

Estem integrant un motor Python de càlcul d'embalatges dins SAP. Necessitem
poder fer `PATCH` a `/Orders({N})` per escriure 3 UDFs propis:
- `U_FCCalcular` (flag S/N)
- `U_FCEmbalatgeResum` (text resum)
- `U_FCEmbalatgeEstat` (estat)

Aquests UDFs ja estan creats correctament (verificat a
`INFORMATION_SCHEMA.COLUMNS`).

## Contacte

Oscar Hijazo — Agrienergia.
Adjunto scripts de diagnòstic si són útils.
