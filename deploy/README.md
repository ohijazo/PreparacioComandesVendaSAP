# Arquitectura de xarxa del servidor `ae01farwebsrv`

> Verificat el 29-09-2026 sondejant el servidor des de fora (capçaleres HTTP i
> ports oberts). Abans d'aquesta data, el repo documentava una arquitectura amb
> Apache com a reverse proxy que **mai va existir** al servidor.

## Com és de veritat

**No hi ha Apache ni nginx.** Cada aplicació és un Gunicorn que escolta
directament al seu socket. No hi ha encaminament per nom de host: qualsevol
capçalera `Host` que arribi a `192.168.11.244:80` la contesta Kais.

```
                      ae01farwebsrv  (192.168.11.244)
                      ───────────────────────────────
  comandes.agrienergia.local ──▶ 192.168.11.244:80 ──▶ gunicorn  Kais
                                                       /var/www/comandes-venda
                                                       comandes-venda.service

  comandes-sap.agrienergia.local ▶ 192.168.11.245:80 ─▶ gunicorn  SAP
       (IP secundària)                                  /var/www/comandes-venda-sap
                                 192.168.11.244:5002 ─▶ comandes-venda-sap.service
       (bind heretat del botó B1UP)
```

Els dos Gunicorn escolten al port 80 **d'IPs diferents**, així que no es disputen
res. Kais no s'ha de tocar per donar una URL pròpia a SAP: aquest és tot el motiu
de la IP secundària.

## Ports

| Socket | Servei | Qui hi arriba |
|---|---|---|
| `192.168.11.244:80` | Kais | Usuaris de `comandes.agrienergia.local` |
| `192.168.11.245:80` | SAP | Usuaris de `comandes-sap.agrienergia.local` |
| `0.0.0.0:5002` | SAP | Botó B1UP (UF-038), que apunta a la IP directa |

El bind `:5002` és transitori. Quan el consultor reapunti la UF-038 a
`http://comandes-sap.agrienergia.local/api/afegir-palets/`, es pot retirar amb un
`--reinstall-service` passant `LEGACY_BIND` buit.

## Prerequisit: l'àlies d'IP

La IP secundària l'ha de configurar Sistemes al servidor (netplan). No la crea el
`deploy.sh` — només comprova que existeixi i avorta amb un error clar si no hi és,
perquè un Gunicorn que no pot lligar-se al socket entra en bucle de reinicis.

```yaml
# /etc/netplan/*.yaml — afegir la segona adreça a la interfície existent
      addresses:
        - 192.168.11.244/24
        - 192.168.11.245/24      # ← SAP
```

```bash
sudo netplan apply
ip -o addr show | grep 192.168.11.245     # ha de retornar una línia
```

## Comandaments

```bash
# Actualitzar codi (git pull + restart). No toca la unit systemd.
sudo bash /var/www/comandes-venda-sap/deploy.sh

# Reescriure la unit systemd i reiniciar. Repetible i idempotent.
sudo bash /var/www/comandes-venda-sap/deploy.sh --reinstall-service

# El mateix, afegint el bind a la IP secundària (port 80).
sudo SAP_BIND_IP=192.168.11.245 bash /var/www/comandes-venda-sap/deploy.sh --reinstall-service
```

## Per què no un reverse proxy

Posar Apache o nginx al davant del port 80 hauria obligat a moure el Gunicorn de
Kais a `127.0.0.1:5001`, és a dir, a tocar la configuració d'un servei que ha de
quedar intacte fins al novembre de 2026, i a obrir una finestra de tall per a
usuaris que ara mateix no tenen cap problema.

Si algun dia cal HTTPS, autenticació centralitzada o un únic punt d'entrada, un
reverse proxy tornarà a tenir sentit. Mentre l'únic requisit sigui "dues apps amb
dues URLs a la xarxa interna", la IP secundària ho resol sense tocar Kais.

Les configuracions d'Apache que hi havia en aquest directori es van eliminar el
29-09-2026 perquè descrivien una arquitectura inexistent (el runbook de swap
ordenava `a2ensite` sobre un Apache que no hi era). Queden a l'històric de git.
