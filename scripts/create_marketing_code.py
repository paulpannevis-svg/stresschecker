#!/usr/bin/env python3
"""
Marketing-code generator voor StressChecker.

Maakt een unbound activatable license aan in saas_licenses.db.
De code is direct deelbaar met een prospect; deze kiest zelf zijn
e-mailadres bij activering via /licentie.

Voorbeeld:
    python3 create_marketing_code.py --plan sc-pro-m \
        --notes "Heropeningscampagne Manuela Muhlberger 2026-05-20" \
        --valid-days 90

Zie SYSTEM_REFERENCE.md sectie 12 voor het volledige unbound-pattern.
"""
import argparse
import datetime
import secrets
import sqlite3
import string
import sys

DB_PATH = '/opt/ic-license-server/data/saas_licenses.db'
KEY_CHARS = string.ascii_uppercase + string.digits
MAX_GEN_TRIES = 100


def gen_consumer_key():
    parts = [''.join(secrets.choice(KEY_CHARS) for _ in range(4)) for _ in range(3)]
    return 'SC-' + '-'.join(parts)


def gen_pro_key():
    return 'SC-PRO-' + secrets.token_hex(4).upper()


def main():
    ap = argparse.ArgumentParser(
        description='Genereer een marketing/unbound license-code.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument('--plan', required=True,
                    help="plan_id uit plans-tabel, bv 'sc-pro-m' / 'sc' / 'sc-month'")
    ap.add_argument('--notes', required=True,
                    help='Campagne-aanduiding (verschijnt in licenses.notes)')
    ap.add_argument('--valid-days', type=int, default=90,
                    help='Hoeveel dagen mag code geactiveerd worden (default 90)')
    args = ap.parse_args()

    if args.valid_days < 1 or args.valid_days > 3650:
        print(f"FATAL: --valid-days moet 1..3650 zijn (kreeg {args.valid_days})",
              file=sys.stderr)
        sys.exit(2)

    cn = sqlite3.connect(DB_PATH)
    cn.row_factory = sqlite3.Row

    plan = cn.execute(
        "SELECT plan_id, name, audience, max_profiles, is_active "
        "FROM plans WHERE plan_id=?", (args.plan,)
    ).fetchone()
    if not plan:
        print(f"FATAL: plan_id '{args.plan}' bestaat niet in plans-tabel",
              file=sys.stderr)
        cn.close()
        sys.exit(2)
    if not plan['is_active']:
        print(f"WAARSCHUWING: plan_id '{args.plan}' is is_active=0", file=sys.stderr)

    lic_type = 'pro' if plan['audience'] == 'pro' else 'consumer'
    gen = gen_pro_key if lic_type == 'pro' else gen_consumer_key

    code = None
    for _ in range(MAX_GEN_TRIES):
        candidate = gen()
        if not cn.execute(
            "SELECT 1 FROM licenses WHERE license_key=?", (candidate,)
        ).fetchone():
            code = candidate
            break
    if code is None:
        print(f"FATAL: kon na {MAX_GEN_TRIES} pogingen geen unieke code genereren",
              file=sys.stderr)
        cn.close()
        sys.exit(3)

    cn.execute("""
        INSERT INTO licenses
            (license_key, product, type, status, origin, max_profiles,
             created_at, code_expires_at,
             expires_at, activated_at, email,
             product_name, notes)
        VALUES (?, 'sc', ?, 'available', 'marketing', ?,
                datetime('now'), datetime('now', ?),
                NULL, NULL, NULL,
                ?, ?)
    """, (code, lic_type, plan['max_profiles'],
          f'+{args.valid_days} days', plan['name'], args.notes))
    cn.commit()

    inserted = cn.execute(
        "SELECT id, license_key, type, max_profiles, created_at, "
        "code_expires_at, product_name, notes "
        "FROM licenses WHERE license_key=?", (code,)
    ).fetchone()
    cn.close()

    print('=' * 64)
    print(f"Code:             {inserted['license_key']}")
    print(f"Plan:             {inserted['product_name']}")
    print(f"Type:             {inserted['type']} (max_profiles={inserted['max_profiles']})")
    print(f"Aangemaakt:       {inserted['created_at']} UTC")
    print(f"Code activeerbaar tot: {inserted['code_expires_at']} UTC  ({args.valid_days} dagen)")
    print(f"Notes:            {inserted['notes']}")
    print(f"Activatie:        https://stresschecker.lifestylemonitors.com/licentie")
    print('=' * 64)
    print(f"DB-id:            {inserted['id']}")


if __name__ == '__main__':
    main()
