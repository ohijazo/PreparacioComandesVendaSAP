# Lliçons apreses — projecte Motor Comandes Venda SAP

Registre de patrons/errors que hem resolt, perquè futures sessions Claude
puguin evitar-los o resoldre'ls més ràpid.

---

## L1 — Service Layer SAP B1: rebuig `-1116` sobre Orders sense causa aparent

**Data**: 2026-07-28.
**Context**: Fase 2.6 (integració SAP), primeres proves de `PATCH /Orders({DocEntry})`.

### Símptomes

Qualsevol `PATCH` via SL sobre `Orders(N)` retornava HTTP 400 amb:
```json
{"error":{"code":-1116,"message":{"value":"Could not commit transaction: Error -1 detected during transaction"}}}
```

- Fallava fins i tot amb camps estàndard (`Comments`).
- Fallava sobre 5+ Orders diferents (100% failure global).
- El client SAP d'escriptori **sí** podia editar les mateixes comandes.
- `PATCH /BusinessPartners('C001024')` amb `Notes` **funcionava** (204).
- Login SL i GET Orders funcionaven perfectament.
- Idèntic amb v1 i v2, amb i sense header `Prefer: return=minimal`.

### Diagnòstic estèril

Vam gastar hores buscant el culpable a la BD:
- SBO_SP_TransactionNotification: només crida SEIDOR SII/SII_PERSONAL — cap toca Order (object 17).
- Cap trigger a `ORDR`, `RDR1`, `OCRD`.
- SP `SEI_VALIDACIONES_GAP001` existeix però està **comentada** al TN.
- Cap add-on Java al filesystem del SL.
- Cap script SL SEIDOR visible al FS.

### Causa real

**Estat corrupte del backend Service Layer** (cache/procés). La BD estava neta;
el problema era pura acumulació al procés SL.

### Solució

Reiniciar els 4 serveis SL al servidor:
```powershell
"b1s50000", "b1s50001", "b1s50002", "B1ServerTools64ServiceLayerController" |
  ForEach-Object { Restart-Service -Name $_ -Force }
```

Després del reinici, tots els PATCH van passar amb 204 al primer intent.

### Regla per al futur

**Si el SL rebutja PATCH/POST amb `-1116` o codis genèrics sense causa
identificable a la BD, ABANS de cavar més fons, reinicia el SL.** És el
diagnòstic més barat (5 min) i històricament el més probable en aquesta
instal·lació.

Ordre de diagnòstic per `-1116`:
1. **Reiniciar SL** (5 min) — si passa, era cache. Fi.
2. Comprovar `SBO_SP_TransactionNotification` (SP + branques per object_type).
3. Comprovar triggers a la taula afectada.
4. Comprovar add-ons Java al SL (`ServiceLayer\bin\*.jar`).
5. Contactar SEIDOR.

### Endpoint `POST /Orders({N})/Update`

Nota adjacent: aquest endpoint retorna `-1029 "Field cannot be updated"` sempre
per als UDFs `U_FC*`. **No és un bug, és disseny SAP** — aquest endpoint no
admet UDFs. Usar sempre PATCH per escriure UDFs a `Orders`.

### Scripts de diagnòstic conservats

A `scripts/` deixem els scripts que vam crear per debug, per si mai torna a
passar (útils com a plantilla):
- `test_patch_isolat.py` — bateria de PATCH sobre camps aïllats.
- `test_patch_multi_orders.py` — PATCH sobre 5 orders random (global vs específic).
- `check_ordr_triggers.py` — triggers sobre ORDR/RDR1/OCRD.
- `check_sii_personal.py` — object_types que gestionen les SP SEIDOR.
- `find_gap001_callers.py` — cerca callers de GAP001*.
- `find_order_interceptors.py` — Approval Templates / User Alerts / FS sobre ORDR.
- `enum_sl_scripts.py` — enumeració de scripts SL registrats via API.
