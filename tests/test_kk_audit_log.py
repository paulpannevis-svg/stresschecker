"""Tests voor KK-CRUD audit-logging (Sessie B.4).

Doel: bevestigen dat elke wijziging via /pro/locaties/* een rij
schrijft naar saas_licenses.db.activation_log met de juiste action,
details, IP en user-agent. Vereist voor KKH-Datenschutz-traceerbaarheid.

Zes tests:
    T1 — toevoegen logt action=kk_office_create + name+region
    T2 — bewerken logt action=kk_office_update + old/new
    T3 — deactiveren logt action=kk_office_deactivate
    T4 — import (confirm) logt action=kk_office_import + counts
    T5 — failed create (lege naam) schrijft GEEN log-rij
    T6 — log bevat IP en User-Agent

Elke test:
    setUp:   verse __TEST_AUDIT_KK__-license_code in cookie + (waar nodig)
             office-rijen in krankenkasse_offices
    actie:   HTTP POST naar de betreffende route
    assert:  diff in activation_log (vóór vs na) is correct
    tearDown: verwijder eigen rijen uit krankenkasse_offices + activation_log

Output: print "test_kk_audit_log: N passed, M failed (Ts)". Exit 0/1.
"""

import glob
import sqlite3
import sys
import time
import requests
from flask import Flask
from flask.sessions import SecureCookieSessionInterface

BASE_URL = "http://localhost:8080"
TIMEOUT = 15
SAAS_DB = "/opt/ic-license-server/data/saas_licenses.db"
TEST_LICENSE_CODE = "__TEST_AUDIT_KK__"
_SECRET_KEY = None


def _load_secret_key():
    global _SECRET_KEY
    if _SECRET_KEY is not None:
        return _SECRET_KEY
    for environ_path in glob.glob("/proc/[0-9]*/environ"):
        try:
            cmdline_path = environ_path.replace("environ", "cmdline")
            with open(cmdline_path, "rb") as fh:
                cmdline = fh.read().decode("utf-8", "ignore")
            if "app:app" not in cmdline or "gunicorn" not in cmdline:
                continue
            with open(environ_path, "rb") as fh:
                env = fh.read().decode("utf-8", "ignore")
            for entry in env.split("\x00"):
                if entry.startswith("SC_SECRET_KEY="):
                    _SECRET_KEY = entry.split("=", 1)[1]
                    return _SECRET_KEY
        except (PermissionError, FileNotFoundError):
            continue
    with open("/opt/stresschecker/.env") as fh:
        for line in fh:
            if line.startswith("SC_SECRET_KEY="):
                _SECRET_KEY = line.split("=", 1)[1].strip()
                break
    if not _SECRET_KEY:
        raise RuntimeError("SC_SECRET_KEY niet gevonden")
    return _SECRET_KEY


def mint_kk_cookie():
    a = Flask(__name__)
    a.secret_key = _load_secret_key()
    serializer = SecureCookieSessionInterface().get_signing_serializer(a)
    data = {
        "license_valid": True,
        "license_type": "pro",
        "audience": "krankenkasse",
        "license_code": TEST_LICENSE_CODE,
        "user_key": "__TEST_AUDIT_USER__",
        "lang": "nl",
        "profile_name": "Audit-test",
        "profile_birth_year": 1980,
        "profile_gender": "male",
        "sensor_pref": "demo",
        "kk_office": "InitOffice",
        "_last_activity": time.time(),
    }
    return serializer.dumps(data)


def cleanup_test_data():
    """Wis alle test-rijen uit beide tabellen — idempotent."""
    db = sqlite3.connect(SAAS_DB)
    db.execute("DELETE FROM krankenkasse_offices WHERE license_code=?", (TEST_LICENSE_CODE,))
    db.execute("DELETE FROM activation_log WHERE license_key=?", (TEST_LICENSE_CODE,))
    db.commit()
    db.close()


def seed_office(name="SetupOffice", region="TestRegion", active=1):
    """Voeg één office toe en geef id terug."""
    db = sqlite3.connect(SAAS_DB)
    cur = db.execute(
        "INSERT INTO krankenkasse_offices (license_code, office_name, region, active) "
        "VALUES (?, ?, ?, ?)",
        (TEST_LICENSE_CODE, name, region, active))
    oid = cur.lastrowid
    db.commit()
    db.close()
    return oid


def count_logs():
    db = sqlite3.connect(SAAS_DB)
    n = db.execute("SELECT COUNT(*) FROM activation_log WHERE license_key=?",
                   (TEST_LICENSE_CODE,)).fetchone()[0]
    db.close()
    return n


def last_log():
    db = sqlite3.connect(SAAS_DB)
    db.row_factory = sqlite3.Row
    row = db.execute(
        "SELECT action, ip_address, user_agent, details FROM activation_log "
        "WHERE license_key=? ORDER BY id DESC LIMIT 1",
        (TEST_LICENSE_CODE,)).fetchone()
    db.close()
    return dict(row) if row else None


def _post(path, data, cookie):
    return requests.post(f"{BASE_URL}{path}",
                         data=data,
                         cookies={"session": cookie},
                         allow_redirects=False,
                         timeout=TIMEOUT)


def test_create_logs_action():
    """T1: POST /pro/locaties/toevoegen logt kk_office_create + name+region."""
    cleanup_test_data()
    n0 = count_logs()
    cookie = mint_kk_cookie()
    r = _post("/pro/locaties/toevoegen",
              {"office_name": "Berlin-Mitte", "region": "Berlin"}, cookie)
    if r.status_code != 302:
        return False, f"verwacht 302 redirect, kreeg {r.status_code}"
    if count_logs() != n0 + 1:
        return False, f"verwacht +1 log-rij, kreeg +{count_logs() - n0}"
    log = last_log()
    if log["action"] != "kk_office_create":
        return False, f"action={log['action']!r}, verwacht kk_office_create"
    if "Berlin-Mitte" not in log["details"] or "Berlin" not in log["details"]:
        return False, f"details mist name/region: {log['details']!r}"
    return True, f"action=kk_office_create details={log['details']!r}"


def test_update_logs_old_and_new():
    """T2: POST /pro/locaties/<id>/bewerken logt kk_office_update met old+new."""
    cleanup_test_data()
    oid = seed_office(name="OudeNaam", region="OudeRegio")
    n0 = count_logs()
    cookie = mint_kk_cookie()
    r = _post(f"/pro/locaties/{oid}/bewerken",
              {"office_name": "NieuweNaam", "region": "NieuweRegio"}, cookie)
    if r.status_code != 302:
        return False, f"verwacht 302, kreeg {r.status_code}"
    if count_logs() != n0 + 1:
        return False, f"verwacht +1 log-rij, kreeg +{count_logs() - n0}"
    log = last_log()
    if log["action"] != "kk_office_update":
        return False, f"action={log['action']!r}"
    d = log["details"]
    for needle in ("OudeNaam", "NieuweNaam", "OudeRegio", "NieuweRegio"):
        if needle not in d:
            return False, f"details mist {needle!r}: {d!r}"
    return True, f"action=kk_office_update bevat oude+nieuwe waarden"


def test_deactivate_logs():
    """T3: POST /pro/locaties/<id>/deactiveren logt kk_office_deactivate."""
    cleanup_test_data()
    oid = seed_office(name="ToBeKilled")
    n0 = count_logs()
    cookie = mint_kk_cookie()
    r = _post(f"/pro/locaties/{oid}/deactiveren", {}, cookie)
    if r.status_code != 302:
        return False, f"verwacht 302, kreeg {r.status_code}"
    if count_logs() != n0 + 1:
        return False, f"verwacht +1 log-rij, kreeg +{count_logs() - n0}"
    log = last_log()
    if log["action"] != "kk_office_deactivate":
        return False, f"action={log['action']!r}"
    if "ToBeKilled" not in log["details"]:
        return False, f"details mist office-naam: {log['details']!r}"
    return True, f"action=kk_office_deactivate details={log['details']!r}"


def test_import_logs_with_counts():
    """T4: /pro/locaties/import confirm logt kk_office_import + counts."""
    cleanup_test_data()
    # 2 rijen waarvan 1 dup: zaai eerst Dup-naam
    seed_office(name="DupName")
    csv = "office_name,region\nNieuw1,RegA\nDupName,RegB\nNieuw2,RegC\n"
    n0 = count_logs()
    cookie = mint_kk_cookie()
    r = _post("/pro/locaties/import", {
        "confirm": "1",
        "csv_text": csv,
        "csv_filename": "smoke.csv",
    }, cookie)
    if r.status_code != 302:
        return False, f"verwacht 302, kreeg {r.status_code}"
    if count_logs() != n0 + 1:
        return False, f"verwacht +1 log-rij, kreeg +{count_logs() - n0}"
    log = last_log()
    if log["action"] != "kk_office_import":
        return False, f"action={log['action']!r}"
    d = log["details"]
    if "imported=2" not in d or "dups=1" not in d or "total_rows=3" not in d:
        return False, f"details mist counts: {d!r}"
    if "smoke.csv" not in d:
        return False, f"details mist filename: {d!r}"
    return True, f"action=kk_office_import details={d!r}"


def test_failed_create_no_log():
    """T5: POST met lege naam → redirect met error, GEEN log-rij."""
    cleanup_test_data()
    n0 = count_logs()
    cookie = mint_kk_cookie()
    r = _post("/pro/locaties/toevoegen",
              {"office_name": "   ", "region": "Whatever"}, cookie)
    if r.status_code != 302:
        return False, f"verwacht 302 (error-redirect), kreeg {r.status_code}"
    if "error=leeg" not in r.headers.get("Location", ""):
        return False, f"verwacht ?error=leeg in Location, kreeg {r.headers.get('Location')!r}"
    if count_logs() != n0:
        return False, f"verwacht 0 nieuwe log-rij, kreeg +{count_logs() - n0}"
    return True, "geen log-rij bij failed create"


def test_log_includes_ip_and_ua():
    """T6: log-rij bevat ip_address en user_agent uit het verzoek."""
    cleanup_test_data()
    cookie = mint_kk_cookie()
    custom_ua = "AuditTestUA/1.0"
    r = requests.post(f"{BASE_URL}/pro/locaties/toevoegen",
                      data={"office_name": "MunchenAlt", "region": "Bayern"},
                      cookies={"session": cookie},
                      headers={"User-Agent": custom_ua},
                      allow_redirects=False, timeout=TIMEOUT)
    if r.status_code != 302:
        return False, f"verwacht 302, kreeg {r.status_code}"
    log = last_log()
    if not log:
        return False, "geen log-rij gevonden"
    if not log["ip_address"]:
        return False, "ip_address leeg"
    if log["user_agent"] != custom_ua:
        return False, f"user_agent={log['user_agent']!r}, verwacht {custom_ua!r}"
    return True, f"ip={log['ip_address']} ua={log['user_agent']}"


TESTS = [
    ("T1 create_logs_action",        test_create_logs_action),
    ("T2 update_logs_old_and_new",   test_update_logs_old_and_new),
    ("T3 deactivate_logs",           test_deactivate_logs),
    ("T4 import_logs_with_counts",   test_import_logs_with_counts),
    ("T5 failed_create_no_log",      test_failed_create_no_log),
    ("T6 log_includes_ip_and_ua",    test_log_includes_ip_and_ua),
]


def main():
    t0 = time.time()
    passed = 0
    failed = 0
    try:
        for name, fn in TESTS:
            try:
                ok, msg = fn()
            except Exception as e:
                ok, msg = False, f"EXC {type(e).__name__}: {e}"
            tag = "PASS" if ok else "FAIL"
            print(f"  {tag} {name} — {msg}")
            if ok:
                passed += 1
            else:
                failed += 1
    finally:
        cleanup_test_data()
    elapsed = time.time() - t0
    print(f"test_kk_audit_log: {passed} passed, {failed} failed ({elapsed:.1f}s)")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
