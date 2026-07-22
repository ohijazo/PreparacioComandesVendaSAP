# Configuració del servei de correu (Microsoft Graph + App Registration)

Aquest motor envia correus de **sol·licitud d'autorització** per a comandes amb pes < 500 kg directament a Microsoft Graph API, autenticant-se amb una **App Registration** d'Azure AD via OAuth2 (client credentials flow).

> Backend anterior: Power Automate (HTTP webhook). Migrat a Graph API per simplificar i guanyar robustesa.

---

## 1. App Registration

L'aplicació `Motor Comandes Agrienergia` ja està creada al tenant amb:

- **Tenant ID**: identificador del tenant Microsoft 365.
- **Client ID** (Application ID): identificador de l'App Registration.
- **Client Secret**: secret generat (té data d'expiració — caldrà rotar-lo).
- **Permís API**: `Microsoft Graph` → `Mail.Send` (tipus **Application**, amb **admin consent**).

Aquests 3 valors van al `.env`:

```
MAIL_TENANT_ID=<tenant id>
MAIL_CLIENT_ID=<client id>
MAIL_CLIENT_SECRET=<client secret>
```

---

## 2. Bústia remitent

L'App Registration amb `Mail.Send` (Application) pot enviar correu en nom de **qualsevol usuari** del tenant. La bústia que volem usar és:

```
MAIL_FROM_EMAIL=farinera@grupagrienergia.onmicrosoft.com
```

Aquesta variable correspon a l'UPN del compte M365. El correu sortirà amb el From d'aquest usuari (o de l'àlies primari si està configurat com a tal — sovint `farinera@agrienergia.com`).

> **Recomanació de seguretat**: restringir el permís `Mail.Send` només a la bústia `farinera@...` mitjançant *Application Access Policy* (PowerShell `New-ApplicationAccessPolicy`). Així si el secret es compromet, l'atacant no pot enviar correu com altres usuaris del tenant.

---

## 3. Destinataris i defaults UI

```
MAIL_TO=ogirona@agrienergia.com
MAIL_CC=lbutinya@agrienergia.com,ldamon@agrienergia.com
```

Aquests valors pre-poblen el modal del motor. L'operari els pot editar abans d'enviar (camps oberts a la previsualització).

---

## 4. Flux intern

```
[Motor]
   │
   │ 1. POST /api/sol-licitar-autoritzacio/<serie/num>
   ▼
[mailer.enviar_correu_autoritzacio]
   │
   │ 2. POST https://login.microsoftonline.com/<tenant>/oauth2/v2.0/token
   │    (client_credentials, scope=https://graph.microsoft.com/.default)
   │ → access_token (cachejat 1h)
   │
   │ 3. POST https://graph.microsoft.com/v1.0/users/<from>/sendMail
   │    Authorization: Bearer <token>
   │    Body: { message: { subject, body(HTML), toRecipients, ccRecipients } }
   │ → 202 Accepted
   ▼
[Bústia farinera@...]  →  Outlook entrega → destinataris
```

---

## 5. Diagnòstic ràpid

### Token KO (auth)

Si veus al log `Graph auth: ... HTTP 401`:

- `Client Secret` caducat o malament copiat.
- `Tenant ID` o `Client ID` incorrectes.

### Mail.Send KO (autorització)

Si `Graph sendMail HTTP 403`:

- Falta l'admin consent del permís `Mail.Send` (Application).
- La bústia `MAIL_FROM_EMAIL` no és un usuari vàlid del tenant.
- Si tens *Application Access Policy* configurada, comprova que la bústia està dins l'àmbit permès.

### Test ràpid amb curl

```bash
# 1. Obtenir token
curl -X POST "https://login.microsoftonline.com/<TENANT_ID>/oauth2/v2.0/token" \
  -d "client_id=<CLIENT_ID>" \
  -d "client_secret=<CLIENT_SECRET>" \
  -d "scope=https://graph.microsoft.com/.default" \
  -d "grant_type=client_credentials"

# 2. Enviar correu (amb el token obtingut)
curl -X POST "https://graph.microsoft.com/v1.0/users/farinera@grupagrienergia.onmicrosoft.com/sendMail" \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "message": {
      "subject": "Test des de curl",
      "body": {"contentType":"HTML","content":"<p>Hola</p>"},
      "toRecipients": [{"emailAddress":{"address":"ohijazo@agrienergia.com"}}]
    },
    "saveToSentItems": true
  }'
```

Resposta esperada del segon comandament: HTTP 202 (sense cos).

---

## 6. Rotació del Client Secret

El Client Secret té data d'expiració (per defecte 24 mesos al portal). Quan estigui a punt de caducar:

1. Anar al portal Azure → App Registrations → `Motor Comandes Agrienergia` → **Certificates & secrets** → **+ New client secret**.
2. Copiar el `Value` (només es veu una vegada).
3. Actualitzar `MAIL_CLIENT_SECRET` al `.env` del servidor.
4. Reiniciar el servei (`sudo systemctl restart comandes-venda.service`).
5. Esborrar el secret antic del portal un cop confirmat que el nou funciona.
