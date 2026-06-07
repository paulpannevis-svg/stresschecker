#!/usr/bin/env python3
"""Structurele JS-syntaxcontrole van de GERENDERDE template-output.

Reden: de template-content-tests (test_voorvragen/test_prediction) checken alleen of
strings aanwezig zijn — ze vingen een echte JS-syntaxfout in voorbereiden.html NIET
(48/48 groen terwijl de pagina-JS stuk was, 2026-06-07). Dit script haalt de pagina's
op zoals ze worden geserveerd, knipt elk inline <script>-blok eruit en draait er
`node --check` op. Eén kapot script = exit 1.

Draait tegen de STAGING-server (default http://127.0.0.1:8090, override met SC_TEST_URL).
Sessie wordt geminned met SC_SECRET_KEY uit .env.staging. Vereist `node` op PATH.
"""
import os, re, sys, subprocess, tempfile
import requests
from flask import Flask
from flask.sessions import SecureCookieSessionInterface

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.environ.get('SC_TEST_URL', 'http://127.0.0.1:8090')

def _secret():
    for line in open(os.path.join(ROOT, '.env.staging'), encoding='utf-8'):
        if line.startswith('SC_SECRET_KEY='):
            return line.split('=', 1)[1].strip()
    raise SystemExit('SC_SECRET_KEY niet gevonden in .env.staging')

def _cookie(lang):
    a = Flask(__name__); a.secret_key = _secret()
    ser = SecureCookieSessionInterface().get_signing_serializer(a)
    return ser.dumps({"license_valid": True, "demo_mode": True, "license_type": "consumer",
                      "user_key": "__TEST_JSSYNTAX__", "lang": lang, "profile_name": "JS",
                      "profile_birth_year": 1980, "profile_gender": "male", "sensor_pref": "demo"})

# Pagina's die inline-JS bevatten en in dit spoor geraakt worden.
PAGES = [
    "/voorbereiden?next=basismeting&cid=0",
    "/voorbereiden?next=situatiemeting",
    "/voorbereiden?next=biofeedback",
    "/sensor-en-meten?type=basismeting",
    "/kwadrant",
    "/resultaten",
]
LANGS = ("nl", "de", "en")
# Inline <script> zonder src= (externe scripts overslaan).
SCRIPT_RE = re.compile(r'<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>', re.S)

def check_node():
    try:
        subprocess.run(['node', '--version'], capture_output=True, check=True)
    except Exception:
        print("[SKIP] node niet beschikbaar — JS-syntaxcontrole overgeslagen", file=sys.stderr)
        sys.exit(0)

def main():
    check_node()
    passed = failed = 0
    for page in PAGES:
        for lang in LANGS:
            url = BASE + page
            try:
                r = requests.get(url, cookies={'session': _cookie(lang)}, timeout=20, allow_redirects=False)
            except Exception as e:
                print(f"[FAIL] {page} [{lang}] — request fout: {e}"); failed += 1; continue
            if r.status_code != 200:
                print(f"[WARN] {page} [{lang}] — status {r.status_code} (geen render, overgeslagen)")
                continue
            blocks = [b for b in SCRIPT_RE.findall(r.text) if b.strip()]
            ok = True
            for i, body in enumerate(blocks):
                with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8') as f:
                    f.write(body); path = f.name
                res = subprocess.run(['node', '--check', path], capture_output=True, text=True)
                os.unlink(path)
                if res.returncode != 0:
                    ok = False
                    print(f"[FAIL] {page} [{lang}] script#{i}:\n{res.stderr.strip()[:500]}")
            if ok:
                passed += 1; print(f"[PASS] {page} [{lang}] — {len(blocks)} script(s) ok")
            else:
                failed += 1
    print(f"\nsmoke_js_syntax: {passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)

if __name__ == '__main__':
    main()
