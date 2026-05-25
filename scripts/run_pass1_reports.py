#!/usr/bin/env python3
"""
Genereert de 5 pass1-rapporten zonder via de UI/2FA-flow te gaan.

Output: PDFs in /opt/stresschecker/reports/SC-KK-44F6-14A3/pass1/ met
heldere bestandsnamen. Mailbezorging wordt overgeslagen.
"""
import json
import os
import sqlite3
import sys
import uuid

sys.path.insert(0, '/opt/stresschecker')

# Mail-functies neutraliseren — we willen geen test-mails versturen
import app as appmod
appmod.send_report_ready_email = lambda *a, **k: True
appmod.send_report_failed_email = lambda *a, **k: None

LICENSE = 'SC-KK-44F6-14A3'
PRO_KEY = '2f2930462d21870da10942410870c20e'
USER_EMAIL = 'paulpannevis+kktest@gmail.com'
OUT_DIR = '/opt/stresschecker/reports/SC-KK-44F6-14A3/pass1'
SAAS_DB = '/opt/ic-license-server/data/saas_licenses.db'


def find_smoke_anna_id():
    db = sqlite3.connect('/opt/stresschecker/data/sc_pro.db')
    row = db.execute(
        "SELECT id FROM clients WHERE pro_key=? AND name='SMOKE_Anna'",
        (PRO_KEY,)).fetchone()
    db.close()
    if not row:
        raise RuntimeError('SMOKE_Anna ontbreekt — draai eerst seed_kk_test.py')
    return row[0]


def run_one(label, lang, report_type, params):
    uuid_str = uuid.uuid4().hex
    # Job-rij vooraf
    db = sqlite3.connect(SAAS_DB)
    db.execute(
        "INSERT INTO report_jobs (uuid, license_code, user_email, report_type, status, params_json) "
        "VALUES (?, ?, ?, ?, 'pending', ?)",
        (uuid_str, LICENSE, USER_EMAIL, report_type, json.dumps(params)))
    db.commit()
    db.close()

    # Genereren in dezelfde thread (synchroon voor scripting)
    appmod._render_report_async(uuid_str, LICENSE, USER_EMAIL, lang, report_type, params, PRO_KEY)

    # Lees status uit
    db = sqlite3.connect(SAAS_DB)
    db.row_factory = sqlite3.Row
    row = db.execute("SELECT status, pdf_path, error_message FROM report_jobs WHERE uuid=?",
                     (uuid_str,)).fetchone()
    db.close()

    if row['status'] != 'ready':
        print(f'!! {label}: status={row["status"]} err={row["error_message"]}')
        return False
    src = os.path.join('/opt/stresschecker', row['pdf_path'])
    if not os.path.exists(src):
        print(f'!! {label}: PDF ontbreekt op {src}')
        return False
    dst = os.path.join(OUT_DIR, f'{label}.pdf')
    os.rename(src, dst)
    print(f'OK  {label:30} → {dst} ({os.path.getsize(dst)} bytes)')
    return True


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    anna_id = find_smoke_anna_id()

    runs = [
        ('kk_overall_nl',        'nl', 'kk_overall',    {'periode': 'alles'}),
        ('kk_overall_de',        'de', 'kk_overall',    {'periode': 'alles'}),
        ('kk_office_hamburg_de', 'de', 'kk_office',     {'periode': 'alles', 'office_label': 'Hamburg'}),
        ('pro_portfolio_de',     'de', 'pro_portfolio', {'periode': 'alles'}),
        ('pro_client_anna_de',   'de', 'pro_client',    {'periode': 'alles', 'client_id': str(anna_id)}),
    ]
    failed = 0
    for label, lang, rtype, params in runs:
        ok = run_one(label, lang, rtype, params)
        if not ok:
            failed += 1
    print(f'\nKlaar: {len(runs)-failed}/{len(runs)} geslaagd')
    sys.exit(0 if not failed else 1)


if __name__ == '__main__':
    main()
