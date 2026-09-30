# Runbook — Nom propi per a l'aplicació SAP

> **Reescrit el 30-09-2026.** Les versions anteriors d'aquest document plantejaven
> moure `comandes.agrienergia.local` de Kais a SAP. **Aquell swap queda
> descartat**: decisió de l'Oscar, no es toca la URL que ja fan servir els
> usuaris. Les dues variants conviuen amb noms propis. L'apartat final conserva
> el procediment del swap per si algun dia es reobre.

**Objectiu**: que `http://comandessap.agrienergia.local/` serveixi la variant SAP,
mentre `http://comandes.agrienergia.local/` segueix servint Kais exactament com
avui.

**Impacte sobre Kais**: cap. No se li toca el vhost, ni el servei, ni el nom.

Arquitectura del servidor: `deploy/README.md`.

---

## Fase 1 — Activar el VirtualHost (es pot fer ja, sense DNS)

Aquest pas **no afecta ningú** i no cal esperar Sistemes: Apache només encamina
pel `Host` que li arriba, i cap client enviarà `comandessap.agrienergia.local`
fins que el nom resolgui. Serveix per deixar-ho tot muntat i verificat.

### 1.1 Portar el fitxer al servidor
```bash
sudo bash /var/www/comandes-venda-sap/deploy.sh
```

### 1.2 Activar-lo
```bash
sudo cp /var/www/comandes-venda-sap/deploy/apache/comandes-venda-sap.conf \
    /etc/apache2/sites-available/
sudo a2ensite comandes-venda-sap.conf
sudo apachectl configtest
sudo systemctl reload apache2
```

`configtest` ha de dir `Syntax OK`. **Si no ho diu, no recarregar**: un `reload`
amb configuració invàlida deixa Apache servint la config antiga, però un
`restart` posterior el tombaria i s'emportaria les altres cinc aplicacions del
servidor.

`reload` i no `restart`: no dropa connexions actives de cap aplicació.

### 1.3 Verificar el camí sencer, per capçalera `Host`
```bash
# SAP a través d'Apache
curl -sS -H "Host: comandessap.agrienergia.local" http://127.0.0.1/ajuda | head -5

# Estàtics servits per Apache, no per Gunicorn
curl -sS -o /dev/null -w "%{http_code} %{content_type}\n" \
    -H "Host: comandessap.agrienergia.local" http://127.0.0.1/static/css/style.css

# Kais intacte
curl -sS -H "Host: comandes.agrienergia.local" http://127.0.0.1/ | head -5

# Els dos vhosts registrats
sudo apachectl -S | grep comandes
```

Criteri d'acceptació:
- La primera retorna HTML de SAP (el títol porta «(SAP)»).
- La segona retorna `200 text/css`.
- La tercera retorna HTML de Kais, com sempre.
- Apareixen logs nous a `/var/log/apache2/comandes-venda-sap-{access,error}.log`.

### 1.4 Rollback de la Fase 1
```bash
sudo a2dissite comandes-venda-sap.conf
sudo apachectl configtest && sudo systemctl reload apache2
```
SAP segueix accessible per `192.168.11.244:5002` i el botó de SAP B1 no se
n'assabenta. Kais no s'ha tocat en cap moment.

---

## Fase 2 — DNS (ho fa Sistemes)

| Nom | Tipus | Valor | TTL |
|---|---|---|---|
| `comandessap.agrienergia.local` | A | `192.168.11.244` | 300 |

La mateixa IP que `comandes.agrienergia.local`: el que separa les dues
aplicacions és el `ServerName` del vhost, no la xarxa. Petició redactada a
`docs/peticio_dns_sistemes.md`.

Verificació des d'un PC Windows de la xarxa:
```powershell
nslookup comandessap.agrienergia.local
curl.exe http://comandessap.agrienergia.local/ajuda      # HTML de SAP
curl.exe http://comandes.agrienergia.local/              # HTML de Kais
curl.exe http://192.168.11.244:5002/api/admin/versio     # el socket del botó B1UP viu
```

Les tres han de respondre. La tercera és la que garanteix que el botó "Calcular
embalatges" de SAP Business One segueix funcionant.

### Prova funcional a SAP Business One
1. Obrir **Comanda de venda** (una comanda esborrany).
2. Clicar **"Calcular embalatges"**.
3. Verificar el missatge d'èxit a la barra d'estat.
4. Verificar les línies palet inserides a `RDR1` amb `U_FCAfegit = 'S'`.

---

## Fase 3 — Reapuntar el botó B1UP (opcional, sense urgència)

**Ho fa el consultor B1UP.** Mentre no es faci, el botó segueix funcionant per IP
directa i el canvi de nom no l'afecta.

1. SAP Fat Client → **Boyum IT → B1 Usability Package → Configurator**.
2. **Función → Función Universal → UF-038 "HTTP Motor Embalatges"**.
3. Substituir:
   ```
   "http://192.168.11.244:5002/api/afegir-palets/" + docEntry
   ```
   per:
   ```
   "http://comandessap.agrienergia.local/api/afegir-palets/" + docEntry
   ```
4. Clicar **Actualizar**.

Codi C# de referència: `docs/b1up_uf038_calcular_embalatges.cs`.

Un cop verificat, tancar Gunicorn darrere d'Apache perquè deixi d'estar exposat
fora del servidor:
```bash
sudo BIND_ADDR=127.0.0.1:5002 bash /var/www/comandes-venda-sap/deploy.sh --reinstall-service
```

---

## Manteniment

- Logs de Gunicorn: `/var/www/comandes-venda-sap/{access,error}.log`, rotació
  setmanal amb 4 setmanes de retenció (`/etc/logrotate.d/comandes-venda-sap`).
  Comprovació el dilluns: els de la setmana anterior han de tenir extensió
  `.1.gz`.
- Logs d'Apache: `/var/log/apache2/comandes-venda-sap-*.log`.
- Actualitzar l'aplicació: `sudo bash /var/www/comandes-venda-sap/deploy.sh`.
- Reescriure la unit systemd (canvi de socket, migració a Gunicorn):
  `sudo bash /var/www/comandes-venda-sap/deploy.sh --reinstall-service`.

---

## Apèndix — El swap de `comandes.agrienergia.local` (descartat)

Es conserva perquè el procediment és correcte i està verificat sobre la
topologia real, per si algun dia es decideix que SAP hereti la URL històrica.
**No és el pla actual.**

Caldria un registre DNS més (`comandes-kais.agrienergia.local` → `192.168.11.244`)
perquè Kais conservés un nom propi, i llavors:

1. Afegir `ServerAlias comandes.agrienergia.local` al vhost de SAP.
2. Al vhost de Kais (`comandes-venda.conf`), canviar
   `ServerName comandes.agrienergia.local` per
   `ServerName comandes-kais.agrienergia.local` i afegir-hi temporalment
   `ServerAlias comandes.agrienergia.local`.
3. `sudo apachectl configtest && sudo systemctl reload apache2`.
4. Retirar l'àlies temporal de Kais i recarregar un altre cop.

Durant el solapament els dos vhosts responen al mateix nom i guanya el que Apache
carrega primer: `comandes-venda-sap.conf` < `comandes-venda.conf` per ordre
alfabètic (`-` va abans que `.`), o sigui SAP. El rollback és el mateix camí al
revés, en menys de 5 minuts, i Kais no s'atura en cap moment.

---

## Contactes

- **Desenvolupador / mantenidor**: Oscar Hijazo (`ohijazo@agrienergia.com`)
- **Consultor B1UP**: [pendent d'assignar per Sistemes]
- **Sistemes / DNS**: [equip intern responsable de `agrienergia.local`]
