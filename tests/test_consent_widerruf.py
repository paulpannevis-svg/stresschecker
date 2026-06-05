"""Categorie D — Widerruf-/gezondheidsdata-instemming op /licentie.

Dekt de juridische instemmingsflow (§ 356 Abs. 5 BGB / art. 6:230p BW):
de tweede checkbox, de verplichte server-side validatie, het wegschrijven
van consent_log-rijen bij een echte activering, en de consent-alinea in de
activeringsbevestiging.

    D1 — Activering zonder widerruf-vinkje → redirect+foutmelding, licentie
         blijft 'available', GEEN consent-rij.
    D2 — Activering met beide vinkjes → /verify → succes: licentie 'activated',
         twee consent_log-rijen (juiste text_version/locale/created_at), en de
         bevestigingsmail wordt verstuurd.
    D3 — build_activation_confirmation_body bevat de consent-alinea + tijdstip
         in alle drie de talen.
    D4 — REGRESSIE: de login-flow (/login) vereist GEEN checkbox en schrijft
         GEEN consent-rij (een login activeert niets).

Eigen fixture-licentie '__TEST_LICENSE_CONSENT__' + eigen test-e-mail; alle
SendGrid-aanroepen gemockt. Productie-fixtures (o.a. id=25/26 test-rifix@)
worden NIET aangeraakt — setup/cleanup raken uitsluitend de eigen marker-rijen.
"""

import sys
import time
import sqlite3
import datetime as _dt
import unittest.mock as _mock

sys.path.insert(0, "/opt/stresschecker")
sys.path.insert(0, "/opt/stresschecker/tests")

import app as _app  # noqa: E402

SAAS = "/opt/ic-license-server/data/saas_licenses.db"
TEST_CODE = "__TEST_LICENSE_CONSENT__"
TEST_EMAIL = "consent_test@example.test"
TEST_PW = "testpw12345"


def _report(name, ok, reason):
    tag = "PASS" if ok else "FAIL"
    print(f"[{tag}] {name}: {reason}")
    return ok


def _client():
    _app.app.config["TESTING"] = True
    return _app.app.test_client()


def _con():
    return sqlite3.connect(SAAS)


def _consent_rows():
    c = _con()
    try:
        c.row_factory = sqlite3.Row
        return c.execute(
            "SELECT * FROM consent_log WHERE license_code=? ORDER BY consent_type",
            (TEST_CODE,)).fetchall()
    finally:
        c.close()


def _license_status():
    c = _con()
    try:
        r = c.execute("SELECT status FROM licenses WHERE license_key=?", (TEST_CODE,)).fetchone()
        return r[0] if r else None
    finally:
        c.close()


def _user_count():
    c = _con()
    try:
        return c.execute("SELECT COUNT(*) FROM users WHERE email=?", (TEST_EMAIL,)).fetchone()[0]
    finally:
        c.close()


def reset_fixture():
    """Verse 'available' consumer-licentie, geen user, geen consent-rijen."""
    c = _con()
    try:
        c.execute("DELETE FROM licenses WHERE license_key=?", (TEST_CODE,))
        c.execute("DELETE FROM users WHERE email=?", (TEST_EMAIL,))
        c.execute("DELETE FROM consent_log WHERE license_code=?", (TEST_CODE,))
        c.execute(
            "INSERT INTO licenses (license_key, product, type, status, origin, max_profiles, created_at) "
            "VALUES (?, 'sc', 'consumer', 'available', 'manual', 1, datetime('now'))",
            (TEST_CODE,))
        c.commit()
    finally:
        c.close()


def cleanup_fixture():
    c = _con()
    try:
        c.execute("DELETE FROM licenses WHERE license_key=?", (TEST_CODE,))
        c.execute("DELETE FROM users WHERE email=?", (TEST_EMAIL,))
        c.execute("DELETE FROM consent_log WHERE license_code=?", (TEST_CODE,))
        c.commit()
    finally:
        c.close()


def d1_activation_without_widerruf_blocked():
    name = "D1 zonder widerruf → blocked, geen consent-rij"
    reset_fixture()
    client = _client()
    r = client.post("/activeer", data={
        "type": "nieuw", "code": TEST_CODE, "email": TEST_EMAIL,
        "password": TEST_PW, "lang": "nl", "privacy_consent": "on",
        # widerruf_consent bewust afwezig
    })
    if r.status_code != 302:
        return _report(name, False, f"verwachte 302, kreeg {r.status_code}")
    loc = r.headers.get("Location", "")
    if "/licentie" not in loc or "error=" not in loc:
        return _report(name, False, f"verwachte /licentie?error=..., kreeg {loc!r}")
    if _license_status() != "available":
        return _report(name, False, f"licentie gewijzigd naar {_license_status()!r}")
    rows = _consent_rows()
    if len(rows) != 0:
        return _report(name, False, f"verwachte 0 consent-rijen, kreeg {len(rows)}")
    if _user_count() != 0:
        return _report(name, False, "user mocht niet aangemaakt worden")
    return _report(name, True, "redirect+foutmelding, licentie available, 0 consent-rijen")


def d2_activation_with_both_logs_two_rows():
    name = "D2 beide vinkjes → activated + 2 consent-rijen + mail"
    reset_fixture()
    client = _client()
    sent = {"mail": []}

    def _capture_mail(email, lang, ts):
        sent["mail"].append((email, lang, ts))
        return True

    with _mock.patch.object(_app, "send_verification_code", return_value=True), \
         _mock.patch.object(_app, "send_activation_confirmation_email", side_effect=_capture_mail):
        r1 = client.post("/activeer", data={
            "type": "nieuw", "code": TEST_CODE, "email": TEST_EMAIL,
            "password": TEST_PW, "lang": "nl",
            "privacy_consent": "on", "widerruf_consent": "on",
        })
        if r1.status_code != 302 or "/verify" not in r1.headers.get("Location", ""):
            return _report(name, False, f"stap1 verwachtte 302→/verify, kreeg {r1.status_code} {r1.headers.get('Location')!r}")
        with client.session_transaction() as s:
            code_2fa = s.get("2fa_code")
            cm = s.get("consent_meta")
        if not code_2fa:
            return _report(name, False, "geen 2fa_code in sessie na /activeer")
        if not cm or "consent_at" not in cm:
            return _report(name, False, f"consent_meta ontbreekt/incompleet: {cm!r}")
        r2 = client.post("/verify", data={"code": code_2fa})
        if r2.status_code != 302:
            return _report(name, False, f"stap2 verwachtte 302, kreeg {r2.status_code}")

    if _license_status() != "activated":
        return _report(name, False, f"licentie niet activated maar {_license_status()!r}")

    rows = _consent_rows()
    if len(rows) != 2:
        return _report(name, False, f"verwachte 2 consent-rijen, kreeg {len(rows)}")
    by_type = {row["consent_type"]: row for row in rows}
    if set(by_type) != {"widerruf", "gezondheidsdata"}:
        return _report(name, False, f"onverwachte consent_types: {set(by_type)}")
    for ctype, row in by_type.items():
        exp_ver = _app.CONSENT_TEXT_VERSIONS[ctype]["nl"]
        if row["text_version"] != exp_ver:
            return _report(name, False, f"{ctype}: text_version {row['text_version']!r} != {exp_ver!r}")
        if row["locale"] != "nl":
            return _report(name, False, f"{ctype}: locale {row['locale']!r} != 'nl'")
        if row["email"] != TEST_EMAIL:
            return _report(name, False, f"{ctype}: email {row['email']!r}")
        try:
            _dt.datetime.fromisoformat(row["created_at"])
        except (TypeError, ValueError):
            return _report(name, False, f"{ctype}: created_at niet-parseerbaar: {row['created_at']!r}")
    # Beide rijen delen exact het aanvink-tijdstip uit /activeer
    if by_type["widerruf"]["created_at"] != by_type["gezondheidsdata"]["created_at"]:
        return _report(name, False, "created_at verschilt tussen de twee rijen")
    if by_type["widerruf"]["created_at"] != cm["consent_at"]:
        return _report(name, False, "created_at != consent_meta.consent_at (aanvink-tijdstip)")

    if len(sent["mail"]) != 1:
        return _report(name, False, f"verwachte 1 bevestigingsmail, kreeg {len(sent['mail'])}")
    if sent["mail"][0][0] != TEST_EMAIL or sent["mail"][0][1] != "nl":
        return _report(name, False, f"mail verkeerd geadresseerd: {sent['mail'][0]!r}")

    return _report(name, True, f"activated, 2 rijen, created_at={by_type['widerruf']['created_at']}, mail verstuurd")


def d3_confirmation_email_contains_consent_paragraph():
    name = "D3 bevestigingsmail bevat consent-alinea (3 talen)"
    ts = "2026-06-05T10:00:00"
    checks = {
        "de": "Widerrufsrecht",
        "nl": "herroepingsrecht",
        "en": "right of withdrawal",
    }
    for lang, needle in checks.items():
        subject, body = _app.build_activation_confirmation_body(lang, ts)
        if needle not in body:
            return _report(name, False, f"{lang}: alinea-fragment {needle!r} ontbreekt")
        if ts not in body:
            return _report(name, False, f"{lang}: tijdstip {ts!r} ontbreekt")
        if not subject:
            return _report(name, False, f"{lang}: lege subject")
    return _report(name, True, "alle 3 talen bevatten de consent-alinea + tijdstip")


def d4_login_flow_requires_no_consent():
    name = "D4 REGRESSIE login (/login) → geen checkbox, geen consent-rij"
    reset_fixture()
    # Maak een al-geactiveerd account met wachtwoord, zoals een terugkerende gebruiker.
    c = _con()
    try:
        c.execute("UPDATE licenses SET status='activated', email=? WHERE license_key=?",
                  (TEST_EMAIL, TEST_CODE))
        c.execute("INSERT INTO users (email, password_hash, display_name, created_at) "
                  "VALUES (?, ?, 'Consent Test', datetime('now'))",
                  (TEST_EMAIL, _app.hash_password(TEST_PW)))
        c.commit()
    finally:
        c.close()
    client = _client()
    with _mock.patch.object(_app, "send_verification_code", return_value=True):
        r = client.post("/login", data={
            "email": TEST_EMAIL, "password": TEST_PW, "lang": "nl", "type": "consumer",
            # geen privacy_consent, geen widerruf_consent
        })
    if r.status_code != 302 or "/verify" not in r.headers.get("Location", ""):
        return _report(name, False, f"verwachte 302→/verify, kreeg {r.status_code} {r.headers.get('Location')!r}")
    rows = _consent_rows()
    if len(rows) != 0:
        return _report(name, False, f"login mocht geen consent-rij schrijven, kreeg {len(rows)}")
    return _report(name, True, "login werkt zonder checkbox, 0 consent-rijen")


TESTS = [
    d1_activation_without_widerruf_blocked,
    d2_activation_with_both_logs_two_rows,
    d3_confirmation_email_contains_consent_paragraph,
    d4_login_flow_requires_no_consent,
]


def main():
    passed = failed = 0
    start = time.time()
    try:
        for t in TESTS:
            try:
                ok = t()
            except Exception as e:
                import traceback
                print(f"[FAIL] {t.__name__}: onverwachte exception: {e}")
                traceback.print_exc()
                ok = False
            passed += 1 if ok else 0
            failed += 0 if ok else 1
    finally:
        cleanup_fixture()
    dur = time.time() - start
    print(f"\ncategorie D: {passed} passed, {failed} failed  ({dur:.1f}s)")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
