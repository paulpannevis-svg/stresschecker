#!/bin/bash
DATE=$(date +%Y%m%d-%H%M)
cp /opt/stresschecker/app.py /opt/backups/app.py.$DATE
cp /opt/stresschecker/SYSTEM_REFERENCE.md /opt/backups/SYSTEM_REFERENCE.md.$DATE 2>/dev/null
cp -r /opt/stresschecker/templates /opt/backups/templates.$DATE
cp -r /opt/stresschecker/static /opt/backups/static.$DATE
cp /opt/stresschecker/data/sc_pro.db /opt/backups/sc_pro.db.$DATE
cp /opt/stresschecker/data/sc_measurements.db /opt/backups/sc_measurements.db.$DATE
cp /opt/ic-license-server/data/saas_licenses.db /opt/backups/saas_licenses.db.$DATE
python3 /opt/stresschecker/gen_context.py
echo "Backup + Context compleet: $DATE"

# ── Auto-rotatie: houd de 3 nieuwste per backup-type (dagelijkse fulls: 5) ────
# Toegevoegd 2026-06-24 — voorheen geen rotatie -> /opt/backups liep vol (92%).
# Per-type (NIET keep-N-overall, anders blijft maar 1 DB-generatie over).
# rm -rf dekt zowel files (app.py/db) als dirs (templates/static).
_rotate_keep() {                      # $1=glob  $2=aantal-te-behouden
    ls -1dt $1 2>/dev/null | tail -n +$(( $2 + 1 )) | while IFS= read -r _p; do
        rm -rf "$_p"
    done
}
for _t in app.py SYSTEM_REFERENCE.md templates static \
          sc_pro.db sc_measurements.db saas_licenses.db sc_event.db; do
    _rotate_keep "/opt/backups/$_t.*" 3
done
_rotate_keep "/opt/backups/stresschecker-full-*.tar.gz" 5   # dagelijkse fulls (andere tool, grootste posten)
echo "Backup-rotatie: 3 nieuwste per type behouden (fulls: 5)"
