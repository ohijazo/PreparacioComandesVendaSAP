#!/bin/bash
# =============================================================================
# Smoke load test — POST /api/afegir-palets/<DocEntry>
# =============================================================================
# Ús:
#   bash smoke_load_test.sh [host_o_ip[:port]] <docentry> [<docentry> ...]
#
# Exemples:
#   bash smoke_load_test.sh 127.0.0.1:5002 128 129 130 131 132
#   bash smoke_load_test.sh comandes.agrienergia.local 128
#
# Objectiu: verificar que Gunicorn amb worker-class gthread no serialitza les
# crides a Service Layer. Si els temps concurrents són ~N× el temps de warmup,
# hi ha un lock (típicament re-login SL). En aquest cas revisar SLClient.
#
# IMPORTANT: l'endpoint ESCRIU línies de palet a la comanda. Passar-hi diversos
# DocEntry diferents, un per petició concurrent, que és el que fan els operaris de
# debò: cada un clica el botó a la seva comanda. Repetir el mateix DocEntry en
# paral·lel afegeix una cursa read-modify-write sobre les mateixes línies (sense
# lock al Service Layer) que pot tornar a generar palets duplicats — el bug del
# commit 1b3c6d6 — i el que mesuraries seria aquesta contenció, no la de Gunicorn.
#
# Fer-lo servir només contra comandes esborrany d'un entorn de test. Per netejar
# després: scripts/netejar_palet_*.py
# =============================================================================

set -u

HOST="${1:-127.0.0.1:5002}"
shift || true

if [ "$#" -eq 0 ]; then
    echo "ERROR: cal com a mínim un DocEntry." >&2
    echo "Ús: bash smoke_load_test.sh [host[:port]] <docentry> [<docentry> ...]" >&2
    exit 1
fi

DOCENTRIES=("$@")
N="${#DOCENTRIES[@]}"

echo "== Target: http://${HOST}/api/afegir-palets/<DocEntry> =="
echo "== DocEntry: ${DOCENTRIES[*]}  (${N}) =="
echo

if [ "$N" -eq 1 ]; then
    echo "AVÍS: un sol DocEntry. La fase concurrent el repetirà, i això mesura la"
    echo "      contenció sobre les línies d'aquesta comanda, no la de Gunicorn."
    echo "      Passa-hi 5-10 DocEntry diferents per tenir una lectura neta."
    echo
fi

# Warmup: la primera petició inclou el login a Service Layer i l'escalfament de
# les caches, així que el seu temps no és comparable amb els següents.
echo "== Warmup (1 petició, DocEntry ${DOCENTRIES[0]}) =="
curl -sS -X POST "http://${HOST}/api/afegir-palets/${DOCENTRIES[0]}" \
    -o /dev/null -w "HTTP %{http_code} en %{time_total}s\n"
echo

# Concurrència: si només hi ha un DocEntry es repeteix 10 vegades (comportament
# històric); si n'hi ha diversos, un per petició.
if [ "$N" -eq 1 ]; then
    PETICIONS=()
    for _ in $(seq 1 10); do PETICIONS+=("${DOCENTRIES[0]}"); done
else
    PETICIONS=("${DOCENTRIES[@]}")
fi

P="${#PETICIONS[@]}"
echo "== ${P} peticions concurrents (P=${P}) =="
printf '%s\n' "${PETICIONS[@]}" | xargs -I{} -P"${P}" -n1 \
    curl -sS -X POST "http://${HOST}/api/afegir-palets/{}" \
        -o /dev/null -w "DocEntry {} → HTTP %{http_code} en %{time_total}s\n"

echo
echo "Criteri: totes HTTP 200 i temps individual < 5 s."
echo "Si els temps concurrents són ~${P}× el warmup, Gunicorn està serialitzant."
