# Deployment del worker de sync SAP

Guia per desplegar `run_sync.py` com a servei Windows amb NSSM.

## Prerequisits

1. **Motor SAP funcionant** — variant SAP validada (`P:\preparacioComandesVendaSAP`) amb `.env` configurat.
2. **NSSM instal·lat** — descarregable de <https://nssm.cc/download>. Un cop descarregat, posar `nssm.exe` al PATH (o usar `-NssmPath` a l'script).
3. **Virtualenv Python** — recomanat, a `venv\` dins el projecte. Si no existeix, l'script usarà el `python` del PATH.
4. **UDFs a SAP creats** — pel consultor SAP: `ORDR.U_FCCalcular`, `ORDR.U_FCEmbalatgeResum`, `ORDR.U_FCEmbalatgeEstat`. Sense això el worker corre però no fa res útil.
5. **Credencials Service Layer** — al `.env`:
   ```
   SAP_SL_URL=https://<sap-host>:50000/b1s/v2
   SAP_SL_COMPANY=DB_FARINERA_TEST
   SAP_SL_USER=<user_sl>
   SAP_SL_PASSWORD=<pwd_sl>
   SAP_SL_VERIFY_SSL=true
   SAP_SL_TIMEOUT=15
   ```

## Prova prèvia (recomanat)

Abans d'instal·lar com a servei, provar manualment:

```powershell
# Verificar que arrenca i fa una passada sense escriure
.\venv\Scripts\python.exe run_sync.py --once --dry-run

# Un cop tot OK, provar una passada real
.\venv\Scripts\python.exe run_sync.py --once
```

Els primers avisos esperats:
- Si el UDF `U_FCCalcular` no existeix a SAP: log warning + `trobades: 0`.
- Si les credencials SL no són vàlides: fallada immediata al login.

## Instal·lació del servei

Obrir PowerShell **com a Administrador** i executar:

```powershell
cd P:\preparacioComandesVendaSAP
.\scripts\install_sync_service.ps1
```

Això farà:
- Registre del servei `MotorComandesSyncSAP` a Windows.
- `AppDirectory` al projecte.
- Logs a `logs\sync_worker.log` i `logs\sync_worker.err.log`.
- **Rotació de logs**: 5 MB × 5 fitxers (~25 MB màxim).
- **Restart automàtic** en cas d'error (throttle 10s).
- **Startup automàtic** a l'inici de Windows.

Verificació post-instal·lació:

```powershell
Get-Service MotorComandesSyncSAP
# Status: Running
```

## Operativa diària

```powershell
# Veure logs en directe
Get-Content P:\preparacioComandesVendaSAP\logs\sync_worker.log -Tail 20 -Wait

# Estat del servei
Get-Service MotorComandesSyncSAP

# Reiniciar (per ex. després d'un canvi a .env)
nssm restart MotorComandesSyncSAP

# Aturar
nssm stop MotorComandesSyncSAP

# Arrencar
nssm start MotorComandesSyncSAP
```

## Actualització de codi

Després d'un `git pull` amb canvis al worker:

```powershell
# El servei es reinicia automàticament amb el codi nou:
nssm restart MotorComandesSyncSAP
```

Si es canvien dependències (`requirements.txt`):

```powershell
.\venv\Scripts\pip.exe install -r requirements.txt
nssm restart MotorComandesSyncSAP
```

## Desinstal·lació

```powershell
.\scripts\install_sync_service.ps1 -Uninstall
```

## Troubleshooting

### El servei arrenca però no fa res
- Verificar que el UDF `ORDR.U_FCCalcular` existeix a SAP (`SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='ORDR' AND COLUMN_NAME='U_FCCalcular'`).
- Verificar que hi ha comandes marcades a `S`.
- Al log hauria d'aparèixer `UDF ORDR.U_FCCalcular NO existeix — obtenir_comandes_a_calcular retornarà []`.

### Fallada al login Service Layer
- Verificar `SAP_SL_URL`, `SAP_SL_COMPANY`, `SAP_SL_USER`, `SAP_SL_PASSWORD` al `.env`.
- Si el certificat SSL és auto-signat: `SAP_SL_VERIFY_SSL=false`.
- Provar amb curl per confirmar accessibilitat: `curl -k <SAP_SL_URL>/`.

### Errors intermitents 5xx
- El worker ja té reintent automàtic amb backoff (3 intents).
- Si persisteix: verificar càrrega del servidor SAP i xarxa.

### El servei no arrenca després d'un reboot
- Verificar `Get-Service MotorComandesSyncSAP` — Status i StartType (`Automatic`).
- Els logs a `logs\sync_worker.err.log` haurien de tenir la causa.

### Recuperació d'una situació dolenta
```powershell
# Si el servei està en loop de crash-restart
nssm stop MotorComandesSyncSAP
# Corregir la causa (ex: .env, credencials, connectivity)
nssm start MotorComandesSyncSAP
```

## Paràmetres avançats de `run_sync.py`

Editable via `nssm edit MotorComandesSyncSAP` → pestanya "Arguments":

- `--interval 5` — polling cada 5s (default 10s). Reduir per més reactivitat, augmentar per menys càrrega.
- `--max-per-pass 20` — màxim comandes per passada (default 50). Útil per limitar càrrega al backfill inicial.
- `--dry-run` — mode simulació (útil temporalment per debug).
- `--log-level DEBUG` — logs més verbosos.

## Alternativa: Linux (systemd)

Si un dia es migra a Linux, l'equivalent seria un unit file systemd. Base:

```ini
# /etc/systemd/system/motor-comandes-sync.service
[Unit]
Description=Motor Comandes — Sync SAP
After=network-online.target

[Service]
Type=simple
User=motorapp
WorkingDirectory=/opt/preparacioComandesVendaSAP
ExecStart=/opt/preparacioComandesVendaSAP/venv/bin/python /opt/preparacioComandesVendaSAP/run_sync.py
Restart=on-failure
RestartSec=10
StandardOutput=append:/var/log/motor-sync.log
StandardError=append:/var/log/motor-sync.err.log

[Install]
WantedBy=multi-user.target
```

## Actualitzat

2026-07-27 — Fase 2.6 tancada. Deployment operatiu (esperant creació d'UDFs a SAP + credencials SL).
