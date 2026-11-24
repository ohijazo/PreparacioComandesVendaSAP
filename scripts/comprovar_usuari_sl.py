"""Comprova que l'usuari del Service Layer del .env pot fer servir el botó.

Només lectura: Login → GET d'una comanda oberta i dels UDFs que escriu el
motor → Logout. No modifica res a SAP.

Ús (al servidor, amb el .env del servei):
    sudo -u www-data /var/www/comandes-venda-sap/venv/bin/python \
        /var/www/comandes-venda-sap/scripts/comprovar_usuari_sl.py

Per provar un usuari nou ABANS de posar-lo al .env (les variables d'entorn
tenen prioritat sobre el .env; `read -s` evita que la contrasenya quedi a
l'historial):
    read -s -p "Contrasenya: " P; echo
    sudo -u www-data env SAP_SL_USER=NOU SAP_SL_PASSWORD="$P" \
        /var/www/comandes-venda-sap/venv/bin/python \
        /var/www/comandes-venda-sap/scripts/comprovar_usuari_sl.py; unset P
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))


def _carregar_env() -> None:
    """Llegeix el .env com `consultes.py`, sense sobreescriure l'entorn.

    No s'importa `consultes`: arrossega `_bootstrap`, que exigeix
    `KAIS_APP_PATH` abans d'haver llegit el .env. El servei no té aquest
    problema perquè systemd li passa el .env (`EnvironmentFile`).
    """
    if not os.path.exists(".env"):
        return
    with open(".env") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip())


def main() -> int:
    _carregar_env()
    from sap_service_layer import SLClient, SLError

    url = os.environ["SAP_SL_URL"]
    company = os.environ["SAP_SL_COMPANY"]
    user = os.environ["SAP_SL_USER"]
    pwd = os.environ["SAP_SL_PASSWORD"]
    verify = os.environ.get("SAP_SL_VERIFY_SSL", "true").lower() not in ("false", "0", "no")
    print(f"Service Layer: {url}  empresa={company}  usuari={user}")

    sl = SLClient(url, company, user, pwd, verify=verify, timeout=15)
    try:
        sl.login()
        print("  OK  Login")
        r = sl._request(
            "GET",
            "Orders?$select=DocEntry,DocNum&$filter=DocumentStatus eq 'bost_Open'&$top=1",
        ).json()
        comandes = r.get("value", [])
        if comandes:
            print(f"  OK  Lectura de comandes (DocEntry={comandes[0]['DocEntry']})")
        else:
            print("  ??  Lectura OK però no hi ha cap comanda oberta")
        for camp in ("FCAfegit", "SEIMotiuPreuZero"):
            r = sl._request(
                "GET",
                f"UserFieldsMD?$select=Name,TableName&$filter=TableName eq 'RDR1' and Name eq '{camp}'",
            ).json()
            estat = "OK " if r.get("value") else "FALTA"
            print(f"  {estat} UDF RDR1.U_{camp}")
    except SLError as e:
        print(f"  ERROR {e} (HTTP {e.status_code}) {e.body}")
        return 1
    finally:
        try:
            sl.logout()
        except Exception:
            pass
    print("Correcte. L'escriptura només es pot validar prement el botó en una comanda.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
