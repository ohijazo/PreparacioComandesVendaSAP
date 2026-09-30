# Petició a Sistemes — registre DNS per a l'aplicació d'embalatges (SAP)

Text preparat per enviar per mail o obrir tiquet. Context tècnic a
`deploy/README.md`; guia completa a `docs/Desplegament_SAP_Sistemes.pdf`.

---

**Assumpte**: Alta de registre DNS `comandessap.agrienergia.local`

Bon dia,

Al servidor `ae01farwebsrv` (`192.168.11.244`) conviuen dues versions de
l'aplicació de càlcul d'embalatges de comandes de venda: la que està en producció
a `http://comandes.agrienergia.local/`, que llegeix les dades de Kais, i una de
nova que llegeix de SAP Business One. Les dues han de seguir funcionant en
paral·lel.

Ara mateix la versió nova només és accessible escrivint la IP i el port
(`http://192.168.11.244:5002/`), cosa incòmoda per als usuaris i fràgil si algun
dia canvia la IP del servidor. Voldríem donar-li un nom propi.

Necessitem **dos registres DNS**, tots dos cap a la mateixa IP:

| Nom | Tipus | Valor | TTL |
|---|---|---|---|
| `comandessap.agrienergia.local` | A | `192.168.11.244` | 300 |
| `agrupacions-sap.agrienergia.local` | A | `192.168.11.244` | 300 |

El segon és per a l'aplicació d'agrupacions de càrregues (variant SAP), que ja
corre al servidor però mai va tenir nom: ara només s'hi arriba per IP. L'app
d'embalatges hi encasta el calendari de càrregues, i amb un nom propi deixa de
dependre de la IP.

És **la mateixa IP** que ja fa servir `comandes.agrienergia.local`. L'Apache del
servidor ja encamina per nom de host cap a l'aplicació que toca —com ja fa amb
`agrupacions`, `fitxesfc`, `labfc` i `visitesfc`— i el VirtualHost nou ja està
configurat i provat, esperant només que el nom resolgui.

**Què NO cal fer:**

- **No cal tocar `comandes.agrienergia.local`.** La versió en producció es queda
  exactament com està, amb el mateix nom i la mateixa configuració.
- No cal cap IP nova ni cap canvi a la configuració de xarxa del servidor.
- No cal obrir ports al tallafocs: és el port 80 que Apache ja fa servir.
- No cal aturar ni reiniciar res de la versió en producció.

Quan estigui donat d'alta, aviseu-me i ho verifico:

```
nslookup comandessap.agrienergia.local
```

Gràcies,
Oscar Hijazo

---

## Seguiment

| Element | Responsable | Estat | Data |
|---|---|---|---|
| Codi al dia al servidor | Oscar | ✅ fet | 29-09-2026 |
| Migració a Gunicorn | Oscar | ✅ fet | 29-09-2026 |
| Fix RF4 desplegat | Oscar | ✅ fet | 29-09-2026 |
| VirtualHost d'Apache activat i provat | Oscar | ⏳ | — |
| DNS `comandessap.agrienergia.local` | Sistemes | ⏳ pendent | — |
| Comunicar la URL nova als usuaris | Oscar | ⏳ | — |

## Més endavant, opcional

El botó "Calcular embalatges" de SAP Business One crida l'aplicació per IP
directa (`192.168.11.244:5002`). Un cop el nom existeixi, el consultor de B1UP el
pot reapuntar a `http://comandessap.agrienergia.local/api/afegir-palets/` i
llavors es pot tancar Gunicorn darrere d'Apache:

```bash
sudo BIND_ADDR=127.0.0.1:5002 bash /var/www/comandes-venda-sap/deploy.sh --reinstall-service
```

No és urgent i no bloqueja res.
