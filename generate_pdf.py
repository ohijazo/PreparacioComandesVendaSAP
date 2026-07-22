"""Genera el PDF de la guia de desplegament."""
from fpdf import FPDF

APP_NAME = "Motor de Preparacio de Comandes de Venda"
APP_DIR = "/var/www/comandes-venda"
SERVICE_NAME = "comandes-venda"
VHOST_NAME = "comandes-venda.conf"
SERVER_NAME = "comandes.agrienergia.local"
GITHUB_REPO = "https://github.com/ohijazo/PreparacioComandesVenda.git"


class GuiaPDF(FPDF):
    def header(self):
        if self.page_no() > 1:
            self.set_font("Helvetica", "I", 8)
            self.set_text_color(150, 150, 150)
            self.cell(0, 8, f"Guia de Desplegament - {APP_NAME}", align="C")
            self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"Pagina {self.page_no()}/{{nb}}", align="C")

    def section_title(self, num, title):
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(43, 108, 176)
        self.cell(0, 10, f"{num}. {title}", new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(43, 108, 176)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(4)

    def sub_title(self, title):
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(45, 55, 72)
        self.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def body_text(self, text):
        self.set_font("Helvetica", "", 10)
        self.set_text_color(26, 32, 44)
        self.multi_cell(0, 5.5, text)
        self.ln(2)

    def code_block(self, text):
        self.set_font("Courier", "", 9)
        self.set_fill_color(26, 32, 44)
        self.set_text_color(226, 232, 240)
        x = self.get_x()
        w = self.w - 20
        lines = text.split("\n")
        h = len(lines) * 5 + 6
        if self.get_y() + h > self.h - 20:
            self.add_page()
        self.rect(x, self.get_y(), w, h, "F")
        self.set_xy(x + 3, self.get_y() + 3)
        for line in lines:
            self.cell(0, 5, line, new_x="LMARGIN", new_y="NEXT")
            self.set_x(x + 3)
        self.set_xy(x, self.get_y() + 3)
        self.set_text_color(26, 32, 44)
        self.ln(3)

    def info_box(self, text, box_type="info"):
        colors = {
            "info": ((235, 248, 255), (49, 130, 206)),
            "warning": ((255, 251, 235), (214, 158, 46)),
            "danger": ((255, 245, 245), (229, 62, 62)),
            "success": ((240, 255, 244), (56, 161, 105)),
        }
        bg, border = colors.get(box_type, colors["info"])
        self.set_fill_color(*bg)
        self.set_draw_color(*border)
        x = self.get_x()
        w = self.w - 20
        self.set_font("Helvetica", "", 9)
        lines = self.multi_cell(w - 10, 5, text, dry_run=True, output="LINES")
        h = len(lines) * 5 + 8
        if self.get_y() + h > self.h - 20:
            self.add_page()
        y = self.get_y()
        self.rect(x, y, w, h, "F")
        self.line(x, y, x, y + h)
        self.set_line_width(1)
        self.set_draw_color(*border)
        self.line(x, y, x, y + h)
        self.set_line_width(0.2)
        self.set_xy(x + 5, y + 4)
        self.set_text_color(*border)
        self.multi_cell(w - 10, 5, text)
        self.set_text_color(26, 32, 44)
        self.set_xy(x, y + h + 2)
        self.ln(2)

    def table(self, headers, rows, col_widths=None):
        if col_widths is None:
            w = (self.w - 20) / len(headers)
            col_widths = [w] * len(headers)
        # Header
        self.set_font("Helvetica", "B", 9)
        self.set_fill_color(237, 242, 247)
        self.set_text_color(45, 55, 72)
        for i, h in enumerate(headers):
            self.cell(col_widths[i], 7, h, border=1, fill=True)
        self.ln()
        # Rows
        self.set_font("Helvetica", "", 9)
        self.set_text_color(26, 32, 44)
        for row in rows:
            for i, cell in enumerate(row):
                if self.get_y() + 7 > self.h - 20:
                    self.add_page()
                self.cell(col_widths[i], 7, str(cell), border=1)
            self.ln()
        self.ln(3)


def generate():
    pdf = GuiaPDF()
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    # ── COVER ──
    pdf.ln(30)
    pdf.set_font("Helvetica", "B", 26)
    pdf.set_text_color(43, 108, 176)
    pdf.cell(0, 12, "Guia de Desplegament", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    pdf.set_font("Helvetica", "", 16)
    pdf.set_text_color(74, 85, 104)
    pdf.cell(0, 10, APP_NAME, align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(15)
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(113, 128, 150)
    pdf.cell(0, 7, "Versio 8  -  Abril 2026", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 7, "Plataforma: Ubuntu Server 24.04 LTS", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 7, "Aplicacio web Python/Flask amb connexio a SQL Server", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(30)
    pdf.set_draw_color(43, 108, 176)
    pdf.line(60, pdf.get_y(), 150, pdf.get_y())
    pdf.ln(10)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(45, 55, 72)
    pdf.cell(0, 7, "Contingut", align="L", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    toc = [
        "1. Requisits de la maquina virtual",
        "2. Arquitectura de l'aplicacio",
        "3. Instal-lacio de paquets",
        "4. Descarrega i configuracio de l'aplicacio",
        "5. Servei systemd amb Gunicorn",
        "6. Apache VirtualHost (proxy invers)",
        "7. Xarxa i tallafocs",
        "8. Llista de verificacio",
        "9. Manteniment i actualitzacions",
        "10. Logs i monitoratge",
        "11. Resolucio de problemes",
        "12. Resum i temps estimats",
    ]
    for item in toc:
        pdf.cell(0, 6, f"  {item}", new_x="LMARGIN", new_y="NEXT")

    pdf.info_box(
        "NOTA: Aquesta aplicacio comparteix servidor amb Lab FC. Molts dels "
        "paquets base (Python, Apache, ODBC Driver, UFW) ja estaran instal-lats. "
        "Les seccions afectades ho indiquen amb un avís.",
        "success",
    )

    # ── 1. REQUISITS VM ──
    pdf.add_page()
    pdf.section_title("1", "Requisits de la maquina virtual")

    pdf.sub_title("Maquinari")
    pdf.table(
        ["Recurs", "Minim", "Recomanat"],
        [
            ["CPU", "2 vCPU", "4 vCPU"],
            ["RAM", "2 GB", "4 GB"],
            ["Disc", "20 GB", "40 GB"],
            ["SO", "Ubuntu Server 24.04 LTS", ""],
        ],
        [40, 50, 50],
    )

    pdf.info_box(
        "Si Lab FC ja esta desplegat en aquesta VM, els recursos ja seran "
        "suficients. Nomes cal afegir ~500 MB d'espai per aquesta aplicacio.",
        "info",
    )

    pdf.sub_title("Programari necessari")
    pdf.table(
        ["Component", "Versio", "Funcio", "Ja instal-lat amb Lab FC?"],
        [
            ["Ubuntu Server", "24.04 LTS", "Sistema operatiu", "Si"],
            ["Python", "3.12+", "Runtime de l'aplicacio", "Si"],
            ["Apache2", "2.4+", "Proxy invers", "Si"],
            ["ODBC Driver 18", "18.x", "Connexio a SQL Server", "No (nou)"],
            ["unixODBC", "2.3+", "Gestor ODBC a Linux", "No (nou)"],
            ["Git", "2.x", "Descarregar el codi", "Si"],
        ],
        [35, 20, 48, 42],
    )

    pdf.sub_title("Connectivitat de xarxa")
    pdf.body_text(
        "- Acces al servidor SQL Server vkais\\kais (port 1433)\n"
        "- Port 80 (Apache) per servir l'aplicacio\n"
        "- Port 5001 (intern, Gunicorn - nomes localhost)\n"
        "- Acces a Internet per descarregar paquets (nomes durant instal-lacio)"
    )

    # ── 2. ARQUITECTURA ──
    pdf.add_page()
    pdf.section_title("2", "Arquitectura de l'aplicacio")

    pdf.body_text(
        "L'aplicacio segueix la mateixa arquitectura que Lab FC: "
        "Apache com a proxy invers davant de Gunicorn, que executa "
        "l'aplicacio Flask. L'unica diferencia es que aquesta aplicacio "
        "es connecta a SQL Server (no PostgreSQL)."
    )

    pdf.code_block(
        "Navegador  --->  Apache (port 80)  --->  Gunicorn (port 5001)\n"
        "                                              |\n"
        "                                        SQL Server\n"
        "                                        vkais\\kais\n"
        "                                        GWSV_AGRI"
    )

    pdf.sub_title("Estructura de directoris")
    pdf.code_block(
        f"{APP_DIR}/\n"
        "  app.py              # Servidor web Flask (punt d'entrada)\n"
        "  motor.py            # Orquestrador principal del calcul\n"
        "  regles.py           # Regles funcionals RF1-RF9\n"
        "  consultes.py        # Consultes SQL i connexio a BD\n"
        "  models.py           # Dataclasses del model de dades\n"
        "  requirements.txt    # Dependencies Python\n"
        "  .env                # Variables de configuracio (ja inclos)\n"
        "  static/             # CSS, JavaScript\n"
        "  templates/          # HTML (Jinja2)\n"
        "  venv/               # Entorn virtual Python"
    )

    pdf.sub_title("Comparativa amb Lab FC")
    pdf.table(
        ["Aspecte", "Lab FC", "Comandes Venda"],
        [
            ["Directori", "/var/www/lab-fc", APP_DIR],
            ["Backend", "Python/Flask", "Python/Flask"],
            ["WSGI", "Gunicorn", "Gunicorn"],
            ["Proxy", "Apache", "Apache"],
            ["Base de dades", "PostgreSQL (local)", "SQL Server (remot)"],
            ["Usuari", "www-data", "www-data"],
            ["Servei", "lab-fc.service", f"{SERVICE_NAME}.service"],
        ],
        [35, 60, 60],
    )

    # ── 3. INSTAL-LACIO PAQUETS ──
    pdf.add_page()
    pdf.section_title("3", "Instal-lacio de paquets")

    pdf.sub_title("3.1 Actualitzar el sistema")
    pdf.code_block("sudo apt update && sudo apt upgrade -y")

    pdf.sub_title("3.2 Paquets base (probablement ja instal-lats)")
    pdf.info_box(
        "Si Lab FC ja esta desplegat, Python, pip, venv, Git, curl i Apache "
        "ja estaran instal-lats. Podeu saltar al pas 3.3.",
        "info",
    )
    pdf.code_block("sudo apt install -y python3 python3-pip python3-venv git curl gnupg2 apache2")

    pdf.sub_title("3.3 Instal-lar el driver ODBC 18 de Microsoft (NOU)")
    pdf.body_text(
        "Aquesta es la unica dependencia nova respecte Lab FC. "
        "Cal instal-lar el driver ODBC per connectar-se a SQL Server."
    )
    pdf.code_block(
        "# Afegir el repositori de Microsoft\n"
        "curl -fsSL https://packages.microsoft.com/keys/microsoft.asc \\\n"
        "  | sudo gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg\n"
        "\n"
        "# Per Ubuntu 24.04:\n"
        'echo "deb [arch=amd64 signed-by=/usr/share/keyrings/microsoft-prod.gpg] \\\n'
        "  https://packages.microsoft.com/ubuntu/24.04/prod noble main\" \\\n"
        "  | sudo tee /etc/apt/sources.list.d/mssql-release.list\n"
        "\n"
        "# Instal-lar\n"
        "sudo apt update\n"
        "sudo ACCEPT_EULA=Y apt install -y msodbcsql18 unixodbc-dev"
    )

    pdf.sub_title("3.4 Verificar el driver ODBC")
    pdf.code_block("odbcinst -q -d\n# Ha d'apareixer: [ODBC Driver 18 for SQL Server]")

    # ── 4. DESCARREGA I CONFIGURACIO ──
    pdf.add_page()
    pdf.section_title("4", "Descarrega i configuracio de l'aplicacio")

    pdf.sub_title("4.1 Clonar el repositori")
    pdf.body_text(
        "Tot el codi font, configuracio i dependencies es troben al repositori GitHub. "
        "El fitxer .env ja esta configurat amb les dades de connexio correctes."
    )
    pdf.code_block(
        f"# Crear directori (mateix patro que Lab FC)\n"
        f"sudo mkdir -p {APP_DIR}\n"
        f"cd {APP_DIR}\n"
        f"\n"
        f"# Clonar el repositori (conte tot el necessari)\n"
        f"sudo git clone {GITHUB_REPO} .\n"
        f"\n"
        f"# Assignar propietat a www-data (mateix usuari que Lab FC)\n"
        f"sudo chown -R www-data:www-data {APP_DIR}"
    )

    pdf.info_box(
        "IMPORTANT: No modifiqueu cap fitxer del repositori. El fitxer .env ja "
        "conte la configuracio de connexio a la base de dades (servidor, base de "
        "dades, credencials). Si cal canviar alguna dada, contacteu amb el "
        "responsable de l'aplicacio.",
        "warning",
    )

    pdf.sub_title("4.2 Crear entorn virtual i instal-lar dependencies")
    pdf.code_block(
        f"cd {APP_DIR}\n"
        f"sudo -u www-data python3 -m venv venv\n"
        f"sudo -u www-data venv/bin/pip install --upgrade pip\n"
        f"sudo -u www-data venv/bin/pip install -r requirements.txt\n"
        f"sudo -u www-data venv/bin/pip install gunicorn"
    )

    pdf.sub_title("4.3 Protegir el fitxer .env")
    pdf.code_block(
        f"sudo chmod 640 {APP_DIR}/.env\n"
        f"sudo chown www-data:www-data {APP_DIR}/.env"
    )

    pdf.sub_title("4.4 Variables de configuracio (referencia)")
    pdf.body_text("Aquestes variables ja estan definides al .env. Nomes com a referencia:")
    pdf.table(
        ["Variable", "Descripcio"],
        [
            ["SQL_SERVER", "Servidor SQL Server (instancia)"],
            ["SQL_DATABASE", "Base de dades"],
            ["SQL_USER", "Usuari SQL (nomes lectura)"],
            ["SQL_PASSWORD", "Contrasenya SQL"],
        ],
        [50, 100],
    )

    pdf.info_box(
        "Permisos SQL: L'usuari nomes necessita permisos de LECTURA (SELECT) sobre:\n"
        "ek_Pedido, ek_PedidoLineas, ARTICLES, CLIENVIO, articli,\n"
        "info_clienvio, INF_ARTICULO, INFOANEX, PREUSCLIENTS.",
        "info",
    )

    pdf.sub_title("4.5 Verificar la connexio a SQL Server")
    pdf.code_block(
        f"cd {APP_DIR}\n"
        'sudo -u www-data venv/bin/python -c "\n'
        "from consultes import connectar\n"
        "conn = connectar()\n"
        "print('Connexio OK')\n"
        'conn.close()\n'
        '"'
    )

    # ── 5. SERVEI SYSTEMD ──
    pdf.add_page()
    pdf.section_title("5", "Servei systemd amb Gunicorn")

    pdf.body_text(
        "Igual que Lab FC, configurem un servei systemd que executa "
        "Gunicorn com a servidor WSGI."
    )

    pdf.sub_title("5.1 Crear el fitxer de servei")
    pdf.code_block(f"sudo nano /etc/systemd/system/{SERVICE_NAME}.service")
    pdf.body_text("Contingut:")
    pdf.code_block(
        "[Unit]\n"
        f"Description={APP_NAME}\n"
        "After=network.target\n"
        "\n"
        "[Service]\n"
        "Type=simple\n"
        "User=www-data\n"
        "Group=www-data\n"
        f"WorkingDirectory={APP_DIR}\n"
        f"EnvironmentFile={APP_DIR}/.env\n"
        f"ExecStart={APP_DIR}/venv/bin/gunicorn \\\n"
        "    --bind 127.0.0.1:5001 \\\n"
        "    --workers 1 \\\n"
        "    --timeout 120 \\\n"
        f"    --access-logfile {APP_DIR}/access.log \\\n"
        f"    --error-logfile {APP_DIR}/error.log \\\n"
        "    app:app\n"
        "Restart=always\n"
        "RestartSec=5\n"
        "\n"
        "[Install]\n"
        "WantedBy=multi-user.target"
    )

    pdf.info_box(
        "Nota: Gunicorn escolta a 127.0.0.1:5001 (nomes localhost). "
        "L'acces extern es fa a traves d'Apache.",
        "info",
    )

    pdf.sub_title("5.2 Activar i iniciar el servei")
    pdf.code_block(
        "sudo systemctl daemon-reload\n"
        f"sudo systemctl enable {SERVICE_NAME}\n"
        f"sudo systemctl start {SERVICE_NAME}\n"
        f"sudo systemctl status {SERVICE_NAME}"
    )

    pdf.sub_title("5.3 Comandes utils del servei")
    pdf.table(
        ["Comanda", "Accio"],
        [
            [f"sudo systemctl start {SERVICE_NAME}", "Iniciar"],
            [f"sudo systemctl stop {SERVICE_NAME}", "Aturar"],
            [f"sudo systemctl restart {SERVICE_NAME}", "Reiniciar"],
            [f"sudo systemctl status {SERVICE_NAME}", "Veure estat"],
            [f"journalctl -u {SERVICE_NAME} -f", "Logs en temps real"],
        ],
        [110, 40],
    )

    # ── 6. APACHE VIRTUALHOST ──
    pdf.add_page()
    pdf.section_title("6", "Apache VirtualHost (proxy invers)")

    pdf.body_text(
        "Configurem Apache com a proxy invers, igual que per Lab FC. "
        "Els moduls necessaris probablement ja estan activats."
    )

    pdf.sub_title("6.1 Activar moduls necessaris")
    pdf.code_block(
        "# Probablement ja activats per Lab FC\n"
        "sudo a2enmod proxy proxy_http rewrite\n"
        "sudo systemctl restart apache2"
    )

    pdf.sub_title("6.2 Crear el VirtualHost")
    pdf.code_block(f"sudo nano /etc/apache2/sites-available/{VHOST_NAME}")
    pdf.body_text("Contingut:")
    pdf.code_block(
        "<VirtualHost *:80>\n"
        f"    ServerName {SERVER_NAME}\n"
        "\n"
        "    ProxyPreserveHost On\n"
        "    ProxyPass / http://127.0.0.1:5001/\n"
        "    ProxyPassReverse / http://127.0.0.1:5001/\n"
        "\n"
        "    # Servir fitxers estatics directament\n"
        f"    Alias /static/ {APP_DIR}/static/\n"
        f"    <Directory {APP_DIR}/static/>\n"
        "        Require all granted\n"
        "        Options -Indexes\n"
        "    </Directory>\n"
        "\n"
        f"    ErrorLog ${{APACHE_LOG_DIR}}/{SERVICE_NAME}-error.log\n"
        f"    CustomLog ${{APACHE_LOG_DIR}}/{SERVICE_NAME}-access.log combined\n"
        "</VirtualHost>"
    )

    pdf.sub_title("6.3 Activar el site i reiniciar")
    pdf.code_block(
        f"# Activar el site\n"
        f"sudo a2ensite {VHOST_NAME}\n"
        f"\n"
        f"# Verificar configuracio\n"
        f"sudo apachectl configtest\n"
        f"\n"
        f"# Reiniciar Apache\n"
        f"sudo systemctl reload apache2"
    )

    # ── 7. XARXA I TALLAFOCS ──
    pdf.add_page()
    pdf.section_title("7", "Xarxa i tallafocs")

    pdf.info_box(
        "Si Lab FC ja esta desplegat, la configuracio de xarxa (IP fixa, "
        "UFW, DNS) ja estara feta. Nomes cal verificar i afegir "
        "l'entrada DNS per a la nova aplicacio.",
        "success",
    )

    pdf.sub_title("7.1 IP fixa (Netplan)")
    pdf.body_text(
        "La VM ja ha de tenir una IP fixa configurada. Si no es el cas, "
        "configurar Netplan:"
    )
    pdf.code_block(
        "sudo nano /etc/netplan/01-netcfg.yaml\n"
        "\n"
        "# Exemple de configuracio:\n"
        "network:\n"
        "  version: 2\n"
        "  ethernets:\n"
        "    ens192:\n"
        "      dhcp4: false\n"
        "      addresses:\n"
        "        - 192.168.X.X/24\n"
        "      routes:\n"
        "        - to: default\n"
        "          via: 192.168.X.1\n"
        "      nameservers:\n"
        "        addresses: [192.168.X.X]\n"
        "\n"
        "sudo netplan apply"
    )

    pdf.sub_title("7.2 Tallafocs (UFW)")
    pdf.body_text("Verificar que els ports necessaris estan oberts:")
    pdf.code_block(
        "# Comprovar estat\n"
        "sudo ufw status\n"
        "\n"
        "# Permetre Apache (probablement ja obert per Lab FC)\n"
        "sudo ufw allow 'Apache'\n"
        "\n"
        "# Permetre SSH (si no esta obert)\n"
        "sudo ufw allow OpenSSH\n"
        "\n"
        "# Verificar\n"
        "sudo ufw status verbose"
    )

    pdf.info_box(
        "NO cal obrir el port 5001 al tallafocs. Gunicorn escolta a "
        "127.0.0.1 i nomes Apache hi accedeix internament.",
        "warning",
    )

    pdf.sub_title("7.3 DNS")
    pdf.body_text(
        "Cal afegir una entrada DNS perque els clients puguin accedir "
        f"a {SERVER_NAME}. Opcions:\n\n"
        "1. Entrada al servidor DNS corporatiu (recomanat)\n"
        "2. Entrada al fitxer /etc/hosts de cada client"
    )
    pdf.code_block(
        f"# Exemple entrada DNS\n"
        f"192.168.X.X    {SERVER_NAME}"
    )

    # ── 8. LLISTA DE VERIFICACIO ──
    pdf.add_page()
    pdf.section_title("8", "Llista de verificacio")

    pdf.body_text("Executar totes les comprovacions abans de donar per finalitzat el desplegament:")

    checks = [
        ["1", "Driver ODBC instal-lat", "odbcinst -q -d", "[ODBC Driver 18...]"],
        ["2", "Repositori clonat", f"ls {APP_DIR}/app.py", "Fitxer existent"],
        ["3", "Entorn virtual creat", f"ls {APP_DIR}/venv/bin/python", "Fitxer existent"],
        ["4", "Connexio SQL OK", "Pas 4.5 (script Python)", "Connexio OK"],
        ["5", f"Servei {SERVICE_NAME} actiu", f"systemctl status {SERVICE_NAME}", "active (running)"],
        ["6", "Port 5001 escoltant", "ss -tlnp | grep 5001", "LISTEN 127.0.0.1:5001"],
        ["7", "Apache respon", f"curl http://localhost/", "HTML de l'app"],
        ["8", "Pagina carrega comandes", f"curl http://{SERVER_NAME}", "Pantalla principal"],
    ]
    pdf.table(
        ["#", "Verificacio", "Comanda", "Resultat esperat"],
        checks,
        [8, 45, 55, 42],
    )

    pdf.sub_title("Verificacio rapida des del terminal")
    pdf.code_block(
        f"# 1. Servei actiu?\n"
        f"systemctl is-active {SERVICE_NAME}\n"
        f"\n"
        f"# 2. Port obert?\n"
        f"ss -tlnp | grep 5001\n"
        f"\n"
        f"# 3. Resposta HTTP?\n"
        f"curl -s -o /dev/null -w '%{{http_code}}' http://localhost:5001/\n"
        f"# Ha de retornar: 200\n"
        f"\n"
        f"# 4. API funciona?\n"
        f"curl -s http://localhost:5001/api/ultimes-comandes | python3 -m json.tool | head -5\n"
        f'# Ha de retornar JSON amb "ok": true'
    )

    # ── 9. MANTENIMENT ──
    pdf.add_page()
    pdf.section_title("9", "Manteniment i actualitzacions")

    pdf.sub_title("9.1 Actualitzar l'aplicacio")
    pdf.body_text(
        "Quan hi hagi una nova versio al repositori GitHub:"
    )
    pdf.code_block(
        f"cd {APP_DIR}\n"
        f"sudo -u www-data git pull origin main\n"
        f"sudo -u www-data venv/bin/pip install -r requirements.txt\n"
        f"sudo systemctl restart {SERVICE_NAME}"
    )

    pdf.sub_title("9.2 Rotacio de logs")
    pdf.code_block(f"sudo nano /etc/logrotate.d/{SERVICE_NAME}")
    pdf.body_text("Contingut:")
    pdf.code_block(
        f"{APP_DIR}/*.log {{\n"
        "    daily\n"
        "    missingok\n"
        "    rotate 14\n"
        "    compress\n"
        "    delaycompress\n"
        "    notifempty\n"
        "    copytruncate\n"
        "}"
    )

    pdf.sub_title("9.3 Copies de seguretat")
    pdf.body_text(
        "Aquesta aplicacio no te base de dades local (es connecta a "
        "SQL Server remot). Nomes cal fer copia de seguretat del fitxer .env "
        "si s'han modificat les credencials."
    )

    # ── 10. LOGS ──
    pdf.section_title("10", "Logs i monitoratge")
    pdf.table(
        ["Fitxer / Comanda", "Contingut"],
        [
            [f"{APP_DIR}/motor.log", "Log del motor (resultats, avisos, errors)"],
            [f"{APP_DIR}/access.log", "Log d'acces HTTP (Gunicorn)"],
            [f"{APP_DIR}/error.log", "Errors del servidor web (Gunicorn)"],
            [f"/var/log/apache2/{SERVICE_NAME}-*.log", "Logs d'Apache"],
            [f"journalctl -u {SERVICE_NAME}", "Logs del servei systemd"],
        ],
        [75, 75],
    )
    pdf.code_block(
        f"# Logs del motor en temps real\n"
        f"tail -f {APP_DIR}/motor.log\n"
        f"\n"
        f"# Logs del servei\n"
        f"journalctl -u {SERVICE_NAME} -f --no-pager\n"
        f"\n"
        f"# Logs d'Apache\n"
        f"tail -f /var/log/apache2/{SERVICE_NAME}-error.log"
    )

    # ── 11. TROUBLESHOOTING ──
    pdf.add_page()
    pdf.section_title("11", "Resolucio de problemes")

    problems = [
        ["El servei no arrenca", "Dependencies o config", f"journalctl -u {SERVICE_NAME} -n 50"],
        ["Can't open lib ODBC 18", "Driver no instal-lat", "Repetir pas 3.3"],
        ["Login failed for user", "Credencials SQL", "Revisar .env (contactar responsable)"],
        ["Connection refused SQL", "Firewall o xarxa", "telnet vkais 1433"],
        ["Named Pipes error", "Instancia SQL", "SQL_SERVER=vkais,1434"],
        ["Error 502 Bad Gateway", "Gunicorn no respon", f"systemctl restart {SERVICE_NAME}"],
        ["Comandes no carreguen", "Error connexio BD", "Revisar motor.log i pas 4.5"],
        ["Pagina no accessible", "DNS o Apache", f"curl http://localhost:5001/"],
    ]
    pdf.table(
        ["Problema", "Causa probable", "Solucio"],
        problems,
        [45, 45, 60],
    )

    pdf.sub_title("Comprovar connectivitat a SQL Server")
    pdf.code_block(
        "# Verificar port accessible\n"
        "telnet vkais 1433\n"
        "\n"
        "# Provar connexio ODBC directa\n"
        'isql -v "ODBC Driver 18 for SQL Server" "vkais\\kais" "usuari" "pwd"'
    )

    # ── 12. RESUM I TEMPS ESTIMATS ──
    pdf.add_page()
    pdf.section_title("12", "Resum i temps estimats")

    pdf.body_text(
        "Temps estimats assumint que Lab FC ja esta desplegat al servidor "
        "(Python, Apache, UFW ja configurats):"
    )

    pdf.table(
        ["Pas", "Descripcio", "Temps estimat"],
        [
            ["3.3-3.4", "Instal-lar driver ODBC 18", "5 min"],
            ["4.1-4.3", "Clonar repo i entorn virtual", "5 min"],
            ["4.4-4.5", "Configuracio i verificacio SQL", "5 min"],
            ["5", "Servei systemd", "5 min"],
            ["6", "Apache VirtualHost", "5 min"],
            ["7", "DNS (entrada nova)", "5 min"],
            ["8", "Verificacio", "5 min"],
            ["", "TOTAL ESTIMAT", "30-40 min"],
        ],
        [25, 85, 40],
    )

    pdf.ln(5)
    pdf.body_text(
        "Si es tracta d'una instal-lacio completa (sense Lab FC previ), "
        "afegir ~20 minuts addicionals per instal-lar Python, Apache, "
        "configurar UFW i IP fixa."
    )

    pdf.sub_title("Comparativa de serveis al servidor")
    pdf.table(
        ["", "Lab FC", "Comandes Venda"],
        [
            ["Directori", "/var/www/lab-fc", APP_DIR],
            ["Servei", "lab-fc.service", f"{SERVICE_NAME}.service"],
            ["Port intern", "8000", "5001"],
            ["ServerName", "labfc.agrienergia.local", SERVER_NAME],
            ["Base de dades", "PostgreSQL (local)", "SQL Server (remot)"],
            ["Usuari SO", "www-data", "www-data"],
        ],
        [35, 60, 60],
    )

    # Save
    output_file = "docs/guia-desplegament-v8.pdf"
    pdf.output(output_file)
    print(f"PDF generat: {output_file}")


if __name__ == "__main__":
    generate()
