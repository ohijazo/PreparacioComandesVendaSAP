# Arquitectura de xarxa del servidor `ae01farwebsrv`

> Estat verificat el 29-09-2026 **des de dins del servidor** (`ss -tlnp`,
> `apachectl -S`, `/etc/apache2/sites-enabled/`). Una auditoria feta el mateix dia
> només des de fora va concloure erròniament que no hi havia Apache; veure
> `tasks/lessons.md` L12 per què les capçaleres HTTP no ho poden dir.

## Com està muntat

**Apache fa de reverse proxy al port 80** amb VirtualHosts per nom. Cada aplicació
és un Gunicorn escoltant a `127.0.0.1` al seu port, i Apache l'encamina segons el
`ServerName`. Al servidor hi conviuen deu aplicacions (llista verificada amb
`apachectl -S` el 30-09-2026).

```
                 Apache  *:80  (NameVirtualHost)
                 ─────────────────────────────────
  agrupacions-sap.agrienergia.local ──▶ agrupacio-carregues-sap.conf  ← default server
  agrupacions.agrienergia.local ──────▶ agrupacio-carregues.conf
  comandessap.agrienergia.local ──────▶ comandes-venda-sap.conf  → 127.0.0.1:5002  SAP
  comandes.agrienergia.local ─────────▶ comandes-venda.conf      → 127.0.0.1:5001  Kais
  deca.agrienergia.local ─────────────▶ deca.conf
  fitxesfc.agrienergia.local ─────────▶ fitxes-tecniques.conf
  labfc.agrienergia.local ────────────▶ labfc.conf
  preus.agrienergia.local ────────────▶ zz-actualitzador-preus-sap.conf
  visitesfc.agrienergia.local ────────▶ visites.conf
```

El **default server** — qui contesta un `Host` que no casa cap `ServerName`, per
exemple una petició feta per IP — és `agrupacio-carregues-sap.conf`, per ser el
primer fitxer per ordre alfabètic. Ull amb això quan es proven coses per IP: no
respon el que un espera. Va canviar sol quan es va afegir la variant SAP
d'agrupacions, perquè `agrupacio-carregues-sap.conf` < `agrupacio-carregues.conf`
(el guionet va abans que el punt).

Diverses d'aquestes aplicacions tenen variant Kais i variant SAP convivint, com
les comandes de venda.

## Estat de la variant SAP

| Element | Estat |
|---|---|
| Servei | `comandes-venda-sap.service`, Gunicorn gthread 2×4, `wsgi:app` |
| Socket | `0.0.0.0:5002` |
| Vhost d'Apache | `comandes-venda-sap.conf`, actiu des del 30-09-2026 (pendent que el DNS resolgui) |
| Directori | `/var/www/comandes-venda-sap` |

El bind és `0.0.0.0` i no `127.0.0.1` perquè el botó B1UP (UF-038) crida
`http://192.168.11.244:5002/api/afegir-palets/<DocEntry>` per IP directa. Tancar-lo
abans de reapuntar la UF-038 mata el botó.

## Estat objectiu: SAP amb nom propi

**Decisió del 30-09-2026**: no es toca `comandes.agrienergia.local`. Les dues
variants conviuen, cadascuna amb el seu nom.

```
  comandes.agrienergia.local    ─────▶ comandes-venda.conf     → 127.0.0.1:5001  Kais
  comandessap.agrienergia.local ─────▶ comandes-venda-sap.conf → 127.0.0.1:5002  SAP
```

Cal **un sol registre DNS nou**, `comandessap.agrienergia.local` → la mateixa
`192.168.11.244`: el que separa les dues aplicacions és el `ServerName` del vhost,
no la xarxa. Kais no es toca gens.

El vhost es pot activar **abans** que el DNS existeixi, sense afectar ningú:
Apache només encamina pel `Host` que li arriba i cap client enviarà aquest nom
fins que resolgui, així que es pot validar tot el camí amb
`curl -H "Host: comandessap.agrienergia.local"`.

Procediment: `docs/runbook_url_propia_sap.md`. Petició per Sistemes:
`docs/peticio_dns_sistemes.md`.

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
| `apache/comandes-venda-sap.conf` | Vhost de SAP (`ServerName comandessap.agrienergia.local`). Es pot activar abans del DNS. |
| `logrotate/comandes-venda-sap` | Rotació setmanal dels logs de Gunicorn |
