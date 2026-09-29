# Runbook — Convivència Kais + SAP i swap de `comandes.agrienergia.local`

> **Reescrit el 29-09-2026.** La versió anterior descrivia un swap basat en
> VirtualHosts d'Apache. Al servidor **no hi ha Apache** (cada app és un Gunicorn
> que escolta directament al seu socket), així que aquells passos eren
> inexecutables. Arquitectura real: `deploy/README.md`.

Aquest runbook cobreix dues operacions independents:

- **Fase 1 — Convivència** (ara): SAP obté la seva pròpia URL sense tocar Kais.
- **Fase 2 — Swap** (quan es decideixi): `comandes.agrienergia.local` passa a
  SAP i Kais es queda amb un nom secundari.

---

# Fase 1 — Convivència (SAP amb URL pròpia)

**Objectiu**: `http://comandes-sap.agrienergia.local/` serveix SAP, mentre
`http://comandes.agrienergia.local/` segueix servint Kais exactament com avui.

**Duració**: ~15 min. **Impacte sobre Kais**: cap (no es reinicia ni es
reconfigura el seu servei).

## 1.1 Demanar a Sistemes (prerequisit)

Veure `docs/peticio_dns_sistemes.md` per al text de la petició. Dues coses:

1. **IP lliure** a la VLAN del servidor — proposta `192.168.11.245` — configurada
   com a segona adreça de la interfície de `ae01farwebsrv` (netplan).
2. **Registre DNS** `comandes-sap.agrienergia.local` → aquesta IP, TTL 300 s.

Verificació abans de continuar:
```bash
ip -o addr show | grep 192.168.11.245        # ha de retornar una línia
```
```powershell
nslookup comandes-sap.agrienergia.local      # des d'un PC de la xarxa
```

## 1.2 Desplegar el codi pendent

```bash
sudo bash /var/www/comandes-venda-sap/deploy.sh
```
Fa `git pull` + reinicia el servei. Si el servei encara corre amb el dev server
de Flask, el script ho avisa explícitament al final.

## 1.3 Migrar a Gunicorn i afegir el bind de la IP secundària

```bash
sudo SAP_BIND_IP=192.168.11.245 bash /var/www/comandes-venda-sap/deploy.sh --reinstall-service
```

Reescriu la unit systemd sencera. Gunicorn queda escoltant a **dos** sockets:
- `192.168.11.245:80` → la URL nova per als usuaris.
- `0.0.0.0:5002` → el botó B1UP, que hi apunta per IP directa i **no s'ha de
  trencar**.

Si la IP `.245` encara no existeix, el script avorta amb un error clar en lloc de
deixar Gunicorn en bucle de reinicis.

## 1.4 Verificar

Al servidor:
```bash
systemctl status comandes-venda-sap                    # Active (running)
ss -tlnp | grep -i gunicorn                            # .245:80 i 0.0.0.0:5002
curl -sS -D - -o /dev/null http://192.168.11.245/      # Server: gunicorn
curl -sS -X POST http://127.0.0.1:5002/api/afegir-palets/<TEST_DOCENTRY>
```

Des d'un PC Windows de la xarxa:
```powershell
curl.exe http://comandes-sap.agrienergia.local/ajuda   # HTML de SAP
curl.exe http://comandes.agrienergia.local/            # HTML de Kais, intacte
curl.exe http://192.168.11.244:5002/api/admin/versio   # el bind del botó B1UP viu
```

Criteri d'acceptació: les **tres** responen. La tercera és la que garanteix que
el botó de SAP B1 segueix funcionant.

Smoke load test (opcional però recomanat el primer cop amb Gunicorn):
```bash
bash /var/www/comandes-venda-sap/scripts/smoke_load_test.sh 127.0.0.1:5002 <TEST_DOCENTRY>
```
Criteri: 10/10 peticions `HTTP 200`, temps individual < 5 s. Si els temps
concurrents són ~10× el de warmup, Gunicorn està serialitzant (revisar
`SLClient`).

## 1.5 Rollback de la Fase 1

```bash
sudo bash /var/www/comandes-venda-sap/deploy.sh --reinstall-service
```
Sense `SAP_BIND_IP`, la unit torna a escoltar només a `0.0.0.0:5002` — l'estat
funcional d'abans, amb Gunicorn en lloc del dev server. Kais no s'ha tocat en cap
moment, així que no té rollback possible ni necessari.

---

# Fase 2 — Swap de `comandes.agrienergia.local` (més endavant)

**Objectiu**: que la URL històrica serveixi SAP, deixant Kais a
`comandes-kais.agrienergia.local` com a fallback.

Amb l'arquitectura d'IPs separades, el swap és **només un canvi de DNS**. No es
toca cap servei, cap config ni cap port al servidor.

## 2.1 Prerequisits

- Fase 1 completada i SAP funcionant amb normalitat des de fa prou temps.
- TTL de `comandes.agrienergia.local` baixat a 300 s **com a mínim 24 h abans**
  (si estava a 3600, durant una hora hi haurà clients amb la resolució antiga).
- Finestra fora d'hores actives (abans de les 9 h o després de les 18 h).
- Comunicat als usuaris: "manteniment de ~5 min el dia X a les Y".

## 2.2 Canvis DNS (els fa Sistemes)

| Registre | Abans | Després |
|---|---|---|
| `comandes.agrienergia.local` | 192.168.11.244 | **192.168.11.245** |
| `comandes-kais.agrienergia.local` | — | **192.168.11.244** (nou) |
| `comandes-sap.agrienergia.local` | 192.168.11.245 | sense canvis |

SAP queda accessible pels dos noms alhora, cosa que no molesta: Gunicorn no filtra
per `Host`.

## 2.3 Verificació post-swap

```powershell
ipconfig /flushdns
nslookup comandes.agrienergia.local          # ha de resoldre a .245
curl.exe http://comandes.agrienergia.local/ajuda         # HTML de SAP
curl.exe http://comandes-kais.agrienergia.local/         # HTML de Kais
```

End-to-end a SAP B1:
1. Obrir **Comanda de venda** (una comanda esborrany).
2. Clicar **"Calcular embalatges"**.
3. Verificar el missatge d'èxit a l'StatusBar.
4. Verificar les línies palet inserides a `RDR1` amb `U_FCAfegit = 'S'`.

## 2.4 Actualitzar el botó B1UP (UF-038)

**Ho fa el consultor B1UP.** No és urgent: el bind `0.0.0.0:5002` segueix viu i
el botó continua funcionant per IP directa mentre no es faci.

1. SAP Fat Client → **Boyum IT → B1 Usability Package → Configurator**.
2. **Función → Función Universal → UF-038 "HTTP Motor Embalatges"**.
3. Substituir:
   ```
   "http://192.168.11.244:5002/api/afegir-palets/" + docEntry
   ```
   per:
   ```
   "http://comandes-sap.agrienergia.local/api/afegir-palets/" + docEntry
   ```
   Fer servir el nom **específic de SAP**, no `comandes.agrienergia.local`: així
   el botó no depèn de qui tingui la URL històrica en cada moment.
4. Clicar **Actualizar**.

Codi C# de referència: `docs/b1up_uf038_calcular_embalatges.cs`.

Un cop fet i verificat, es pot retirar el bind heretat:
```bash
sudo LEGACY_BIND= SAP_BIND_IP=192.168.11.245 bash /var/www/comandes-venda-sap/deploy.sh --reinstall-service
```

## 2.5 Rollback de la Fase 2

Revertir el registre `comandes.agrienergia.local` a `192.168.11.244`. Amb TTL 300
s, la propagació és de ~5 min.

**Criteri per fer rollback**: 502/504 recurrents, tracebacks Python a
`journalctl -u comandes-venda-sap`, o el consultor comunica errors sistemàtics del
botó B1UP.

Si la UF-038 ja apuntava a `comandes-sap.agrienergia.local`, el rollback de DNS
**no la trenca** (aquest nom segueix apuntant a SAP). Aquest és el motiu de fer
servir el nom específic al pas 2.4.

---

# Post-swap (dies següents)

- Monitorar `/var/www/comandes-venda-sap/error.log` durant una setmana.
- Verificar `logrotate` el dilluns: els logs de la setmana anterior han de tenir
  extensió `.1.gz`.
  ```bash
  ls -la /var/www/comandes-venda-sap/*.log*
  ```
- Comunicar `comandes-kais.agrienergia.local` als usuaris que necessitin consultar
  dades històriques via Kais.

---

# Contactes

- **Desenvolupador / mantenidor**: Oscar Hijazo (`ohijazo@agrienergia.com`)
- **Consultor B1UP**: [pendent d'assignar per Sistemes]
- **Sistemes / DNS**: [equip intern responsable de `agrienergia.local`]
