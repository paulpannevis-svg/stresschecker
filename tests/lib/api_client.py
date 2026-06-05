"""HTTP-helper voor tests tegen http://localhost:8080.

Omdat de echte /login-flow e-mail+wachtwoord+2FA vereist, "minten" we
hier een Flask-session-cookie met de SC_SECRET_KEY uit .env. De tests
draaien dan tegen de échte app-routes — inclusief de routing-logica
van app.py — maar zonder dat we e-mails moeten afhandelen.

Belangrijke valkuil in app.get_user_key(): als session['email'] gezet
is, overschrijft die elk frame session['user_key'] met sha256(email).
Daarom zetten we in onze gecrafte sessie GEEN email — alleen
user_key, license_valid, license_type en wat profielvelden.

Publieke API:
    mint_session_cookie(user_key, license_type) -> str
    ApiClient()                        — persistente HTTP-sessie
        .login_consumer(user_key)
        .login_pro(user_key)
        .select_client(cid)            — GET /pro/client/<cid>/meten
        .submit_measurement(**body)    — POST /api/meting/opslaan
        .list_client_metingen(cid)     — GET /api/pro/client/<cid>/metingen

De ApiClient houdt één requests.Session aan — cruciaal voor A4,
waar A2 en A3 in dezelfde sessie moeten lopen zodat de regressie-
bug zichtbaar wordt.
"""

import os
import time
import requests
from flask import Flask
from flask.sessions import SecureCookieSessionInterface

BASE_URL = "http://localhost:8080"
TIMEOUT = 30

_SECRET_KEY = None


def _load_secret_key():
    """Leest SC_SECRET_KEY uit de draaiende app-process-environment.

    Reden: .env wordt alleen geladen als systemd die env-var niet al
    heeft gezet (load_dotenv overschrijft niet). Om te garanderen dat
    de tests ALTIJD dezelfde signing-key gebruiken als de live app,
    lezen we uit /proc/<pid>/environ van het gunicorn-proces.
    Fallback naar .env als we het proces niet kunnen vinden.
    """
    global _SECRET_KEY
    if _SECRET_KEY is not None:
        return _SECRET_KEY
    import glob
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
        raise RuntimeError(
            "SC_SECRET_KEY niet gevonden — niet in /proc/<app>/environ "
            "en niet in /opt/stresschecker/.env"
        )
    return _SECRET_KEY


def mint_session_cookie(user_key, license_type):
    """Creëert een Flask-geldige sessie-cookie voor de opgegeven user_key."""
    _a = Flask(__name__)
    _a.secret_key = _load_secret_key()
    si = SecureCookieSessionInterface()
    serializer = si.get_signing_serializer(_a)
    session_data = {
        "license_valid": True,
        "license_type": license_type,
        "user_key": user_key,
        "lang": "nl",
        "profile_name": "Regressietest",
        "profile_birth_year": 1980,
        "profile_gender": "male",
        "sensor_pref": "demo",
    }
    return serializer.dumps(session_data)


class ApiClient:
    def __init__(self):
        self.session = requests.Session()
        self.license_type = None
        self.user_key = None

    def _install_cookie(self, user_key, license_type):
        # De initiële cookie moet dezelfde (domain, path) hebben als wat
        # requests toekent aan Set-Cookie-headers van de server. Anders
        # krijgen we twéé 'session' cookies naast elkaar na de eerste
        # server-response (stale + vers), en stuurt requests beide mee —
        # dan leest Flask de verkeerde en zijn session-mutaties weg.
        # Voor localhost gebruikt requests domain='localhost.local'.
        cookie = mint_session_cookie(user_key, license_type)
        self.session.cookies.clear()
        self.session.cookies.set(
            "session", cookie, domain="localhost.local", path="/",
        )
        self.license_type = license_type
        self.user_key = user_key

    def login_consumer(self, user_key):
        self._install_cookie(user_key, "consumer")

    def login_pro(self, user_key):
        self._install_cookie(user_key, "pro")

    def select_client(self, cid):
        """Zet session['measuring_for_client']=cid via de echte pro-route."""
        r = self.session.get(
            f"{BASE_URL}/pro/client/{cid}/meten",
            timeout=TIMEOUT,
            allow_redirects=False,
        )
        return r

    def submit_measurement(self, client_id=None, **overrides):
        """POST /api/meting/opslaan.

        client_id=None  — laat server beslissen (session.measuring_for_client
                          of ontbrekend body-veld)
        client_id=0     — forceert eigen meting via body
        client_id=N>0   — forceert cliënt-meting via body
        """
        body = {
            "ts": int(time.time() * 1000),
            "ri": 5.0,
            "bpm": 65,
            "hrv": 50,
            "rmssd": 30.0,
            "sdnn": 40.0,
            "pnn50": 10.0,
            "beats": 100,
            "duration": 90,
            "sensor": "regressietest",
            "meting_type": "basismeting",
        }
        if client_id is not None:
            body["client_id"] = client_id
        body.update(overrides)
        r = self.session.post(
            f"{BASE_URL}/api/meting/opslaan",
            json=body,
            timeout=TIMEOUT,
        )
        return r

    def list_client_metingen(self, cid):
        r = self.session.get(
            f"{BASE_URL}/api/pro/client/{cid}/metingen",
            timeout=TIMEOUT,
            allow_redirects=False,
        )
        return r
