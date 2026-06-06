#!/bin/bash
# refresh_data.sh — ververs de STAGING-DB-kopieën vanaf live, EENRICHTING + verplichte PII-scrub.
# Draai als root (leest live-DB's read-only, doet systemctl). Bron altijd mode=ro -> kan live
# technisch niet wijzigen. Doel uitsluitend onder /opt/stresschecker-staging/.
#
# Eis #3: de scrub is NIET optioneel. `set -e` + de zelf-verifiërende scrub_pii.py zorgen dat de
# service NIET (her)start zolang er ook maar één echt extern e-mailadres in de kopie staat.
set -euo pipefail

STAG=/opt/stresschecker-staging/data
SCRUB=/opt/stresschecker-staging/scrub_pii.py

echo "[refresh] staging stoppen (voorkom schrijven tijdens kopie)…"
systemctl stop stresschecker-staging 2>/dev/null || true

echo "[refresh] DB's kopiëren (bron mode=ro, eenrichting live→staging)…"
for pair in \
  "/opt/stresschecker/data/sc_measurements.db:$STAG/sc_measurements.db" \
  "/opt/stresschecker/data/sc_pro.db:$STAG/sc_pro.db" \
  "/opt/ic-license-server/data/saas_licenses.db:$STAG/saas_licenses.db"; do
    SRC=${pair%%:*}; DST=${pair##*:}
    sqlite3 "file:$SRC?mode=ro" ".backup '$DST'"
    echo "  $SRC -> $DST"
done
chown -R scstaging:scstaging "$STAG"

echo "[refresh] VERPLICHTE PII-scrub + verificatie…"
# Bij een leak eindigt scrub_pii.py met exit 1 -> set -e stopt hier -> service blijft gestopt.
python3 "$SCRUB" "$STAG"

echo "[refresh] scrub OK — staging starten…"
systemctl start stresschecker-staging
echo "[refresh] Staging-data ververst + gescrubd: $(date '+%Y-%m-%d %H:%M:%S')"
