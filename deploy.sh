#!/bin/bash
# ==============================================================
# Script de desplegament - Preparació Comandes Venda **variant SAP**
# ==============================================================
# Ús:   sudo bash deploy.sh [--first-install]
#
#   --first-install   Primera instal·lació (clona repo, crea venv, servei systemd)
#   (sense arguments)  Actualitza a l'última versió de GitHub
#
# NOTA: aquesta és la variant SAP (port 5002). NO tocar Kais (port 5001,
# `/var/www/comandes-venda`, servei `comandes-venda.service`).
# Els mòduls compartits (models/regles/mailer) es resolen via KAIS_APP_PATH
# al `.env` — apuntar a `/var/www/comandes-venda`.
# ==============================================================

set -e

# ---- Configuració ----
REPO_URL="https://github.com/ohijazo/PreparacioComandesVendaSAP.git"
APP_DIR="/var/www/comandes-venda-sap"
SERVICE_NAME="comandes-venda-sap"
PYTHON_BIN="python3"
VENV_DIR="$APP_DIR/venv"
APP_PORT=5002
APP_USER="www-data"
KAIS_PATH="/var/www/comandes-venda"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[AVÍS]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# ---- Verificar que s'executa com a root ----
if [ "$EUID" -ne 0 ]; then
    error "Cal executar amb sudo: sudo bash deploy.sh"
fi

# ==============================================================
# PRIMERA INSTAL·LACIÓ
# ==============================================================
if [ "$1" == "--first-install" ]; then
    info "=== Primera instal·lació ==="

    # Dependències del sistema
    info "Instal·lant dependències del sistema..."
    apt-get update -qq
    apt-get install -y -qq git python3 python3-venv python3-pip > /dev/null

    # Driver ODBC per SQL Server
    if ! odbcinst -q -d 2>/dev/null | grep -qi "ODBC Driver"; then
        info "Instal·lant driver ODBC per SQL Server..."
        curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg
        . /etc/os-release
        echo "deb [arch=amd64 signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/ubuntu/$VERSION_ID/prod $VERSION_CODENAME main" > /etc/apt/sources.list.d/mssql-release.list
        apt-get update -qq
        ACCEPT_EULA=Y apt-get install -y -qq msodbcsql18 unixodbc-dev > /dev/null
        info "Driver ODBC instal·lat"
    else
        info "Driver ODBC ja instal·lat"
    fi

    # Clonar repositori
    if [ -d "$APP_DIR" ]; then
        warn "$APP_DIR ja existeix. Fent backup..."
        mv "$APP_DIR" "$APP_DIR.bak.$(date +%Y%m%d%H%M%S)"
    fi

    info "Clonant repositori..."
    git clone "$REPO_URL" "$APP_DIR"

    # Crear entorn virtual
    info "Creant entorn virtual..."
    $PYTHON_BIN -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --upgrade pip -q
    "$VENV_DIR/bin/pip" install -r "$APP_DIR/requirements.txt" -q

    # Permisos
    chown -R "$APP_USER:$APP_USER" "$APP_DIR"

    # Verificar que Kais existeix (per resoldre imports compartits)
    if [ ! -d "$KAIS_PATH" ]; then
        warn "Kais no trobat a $KAIS_PATH. Els mòduls compartits (models/regles/mailer) fallaran."
        warn "Si Kais és en un altre path, edita KAIS_APP_PATH al .env manualment."
    fi

    # Crear servei systemd
    info "Creant servei systemd..."
    cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<UNIT
[Unit]
Description=Motor Preparació Comandes Venda (variant SAP)
After=network.target

[Service]
Type=simple
User=$APP_USER
WorkingDirectory=$APP_DIR
Environment=KAIS_APP_PATH=$KAIS_PATH
Environment=PORT=$APP_PORT
EnvironmentFile=$APP_DIR/.env
ExecStart=$VENV_DIR/bin/python app.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

    systemctl daemon-reload
    systemctl enable "$SERVICE_NAME"

    # NO arrenquem automàticament: cal .env preparat primer.
    info ""
    info "=== Instal·lació estructural completada ==="
    warn "IMPORTANT: encara falta el fitxer .env amb credencials SAP."
    info "1) Copia el .env de dev a: $APP_DIR/.env"
    info "   (SCP: scp .env $APP_USER@\$(hostname):$APP_DIR/.env)"
    info "2) Assegura permisos: sudo chown $APP_USER:$APP_USER $APP_DIR/.env && sudo chmod 600 $APP_DIR/.env"
    info "3) Arrenca el servei: sudo systemctl start $SERVICE_NAME"
    info "4) Verifica: sudo systemctl status $SERVICE_NAME"
    info "5) Prova endpoint: curl -X POST http://localhost:$APP_PORT/api/afegir-palets/<DocEntry>"
    info ""
    info "Comandes útils:"
    info "  systemctl {start|stop|restart|status} $SERVICE_NAME"
    info "  journalctl -u $SERVICE_NAME -f"
    exit 0
fi

# ==============================================================
# ACTUALITZACIÓ
# ==============================================================
info "=== Actualitzant aplicació ==="

# Verificar que existeix la instal·lació
[ -d "$APP_DIR" ] || error "$APP_DIR no existeix. Executa primer: sudo bash deploy.sh --first-install"
[ -d "$VENV_DIR" ] || error "Entorn virtual no trobat a $VENV_DIR"

cd "$APP_DIR"

# Executem git com a l'usuari propietari (www-data) per evitar
# "dubious ownership" que Git modern rebutja quan root toca un repo
# que pertany a un altre usuari.
GIT_AS_APP="sudo -u $APP_USER git"

# Guardar versió actual
OLD_COMMIT=$($GIT_AS_APP rev-parse --short HEAD 2>/dev/null || echo "desconegut")
info "Versió actual: $OLD_COMMIT"

# Descarregar canvis
info "Descarregant última versió de GitHub..."
$GIT_AS_APP fetch origin
$GIT_AS_APP reset --hard origin/main

NEW_COMMIT=$($GIT_AS_APP rev-parse --short HEAD)
if [ "$OLD_COMMIT" == "$NEW_COMMIT" ]; then
    info "Ja estàs a l'última versió ($NEW_COMMIT). No cal fer res."
    exit 0
fi

info "Nova versió: $NEW_COMMIT"

# Actualitzar dependències si han canviat
if $GIT_AS_APP diff "$OLD_COMMIT" "$NEW_COMMIT" -- requirements.txt | grep -q .; then
    info "Actualitzant dependències Python..."
    "$VENV_DIR/bin/pip" install -r requirements.txt -q
else
    info "Dependències sense canvis"
fi

# Permisos
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

# Reiniciar servei
info "Reiniciant servei..."
systemctl restart "$SERVICE_NAME"
sleep 2

# Verificar que funciona
if systemctl is-active --quiet "$SERVICE_NAME"; then
    info "=== Actualització completada ==="
    info "Versió: $OLD_COMMIT → $NEW_COMMIT"
    info "Canvis: git log --oneline $OLD_COMMIT..$NEW_COMMIT"
else
    error "El servei no ha arrencat correctament. Revisar: sudo journalctl -u $SERVICE_NAME -n 50"
fi
