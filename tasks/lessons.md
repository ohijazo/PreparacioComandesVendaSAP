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

---

## L2 — Gotchas del PATCH sobre `Orders` via Service Layer

**Data**: 2026-07-28.
**Context**: implementació endpoint `/api/afegir-palets/<doc_entry>` que fa
GET-modify-PATCH sobre `/Orders({N})/DocumentLines`.

Aquests gotchas els vam descobrir empíricament (SAP no els documenta bé) i
si no es coneixen fan perdre hores i poden **destruir dades de comandes**.

### G2.1 — `DELETE /Orders(N)/DocumentLines(K)` NO existeix

**Retorna**: `-5006 "The requested action is not supported for this object"`.
**Alternativa**: marcar la línia amb `LineStatus="bost_Close"` via PATCH.
Queda a `RDR1` però desapareix del formulari i no compta al workflow
comercial.

### G2.2 — `POST /Orders(N)/DocumentLines` (add subcollection) NO existeix

**Retorna**: `-1008 "Command Not Found"`.
**Alternativa**: veure G2.4 (afegir amb PATCH + placeholders).

### G2.3 — `Close + altres modificacions` al mateix PATCH → `-5002`

Missatge: `Document rows cannot be closed concurrently with the other
document modifications you have made [DocumentLines.LineStatus][line: N]`.

El PATCH que tanca una línia **NOMÉS** pot contenir `{LineNum, LineStatus}`.
Qualsevol altre camp (fins i tot un UDF per netejar un marcador
d'idempotència) es considera "altra modificació" i trenca.

**Patró correcte**: separar en 2 PATCH:
1. PATCH només-close (només `LineNum + LineStatus="bost_Close"` per cada línia).
2. PATCH d'update/add.

### G2.4 — `DocumentLines` sense placeholders → sobreescriu línies existents (DESTRUCTIU)

Si al PATCH #2 envies només les línies noves sense `LineNum`, SAP les
matcha per **posició** amb les línies existents del document i sobreescriu.
Ja ens va **eliminar la línia `30150 FARINA Nº1`** de la comanda 92 durant
els tests — vam poder-la recuperar de l'històric `ADO1`.

**Patró correcte**: enviar un placeholder `{LineNum: X}` per **CADA
línia existent** (obertes I tancades) + les noves sense `LineNum`. SAP
preserva les existents intactes i afegeix les noves al final.

```python
body = {"DocumentLines":
    [{"LineNum": l["LineNum"]} for l in current_lines_no_closing_ara]
    + [nova_sense_linenum for nova in new_lines]
}
```

Si ometem placeholders d'algunes línies existents (encara que estiguin
tancades!) SAP reorganitza el document destructivament.

### G2.5 — UDFs amb Valid Values no accepten `""` (cadena buida)

Si crees un UDF amb Valid Values (S/N, Y/N, etc.), passar `""` retorna
`-1004 "'' is not a valid value for property 'X'"`. Cal passar sempre un
dels valors vàlids. Al nostre cas amb `U_FCAfegit` (S/N), el reset del
marker s'ometia perquè el filtre ja usa `LineStatus == bost_Close` per
saber quines ignorar.

### G2.6 — Recuperació de dades: `ADO1` conserva històric complet

Cada canvi a una Order genera una entrada nova a `ADOC` + versió completa
de línies a `ADO1` (indexat per `LogInstanc`). Si algun test destrueix
dades, es poden reconstruir del `Log1` (versió inicial).

Script útil: `scripts/recuperar_comanda_92.py` (plantilla per veure
històric d'una comanda concreta).

### Implementació

`SLClient.replace_marked_lines` (`sap_service_layer.py`) implementa la
lògica completa amb tots aquests gotchas incorporats. Tests amb `responses`
mock a `tests/test_afegir_palets.py`.

### Regla per al futur

**Abans d'inventar patró propi per PATCH sobre `Orders`, revisar aquests
gotchas.** El SL té molt de comportament no documentat que només es
descobreix trencant coses.
