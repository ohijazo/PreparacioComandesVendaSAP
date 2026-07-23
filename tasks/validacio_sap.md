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

| UDF esperat pel motor | Camp SAP | Present | Amb valor | Total | Estat |
|---|---|---|---|---|---|
| `uxc` | `U_SEIUnitatsPalet` | ✅ | 658 | 2027 | OK |
| `cantidadapilable` | `U_SEIUnitatsApilables` | ✅ | 58 | 2027 | OK |
| `palet_producte_estoc` | `U_SEIPaletProd` | ✅ | 88 | 2027 | OK |
| `sac_colagne_normal` | derivat de `U_SEIFamCialCat='MOULIN DE COLAGNE'` | ⚠ | 40 | 2027 | Proxy (no UDF explícit) |
| `dimensio_especial` | *(cap)* | ❌ | — | — | **RF4 no s'aplicarà** |
| `sac_25_especial` | *(cap)* | ❌ | — | — | **RF6 no s'aplicarà** |
| `comanda_minima_produccio` | *(cap)* | ❌ | — | — | **RF3 no s'aplicarà** |

Fallback conservador a `consultes.py:461-463`: `comanda_minima_produccio=None`, `dimensio_especial=False`, `sac_25_especial=False`. Els articles sempre es processen amb aquests valors → RF3, RF4 i RF6 mai s'activen a SAP fins que es creïn els UDFs corresponents.

**UDFs U_SEI\* addicionals a OITM disponibles** (no usats): `U_SEICadLot`, `U_SEIFamCialCast`, `U_SEIObserCast`, `U_SEIObserCat`, `U_SEIObserTec`, `U_SEISubFamCialCast`, `U_SEISubFamCialCat`. Cap sembla equivalent als 3 pendents.

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

1. **Bloquejant per RF3/RF4/RF6**: crear amb el consultor SAP els UDFs mancants a OITM:
   - `U_SEIDimensioEspecial` (bit o Y/N) — per `dimensio_especial`.
   - `U_SEISac25Especial` (bit o Y/N) — per `sac_25_especial`.
   - `U_SEIComandaMinimaProd` (int, kg) — per `comanda_minima_produccio`.
   
   Un cop creats, afegir la lectura a `consultes.py:_row_to_linia` (10 línies de codi). Sense això, aquestes regles mai s'apliquen a SAP.

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
