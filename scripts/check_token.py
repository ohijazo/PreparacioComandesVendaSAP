"""Diagnòstic ràpid: obté un token de Microsoft Graph amb les credencials
del .env i mostra els claims (especialment `roles`) per verificar que
l'App Registration té els permisos d'aplicació concedits amb admin consent.

Ús al servidor:
    sudo python3 scripts/check_token.py

Si la línia `Roles:` mostra `['Mail.Send']` → tot OK.
Si mostra `None` o `[]` → l'admin no ha clicat "Grant admin consent".
"""
import base64
import json
import urllib.parse
import urllib.request

ENV_PATH = "/var/www/comandes-venda/.env"


def carregar_env(path):
    env = {}
    with open(path) as f:
        for line in f:
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def main():
    env = carregar_env(ENV_PATH)

    for k in ("MAIL_TENANT_ID", "MAIL_CLIENT_ID", "MAIL_CLIENT_SECRET", "MAIL_FROM_EMAIL"):
        if not env.get(k):
            print(f"FALTA al .env: {k}")
            return

    url = f"https://login.microsoftonline.com/{env['MAIL_TENANT_ID']}/oauth2/v2.0/token"
    data = urllib.parse.urlencode({
        "client_id": env["MAIL_CLIENT_ID"],
        "client_secret": env["MAIL_CLIENT_SECRET"],
        "scope": "https://graph.microsoft.com/.default",
        "grant_type": "client_credentials",
    }).encode()

    try:
        resp = urllib.request.urlopen(urllib.request.Request(url, data=data))
        body = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"ERROR auth HTTP {e.code}: {e.read().decode()[:500]}")
        return
    except Exception as e:
        print(f"ERROR auth: {e}")
        return

    token = body.get("access_token", "")
    print(f"Token rebut: longitud={len(token)}")

    parts = token.split(".")
    if len(parts) < 2:
        print("Token amb format incorrecte")
        return

    payload = parts[1] + "=" * ((4 - len(parts[1]) % 4) % 4)
    claims = json.loads(base64.urlsafe_b64decode(payload))

    print()
    print(f"App display:  {claims.get('app_displayname') or claims.get('appid')}")
    print(f"Tenant ID:    {claims.get('tid')}")
    print(f"Audience:     {claims.get('aud')}")
    print(f"Roles:        {claims.get('roles')}")
    print(f"Issued at:    {claims.get('iat')}")
    print(f"Expires at:   {claims.get('exp')}")
    print()

    roles = claims.get("roles") or []
    if "Mail.Send" in roles:
        print(">>> OK: el token té el rol Mail.Send. El problema NO és l'admin consent.")
        print(">>> Causa probable: Application Access Policy o RBAC for Applications restringint la bústia.")
    else:
        print(">>> PROBLEMA: el token NO té el rol Mail.Send.")
        print(">>> L'admin ha d'anar a l'App Registration → API permissions →")
        print(">>>   1. Comprovar que Mail.Send és de tipus 'Application' (no 'Delegated')")
        print(">>>   2. Clicar 'Grant admin consent for [tenant]'")
        print(">>>   3. Esperar 5-15 min per a propagació")


if __name__ == "__main__":
    main()
