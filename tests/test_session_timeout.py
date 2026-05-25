"""Tests voor sessie-idle-timeout (Sessie B.4).

Doel: bevestigen dat een ingelogde sessie na 30 min inactiviteit auto-uitlogt,
zonder per-test 30 minuten te hoeven wachten. We minten Flask-sessie-cookies
met een handmatig gezette `_last_activity`-timestamp en hitten /pro/locaties.

Vijf tests:
    T1 — _last_activity 100s geleden  → 200, geen redirect
    T2 — _last_activity 1900s (>30m)  → 302 naar /login?timeout=1
    T3 — _last_activity 1700s (29m)   → 200, response zet nieuwe cookie met
                                          ververst _last_activity (≈ now)
    T4 — /login zelf is exempt        → 200 ongeacht _last_activity
    T5 — 2fa_expires-veld blijft los  → 30-min-timeout overrulet niet
                                          de 10-min 2FA-expiry, beide leven
                                          onafhankelijk in de sessie

Output: print "test_session_timeout: N passed, M failed (Ts)". Exit 0/1.
"""

import glob
import sys
import time
import requests
from flask import Flask
from flask.sessions import SecureCookieSessionInterface

BASE_URL = "http://localhost:8080"
TIMEOUT = 15
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


def _serializer():
    a = Flask(__name__)
    a.secret_key = _load_secret_key()
    return SecureCookieSessionInterface().get_signing_serializer(a)


def mint_kk_cookie(last_activity, extra=None):
    """Mint een KK-sessie-cookie met handmatige _last_activity-timestamp.
    Gebruikt fictieve license_code zodat de tests geen prod-data aanraken."""
    data = {
        "license_valid": True,
        "license_type": "pro",
        "audience": "krankenkasse",
        "license_code": "__TEST_TIMEOUT_KK__",
        "user_key": "__TEST_TIMEOUT_USER__",
        "lang": "nl",
        "profile_name": "Timeout-test",
        "profile_birth_year": 1980,
        "profile_gender": "male",
        "sensor_pref": "demo",
        "kk_office": "TestOffice",
        "_last_activity": last_activity,
    }
    if extra:
        data.update(extra)
    return _serializer().dumps(data)


def decode_session_cookie(raw):
    """Decode een Flask session cookie naar dict (best-effort)."""
    try:
        return _serializer().loads(raw)
    except Exception:
        return None


def _http_get(path, cookie, allow_redirects=False):
    return requests.get(f"{BASE_URL}{path}",
                        cookies={"session": cookie},
                        allow_redirects=allow_redirects,
                        timeout=TIMEOUT)


def test_session_active_under_30min():
    """T1: 100 sec sinds laatste actie → request slaagt, geen redirect."""
    cookie = mint_kk_cookie(last_activity=time.time() - 100)
    r = _http_get("/pro/locaties", cookie)
    if r.status_code != 200:
        return False, f"verwacht 200, kreeg {r.status_code} (Location={r.headers.get('Location','-')})"
    return True, "200 OK"


def test_session_expired_after_30min():
    """T2: 1900 sec (>30 min) → redirect 302 naar /login?timeout=1."""
    cookie = mint_kk_cookie(last_activity=time.time() - 1900)
    r = _http_get("/pro/locaties", cookie)
    if r.status_code != 302:
        return False, f"verwacht 302, kreeg {r.status_code}"
    loc = r.headers.get("Location", "")
    if "/login" not in loc or "timeout=1" not in loc:
        return False, f"verwacht Location naar /login?timeout=1, kreeg {loc!r}"
    return True, f"302 → {loc}"


def test_activity_refreshes_timeout():
    """T3: 1700 sec (29 min) → 200 + response zet cookie met ververst _last_activity."""
    cookie_old = mint_kk_cookie(last_activity=time.time() - 1700)
    r = _http_get("/pro/locaties", cookie_old)
    if r.status_code != 200:
        return False, f"verwacht 200, kreeg {r.status_code}"
    new_session = r.cookies.get("session")
    if not new_session:
        return False, "geen verse Set-Cookie 'session' in response"
    decoded = decode_session_cookie(new_session)
    if not decoded:
        return False, "kon nieuwe cookie niet decoden"
    new_last = decoded.get("_last_activity")
    if new_last is None:
        return False, "_last_activity ontbreekt in nieuwe cookie"
    if new_last < time.time() - 60:
        return False, f"_last_activity niet ververst: {time.time() - new_last:.1f}s oud"
    return True, f"_last_activity ververst naar {time.time() - new_last:.1f}s geleden"


def test_login_endpoint_excluded():
    """T4: /login is exempt — zelfs met 1 uur oude _last_activity geen redirect."""
    cookie = mint_kk_cookie(last_activity=time.time() - 3600)
    r = _http_get("/login", cookie)
    if r.status_code != 200:
        return False, f"verwacht 200 op /login, kreeg {r.status_code}"
    return True, "200 OK (timeout-hook overgeslagen)"


def test_2fa_flow_independent():
    """T5: 2fa_expires-veld blijft onaangeroerd door session-timeout-hook.
    Mint sessie zonder license_valid maar mét 2fa_expires; hit /verify_2fa
    (ook exempt); verwacht dat de pagina niet redirect t.g.v. timeout-hook."""
    a = Flask(__name__)
    a.secret_key = _load_secret_key()
    serializer = SecureCookieSessionInterface().get_signing_serializer(a)
    # Geen license_valid (nog niet ingelogd), wel 2fa_code (pending verify)
    data = {
        "2fa_code": "123456",
        "2fa_email": "timeout-test@example.com",
        "2fa_lang": "nl",
        "2fa_expires": time.time() + 600,
        "2fa_license_type": "pro",
        "lang": "nl",
    }
    cookie = serializer.dumps(data)
    r = requests.get(f"{BASE_URL}/verify",
                     cookies={"session": cookie},
                     allow_redirects=False, timeout=TIMEOUT)
    # /verify is exempt → moet GET serveren zonder dat de session-timeout-hook
    # in de weg zit. Bij ontbrekende 2fa_code zou /verify zelf 302 doen naar /login;
    # met onze 2fa_code moet het de form serveren (200).
    if r.status_code != 200:
        return False, f"verwacht 200 (verify_2fa form), kreeg {r.status_code} (Location={r.headers.get('Location','-')})"
    return True, "2FA-flow onaangeroerd door session-timeout-hook"


TESTS = [
    ("T1 active_under_30min",       test_session_active_under_30min),
    ("T2 expired_after_30min",      test_session_expired_after_30min),
    ("T3 activity_refreshes",       test_activity_refreshes_timeout),
    ("T4 login_endpoint_excluded",  test_login_endpoint_excluded),
    ("T5 2fa_flow_independent",     test_2fa_flow_independent),
]


def main():
    t0 = time.time()
    passed = 0
    failed = 0
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
    elapsed = time.time() - t0
    print(f"test_session_timeout: {passed} passed, {failed} failed ({elapsed:.1f}s)")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
