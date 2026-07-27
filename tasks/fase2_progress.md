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
