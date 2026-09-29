"""Generador de la guia de desplegament per l'equip de Sistemes.

Genera `docs/Desplegament_SAP_Sistemes.docx` (+ `.pdf`) amb tot el que Sistemes
ha de fer per donar una URL propia a la variant SAP mantenint Kais intacte:
alta d'IP secundaria, registre DNS, i els comandaments de desplegament.

Public objectiu: administradors de sistemes, no desenvolupadors. Cada
comandament va acompanyat de que fa i de com verificar que ha anat be.

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

IP_KAIS = "192.168.11.244"
IP_SAP = "192.168.11.245"
SERVIDOR = "ae01farwebsrv"
APP_DIR = "/var/www/comandes-venda-sap"


def add_avis(doc, text):
    add_info_box(doc, text, bg=COLOR_AVIS_BG, icon="⚠")


def add_ok(doc, text):
    add_info_box(doc, text, bg=COLOR_OK_BG, icon="✔")


def add_pas(doc, numero, titol):
    """Capcalera de pas numerat dins d'un procediment."""
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
    add_para(doc, "Motor d'Embalatges — variant SAP Business One", bold=True,
             size=17, color=COLOR_SUBTITOL, align=WD_ALIGN_PARAGRAPH.CENTER,
             space_after=20)
    add_para(doc, "Convivència amb l'aplicació actual (Kais) al servidor "
                  f"{SERVIDOR}", italic=True, size=13, color=COLOR_MUTED,
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
             "Al servidor " + SERVIDOR + " conviuen dues versions de l'aplicació "
             "de càlcul d'embalatges de comandes de venda. L'una llegeix les dades "
             "de Kais i està en producció; l'altra llegeix de SAP Business One i "
             "s'està validant. Les dues han de seguir funcionant en paral·lel una "
             "temporada.")

    add_para(doc,
             "La versió SAP només és accessible ara mateix escrivint la IP i el "
             f"port (http://{IP_KAIS}:5002/). Aquesta guia explica com donar-li un "
             "nom propi — comandes-sap.agrienergia.local — sense tocar en absolut "
             "l'aplicació que està en producció.")

    add_heading(doc, "Què cal fer, en tres línies", level=2)
    add_bullet(doc, f"Sistemes: afegir una IP secundària ({IP_SAP}) al servidor i "
                    "un registre DNS que hi apunti.")
    add_bullet(doc, "Oscar: executar dos comandaments de desplegament al servidor.")
    add_bullet(doc, "Tots dos: verificar que les tres URLs responen (apartat 6).")

    add_ok(doc, "L'aplicació en producció (Kais) no es reinicia, no es "
                "reconfigura i no canvia de port ni d'adreça. Aquest és el criteri "
                "que ha guiat tot el disseny.")

    add_heading(doc, "Temps i risc", level=2)
    add_taula(doc,
              ["Tasca", "Responsable", "Temps", "Risc per producció"],
              [
                  ["Alta IP secundària (netplan)", "Sistemes", "5 min", "Cap"],
                  ["Registre DNS", "Sistemes", "5 min", "Cap"],
                  ["Desplegament del codi", "Oscar", "2 min", "Cap"],
                  ["Migració a Gunicorn", "Oscar", "3 min", "Cap (només app SAP)"],
                  ["Verificació conjunta", "Tots dos", "5 min", "Cap"],
              ],
              amples=[6.5, 3.0, 2.0, 4.5])

    add_page_break(doc)

    # ================= 2. ESTAT ACTUAL =================
    add_heading(doc, "2. Estat actual del servidor", level=1)

    add_para(doc,
             "Estat verificat el 29/09/2026 sondejant el servidor des de la xarxa "
             "(capçaleres HTTP i ports oberts). Convé llegir-lo perquè hi ha dues "
             "coses que no són com la documentació anterior deia.")

    add_heading(doc, "No hi ha cap reverse proxy", level=2)
    add_para(doc,
             "No hi ha Apache ni nginx instal·lat i actiu. Cada aplicació és un "
             "procés Gunicorn que escolta directament al seu socket. Com que no hi "
             f"ha encaminament per nom de host, qualsevol petició que arribi a "
             f"{IP_KAIS}:80 la contesta l'aplicació de Kais, independentment del "
             "nom que s'hagi fet servir per arribar-hi.")

    add_heading(doc, "Ports oberts ara mateix", level=2)
    add_taula(doc,
              ["Socket", "Aplicació", "Servidor web", "Accés"],
              [
                  [f"{IP_KAIS}:80", "Kais (producció)", "gunicorn",
                   "comandes.agrienergia.local"],
                  ["0.0.0.0:5002", "SAP (validació)", "Flask dev server",
                   f"http://{IP_KAIS}:5002/"],
              ],
              amples=[4.0, 4.5, 3.5, 4.5])

    add_para(doc,
             "Els ports 443, 5001, 8000 i 8080 estan tancats des de la xarxa.")

    add_avis(doc, "La versió SAP corre amb el servidor de desenvolupament de "
                  "Flask, que no està pensat per a producció (un sol procés, sense "
                  "gestió de concurrència). Aquest desplegament ho corregeix "
                  "passant-la a Gunicorn, el mateix que ja fa servir Kais.")

    add_heading(doc, "Com quedarà després del desplegament", level=2)
    add_code_block(doc,
                   f"""                      {SERVIDOR}
                      ---------------------------------

  comandes.agrienergia.local ----> {IP_KAIS}:80  ----> gunicorn  Kais
                                                       (sense cap canvi)

  comandes-sap.agrienergia.local > {IP_SAP}:80  ----> gunicorn  SAP
                                                       (nou)
  Botó de SAP B1 (B1UP) --------> {IP_KAIS}:5002 ----> gunicorn  SAP
                                                       (es manté)""")

    add_para(doc,
             "Els dos Gunicorn escolten al port 80 d'IPs diferents, per tant no es "
             "disputen res. És tot el motiu de demanar una IP secundària: evitar "
             "haver de tocar Kais.")

    add_page_break(doc)

    # ================= 3. PETICIÓ A SISTEMES =================
    add_heading(doc, "3. Què demanem a Sistemes", level=1)

    add_heading(doc, "3.1 Una IP lliure de la VLAN, al mateix servidor", level=2)
    add_para(doc,
             f"Proposem {IP_SAP} si està lliure; qualsevol altra de la mateixa "
             "VLAN serveix igual (caldria avisar-nos del canvi). No és una màquina "
             "nova: és una segona adreça de la interfície que ja existeix.")

    add_code_block(doc,
                   """# /etc/netplan/*.yaml — afegir la segona adreça
      addresses:
        - %s/24
        - %s/24      # <-- nova, per a l'app SAP""" % (IP_KAIS, IP_SAP))

    add_code_block(doc, "sudo netplan apply")

    add_para(doc, "Verificació:")
    add_code_block(doc, f"ip -o addr show | grep {IP_SAP}")
    add_para(doc, "Ha de retornar una línia. Si no retorna res, la IP no s'ha "
                  "aplicat.", size=10, color=COLOR_MUTED)

    add_heading(doc, "3.2 Un registre DNS", level=2)
    add_taula(doc,
              ["Nom", "Tipus", "Valor", "TTL"],
              [["comandes-sap.agrienergia.local", "A", IP_SAP, "300"]],
              amples=[7.5, 2.0, 4.0, 2.5])

    add_para(doc,
             "El TTL curt (300 segons) és perquè més endavant, quan la versió SAP "
             "substitueixi definitivament l'actual, el canvi serà només de DNS i "
             "volem poder revertir-lo en minuts si cal.")

    add_heading(doc, "3.3 Què NO cal fer", level=2)
    add_bullet(doc, "No cal tocar el registre comandes.agrienergia.local: ha de "
                    f"seguir apuntant a {IP_KAIS} (producció).")
    add_bullet(doc, "No cal obrir ports al tallafocs: és tràfic HTTP intern al "
                    "port 80, el mateix que ja fa servir l'aplicació actual.")
    add_bullet(doc, "No cal reiniciar ni reconfigurar comandes-venda.service "
                    "(producció Kais).")
    add_bullet(doc, "No cal instal·lar Apache ni nginx.")

    add_page_break(doc)

    # ================= 4. DESPLEGAMENT =================
    add_heading(doc, "4. Desplegament al servidor", level=1)

    add_para(doc,
             "Aquests passos els executa l'Oscar per SSH, o Sistemes si cal fer-ho "
             "sense ell. Tots afecten únicament el servei comandes-venda-sap.")

    add_avis(doc, "Ordre important: els passos 1 i 2 es poden fer ja, sense esperar "
                  "la IP. El pas 3 requereix que la IP secundària estigui activa, "
                  "i avorta amb un error clar si no ho està.")

    add_pas(doc, 1, "Actualitzar el codi a l'última versió")
    add_code_block(doc, f"sudo bash {APP_DIR}/deploy.sh")
    add_para(doc,
             "Fa git pull del repositori i reinicia el servei. Al final avisa si el "
             "servei encara corre amb el servidor de desenvolupament de Flask.",
             size=10, color=COLOR_MUTED)

    add_pas(doc, 2, "Migrar a Gunicorn")
    add_code_block(doc, f"sudo bash {APP_DIR}/deploy.sh --reinstall-service")
    add_para(doc,
             "Reescriu la definició del servei systemd sencera i el reinicia amb "
             "Gunicorn (2 processos × 4 fils). Encara escolta només al port 5002, "
             "de manera que el botó de SAP B1 segueix funcionant igual.",
             size=10, color=COLOR_MUTED)

    add_pas(doc, 3, "Afegir la IP secundària al port 80")
    add_code_block(doc,
                   f"sudo SAP_BIND_IP={IP_SAP} bash {APP_DIR}/deploy.sh --reinstall-service")
    add_para(doc,
             "Ara Gunicorn escolta a dos sockets alhora: el nou "
             f"{IP_SAP}:80 per als usuaris, i {IP_KAIS}:5002 per al botó de SAP B1, "
             "que hi apunta per IP directa i no s'ha de trencar.",
             size=10, color=COLOR_MUTED)

    add_info_box(doc,
                 "Els passos 2 i 3 són repetibles tantes vegades com calgui: "
                 "reescriuen sempre la definició sencera del servei, així que no "
                 "queda estat acumulat de desplegaments anteriors.")

    add_heading(doc, "Per què el port 80 sense ser root", level=2)
    add_para(doc,
             "El servei segueix corrent amb l'usuari www-data, no com a root. Per "
             "poder lligar-se a un port privilegiat (< 1024) la definició del "
             "servei inclou la capability mínima necessària:")
    add_code_block(doc, "AmbientCapabilities=CAP_NET_BIND_SERVICE")

    add_page_break(doc)

    # ================= 5. VERIFICACIÓ =================
    add_heading(doc, "5. Verificació", level=1)

    add_heading(doc, "5.1 Al servidor", level=2)
    add_code_block(doc, f"""systemctl status comandes-venda-sap      # Active (running)
ss -tlnp | grep -i gunicorn             # {IP_SAP}:80 i 0.0.0.0:5002
curl -sS -D - -o /dev/null http://{IP_SAP}/""")
    add_para(doc, "L'última ordre ha de mostrar «Server: gunicorn». Si mostra "
                  "«Server: Werkzeug», la migració del pas 2 no s'ha aplicat.",
             size=10, color=COLOR_MUTED)

    add_heading(doc, "5.2 Des d'un PC Windows de la xarxa", level=2)
    add_code_block(doc, """curl.exe http://comandes-sap.agrienergia.local/ajuda
curl.exe http://comandes.agrienergia.local/
curl.exe http://%s:5002/api/admin/versio""" % IP_KAIS)

    add_taula(doc,
              ["Comprovació", "Resultat esperat"],
              [
                  ["comandes-sap.agrienergia.local",
                   "HTML de l'aplicació SAP (títol amb «(SAP)»)"],
                  ["comandes.agrienergia.local",
                   "HTML de Kais, exactament com abans"],
                  [f"{IP_KAIS}:5002/api/admin/versio",
                   "JSON amb el commit desplegat"],
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

    add_page_break(doc)

    # ================= 6. ROLLBACK =================
    add_heading(doc, "6. Marxa enrere", level=1)

    add_para(doc,
             "Kais no es toca en cap moment del procediment, per tant no té marxa "
             "enrere ni la necessita. Tot el que es pot desfer afecta només "
             "l'aplicació SAP.")

    add_heading(doc, "Retirar el bind del port 80", level=2)
    add_code_block(doc, f"sudo bash {APP_DIR}/deploy.sh --reinstall-service")
    add_para(doc,
             "Sense la variable SAP_BIND_IP, el servei torna a escoltar només al "
             "port 5002. La URL comandes-sap.agrienergia.local deixa de respondre; "
             "el botó de SAP B1 segueix funcionant.", size=10, color=COLOR_MUTED)

    add_heading(doc, "Si el servei no arrenca", level=2)
    add_code_block(doc, """sudo journalctl -u comandes-venda-sap -n 50
sudo tail -50 %s/error.log""" % APP_DIR)

    add_taula(doc,
              ["Símptoma al log", "Causa", "Solució"],
              [
                  ["Cannot assign requested address",
                   f"La IP {IP_SAP} no està activa al servidor",
                   "Aplicar el netplan (apartat 3.1)"],
                  ["Permission denied (port 80)",
                   "Falta la capability a la definició del servei",
                   "Repetir el pas 3 del desplegament"],
                  ["Address already in use",
                   "Un altre procés té el socket ocupat",
                   "ss -tlnp | grep :80 per veure qui és"],
                  ["ModuleNotFoundError: gunicorn",
                   "El venv no té gunicorn instal·lat",
                   "El pas 2 ja l'instal·la; repetir-lo"],
              ],
              amples=[4.5, 5.5, 6.0])

    add_heading(doc, "7. Manteniment", level=1)

    add_heading(doc, "Comandaments habituals", level=2)
    add_code_block(doc, """sudo systemctl status comandes-venda-sap
sudo systemctl restart comandes-venda-sap
sudo journalctl -u comandes-venda-sap -f
sudo tail -f %s/access.log %s/error.log""" % (APP_DIR, APP_DIR))

    add_heading(doc, "Logs i rotació", level=2)
    add_para(doc,
             f"Els logs viuen a {APP_DIR}/access.log i error.log, amb rotació "
             "setmanal i 4 setmanes de retenció "
             "(/etc/logrotate.d/comandes-venda-sap). Comprovació el dilluns:")
    add_code_block(doc, f"ls -la {APP_DIR}/*.log*")
    add_para(doc, "Els fitxers de la setmana anterior han de tenir extensió .1.gz.",
             size=10, color=COLOR_MUTED)

    add_heading(doc, "Els dos serveis del servidor", level=2)
    add_taula(doc,
              ["Aplicació", "Servei systemd", "Directori"],
              [
                  ["Kais (producció)", "comandes-venda.service",
                   "/var/www/comandes-venda"],
                  ["SAP (validació)", "comandes-venda-sap.service", APP_DIR],
              ],
              amples=[4.0, 6.0, 6.0])

    add_avis(doc, "El servei comandes-venda.service és l'aplicació en producció i "
                  "ha de quedar intacte fins al novembre de 2026. Cap pas d'aquesta "
                  "guia el toca.")

    # ================= 8. FUTUR =================
    add_heading(doc, "8. Què vindrà després (informatiu)", level=1)

    add_para(doc,
             "Quan la versió SAP hagi acumulat prou temps de funcionament normal, "
             "es plantejarà que hereti la URL històrica. Amb aquesta arquitectura, "
             "aquell canvi serà només de DNS: no caldrà tocar cap servei ni cap "
             "port al servidor.")

    add_taula(doc,
              ["Registre", "Abans", "Després"],
              [
                  ["comandes.agrienergia.local", IP_KAIS, IP_SAP],
                  ["comandes-kais.agrienergia.local", "—", IP_KAIS + " (nou)"],
                  ["comandes-sap.agrienergia.local", IP_SAP, "sense canvis"],
              ],
              amples=[7.0, 4.5, 4.5])

    add_para(doc,
             "La marxa enrere seria revertir el registre, amb una propagació de ~5 "
             "minuts gràcies al TTL curt. Aquesta operació no forma part d'aquest "
             "desplegament; es demanarà per separat.")

    # ================= CONTACTES =================
    add_heading(doc, "Contacte", level=1)
    add_para(doc, "Oscar Hijazo — ohijazo@agrienergia.com", bold=True)
    add_para(doc,
             "Documentació tècnica completa al repositori de l'aplicació: "
             "deploy/README.md (arquitectura de xarxa), "
             "docs/runbook_swap_url_produccio.md (procediment detallat), "
             "docs/peticio_dns_sistemes.md (aquesta petició en text pla).",
             size=10, color=COLOR_MUTED)

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
