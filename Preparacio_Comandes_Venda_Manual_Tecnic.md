# Manual tècnic — Preparació de Comandes de Venda

**Última revisió:** 2026-06-19
**Responsable:** Oscar Hijazo (ohijazo@agrienergia.com)
**Repositori:** GitHub intern (`PreparacioComandesVenda`)
**Servidor:** `ae01farwebsrv.agrienergia.local` (192.168.11.244) — `/var/www/preparacio-comandes-venda` (Ubuntu)

---

## 1. Descripció funcional

**Preparació de Comandes de Venda** és un **motor determinista de paletització** que, donada una comanda de venda (sèrie/número), llegeix la BD del ERP KAIS, aplica 14 regles logístiques (RF1–RF14) i retorna la proposta d'embalatge: quants palets, quins sacs per palet, quina base, quin tipus de descàrrega, etc.

**Procés que cobreix:**

1. **Oficina** entra a `/` i introdueix `Sèrie/Número` (ex: `51/0002456`).
2. L'app crida `/api/calcular/<sèrie>/<número>` que orquestra:
   - SQL Server (KAIS) → llegir comanda + línies + articles + direccions.
   - Motor Python → aplica RF1–RF14 (filtres, mínims, articles especials, base/màxim, agrupacions).
3. Resultat: JSON amb palets proposats, sacs per article, explicacions i **traçabilitat** (totes les decisions).
4. UI mostra cards visuals i botons d'imprimir, exportar CSV o sol·licitar autorització (si la comanda és < 500 kg).

**Modes d'ús:**

- **Calculadora interactiva** (`/`) — operari busca i veu el resultat.
- **API batch** (`/api/calcular-batch`) — fins a 50 comandes en una sola crida.
- **API agrupada** (`/api/calcular-agrupat`) — agrupa comandes del mateix client per a una mateixa càrrega. Aquesta és la que crida l'app `agrupacioCarregues`.

**Usuaris finals:** Operaris d'oficina i magatzem que preparen comandes. **No hi ha autenticació** — accés intern via xarxa.

**Pàgines clau:**

- `/` — Calculadora interactiva.
- `/api/buscar/<sèrie/núm>` — Cerca comanda per albarà.
- `/api/calcular/<sèrie/núm>` — Càlcul d'una comanda.
- `/api/calcular-agrupat` (POST) — Agrupació multi-comanda.
- `/api/calcular-batch` (POST) — Fins a 50 comandes.
- `/api/exportar-csv/<sèrie/núm>` — Descàrrega CSV.
- `/api/sol-licitar-autoritzacio/<sèrie/núm>` — Envia correu si < 500 kg.
- `/ajuda` — Manual d'usuari (HTML).
- `/admin/sql-stats` — Monitorització SQL (tècnic).

---

## 2. Arquitectura tècnica

**Stack:**

- **Backend:** Python 3.10+ amb Flask 3.x (sense ORM, queries SQL directes).
- **Frontend:** Vanilla JavaScript (sense framework).
- **BD:** SQL Server (ERP KAIS, només lectura via `pyodbc` + `ApplicationIntent=ReadOnly`). NO té BD pròpia.
- **Servidor web (prod):** Gunicorn rere Apache, servei `preparacio-comandes.service` (systemd).

**Diagrama (flux principal):**

```
Oficina/Magatzem
    |
    v
Apache  ->  Gunicorn  ->  Flask (app.py)
                            |
                            +-> SQL Server KAIS (lectura)
                            |     ek_Pedido, ek_PedidoLineas,
                            |     ARTICLES, CLIENVIO, INFOANEX
                            |
                            +-> motor.py + regles.py
                            |     (14 regles RF1-RF14)
                            |
                            +-> mailer.py
                                  Microsoft Graph API (correus < 500 kg)
```

**Dependències Python principals** (`requirements.txt`):

| Paquet | Per a què |
|---|---|
| `Flask==3.1.3` | Framework web |
| `pyodbc==5.3.0` | SQL Server (KAIS) |
| `openpyxl==3.1.5` | Llegir `PREUSCLIENTS.xlsx` (cache fitxer) |
| `requests==2.32.3` | Microsoft Graph API (correus) |
| `python-docx==1.2.0`, `pdfkit`, `fpdf2`, `Pillow` | Generació documents (parcialment usats) |

**Fitxers clau:**

- `app.py` — Entrypoint Flask, endpoints, cache de comandes (TTL 55s).
- `motor.py` — Orquestra el càlcul d'embalatges per a una comanda.
- `regles.py` — Implementa les 14 regles logístiques RF1–RF14.
- `consultes.py` — Queries SQL Server, semàfor de concurrència (1 conn màx), cache.
- `models.py` — Dataclasses (`Comanda`, `Linia`, `Direccio`, `Resultat`).
- `mailer.py` — Enviament correus via Microsoft Graph (OAuth2 client_credentials).
- `templates/ajuda.html` — Manual d'usuari (80 KB).
- `static/PREUSCLIENTS.xlsx` — Taula de preus/palets per client (cache).

---

## 3. Configuració i desplegament

### 3.1 Variables d'entorn (`.env`)

```ini
# SQL Server (KAIS, només lectura)
SQL_SERVER=vkais\kais
SQL_DATABASE=GWSV_AGRI
SQL_USER=usuari_sql
SQL_PASSWORD=...

# Admin (per actualitzacions per URL)
ADMIN_KEY=clau_admin_segura

# Correus via Microsoft Graph (OAuth2)
MAIL_TENANT_ID=00000000-0000-0000-0000-000000000000
MAIL_CLIENT_ID=00000000-0000-0000-0000-000000000000
MAIL_CLIENT_SECRET=...
MAIL_FROM_EMAIL=farinera@grupagrienergia.onmicrosoft.com
MAIL_FROM_NAME=Motor Comandes Agrienergia
MAIL_TO=destinatari@dominio.com
MAIL_CC=cc1,cc2
```

Configuració OAuth detallada a `MAIL_SETUP.md` (App Registration al portal Azure).

### 3.2 Desplegament inicial

```bash
# 1. Clonar i instal·lar dependències
sudo bash deploy.sh --first-install

# El script fa:
#   - clona el repo a /var/www/preparacio-comandes-venda
#   - crea venv i instal·la requirements.txt
#   - configura el driver ODBC 18 per SQL Server
#   - crea el servei systemd 'preparacio-comandes.service'
#   - copia .env d'exemple per editar manualment

# 2. Editar .env amb les credencials reals
sudo -u www-data nano /var/www/preparacio-comandes-venda/.env

# 3. Arrencar servei
sudo systemctl enable preparacio-comandes.service
sudo systemctl start preparacio-comandes.service
```

### 3.3 Desplegament d'una actualització

```bash
sudo bash /var/www/preparacio-comandes-venda/deploy.sh

# Internament fa:
#   - git pull
#   - pip install -r requirements.txt (si ha canviat)
#   - systemctl restart preparacio-comandes
```

### 3.4 Entorns

| Entorn | URL | Servidor | Port | BD | Notes |
|---|---|---|---|---|---|
| Local (dev) | http://127.0.0.1:5001 | Portàtil | 5001 | SQL Server (compartit) | `python app.py` |
| Producció | http://ae01farwebsrv.agrienergia.local:5001/ | `ae01farwebsrv` (192.168.11.244) | Gunicorn rere Apache | SQL Server KAIS | systemd, www-data |

> Aquesta app **no té BD pròpia**. Només llegeix del SQL Server (ERP KAIS).

---

## 4. Accessos i permisos

### 4.1 Usuari del sistema operatiu (servidor)

L'app corre com a `www-data`. Fitxers amb owner `www-data:www-data`. `.env` amb permissos `640`.

### 4.2 Rols d'aplicació

**No hi ha autenticació local.** L'app és accessible per qualsevol qui pugui arribar al port 5001 (xarxa interna). En producció, Apache pot afegir auth bàsica si cal.

### 4.3 Accessos a BD

- **SQL Server (KAIS)**: usuari `SQL_USER` definit a `.env`. Connexió **forçadament només lectura** (`ApplicationIntent=ReadOnly`) — l'app no fa `INSERT`/`UPDATE`/`DELETE` mai.
- **Concurrència**: màxim 1 connexió simultània (semàfor a `consultes.py:61`). Timeout per query: 15s.

### 4.4 Admin endpoint

- `/admin/sql-stats` — Dashboard de monitorització SQL (queries, temps mig, errors recents). Sense auth — protegir per IP si cal.
- `/api/admin/clients` — Llista IPs actives i últims requests (debug).

---

## 5. Base de dades

### 5.1 No té BD pròpia

L'app és **stateless**: tota la informació viu al SQL Server del ERP KAIS. Només té caches en memòria (TTL curt).

### 5.2 SQL Server (KAIS) — taules consultades

| Taula | Per a què |
|---|---|
| `ek_Pedido` | Capçalera comanda (`pedi_num`, `cli_codi`, `pedi_dire`, `pedi_fech`) |
| `ek_PedidoLineas` | Línies de comanda (`art_codi`, sacs, kg) |
| `ARTICLES` | Mestre d'articles (`art_descunit` = S05/S10/S15/S20/S25/GRA/UNI, `art_unitcaixa` = UxC/màxim sacs, `art_pes`) |
| `CLIENVIO` | Direccions d'enviament per client |
| `INFOANEX` | Metadades del producte (sacs per base, màxim sacs per palet, tipus descàrrega, etc.) |

Totes les queries són `SELECT ... WITH (NOLOCK)`. **Mai s'escriu** al ERP.

### 5.3 Caches

| Cache | TTL | Refresc |
|---|---|---|
| Últimes comandes (dashboard) | 55 s | Background |
| Direccions per client | 10 min | On-demand |
| Dades mestres (articles, etc.) | Permanent (per worker) | Mai |
| `PREUSCLIENTS.xlsx` (palets per client) | Auto per mtime del fitxer | Quan l'Excel canvia |

---

## 6. Integracions externes

### 6.1 ERP SQL Server (KAIS)

Origen únic de dades. Si KAIS cau, l'app retorna 503. Vegeu **§ 10** per al contacte.

### 6.2 Microsoft Graph API (correus)

Per al flux d'autorització de comandes < 500 kg, l'app envia un correu via OAuth2 (client_credentials). El llindar es revalida al backend (`mailer.py:542`). Configuració completa: `MAIL_SETUP.md`.

### 6.3 Apps germanes que consumeixen aquesta

- **`agrupacioCarregues`** — importa `motor.calcular_embalatges()` via `sys.path` per orquestrar el càlcul de múltiples comandes agrupades en una càrrega. **Aquesta app és dependència crítica per a `agrupacioCarregues`**.

---

## 7. Errors habituals i resolució

| Símptoma | Causa probable | Diagnòstic | Resolució |
|---|---|---|---|
| 503 "Error connectant a SQL Server" | KAIS caigut o credencials canviades | `journalctl -u preparacio-comandes -n 50` | Verificar KAIS i `.env` |
| Timeout en queries pesades | Comandes complexes triguen >15s | Mirar `motor.log` | Pujar `_QUERY_TIMEOUT` a `consultes.py` (només si cal) |
| Correu d'autorització no s'envia | Token Microsoft Graph caducat o credencials OAuth canviades | Mirar `mailer.py` logs | Refrescar el secret a Azure App Registration |
| Resultat incorrecte per a una comanda | Bug en una de les 14 regles | Mirar la **traçabilitat** del resultat (`resultat.trazabilitat[]`) | Reportar amb la comanda concreta i el detall de traçabilitat |
| Operari diu que la comanda "no existeix" | Comanda no existeix o `sèrie/número` mal escrits | Buscar a `/api/buscar/<sèrie/núm>` | Confirmar amb el ERP |
| Cache desactualitzat | TTL llarg (10 min direccions) | Reiniciar servei o esperar TTL | `systemctl restart preparacio-comandes` |

---

## 8. Logs i monitorització

### 8.1 Logs de l'aplicació

| Tipus | Ubicació | Comanda |
|---|---|---|
| Log de l'app (local dev) | `motor.log` (rotat automàticament per Python) | `tail -f motor.log` |
| Log del servei (producció) | systemd journal | `journalctl -u preparacio-comandes.service -f` |
| Errors crítics | També al journal | `journalctl -u preparacio-comandes -p err -n 50` |

### 8.2 Monitorització SQL

- `/api/admin/sql-stats` — JSON amb: queries totals, temps mig, errors recents (últims 50), connexions actives.
- Dashboard visual: `/admin/sql-stats` (HTML).

### 8.3 Traçabilitat funcional

Cada resultat de `/api/calcular/...` inclou un camp `traçabilitat` que enregistra les decisions de cada regla RF aplicada. Útil per diagnosticar per què una comanda ha retornat un resultat concret.

---

## 9. Pla de contingència

### 9.1 No hi ha BD pròpia → no calen backups d'aquesta app

L'estat viu al ERP KAIS. Per al **backup del ERP**, vegeu el proveïdor (Kais).

### 9.2 Rollback de codi

```bash
sudo -u www-data git -C /var/www/preparacio-comandes-venda log --oneline -10
sudo -u www-data git -C /var/www/preparacio-comandes-venda checkout <commit_estable>
sudo systemctl restart preparacio-comandes.service
```

### 9.3 Què fer si cau el servei

1. `sudo systemctl status preparacio-comandes.service`
2. Si "failed": `sudo journalctl -u preparacio-comandes -n 100`. Buscar `pyodbc.Error` o `ModuleNotFoundError`.
3. Si "active" però no respon: `sudo systemctl restart preparacio-comandes.service`.
4. Si el reinici no soluciona: comprovar SQL Server KAIS (`telnet vkais 1433` per testar connectivity).

### 9.4 Identificar la versió desplegada

```bash
sudo -u www-data git -C /var/www/preparacio-comandes-venda log -1 --format="%h %s"
```

### 9.5 Impacte d'una caiguda

- L'app `agrupacioCarregues` retornarà 503 a `/api/agrupar` (cap impacte a la resta de la seva funcionalitat).
- Operaris no podran calcular embalatges des de la UI fins que es restableixi.

---

## 10. Contactes i dependències externes

### 10.1 Contactes interns

| Rol | Nom | Contacte |
|---|---|---|
| Responsable tècnic | Oscar Hijazo | ohijazo@agrienergia.com |
| Responsable funcional | Oscar Hijazo | ohijazo@agrienergia.com |
| IT (servidor `ae01farwebsrv`) | Jordi Coma | jcoma@agrienergia.com |

### 10.2 Dependències externes

| Servei | Proveïdor | Contacte |
|---|---|---|
| ERP SQL Server (KAIS, `GWSV_AGRI`) | Kais | — |
| Microsoft Graph API (correus) | Microsoft (M365) | Admin Entra ID intern |
| Hosting (servidor intern) | `ae01farwebsrv.agrienergia.local` (192.168.11.244) | Jordi Coma (jcoma@agrienergia.com) |

### 10.3 Recursos addicionals

- `CLAUDE.md` — Especificacions de les 14 regles RF.
- `MAIL_SETUP.md` — Configuració OAuth per Microsoft Graph.
- `docs/Informe_Tecnic_Connexions_BD.md` — Detall de connexions BD.
- `templates/ajuda.html` — Manual d'usuari (servit a `/ajuda`).
