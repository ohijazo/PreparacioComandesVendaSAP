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

---

## L3 — B1UP Function Buttons: afegir línia a la FB existent, no crear-ne una nova

**Data**: 2026-07-29.
**Context**: intentàvem que aparegués el botó "Calcular embalatges" al
formulari **Comanda de venda (form type 139)** creant una nova Function
Button `FB-005`. El botó no apareixia mai al formulari.

### Causa

A B1UP, les **Function Buttons** es configuren com a **grup per form type**,
no com a entitats independents. El form 139 ja tenia `FB-004` amb la
funció existent "Enviar confirmació" (UF-033). Crear una nova `FB-005`
paral·lela per al mateix form fa que SAP no la mostri (només una FB per
form pren efecte, o l'ordre d'aparició és imprevisible).

### Solució

Obrir la **configuració FB-004 existent** i afegir una línia nova a la
graella de botons:

| # | Títol | Funció universal |
|---|---|---|
| 1 | Enviar confir... | UF-033 |
| 2 | (Búsqueda form) | — |
| 3 | **Calcular emba...** | **UF-038** (nou) |
| 4 | (Búsqueda form) | — |

Cada línia de la graella dins una FB és un botó separat al toolbar.

### Regla per al futur

**Abans de crear una nova Function Button (`FB-XXX`) a B1UP per a un
form type, comprovar si ja existeix una FB per aquell form** (menú
Boyum → Configurator → Function Buttons, filtrar per Form Type). Si
existeix, obrir-la i afegir una línia extra amb el títol + Funció
universal (UF-XXX) del nou botó. Només crear una FB nova si el form
type encara no en té cap.

### Nota adjacent

El diagnòstic previst (`scripts/diag_b1up_fb005.py`, comparació SQL de
les taules `@BOY_*`) no va ser necessari; el problema era de disseny B1UP,
no de dades corruptes. El script pot esborrar-se o conservar-se com a
plantilla de query sobre taules Boyum.

---

## L4 — Reciclatge in-place de línies palet per no acumular residus tancats

**Data**: 2026-07-29.
**Context**: L'endpoint `/api/afegir-palets/<doc_entry>` tancava les línies
palet velles (`LineStatus="bost_Close"`) i creava noves cada vegada.
Resultat: cada clic al botó "Calcular embalatges" acumulava residus grisos
a la graella del Sales Order — no es podien esborrar (limitació SL, veure
L2 G2.1) i visualment embrutaven el formulari.

### Estratègia in-place (implementada a `SLClient.replace_marked_lines`)

Abans de tancar+afegir, intentar **reciclar** la línia palet vella si té
mateix `ItemCode` que alguna nova:

- **Match per ItemCode** entre `open_marked` (palet obertes) i `new_lines`.
- Si coincideix → **PATCH in-place**: `{LineNum, ItemCode, Quantity, ...}`
  a la mateixa línia. Sense tancament, sense línia nova.
- Si no coincideix → cau al patró anterior: la palet vella es tanca
  (`bost_Close`) i la nova s'afegeix.

Cas habitual (mateixa comanda, l'usuari re-clica el botó sense canviar
articles): **0 residus grisos**. Cas rar (canvi de tipus de palet per
canvi de dades article): 1 residu gris per canvi.

### Detall crític del PATCH #2

L'update in-place (LineNum + camps nous) i les noves (sense LineNum) van
al **mateix PATCH** que els placeholders. Comprovat empíricament que això
NO trenca (a diferència de close + altres modificacions, que sí — G2.3).

Payload del PATCH #2:
```json
{"DocumentLines": [
    {"LineNum": 0},                              // placeholder (usuari)
    {"LineNum": 1, "ItemCode": "01030", "Quantity": 5, "U_FCAfegit": "S"},  // update
    {"ItemCode": "01050", "Quantity": 1, "U_FCAfegit": "S"}                 // afegir
]}
```

### Semàntica `stats` retornada

`{"removed": T, "updated": U, "added": A, "kept": K}`:
- `removed`: línies palet tancades (sense reciclatge possible).
- `updated`: línies palet reciclades in-place (millora principal).
- `added`: noves línies palet afegides.
- `kept`: línies no marcades (usuari + palet ja tancades preservades).

### Regla per al futur

**Si en algun altre endpoint cal sincronitzar una col·lecció de línies
d'una Order via SL, aplicar aquesta estratègia**:
1. GET línies actuals amb els camps clau (`ItemCode`, `LineStatus`, marker).
2. Emparellar per ItemCode → build de `to_update` + `to_add` + `to_close`.
3. PATCH #1 tancament pur (només si `to_close` no buit).
4. PATCH #2 amb placeholders + updates + noves.

Evita l'acumulació de línies tancades al document.

---

## L5 — B1UP "Código dinámico (.NET SDK)" — noms de paràmetres i refresh

**Data**: 2026-07-29.
**Context**: implementació de UF-038 "Calcular embalatges" com a codi C#
executat des del botó B1UP al form Sales Order. Van fer falta múltiples
iteracions per resoldre 3 gotchas.

### G5.1 — La plantilla B1UP no exposa `SBO_Application`

El codi C# de "Código dinámico" s'insereix dins una signatura fixa:
```csharp
public void DynamicCode(params object[] parameters) {
    SAPbobsCOM.Company company        = (SAPbobsCOM.Company)parameters[0];
    SAPbouiCOM.Application application = (SAPbouiCOM.Application)parameters[1];
    SAPbouiCOM.Form form               = (SAPbouiCOM.Form)parameters[2];
    // ... altres 3 params (eventForm, eventData, addonData)
    // AQUÍ va el teu codi
}
```

**No** existeix `SBO_Application` — cal usar `application` (paràmetre local).
**No** cal `SBO_Application.Forms.ActiveForm` — el `form` actiu ja és `form`.

### G5.2 — Obtenir DocEntry: DBDataSource, no Item UID

Per accedir a valors del form actiu, el patró estable és:
```csharp
string docEntry = form.DataSources.DBDataSources
    .Item("ORDR")
    .GetValue("DocEntry", 0)
    .Trim();
```

Depenent del UID de control (`form.Items.Item("8").Specific`) és fràgil
—canvia entre versions SAP i personalitzacions.

### G5.3 — Refresh del form: MenuID `1304` amb precondició `fm_OK_MODE`

**Provats i descartats**:
- `form.Refresh()` — no re-executa la SELECT del document.
- `application.SendKeys("^w")` — dispara Ctrl+W però a versions concretes
  Ctrl+W està assignat a una altra acció ("Cálculo de volumen y peso"
  a la instal·lació actual).
- `System.Windows.Forms.SendKeys.SendWait(...)` — requereix referència a
  `System.Windows.Forms.dll` que B1UP no carrega.
- `application.ActivateMenuItem("1288")` — provoca comportament raro
  (mostra només la primera línia).
- `application.ActivateMenuItem("1281")` (Find mode) + `SendKeys("{ENTER}")`
  — buida els camps i deixa el form com si s'entrés una nova comanda.
- `application.ActivateMenuItem("1290")` + `"1289"` (Next+Prev) — navega
  per DocEntry, no per DocNum: salta a comandes diferents.
- `application.ActivateMenuItem("1301")` — dona `-66000-75 "Cannot activate
  a disabled menu item"` en molts contexts.

**Solució validada** (funciona a l'entorn actual: SAP B1 v.2026.03 HF04):
```csharp
if (form.Mode != SAPbouiCOM.BoFormMode.fm_OK_MODE) {
    application.MessageBox("La comanda té canvis pendents. Desa-la abans.");
    return;
}
// ... POST HTTP ...
application.ActivateMenuItem("1304");   // Refresh Record
```

**Per què cal la precondició `fm_OK_MODE`**: `1304` només és clicable
quan el form està en mode View sense canvis pendents. Si l'usuari té
canvis a mig introduir, el MenuID queda deshabilitat i `ActivateMenuItem`
llança `Cannot activate a disabled menu item [66000-75]`.

### Regla per al futur

- Codi B1UP: `application` i `form` (paràmetres locals), MAI `SBO_Application`.
- Accés a valors del form actiu: `form.DataSources.DBDataSources.Item("<tabla>").GetValue(...)`.
- Refresh d'un document Sales Order/Purchase Order: `ActivateMenuItem("1304")`
  amb precondició `form.Mode == fm_OK_MODE`. Si no compleix, guiar
  l'usuari amb un MessageBox.
- El codi final està al repo a `docs/b1up_uf038_calcular_embalatges.cs`
  per si es perd la configuració B1UP.
