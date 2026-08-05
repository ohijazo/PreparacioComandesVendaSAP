# Runbook — Swap URL `comandes.agrienergia.local` de Kais a SAP

**Objectiu**: moure la URL `http://comandes.agrienergia.local/` de l'app Kais
(port 5001) a l'app SAP (port 5002), deixant Kais accessible com a fallback a
`http://comandes-kais.agrienergia.local/`.

**Duració estimada**: ~10 min. **Rollback**: < 5 min.

**Prerequisit indispensable**: l'app SAP ja ha de córrer en producció seriosa
(Gunicorn + systemd), NO amb el dev server de Flask. Verificar amb
`ss -tlnp | grep 5002` → ha de mostrar `127.0.0.1:5002` (localhost only).
Si mostra `0.0.0.0:5002`, cal completar abans la Fase B d'aquesta guia.

---

## Fase A — Preparació (T-24h abans del swap)

### A.1 DNS
Coordinar amb Sistemes per:
1. Afegir entrada `comandes-kais.agrienergia.local → 192.168.11.244`.
2. Confirmar TTL baix (300 s o menys) per possibles ajusts ràpids.
3. `comandes.agrienergia.local` **ja existeix** — s'aprofita, no es toca.

### A.2 Backup Apache al servidor
```bash
sudo tar czf /root/apache-backup-$(date +%F).tgz \
    /etc/apache2/sites-available /etc/apache2/sites-enabled
```

### A.3 Verificar Gunicorn SAP
```bash
sudo systemctl status comandes-venda-sap        # Active (running)
ss -tlnp | grep 5002                            # 127.0.0.1:5002 (localhost)
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

### B.7 Actualitzar el botó B1UP (UF-038)
**Ho fa el consultor B1UP**. Instrucció:
1. SAP Fat Client → **Boyum IT → B1 Usability Package → Configurator**.
2. **Función → Función Universal → UF-038 "HTTP Motor Embalatges"**.
3. Substituir la línia:
   ```
   "http://192.168.11.244:5002/api/afegir-palets/" + docEntry
   ```
   per:
   ```
   "http://comandes.agrienergia.local/api/afegir-palets/" + docEntry
   ```
4. Clicar **Actualizar**.

Codi C# de referència al repo: `docs/b1up_uf038_calcular_embalatges.cs`.

**Nota**: si el consultor B1UP no està disponible el mateix dia, el botó pot
seguir apuntant a `192.168.11.244:5002` (IP directa) — Gunicorn continua
escoltant allà. El swap DNS no trenca la IP directa.

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
- Si encara apunta a `192.168.11.244:5002` (IP directa): segueix funcionant
  perquè Gunicorn SAP continua actiu.
- Si ja s'havia canviat a `comandes.agrienergia.local`: retornarà 404/HTML de
  Kais (Kais no té l'endpoint `/api/afegir-palets/`). El consultor B1UP ha de
  revertir també la UF-038 a la IP directa mentre s'investiga.

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
