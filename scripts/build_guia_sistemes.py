"""Generador de la guia de desplegament per l'equip de Sistemes.

Genera `docs/Desplegament_SAP_Sistemes.docx` (+ `.pdf`): que
`comandes.agrienergia.local` passi a servir la variant SAP, deixant Kais viu en
paral·lel a `comandes-kais.agrienergia.local`.

Public objectiu: administradors de sistemes, no desenvolupadors. Cada comandament
va acompanyat de que fa i de com verificar que ha anat be.

Reutilitza els helpers i la paleta de `build_proposta_sap.py`.

Us:
    python scripts/build_guia_sistemes.py
"""
from __future__ import annotations

import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Pt

from build_proposta_sap import (  # noqa: E402
    COLOR_MUTED,
    COLOR_SUBTITOL,
    COLOR_TITOL,
    add_bullet,
    add_code_block,
    add_heading,
    add_info_box,
    add_page_break,
    add_para,
    add_taula,
)

COLOR_AVIS_BG = "FFF4CE"
COLOR_OK_BG = "E8F5E9"

IP = "192.168.11.244"
SERVIDOR = "ae01farwebsrv"
APP_DIR = "/var/www/comandes-venda-sap"
URL = "comandes.agrienergia.local"
URL_KAIS = "comandes-kais.agrienergia.local"
CONF_SAP = "comandes-venda-sap.conf"
CONF_KAIS = "comandes-venda.conf"


def add_avis(doc, text):
    add_info_box(doc, text, bg=COLOR_AVIS_BG, icon="⚠")


def add_ok(doc, text):
    add_info_box(doc, text, bg=COLOR_OK_BG, icon="✔")


def add_pas(doc, numero, titol):
    add_heading(doc, f"Pas {numero} — {titol}", level=2)


def build_document():
    doc = Document()

    for section in doc.sections:
        section.top_margin = Cm(2)
        section.bottom_margin = Cm(2)
        section.left_margin = Cm(2.5)
        section.right_margin = Cm(2.5)

    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    # ================= PORTADA =================
    for _ in range(7):
        doc.add_paragraph()

    add_para(doc, "GUIA DE DESPLEGAMENT", bold=True, size=24, color=COLOR_TITOL,
             align=WD_ALIGN_PARAGRAPH.CENTER, space_after=4)
    add_para(doc, "Motor d'Embalatges — pas a les dades de SAP", bold=True,
             size=17, color=COLOR_SUBTITOL, align=WD_ALIGN_PARAGRAPH.CENTER,
             space_after=20)
    add_para(doc, f"{URL} passa a la versió SAP, amb la de Kais viva en paral·lel",
             italic=True, size=12.5, color=COLOR_MUTED,
             align=WD_ALIGN_PARAGRAPH.CENTER, space_after=40)

    for _ in range(5):
        doc.add_paragraph()

    add_para(doc, "Destinatari: equip de Sistemes", bold=True, size=11,
             align=WD_ALIGN_PARAGRAPH.CENTER, space_after=4)
    add_para(doc, f"Data: {date.today().strftime('%d/%m/%Y')}", size=11,
             align=WD_ALIGN_PARAGRAPH.CENTER, space_after=4)
    add_para(doc, "Empresa: Agrienergia — Farinera Coromina", size=11,
             align=WD_ALIGN_PARAGRAPH.CENTER, space_after=4)
    add_para(doc, "Autor: Oscar Hijazo", size=11,
             align=WD_ALIGN_PARAGRAPH.CENTER)

    add_page_break(doc)

    # ================= 1. RESUM =================
    add_heading(doc, "1. Resum executiu", level=1)

    add_para(doc,
             f"L'aplicació de càlcul d'embalatges de comandes de venda que els "
             f"usuaris fan servir a http://{URL}/ llegeix les dades del sistema "
             "antic (Kais). N'existeix una segona versió, ja desplegada al mateix "
             "servidor, que llegeix de SAP Business One. Volem que la URL de sempre "
             "passi a servir aquesta segona versió.")

    add_para(doc,
             "La versió de Kais no s'atura: ha de seguir disponible en paral·lel "
             "(acord operatiu: viu fins al novembre de 2026). Quedarà accessible a "
             f"http://{URL_KAIS}/, i serveix també de marxa enrere ràpida si la "
             "versió SAP dona problemes.")

    add_ok(doc, "Els usuaris no han de canviar cap enllaç ni cap favorit: la URL "
                "que tenien segueix sent la bona.")

    add_heading(doc, "El canvi, en una frase", level=2)
    add_para(doc,
             "Les dues aplicacions ja conviuen al mateix servidor darrere del mateix "
             "Apache, cadascuna amb el seu VirtualHost. Fer el canvi és moure el nom "
             "de host d'un VirtualHost a l'altre i recarregar Apache.")

    add_info_box(doc,
                 f"No hi ha canvi de DNS per a la URL principal. {URL} ja apunta a "
                 f"{IP} i s'hi queda: les dues aplicacions viuen a la mateixa IP i "
                 "és Apache qui decideix quina serveix cada nom.")

    add_heading(doc, "Repartiment de la feina", level=2)
    add_taula(doc,
              ["Tasca", "Responsable", "Temps", "Estat"],
              [
                  [f"Registre DNS {URL_KAIS} (apartat 3)", "Sistemes", "5 min",
                   "Pendent"],
                  ["Desplegar el codi al dia", "Oscar", "2 min", "Fet 29/09"],
                  ["Migrar de Flask dev server a Gunicorn", "Oscar", "3 min",
                   "Fet 29/09"],
                  ["Backup config Apache + smoke test", "Oscar", "10 min",
                   "Pendent"],
                  ["Finestra del canvi (apartat 4)", "Oscar", "10 min",
                   "Pendent del DNS"],
                  ["Verificació conjunta (apartat 5)", "Tots dos", "5 min",
                   "Pendent"],
              ],
              amples=[6.5, 3.0, 2.0, 4.5])

    add_para(doc,
             "La finestra del canvi es programa fora d'hores actives (abans de les "
             "9 h o després de les 18 h) i es comunica als usuaris com un "
             "manteniment de ~5 minuts.")

    add_page_break(doc)

    # ================= 2. ARQUITECTURA =================
    add_heading(doc, "2. Com està muntat el servidor", level=1)

    add_para(doc,
             "Apache fa de proxy invers al port 80 amb VirtualHosts per nom. Cada "
             "aplicació és un procés Gunicorn escoltant a 127.0.0.1 al seu port, i "
             "Apache l'encamina segons el nom de host de la petició. Al servidor hi "
             "conviuen cinc aplicacions més la variant SAP.")

    add_heading(doc, "Ara", level=2)
    add_code_block(doc,
                   f"""                 Apache  *:80  (NameVirtualHost)
                 ---------------------------------
  agrupacions.agrienergia.local --> agrupacio-carregues.conf   (default)
  {URL} -----> {CONF_KAIS}      --> 127.0.0.1:5001  Kais
  fitxesfc.agrienergia.local ------> fitxes-tecniques.conf
  labfc.agrienergia.local ---------> labfc.conf
  visitesfc.agrienergia.local -----> visites.conf

  (cap nom encara) ----------------> {CONF_SAP}  --> 127.0.0.1:5002  SAP""")

    add_heading(doc, "Després", level=2)
    add_code_block(doc,
                   f"""  {URL} -----> {CONF_SAP}  --> 127.0.0.1:5002  SAP
  {URL_KAIS} > {CONF_KAIS}      --> 127.0.0.1:5001  Kais""")

    add_para(doc,
             "Les altres quatre aplicacions del servidor no es veuen afectades de "
             "cap manera.", size=10, color=COLOR_MUTED)

    add_heading(doc, "Estat de la versió SAP", level=2)
    add_taula(doc,
              ["Element", "Valor"],
              [
                  ["Servei systemd", "comandes-venda-sap.service"],
                  ["Servidor web", "Gunicorn (gthread, 2 processos × 4 fils)"],
                  ["Socket", "0.0.0.0:5002"],
                  ["Directori", APP_DIR],
                  ["VirtualHost d'Apache", f"{CONF_SAP} (preparat, no activat)"],
              ],
              amples=[5.0, 11.0])

    add_para(doc,
             "El socket és 0.0.0.0 i no 127.0.0.1 perquè el botó «Calcular "
             f"embalatges» de SAP Business One crida http://{IP}:5002/ per IP "
             "directa. Aquesta via ha de seguir funcionant durant i després del "
             "canvi; veure l'apartat 8.")

    add_page_break(doc)

    # ================= 3. PETICIÓ =================
    add_heading(doc, "3. Què demanem a Sistemes", level=1)

    add_para(doc, "Un sol registre DNS, per al nom secundari de la versió Kais:")

    add_taula(doc,
              ["Nom", "Tipus", "Valor", "TTL"],
              [[URL_KAIS, "A", IP, "300"]],
              amples=[7.5, 2.0, 4.0, 2.5])

    add_para(doc,
             f"És la mateixa IP que ja fa servir {URL}. El TTL curt (300 s) és per "
             "poder ajustar ràpid si cal.")

    add_heading(doc, "Què NO cal fer", level=2)
    add_bullet(doc, f"No cal tocar el registre {URL}: ha de seguir apuntant a {IP} "
                    "exactament com ara. El que canvia és quin VirtualHost el "
                    "serveix, i això és configuració d'Apache, no DNS.")
    add_bullet(doc, "No cal cap IP nova ni cap canvi a la configuració de xarxa.")
    add_bullet(doc, "No cal obrir ports al tallafocs: és el port 80 que Apache ja "
                    "fa servir.")
    add_bullet(doc, "No cal aturar ni reconfigurar el servei de la versió Kais "
                    "(comandes-venda.service). Segueix corrent igual.")

    add_para(doc,
             f"Si podeu, confirmeu també que el TTL de {URL} és de 300 s o menys. No "
             "el canviem, però si algun dia cal moure'l voldríem propagació ràpida.")

    add_para(doc, "Verificació un cop donat d'alta:")
    add_code_block(doc, f"nslookup {URL_KAIS}")

    add_page_break(doc)

    # ================= 4. EL CANVI =================
    add_heading(doc, "4. La finestra del canvi", level=1)

    add_para(doc,
             "Procediment que executa l'Oscar per SSH al servidor. Es documenta "
             "perquè Sistemes el pugui seguir o repetir. Duració ~10 min, marxa "
             "enrere < 5 min.")

    add_pas(doc, 0, "Abans de començar")
    add_code_block(doc, """sudo tar czf /root/apache-backup-$(date +%F).tgz \\
    /etc/apache2/sites-available /etc/apache2/sites-enabled
systemctl status comandes-venda-sap""")

    add_pas(doc, 1, "Copiar el VirtualHost de la versió SAP")
    add_code_block(doc, f"""sudo cp {APP_DIR}/deploy/apache/{CONF_SAP} \\
    /etc/apache2/sites-available/""")
    add_para(doc, f"Aquest fitxer ja porta «ServerName {URL}» i el proxy cap al "
                  "port 5002.", size=10, color=COLOR_MUTED)

    add_pas(doc, 2, "Rebatejar el VirtualHost de la versió Kais")
    add_code_block(doc, f"sudo nano /etc/apache2/sites-available/{CONF_KAIS}")
    add_para(doc, "Dos canvis:")
    add_bullet(doc, f"Canviar «ServerName {URL}» per «ServerName {URL_KAIS}».")
    add_bullet(doc, f"Afegir just a sota, temporalment: «ServerAlias {URL}».")
    add_para(doc,
             "L'alias temporal fa que durant els segons entre els dos «reload» els "
             "dos VirtualHosts responguin al nom antic, de manera que cap petició en "
             "curs es perdi. Amb dos VirtualHosts pel mateix nom guanya el que "
             f"Apache carrega primer: «{CONF_SAP}» va abans que «{CONF_KAIS}» per "
             "ordre alfabètic, o sigui la versió SAP.", size=10, color=COLOR_MUTED)

    add_pas(doc, 3, "Validar i activar")
    add_code_block(doc, f"""sudo apachectl configtest
sudo a2ensite {CONF_SAP}
sudo systemctl reload apache2
sudo apachectl -S | grep comandes""")

    add_avis(doc, "Si «apachectl configtest» no diu «Syntax OK», NO continuar. Un "
                  "«reload» amb configuració invàlida deixa Apache servint la "
                  "configuració antiga, però un «restart» posterior el tombaria i "
                  "s'emportaria les altres cinc aplicacions del servidor.")

    add_para(doc, "Es fa «reload» i no «restart» precisament per no tallar "
                  "connexions actives de cap de les aplicacions.", size=10,
             color=COLOR_MUTED)

    add_pas(doc, 4, "Retirar l'alias temporal")
    add_code_block(doc, f"""sudo nano /etc/apache2/sites-available/{CONF_KAIS}
# esborrar la línia: ServerAlias {URL}
sudo apachectl configtest && sudo systemctl reload apache2""")

    add_page_break(doc)

    # ================= 5. VERIFICACIÓ =================
    add_heading(doc, "5. Verificació", level=1)

    add_heading(doc, "5.1 Al servidor", level=2)
    add_code_block(doc, f"""curl -sS -H "Host: {URL}" http://127.0.0.1/ajuda | head -20
curl -sS -H "Host: {URL_KAIS}" http://127.0.0.1/ | head -20""")

    add_heading(doc, "5.2 Des d'un PC Windows de la xarxa", level=2)
    add_code_block(doc, f"""ipconfig /flushdns
curl.exe http://{URL}/ajuda
curl.exe http://{URL_KAIS}/
curl.exe http://{IP}:5002/api/admin/versio""")

    add_taula(doc,
              ["Comprovació", "Resultat esperat"],
              [
                  [URL, "HTML de la versió SAP (el títol porta «(SAP)»)"],
                  [URL_KAIS, "HTML de la versió Kais, funcionant com sempre"],
                  [f"{IP}:5002/api/admin/versio", "JSON amb el commit desplegat"],
              ],
              amples=[6.5, 9.5])

    add_ok(doc, "Criteri d'acceptació: les tres responen. La tercera és la que "
                "garanteix que el botó «Calcular embalatges» de SAP Business One "
                "segueix funcionant.")

    add_heading(doc, "5.3 Prova funcional a SAP Business One", level=2)
    add_bullet(doc, "Obrir el SAP Fat Client i entrar a Comanda de venda "
                    "(una comanda esborrany).")
    add_bullet(doc, "Clicar el botó «Calcular embalatges».")
    add_bullet(doc, "Comprovar el missatge d'èxit a la barra d'estat.")
    add_bullet(doc, "Comprovar que apareixen les línies de palet a la comanda.")

    # ================= 6. ROLLBACK =================
    add_heading(doc, "6. Marxa enrere", level=1)

    add_para(doc,
             "Criteri per fer-la: errors 502/504 repetits a la URL principal, "
             "errors de Python al log del servei, o el consultor comunica que el "
             "botó de SAP falla sistemàticament.")

    add_code_block(doc, f"""# 1. Desactivar el VirtualHost de la versió SAP
sudo a2dissite {CONF_SAP}

# 2. Tornar el nom original al VirtualHost de Kais
sudo nano /etc/apache2/sites-available/{CONF_KAIS}
#    ServerName {URL_KAIS}  ->  ServerName {URL}

# 3. Recarregar i verificar
sudo apachectl configtest && sudo systemctl reload apache2
curl -sS -H "Host: {URL}" http://127.0.0.1/ | head -20""")

    add_ok(doc, "La versió Kais no s'ha tocat en cap moment: el seu servei, el seu "
                "port i les seves dades són els mateixos abans i després. Per això "
                "la marxa enrere és només un canvi de nom a Apache.")

    add_heading(doc, "Diagnòstic", level=2)
    add_code_block(doc, f"""sudo journalctl -u comandes-venda-sap -n 50
sudo tail -50 {APP_DIR}/error.log
sudo tail -50 /var/log/apache2/comandes-venda-sap-error.log""")

    add_taula(doc,
              ["Símptoma", "Causa", "Solució"],
              [
                  ["502 / 503 al navegador",
                   "Gunicorn aturat o no escolta al 5002",
                   "systemctl status comandes-venda-sap"],
                  ["La URL serveix encara la versió Kais",
                   "El VirtualHost no està activat o Apache no s'ha recarregat",
                   "sudo apachectl -S | grep comandes"],
                  ["«Syntax error» al configtest",
                   "Error al fitxer del VirtualHost",
                   "No recarregar; revisar el fitxer"],
                  [f"{URL_KAIS} no resol",
                   "El registre DNS no està donat d'alta o propagat",
                   f"nslookup {URL_KAIS}"],
                  ["ModuleNotFoundError: gunicorn",
                   "El venv no té gunicorn instal·lat",
                   f"sudo bash {APP_DIR}/deploy.sh --reinstall-service"],
              ],
              amples=[4.5, 5.5, 6.0])

    add_page_break(doc)

    # ================= 7. MANTENIMENT =================
    add_heading(doc, "7. Manteniment", level=1)

    add_heading(doc, "Actualitzar l'aplicació", level=2)
    add_code_block(doc, f"""# Codi al dia (git pull + reinici del servei)
sudo bash {APP_DIR}/deploy.sh

# Reescriure la definició del servei systemd. Repetible i idempotent.
sudo bash {APP_DIR}/deploy.sh --reinstall-service""")

    add_para(doc,
             "El segon comandament existeix perquè el primer no toca la definició "
             "del servei. Per això l'aplicació havia quedat mesos amb el servidor de "
             "desenvolupament de Flask tot i que el repositori ja definia Gunicorn: "
             "cap actualització hi arribava.", size=10, color=COLOR_MUTED)

    add_heading(doc, "Comandaments habituals", level=2)
    add_code_block(doc, """sudo systemctl status comandes-venda-sap
sudo systemctl restart comandes-venda-sap
sudo journalctl -u comandes-venda-sap -f
sudo tail -f %s/access.log %s/error.log""" % (APP_DIR, APP_DIR))

    add_heading(doc, "Logs i rotació", level=2)
    add_para(doc,
             f"Els logs de Gunicorn viuen a {APP_DIR}/access.log i error.log, amb "
             "rotació setmanal i 4 setmanes de retenció "
             "(/etc/logrotate.d/comandes-venda-sap). Els d'Apache, a "
             "/var/log/apache2/comandes-venda-sap-*.log. Comprovació el dilluns:")
    add_code_block(doc, f"ls -la {APP_DIR}/*.log*")
    add_para(doc, "Els fitxers de la setmana anterior han de tenir extensió .1.gz.",
             size=10, color=COLOR_MUTED)

    add_heading(doc, "Les dues aplicacions d'embalatges", level=2)
    add_taula(doc,
              ["Versió", "Servei systemd", "Port intern", "Directori"],
              [
                  ["Kais", "comandes-venda.service", "5001",
                   "/var/www/comandes-venda"],
                  ["SAP", "comandes-venda-sap.service", "5002", APP_DIR],
              ],
              amples=[2.5, 5.5, 2.5, 5.5])

    add_avis(doc, "El servei comandes-venda.service (versió Kais) ha de quedar "
                  "operatiu fins al novembre de 2026. Cap pas d'aquesta guia el "
                  "toca ni l'atura.")

    # ================= 8. BOTÓ B1UP =================
    add_heading(doc, "8. El botó de SAP Business One", level=1)

    add_para(doc,
             "Dins de SAP Business One, al formulari Comanda de venda, hi ha un botó "
             "«Calcular embalatges» (configurat amb B1UP) que crida l'aplicació per "
             f"HTTP a http://{IP}:5002/api/afegir-palets/.")

    add_ok(doc, "El canvi d'aquesta guia no l'afecta: crida l'aplicació per IP i "
                "port directes, no per nom, i aquesta via segueix oberta. Tampoc "
                "l'afecta la marxa enrere. No cal coordinar el consultor de B1UP per "
                "fer el canvi.")

    add_para(doc,
             "Si algun dia es vol treure la IP del codi de B1UP, la manera segura és "
             "donar a la versió SAP un nom propi addicional "
             "(comandes-sap.agrienergia.local, un registre DNS més cap a la mateixa "
             f"IP) i afegir-lo com a ServerAlias al seu VirtualHost. Fer servir {URL} "
             "seria pitjor: el botó quedaria lligat a qui tingui la URL històrica en "
             "cada moment i una marxa enrere el faria caure contra la versió Kais, "
             "que no té aquest endpoint.")

    add_para(doc,
             "Un cop el botó no depengui de la IP directa, es pot tancar Gunicorn "
             "darrere d'Apache, que és la configuració desitjable:")
    add_code_block(doc,
                   f"sudo BIND_ADDR=127.0.0.1:5002 bash {APP_DIR}/deploy.sh --reinstall-service")
    add_para(doc, "Res d'això bloqueja el canvi; és feina posterior i opcional.",
             size=10, color=COLOR_MUTED)

    # ================= CONTACTES =================
    add_heading(doc, "Contacte", level=1)
    add_para(doc, "Oscar Hijazo — ohijazo@agrienergia.com", bold=True)
    add_para(doc,
             "Documentació tècnica al repositori de l'aplicació: deploy/README.md "
             "(arquitectura de xarxa del servidor), "
             "docs/runbook_swap_url_produccio.md (procediment detallat amb la "
             "finestra i el rollback), docs/peticio_dns_sistemes.md (la petició de "
             "l'apartat 3 en text pla).", size=10, color=COLOR_MUTED)

    return doc


SOFFICE = r"C:\Program Files\LibreOffice\program\soffice.exe"


def _exporta_pdf(docx_path, pdf_path):
    """Converteix a PDF. LibreOffice primer (no depen que Word estigui tancat)."""
    if os.path.exists(SOFFICE):
        import shutil
        import subprocess
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            res = subprocess.run(
                [SOFFICE, "--headless", "--norestore", "--convert-to", "pdf",
                 "--outdir", tmp, docx_path],
                capture_output=True, text=True)
            generat = os.path.join(tmp, os.path.basename(docx_path)[:-5] + ".pdf")
            if res.returncode == 0 and os.path.exists(generat):
                shutil.copy2(generat, pdf_path)
                return True
            print("AVIS LibreOffice:", res.stderr.strip() or res.stdout.strip())

    try:
        from docx2pdf import convert
        convert(docx_path, pdf_path)
        return True
    except Exception as e:  # noqa: BLE001 - el .docx ja esta desat; el PDF es opcional
        print("AVIS docx2pdf: {} (tanca el Word i torna-ho a provar)".format(e))
        return False


def main():
    docs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs")
    os.makedirs(docs_dir, exist_ok=True)
    docx_path = os.path.abspath(os.path.join(docs_dir, "Desplegament_SAP_Sistemes.docx"))
    pdf_path = docx_path[:-5] + ".pdf"

    doc = build_document()
    doc.save(docx_path)
    print("Generat: {} ({:.1f} KB)".format(docx_path, os.path.getsize(docx_path) / 1024))

    if _exporta_pdf(docx_path, pdf_path):
        print("Generat: {} ({:.1f} KB)".format(pdf_path, os.path.getsize(pdf_path) / 1024))
    else:
        print("AVIS: no s'ha pogut generar el PDF. Obre el .docx i desa'l com a PDF.")


if __name__ == "__main__":
    main()
