#!/usr/bin/env python3
"""
scrub_pii.py <datadir> [--verify-only]

Anonimiseert PII in de STAGING-kopieen van de drie SQLite-DB's
(sc_measurements.db, sc_pro.db, saas_licenses.db). Idempotent + deterministisch.

Eisen (afgesproken 2026-06-06):
  1. WHITELIST: Paul's twee eigen accounts + de RI-fix-fixtures (id 25/26) blijven
     ongemoeid. Al het overige: e-mail/naam deterministisch anonimiseren
     (userN@test.invalid), licentiesleutels + Stripe/PayPal-id's -> duidelijk nep.
  2. VERIFICATIE: na afloop nul echte externe e-mailadressen (alles wat niet op de
     whitelist of op *.invalid matcht). De telling wordt gerapporteerd; bij >0
     eindigt het script met exit-code 1 (zodat refresh_data.sh de service niet start).
  3. HERHAALBAAR: wordt aangeroepen vanuit refresh_data.sh, zodat elke verse kopie
     automatisch gescrubd wordt. Een verse kopie zonder scrub mag niet serveren.

Bron raakt nooit aan: dit script opent UITSLUITEND bestanden onder <datadir>.
"""
import sys, os, re, sqlite3, hashlib

WHITELIST = {
    'paulpannevis@gmail.com',
    'paulpannevis@lifestylemonitors.com',
    'test-rifix@lifestylemonitors.com',
    'test-rifix-divers@lifestylemonitors.com',
}

EMAIL_RE = re.compile(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}')

DBS = ('sc_measurements.db', 'sc_pro.db', 'saas_licenses.db')

# Kolommen die we als PERSOONSNAAM anonimiseren (per rij). (tabel, kolom, naam-prefix).
# Wordt overgeslagen wanneer de rij een gewhiteliste e-mail heeft (zie email_col).
NAME_COLS = {
    'saas_licenses.db': [
        ('users', 'display_name', 'Gebruiker', 'email'),
        ('users', 'surname', 'Achternaam', 'email'),
        ('clients', 'display_name', 'Client', None),
        ('krankenkasse_offices', 'office_name', 'Office', None),
        ('profiles', 'name', 'Profiel', None),
    ],
    'sc_pro.db': [
        ('clients', 'name', 'Naam', 'email'),
        ('clients', 'surname', 'Achternaam', 'email'),
    ],
    'sc_measurements.db': [
        ('user_profiles', 'naam', 'Gebruiker', 'email'),
    ],
}

# Telefoonkolommen -> nep nummer.
PHONE_COLS = {'sc_pro.db': [('clients', 'phone', 'email')]}

# password_hash -> onbruikbaar (behalve whitelist, zodat Paul kan inloggen).
PW_COLS = {'saas_licenses.db': [('users', 'password_hash', 'email')]}

# IP/user-agent -> generiek.
IP_COLS = {'saas_licenses.db': [('activation_log', 'ip_address', '0.0.0.0'),
                                ('activation_log', 'user_agent', 'scrubbed-staging')]}

# JSON-payloads die ruwe provider-data (namen/adressen/ids) kunnen bevatten -> leeg.
BLANK_JSON = {'saas_licenses.db': [('billing_events', 'payload_json'),
                                   ('backups', 'snapshot_json'),
                                   ('reflections', 'payload_json')]}

# Kolommen met licentiesleutels/codes -> nep (whitelist-gebonden keys blijven).
KEY_COLS = {
    'saas_licenses.db': [
        ('licenses', 'license_key', 'email'),
        ('legacy_keys', 'license_key', None),
        ('user_licenses', 'license_key', None),
        ('activation_log', 'license_key', None),
        ('legacy_codes', 'code', None),
        ('redeem_codes', 'code', None),
        ('krankenkasse_offices', 'license_code', None),
        ('report_jobs', 'license_code', None),
        ('consent_log', 'license_code', None),
        ('pairing_codes', 'code', None),
    ],
}

# Stripe/PayPal-id's -> nep (product-niveau plans.* blijven; die zijn geen PII).
STRIPE_COLS = {
    'saas_licenses.db': [
        ('users', 'stripe_customer_id', 'cus', 'email'),
        ('users', 'stripe_subscription_id', 'sub', 'email'),
        ('licenses', 'stripe_subscription_id', 'sub', 'email'),
        ('licenses', 'paypal_subscription_id', 'paypalsub', 'email'),
        ('licenses', 'order_id', 'order', 'email'),
        ('subscriptions', 'stripe_customer_id', 'cus', None),
        ('subscriptions', 'subscription_id', 'sub', None),
        ('subscriptions', 'provider_ref', 'ref', None),
    ],
}


def wl(email):
    return bool(email) and email.strip().lower() in WHITELIST


def table_exists(cur, t):
    return cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone() is not None


def cols_of(cur, t):
    return [r[1] for r in cur.execute(f'PRAGMA table_info("{t}")').fetchall()]


def all_text_values(cur):
    """Yield (table, col, rowid, value) voor elke niet-lege kolomwaarde in de DB."""
    tables = [r[0] for r in cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()]
    for t in tables:
        cols = cols_of(cur, t)
        has_rowid = True
        try:
            cur.execute(f'SELECT rowid FROM "{t}" LIMIT 1')
        except sqlite3.OperationalError:
            has_rowid = False
        sel = ('rowid, ' if has_rowid else '') + ', '.join(f'"{c}"' for c in cols)
        for row in cur.execute(f'SELECT {sel} FROM "{t}"').fetchall():
            rid = row[0] if has_rowid else None
            vals = row[1:] if has_rowid else row
            for c, v in zip(cols, vals):
                if isinstance(v, str) and v:
                    yield t, c, rid, v


def build_global_email_map(paths):
    """Verzamel alle echte (niet-whitelist) e-mails over alle DB's -> userN@test.invalid."""
    found = set()
    for p in paths:
        if not os.path.exists(p):
            continue
        con = sqlite3.connect(p); cur = con.cursor()
        for _t, _c, _rid, v in all_text_values(cur):
            for m in EMAIL_RE.findall(v):
                el = m.lower()
                if not wl(el) and not el.endswith('.invalid'):
                    found.add(el)
        con.close()
    mapping = {}
    for i, e in enumerate(sorted(found), 1):
        mapping[e] = f'user{i}@test.invalid'
    return mapping


def scrub_db(path, email_map):
    if not os.path.exists(path):
        return
    name = os.path.basename(path)
    con = sqlite3.connect(path); cur = con.cursor()

    def email_of(t, col, rid):
        if not col or rid is None:
            return None
        try:
            r = cur.execute(f'SELECT "{col}" FROM "{t}" WHERE rowid=?', (rid,)).fetchone()
            return r[0] if r else None
        except sqlite3.OperationalError:
            return None

    # 1. Namen
    for t, col, prefix, ecol in NAME_COLS.get(name, []):
        if not table_exists(cur, t) or col not in cols_of(cur, t):
            continue
        for (rid,) in cur.execute(f'SELECT rowid FROM "{t}"').fetchall():
            if wl(email_of(t, ecol, rid)):
                continue
            cur.execute(f'UPDATE "{t}" SET "{col}"=? WHERE rowid=? AND "{col}" IS NOT NULL AND "{col}"<>""',
                        (f'{prefix}{rid}', rid))

    # 2. Telefoon
    for t, col, ecol in PHONE_COLS.get(name, []):
        if not table_exists(cur, t) or col not in cols_of(cur, t):
            continue
        for (rid,) in cur.execute(f'SELECT rowid FROM "{t}"').fetchall():
            if wl(email_of(t, ecol, rid)):
                continue
            cur.execute(f'UPDATE "{t}" SET "{col}"=? WHERE rowid=? AND "{col}" IS NOT NULL AND "{col}"<>""',
                        (f'+310000{rid:05d}', rid))

    # 3. Wachtwoord-hash
    for t, col, ecol in PW_COLS.get(name, []):
        if not table_exists(cur, t) or col not in cols_of(cur, t):
            continue
        for (rid,) in cur.execute(f'SELECT rowid FROM "{t}"').fetchall():
            if wl(email_of(t, ecol, rid)):
                continue
            cur.execute(f'UPDATE "{t}" SET "{col}"=? WHERE rowid=?', ('SCRUBBED-NO-LOGIN', rid))

    # 4. IP / user-agent
    for t, col, val in IP_COLS.get(name, []):
        if table_exists(cur, t) and col in cols_of(cur, t):
            cur.execute(f'UPDATE "{t}" SET "{col}"=? WHERE "{col}" IS NOT NULL AND "{col}"<>""', (val,))

    # 5. JSON-payloads blanken
    for t, col in BLANK_JSON.get(name, []):
        if table_exists(cur, t) and col in cols_of(cur, t):
            cur.execute(f'UPDATE "{t}" SET "{col}"=\'{{}}\' WHERE "{col}" IS NOT NULL AND "{col}"<>""')

    # 6. Licentiesleutels -> nep (per-DB map; whitelist-gebonden keys blijven)
    key_map = {}
    for t, col, ecol in KEY_COLS.get(name, []):
        if not table_exists(cur, t) or col not in cols_of(cur, t):
            continue
        for rid, val in cur.execute(f'SELECT rowid, "{col}" FROM "{t}"').fetchall():
            if not val or str(val).startswith('SC-STAGING'):
                continue
            if wl(email_of(t, ecol, rid)):
                continue  # Paul's eigen sleutels behouden
            if val not in key_map:
                h = hashlib.sha256(val.encode()).hexdigest()[:8].upper()
                key_map[val] = f'SC-STAGING-{h}'

    # 7. Stripe/PayPal-id's -> nep
    stripe_map = {}
    for t, col, pfx, ecol in STRIPE_COLS.get(name, []):
        if not table_exists(cur, t) or col not in cols_of(cur, t):
            continue
        for rid, val in cur.execute(f'SELECT rowid, "{col}" FROM "{t}"').fetchall():
            if not val or 'STAGING' in str(val):
                continue
            if wl(email_of(t, ecol, rid)):
                continue
            if val not in stripe_map:
                h = hashlib.sha256(val.encode()).hexdigest()[:10]
                stripe_map[val] = f'{pfx}_STAGING_{h}'

    # 8. Globale sweep: e-mail-, key- en stripe-waarden overal (ook in vrije tekst/JSON)
    replace_map = dict(email_map)
    replace_map.update(key_map)
    replace_map.update(stripe_map)
    if replace_map:
        # itereer opnieuw over alle waarden en vervang letterlijk (case-insensitive voor e-mail)
        for t, c, rid, v in list(all_text_values(cur)):
            nv = v
            for real, fake in replace_map.items():
                if real in nv:
                    nv = nv.replace(real, fake)
                if '@' in real:  # e-mail ook case-insensitive
                    nv = re.sub(re.escape(real), fake, nv, flags=re.IGNORECASE)
            if nv != v and rid is not None:
                try:
                    cur.execute(f'UPDATE "{t}" SET "{c}"=? WHERE rowid=?', (nv, rid))
                except sqlite3.OperationalError:
                    pass

    con.commit(); con.close()


def verify(paths):
    """Tel echte externe e-mails (niet whitelist, niet *.invalid) over alle DB's."""
    leaks = []
    for p in paths:
        if not os.path.exists(p):
            continue
        con = sqlite3.connect(p); cur = con.cursor()
        for t, c, rid, v in all_text_values(cur):
            for m in EMAIL_RE.findall(v):
                el = m.lower()
                if el.endswith('.invalid') or wl(el):
                    continue
                leaks.append((os.path.basename(p), t, c, rid, m))
        con.close()
    return leaks


def main():
    if len(sys.argv) < 2:
        print('usage: scrub_pii.py <datadir> [--verify-only]', file=sys.stderr)
        sys.exit(2)
    datadir = sys.argv[1]
    verify_only = '--verify-only' in sys.argv[2:]
    paths = [os.path.join(datadir, d) for d in DBS]

    if not verify_only:
        email_map = build_global_email_map(paths)
        print(f'[scrub] {len(email_map)} echte e-mailadressen -> userN@test.invalid')
        for p in paths:
            scrub_db(p, email_map)
            if os.path.exists(p):
                print(f'[scrub] {os.path.basename(p)} verwerkt')

    leaks = verify(paths)
    print(f'[verify] echte externe e-mailadressen resterend: {len(leaks)}')
    if leaks:
        for row in leaks[:20]:
            print(f'  LEAK {row[0]}.{row[1]}.{row[2]} (rowid={row[3]}): {row[4]}')
        if len(leaks) > 20:
            print(f'  ... +{len(leaks)-20} meer')
        sys.exit(1)
    print('[verify] OK — geen echte externe e-mailadressen.')


if __name__ == '__main__':
    main()
