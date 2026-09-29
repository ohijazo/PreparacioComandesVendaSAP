# Arquitectura de xarxa del servidor `ae01farwebsrv`

> Estat verificat el 29-09-2026 **des de dins del servidor** (`ss -tlnp`,
> `apachectl -S`, `/etc/apache2/sites-enabled/`). Una auditoria feta el mateix dia
> només des de fora va concloure erròniament que no hi havia Apache; veure
> `tasks/lessons.md` L12 per què les capçaleres HTTP no ho poden dir.

## Com està muntat

**Apache fa de reverse proxy al port 80** amb VirtualHosts per nom. Cada aplicació
és un Gunicorn escoltant a `127.0.0.1` al seu port, i Apache l'encamina segons el
`ServerName`. Al servidor hi conviuen cinc aplicacions més la variant SAP.

```
                 Apache  *:80  (NameVirtualHost)
                 ─────────────────────────────────
  agrupacions.agrienergia.local ──▶ agrupacio-carregues.conf   ← default server
  comandes.agrienergia.local ─────▶ comandes-venda.conf        → 127.0.0.1:5001  Kais
  fitxesfc.agrienergia.local ─────▶ fitxes-tecniques.conf
  labfc.agrienergia.local ────────▶ labfc.conf
  visitesfc.agrienergia.local ────▶ visites.conf

  (cap vhost encara) ─────────────▶ comandes-venda-sap.conf    → 127.0.0.1:5002  SAP
```

`agrupacions.agrienergia.local` és el **default server**: qualsevol `Host` que no
casi cap `ServerName` — per exemple una petició feta directament per IP — el
serveix aquest vhost. És conseqüència de ser el primer fitxer per ordre alfabètic,
no d'una configuració explícita.

## Estat de la variant SAP

| Element | Estat |
|---|---|
| Servei | `comandes-venda-sap.service`, Gunicorn gthread 2×4, `wsgi:app` |
| Socket | `0.0.0.0:5002` |
| Vhost d'Apache | **cap encara** — només s'hi arriba per `192.168.11.244:5002` |
| Directori | `/var/www/comandes-venda-sap` |

El bind és `0.0.0.0` i no `127.0.0.1` perquè el botó B1UP (UF-038) crida
`http://192.168.11.244:5002/api/afegir-palets/<DocEntry>` per IP directa. Tancar-lo
abans de reapuntar la UF-038 mata el botó.

## Estat objectiu: SAP hereta `comandes.agrienergia.local`

L'objectiu és que la URL que ja fan servir els usuaris serveixi les dades de SAP,
amb Kais viu en paral·lel a un nom secundari.

```
  comandes.agrienergia.local ─────▶ comandes-venda-sap.conf → 127.0.0.1:5002  SAP
  comandes-kais.agrienergia.local ▶ comandes-venda.conf     → 127.0.0.1:5001  Kais
```

**No hi ha canvi de DNS per a la URL principal.** `comandes.agrienergia.local` ja
apunta a `192.168.11.244` i s'hi queda: les dues apps viuen a la mateixa IP i és
Apache qui decideix quina serveix cada nom. L'únic registre nou és
`comandes-kais.agrienergia.local` → la mateixa `192.168.11.244`.

El swap és, doncs, moure el `ServerName` d'un vhost a l'altre i un
`systemctl reload apache2`. Kais no s'atura ni es reconfigura el seu servei.
Procediment complet, amb la finestra i el rollback:
`docs/runbook_swap_url_produccio.md`. Petició per Sistemes:
`docs/peticio_dns_sistemes.md`.

Durant el solapament de 30-60 segons entre els dos `reload`, els dos vhosts
responen al mateix nom i guanya el que Apache carrega primer:
`comandes-venda-sap.conf` < `comandes-venda.conf` per ordre alfabètic (`-` va
abans que `.`), o sigui SAP.

## Comandaments del desplegament

```bash
# Actualitzar codi (git pull + restart). NO toca la unit systemd.
sudo bash /var/www/comandes-venda-sap/deploy.sh

# Reescriure la unit systemd i reiniciar. Repetible i idempotent.
sudo bash /var/www/comandes-venda-sap/deploy.sh --reinstall-service

# El mateix canviant el socket (un cop la UF-038 no depengui de la IP directa).
sudo BIND_ADDR=127.0.0.1:5002 bash .../deploy.sh --reinstall-service
```

`--reinstall-service` existeix perquè el camí d'actualització **no reescriu la
unit**: la definició amb Gunicorn només es creava a `--first-install`, i el
servidor es va instal·lar abans que existís. Per això va córrer mesos amb el dev
server de Flask tot i que el repo ja definia Gunicorn — cap `deploy.sh` hi
arribava.

## Fitxers d'aquest directori

| Fitxer | Rol |
|---|---|
| `apache/comandes-venda-sap.conf` | Vhost de SAP amb `ServerName comandes.agrienergia.local`. S'activa el dia del swap. |
| `apache/comandes-venda-kais.conf.reference` | Còpia de referència del vhost de Kais amb els canvis del swap marcats. **No es desplega.** |
| `logrotate/comandes-venda-sap` | Rotació setmanal dels logs de Gunicorn |
