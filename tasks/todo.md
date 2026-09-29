# Producció: Gunicorn + swap de la URL a SAP (29-09-2026)

## Objectiu

Que `http://comandes.agrienergia.local/` — la URL que ja fan servir els usuaris —
serveixi la variant SAP, amb la de Kais viva en paral·lel a
`comandes-kais.agrienergia.local`. Les dues han de conviure (Kais viu fins al
novembre de 2026).

## Estat inicial trobat

El servidor corria `1b3c6d6` (15-09) i encara amb el **dev server de Flask**, tot i
que el repo definia Gunicorn des de feia mesos.

**Causa arrel**: el camí d'actualització de `deploy.sh` fa `git pull` +
`systemctl restart` però **no reescriu la unit systemd**. La definició amb Gunicorn
només es creava a `--first-install`, i el servidor es va instal·lar abans que
existís. Cap `deploy.sh` hi arribava mai.

## Fet

- [x] Auditar l'estat del servidor
- [x] `app.py`: fix — `/api/admin/actualitzar` reiniciava `comandes-venda` (Kais,
      **producció**) en lloc de `comandes-venda-sap`. Amb botó a la UI i `sudoers`
      concedit. Lliçó L11.
- [x] `deploy.sh`: `write_service_unit()` com a font única de la unit, flag
      `--reinstall-service` repetible, socket via `BIND_ADDR`, avís si la unit no
      fa servir Gunicorn
- [x] Desplegats 5 commits al servidor: `1b3c6d6` → `a33c5e0`
- [x] Migrat a Gunicorn (`--reinstall-service`) i verificat des de fora:
      `Server: gunicorn`, `/api/admin/versio` → `a33c5e0`
- [x] `deploy/README.md`: topologia real d'Apache i estat objectiu del swap
- [x] Runbook actualitzat (prerequisit + pas B.7 del botó B1UP)
- [x] `docs/peticio_dns_sistemes.md`: petició d'un registre DNS
- [x] `docs/Desplegament_SAP_Sistemes.pdf` (10 pàgines) + el seu generador
- [x] `tasks/lessons.md`: L11 i L12
- [ ] **Swap** — pendent del registre DNS de Sistemes

## L'error que va costar més

Vaig auditar el servidor **només des de fora** (capçaleres HTTP + sondeig de
ports) i vaig concloure que no hi havia Apache i que el Gunicorn de Kais ocupava
`0.0.0.0:80`. Sobre aquesta base vaig redissenyar la convivència amb una IP
secundària i `CAP_NET_BIND_SERVICE`, vaig **esborrar** `deploy/apache/`, vaig
marcar `docs/guia-desplegament-sap.html` com a obsoleta i vaig generar un PDF
demanant a Sistemes una IP que no calia.

Era fals. Hi ha Apache al port 80 amb vhosts per nom i Kais escolta a
`127.0.0.1:5001` — el que el repo ja deia. Les dues proves que em van enganyar:

- **`Server: gunicorn` al port 80.** Apache **no** sobreescriu aquesta capçalera a
  les respostes que proxifica: `mod_proxy` deixa passar la del backend. Només posa
  la seva a les respostes que genera ell.
- **Un `Host` inexistent retornava Kais.** És el comportament normal d'Apache amb
  un `Host` que no casa cap `ServerName`: el serveix el primer vhost que carrega.

Tot revertit. Detall a `tasks/lessons.md` L12, amb la regla: quan una conclusió
meva contradiu la documentació del repo, la hipòtesi per defecte és que
m'equivoco jo.

## Topologia real

```
Apache *:80 (NameVirtualHost)
  agrupacions.agrienergia.local → agrupacio-carregues.conf   ← default server
  comandes.agrienergia.local    → comandes-venda.conf  → 127.0.0.1:5001  Kais
  fitxesfc / labfc / visitesfc  → els seus vhosts
  (cap nom encara)              → comandes-venda-sap.conf → 127.0.0.1:5002  SAP
```

## Per què el swap és senzill

`comandes.agrienergia.local` **ja apunta a `192.168.11.244` i no s'ha de tocar**:
les dues apps viuen a la mateixa IP i és Apache qui decideix quina serveix cada
nom. El swap és moure el `ServerName` d'un vhost a l'altre i un
`systemctl reload apache2`. Kais no s'atura ni es reconfigura el seu servei, i el
rollback és el mateix canvi al revés.

A Sistemes només se li demana **un registre DNS**:
`comandes-kais.agrienergia.local` → la mateixa `192.168.11.244`.

## Pendent

1. **Sistemes**: DNS `comandes-kais.agrienergia.local` → `192.168.11.244`, TTL 300.
2. Backup de la config d'Apache + smoke load test amb Gunicorn.
3. Finestra del swap: Fase B del runbook (~10 min, fora d'hores actives).
4. Opcional i posterior: DNS `comandes-sap.agrienergia.local` + `ServerAlias` +
   UF-038 al nom nou + `BIND_ADDR=127.0.0.1:5002` per tancar Gunicorn darrere
   d'Apache.

## Revisió

### Decisions

- **El botó B1UP no es toca.** Apunta a `192.168.11.244:5002` per IP directa, el
  swap no l'afecta i sobreviu a un rollback. Reapuntar-lo a
  `comandes.agrienergia.local` seria pitjor: quedaria lligat a qui tingui la URL
  històrica i un rollback el faria caure contra Kais, que no té l'endpoint. Si es
  vol treure la IP del codi de B1UP, la via segura és un nom propi de SAP.
- **El socket es queda a `0.0.0.0:5002`** mentre la UF-038 depengui de la IP
  directa. Tancar-lo a `127.0.0.1` és desitjable però mata el botó si es fa abans
  d'hora, així que és un pas posterior i explícit (`BIND_ADDR`).
- **`--reinstall-service` es queda tot i que la resta del redisseny s'ha
  descartat.** Resol un problema que sí que era real i que ja s'ha fet servir: la
  unit systemd no es tornava a escriure mai.

### Fitxers modificats

- `app.py` — fix del servei reiniciat per `/api/admin/actualitzar`
- `deploy.sh` — `write_service_unit()`, `--reinstall-service`, `BIND_ADDR`
- `deploy/README.md` — **nou**, topologia real i estat objectiu
- `docs/runbook_swap_url_produccio.md` — prerequisit + pas B.7
- `docs/peticio_dns_sistemes.md` — **nou**
- `scripts/build_guia_sistemes.py`, `docs/Desplegament_SAP_Sistemes.pdf` — **nous**
- `deploy/apache/comandes-venda-sap.conf` — `ServerAlias` opcional comentat
- `tasks/lessons.md` — L11 i L12
- `CLAUDE.md` — referències als documents nous
