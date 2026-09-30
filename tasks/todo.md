# Nom propi per a l'aplicació SAP (30-09-2026)

## Objectiu

Que la variant SAP sigui accessible a `http://comandessap.agrienergia.local/` en
lloc de per IP i port. **La URL de producció no es toca**: Kais es queda a
`comandes.agrienergia.local` amb la mateixa configuració i el mateix servei.

Decisió de l'Oscar: el swap que s'havia plantejat abans queda descartat.

## Per què és senzill

Apache ja encamina per nom de host cap a cinc aplicacions del servidor.
Afegir-n'hi una és un VirtualHost nou i un registre DNS cap a **la mateixa IP** —
el que separa les aplicacions és el `ServerName`, no la xarxa.

I el VirtualHost es pot activar **abans** que el DNS existeixi, sense afectar
ningú: cap client enviarà aquest `Host` fins que el nom resolgui, així que tot el
camí (proxy, estàtics, logs) es pot validar amb `curl -H "Host: ..."`.

## Fet al repo

- [x] `deploy/apache/comandes-venda-sap.conf` amb `ServerName comandessap...`
- [x] Eliminat `comandes-venda-kais.conf.reference` (era per al swap)
- [x] `docs/runbook_url_propia_sap.md` (abans `runbook_swap_url_produccio.md`),
      reescrit; el swap queda en un apèndix marcat com a descartat
- [x] `docs/peticio_dns_sistemes.md` — un sol registre
- [x] `docs/Desplegament_SAP_Sistemes.pdf` refet (9 pàgines, sense rastre del swap)
- [x] `deploy/README.md` i `CLAUDE.md` actualitzats

## Pendent

- [ ] **Activar el vhost al servidor** (no depèn del DNS)
- [ ] **Sistemes**: `comandessap.agrienergia.local` → `192.168.11.244`, TTL 300
- [ ] Verificar des d'un PC de la xarxa un cop resolgui
- [ ] Comunicar la URL als usuaris

## Comandaments

```bash
# 1. Portar el vhost al servidor
sudo bash /var/www/comandes-venda-sap/deploy.sh

# 2. Activar-lo
sudo cp /var/www/comandes-venda-sap/deploy/apache/comandes-venda-sap.conf \
    /etc/apache2/sites-available/
sudo a2ensite comandes-venda-sap.conf
sudo apachectl configtest          # ha de dir "Syntax OK"
sudo systemctl reload apache2

# 3. Verificar sense DNS, per capçalera Host
curl -sS -H "Host: comandessap.agrienergia.local" http://127.0.0.1/ajuda | head -5
curl -sS -o /dev/null -w "%{http_code} %{content_type}\n" \
    -H "Host: comandessap.agrienergia.local" http://127.0.0.1/static/css/style.css
curl -sS -H "Host: comandes.agrienergia.local" http://127.0.0.1/ | head -5
sudo apachectl -S | grep comandes
```

Criteri: HTML de SAP, `200 text/css`, HTML de Kais intacte, i els dos vhosts
registrats.

Si `configtest` no diu `Syntax OK`, **no recarregar**: un `reload` amb config
invàlida deixa Apache servint l'antiga, però un `restart` posterior el tombaria i
s'emportaria les altres cinc aplicacions del servidor.

Rollback: `sudo a2dissite comandes-venda-sap.conf` + `reload`. SAP segueix
accessible per `192.168.11.244:5002` i el botó de SAP B1 no se n'assabenta.

## Revisió

### Decisions

- **Nom sense guionet** (`comandessap`, no `comandes-sap`): és el que va demanar
  l'Oscar i encaixa amb l'estil de la resta de noms del servidor.
- **Activar el vhost abans del DNS**: no té cap risc i converteix el dia de l'alta
  en una simple comprovació, en lloc d'un desplegament.
- **El botó B1UP no es toca**: crida l'aplicació per IP i port directes. Reapuntar
  la UF-038 al nom nou és feina posterior i opcional; només llavors té sentit
  tancar Gunicorn a `127.0.0.1:5002`.
- **L'apèndix del swap es conserva**: el procediment és correcte i està verificat
  sobre la topologia real. Esborrar-lo obligaria a refer la investigació si algun
  dia es reobre.

### Pendent d'altres fronts

- Repo de Kais per endreçar: 4 commits sense pujar, arbre brut, i el directori del
  servidor apuntant a la branca `fix/rf4-capacitat-apilament`.
- Dos defectes del motor documentats i no tocats: `art_max_map` fora d'àmbit
  (`regles.py:982` vs `:1332`, amb `NameError` latent) i RF14 sense comprovació
  per article. RF11 es va descartar com a defecte el 29-09 després de comprovar-lo
  amb una comanda real.
