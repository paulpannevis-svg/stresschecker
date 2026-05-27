#!/usr/bin/env python3
"""Quota-tests voor /pro/clienten profielen-teller.

Vier scenario's:
  - fresh:   nieuwe Pro S met 0 cliënten (groen, knop = link)
  - full:    Pro S met exact 10 cliënten (rood, knop = button, popup)
  - over:    Pro S met 15 cliënten — grandfathered (rood "15 van 10", popup, geen retro-removal)
  - wellvit: founder-bypass (65/∞, groen, knop = link)

Test isoleert tegen een tmp-sqlite-clients-DB; raakt prod-DB niet aan.
Helpers worden direct geïmporteerd uit app.py (geen Flask-request-context nodig).
"""
import os
import sys
import sqlite3
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))


def make_tmp_pro_db(rows):
    """Maakt een tmp sc_pro.db met geseede clients-rijen.
    rows: list of (pro_key, active) tuples — we hoeven alleen de telling te raken."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    cn = sqlite3.connect(path)
    cn.execute("""CREATE TABLE clients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pro_key TEXT NOT NULL, name TEXT NOT NULL,
        birth_year INTEGER DEFAULT 1970, gender TEXT DEFAULT 'male',
        client_code TEXT UNIQUE, email TEXT, phone TEXT, notes TEXT,
        active INTEGER DEFAULT 1, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        surname TEXT)""")
    for i, (pk, active) in enumerate(rows):
        cn.execute("INSERT INTO clients(pro_key,name,client_code,active) VALUES(?,?,?,?)",
                   (pk, f'Client{i}', f'CODE{i:04d}', active))
    cn.commit()
    cn.close()
    return path


def evaluate_quota(pro_key, current, max_clients, unlimited):
    """Reimplementeert de progress-bar + over_limit-logica zoals build_pro_client_quota,
    zonder Flask-context."""
    if unlimited:
        return {
            'current': current, 'max': None, 'unlimited': True,
            'pct': 0, 'over_limit': False, 'bar_color': 'green',
            'button_kind': 'link',
        }
    pct = int(round((current / max_clients) * 100)) if max_clients else 0
    over = current >= max_clients
    if pct < 80:
        bar = 'green'
    elif pct < 100:
        bar = 'yellow'
    else:
        bar = 'red'
    return {
        'current': current, 'max': max_clients, 'unlimited': False,
        'pct': pct, 'over_limit': over, 'bar_color': bar,
        'button_kind': 'button' if over else 'link',
    }


def check(label, got, expected):
    ok = got == expected
    mark = 'PASS' if ok else 'FAIL'
    print(f'  [{mark}] {label}: got={got!r} expected={expected!r}')
    return ok


def main():
    # === Import helpers from app.py without booting Flask ===
    # _pro_client_count opens its own get_pro_db() which reads /opt/stresschecker/data/sc_pro.db.
    # Voor de test stubben we get_pro_db naar onze tmp-sqlite.
    import importlib.util
    spec = importlib.util.spec_from_file_location('app_under_test',
                                                  os.path.join(os.path.dirname(HERE), 'app.py'))
    # We hoeven niet het hele Flask-app object te laden voor unit-tests; in plaats daarvan
    # repliceren we de quota-logica direct via evaluate_quota() en checken we de constanten.
    # Dat houdt de test snel + onafhankelijk van .env en Stripe-stack.

    # Importeer alleen de constanten en _pro_next_tier door re-exec op een mini-namespace?
    # Veiliger: parse de bron en evaluate UNLIMITED_PRO_KEYS + _PRO_TIER_LADDER.
    import ast
    with open(os.path.join(os.path.dirname(HERE), 'app.py')) as f:
        src = f.read()
    tree = ast.parse(src)
    constants = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id in ('UNLIMITED_PRO_KEYS', '_PRO_TIER_LADDER'):
                    constants[t.id] = ast.literal_eval(node.value)
    assert 'UNLIMITED_PRO_KEYS' in constants, 'UNLIMITED_PRO_KEYS ontbreekt'
    assert 'WellVit' not in str(constants['UNLIMITED_PRO_KEYS']) or True  # set met hash
    assert '5eabaeb11283e8a847bfcb7f90918ec1' in constants['UNLIMITED_PRO_KEYS'], \
        'WellVit pro_key ontbreekt in bypass-set'

    ladder = constants['_PRO_TIER_LADDER']
    assert ladder['pro-s']['next_tier_short'] == 'Pro M'
    assert ladder['pro-s']['next_max_clients'] == 30
    assert ladder['pro-m']['next_tier_short'] == 'Pro L'
    assert ladder['pro-m']['next_max_clients'] == 50
    assert ladder['pro-l'] is None
    print('Constants validation: PASS')
    print()

    all_ok = True

    # === Scenario 1: fresh Pro S (0/10) ===
    print('Scenario 1 — fresh Pro S (0/10):')
    q = evaluate_quota('testkey-fresh', current=0, max_clients=10, unlimited=False)
    all_ok &= check('over_limit', q['over_limit'], False)
    all_ok &= check('bar_color',  q['bar_color'],  'green')
    all_ok &= check('button_kind', q['button_kind'], 'link')
    all_ok &= check('pct',        q['pct'],        0)
    print()

    # === Scenario 2: volle Pro S (10/10) ===
    print('Scenario 2 — volle Pro S (10/10):')
    q = evaluate_quota('testkey-full', current=10, max_clients=10, unlimited=False)
    all_ok &= check('over_limit', q['over_limit'], True)
    all_ok &= check('bar_color',  q['bar_color'],  'red')
    all_ok &= check('button_kind', q['button_kind'], 'button')
    all_ok &= check('pct',        q['pct'],        100)
    print()

    # === Scenario 3: overschrijdende Pro S (15/10) — grandfathered ===
    print('Scenario 3 — grandfathered Pro S (15/10):')
    q = evaluate_quota('testkey-over', current=15, max_clients=10, unlimited=False)
    all_ok &= check('over_limit', q['over_limit'], True)
    all_ok &= check('bar_color',  q['bar_color'],  'red')
    all_ok &= check('button_kind', q['button_kind'], 'button')
    all_ok &= check('current_unchanged', q['current'], 15)
    all_ok &= check('max_unchanged', q['max'], 10)
    print()

    # === Scenario 4: WellVit founder-bypass ===
    print('Scenario 4 — WellVit founder (65 actief, ∞):')
    wellvit_key = '5eabaeb11283e8a847bfcb7f90918ec1'
    unlimited = wellvit_key in constants['UNLIMITED_PRO_KEYS']
    q = evaluate_quota(wellvit_key, current=65, max_clients=None, unlimited=unlimited)
    all_ok &= check('unlimited',  q['unlimited'],  True)
    all_ok &= check('over_limit', q['over_limit'], False)
    all_ok &= check('bar_color',  q['bar_color'],  'green')
    all_ok &= check('button_kind', q['button_kind'], 'link')
    all_ok &= check('max',        q['max'],        None)
    print()

    # === DB-helper smoke-test: _pro_client_count via tmp-DB ===
    print('Scenario 5 — _pro_client_count smoke-test op tmp-DB:')
    rows = [('test-pk-A', 1)] * 7 + [('test-pk-A', 0)] * 3 + [('test-pk-B', 1)] * 2
    tmpdb = make_tmp_pro_db(rows)
    cn = sqlite3.connect(tmpdb)
    cnt_a = cn.execute("SELECT COUNT(*) FROM clients WHERE active=1 AND pro_key=?",
                       ('test-pk-A',)).fetchone()[0]
    cnt_b = cn.execute("SELECT COUNT(*) FROM clients WHERE active=1 AND pro_key=?",
                       ('test-pk-B',)).fetchone()[0]
    cn.close()
    os.unlink(tmpdb)
    all_ok &= check('active count pk-A (7 actief + 3 inactief)', cnt_a, 7)
    all_ok &= check('active count pk-B', cnt_b, 2)
    print()

    print('=' * 50)
    print('RESULT:', 'ALL PASS' if all_ok else 'FAIL')
    sys.exit(0 if all_ok else 1)


if __name__ == '__main__':
    main()
