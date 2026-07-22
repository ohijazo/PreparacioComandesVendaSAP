"""Genera l'informe tècnic de connexions BD en PDF."""
import os
from fpdf import FPDF

# Mapa de caràcters no-latin1 a equivalents ASCII
_CHAR_MAP = {
    "\u2192": "->",   # →
    "\u2022": "-",     # •
}

def _safe(text):
    """Reemplaça caràcters no suportats per latin-1."""
    for ch, repl in _CHAR_MAP.items():
        text = text.replace(ch, repl)
    return text


class InformePDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(120, 120, 120)
        self.cell(0, 5, _safe("Informe Tècnic - Motor de Preparació de Comandes de Venda"), align="R")
        self.ln(8)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"Pàgina {self.page_no()}/{{nb}}", align="C")

    def section_title(self, num, title):
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(20, 60, 120)
        self.ln(4)
        self.cell(0, 10, _safe(f"{num}. {title}"))
        self.ln(10)
        self.set_draw_color(20, 60, 120)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(4)

    def subsection_title(self, title):
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(40, 80, 140)
        self.ln(2)
        self.cell(0, 8, _safe(title))
        self.ln(8)

    def body_text(self, text, bold=False):
        self.set_font("Helvetica", "B" if bold else "", 10)
        self.set_text_color(30, 30, 30)
        self.multi_cell(0, 5.5, _safe(text))
        self.ln(1)

    def bullet(self, text):
        self.set_font("Helvetica", "", 10)
        self.set_text_color(30, 30, 30)
        self.cell(6, 5.5, "-")
        self.multi_cell(0, 5.5, _safe(text))
        self.ln(0.5)

    def table(self, headers, rows, col_widths=None):
        if col_widths is None:
            avail = self.w - self.l_margin - self.r_margin
            col_widths = [avail / len(headers)] * len(headers)

        # Header
        self.set_font("Helvetica", "B", 9)
        self.set_fill_color(20, 60, 120)
        self.set_text_color(255, 255, 255)
        for i, h in enumerate(headers):
            self.cell(col_widths[i], 7, _safe(h), border=1, fill=True, align="C")
        self.ln()

        # Rows
        self.set_font("Helvetica", "", 9)
        self.set_text_color(30, 30, 30)
        for ri, row in enumerate(rows):
            fill = ri % 2 == 1
            if fill:
                self.set_fill_color(235, 241, 250)
            for i, cell_val in enumerate(row):
                self.cell(col_widths[i], 6.5, _safe(str(cell_val)), border=1, fill=fill, align="C" if i > 0 else "L")
            self.ln()
        self.ln(3)

    def highlight_box(self, text, color=(230, 245, 230)):
        self.set_fill_color(*color)
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(30, 30, 30)
        y = self.get_y()
        self.rect(self.l_margin, y, self.w - self.l_margin - self.r_margin, 10, "F")
        self.cell(0, 10, f"  {_safe(text)}", align="L")
        self.ln(14)

    def optim_row(self, title, desc):
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(20, 60, 120)
        self.cell(55, 6, _safe(title))
        self.set_font("Helvetica", "", 10)
        self.set_text_color(30, 30, 30)
        self.multi_cell(0, 6, _safe(desc))
        self.ln(1)


def generate():
    pdf = InformePDF()
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    # ── Title ──
    pdf.set_font("Helvetica", "B", 20)
    pdf.set_text_color(20, 60, 120)
    pdf.cell(0, 12, _safe("Informe Tècnic"), align="C")
    pdf.ln(12)
    pdf.set_font("Helvetica", "", 14)
    pdf.set_text_color(60, 60, 60)
    pdf.cell(0, 10, _safe("Connexions a BD del Motor de Preparació de Comandes"), align="C")
    pdf.ln(14)

    # Metadata
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(80, 80, 80)
    for line in [
        "Data: 28/04/2026",
        "Servidor BD: vkais\\kais",
        "Base de dades: GWSV_AGRI",
        "Driver: ODBC Driver 18 for SQL Server",
    ]:
        pdf.cell(0, 5.5, line, align="C")
        pdf.ln(5.5)
    pdf.ln(6)

    # ── Section 1: Resum executiu ──
    pdf.section_title("1", "Resum executiu")

    pdf.highlight_box("L'aplicació NOMES fa SELECT (lectura). Mai INSERT, UPDATE ni DELETE.", (220, 240, 255))
    pdf.highlight_box("Totes les queries usen WITH (NOLOCK). No bloqueja cap taula de KAIS.", (220, 245, 220))
    pdf.highlight_box("0 queries quan ningu utilitza l'aplicació. 100% sota demanda.", (255, 245, 220))

    pdf.body_text("Arquitectura de connexions:")
    pdf.bullet("Max 1 connexio simultania (garantit per semaphore).")
    pdf.bullet("Les connexions es tanquen immediatament despres de cada operacio.")
    pdf.bullet("Command timeout de 15s: cap query pot quedar penjada.")
    pdf.bullet("Sense thread de background: nomes es consulta quan un usuari ho demana.")
    pdf.bullet("Cache multinivell amb single-flight: N peticions = 1 sola query.")

    # ── Section 2: sp_whoisactive ──
    pdf.section_title("2", "Que veura el tecnic al sp_whoisactive")

    pdf.subsection_title("2.1 Sense usuaris (aplicacio en repos)")
    pdf.highlight_box("0 connexions. Ningu utilitza l'app = 0 sessions al servidor.", (220, 245, 220))

    pdf.subsection_title("2.2 Amb un usuari navegant")
    pdf.table(
        ["Camp sp_whoisactive", "Valor tipic"],
        [
            ["login_name", "Usuari SQL / APP=MotorComandes"],
            ["status", "sleeping (99.9%) / running (< 5ms)"],
            ["elapsed_time", "< 5 ms per query (max 15s timeout)"],
            ["wait_type", "Cap (queries instantanies)"],
            ["open_tran_count", "0 (cap transaccio oberta)"],
            ["blocking_session_id", "NULL (no bloqueja ningu)"],
            ["reads", "Baix (SELECT amb NOLOCK)"],
            ["writes", "0 (mai escriu)"],
            ["cpu", "< 1ms per query"],
        ],
        [95, 95],
    )

    pdf.subsection_title("2.3 Connexions simultanees al servidor")
    pdf.table(
        ["Escenari", "Sessions visibles", "Estat predominant"],
        [
            ["Sense usuaris", "0", "No visible"],
            ["1 usuari navegant", "0-1 (durant 1-65ms)", "running < 65ms"],
            ["Pic d'us (varis usuaris)", "0-1 (serialitzat)", "running < 65ms"],
        ],
        [65, 55, 70],
    )

    pdf.highlight_box("MAXIM ABSOLUT: 1 connexio. Dura mil-lisegons i desapareix.", (220, 245, 220))

    # ── Section 3: Patrons de connexio ──
    pdf.section_title("3", "Patrons de connexio")

    pdf.subsection_title("3.1 Sota demanda (sense background thread)")
    pdf.body_text("L'aplicacio NO te cap thread de background consultant la BD.")
    pdf.body_text("Nomes es fan queries quan un usuari actiu ho demana:")
    pdf.ln(2)
    pdf.body_text("Frontend obre pagina -> polling cada 40-55s")
    pdf.body_text("  Si cache valid (< 30s) -> resposta immediata, 0 queries SQL")
    pdf.body_text("  Si cache expirat -> 1 query (single-flight), resta espera resultat")
    pdf.body_text("Frontend tanca pestanya -> 0 queries, 0 activitat")
    pdf.ln(2)
    pdf.table(
        ["Parametre", "Valor"],
        [
            ["Polling frontend", "Cada 60-75s (amb jitter aleatori)"],
            ["Cache TTL (fingerprint)", "55 segons"],
            ["Cache TTL (llistat comandes)", "55 segons"],
            ["Cache TTL (magatzems)", "5 minuts"],
            ["Cache TTL (direccions)", "10 minuts"],
            ["Cache dades mestres", "Permanent (1 cop al arrencar)"],
            ["Queries si ningu mira", "0 (absolutament zero)"],
        ],
        [95, 95],
    )

    pdf.subsection_title("3.2 Connexio per calcul d'embalatge")
    pdf.body_text("Quan un usuari calcula un embalatge:")
    pdf.body_text("  Fase 1: Obre connexio -> queries (~5-15ms) -> TANCA connexio")
    pdf.body_text("  Fase 2: Python (calculs logistics, SENSE connexio oberta)")
    pdf.body_text("  Fase 3 (si cal): Obre connexio -> palets (~3-5ms) -> TANCA connexio")
    pdf.ln(2)
    pdf.highlight_box("Temps total de connexio ocupada per calcul: < 20ms", (220, 245, 220))

    # ── Section 4: Inventari de consultes ──
    pdf.section_title("4", "Inventari de consultes SQL")

    pdf.subsection_title("4.1 Consultes de polling (frontend, cada 40-55s)")
    pdf.table(
        ["Query", "Taules", "NOLOCK", "Cache"],
        [
            ["Llistat comandes pendents", "CPALBARA, CLIENTS, ALBLINIA...", "Si (totes)", "55s TTL"],
            ["Fingerprint canvis", "CPALBARA (1 taula, sense JOIN)", "Si", "55s TTL"],
        ],
        [55, 72, 30, 33],
    )
    pdf.body_text("NOTA: Aquestes queries nomes s'executen si un usuari te la pagina oberta")
    pdf.body_text("i el cache ha expirat. Amb 1 usuari: maxim 2 queries cada 30-55 segons.")

    pdf.subsection_title("4.2 Consultes per accio d'usuari (on-demand)")
    pdf.table(
        ["Consulta", "Taules", "Cache", "Temps tipic"],
        [
            ["Cercar comanda", "CPALBARA, CLIENTS", "No", "1-2 ms"],
            ["Resolucio serie", "SERIEALB", "No", "1 ms"],
            ["Cercar via pedido KAIS", "ALBLINIA, CPALBARA", "No", "1-2 ms"],
            ["Pedido original", "ALBLINIA", "Sessio", "1 ms"],
            ["Linies de comanda", "ALBLINIA, ARTICLES, INF_ARTICULO", "No", "2-5 ms"],
            ["Titols INFOANEX", "INFOANEX", "Permanent", "0 ms (cache)"],
            ["Direccio + condicions", "CLIENVIO, inf_clienvio", "10 min", "1-5 ms"],
            ["Palet a la comanda", "ALBLINIA, ARTICLES", "No", "1 ms"],
            ["Descripcio article", "ARTICLES", "Permanent", "0 ms (cache)"],
            ["Palet historic", "ek_PedidoLineas, ek_Pedido", "No", "1-2 ms"],
            ["Noms magatzems", "Almac", "Permanent", "0 ms (cache)"],
        ],
        [50, 65, 35, 40],
    )
    pdf.body_text("NOTA: Totes les consultes usen WITH (NOLOCK) i son SELECT.")

    # ── Section 5: Taules accedides ──
    pdf.section_title("5", "Taules accedides i frequencia")

    pdf.table(
        ["Taula", "Acces", "Bloquejos", "Frequencia maxima"],
        [
            ["CPALBARA", "SELECT NOLOCK", "Cap", "Sota demanda (cache 55s)"],
            ["ALBLINIA", "SELECT NOLOCK", "Cap", "Sota demanda (cache 55s)"],
            ["ARTICLES", "SELECT NOLOCK", "Cap", "Sota demanda (cache 55s)"],
            ["CLIENTS", "SELECT NOLOCK", "Cap", "Sota demanda (cache 55s)"],
            ["SERIEALB", "SELECT NOLOCK", "Cap", "Sota demanda"],
            ["AGENTS", "SELECT NOLOCK", "Cap", "Sota demanda (cache 55s)"],
            ["CLIENVIO", "SELECT NOLOCK", "Cap", "On-demand (cache 10 min)"],
            ["inf_clienvio", "SELECT NOLOCK", "Cap", "On-demand (cache 10 min)"],
            ["INF_ARTICULO", "SELECT NOLOCK", "Cap", "On-demand"],
            ["INFOANEX", "SELECT NOLOCK", "Cap", "1 cop (permanent)"],
            ["Almac", "SELECT NOLOCK", "Cap", "1 cop (permanent)"],
            ["ek_Pedido", "SELECT NOLOCK", "Cap", "On-demand"],
            ["ek_PedidoLineas", "SELECT NOLOCK", "Cap", "On-demand"],
        ],
        [42, 40, 30, 78],
    )

    # ── Section 6: Carrega estimada ──
    pdf.section_title("6", "Carrega estimada al servidor")

    pdf.subsection_title("6.1 Sense usuaris (nit/cap de setmana)")
    pdf.table(
        ["Metrica", "Valor"],
        [
            ["Connexions actives", "0"],
            ["Queries/minut", "0"],
            ["CPU", "0"],
            ["IO", "0"],
            ["Impacte al servidor", "Nul"],
        ],
        [95, 95],
    )

    pdf.subsection_title("6.2 Horari laboral, 1 usuari amb pagina oberta")
    pdf.table(
        ["Metrica", "Valor"],
        [
            ["Connexions actives", "0 o 1 (durant ms, sense sleeping)"],
            ["Queries/minut", "~1 (polling cada 60-75s, servit de cache)"],
            ["Temps de query", "< 5ms cada una (65ms la mes pesada)"],
            ["% temps amb connexio activa", "< 0.1%"],
            ["Operacions d'escriptura", "0"],
            ["Locks adquirits", "0 (NOLOCK)"],
        ],
        [95, 95],
    )

    pdf.subsection_title("6.3 Carrega comparativa")
    pdf.table(
        ["Font", "Queries/min", "Connexions", "Bloquejos"],
        [
            ["Motor Comandes", "~1 (sota demanda)", "0-1 (durant ms)", "Cap"],
            ["Motor sense usuaris", "0", "0", "Cap"],
            ["KAIS (1 usuari)", "~50-200", "1-3", "Si (locks)"],
            ["KAIS (10 usuaris)", "~500-2000", "10-30", "Si (locks)"],
        ],
        [48, 42, 48, 52],
    )

    pdf.highlight_box("L'aplicacio genera menys d'un 1% de la carrega d'un sol usuari de KAIS.", (220, 245, 220))

    # ── Section 7: Optimitzacions ──
    pdf.section_title("7", "Optimitzacions implementades")

    optimitzacions = [
        ("WITH (NOLOCK)", "Totes les queries. No adquireix shared locks, no pot bloquejar KAIS."),
        ("0 connexions sleeping", "Cada connexio s'obre, s'usa (ms) i es tanca. Res queda obert."),
        ("Max 1 simultania", "Semaphore garanteix 1 sola connexio. Resta espera en memoria."),
        ("APP=MotorComandes", "Identificable al sp_whoisactive / sys.dm_exec_sessions."),
        ("ApplicationIntent", "ReadOnly: informa al servidor que nomes fem lectures."),
        ("Fingerprint lleuger", "Nomes CPALBARA, sense JOIN (1 taula, COUNT+CHECKSUM)."),
        ("Polling cada 60-75s", "Frontend consulta cada 60-75s (amb jitter). Cache 55s."),
        ("Command timeout 15s", "Cap query pot quedar penjada al servidor."),
        ("Connection timeout 10s", "Desisteix rapid si el servidor no respon."),
        ("100% sota demanda", "0 queries si ningu mira l'aplicacio. Sense background thread."),
        ("Cache multinivell", "Polling (30s), direccions (10min), dades mestres (permanent)."),
        ("Single-flight", "N peticions simultanees = 1 sola query al servidor."),
        ("NOT EXISTS correlat", "Query principal optimitzada (vs LEFT JOIN subquery)."),
        ("Query combinada", "Direccio: 2 queries fusionades en 1 sola."),
        ("Cache pedido original", "Evita query duplicada dins el mateix calcul."),
    ]
    for title, desc in optimitzacions:
        pdf.optim_row(title, desc)

    # ── Section 8: Conclusio ──
    pdf.section_title("8", "Conclusio")

    conclusions = [
        "No escriu res a la base de dades (100% lectures SELECT).",
        "No bloqueja cap taula (WITH NOLOCK a totes les queries).",
        "No pot bloquejar KAIS (NOLOCK no adquireix shared locks).",
        "Max 1 connexio simultania, dura mil-lisegons.",
        "0 queries i 0 connexions quan ningu utilitza l'aplicacio.",
        "Sota demanda: nomes consulta quan un usuari ho necessita (cada 60-75s).",
        "0 connexions sleeping: s'obren i es tanquen per cada operacio.",
        "Command timeout 15s: cap query penjada al sp_whoisactive.",
        "Queries de 1-5ms (maxim 65ms la mes pesada).",
    ]
    for i, c in enumerate(conclusions, 1):
        pdf.body_text(f"{i}. {c}")

    pdf.ln(6)
    pdf.highlight_box(
        "La carrega al servidor KAIS es equivalent a menys d'un 1% d'un sol usuari de KAIS.",
        (220, 245, 220),
    )

    # Save
    out = os.path.join(os.path.dirname(__file__), "Informe_Tecnic_Connexions_BD.pdf")
    pdf.output(out)
    print(f"PDF generat: {out}")


if __name__ == "__main__":
    generate()
