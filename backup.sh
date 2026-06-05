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
