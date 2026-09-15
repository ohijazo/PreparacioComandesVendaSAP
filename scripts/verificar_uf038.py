"""Compara el codi C# de la UF-038 guardat a SAP amb la còpia del repo.

Ús:
    python scripts/verificar_uf038.py

Serveix per (a) saber si algú ha tocat el codi directament a B1UP sense
actualitzar el repo, i (b) confirmar que un "enganxa i actualitza" al
Configurator ha arribat de veres a la base de dades.

Només llegeix. Compara ignorant comentaris i espais: el que importa és el
codi executable.
"""
import difflib
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import _bootstrap  # noqa: F401
import consultes

UF_CODE = "UF-038"
FITXER_REPO = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "docs", "b1up_uf038_calcular_embalatges.cs",
)


def _norm(text: str) -> list[str]:
    """Línies de codi executable: sense comentaris ni espais sobrants.

    B1UP desa el codi amb salts de línia CR sols; `splitlines()` els entén
    tots, un `split("\n")` no.
    """
    return [
        l.strip() for l in text.splitlines()
        if l.strip() and not l.strip().startswith("//")
    ]


def main() -> int:
    conn = consultes.connectar()
    try:
        row = conn.execute(
            "SELECT Name, UpdateDate, CAST(U_BOY_DYCO AS nvarchar(MAX)) AS codi "
            "FROM [@BOY_41_FUNCTIONS] WHERE Code = ?",
            UF_CODE,
        ).fetchone()
    finally:
        conn.close()

    if row is None or not row.codi:
        print(f"{UF_CODE} no existeix a @BOY_41_FUNCTIONS (o no té codi dinàmic).")
        return 2

    sap = _norm(row.codi)
    repo = _norm(io.open(FITXER_REPO, encoding="utf-8").read())

    print(f"{UF_CODE} · {row.Name} · última actualització a SAP: {row.UpdateDate:%Y-%m-%d}")
    print(f"línies de codi — SAP: {len(sap)} · repo: {len(repo)}")

    if sap == repo:
        print("IDENTICS - res a fer")
        return 0

    print("DIFEREIXEN:")
    for linia in difflib.unified_diff(repo, sap, "repo", "sap", lineterm=""):
        print(linia)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
