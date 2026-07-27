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
| 2.3 | Format del resum textual (`sap_formatter.py`) | ⏳ Pendent |
| 2.4 | Worker sync (`sync_worker.py`) + entry point | ⏳ Pendent |
| 2.5 | Endpoint admin monitoratge | ⏳ Pendent |
| 2.6 | Deployment amb NSSM + validació end-to-end | ⏳ Pendent |

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

## Propers passos

**§2.3 — Format del resum textual** (`sap_formatter.py`):
- Funció `formatar_resum(resultat) -> tuple[str, str]` que produeix `(text_resum, estat)` a partir del `Resultat` del motor.
- Ex: `("3 palets · 120 sacs · palet europeu · CALCULAT", "CALCULAT")`.
- Sense dependència de SAP; pure Python function.
- Tests unitaris amb fixtures `Resultat`.

**§2.4 — Worker sync** (`sync_worker.py` + `run_sync.py`):
- Uneix motor + formatter + SLClient.
- Loop cada 5-10s: obtenir_comandes_a_calcular → per cada una: calcular_embalatges → formatar → sl.patch_order (amb `U_FCCalcular=N`).
- Estat local SQLite per errors i logs?  Potser innecessari amb l'enfocament sota demanda (el "estat" viu al mateix ORDR).
- Graceful shutdown (SIGINT/SIGTERM).
- Entry point CLI: `python run_sync.py [--once|--dry-run]`.
- Tests unitaris amb mocks del SL i BD.

**§2.5 — Endpoint admin monitoratge**:
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
