# Validació variant SAP — Fase 1

Data: 2026-07-23
Executor: Claude Opus 4.7 (sessió d'Oscar Hijazo)
Pla vinculat: `C:\Users\ohijazo.AGRIENERGIA\.claude\plans\la-idea-era-que-partitioned-rabin.md`

## Resum executiu

| Pas | Descripció | Estat |
|---|---|---|
| 1.1 | Preflight configuració | ✅ OK |
| 1.2 | pytest tests/ | ✅ OK (71/71) |
| 1.3 | Smoke test connexió SAP | ✅ OK (~160 ms) |
| 1.4 | Endpoints Flask | ✅ OK |
| 1.5 | Càlcul 14 comandes reals | ✅ OK (post-fix bug) |
| 1.6 | Matriu UDFs presents/NULL/absents | ⚠ **Buit crític** |
| 1.7 | Comparació Kais vs SAP | 🟡 Requereix acció usuari |
| 1.8 | Aquest report | ✅ OK |
| **1.9** | **Fase 1.5 — Bug Kais + activació RF4/RF6 a SAP** | **✅ Tancada 2026-07-23** |

**Bug crític trobat i arreglat**: deadlock del semàfor pyodbc a `obtenir_palet_client`. Ara la variant SAP calcula correctament totes les comandes provades.

**Bloquejadors per Fase 2**: manquen UDFs a SAP (`dimensio_especial`, `sac_25_especial`, `comanda_minima_produccio`). RF13 ja resolt via `_bootstrap.py`.

---

## 1.1 Preflight configuració — ✅ OK

- `.env` complet: `SAP_SQL_SERVER=AE01SAPSQL.Agrienergia.local`, `SAP_SQL_DATABASE=DB_FARINERA_TEST`, `SAP_SQL_USER=sa`, `KAIS_APP_PATH=P:\preparacioComandesVenda`, `PORT=5002`.
- ODBC Driver 18 for SQL Server instal·lat (32 + 64-bit).
- Python 3.13.14, virtualenv operatiu.

## 1.2 Tests unitaris — ✅ OK

```
71 passed in 2.65s
```

Re-executats després del fix del bug — segueixen passant.

## 1.3 Smoke test connexió SAP — ✅ OK

Query `SELECT TOP 5 FROM ORDR WHERE DocStatus='O'` retorna 5 registres, comptador total = 80 comandes obertes, temps 160 ms. Semàfor pyodbc funciona correctament per queries aïllades.

## 1.4 Endpoints Flask — ✅ OK

- `GET /api/ultimes-comandes` → 77 comandes actives (de 80 obertes).
- `GET /api/comandes-check` → `{"fingerprint": -894441211, "ok": true, "total": 80}`.
- `GET /api/magatzems` → 4 magatzems.
- `GET /` → HTML 200.

## 1.5 Càlcul de comandes reals — ✅ OK (post-fix)

### 🐛 Bug trobat: deadlock del semàfor pyodbc

**Símptoma**: qualsevol comanda que arribi a `_resolver_tipus_palet` (motor.py:260) es queda penjada indefinidament.

**Causa arrel**:
- `motor.calcular_embalatges` obre una connexió pyodbc (`conn = connectar()`).
- El motor crida `_resolver_tipus_palet`, que crida `obtenir_palet_client(cli_codi, adr_codi)` **sense passar-hi `conn`**.
- `obtenir_palet_client` a `consultes.py:602` obre una **segona** connexió pyodbc (`conn = connectar()`).
- El semàfor `_conn_semaphore` és de mida **1** → la segona `connectar()` espera indefinidament que el motor alliberi la primera → **deadlock permanent**.

Els tests unitaris NO detectaven el bug perquè mockejen les funcions de `consultes.py` (no toquen la BD).

Les 3 primeres comandes del batch inicial (`26600028`, `26600052`, `26600112`) van OK perquè:
- No arriben a `_resolver_tipus_palet` (RF1/RF2 STOP, o palet ja resolt per RF7 directament).

La comanda `26600093` (2400 sacs S25, direcció amb `preval=True`, sxb=4, max=24) va ser la primera que va disparar el deadlock.

**Fix aplicat** (2 canvis mínims):

- `consultes.py:602`: signatura de `obtenir_palet_client` accepta `conn: pyodbc.Connection | None = None`. Si es passa, es reutilitza (no obre semàfor). Si no, es manté el comportament anterior (compatibilitat).
- `motor.py:260`: la crida passa `conn=conn`.

**Verificació post-fix**:
- `pytest tests/` → 71/71 OK.
- Batch de 14 comandes → 14/14 OK. Temps màxim per comanda: 0.20 s.

### Resultats del batch (14 comandes)

| Ser/Num | Descrip | Estat | Lin | Palets | Sacs |
|---|---|---|---|---|---|
| 268/26600028 | Simple 1 art, MANUAL | CALCULAT | 1 | 2 | 60 |
| 268/26600052 | 1 sac, MANUAL | **SOTA_MINIM** | 1 | 1 | 1 |
| 268/26600112 | 20 kg GRA | **NO_CALCULABLE** | 1 | 0 | 0 |
| 268/26600093 | 2400 sacs PALET (bug trigger) | CALCULAT | 3 | 100 | 2400 |
| 268/26600094 | 6000 sacs + 1 estoc | CALCULAT | 2 | 134 | 6000 |
| 268/26600075 | 2000 sacs + 1 GRA | CALCULAT | 3 | 45 | 2000 |
| 268/26600092 | 7075 sacs + 3 estoc + 1 cola | CALCULAT | 5 | 189 | 7075 |
| 268/26600090 | 65 sacs, 2 estoc, cola, S05/S10 | CALCULAT | 2 | 2 | 65 |
| 268/26600078 | 15 art, 1935 sacs (RF14 activada) | CALCULAT | 15 | 46 | 1935 |
| 268/26600071 | 7 art, 3035 sacs | CALCULAT | 7 | 84 | 3035 |
| 268/26600124 | 10 sacs + 1 GRA | **SOTA_MINIM** | 2 | 1 | 10 |
| 268/26600038 | 60 sacs simple | CALCULAT | 1 | 2 | 60 |
| 268/26600064 | 6 art, 320 sacs | CALCULAT | 6 | 8 | 320 |
| 268/26600043 | 2000 sacs mono | CALCULAT | 1 | 45 | 2000 |

**Regles activades observades**: RF1, RF2, RF3, RF4, RF5, RF6, RF7, RF8, RF9, RF10, RF11, RF12, RF14. **RF13 mai** (cap comanda amb el CardCode del override).

**Sample palet correcte** (26600093, direcció preval=True, max=24):
```
P01 tipus=01000 max=24 base=4 total=24 [NB]: 40450×24
P02 tipus=01000 max=24 base=4 total=24 [NB]: 40450×24
... (100 palets amb 24 sacs cadascun)
```

Traçabilitat completa a `tasks/_test_direct_output.json` (JSON de 516 KB amb els 14 resultats sencers).

### ⚠ Nota operativa complementària

Les proves inicials amb HTTP a Flask van penjar el servidor de manera intermitent (peticions successives de batch amb timeout > 60s). Amb el fix del deadlock aquest problema s'ha eliminat (el motor Flask no encavalca connexions ara). No obstant, convindria que la Fase 2 (worker de sync) obri/tanqui la connexió estrictament per càlcul, per no acumular contenció.

## 1.6 Matriu UDFs — ⚠ Buit crític

### UDFs OITM (articles)

| Camp del motor | Camp SAP | Present | Amb valor | Total | Estat |
|---|---|---|---|---|---|
| `uxc` | `U_SEIUnitatsPalet` | ✅ | 658 | 2027 | OK |
| `cantidadapilable` | `U_SEIUnitatsApilables` | ✅ | 58 | 2027 | OK |
| `palet_producte_estoc` | `U_SEIPaletProd` | ✅ | 88 | 2027 | OK |
| `sac_colagne_normal` | derivat de `U_SEIFamCialCat='MOULIN DE COLAGNE'` | ⚠ | 40 | 2027 | Proxy (no UDF explícit) |
| `dimensio_especial` | **`OITM.QryGroup2`** (standard SAP) | ✅ | 21 | 2027 | **Utilitzable** — descobert via VBA .bas 2026-07-23 |
| `sac_25_especial` | **`OITM.QryGroup3`** (standard SAP) | ⚠ | **0** | 2027 | Camp existeix però buit — cal repoblar amb dades Kais |
| `comanda_minima_produccio` | *(cap adequat)* | ❌ | — | — | `MinOrdrQty` és MOQ de compra, no serveix. Cal UDF nou (p.ex. `U_SEIMinKgProduccio`, int) |

**Descobriment 2026-07-23 (via anàlisi de `P:\VBA\OITM\Módulo1.bas` i template `OITM - Items1 AE.xlsx`)**:
- Les columnes BP.xlsx `ED`, `EE`, `EF` corresponen a `QryGroup2`, `QryGroup3`, `QryGroup4` (Query Groups natius SAP), NO a UDFs.
- Mapatge InfoAnex Kais → BP.xlsx → SAP:
  - InfoAnex `ARTICE_ESP` → BP.xlsx `ED` → `OITM.QryGroup2` (Y/N) = `dimensio_especial`.
  - InfoAnex `SAC__ESPEC` → BP.xlsx `EE` → `OITM.QryGroup3` (Y/N) = `sac_25_especial`.
  - InfoAnex `ES_PALET` → BP.xlsx `EC` → `OITM.QryGroup1` (Y/N) = flag "és un palet" (7 articles marcats).

Fallback actual a `consultes.py:461-463`: `comanda_minima_produccio=None`, `dimensio_especial=False`, `sac_25_especial=False`. RF3, RF4 i RF6 romanen inactives fins que s'afegeixi la lectura de `QryGroup2`, `QryGroup3` i (per RF3) es creï un UDF nou.

**UDFs U_SEI\* addicionals a OITM (no usats pel motor)**: `U_SEICadLot`, `U_SEIFamCialCast`, `U_SEIObserCast`, `U_SEIObserCat`, `U_SEIObserTec`, `U_SEISubFamCialCast`, `U_SEISubFamCialCat`. Cap útil per RF3.

### UDFs CRD1 (direccions client)

| UDF | Total dir. | Amb valor | Cobertura |
|---|---|---|---|
| `U_SEITIPOD` (tipus_descarrega) | 12 445 | 12 442 | ✅ ≈100% |
| `U_SEIPREVAL` (preval_direccio) | 12 445 | 9 834 | ✅ ≈79% |
| `U_SEISACOSB` (sacs_x_base) | 12 445 | 76 | ⚠ 0.6% |
| `U_SEIMAXSP` (max_sacs) | 12 445 | 251 | ⚠ 2% |
| `U_SEIPEDIDOM` (min_ped) | 12 445 | 250 | ⚠ 2% |

**Per les 80 comandes obertes analitzades:**
- `U_SEIPREVAL`: 78/80.
- `U_SEITIPOD`: 80/80 (però 32 amb valor `-` = no definit).
- `U_SEIMAXSP`: 18/80.
- `U_SEISACOSB`: **7/80**.
- `U_SEIPEDIDOM`: 6/80.
- Sense correspondència a CRD1 (JOIN NULL): 2/80.

Distribució `U_SEITIPOD` a comandes obertes: 32 `-` · 28 `P` (PALET) · 18 `M` (MANUAL).

**Impacte**: gran majoria de comandes es calculen amb defaults del motor perquè la direcció no defineix `sacs_x_base`/`max_sacs`. Funcional però indica que la migració de valors des de Kais està incompleta.

### UDFs ORDR

Cap dels UDFs esperats per la Fase 2 (`U_SEIEmbalatgeResum`, `U_SEIEmbalatgeEstat`) existeix — s'han de crear.

### UDTs @SEI* existents

38 UDTs `@SEI*` ja instal·lades. **Cap** anomenada `@SEIEMBALATGE*`. Nomenclatura lliure per crear les de la Fase 2.

## 1.7 Comparació Kais vs SAP — 🟡 Requereix acció usuari

**No executable des d'aquesta sessió**. Cal cooperació de l'Oscar per:
- Identificar 3-5 comandes que existeixin equivalentment a les dues BD (Kais + SAP), o
- Validar visualment els resultats SAP de la secció 1.5 amb criteri de negoci.

**Nota tècnica sobre RF13**: els codis de client SAP (`C201119`, `C221469`, ...) semblen diferents dels codis Kais. L'override RF13 (`OVERRIDES_PALET_CLIENT`) està codificat amb `00301614`, probablement codi Kais. **RF13 no s'activarà mai a SAP fins que es traduexi el codi client al format SAP corresponent** (o es facin overrides amb tots dos formats).

## 1.8 Recomanació final

### ✅ Anar a Fase 2? **SÍ, amb 3 condicions prèvies:**

1. **Bloquejant per RF3/RF4/RF6** (revisat 2026-07-23 post-anàlisi VBA):
   - **RF4** (`dimensio_especial`): ✅ NO cal UDF nou. Usar `OITM.QryGroup2` (21 articles ja marcats). Cal afegir lectura a `consultes.py:_row_to_linia`.
   - **RF6** (`sac_25_especial`): ⚠ `OITM.QryGroup3` existeix però buit. Cal repoblar amb dades Kais (executar/adaptar macro VBA existent) i afegir lectura a `consultes.py`.
   - **RF3** (`comanda_minima_produccio`): ❌ Sí que cal crear un UDF nou (ex. `U_SEIMinKgProduccio`, int) — no hi ha camp SAP equivalent. `MinOrdrQty` NO serveix (és MOQ de compra a proveïdor, no comanda mínima Kais).

2. ~~**Bloquejant per RF13**~~ **✅ Resolt 2026-07-23**: mapping confirmat — codis Kais 8 dígits `00301614` → SAP 6 dígits `C301614` (`ACID CAFE BERLIN GMBH`). Fix aplicat a `_bootstrap.py`: nova funció `_apply_sap_overrides()` afegeix dinàmicament les entrades SAP a `regles.OVERRIDES_PALET_CLIENT` sense tocar `regles.py` (fitxer compartit amb Kais). Tests 71/71 OK.

3. **Nota per la Fase 2**: assegurar que el worker de sync respecti l'aïllament de connexions pyodbc (obrir → calcular → tancar → escriure via Service Layer) per no repetir contenció.

### 🚧 Recomanacions no bloquejants

- Repoblar `U_SEISACOSB`/`U_SEIMAXSP`/`U_SEIPEDIDOM` a `CRD1` per les direccions actives. Sense això, gran part de les comandes es calculen amb defaults.
- Considerar un UDF explícit `U_SEISacColagne` (Y/N) a OITM per no dependre del text lliure de `U_SEIFamCialCat = 'MOULIN DE COLAGNE'`.
- Netejar els fitxers temporals de la validació: `tasks/_scan_*.py`, `tasks/_test_*.py`, `tasks/_test_*.log`, `tasks/_test_direct_output.json` (516 KB — no committar).

### 🎯 Fixes aplicats (canvis a codi existent, no committats)

1. **Deadlock semàfor pyodbc**:
   - `consultes.py:602`: `obtenir_palet_client` accepta `conn=None` opcional.
   - `motor.py:260`: passa `conn=conn` a la crida.

2. **RF13 mapatge codi client Kais → SAP**:
   - `_bootstrap.py`: nova funció `_apply_sap_overrides()` afegeix dinàmicament `('C301614', '40150')` a `regles.OVERRIDES_PALET_CLIENT` (mantenint també l'original `('00301614', '40150')`). Ampliable amb més entrades al diccionari `kais_to_sap` sense tocar `regles.py`.

**Verificació**: 71/71 tests OK amb ambdós fixes. Càlcul de 14 comandes reals: 14/14 OK en <0.20s cadascuna.

**Recomanació**: fer commit dels dos fixes abans de moure's a Fase 2. Missatge suggerit:
```
fix: deadlock pyodbc + mapatge codis client Kais→SAP

1. Deadlock del semàfor pyodbc a obtenir_palet_client: el motor
   mantenia una conn oberta i obtenir_palet_client n'obria una segona
   → semàfor de 1 conn causava deadlock permanent. Ara la funció
   accepta `conn=None` opcional; si es passa, es reutilitza.

2. Mapatge de codis client per RF13: els codis Kais (00301614) no
   coincideixen amb SAP (C301614). Afegit _apply_sap_overrides() a
   _bootstrap.py que injecta els equivalents SAP a
   regles.OVERRIDES_PALET_CLIENT sense tocar regles.py (compartit).

Detectat validant càlculs contra BD SAP real (comanda 268/26600093).
```

---

## §1.9 Fase 1.5 — Bug de Kais i activació de RF4/RF6 a SAP (2026-07-23)

### Descobriment del bug de Kais

Analitzant per què "faltaven" 3 UDFs a SAP, es va detectar un bug latent a la variant Kais:

- `P:\preparacioComandesVenda\consultes.py:200-202` fa `WHERE INF_CONCEPTO IN ('ARTICE_ESPECIAL', 'SAC_25_ESPECIAL', 'ARTICLE_ESPECIFIC', 'APROVISIONAMENT', 'SAC_COLAGNE_ NORMAL')`.
- Però a la BD Kais **no existeixen** `ARTICE_ESPECIAL` ni `ARTICLE_ESPECIFIC`. Els noms reals són `DIMENSIO_ESPECIAL` (títol `ARTICE_ESP_7FJ0KZTDV`, 21 articles amb dades) i `COMANDA MÍNIMA PRODUCCIÓ` (títol `ARTICLE_ES_7FJ0L1ULT`, 32 articles amb kg 500-1000).
- Conseqüència: `titols["DIMENSIO_ESPECIAL"]` i `titols["ARTICLE_ESPECIFIC"]` mai s'assignen → **RF3 (comanda mínima producció) i RF4 (dimensió especial) mai s'apliquen a Kais**.

Notablement, l'import massiu Kais → SAP via `P:\VBA\OITM\Módulo1.bas` cerca per **INF_TITULO** (començant per `ARTICE_ESP`), NO per `INF_CONCEPTO` — per això va migrar correctament els 21 articles de dimensió especial a `OITM.QryGroup2` a SAP, malgrat el motor Kais no els llegís.

### Estat real de RF3, RF4, RF6

| Regla | Kais | SAP | Dades disponibles |
|---|---|---|---|
| RF3 (`comanda_minima_produccio`) | ❌ Bug | ❌ | 32 articles a Kais (kg 500-1000). No hi ha camp SAP. |
| RF4 (`dimensio_especial`) | ❌ Bug | ✅ `OITM.QryGroup2` (21 articles) | Migrat pel VBA `.bas` |
| RF6 (`sac_25_especial`) | ✅ Funciona | ⚠ `OITM.QryGroup3` **buit** | 13 articles a Kais pendents de migrar |

### Decisions preses (Oscar 2026-07-23)

- **RF3**: **NO activar** a SAP. Mantenir com Kais actual. No es crea UDF ni es migra res. La regla queda inactiva en ambdues variants (comportament actual d'operativa que ja funciona).
- **RF4**: **Activar** a SAP. Les dades ja hi són. Codi Python modificat per llegir `QryGroup2`.
- **RF6**: **Activar** a SAP (pendent migració de 13 articles al `QryGroup3`, fora d'aquesta app). Codi Python ja llegeix `QryGroup3`, però romandrà sempre `False` fins que el consultor SAP faci la migració.

### Canvis aplicats a codi (variant SAP)

`P:\preparacioComandesVendaSAP\consultes.py`:

- `_LINIES_SELECT`: afegides 2 columnes `i.QryGroup2 AS dimensio_especial_flag`, `i.QryGroup3 AS sac_25_especial_flag`.
- `_row_to_linia`: `dimensio_especial=(r.dimensio_especial_flag == 'Y')`, `sac_25_especial=(r.sac_25_especial_flag == 'Y')`.
- `comanda_minima_produccio=None` es queda igual (RF3 desactivada).
- Comentaris afegits per explicar el context.

### Verificació

- **Tests unitaris**: 71/71 OK (els tests mockejen les dades).
- **Comandes reals amb articles QG2='Y'**: es van triar 3 comandes obertes que inclouen articles amb dimensió especial:
  - `268/26600116` (SEMOLA FINA): CALCULAT, 1 palet.
  - `268/26600081` (SEGO): CALCULAT, 9 palets.
  - `268/26600078` (SEMOLA FINA + ESPELTA BLANCA + T80): **canvi de 46 → 45 palets** respecte Fase 1 — RF4 aplicada correctament a articles amb dim_esp=True.
- **`sac_25_especial`**: sempre False actualment (QryGroup3 buit). Es reactivarà automàticament tan bon punt el consultor SAP migri les 13 files.

### Query SQL per migració de RF6 (per al consultor SAP)

Llista d'articles a marcar amb `OITM.QryGroup3='Y'` a SAP (font: Kais):

```sql
-- Executar contra la BD Kais (vkais\kais / GWSV_AGRI):
SELECT ia.art_codi
FROM INF_ARTICULO ia WITH (NOLOCK)
WHERE ia.INF_TITULO = 'SAC__ESPEC_7FJ0L0CG3'
  AND RTRIM(ISNULL(ia.INF_VALOR,'')) = 'SI'
ORDER BY ia.art_codi
-- (13 files esperades)
```

Els codis d'article a Kais coincideixen amb `OITM.ItemCode` a SAP (mateix codi numèric, sense prefix). Actualitzar `UPDATE OITM SET QryGroup3='Y' WHERE ItemCode IN (...)` a la BD SAP (o millor: adaptar el VBA `Módulo1.bas` que ja té la lògica).

### Observació sobre el bug de Kais

El bug latent a la variant Kais (`consultes.py:200-202`) es **coneix però NO es corregeix** des d'aquest projecte per la restricció explícita de no tocar `P:\preparacioComandesVenda`. Convindria comunicar-lo a l'equip que manté Kais per si volen corregir-lo (canviar `'ARTICE_ESPECIAL'` → `'DIMENSIO_ESPECIAL'` i `'ARTICLE_ESPECIFIC'` → `'COMANDA MÍNIMA PRODUCCIÓ'`).

---

## §1.10 Fase 1.6 — Bug al VBA `Módulo1.bas` (2026-07-23)

### Descoberta

Investigant per què `QryGroup3` (Sac 25 Especial) i `QryGroup4` (Sac Colagne Especial) tenien 0 articles marcats a SAP (malgrat que a Kais hi ha 13 i 41 articles respectivament amb valor SI), es va comprovar que:

1. El **xlsm mateix** (`P:\VBA\OITM\OITM - Items1.xlsm`, fulla BP) també té 0 articles amb `tYES` a les columnes EE i EF. Vol dir que el problema no era la pujada DT sinó la **generació del xlsm per la macro VBA**.
2. La macro `P:\VBA\OITM\Módulo1.bas` **cerca a la columna equivocada** de la fulla InfoAnex:
   - Columnes InfoAnex: A=`INF_TIPO`, **B=`INF_TITULO`**, **C=`art_codi`**, D=`INF_VALOR`.
   - Els blocs `dictSacEspec` (línies 128-140) i `dictProducteE` (línies 142-153) llegien `wsInfoAnex.Cells(n, "C")` (art_codi) i comparaven amb prefixos `"SAC__ESPEC"` / `"PRODUCTE_E_7G6115Z5T"` — que són valors de `INF_TITULO` (columna B). Cap art_codi comença per aquests prefixos → **0 coincidències**.
3. En canvi, el bloc `dictArticeEsp` (línies 116-126) llegia correctament de columna B, i per això `QryGroup2` (Dimensió especial) sí que tenia 21 articles marcats.

### Fix aplicat (2026-07-23)

Fitxer: `P:\VBA\OITM\Módulo1.bas`. Dos blocs corregits perquè segueixin el mateix patró que `dictArticeEsp` (que ja funcionava):

**Línies 128-142** (`dictSacEspec`):
```vba
' Ara llegeix INF_TITULO de col B; si coincideix, agafa art_codi de col C:
valB = Trim(CStr(wsInfoAnex.Cells(n, "B").Value))
If Len(valB) >= 10 Then
    If UCase(Left(valB, 10)) = "SAC__ESPEC" Then
        If Trim(CStr(wsInfoAnex.Cells(n, "D").Value)) <> "" Then
            valC = Trim(CStr(wsInfoAnex.Cells(n, "C").Value))
            If Len(valC) > 0 Then dictSacEspec(valC) = True
        End If
    End If
End If
```

**Línies 144-156** (`dictProducteE`): mateix patró.

**Línies 399-404 i 407-412**: actualitzats els comentaris explicatius (només documentació).

### Passos pendents (executor: usuari)

1. Obrir `P:\VBA\OITM\OITM - Items1.xlsm` amb Excel.
2. Executar la macro del `Módulo1` (`Alt+F8` → executar procediment principal).
3. Verificar que la columna EE ara té ~13 `tYES` i la EF ~41 `tYES`.
4. Pujar el xlsm actualitzat a SAP via Data Transfer Workbench (mateix flux habitual).

### Verificació post-import (per Claude un cop pujat)

Queries SAP (read-only):
```sql
SELECT COUNT(*) FROM OITM WHERE QryGroup3='Y';  -- esperar ≈13
SELECT COUNT(*) FROM OITM WHERE QryGroup4='Y';  -- esperar ≈41
```

Re-executar el batch de comandes reals de §1.9 i observar canvis de comportament:
- Comandes amb articles marcats `QG3='Y'` haurien de veure RF6 aplicada (base=8, palet basepalet).
- Comandes amb articles marcats `QG4='Y'`: cap canvi al motor de moment (encara usa proxy `U_SEIFamCialCat`).

### Notes col·laterals

- **`dictAprovision` (línies 155-166)** també cerca a col C erròniament, però NO s'utilitza per omplir cap columna del BP (només carrega el diccionari). Cerca inefectiva sense impacte visible. No corregit (fora d'aquest scope).
- **QG4 populació col·lateral (41 articles)**: encara que el motor Python usa proxy `U_SEIFamCialCat='MOULIN DE COLAGNE'`, tindrem QG4 com font autoritativa disponible per si un dia volem canviar-hi.
