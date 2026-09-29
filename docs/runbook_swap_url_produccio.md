# Runbook — Swap URL `comandes.agrienergia.local` de Kais a SAP

**Objectiu**: moure la URL `http://comandes.agrienergia.local/` de l'app Kais
(port 5001) a l'app SAP (port 5002), deixant Kais accessible com a fallback a
`http://comandes-kais.agrienergia.local/`.

**Duració estimada**: ~10 min. **Rollback**: < 5 min.

**Les dues apps conviuen**: Kais no s'atura ni es reconfigura el seu servei. El
swap només mou el `ServerName` d'un VirtualHost a l'altre; el seu Gunicorn segueix
igual al `127.0.0.1:5001`.

**No hi ha canvi de DNS per a la URL principal.** `comandes.agrienergia.local` ja
apunta a `192.168.11.244` i s'hi queda: les dues apps viuen a la mateixa IP i és
Apache qui decideix quina serveix cada nom. L'únic registre nou és el de fallback
de Kais (pas A.1).

**Prerequisit**: l'app SAP ha de córrer amb Gunicorn, no amb el dev server de
Flask. **Completat el 29-09-2026** (commit `a33c5e0` + `deploy.sh
--reinstall-service`). Verificar-ho amb:
```bash
curl -sS -D - -o /dev/null http://127.0.0.1:5002/ | grep -i server   # gunicorn
```

El socket és `0.0.0.0:5002` i **així ha de quedar mentre el botó B1UP (UF-038)
apunti a `192.168.11.244:5002` per IP directa**. Tancar-lo a `127.0.0.1` abans
d'hora mata el botó. Veure el pas B.7.

---

## Fase A — Preparació (T-24h abans del swap)

### A.1 DNS
Coordinar amb Sistemes per:
1. Afegir entrada `comandes-kais.agrienergia.local → 192.168.11.244` (la mateixa
   IP; el nom nou és per al fallback de Kais).
2. Confirmar TTL baix (300 s o menys) per possibles ajusts ràpids.
3. `comandes.agrienergia.local` **ja existeix i no es toca** — seguirà apuntant a
   `192.168.11.244`. El que canvia és quin VirtualHost la serveix.

Text de la petició preparat a `docs/peticio_dns_sistemes.md`.

### A.2 Backup Apache al servidor
```bash
sudo tar czf /root/apache-backup-$(date +%F).tgz \
    /etc/apache2/sites-available /etc/apache2/sites-enabled
```

### A.3 Verificar Gunicorn SAP
```bash
sudo systemctl status comandes-venda-sap        # Active (running)
ss -tlnp | grep -i gunicorn | grep 5002         # 0.0.0.0:5002 (veure prerequisit)
curl -sS -X POST http://127.0.0.1:5002/api/afegir-palets/<TEST_DOCENTRY>
# Esperat: JSON amb "ok":true
```

### A.4 Smoke load test contra Gunicorn directe
```bash
bash /var/www/comandes-venda-sap/scripts/smoke_load_test.sh 127.0.0.1:5002 <TEST_DOCENTRY>
```
Criteri d'acceptació: totes 10 peticions retornen `HTTP 200`, temps individual
< 5 s. Si els temps concurrents són ~10× el warmup, Gunicorn està serialitzant
(revisar `SLClient`).

### A.5 Comunicat
Avisar usuaris: "El servei estarà en manteniment ~5 min el dia X a les Y."
Programar el swap fora d'hores actives (matí abans de 9h o tarda després de
18h).

---

## Fase B — Swap (T-0, finestra ~10 min)

Executar per SSH al servidor `ae01farwebsrv` com a `root`/`sudo`.

### B.1 Copiar la config Apache SAP
```bash
sudo cp /var/www/comandes-venda-sap/deploy/apache/comandes-venda-sap.conf \
    /etc/apache2/sites-available/
```

### B.2 Editar el VirtualHost Kais existent
```bash
sudo nano /etc/apache2/sites-available/comandes-venda.conf
```
Fer aquests dos canvis:
1. Canviar la línia `ServerName comandes.agrienergia.local` per
   `ServerName comandes-kais.agrienergia.local`.
2. **Afegir just a sota** (temporal, els propers 30-60 s):
   ```
   ServerAlias comandes.agrienergia.local
   ```

L'alias evita que Apache dropi peticions in-flight cap a Kais mentre s'activa
el VirtualHost SAP en el pas B.4.

### B.3 Validar sintaxi
```bash
sudo apachectl configtest
```
Ha de retornar `Syntax OK`. Si dona error, no continuar; revisar el fitxer.

### B.4 Activar el VirtualHost SAP
```bash
sudo a2ensite comandes-venda-sap.conf
sudo systemctl reload apache2
```
`reload` (no `restart`) → no dropa connexions actives.

### B.5 Verificar la coexistència temporal
```bash
sudo apachectl -S | grep comandes.agrienergia
```
Ha de mostrar 2 VirtualHosts responent a `comandes.agrienergia.local` (SAP amb
ServerName, Kais amb ServerAlias). Apache prioritza el que carrega primer
alfabèticament — hauria de ser SAP (`comandes-venda-sap.conf` <
`comandes-venda.conf`).

### B.6 Eliminar l'alias temporal Kais
```bash
sudo nano /etc/apache2/sites-available/comandes-venda.conf
```
Eliminar la línia `ServerAlias comandes.agrienergia.local`.

```bash
sudo apachectl configtest && sudo systemctl reload apache2
```

Ara SAP té control exclusiu de `comandes.agrienergia.local`.

### B.7 El botó B1UP (UF-038) — no cal tocar-lo

**Recomanació: deixar-lo com està**, apuntant a
`http://192.168.11.244:5002/api/afegir-palets/`. El swap no l'afecta (Gunicorn
segueix escoltant al `0.0.0.0:5002`) i així sobreviu intacte a un rollback.

Si algun dia es vol treure la IP del codi de B1UP, **no fer servir
`comandes.agrienergia.local`**: quedaria lligat a qui tingui la URL històrica en
cada moment i un rollback el faria caure contra Kais, que no té l'endpoint. La
manera segura és donar a SAP un nom propi addicional:

1. Sistemes: registre `comandes-sap.agrienergia.local → 192.168.11.244`.
2. Afegir-lo com a `ServerAlias` al VirtualHost de SAP:
   ```apache
   ServerName comandes.agrienergia.local
   ServerAlias comandes-sap.agrienergia.local
   ```
3. El consultor B1UP actualitza la UF-038 (SAP Fat Client → **Boyum IT → B1
   Usability Package → Configurator → Función → Función Universal → UF-038 "HTTP
   Motor Embalatges"**):
   ```
   "http://comandes-sap.agrienergia.local/api/afegir-palets/" + docEntry
   ```
   i clica **Actualizar**. Codi C# de referència:
   `docs/b1up_uf038_calcular_embalatges.cs`.
4. Un cop verificat, tancar Gunicorn darrere d'Apache:
   ```bash
   sudo BIND_ADDR=127.0.0.1:5002 bash /var/www/comandes-venda-sap/deploy.sh --reinstall-service
   ```

Aquests quatre passos són opcionals i independents del swap: es poden fer
setmanes després.

---

## Fase C — Verificacions post-swap (< 5 min)

Executar des del servidor (`ae01farwebsrv`):
```bash
# SAP respon a la URL principal
curl -sS -H "Host: comandes.agrienergia.local" http://127.0.0.1/ajuda | head -30
# Esperat: HTML de la pàgina d'ajuda (cadena SAP-distintiva).

curl -sS -X POST -H "Host: comandes.agrienergia.local" \
    http://127.0.0.1/api/afegir-palets/<TEST_DOCENTRY>
# Esperat: JSON amb "ok":true.

# Kais respon al fallback
curl -sS -H "Host: comandes-kais.agrienergia.local" http://127.0.0.1/ | head -30
# Esperat: HTML de Kais.
```

Executar des d'un PC Windows (validar DNS + xarxa real):
```powershell
curl.exe http://comandes.agrienergia.local/ajuda
curl.exe http://comandes-kais.agrienergia.local/
```

End-to-end SAP B1:
1. Obrir SAP Fat Client → **Comanda de venda** (una comanda esborrany).
2. Clicar el botó **"Calcular embalatges"**.
3. Verificar que apareix missatge d'èxit a l'StatusBar.
4. Verificar que les línies palet s'han inserit sota `RDR1` (rows amb
   `U_FCAfegit = 'S'`).

Logs (opcional, per observar trànsit real):
```bash
sudo tail -f /var/log/apache2/comandes-venda-sap-access.log
sudo tail -f /var/log/apache2/comandes-venda-access.log
```

---

## Rollback (si SAP peta durant les primeres hores)

**Criteri per fer rollback**: 502/504 recurrents a `comandes.agrienergia.local`,
tracebacks Python al `journalctl -u comandes-venda-sap`, o el consultor
comunica que el botó B1UP retorna errors sistemàtics.

### Passos rollback (< 5 min)
```bash
# 1. Desactivar SAP a Apache
sudo a2dissite comandes-venda-sap.conf

# 2. Revertir el ServerName de Kais
sudo nano /etc/apache2/sites-available/comandes-venda.conf
# Canviar: ServerName comandes-kais.agrienergia.local
#      → ServerName comandes.agrienergia.local

# 3. Recarregar Apache
sudo apachectl configtest && sudo systemctl reload apache2

# 4. Verificar Kais respon a la URL principal
curl -sS -H "Host: comandes.agrienergia.local" http://127.0.0.1/ | head -30
```

**Estat post-rollback**: Kais torna a servir `comandes.agrienergia.local`. El
botó B1UP:
- Si apunta a `192.168.11.244:5002` (IP directa, el cas recomanat): segueix
  funcionant, perquè Gunicorn de SAP continua actiu i el rollback no el toca.
- Si apunta a `comandes-sap.agrienergia.local` (l'alias del pas B.7): també
  segueix funcionant, perquè aquest nom continua servint SAP.
- Si algú l'hagués apuntat a `comandes.agrienergia.local`: retornaria 404/HTML de
  Kais, que no té l'endpoint `/api/afegir-palets/`. És exactament el motiu de no
  fer-ho.

---

## Post-swap (dies següents)

- Monitorar `/var/log/apache2/comandes-venda-sap-error.log` durant una setmana.
- Verificar que `logrotate` funciona correctament (dilluns): els fitxers de la
  setmana anterior han de tenir extensió `.1.gz`.
  ```bash
  ls -la /var/www/comandes-venda-sap/*.log*
  ```
- Comunicar la nova URL secundària `comandes-kais.agrienergia.local` als
  usuaris (per si algú necessita consultar dades històriques via Kais).

---

## Contactes

- **Desenvolupador / mantenidor**: Oscar Hijazo (`ohijazo@agrienergia.com`)
- **Consultor B1UP**: [pendent d'assignar per Sistemes]
- **Sistemes / DNS**: [equip intern responsable de `agrienergia.local`]
