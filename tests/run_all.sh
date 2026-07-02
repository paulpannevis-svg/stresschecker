#!/bin/bash
# StressChecker regressietest-suite — orchestrator.
#
# Draait: pre-flight residu-check → setup → routing (A) → berekening (B)
#        → Spoor 3 portal (C) → Widerruf (D) → pipeline-parity (E)
#        → cleanup (via trap, altijd).
# Exit 0 = alle tests geslaagd, exit 1 = residu / setup-fout / test-fail.
# Target runtime: onder 2 minuten.

set -u
cd /opt/stresschecker/tests

START=$(date +%s)

echo "=== pre-flight residu-check ==="
if ! python3 lib/cleanup.py check; then
    echo
    echo "ABORT: residu aanwezig van vorige run." >&2
    echo "Controleer handmatig wat er staat (zie output hierboven)" >&2
    echo "en draai 'python3 lib/cleanup.py cleanup' alléén als je zeker weet" >&2
    echo "dat het om testdata gaat. Daarna opnieuw run_all.sh." >&2
    exit 1
fi

# Cleanup-trap pas INSTELLEN nadat pre-flight geslaagd is, zodat een echte
# residu-melding niet stilletjes wordt opgeruimd vóór de gebruiker hem ziet.
trap 'echo; echo "=== cleanup (trap) ==="; python3 /opt/stresschecker/tests/lib/cleanup.py cleanup' EXIT

echo
echo "=== setup ==="
if ! python3 lib/setup.py; then
    echo "ABORT: setup faalde" >&2
    exit 1
fi

A_LOG=$(mktemp)
B_LOG=$(mktemp)
C_LOG=$(mktemp)
D_LOG=$(mktemp)
E_LOG=$(mktemp)
trap 'echo; echo "=== cleanup (trap) ==="; python3 /opt/stresschecker/tests/lib/cleanup.py cleanup; rm -f "'"$A_LOG"'" "'"$B_LOG"'" "'"$C_LOG"'" "'"$D_LOG"'" "'"$E_LOG"'"' EXIT

echo
echo "=== categorie A — routing tests ==="
python3 check_routing.py | tee "$A_LOG"
A_RC=${PIPESTATUS[0]}

echo
echo "=== categorie B — kernberekeningen ==="
python3 check_calculations.py | tee "$B_LOG"
B_RC=${PIPESTATUS[0]}

echo
echo "=== categorie C — Spoor 3 Stripe Customer Portal ==="
python3 test_spoor3_portal.py | tee "$C_LOG"
C_RC=${PIPESTATUS[0]}

echo
echo "=== categorie D — Widerruf-/gezondheidsdata-instemming ==="
python3 test_consent_widerruf.py | tee "$D_LOG"
D_RC=${PIPESTATUS[0]}

echo
echo "=== categorie E — cross-pipeline parity (RI/zone/quality) ==="
python3 test_pipeline_parity.py | tee "$E_LOG"
E_RC=${PIPESTATUS[0]}

# Parse per-suite totalen uit "categorie X: P passed, F failed (Ts)"
read A_PASSED A_FAILED <<< "$(awk '/^categorie A:/ { print $3, $5 }' "$A_LOG")"
read B_PASSED B_FAILED <<< "$(awk '/^categorie B:/ { print $3, $5 }' "$B_LOG")"
read C_PASSED C_FAILED <<< "$(awk '/^categorie C:/ { print $3, $5 }' "$C_LOG")"
read D_PASSED D_FAILED <<< "$(awk '/^categorie D:/ { print $3, $5 }' "$D_LOG")"
# categorie E rapporteert als "test_pipeline_parity: P passed, F failed  (Ts)"
read E_PASSED E_FAILED <<< "$(awk '/^test_pipeline_parity:/ { print $2, $4 }' "$E_LOG")"
: "${A_PASSED:=0}" "${A_FAILED:=?}"
: "${B_PASSED:=0}" "${B_FAILED:=?}"
: "${C_PASSED:=0}" "${C_FAILED:=?}"
: "${D_PASSED:=0}" "${D_FAILED:=?}"
: "${E_PASSED:=0}" "${E_FAILED:=?}"

TOTAL_PASSED=$(( A_PASSED + B_PASSED + C_PASSED + D_PASSED + E_PASSED ))
TOTAL_FAILED=$(( A_FAILED + B_FAILED + C_FAILED + D_FAILED + E_FAILED ))
ELAPSED=$(( $(date +%s) - START ))

echo
echo "===================================================="
echo "TOTAAL: $TOTAL_PASSED passed, $TOTAL_FAILED failed  (${ELAPSED}s)"
echo "  categorie A (routing):     $A_PASSED/$(( A_PASSED + A_FAILED ))"
echo "  categorie B (berekening):  $B_PASSED/$(( B_PASSED + B_FAILED ))"
echo "  categorie C (Spoor 3):     $C_PASSED/$(( C_PASSED + C_FAILED ))"
echo "  categorie D (instemming):  $D_PASSED/$(( D_PASSED + D_FAILED ))"
echo "  categorie E (parity):      $E_PASSED/$(( E_PASSED + E_FAILED ))"
echo "===================================================="

if [ "$TOTAL_FAILED" -ne 0 ] || [ "$A_RC" -ne 0 ] || [ "$B_RC" -ne 0 ] || [ "$C_RC" -ne 0 ] || [ "$D_RC" -ne 0 ] || [ "$E_RC" -ne 0 ]; then
    exit 1
fi
exit 0
