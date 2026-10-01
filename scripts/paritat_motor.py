"""Instantania del comportament de les consultes del motor, i comparacio.

Les set funcions que fa servir `motor.calcular_embalatges` es migraran de SQL
Server directe a Service Layer. Aquest script existeix per poder demostrar que
el resultat no canvia.

Us:
    # 1) ABANS de tocar res: capturar el comportament actual
    python scripts/paritat_motor.py --captura

    # 2) Despres de cada canvi: comparar
    python scripts/paritat_motor.py
    python scripts/paritat_motor.py --backend sl
    python scripts/paritat_motor.py --detall

Codi de sortida 0 si tot coincideix amb la instantania, 1 si no.

Per que una instantania i no una comparacio SQL-contra-SL en viu: aquestes
funcions les fa servir el boto de B1UP, que es el que esta en produccio. Una
instantania presa abans de començar cobreix tambe el cas que el canvi espatlli
el cami SQL, no nomes que el de Service Layer no coincideixi.

ATENCIO: el fitxer d'instantania conte dades reals de clients (noms, adreces,
poblacions). Esta al .gitignore i NO s'ha de commitejar.

Les funcions tenen caches de modul amb TTL. L'arnes les buida abans de cada
crida: si no, la segona execucio tornaria el valor cachejat i no provaria res.
"""
import argparse
import dataclasses
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import _bootstrap  # noqa: F401,E402  — resol models/regles via KAIS_APP_PATH
import consultes  # noqa: E402

SNAPSHOT = os.path.join(_ROOT, "paritat_motor_snapshot.json")

# Caches de modul de consultes.py. Les buidem entre crides perque l'arnes
# provi de debo el cami de dades i no el diccionari.
_CACHES = [
    "_comanda_cache", "_linies_cache", "_direccio_cache", "_descrip_cache",
    "_palet_client_cache", "_palet_comanda_cache",
]


def _buida_caches() -> None:
    for nom in _CACHES:
        c = getattr(consultes, nom, None)
        if c is not None:
            c.clear()


def _serialitza(valor):
    """Converteix el resultat a una cosa comparable i desable a JSON."""
    if dataclasses.is_dataclass(valor) and not isinstance(valor, type):
        return {k: _serialitza(v) for k, v in dataclasses.asdict(valor).items()}
    if isinstance(valor, (list, tuple)):
        return [_serialitza(x) for x in valor]
    if isinstance(valor, dict):
        return {str(k): _serialitza(v) for k, v in sorted(valor.items(), key=lambda kv: str(kv[0]))}
    if isinstance(valor, (str, int, float, bool)) or valor is None:
        return valor
    return str(valor)   # dates i el que vingui


def construeix_matriu(conn, max_comandes: int) -> list[dict]:
    """Casos reals, treats de la BD.

    Es fa sempre per SQL: la matriu ha de ser la mateixa tant si despres
    comparem el backend SQL com el de Service Layer.
    """
    files = conn.execute(
        """
        SELECT TOP (?) h.Series, h.DocNum, RTRIM(h.CardCode) AS cli,
               RTRIM(h.ShipToCode) AS adr
        FROM   ORDR h WITH (NOLOCK)
        ORDER  BY h.DocEntry DESC
        """,
        max_comandes,
    ).fetchall()

    casos: list[dict] = []
    claus = []
    for r in files:
        sal, alb = str(r.Series), str(r.DocNum)
        claus.append((sal, alb))
        casos.append({"fn": "obtenir_comanda", "args": [sal, alb]})
        casos.append({"fn": "obtenir_linies", "args": [sal, alb]})
        casos.append({"fn": "obtenir_palet_comanda", "args": [sal, alb]})
        if r.cli:
            casos.append({"fn": "obtenir_direccio", "args": [r.cli, r.adr or ""]})
            casos.append({"fn": "obtenir_palet_client", "args": [r.cli, r.adr or None]})

    # El batch, en trossos de mides diferents (i un buit, que ha de tornar []).
    for mida in (0, 1, 3, 10):
        casos.append({"fn": "obtenir_linies_batch", "args": [claus[:mida]]})

    # Descripcions: articles que surten de debo a les linies, mes un inexistent
    # (que ha de tornar el codi mateix, no petar).
    arts = conn.execute(
        """
        SELECT DISTINCT TOP 30 RTRIM(l.ItemCode) AS art
        FROM   RDR1 l WITH (NOLOCK)
        WHERE  l.ItemCode IS NOT NULL
        ORDER  BY art
        """
    ).fetchall()
    for a in arts:
        casos.append({"fn": "obtenir_descrip_article", "args": [a.art]})
    casos.append({"fn": "obtenir_descrip_article", "args": ["NO_EXISTEIX"]})

    # Casos limit del que mes facilment peta.
    casos.append({"fn": "obtenir_direccio", "args": ["NO_EXISTEIX", "NO_EXISTEIX"]})
    casos.append({"fn": "obtenir_palet_client", "args": ["NO_EXISTEIX", None]})
    casos.append({"fn": "obtenir_linies", "args": ["999", "999999"]})
    return casos


def executa(conn, cas: dict):
    """Crida una funcio i torna el resultat serialitzat, o l'error."""
    fn = getattr(consultes, cas["fn"])
    args = cas["args"]
    _buida_caches()
    try:
        # obtenir_palet_client te el `conn` com a kwarg opcional al final;
        # la resta el reben com a primer posicional.
        if cas["fn"] == "obtenir_palet_client":
            res = fn(*args, conn=conn)
        else:
            res = fn(conn, *args)
        return {"ok": True, "valor": _serialitza(res)}
    except Exception as e:
        # Un ValueError esperat (comanda no trobada) forma part del contracte
        # i s'ha de reproduir igual, aixi que el desem com a resultat.
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def clau_cas(cas: dict) -> str:
    return cas["fn"] + "|" + json.dumps(cas["args"], default=str, sort_keys=True)


def main() -> int:
    p = argparse.ArgumentParser(description="Paritat de les consultes del motor.")
    p.add_argument("--captura", action="store_true",
                   help="Desa el comportament actual com a instantania de referencia.")
    p.add_argument("--backend", choices=("sql", "sl"),
                   help="Forca el backend d'aquesta execucio.")
    p.add_argument("--detall", action="store_true", help="Ensenya les diferencies.")
    p.add_argument("--comandes", type=int, default=40,
                   help="Quantes comandes entren a la matriu (per defecte 40).")
    args = p.parse_args()

    if args.backend:
        os.environ["SAP_BACKEND"] = args.backend

    conn = consultes.connectar()
    try:
        casos = construeix_matriu(conn, args.comandes)
        resultats = {clau_cas(c): executa(conn, c) for c in casos}
    finally:
        conn.close()

    if args.captura:
        with open(SNAPSHOT, "w", encoding="utf-8") as f:
            json.dump(resultats, f, ensure_ascii=False, indent=1, sort_keys=True)
        print(f"Instantania desada: {len(resultats)} casos -> {SNAPSHOT}")
        print("NO la commitegis: conte noms i adreces de clients reals.")
        return 0

    if not os.path.exists(SNAPSHOT):
        print(f"No hi ha instantania a {SNAPSHOT}.", file=sys.stderr)
        print("Executa primer: python scripts/paritat_motor.py --captura", file=sys.stderr)
        return 1

    with open(SNAPSHOT, encoding="utf-8") as f:
        referencia = json.load(f)

    nomes_ref = sorted(set(referencia) - set(resultats))
    nomes_ara = sorted(set(resultats) - set(referencia))
    comuns = sorted(set(referencia) & set(resultats))
    difs = [k for k in comuns if referencia[k] != resultats[k]]

    per_funcio: dict[str, list[int]] = {}
    for k in comuns:
        fn = k.split("|", 1)[0]
        ok, ko = per_funcio.setdefault(fn, [0, 0])
        per_funcio[fn] = [ok + 1, ko + (1 if k in difs else 0)]

    print(f"{'FUNCIO':<28} {'CASOS':>6} {'KO':>4}")
    for fn in sorted(per_funcio):
        n, ko = per_funcio[fn]
        print(f"{fn:<28} {n:>6} {ko:>4}" + ("  <-- revisar" if ko else ""))

    if args.detall:
        for k in difs[:8]:
            print()
            print(f"  DIFEREIX {k}")
            print(f"    referencia: {json.dumps(referencia[k], ensure_ascii=False)[:300]}")
            print(f"    ara:        {json.dumps(resultats[k], ensure_ascii=False)[:300]}")

    print()
    if nomes_ref or nomes_ara:
        print(f"AVIS: la matriu no coincideix amb la de la instantania "
              f"({len(nomes_ref)} casos perduts, {len(nomes_ara)} de nous). "
              f"Si les dades de SAP han canviat, torna a capturar.")
    if difs:
        print(f"HI HA {len(difs)} DIFERENCIES de {len(comuns)} casos comparats.")
        return 1
    print(f"Sense diferencies: {len(comuns)} casos igual que la instantania.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
