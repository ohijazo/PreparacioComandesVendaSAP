"""Format del resum textual del càlcul per als UDFs de SAP.

Produeix el text que s'escriu a `ORDR.U_FCEmbalatgeResum` (Alfa 254) i
l'estat que va a `ORDR.U_FCEmbalatgeEstat` (Alfa 30) a partir d'un
`Resultat` del motor.

Sense dependències de SAP — pure function.

Exemples de sortida:
    formatar_resum(r_calculat) → ("3 palets · 120 sacs · 2×palet europeu, 1×palet nou · CALCULAT", "CALCULAT")
    formatar_resum(r_sota_min) → ("10 sacs · SOTA_MINIM · RF2: comanda amb 10 sacs...", "SOTA_MINIM")
    formatar_resum(r_no_calc)  → ("NO CALCULABLE · RF1: comanda amb article granel...", "NO_CALCULABLE")
"""
from __future__ import annotations

from models import Estat, Resultat

# Longitud màxima del UDF `U_FCEmbalatgeResum` a SAP (Alfa 254).
_MAX_LEN = 254
_ELLIPSIS = "…"


def formatar_resum(resultat: Resultat) -> tuple[str, str]:
    """Genera (text_resum, estat) per als UDFs de SAP.

    - `text_resum`: format llegible per l'operari, ≤ 254 chars (Alfa 254).
    - `estat`: valor de l'enum `Estat` (CALCULAT / CALCULAT_AMB_AVISOS /
      SOTA_MINIM / NO_CALCULABLE).
    """
    estat = resultat.estat.value

    if resultat.estat == Estat.NO_CALCULABLE:
        text = _format_no_calculable(resultat)
    elif resultat.estat == Estat.SOTA_MINIM:
        text = _format_sota_minim(resultat)
    else:
        # CALCULAT o CALCULAT_AMB_AVISOS
        text = _format_calculat(resultat)

    return _truncar(text), estat


# ============================================================
# Format per estat
# ============================================================

def _format_no_calculable(r: Resultat) -> str:
    parts = ["NO CALCULABLE"]
    motiu = _primer_motiu(r.missatges)
    if motiu:
        parts.append(motiu)
    return " · ".join(parts)


def _format_sota_minim(r: Resultat) -> str:
    n_sacs = sum(e.total_sacs for e in r.embalatges)
    parts = [f"{n_sacs} sacs", "SOTA_MINIM"]
    motiu = _primer_motiu(r.missatges)
    if motiu:
        parts.append(motiu)
    return " · ".join(parts)


def _format_calculat(r: Resultat) -> str:
    n_palets = len(r.embalatges)
    n_sacs = sum(e.total_sacs for e in r.embalatges)
    parts = [f"{n_palets} palets", f"{n_sacs} sacs"]

    palets_desc = _describe_palets(r)
    if palets_desc:
        parts.append(palets_desc)

    parts.append(r.estat.value)

    if r.estat == Estat.CALCULAT_AMB_AVISOS:
        n_avisos = _comptar_avisos(r.trazabilitat)
        if n_avisos:
            parts.append(f"{n_avisos} avisos")

    return " · ".join(parts)


# ============================================================
# Helpers
# ============================================================

def _primer_motiu(missatges: list[str]) -> str:
    """Extreu el primer motiu llegible del primer missatge.

    Talla per punt o salt de línia perquè el resum sigui compacte.
    """
    if not missatges:
        return ""
    msg = missatges[0].strip()
    # Tallar per primer punt o salt de línia
    for sep in ("\n", ". "):
        idx = msg.find(sep)
        if idx > 0:
            msg = msg[:idx]
            break
    return msg.strip()


def _describe_palets(r: Resultat) -> str:
    """Retorna '2×palet europeu, 1×palet nou' per als palets físics."""
    fisics = [p for p in r.palets if p.es_fisic]
    if not fisics:
        return ""
    return ", ".join(
        f"{p.quantitat}×{p.art_descrip.lower()}" for p in fisics
    )


def _comptar_avisos(trazabilitat: list[str]) -> int:
    """Compta línies de traçabilitat que contenen 'AVÍS' o 'AVIS'."""
    return sum(1 for t in trazabilitat if "AVÍS" in t or "AVIS" in t)


def _truncar(text: str) -> str:
    if len(text) <= _MAX_LEN:
        return text
    return text[: _MAX_LEN - 1] + _ELLIPSIS
