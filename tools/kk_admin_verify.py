#!/usr/bin/env python3
"""T1-T7 verificatie KK-admin/operator-flow (Sessie B.6).
Gebruikt Flask test client; geen externe HTTP, dus geen race-condities.
Resultaat per test: PASS / FAIL met details.
"""
import sys, sqlite3, time, secrets, hashlib
sys.path.insert(0, '/opt/stresschecker')

from app import app, hash_password

SAAS_DB = '/opt/ic-license-server/data/saas_licenses.db'
ADMIN_EMAIL = 'paulpannevis+kktest@gmail.com'
OPERATOR_EMAIL = 'paulpannevis+kkoperator@gmail.com'
OPERATOR_PW = None  # gezet door reset_operator_password_for_test() bij testsetup
PRO_EMAIL = 'paulpannevis+evaltest@gmail.com'  # eval-Pro fixture uit TEST_ACCOUNTS.md
LICENSE = 'SC-KK-44F6-14A3'

results = []
def report(test_id, ok, msg):
    status = 'PASS' if ok else 'FAIL'
    line = f"[{status}] {test_id}: {msg}"
    print(line)
    results.append((test_id, ok, msg))
    return ok


def get_user(email):
    cn = sqlite3.connect(SAAS_DB); cn.row_factory = sqlite3.Row
    r = cn.execute("SELECT id, email, role FROM users WHERE email=?", (email,)).fetchone()
    cn.close()
    return r and dict(r)


def reset_admin_password_for_test():
    """Zet wachtwoord op een testbekend wachtwoord, leeg display_name + zet birth_year/gender
    zodat verify_2fa de profile_setup-redirect skipt. Restore-blok aan einde van testfile."""
    pw = secrets.token_urlsafe(12)
    cn = sqlite3.connect(SAAS_DB)
    cn.execute("UPDATE users SET password_hash=?, display_name=NULL, birth_year=1965, gender='male' WHERE email=?",
               (hash_password(pw), ADMIN_EMAIL))
    cn.commit(); cn.close()
    return pw


def reset_operator_password_for_test():
    """Zet operator-wachtwoord op een testbekende waarde. Bootstrap-wachtwoord
    wordt niet vertrouwd over runs (eerdere run liet hash inconsistent achter)."""
    global OPERATOR_PW
    OPERATOR_PW = secrets.token_urlsafe(12)
    cn = sqlite3.connect(SAAS_DB)
    cn.execute("UPDATE users SET password_hash=? WHERE email=?", (hash_password(OPERATOR_PW), OPERATOR_EMAIL))
    cn.commit(); cn.close()


def reset_pro_password_for_test():
    pw = secrets.token_urlsafe(12)
    cn = sqlite3.connect(SAAS_DB)
    cn.execute("UPDATE users SET password_hash=?, display_name=NULL, birth_year=1980, gender='male' WHERE email=?",
               (hash_password(pw), PRO_EMAIL))
    cn.commit(); cn.close()
    return pw


# ============================================================================
# T1 — admin login + 2FA → /pro/admin
# ============================================================================
def t1_admin_login():
    pw = reset_admin_password_for_test()
    client = app.test_client()
    # Stap 1: POST /login met admin-credentials
    r = client.post('/login', data={'email': ADMIN_EMAIL, 'password': pw, 'lang': 'de', 'type': 'pro'}, follow_redirects=False)
    if r.status_code != 302 or '/verify' not in r.headers.get('Location', ''):
        return report('T1', False, f"POST /login redirect={r.status_code} loc={r.headers.get('Location')}")
    # Stap 2 — Fix B verificatie: 2fa_audience='krankenkasse' moet door sc_login zijn gezet
    with client.session_transaction() as sess:
        code = sess.get('2fa_code')
        pre_audience = sess.get('2fa_audience')
        if pre_audience != 'krankenkasse':
            return report('T1', False, f"FIX-B-FAIL: 2fa_audience={pre_audience!r} (expected 'krankenkasse')")
    r = client.post('/verify', data={'code': code, 'lang': 'de'}, follow_redirects=False)
    if r.status_code != 302:
        return report('T1', False, f"POST /verify status={r.status_code}")
    loc = r.headers.get('Location', '')
    if '/pro/admin' not in loc:
        return report('T1', False, f"verify redirect naar {loc} (expected /pro/admin)")
    # Stap 3: na verify expliciet checken sessie.audience == 'krankenkasse'
    with client.session_transaction() as sess:
        post_audience = sess.get('audience')
        post_role = sess.get('role')
        if post_audience != 'krankenkasse':
            return report('T1', False, f"na 2FA: session.audience={post_audience!r} (expected 'krankenkasse')")
        if post_role != 'admin':
            return report('T1', False, f"na 2FA: session.role={post_role!r} (expected 'admin')")
    # Stap 4: GET /pro/admin → 200 + aggregaties zichtbaar
    r = client.get('/pro/admin')
    if r.status_code != 200:
        return report('T1', False, f"GET /pro/admin status={r.status_code}")
    body = r.data.decode('utf-8', 'replace')
    for needed in ('Admin-Übersicht', 'Hamburg', 'Hannover', 'München'):
        if needed not in body:
            return report('T1', False, f"missing in dashboard: {needed!r}")
    return report('T1', True, f"FIX B ✓ session.audience=krankenkasse, role=admin, /pro/admin 200 met Hamburg/Hannover/München zichtbaar")


# ============================================================================
# T2 — operator login zonder 2FA → /pro/locatie
# ============================================================================
def t2_operator_login():
    reset_operator_password_for_test()
    client = app.test_client()
    r = client.post('/login', data={'email': OPERATOR_EMAIL, 'password': OPERATOR_PW, 'lang': 'de', 'type': 'pro'}, follow_redirects=False)
    if r.status_code != 302:
        return report('T2', False, f"POST /login status={r.status_code} body={r.data[:200]}")
    loc = r.headers.get('Location', '')
    if '/pro/locatie' not in loc:
        return report('T2', False, f"redirect naar {loc} (expected /pro/locatie, geen /verify)")
    if '/verify' in loc:
        return report('T2', False, f"operator wordt naar 2FA gestuurd: {loc}")
    # Sessie-keys check
    with client.session_transaction() as sess:
        ok = (sess.get('role') == 'operator'
              and sess.get('audience') == 'krankenkasse'
              and sess.get('_session_window') == 'operator_24h'
              and sess.get('license_valid') is True)
        if not ok:
            return report('T2', False, f"sessie-keys: role={sess.get('role')} audience={sess.get('audience')} window={sess.get('_session_window')}")
    # Volg redirect
    r = client.get('/pro/locatie')
    if r.status_code != 200:
        return report('T2', False, f"GET /pro/locatie status={r.status_code}")
    return report('T2', True, "operator skipt 2FA, role=operator, window=24u, /pro/locatie 200")


# ============================================================================
# T3 — non-KK Pro login regressie
# ============================================================================
def t3_pro_regression():
    pw = reset_pro_password_for_test()
    client = app.test_client()
    r = client.post('/login', data={'email': PRO_EMAIL, 'password': pw, 'lang': 'nl', 'type': 'pro'}, follow_redirects=False)
    if r.status_code != 302 or '/verify' not in r.headers.get('Location', ''):
        return report('T3', False, f"POST /login → {r.status_code} {r.headers.get('Location')}")
    with client.session_transaction() as sess:
        code = sess.get('2fa_code')
        # Fix B regressie-check: non-KK Pro mag GEEN krankenkasse-audience krijgen
        if sess.get('2fa_audience') == 'krankenkasse':
            return report('T3', False, f"FIX-B-REGRESSIE: non-KK Pro kreeg 2fa_audience=krankenkasse")
    r = client.post('/verify', data={'code': code, 'lang': 'nl'}, follow_redirects=False)
    loc = r.headers.get('Location', '')
    if '/pro/admin' in loc:
        return report('T3', False, f"non-KK Pro wordt naar /pro/admin gestuurd: {loc}")
    if '/pro' not in loc:
        return report('T3', False, f"non-KK Pro redirect onverwacht: {loc}")
    with client.session_transaction() as sess:
        if sess.get('audience') == 'krankenkasse':
            return report('T3', False, "non-KK Pro krijgt audience=krankenkasse")
        if sess.get('role') == 'admin':
            return report('T3', False, "non-KK Pro krijgt role=admin")
    return report('T3', True, f"non-KK Pro → {loc}, geen KK-audience, geen admin-role")


# ============================================================================
# T4 — admin maakt operator aan, nieuwe operator kan inloggen
# ============================================================================
def t4_operator_add():
    # Genereer unieke test-operator-email
    tag = f"t4test{int(time.time())}"
    new_op_email = f"paulpannevis+{tag}@gmail.com"
    # Maak admin-sessie
    pw = reset_admin_password_for_test()
    client = app.test_client()
    client.post('/login', data={'email': ADMIN_EMAIL, 'password': pw, 'lang': 'de', 'type': 'pro'})
    with client.session_transaction() as sess:
        code = sess.get('2fa_code')
    client.post('/verify', data={'code': code, 'lang': 'de'})
    # POST /pro/operatoren/toevoegen
    r = client.post('/pro/operatoren/toevoegen', data={'email': new_op_email, 'display_name': 'T4 Test Op'}, follow_redirects=False)
    if r.status_code != 302:
        return report('T4', False, f"toevoegen status={r.status_code}")
    # Haal credentials uit session-flash via GET /pro/operatoren
    r = client.get('/pro/operatoren')
    body = r.data.decode('utf-8', 'replace')
    # Password staat in <code>...</code> in alert-success
    import re as _re
    pws = _re.findall(r'<code>([A-Za-z0-9_\-]{14,})</code>', body)
    if not pws:
        # Cleanup en faal
        cn = sqlite3.connect(SAAS_DB)
        cn.execute("DELETE FROM user_licenses WHERE user_id IN (SELECT id FROM users WHERE email=?)", (new_op_email,))
        cn.execute("DELETE FROM users WHERE email=?", (new_op_email,))
        cn.commit(); cn.close()
        return report('T4', False, "geen password gevonden in dashboard-flash")
    new_pw = pws[-1]  # laatste = password (eerste = email)
    # Test login als deze operator
    op_client = app.test_client()
    r = op_client.post('/login', data={'email': new_op_email, 'password': new_pw, 'lang': 'de', 'type': 'pro'}, follow_redirects=False)
    ok = (r.status_code == 302 and '/pro/locatie' in r.headers.get('Location', '') and '/verify' not in r.headers.get('Location', ''))
    # Cleanup
    cn = sqlite3.connect(SAAS_DB)
    cn.execute("DELETE FROM user_licenses WHERE user_id IN (SELECT id FROM users WHERE email=?)", (new_op_email,))
    cn.execute("DELETE FROM users WHERE email=?", (new_op_email,))
    cn.execute("DELETE FROM activation_log WHERE action='kk_operator_create' AND details LIKE ?", (f"%{new_op_email}%",))
    cn.commit(); cn.close()
    if not ok:
        return report('T4', False, f"nieuwe operator login → {r.status_code} {r.headers.get('Location')}")
    return report('T4', True, f"operator {new_op_email} aangemaakt + login zonder 2FA werkt")


# ============================================================================
# T5 — operator-sessie >30 min idle blijft actief (24u window)
# ============================================================================
def t5_operator_24h_window():
    if OPERATOR_PW is None:
        reset_operator_password_for_test()
    client = app.test_client()
    client.post('/login', data={'email': OPERATOR_EMAIL, 'password': OPERATOR_PW, 'lang': 'de', 'type': 'pro'})
    # Forceer _last_activity 35 minuten geleden
    with client.session_transaction() as sess:
        sess['_last_activity'] = time.time() - (35 * 60)
    r = client.get('/pro/locatie', follow_redirects=False)
    if r.status_code != 200:
        return report('T5', False, f"operator na 35 min idle: status={r.status_code} loc={r.headers.get('Location')}")
    # Forceer 23 uur idle (nog binnen 24u-window)
    with client.session_transaction() as sess:
        sess['_last_activity'] = time.time() - (23 * 3600)
    r = client.get('/pro/locatie', follow_redirects=False)
    if r.status_code != 200:
        return report('T5', False, f"operator na 23u: status={r.status_code} loc={r.headers.get('Location')}")
    return report('T5', True, "operator sessie 35min + 23u idle nog actief")


# ============================================================================
# T6 — admin-sessie >30 min idle vervalt (regressie B.4)
# ============================================================================
def t6_admin_30min_timeout():
    pw = reset_admin_password_for_test()
    client = app.test_client()
    client.post('/login', data={'email': ADMIN_EMAIL, 'password': pw, 'lang': 'de', 'type': 'pro'})
    with client.session_transaction() as sess:
        code = sess.get('2fa_code')
    client.post('/verify', data={'code': code, 'lang': 'de'})
    # Forceer 31 min idle
    with client.session_transaction() as sess:
        sess['_last_activity'] = time.time() - (31 * 60)
        window_marker = sess.get('_session_window')
    r = client.get('/pro/admin', follow_redirects=False)
    if r.status_code != 302:
        return report('T6', False, f"admin na 31min idle: status={r.status_code} (expected 302 redirect)")
    if 'timeout=1' not in (r.headers.get('Location') or ''):
        return report('T6', False, f"admin redirect zonder timeout-marker: {r.headers.get('Location')} (window-marker was {window_marker})")
    return report('T6', True, f"admin >30min idle → redirect /login?timeout=1 (window={window_marker!r})")


# ============================================================================
# T7 — KK-activatie auto-create admin + operator
# ============================================================================
def t7_kk_activation():
    test_license = f"SC-KK-T7TST-{secrets.token_hex(2).upper()}"
    # Unieke local-part zodat _derive_operator_email een nieuw operator-adres produceert
    test_admin_email = f"t7admin{int(time.time())}@example.invalid"
    # Genereer een test-license
    cn = sqlite3.connect(SAAS_DB)
    cn.execute(
        "INSERT INTO licenses (license_key, product, type, status, origin, max_profiles, created_at) "
        "VALUES (?, 'sc-krankenkasse-standard', 'pro', 'available', 'test', -1, datetime('now'))",
        (test_license,)
    )
    cn.commit(); cn.close()
    # Maak admin-user vooraf met password (verify_2fa zoekt user-record)
    pw = secrets.token_urlsafe(12)
    cn = sqlite3.connect(SAAS_DB)
    cn.execute(
        "INSERT INTO users (email, password_hash, display_name, language, created_at, birth_year, gender) "
        "VALUES (?, ?, 'T7 Admin', 'de', datetime('now'), 1970, 'male')",
        (test_admin_email, hash_password(pw))
    )
    cn.commit(); cn.close()
    # Inloggen + verify_2fa met license_code in sessie (zoals /activeer-pad)
    client = app.test_client()
    client.post('/login', data={'email': test_admin_email, 'password': pw, 'lang': 'de', 'type': 'pro'})
    with client.session_transaction() as sess:
        code = sess.get('2fa_code')
        sess['2fa_license_code'] = test_license  # simuleert /activeer-pad
        sess['2fa_audience'] = 'krankenkasse'
        sess['2fa_license_type'] = 'pro'
    client.post('/verify', data={'code': code, 'lang': 'de'})

    cn = sqlite3.connect(SAAS_DB); cn.row_factory = sqlite3.Row
    admin_row = cn.execute("SELECT role FROM users WHERE email=?", (test_admin_email,)).fetchone()
    op_row = cn.execute(
        "SELECT u.id, u.role FROM users u JOIN user_licenses ul ON ul.user_id=u.id "
        "WHERE ul.license_key=? AND u.role='operator'", (test_license,)
    ).fetchone()
    # Cleanup
    if op_row:
        cn.execute("DELETE FROM user_licenses WHERE user_id=?", (op_row['id'],))
        cn.execute("DELETE FROM users WHERE id=?", (op_row['id'],))
    cn.execute("DELETE FROM users WHERE email=?", (test_admin_email,))
    cn.execute("DELETE FROM licenses WHERE license_key=?", (test_license,))
    cn.commit(); cn.close()

    if not admin_row or admin_row['role'] != 'admin':
        return report('T7', False, f"admin-user kreeg role={admin_row and admin_row['role']} (expected admin)")
    if not op_row:
        return report('T7', False, "geen operator-user aangemaakt voor verse KK-licentie")
    return report('T7', True, f"verse KK-activatie {test_license}: admin role gezet + operator auto-created")


# ============================================================================
# T8 — Pro mét display_name + birth_year laadt profiel, GEEN profile_setup
#       Regressietest voor fix 2026-05-30: verify_2fa laadde birth_year/gender
#       alleen in het `if nm == em`-blok, waardoor users mét display_name elke
#       login opnieuw naar /profiel werden gestuurd.
# ============================================================================
def reset_pro_with_display_name_for_test():
    """Zet PRO_EMAIL op display_name='Paul' + birth_year=1949 (het pad dat vóór
    de fix faalde). Restore naar T3-neutrale staat aan einde van de test."""
    pw = secrets.token_urlsafe(12)
    cn = sqlite3.connect(SAAS_DB)
    cn.execute("UPDATE users SET password_hash=?, display_name='Paul', birth_year=1949, gender='male' WHERE email=?",
               (hash_password(pw), PRO_EMAIL))
    cn.commit(); cn.close()
    return pw


def t8_pro_with_display_name():
    pw = reset_pro_with_display_name_for_test()
    try:
        client = app.test_client()
        r = client.post('/login', data={'email': PRO_EMAIL, 'password': pw, 'lang': 'nl', 'type': 'pro'}, follow_redirects=False)
        if r.status_code != 302 or '/verify' not in r.headers.get('Location', ''):
            return report('T8', False, f"POST /login → {r.status_code} {r.headers.get('Location')}")
        with client.session_transaction() as sess:
            code = sess.get('2fa_code')
        r = client.post('/verify', data={'code': code, 'lang': 'nl'}, follow_redirects=False)
        loc = r.headers.get('Location', '')
        # Kernassertie: NIET naar /profiel (let op: '/profiel' bevat '/pro' als substring)
        if '/profiel' in loc:
            return report('T8', False, f"BUG-REGRESSIE: Pro mét display_name → profile_setup ({loc})")
        if not loc.split('?')[0].rstrip('/').endswith('/pro'):
            return report('T8', False, f"verwacht redirect /pro, kreeg {loc}")
        # Sessie moet de DB-waarde bevatten, niet de 1970-default
        with client.session_transaction() as sess:
            by = sess.get('profile_birth_year')
            if by != 1949:
                return report('T8', False, f"profile_birth_year={by!r} in sessie (expected 1949)")
        return report('T8', True, f"Pro display_name=Paul birth_year=1949 → {loc}, géén profile_setup")
    finally:
        # Restore naar T3-neutrale staat (display_name NULL, birth_year 1980)
        cn = sqlite3.connect(SAAS_DB)
        cn.execute("UPDATE users SET display_name=NULL, birth_year=1980 WHERE email=?", (PRO_EMAIL,))
        cn.commit(); cn.close()


# ============================================================================
# Run all
# ============================================================================
print("=== T1-T8 verificatie KK-admin/operator flow ===\n")
t1_admin_login()
t2_operator_login()
t3_pro_regression()
t4_operator_add()
t5_operator_24h_window()
t6_admin_30min_timeout()
t7_kk_activation()
t8_pro_with_display_name()

passed = sum(1 for _, ok, _ in results if ok)
total = len(results)
print(f"\n=== {passed}/{total} tests geslaagd ===")
sys.exit(0 if passed == total else 1)
