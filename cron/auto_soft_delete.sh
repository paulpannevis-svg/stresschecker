#!/bin/bash
# ============================================================================
# DORMANT — auto-soft-delete van verlopen users (Fase 2).
# NIET in crontab geïnstalleerd. Activering: docs/retention/ACTIVATION.md
# (pas ná juridische clearing). OMKEERBAAR: zet alleen archived_at/retention_until.
# ============================================================================
set -euo pipefail
cd /opt/stresschecker
/usr/bin/python3 /opt/stresschecker/retention.py --auto-soft-delete --execute \
    >> /opt/stresschecker/logs/retention.log 2>&1
