# Fase 2 — Integració dins SAP (progrés)

Document viu que registra el progrés de la Fase 2 tècnica, subfase a subfase.
S'actualitza a cada commit rellevant. Complement a:
- `tasks/validacio_sap.md` — Fase 1 (validació del motor amb dades SAP).
- `docs/proposta_integracio_sap.docx` — proposta consultiva al consultor SAP.
- `C:\Users\ohijazo.AGRIENERGIA\.claude\plans\la-idea-era-que-partitioned-rabin.md` — pla general.

## Disseny final (post-consulta, 2026-07-27)

**Impacte mínim a SAP**: només 3 UDFs a la taula ORDR (prefix `U_FC`).

| UDF | Tipus | Rol |
|---|---|---|
| `U_FCCalcular` | Alfa 1 (`S`/`N`) | Flag trigger — l'usuari el marca a `S` i desa |
| `U_FCEmbalatgeResum` | Alfa 254 | Resum textual escrit pel worker |
| `U_FCEmbalatgeEstat` | Alfa 30 | Estat (CALCULAT/ERROR/etc.) |

**Trigger sota demanda** (no automàtic):
- L'usuari edita comandes iterativament ("sac a munt, sac a vall") sense pressió.
- Quan la comanda ja és definitiva, marca `U_FCCalcular=S` i desa.
- Un worker Python polleja cada ~5-10s **només les comandes amb aquest flag actiu**.
- El worker: calcula, escriu `U_FCEmbalatgeResum` i `U_FCEmbalatgeEstat`, i posa `U_FCCalcular=N` (via SAP Service Layer PATCH).
- Si més tard cal recalcular, l'usuari torna a marcar el flag.

**Sense**: UDTs personalitzades, User Query panel, add-ons SDK.

## Estat de les subfases

| Subfase | Descripció | Estat |
|---|---|---|
| 2.0 | Proposta consultiva al consultor SAP | ✅ Enviada (commit `b86fbc2`) |
| 2.1 | Client Service Layer aïllat + tests | ✅ Fet (commit `df1a1b9`) |
| 2.2 | Detecció comandes amb `U_FCCalcular='S'` | ✅ Fet (commit `d1916da`) |
| 2.3 | Format del resum textual (`sap_formatter.py`) | ✅ Fet (commit `f7aedb6`) |
| 2.4 | Worker sync (`sync_worker.py`) + entry point | ✅ Fet (commit `c328d3c`) |
| 2.5 | Endpoint admin monitoratge | ✅ Fet |
| 2.6 | Deployment amb NSSM + validació end-to-end | ✅ Fet (script + docs; validació esperant consultor) |
| 2.7 | Fix duplicació de palets i recàlcul obsolet | ✅ Fet (commit `1b3c6d6`) |
| 2.8 | Gunicorn en producció + swap de la URL a SAP | ✅ Gunicorn fet (`a33c5e0`); swap pendent del DNS de Sistemes |
| 2.9 | Reutilització de la sessió Service Layer | ✅ Fet i verificat al servidor (commit `7b75380`, smoke test 8/8) |
| 2.10 | Fix RF4: apilament ignorava la capacitat del palet | 🔧 Fet i provat al repo; pendent desplegar |

---

## §2.1 Client Service Layer (2026-07-27)

### Objectiu
Client REST per SAP Service Layer amb gestió de sessió i reintents, aïllat i completament testable sense necessitat d'accés a un SAP real.

### Canvis
- **Nou fitxer** `sap_service_layer.py`: classe `SLClient`.
  - Login (POST /Login) + logout (POST /Logout).
  - Renovació preventiva sessió cada 25 min (sobre 30 min de SAP).
  - Wrapper `_request` amb 2 tipus de reintent:
    - `401` → relogin + retry 1 cop.
    - `5xx` → backoff exponencial (3 intents totals).
  - `404` → `SLNotFoundError`.
  - `4xx` altres → `SLError` amb status + body.
  - `patch_order(doc_entry, fields)` — única operació de negoci que necessitem.
  - Context manager (`with SLClient(...) as sl:`).
- **Nou fitxer** `tests/test_sap_service_layer.py` — 13 tests amb `responses` HTTP mock.
- **`.env.example`** — nou bloc `SAP_SL_*` (URL, company, user, pwd, verify SSL, timeout).
- **`requirements-dev.txt`** — `responses>=0.24`.

### Verificació
- `pytest tests/test_sap_service_layer.py -v` → 13/13 OK.
- `pytest tests/` → 84/84 OK (71 existents + 13 nous). Cap regressió.

### Commit
`df1a1b9 feat(sap): client Service Layer amb tests mock (Fase 2.1)`

---

## §2.2 Detecció de comandes marcades (2026-07-27)

### Objectiu
Funció que retorna les comandes obertes que l'usuari ha marcat amb `U_FCCalcular='S'`, amb fallback robust si el UDF encara no existeix a SAP.

### Canvis
- **`consultes.py`** — dos elements nous al final del fitxer:
  - `_udf_calcular_exists(conn)` — comprova existència del UDF via INFORMATION_SCHEMA. Cachejat en memòria (canvi molt puntual d'entorn).
  - `obtenir_comandes_a_calcular(conn) -> list[dict]` — retorna `{doc_entry, series, docnum, card_code}` per cada comanda amb flag actiu. Si el UDF no existeix, retorna `[]` amb log warning.
- **Nou fitxer** `tests/test_obtenir_comandes_a_calcular.py` — 6 tests amb mock pyodbc:
  - UDF no existeix → `[]` + warning.
  - UDF no existeix → cache evita repetir INFORMATION_SCHEMA.
  - UDF existeix → retorna comandes marcades.
  - UDF existeix, cap marcada → `[]`.
  - `CardCode=None` → string buit (defensiu).
  - Cache `True` es reutilitza entre crides.

### Verificació
- `pytest tests/test_obtenir_comandes_a_calcular.py -v` → 6/6 OK.
- `pytest tests/` → 90/90 OK (71 existents + 13 SLClient + 6 nous). Cap regressió.
- **Prova contra BD SAP real**: `obtenir_comandes_a_calcular(conn)` retorna `[]` amb warning esperat (`U_FCCalcular` no existeix encara).

### Commit
`d1916da feat(sap): detecció de comandes amb U_FCCalcular='S' (Fase 2.2)`

### Ajusts obsoletes al capçalera de `consultes.py`
El comentari inicial (línies 35-43) diu que RF3, RF4, RF6 no s'apliquen — obsolet post-fix Kais BUG #1. Cal actualitzar-lo. Marcat com a TODO menor per la propera revisió.

---

---

## §2.3 Format del resum textual (2026-07-27)

### Objectiu
Funció pure Python que produeix el text del resum + l'estat a partir d'un `Resultat` del motor, per omplir els UDFs `ORDR.U_FCEmbalatgeResum` (Alfa 254) i `U_FCEmbalatgeEstat` (Alfa 30).

### Canvis
- **Nou fitxer** `sap_formatter.py`:
  - `formatar_resum(resultat) -> tuple[str, str]` — signatura única.
  - 3 formatters interns per estat: `_format_calculat`, `_format_sota_minim`, `_format_no_calculable`.
  - Truncament automàtic a 254 chars amb `…` si excedeix.
  - Helpers: `_primer_motiu` (extreu el primer motiu talladíssim al primer punt o salt de línia), `_describe_palets` (formata "N×descrip"), `_comptar_avisos` (compta AVÍS a traçabilitat).
- **Nou fitxer** `tests/test_sap_formatter.py` — 13 tests cobrint:
  - CALCULAT basic / multi tipus palet / sense palets / ignora palets lògics.
  - CALCULAT_AMB_AVISOS afegeix comptador.
  - SOTA_MINIM amb i sense missatge.
  - NO_CALCULABLE amb i sense missatge.
  - Truncament a 254 amb el·lipsi.
  - Missatge tallat al primer punt / salt de línia.

### Verificació
- `pytest tests/test_sap_formatter.py -v` → 13/13 OK.
- `pytest tests/` → **103/103 OK** (90 previs + 13 nous). Cap regressió.
- **Prova contra el motor real** amb 5 comandes SAP:
  - `268/26600028`: `"2 palets · 60 sacs · CALCULAT"` (29 chars).
  - `268/26600052`: `"1 sacs · SOTA_MINIM · RF2 STOP: La comanda té 1 sacs..."` (132 chars).
  - `268/26600112`: `"NO CALCULABLE · RF1 STOP: La comanda inclou articles a granel..."` (75 chars).
  - `268/26600093`: `"100 palets · 2400 sacs · 100×palet plastic europeu 120x80 · CALCULAT"` (68 chars).
  - `268/26600092`: `"189 palets · 7075 sacs · 70×palet fusta europeu 120x80, 119×1030 · CALCULAT"` (75 chars).

Tots ben dins el límit 254 amb marge sobrat.

### Commit
Pendent commit + push.

### Observació menor
En una prova (`268/26600092`) apareix `119×1030` (art_codi enlloc de descripció). El `PaletResum.art_descrip` és `"1030"` per aquest palet — el `_describe_palets` ho reflecteix fidelment. No és un problema del formatter, és consistent amb les dades del motor.

---

---

## §2.4 Worker sync + entry point (2026-07-27)

### Objectiu
Uneix els mòduls previs (`consultes`, `motor`, `sap_formatter`, `sap_service_layer`) en un worker que polleja les comandes marcades i les processa. Entry point CLI amb opcions.

### Canvis
- **Nou fitxer** `sync_worker.py`:
  - Dataclass `PassStats` — estadístiques d'una passada (trobades, ok, error_motor/patch/altres, dry_run, errors, elapsed_sec).
  - Classe `SyncWorker` amb injecció de dependències (facilita testejar sense mòduls globals):
    - `run_one_pass()` — executa una passada, retorna `PassStats`.
    - `run_forever(stop_event)` — loop indefinit amb graceful shutdown via `threading.Event`.
    - `_process_one(c, stats)` — orquestra el pipeline per una comanda: calcular → formatar → patch.
    - `_patch_error(doc_entry, msg, stats)` — escriu error a SAP i posa `U_FCCalcular='N'` perquè no es reprocessi (evita loops).
  - Errors del motor / formatter → marca `U_FCEmbalatgeEstat='ERROR'` a SAP + continua amb la següent comanda.
  - Errors del patch → registra, NO fa patch d'error recursiu, deixa el flag actiu perquè la propera passada reintenti.
  - Sense estat local (SQLite, fitxers): el "estat" viu al mateix ORDR.
  - `max(0.1, ...)` al wait del loop evita tight loop si passades peten ràpidament.

- **Nou fitxer** `run_sync.py`:
  - CLI amb `argparse`: `--once`, `--dry-run`, `--interval`, `--max-per-pass`, `--log-level`.
  - Carrega config `.env` automàticament (via import de `consultes.py`).
  - Login explícit al SLClient — falla aviat si credencials incorrectes.
  - Signal handlers SIGINT/SIGTERM per graceful shutdown.
  - `try/finally` per garantir `sl.logout()` sempre.

- **Nou fitxer** `tests/test_sync_worker.py` — 13 tests amb mocks:
  - 0 comandes → cap patch.
  - 1 comanda OK → patch amb payload `{U_FCCalcular=N, Resum, Estat}` correcte.
  - Múltiples comandes → un patch per cadascuna.
  - Respect `max_per_pass`.
  - Error motor → patch d'error + continua + estat ERROR a SAP.
  - Error patch → registrat, NO recursiu, continua amb la següent.
  - Dry-run → cap patch real.
  - Dry-run + error motor → cap patch tampoc.
  - Conn BD tancada sempre (fins amb excepció).
  - `run_forever` s'atura amb stop_event.
  - `run_forever` continua després d'una passada que peta.

### Verificació
- `pytest tests/test_sync_worker.py -v` → 13/13 OK.
- `pytest tests/` → **116/116 OK** (103 previs + 13 nous). Cap regressió.
- `python run_sync.py --help` → mostra ajuda amb totes les opcions.
- `python -c "import run_sync"` → OK (verifica que tots els imports encaixen).

### Commit
Pendent commit + push.

### Notes de disseny
- La injecció de dependències (`connectar_fn`, `obtenir_comandes_fn`, etc.) fa que el worker sigui testable sense mocks globals — facilita l'aïllament de tests.
- El worker no fa autologin al SLClient: el CLI ho fa explícitament abans d'entrar al loop, per fallar aviat en cas de credencials incorrectes.
- Sense lockfile per prevenir 2 workers simultanis — el servei NSSM al deployment (§2.6) ja garanteix una única instància. Es podrà afegir un lockfile portable (msvcrt/fcntl) si algun dia canvien les circumstàncies.

---

---

## §2.6 Deployment amb NSSM (2026-07-27)

### Objectiu
Registrar `run_sync.py` com a servei Windows perquè arrenqui automàticament, es reinicii en cas d'error, i tingui rotació de logs.

### Canvis
- **Nou fitxer** `scripts/install_sync_service.ps1` — script PowerShell per instal·lar/desinstal·lar el servei NSSM.
  - Paràmetres: `-Install` (default), `-Uninstall`, `-ServiceName`, `-ProjectPath`, `-PythonExe`, `-NssmPath`.
  - Verificacions: administrador, NSSM accessible, python executable, `run_sync.py` present.
  - Configuració NSSM: AppDirectory, DisplayName, Description, StartType=Auto, logs a `logs/sync_worker.log` amb rotació (5 MB × 5 fitxers ≈ 25 MB màx), restart on failure amb throttle 10s.
  - Codificació **UTF-8 amb BOM** (requerit per Windows PowerShell 5.1 amb caràcters accentuats).
- **Nou fitxer** `docs/deployment_worker.md` — guia completa:
  - Prerequisits (NSSM, venv, UDFs SAP creats, credencials Service Layer).
  - Prova prèvia amb `--once --dry-run`.
  - Instal·lació step-by-step.
  - Operativa diària (veure logs, reiniciar, aturar).
  - Actualització de codi.
  - Desinstal·lació.
  - Troubleshooting.
  - Paràmetres avançats (interval, max_per_pass, log-level).
  - Alternativa systemd (Linux) documentada.

### Verificació
- **Parser PS1**: `[System.Management.Automation.Language.Parser]::ParseFile` retorna 648 tokens, 0 errors.
- **Instal·lació real**: no provada aquí (requereix privilegis d'administrador + NSSM + servidor SAP amb UDFs creats). El script farà `nssm install/set/start` amb els paràmetres correctes; el troubleshooting està documentat.
- Documentació coherent amb els noms de mòduls i fitxers actuals.

### Commit
Pendent commit + push.

### Bloquejant
La validació end-to-end del servei requereix:
1. UDFs `U_FCCalcular`, `U_FCEmbalatgeResum`, `U_FCEmbalatgeEstat` creats a SAP (pendent consultor).
2. Credencials Service Layer amb usuari dedicat (pendent consultor).
3. NSSM instal·lat al host de producció.

Fins llavors, el deployment queda "code-ready + docs-ready" — s'executarà quan el consultor doni el vistiplau i creï els requisits.

---

## §2.5 Endpoint admin monitoratge (2026-07-27)

### Objectiu
Permetre veure l'estat del worker de sync des de la web Flask sense obrir logs. Útil per debug, monitoratge i per verificar que el worker està sa.

### Arquitectura
El worker (`run_sync.py`) i Flask (`app.py`) són processos separats (NSSM service vs. Flask server). Comuniquen via **fitxer JSON** compartit a `logs/sync_status.json`:
- **Worker**: després de cada passada escriu snapshot amb totals acumulats + últimes 20 passades + config. Escriptura atòmica (temp + rename) per evitar reads parcials.
- **Flask**: endpoint `/api/admin/sync-status` llegeix el JSON i el retorna.

### Canvis
- **`sync_worker.py`**:
  - Nou paràmetre `status_file` al `SyncWorker.__init__` (default `None`).
  - Nova constant `_HISTORIC_MAX = 20` — buffer intern de les últimes N passades.
  - `_register_pass(stats)` — actualitza buffer intern + totals + escriu fitxer.
  - `_write_status_file()` — escriptura JSON atòmica amb `os.replace`.
  - Snapshot inclou: `started_at`, `last_pass_at`, `totals`, `recent_passes`, `config`.
  - Errors d'escriptura (OSError) es loggen com WARNING i no aturen el worker.
  - Aprofitat per corregir warning de `datetime.utcnow()` deprecat.

- **`run_sync.py`**:
  - Nova env var `SYNC_STATUS_FILE` (default `logs/sync_status.json`).
  - `_build_worker` accepta i passa `status_file`.
  - Crea `logs/` si no existeix abans d'arrencar el worker.

- **`app.py`**:
  - Nou endpoint `GET /api/admin/sync-status`.
  - Llegeix `SYNC_STATUS_FILE` (mateix default que `run_sync.py`).
  - Retorna 3 estats possibles:
    - `not_running` (200): fitxer no existeix — worker aturat o mai executat.
    - `running` (200): snapshot llegit OK, retorna totes les dades.
    - `error_reading_status` (500): fitxer corrupte (JSON malformat).

### Tests nous
- **`tests/test_sync_worker.py`** (+6 tests): status_file no configurat / creat amb dades / totals acumulats / respect max histori / escriptura atòmica / error OSError loggejat i no atura.
- **`tests/test_endpoint_sync_status.py`** (3 tests amb Flask test client): not_running / running amb snapshot / error JSON malformat.

### Verificació
- `pytest tests/` → **125/125 OK** (116 previs + 6 worker + 3 endpoint). Cap regressió.

### Ús
```bash
# Consulta a l'endpoint (browser o curl):
curl http://comandes.agrienergia.local/api/admin/sync-status

# Exemple resposta (worker sa):
{
  "ok": true, "state": "running",
  "started_at": "2026-07-27T09:00:00Z",
  "last_pass_at": "2026-07-27T15:34:12Z",
  "totals": {"trobades": 128, "ok": 125, "error_motor": 2, "error_patch": 1, "error_altres": 0},
  "recent_passes": [...últimes 20 passades...],
  "config": {"interval_sec": 10.0, "max_per_pass": 50, "dry_run": false}
}
```

### Commit
Pendent commit + push.

---

## Estat final Fase 2 tècnica

Amb aquest commit **totes les subfases estan tancades**. Falta només:
1. **Consultor SAP** — crear els 3 UDFs a ORDR + usuari Service Layer.
2. **Instal·lació física** — executar `install_sync_service.ps1` al servidor.

Un cop fets aquests 2 passos externs, l'integració estarà operativa.

---

## Propers passos (post-consultor)
- `GET /api/admin/sync-status` a `app.py`.
- Retorna estadístiques del worker (últimes execucions, últimes errors).
- Reutilitza rate limiting existent.

**§2.6 — Deployment**:
- Servei Windows amb NSSM.
- Script `scripts/install_sync_service.ps1`.
- Validació end-to-end contra SAP real un cop el consultor hagi creat els UDFs.

## Convenció

Aquest fitxer s'actualitza abans de cada commit d'una subfase de Fase 2:
- Afegir nou apartat `§2.X` amb objectiu, canvis, verificació i commit hash.
- Actualitzar la taula d'estat de subfases al principi.
- Registrar qualsevol descoberta col·lateral o pendent.

---

## §2.7 Fix de producció: duplicació de palets i recàlcul obsolet (2026-09-15)

### Objectiu
Resoldre les dues queixes dels usuaris sobre el botó "Calcular embalatges":
el palet ja anotat es duplicava, i per algunes comandes semblava que no
recalculava.

### Canvis
- **`consultes.py`**
  - `obtenir_articles_palet(conn)` — catàleg d'ItemCodes del grup d'articles
    palet (`OITM.ItmsGrpCod`, per defecte 152 = `070002-PALETS`, configurable
    amb `SAP_ITM_GRP_PALETS`). Cachejat en memòria.
  - `invalidar_caches_comanda(..., cli_codi=None, adr_codi=None)` — purga també
    `_direccio_cache` i `_palet_client_cache` (que cacheja resultats negatius)
    sense dependre que la comanda ja fos al cache.
  - `obtenir_direccio` retorna còpia: el motor muta `tipus_descarrega` quan
    l'autodetecta i contaminava el cache per a tot el (client, direcció).
  - `obtenir_metadata_ordr_per_doc_entry` retorna `ShipToCode` (codi de
    direcció) en lloc de `Address2` (adreça formatada).
  - `obtenir_palet_client` / `obtenir_preus_palets_client`: la prioritat per
    direcció es fa per igualtat amb `U_SEIDireccion` (el `LIKE '<adr>-%'`
    anterior no casava mai).
  - `obtenir_palet_comanda` ignora les línies del propi motor (`U_FCAfegit='S'`)
    i ordena per `LineNum` (el `TOP 1` no era determinista).
- **`sap_service_layer.py`** — `replace_marked_lines(..., owned_item_codes=...)`:
  també són línies del motor les obertes amb un ItemCode de palet, encara que
  no portin marcador. Amb dues del mateix article, sobreviu la de l'operari
  (se li corregeix la quantitat) i es tanca la del motor. Amb `None` el comportament és l'anterior.
- **`app.py`** — l'endpoint invalida els caches abans de calcular, passa
  `owned_item_codes`, retorna `resum.avisos` i emet JSON sense escapar accents.
- **`motor.py`** — `obtenir_palet_client` rep `conn_compartida` (sense això,
  el camí batch es penjava al semàfor d'1 connexió).
- **`docs/b1up_uf038_calcular_embalatges.cs`** — llegeix la resposta i mostra
  el resum real (StatusBar si `CALCULAT` sense avisos, MessageBox amb els
  missatges del motor si no).

### Verificació
- `pytest tests/` → **122/122 OK** (113 previs + 5 de propietat de línies palet
  + 4 d'invalidació de caches).
- Contra `DB_FARINERA_TEST`:
  - 26600207: la línia manual queda tancada i en queda una de sola amb Qty=2;
    segon clic → `+0 ~1 -0` (idempotent).
  - 26600209 (Descamps): passa d'1 a 2 BasePalet, que és el que diu el motor.
  - 26600199: la línia de l'operari `01000` passa a x37 i es tanca la del
    motor; queden `01000 x37` + `01030 x4`.
  - Comandes obertes amb palets duplicats: **7 → 0** (203, 206, 208, 91, 92
    consolidades passant el botó).
  - Tarifes per direcció: `C301147` + `089-...SAILEFORNERS` ara dona `01000`
    (abans `01022`, d'una altra direcció).

### Pendent operatiu
Enganxar el codi C# nou a B1UP (UF-038) — el fitxer del repo és la còpia de
referència, no s'aplica sol.

---


## §2.8 Producció: Gunicorn + swap de la URL a SAP (2026-09-29)

### Objectiu
1. Desplegar els commits pendents i treure l'app del dev server de Flask.
2. Preparar que `comandes.agrienergia.local` passi a servir la variant SAP,
   deixant Kais viu en paral·lel a `comandes-kais.agrienergia.local`.

### Fet i verificat al servidor
- `sudo bash deploy.sh` → `1b3c6d6` → `a33c5e0` (5 commits).
- `sudo bash deploy.sh --reinstall-service` → Gunicorn gthread 2×4 a
  `0.0.0.0:5002`. Verificat des de fora: `Server: gunicorn` i
  `/api/admin/versio` retorna `a33c5e0`.

**Causa arrel del dev server**: el camí d'actualització de `deploy.sh` fa
`git pull` + `systemctl restart` però **no reescriu la unit systemd**. La
definició amb Gunicorn només es creava a `--first-install` i el servidor es va
instal·lar abans que existís, així que cap `deploy.sh` hi arribava mai. D'aquí el
flag nou `--reinstall-service`.

### Bug de producció trobat pel camí
`/api/admin/actualitzar` a `app.py` feia
`sudo systemctl restart comandes-venda` — el servei de **Kais**, no
`comandes-venda-sap`. Identificador heretat de la còpia des de la variant Kais.
No era codi mort: `templates/ajuda.html` té un botó que crida l'endpoint, i la
guia de Kais documenta el `sudoers` que concedeix exactament aquest permís a
`www-data`. Clicar "actualitzar" des de SAP reiniciava producció i deixava SAP
amb el codi antic, retornant `"restart": "ok"`. Veure `tasks/lessons.md` L11.

### Error propi: vaig concloure que no hi havia Apache
Auditant el servidor només des de fora (capçaleres HTTP + sondeig de ports) vaig
concloure que no hi havia reverse proxy i que el Gunicorn de Kais ocupava
`0.0.0.0:80`. Sobre aquesta base vaig redissenyar la convivència amb una IP
secundària i `CAP_NET_BIND_SERVICE`, vaig **esborrar** `deploy/apache/`, vaig
marcar `docs/guia-desplegament-sap.html` com a obsoleta i vaig generar un PDF
demanant a Sistemes una IP que no calia.

Era fals. Hi ha Apache al port 80 amb vhosts per nom, i Kais escolta a
`127.0.0.1:5001` — exactament el que el repo ja documentava. Les dues proves que
em van enganyar (la capçalera `Server: gunicorn` i un `Host` inexistent servit per
Kais) no demostraven res; el detall a `tasks/lessons.md` L12. Tot revertit: les
configs d'Apache recuperades, la guia HTML vàlida un altre cop.

### Topologia real (verificada amb `apachectl -S` i `ss -tlnp`)
```
Apache *:80 (NameVirtualHost)
  agrupacions.agrienergia.local → agrupacio-carregues.conf   ← default server
  comandes.agrienergia.local    → comandes-venda.conf  → 127.0.0.1:5001  Kais
  fitxesfc / labfc / visitesfc  → els seus vhosts
  (cap nom encara)              → comandes-venda-sap.conf → 127.0.0.1:5002  SAP
```

### El swap és més senzill del que semblava
`comandes.agrienergia.local` **ja apunta a `192.168.11.244` i no s'ha de tocar**:
les dues apps viuen a la mateixa IP i és Apache qui decideix quina serveix cada
nom. El swap és moure el `ServerName` d'un vhost a l'altre i un
`systemctl reload apache2`. Kais no s'atura ni es reconfigura.

A Sistemes només se li demana **un registre DNS**:
`comandes-kais.agrienergia.local` → la mateixa `192.168.11.244`.

### Canvis al repo
- **`app.py`** — fix del servei reiniciat per `/api/admin/actualitzar`.
- **`deploy.sh`** — `write_service_unit()` com a font única de la unit (cridada
  per `--first-install` i pel flag nou), flag `--reinstall-service` repetible i
  idempotent que garanteix `pip install -r requirements.txt`, socket via
  `BIND_ADDR` (per defecte `0.0.0.0:5002`), i avís al final de l'actualització si
  la unit encara no fa servir Gunicorn.
- **`deploy/README.md`** — nou: topologia real d'Apache, estat objectiu del swap,
  i per què el bind és `0.0.0.0` (el botó B1UP hi apunta per IP directa).
- **`docs/runbook_swap_url_produccio.md`** — el de sempre, amb el prerequisit
  actualitzat (Gunicorn ja fet; el socket ha de quedar a `0.0.0.0` mentre la
  UF-038 depengui de la IP) i el pas B.7 reescrit: **no tocar el botó B1UP**, i si
  algun dia es vol, fer-ho amb un nom propi de SAP i no amb la URL històrica —
  així un rollback no el trenca.
- **`docs/peticio_dns_sistemes.md`** — nou: petició d'un registre DNS.
- **`scripts/build_guia_sistemes.py`** + **`docs/Desplegament_SAP_Sistemes.pdf`** —
  nous: guia de 10 pàgines per Sistemes (arquitectura abans/després, petició,
  finestra pas a pas, verificació, rollback, diagnòstic, manteniment, botó B1UP).
- **`tasks/lessons.md`** — L11 (identificadors heretats de Kais) i L12 (no deduir
  l'arquitectura d'un servidor des de fora).

### Pendent operatiu
1. **Sistemes**: DNS `comandes-kais.agrienergia.local` → `192.168.11.244`, TTL 300.
2. Backup de la config d'Apache i smoke load test amb Gunicorn.
3. Finestra del swap seguint la Fase B del runbook (~10 min, fora d'hores).
4. Opcional i posterior: DNS `comandes-sap.agrienergia.local` + `ServerAlias` +
   UF-038 al nom nou + `BIND_ADDR=127.0.0.1:5002`.

---

## §2.9 Reutilització de la sessió Service Layer (2026-09-29)

### Objectiu
Que el botó B1UP no falli quan diversos operaris el cliquen alhora.

### Com es va trobar
Smoke load test previ al swap, amb 8 comandes diferents en paral·lel contra
`POST /api/afegir-palets/`: **5 de 8 respostes 502**, totes agrupades entre 15,19
i 15,36 s. Al log, `Fallada de xarxa al login: ... Read timed out (read
timeout=15)`.

### Causa
`app.py` feia `with _sl_client() as sl:` a cada petició → `POST /Login` i
`Logout` al Service Layer **per cada clic**. Amb 8 logins simultanis el Service
Layer no hi arriba i els que no entren venen als 15 s (`SAP_SL_TIMEOUT`);
`login()` embolcalla el timeout dins `SLLoginError`, subclasse d'`SLError`, i
l'endpoint el tradueix a 502.

`SLClient` ja estava escrit per viure molt (renovació preventiva als 25 min a
`_ensure_session`), però creant-ne un per petició aquella lògica no s'executava
mai.

**No és una regressió de la migració a Gunicorn**: el dev server de Flask
serialitzava les peticions i mai n'hi havia dues alhora al Service Layer. La
concurrència real va fer visible un defecte latent.

### Canvis
- **`app.py`** — `_sl_client()` passa a retornar un singleton del procés
  (double-checked locking); `_build_sl_client()` conserva la construcció des de
  l'entorn. L'endpoint deixa de fer servir el context manager.
- **`sap_service_layer.py`** — `RLock` per instància. `_request` i
  `replace_marked_lines` passen a ser embolcalls prims que prenen el lock i
  deleguen a `_request_locked` / `_replace_marked_lines_locked`. Protegeix que
  `requests.Session` no és thread-safe, que `_ensure_session()` muta l'estat de
  sessió, i que `replace_marked_lines` és un read-modify-write que dos fils
  podrien travessar alhora escrivint línies duplicades (L9 per una altra porta).

### Verificació
- `pytest tests/` → **128/128 OK** (124 previs + 4 nous).
- Els tests nous cobreixen: una sola sessió per a N peticions successives, un sol
  login amb 5 fils concurrents, cap solapament entre `replace_marked_lines` de
  fils diferents, i que `app._sl_client()` retorna sempre la mateixa instància.
- **Comprovat que els tests no són buits**: amb un lock fals (el comportament
  anterior) el test de concurrència dona 5 logins; amb el lock real, 1.

### Verificació al servidor (post-desplegament, commit `7b75380`)
Mateix smoke test, mateixes 8 comandes, abans i després:

| DocEntry | Abans | Després |
|---|---|---|
| 258 | 200 en 2,28 s | 200 en 0,38 s |
| 252 | 200 en 11,57 s | 200 en 0,69 s |
| 255 | **502 en 15,27 s** | 200 en 2,40 s |
| 242 | **502 en 15,25 s** | 200 en 2,69 s |
| 254 | 200 en 1,96 s | 200 en 2,97 s |
| 234 | **502 en 15,36 s** | 200 en 3,25 s |
| 253 | **502 en 15,19 s** | 200 en 3,49 s |
| 250 | **502 en 15,32 s** | 200 en 3,68 s |

**8/8 HTTP 200**, el més lent a 3,68 s, molt per sota del criteri de 5 s. El
warmup (2,22 s) inclou el login del primer worker; les dues primeres peticions
concurrents cauen a 0,38 i 0,69 s perquè ja troben la sessió feta. La resta puja
en esglaons d'uns 0,25-0,30 s, que és el cost real d'una operació al Service
Layer un cop serialitzades pel lock del client.

El total de les 8 concurrents (3,68 s) és 1,7× el warmup, no 8×: els dos workers
treballen en paral·lel i dins de cadascun les crides van en fila. Detall a
`tasks/lessons.md` L13.

---

## §2.10 Fix RF4: l'apilament ignorava la capacitat del palet (2026-09-29)

### Objectiu
Corregir una incidència d'usuari: una comanda amb 455 sacs i màxim 40 sacs/palet
a la direcció calculava 11 palets en comptes de 12.

### Causa
El repartiment principal era correcte (11 palets de 40). El pas d'apilament de
RF4, que col·loca els articles de dimensió especial a sobre dels palets
existents, limitava per `cantidadapilable` però **no per l'espai lliure del palet
receptor** (`regles.py:1614`). Els tres primers palets, ja plens a 40/40, rebien
5 sacs de sèmola cadascun i quedaven a 45 amb `max_sacs=40`.

La branca d'overflow que crea palets propis per als sacs que no caben ja existia,
però era inabastable: com que cap palet es rebutjava per estar ple, `remaining`
sempre arribava a 0.

Reproduït amb la comanda real `DocEntry 258` (`C321531`, direcció
`000-HARINAS LA ENCARNACION, SL-CDS`, `U_SEIMAXSP=40`).

### Canvis (al `regles.py` compartit, `P:\preparacioComandesVenda`)
- Comprovació de capacitat al bucle d'apilament: es salten els palets sense espai
  i `posar` es limita també per l'espai lliure.
- Missatge de traçabilitat propi per al cas "cap palet té espai lliure", que
  abans quedava mig buit.
- **Invariant de sortida a `aplicar_regles`**: si algun palet acaba per sobre del
  seu màxim s'afegeix un `AVÍS` a la traçabilitat i l'estat puja a
  `CALCULAT_AMB_AVISOS`. No hi havia cap comprovació d'aquest tipus, i és per
  això que el bug va arribar fins a l'usuari. No llença excepció a propòsit.
- Dos tests de regressió a `tests/test_rf4.py` (sincronitzat a les dues variants;
  la còpia de SAP anava dos tests enrere).

### Verificació
- Comanda real: **12 palets**, cap per sobre de 40, els 15 sacs de sèmola en un
  palet propi amb `tipus_palet='01030'`, el mateix que els altres onze — així que
  l'operari només veurà la línia de palet passar d'11 a 12.
- `pytest` → **113 a Kais**, **132 a SAP**. Cap regressió.
- Els tests nous verificats contra el codi anterior (worktree a `HEAD`): fallen
  amb el símptoma exacte del report (`Palet 1: 45 sacs amb max=40`).

### Desplegament
Kais en producció corre `9691d38` (30-06-2026) i el seu `regles.py` — que és el
que **SAP importa al servidor** — no tenia ni tan sols la branca d'overflow de la
qual depèn l'arreglo (commit `a83fed8`, mai pujat).

Branca `fix/rf4-capacitat-apilament` (`e279128`) amb `db275ce` + `a83fed8` + el
fix, deixant **fora** `332a64a` (avisos a fabricació, +207 línies a `mailer.py`,
mòdul compartit amb SAP), que és un canvi molt més gran i mereix la seva pròpia
finestra.

```bash
cd /var/www/comandes-venda
sudo -u www-data git fetch origin
sudo -u www-data git reset --hard origin/fix/rf4-capacitat-apilament
sudo systemctl restart comandes-venda-sap
sudo systemctl restart comandes-venda
```

**Entrebanc trobat al primer intent**: el `fetch` com a `www-data` fallava amb
`insufficient permission for adding an object to repository database
.git/objects`, tot i que `/var/www/comandes-venda` és de `www-data`. La causa eren
**27 objectes de `root:root` dins de `.git/objects`** — inclosos directoris com
`08`, `ad`, `35` i `21` — restes d'algun `sudo git` executat com a root. Git ha de
crear fitxers dins d'aquests directoris i no podia. Arreglat amb:

```bash
sudo chown -R www-data:www-data /var/www/comandes-venda/.git
```

El botó "actualitzar" de Kais (`/api/admin/actualitzar`) fa `git pull origin main`.
Com que `origin/main` (`9691d38`) és **avantpassat** del commit desplegat, el pull
diu "Already up to date" i no desfà res: `git pull` fusiona, no pot moure `HEAD`
enrere. L'únic efecte és que el botó no actualitzarà res fins que `origin/main`
avanci, i llavors caldrà resoldre la fusió.

### Pendent
1. Desplegar (comandaments de sobre) i confirmar-ho amb l'usuari que ho va
   reportar.
2. Endreçar el repo de Kais: té 4 commits sense pujar i l'arbre de treball brut.
   Decidir què es fa amb la feature d'avisos a fabricació i tornar el servidor a
   `main`.
3. Tres defectes més trobats al mateix fitxer, documentats però no tocats:
   RF11 supera el màxim de la direcció (`regles.py:403-404`), `art_max_map` fora
   d'àmbit (`regles.py:982` vs `:1332`, amb `NameError` latent) i RF14 sense
   comprovació per article.
