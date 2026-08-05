#!/bin/bash
# =============================================================================
# Smoke load test — POST /api/afegir-palets/<DocEntry>
# =============================================================================
# Ús:
#   bash smoke_load_test.sh [host_o_ip[:port]] <docentry_test>
#
# Exemples:
#   bash smoke_load_test.sh 127.0.0.1:5002 128
#   bash smoke_load_test.sh comandes.agrienergia.local 128
#
# Objectiu: verificar que Gunicorn amb worker-class gthread no serialitza les
# crides a Service Layer. Si els 10 temps concurrents són ~10× el temps warmup,
# hi ha un lock (típicament re-login SL). En aquest cas revisar SLClient.
# =============================================================================

set -u

HOST="${1:-127.0.0.1:5002}"
DOCENTRY="${2:?Cal DocEntry de test: bash smoke_load_test.sh <host> <docentry>}"
URL="http://${HOST}/api/afegir-palets/${DOCENTRY}"

echo "== Target: ${URL} =="
echo

echo "== Warmup (1 petició) =="
curl -sS -X POST "${URL}" -o /dev/null -w "HTTP %{http_code} en %{time_total}s\n"
echo

echo "== 10 peticions concurrents (P=10) =="
seq 1 10 | xargs -I{} -P10 -n1 \
    curl -sS -X POST "${URL}" -o /dev/null -w "HTTP %{http_code} en %{time_total}s\n"
