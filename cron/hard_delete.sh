#!/bin/bash
# ============================================================================
# DORMANT — DESTRUCTIEVE hard-delete van >180d gearchiveerde users (Fase 2).
# NIET in crontab geïnstalleerd. ONOMKEERBAAR (m.u.v. backup-restore).
#
# Dubbele grendel:
#   1. Dit script staat in geen cron.
#   2. retention.py weigert hard-delete zonder RETENTION_HARD_DELETE_CLEARED=1.
# Activering pas ná juridische clearing — zie docs/retention/ACTIVATION.md.
# ============================================================================
set -euo pipefail
cd /opt/stresschecker
# Maak ALTIJD eerst een verse backup-snapshot vóór een destructieve run.
SUFFIX="fase2-$(date +%Y%m%d-%H%M%S)"
cp /opt/ic-license-server/data/saas_licenses.db  "/opt/ic-license-server/data/saas_licenses.db.bak-${SUFFIX}"
cp /opt/stresschecker/data/sc_pro.db             "/opt/stresschecker/data/sc_pro.db.bak-${SUFFIX}"
cp /opt/stresschecker/data/sc_measurements.db    "/opt/stresschecker/data/sc_measurements.db.bak-${SUFFIX}"
echo "[hard_delete] backup-suffix=${SUFFIX}"
# RETENTION_HARD_DELETE_CLEARED moet expliciet in de cron-omgeving gezet zijn.
/usr/bin/python3 /opt/stresschecker/retention.py --hard-delete --execute \
    >> /opt/stresschecker/logs/retention.log 2>&1
