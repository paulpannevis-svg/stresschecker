#!/bin/bash
# ============================================================================
# Emergency rollback: herstel de 3 StressChecker-DB's uit een backup-set.
# FASE-2-VOORBEREIDING. Niet in cron. Voer ALLEEN handmatig uit bij nood.
#
# Corrigeert de fouten uit het spec-concept:
#  - JUISTE paden: saas_licenses.db staat in /opt/ic-license-server/data/,
#    NIET in /opt/stresschecker/data/.
#  - GEEN `kill -9 <master>` gevolgd door HUP (dat is onzin: na -9 is de master
#    weg). We doen een GRACEFUL HUP zodat workers verse DB-connecties openen.
#  - Maakt eerst een snapshot van de HUIDIGE staat (rollback is zelf omkeerbaar).
#  - Verifieert dat elke backup een geldige SQLite-DB is (integrity_check).
#
# Gebruik:
#   ./rollback_restore.sh <backup-suffix> --confirm
# waarbij <backup-suffix> de tijd-suffix is van de backup-bestanden, bv:
#   retention-1782633439   (Fase-1)   of   fase2-20260628-031500
# Verwachte bestanden:
#   /opt/ic-license-server/data/saas_licenses.db.bak-<suffix>
#   /opt/stresschecker/data/sc_pro.db.bak-<suffix>
#   /opt/stresschecker/data/sc_measurements.db.bak-<suffix>
# ============================================================================
set -euo pipefail

SAAS=/opt/ic-license-server/data/saas_licenses.db
PRO=/opt/stresschecker/data/sc_pro.db
MEAS=/opt/stresschecker/data/sc_measurements.db

SUFFIX="${1:-}"
CONFIRM="${2:-}"
if [[ -z "$SUFFIX" || "$CONFIRM" != "--confirm" ]]; then
  echo "Gebruik: $0 <backup-suffix> --confirm"
  echo "  (zonder --confirm gebeurt er niets)"
  exit 2
fi

declare -A MAP=( ["$SAAS"]="${SAAS}.bak-${SUFFIX}" ["$PRO"]="${PRO}.bak-${SUFFIX}" ["$MEAS"]="${MEAS}.bak-${SUFFIX}" )

# 1. Alle backups aanwezig + geldig SQLite?
for live in "${!MAP[@]}"; do
  bak="${MAP[$live]}"
  [[ -f "$bak" ]] || { echo "FOUT: backup ontbreekt: $bak"; exit 1; }
  if ! sqlite3 "$bak" "PRAGMA integrity_check;" | grep -q '^ok$'; then
    echo "FOUT: backup is geen geldige/intacte SQLite-DB: $bak"; exit 1
  fi
done
echo "[rollback] alle 3 backups aanwezig + integrity_check OK"

# 2. Snapshot van de HUIDIGE staat (rollback zelf omkeerbaar maken)
TS=$(date +%Y%m%d-%H%M%S)
for live in "${!MAP[@]}"; do cp -a "$live" "${live}.pre-rollback-${TS}"; done
echo "[rollback] huidige staat veiliggesteld als *.pre-rollback-${TS}"

# 3. Restore (de app opent per request een verse sqlite3-connectie; swap werkt
#    bij de volgende request, HUP forceert schone workers)
for live in "${!MAP[@]}"; do cp -a "${MAP[$live]}" "$live"; done
echo "[rollback] 3 DB's hersteld uit suffix ${SUFFIX}"

# 4. Graceful reload van de prod-master (dynamisch PID, GEEN kill -9)
MASTER=$(pgrep -f 'gunicorn.*127.0.0.1:8080' | head -1 || true)
if [[ -n "$MASTER" ]]; then kill -HUP "$MASTER" && echo "[rollback] HUP master $MASTER"; else echo "[rollback] WAARSCHUWING: master niet gevonden — herstart handmatig"; fi

# 5. Verifieer
sleep 3
echo "[rollback] DONE suffix=${SUFFIX} users=$(sqlite3 "$SAAS" 'SELECT COUNT(*) FROM users;')"
echo "[ROLLBACK] completed: ${SUFFIX} (pre-rollback-snapshot: ${TS})"
