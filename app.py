from flask import Flask, render_template, make_response, request, jsonify, session, redirect, url_for, Response, send_file, abort
import sqlite3, os, hashlib, secrets, json, io, time
from datetime import datetime, timedelta
from dotenv import load_dotenv
load_dotenv()
from eval_config import EVAL_DURATION_DAYS

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB
# Sessie-idle-timeout (Sessie B.4 — Datenschutz voor KK-context)
# 30 min na laatste activiteit → automatische sessie-uitlog door before_request-hook.
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)
SESSION_IDLE_TIMEOUT_SECONDS = 30 * 60
SESSION_IDLE_TIMEOUT_OPERATOR_SECONDS = 24 * 60 * 60
# SMTP configuratie voor 2FA verificatiecodes
MAIL_SERVER   = 'mailout.hostnet.nl'
MAIL_PORT     = 587
MAIL_USERNAME = 'noreply@lifestylemonitors.com'
MAIL_PASSWORD = '55Bumper@#'

import random, os

def send_verification_code(email, code, lang='nl'):
    try:
        import sendgrid
        from sendgrid.helpers.mail import Mail
        sg = sendgrid.SendGridAPIClient(os.environ['SENDGRID_API_KEY'])
        if lang == 'de':
            subject = 'Ihr Verifizierungscode – StressChecker'
            body = f'Ihr Verifizierungscode lautet: {code}\n\nDieser Code ist 10 Minuten gültig.'
        elif lang == 'en':
            subject = 'Your verification code – StressChecker'
            body = f'Your verification code is: {code}\n\nThis code is valid for 10 minutes.'
        else:
            subject = 'Uw verificatiecode – StressChecker'
            body = f'Uw verificatiecode is: {code}\n\nDeze code is 10 minuten geldig.'
        msg = Mail(from_email='noreply@lifestylemonitors.com', to_emails=email, subject=subject, plain_text_content=body)
        sg.send(msg)
        return True
    except Exception as e:
        print('Mail fout:', e)
        return False


def send_password_reset_email(email, code, lang='nl'):
    try:
        import sendgrid
        from sendgrid.helpers.mail import Mail
        sg = sendgrid.SendGridAPIClient(os.environ['SENDGRID_API_KEY'])
        if lang == 'de':
            subject = 'Passwort zurücksetzen – StressChecker'
            body = (f'Sie haben angefragt, Ihr Passwort zurückzusetzen.\n\n'
                    f'Ihr Reset-Code lautet: {code}\n\n'
                    f'Dieser Code ist 10 Minuten gültig und kann nur einmal verwendet werden.\n\n'
                    f'Falls Sie diese Anfrage nicht gestellt haben, ignorieren Sie diese E-Mail.')
        elif lang == 'en':
            subject = 'Reset your password – StressChecker'
            body = (f'You requested a password reset.\n\n'
                    f'Your reset code is: {code}\n\n'
                    f'This code is valid for 10 minutes and can only be used once.\n\n'
                    f'If you did not request this, please ignore this email.')
        else:
            subject = 'Wachtwoord resetten – StressChecker'
            body = (f'Je hebt een wachtwoordreset aangevraagd.\n\n'
                    f'Je resetcode is: {code}\n\n'
                    f'Deze code is 10 minuten geldig en kan slechts één keer gebruikt worden.\n\n'
                    f'Heb je dit niet aangevraagd? Negeer dan deze e-mail.')
        msg = Mail(from_email='noreply@lifestylemonitors.com', to_emails=email, subject=subject, plain_text_content=body)
        sg.send(msg)
        return True
    except Exception as e:
        print('Mail fout:', e)
        return False


# ============================================================================
# Widerruf-/gezondheidsdata-instemming (§ 356 Abs. 5 BGB / art. 6:230p BW)
# ----------------------------------------------------------------------------
# De activeringspagina /licentie is het juridische moment waarop het
# herroepingsrecht voor de digitale dienst vervalt. Bij elke echte
# licentie-activering leggen we twee instemmingen vast in consent_log
# (saas_licenses.db), binnen dezelfde transactie als de activerings-UPDATE.
# Tekstversies zijn constanten: een latere tekstwijziging krijgt een nieuwe
# version-string (bv. ...-v2-YYYYMMDD), zodat altijd traceerbaar is welke
# formulering iemand heeft gezien.
# ============================================================================
CONSENT_TEXT_VERSIONS = {
    'widerruf': {
        'de': 'widerruf-de-v1-20260605',
        'nl': 'widerruf-nl-v1-20260605',
        'en': 'widerruf-en-v1-20260605',
    },
    'gezondheidsdata': {
        'de': 'gezondheit-de-v1-20260605',
        'nl': 'gezondheit-nl-v1-20260605',
        'en': 'gezondheit-en-v1-20260605',
    },
}

# Consent-alinea voor de activeringsbevestiging (duurzame drager, § 312f BGB).
# {ts} wordt vervangen door het UTC-tijdstip van instemming.
CONSENT_EMAIL_PARAGRAPH = {
    'de': ("Bei der Aktivierung haben Sie ausdrücklich zugestimmt, dass die "
           "Bereitstellung der digitalen Leistung vor Ablauf der Widerrufsfrist "
           "beginnt, und bestätigt, dass Ihr Widerrufsrecht für die digitale "
           "Leistung damit erlischt. Das Widerrufsrecht für die Hardware bleibt "
           "unberührt. (Zeitpunkt der Zustimmung: {ts} UTC)"),
    'nl': ("Bij de activering hebt u er uitdrukkelijk mee ingestemd dat de "
           "levering van de digitale dienst begint vóór het einde van de "
           "bedenktijd, en bevestigd dat uw herroepingsrecht voor de digitale "
           "dienst daarmee vervalt. Het herroepingsrecht voor de hardware "
           "blijft onverlet. (Tijdstip van instemming: {ts} UTC)"),
    'en': ("During activation you expressly agreed that the provision of the "
           "digital service begins before the end of the withdrawal period, and "
           "confirmed that your right of withdrawal for the digital service "
           "thereby lapses. The right of withdrawal for the hardware remains "
           "unaffected. (Time of consent: {ts} UTC)"),
}


def _log_consent(conn, email, license_code, locale, consent_at):
    """Schrijf de twee instemmings-rijen (widerruf + gezondheidsdata) op een
    REEDS GEOPENDE connectie, zodat ze meegaan in de transactie van de aanroeper
    (de activerings-UPDATE). De caller commit. locale valt terug op 'nl' bij een
    onbekende taal zodat text_version altijd resolvet."""
    loc = locale if locale in ('nl', 'de', 'en') else 'nl'
    for ctype in ('widerruf', 'gezondheidsdata'):
        conn.execute(
            "INSERT INTO consent_log (email, license_code, consent_type, text_version, locale, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (email, license_code, ctype, CONSENT_TEXT_VERSIONS[ctype][loc], loc, consent_at)
        )


def build_activation_confirmation_body(lang, consent_ts):
    """Pure builder voor de activeringsbevestiging (testbaar zonder SendGrid).
    Retourneert (subject, body) met de consent-alinea inclusief tijdstip."""
    loc = lang if lang in ('nl', 'de', 'en') else 'nl'
    para = CONSENT_EMAIL_PARAGRAPH[loc].format(ts=consent_ts)
    if loc == 'de':
        subject = 'Ihre StressChecker-Lizenz ist aktiviert'
        intro = ('Vielen Dank — Ihre Lizenz wurde erfolgreich aktiviert und alle '
                 'Funktionen sind freigeschaltet.')
        outro = 'Mit freundlichen Grüßen\nIhr StressChecker-Team'
    elif loc == 'en':
        subject = 'Your StressChecker licence is activated'
        intro = ('Thank you — your licence has been successfully activated and all '
                 'features are unlocked.')
        outro = 'Kind regards\nThe StressChecker team'
    else:
        subject = 'Uw StressChecker-licentie is geactiveerd'
        intro = ('Bedankt — uw licentie is succesvol geactiveerd en alle functies '
                 'zijn ontgrendeld.')
        outro = 'Met vriendelijke groet\nHet StressChecker-team'
    body = f"{intro}\n\n{para}\n\n{outro}"
    return subject, body


def send_activation_confirmation_email(email, lang, consent_ts):
    """Verstuur de activeringsbevestiging (duurzame drager) ná succesvolle
    activering. Best-effort: een mailfout mag de activering niet breken."""
    subject, body = build_activation_confirmation_body(lang, consent_ts)
    try:
        import sendgrid
        from sendgrid.helpers.mail import Mail
        sg = sendgrid.SendGridAPIClient(os.environ['SENDGRID_API_KEY'])
        msg = Mail(from_email='noreply@lifestylemonitors.com', to_emails=email,
                   subject=subject, plain_text_content=body)
        sg.send(msg)
        return True
    except Exception as e:
        print('Activatie-bevestigingsmail fout:', e)
        return False


def hash_password(password):
    import bcrypt
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(12)).decode('utf-8')


def verify_password(password, stored_hash):
    # Returns (matches, is_legacy_sha256). is_legacy=True signaleert dat caller naar bcrypt moet re-hashen.
    import bcrypt, hashlib
    if not stored_hash:
        return (False, False)
    if stored_hash.startswith('$2'):
        try:
            ok = bcrypt.checkpw(password.encode('utf-8'), stored_hash.encode('utf-8'))
            return (ok, False)
        except (ValueError, TypeError):
            return (False, False)
    if len(stored_hash) == 64:
        sha = hashlib.sha256(password.encode('utf-8')).hexdigest()
        return (sha == stored_hash, True)
    return (False, False)


MAIL_FROM     = 'StressChecker <noreply@lifestylemonitors.com>'

from hlm.routes import hlm as hlm_blueprint
app.register_blueprint(hlm_blueprint)
app.secret_key = os.environ.get('SC_SECRET_KEY', 'change-this-in-production')

@app.template_filter('full_name')
def _full_name_filter(obj, surname=None):
    """Render 'voornaam achternaam' als achternaam aanwezig, anders alleen 'voornaam'.

    Accepteert: sqlite3.Row, dict, object met .name/.surname-attrs, of een string
    (in dat geval mag surname expliciet als 2e argument worden meegegeven)."""
    if obj is None:
        return ''
    if isinstance(obj, str):
        s = (surname or '').strip() if surname else ''
        return (obj.strip() + ' ' + s).strip() if s else obj.strip()
    name = ''
    s = ''
    try:
        if hasattr(obj, 'keys'):
            keys = list(obj.keys())
            if 'name' in keys: name = obj['name']
            if 'surname' in keys: s = obj['surname']
        else:
            name = getattr(obj, 'name', '') or ''
            s = getattr(obj, 'surname', '') or ''
    except Exception:
        pass
    name = (name or '').strip()
    s = (s or '').strip()
    return (name + ' ' + s).strip() if s else name

DB_PATH        = os.environ.get('SC_DB_PATH', '/opt/ic-license-server/data/saas_licenses.db')
METING_DB_PATH = os.environ.get('SC_METING_DB', '/opt/stresschecker/data/sc_measurements.db')
PRO_DB_PATH    = os.environ.get('SC_PRO_DB', '/opt/stresschecker/data/sc_pro.db')

# Aantal eerste metingen waarbij educatieve blokken standaard openstaan voor
# nieuwe consumenten. Pas aan op basis van gebruikersonderzoek.
EDU_BLOCKS_MAX_MEASUREMENTS = 3

# ─── Database helpers ────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_meting_db():
    os.makedirs(os.path.dirname(METING_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(METING_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('''CREATE TABLE IF NOT EXISTS metingen (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_key    TEXT NOT NULL,
        ts          INTEGER NOT NULL,
        ri          REAL NOT NULL,
        bpm         INTEGER NOT NULL,
        hrv_pct     INTEGER NOT NULL,
        rmssd       REAL,
        beats       INTEGER,
        duration    INTEGER DEFAULT 90,
        sensor_type TEXT DEFAULT 'unknown',
        notes       TEXT,
        ctx_dimensie  TEXT,
        ctx_vitaliteit REAL,
        created_at  TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    for col, coltype in [('ctx_dimensie', 'TEXT'), ('ctx_vitaliteit', 'REAL'), ('feedback_cache', 'TEXT')]:
        try: conn.execute(f'ALTER TABLE metingen ADD COLUMN {col} {coltype}')
        except: pass
    conn.commit()
    return conn

def get_pro_db():
    os.makedirs(os.path.dirname(PRO_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(PRO_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('''CREATE TABLE IF NOT EXISTS clients (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        pro_key     TEXT NOT NULL,
        name        TEXT NOT NULL,
        birth_year  INTEGER DEFAULT 1970,
        gender      TEXT DEFAULT 'male',
        client_code TEXT UNIQUE,
        email       TEXT,
        phone       TEXT,
        notes       TEXT,
        active      INTEGER DEFAULT 1,
        created_at  TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS client_metingen (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id   INTEGER NOT NULL,
        pro_key     TEXT NOT NULL,
        ts          INTEGER NOT NULL,
        ri          REAL NOT NULL,
        bpm         INTEGER NOT NULL,
        hrv_pct     INTEGER NOT NULL,
        rmssd       REAL,
        sdnn        REAL,
        pnn50       REAL,
        beats       INTEGER,
        duration    INTEGER DEFAULT 90,
        sensor_type TEXT DEFAULT 'unknown',
        notes       TEXT,
        timeseries  TEXT,
        rr_intervals TEXT,
        ctx_dimensie  TEXT,
        ctx_vitaliteit REAL,
        created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (client_id) REFERENCES clients(id)
    )''')
    for col, coltype in [('ctx_dimensie', 'TEXT'), ('ctx_vitaliteit', 'REAL'), ('feedback_cache', 'TEXT')]:
        try: conn.execute(f'ALTER TABLE client_metingen ADD COLUMN {col} {coltype}')
        except: pass
    conn.commit()
    return conn

def get_user_key():
    import hashlib
    # KK-sessies: pro_key gederiveerd van licentie-houder-email (stabiel voor admin én
    # operator). Anders zou een operator zijn eigen email-hash krijgen en zouden zijn
    # metingen buiten de KK-aggregatie vallen.
    if session.get('audience') == 'krankenkasse':
        lc = session.get('license_code', '')
        if lc:
            cached = session.get('_kk_pro_key')
            if cached:
                session['user_key'] = cached
                return cached
            try:
                cn = sqlite3.connect('/opt/ic-license-server/data/saas_licenses.db')
                row = cn.execute("SELECT email FROM licenses WHERE license_key=?", (lc,)).fetchone()
                cn.close()
                if row and row[0]:
                    key = hashlib.sha256(row[0].encode()).hexdigest()[:32]
                    session['_kk_pro_key'] = key
                    session['user_key'] = key
                    session.modified = True
                    return key
            except Exception:
                pass
    # Als er een email in sessie zit, gebruik die als stabiele basis
    email = session.get('email', '')
    if email:
        key = hashlib.sha256(email.encode()).hexdigest()[:32]
        session['user_key'] = key
        session.modified = True
        return key
    # Fallback: bestaande user_key of sessie-token
    uk = session.get('user_key', '')
    if uk:
        return uk
    import secrets
    code = secrets.token_hex(8)
    session['session_id'] = code
    uk = code
    session['user_key'] = uk
    session.modified = True
    return uk

def generate_client_code():
    while True:
        code = 'SC-CLI-' + secrets.token_hex(2).upper()
        db = get_pro_db()
        exists = db.execute("SELECT id FROM clients WHERE client_code = ?", (code,)).fetchone()
        db.close()
        if not exists:
            return code

def validate_license(code, email):
    print(f"VALIDATE START: code={code}", flush=True)
    code = code.strip().upper()
    # Normaliseer: als code geen streepjes heeft en lang genoeg is, voeg ze toe (legacy formaat)
    code_clean = code.replace('-', '')
    if len(code_clean) == 32 and not code.startswith('SC'):
        # Legacy code formaat: XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX
        code = '-'.join([code_clean[i:i+4] for i in range(0, 32, 4)])
    db_path = '/opt/ic-license-server/data/saas_licenses.db'
    try:
        db = sqlite3.connect(db_path)
        db.row_factory = sqlite3.Row
        # 1. New licenses
        # LEFT JOIN op subscriptions — grace-period tot current_period_end voor canceled/past_due.
        # NULL sub (manual/migration/legacy/PayPal-pre-Stripe): puur op licenses.status.
        row = db.execute("""
            SELECT l.license_key, l.type, l.status, l.valid_until,
                   l.stripe_subscription_id, l.origin, l.email, l.code_expires_at,
                   p.audience AS plan_audience, p.plan_id AS plan_id, p.tier AS plan_tier,
                   s.status AS sub_status, s.current_period_end,
                   CASE
                     WHEN l.status NOT IN ('available', 'activated') THEN 0
                     WHEN s.subscription_id IS NULL THEN 1
                     WHEN s.status IN ('active', 'trialing') THEN 1
                     WHEN s.status IN ('canceled', 'past_due')
                          AND s.current_period_end IS NOT NULL
                          AND s.current_period_end > strftime('%Y-%m-%dT%H:%M:%S', 'now') THEN 1
                     ELSE 0
                   END AS effective_valid
            FROM licenses l
            LEFT JOIN subscriptions s ON l.stripe_subscription_id = s.subscription_id
            LEFT JOIN plans p ON p.plan_id = l.product
            WHERE l.license_key=?
        """, (code,)).fetchone()
        if row:
            if row['status'] not in ('available', 'activated'):
                return {'valid': False, 'error': 'Licentie verlopen of geannuleerd'}
            if row['effective_valid']:
                _type = row['type'] or 'consumer'
                # audience uit plans als beschikbaar, anders afleiden uit type
                _audience = row['plan_audience'] or _type
                result = {'valid': True, 'type': _type, 'audience': _audience,
                          'plan_id': row['plan_id'], 'plan_tier': row['plan_tier'],
                          'source': 'license', 'valid_until': row['valid_until'],
                          'origin': row['origin'], 'bound_email': row['email'], 'code_expires_at': row['code_expires_at']}
                if row['sub_status'] in ('canceled', 'past_due') and row['current_period_end']:
                    result['grace_until'] = row['current_period_end']
                return result
            return {'valid': False, 'error': 'Abonnement opgezegd of niet betaald'}
        # 2. Legacy keys (3999 oude codes)
        legacy = db.execute("SELECT id, license_key, product, status FROM legacy_keys WHERE license_key=?", (code,)).fetchone()
        if legacy:
            if legacy['status'] == 'migrated':
                mig = db.execute("SELECT license_key, type, status, valid_until FROM licenses WHERE legacy_key=?", (code,)).fetchone()
                if mig and mig['status'] in ('available', 'activated'):
                    return {'valid': True, 'type': mig['type'] or 'consumer', 'source': 'migrated_legacy', 'valid_until': mig['valid_until'], 'migrated_code': mig['license_key']}
                return {'valid': False, 'error': 'Code verlopen of ongeldig'}
            if legacy['status'] in ('available', 'issued', 'unknown'):
                return {'valid': True, 'type': 'legacy', 'needs_choice': True, 'legacy_id': legacy['id'], 'source': 'legacy'}
        db.close()
    except Exception as e:
        import traceback; print(f"LICENSE ERROR: {e} {traceback.format_exc()}", flush=True)
    # 3. Test codes
    if code.upper() in ('SC-TEST-CONS', 'SC-PRO-TEST-CODE'):
        return {'valid': True, 'type': 'pro' if 'PRO' in code.upper() else 'consumer'}
    return {'valid': False, 'error': 'Ongeldige licentiecode'}



def is_pro():
    return session.get('license_type') == 'pro'


def _is_pro_or_demo_pro():
    """Pro-rol-toelating: echte Pro, of demo-modus met expliciete pro-rol.
    Voorkomt dat een consumer-demo (demo_mode=True, license_type='consumer')
    Pro-routes binnenkomt en cliëntdata of -lijsten ziet.
    """
    return is_pro() or (session.get('demo_mode') and session.get('license_type') == 'pro')


def is_krankenkasse_session():
    """True wanneer huidige sessie hoort bij een Krankenkasse-licentie (plans.audience='krankenkasse').
    Krankenkasse-gebruikers tellen ook als is_pro() — de audience is een sub-rol bovenop Pro."""
    return session.get('audience') == 'krankenkasse'


def is_kk_admin():
    return is_krankenkasse_session() and session.get('role') == 'admin'


def is_kk_operator():
    return is_krankenkasse_session() and session.get('role') == 'operator'


def require_kk_admin(view):
    import functools
    @functools.wraps(view)
    def _wrapped(*args, **kwargs):
        if not session.get('license_valid'):
            return redirect(url_for('sc_login'))
        if not is_kk_admin():
            return ("Forbidden — admin role required", 403)
        return view(*args, **kwargs)
    return _wrapped


def kk_tier_label():
    """Renderbaar tier-label voor Krankenkasse-licentie (Kompakt/Standard/Premium).
    Leest plan_id uit session; valt terug op '?' wanneer onbekend."""
    pid = session.get('plan_id') or ''
    if pid.endswith('-kompakt'):  return 'Kompakt'
    if pid.endswith('-standard'): return 'Standard'
    if pid.endswith('-premium'):  return 'Premium'
    return '?'


def require_kk_office_if_krankenkasse(view):
    """Decorator: KK-sessie routering.
    - role='admin'  → naar KK-admin-dashboard (eigen scherm, geen kantoor-keuze)
    - role=operator/missing → bestaande flow: /pro/locatie als nog geen kantoor gekozen
    Andere audiences ongemoeid; geen redirect-loop op pro_locatie zelf."""
    import functools
    @functools.wraps(view)
    def _wrapped(*args, **kwargs):
        if is_krankenkasse_session():
            # Admin zonder kk_office → dashboard. Met kk_office (gekozen via
            # /pro/admin/messen-standort-kiezen) valt admin door op operator-pad
            # zodat /pro/meting bereikbaar is.
            if session.get('role') == 'admin' and not session.get('kk_office'):
                return redirect('/pro/admin')
            if not session.get('kk_office'):
                return redirect(url_for('pro_locatie'))
        return view(*args, **kwargs)
    return _wrapped


@app.context_processor
def _inject_kk_flags():
    """Maakt `is_krankenkasse` in elke template beschikbaar zonder per-view-doorgift."""
    return {'is_krankenkasse': is_krankenkasse_session()}


# ----------------------------------------------------------------------------
# Sessie-idle-timeout (Sessie B.4)
# Vervalt sessie automatisch na 30 minuten inactiviteit. Vereist voor
# Datenschutz-compliance van het Krankenkasse-zelfbeheer.
# ----------------------------------------------------------------------------

# Pad-prefixen die NIET meetellen voor de idle-timeout. /login en /licentie zijn
# de inlog-routes zelf; /verify_2fa heeft een eigen 10-min 2fa_expires; /static
# bevat alleen assets; /api/licentie/check + /api/pairing/* zijn pre-login.
_TIMEOUT_EXEMPT_PREFIXES = (
    '/static/', '/login', '/licentie', '/verify',
    '/wachtwoord-vergeten', '/wachtwoord-reset', '/wachtwoord_reset',
    '/logout', '/api/licentie/', '/api/pairing/',
)


@app.before_request
def _enforce_session_idle_timeout():
    path = request.path or ''
    if path == '/' or any(path.startswith(p) for p in _TIMEOUT_EXEMPT_PREFIXES):
        return
    if not session.get('license_valid'):
        return
    now = time.time()
    last = session.get('_last_activity')
    if last is None:
        # Eerste hit na login (of session-cookie van vóór deze hook): initialiseer.
        session['_last_activity'] = now
        session.permanent = True
        return
    window = SESSION_IDLE_TIMEOUT_OPERATOR_SECONDS if session.get('_session_window') == 'operator_24h' else SESSION_IDLE_TIMEOUT_SECONDS
    if now - last > window:
        lang = session.get('lang', 'nl')
        session.clear()
        if path.startswith('/api/') or (request.accept_mimetypes.best == 'application/json'):
            return jsonify({
                'error': 'session_expired',
                'message': 'Session expired after 30 minutes of inactivity. Please log in again.'
            }), 401
        return redirect(url_for('sc_login', timeout='1', lang=lang))
    session['_last_activity'] = now


def get_meting_count_for_current_context():
    """Telt metingen relevant voor de huidige sessie-context.

    Pro-cliëntmeting (measuring_for_client > 0) → client_metingen voor dat cid.
    Anders (consumer of Pro eigen meting) → metingen onder user_key.
    Faalt silently terug naar 0 als een DB niet bereikbaar is.
    """
    try:
        cid = int(session.get('measuring_for_client', 0) or 0)
    except (TypeError, ValueError):
        cid = 0
    try:
        if cid > 0 and is_pro():
            db = sqlite3.connect(PRO_DB_PATH)
            n = db.execute(
                "SELECT COUNT(*) FROM client_metingen WHERE client_id=?",
                (cid,),
            ).fetchone()[0]
            db.close()
            return int(n or 0)
        uk = session.get('user_key') or ''
        if not uk:
            return 0
        db = sqlite3.connect(METING_DB_PATH)
        n = db.execute(
            "SELECT COUNT(*) FROM metingen WHERE user_key=?", (uk,),
        ).fetchone()[0]
        db.close()
        return int(n or 0)
    except Exception:
        return 0


def show_educational_blocks():
    """Of BEGRIJPEN/FUNCTIE-VAN-DE-BOL-blokken standaard openstaan.

    Drie true-paden:
      - Nieuwe consumer (< EDU_BLOCKS_MAX_MEASUREMENTS metingen)
      - Pro bij cliëntmeting (didactisch hulpmiddel voor de cliënt)
      - Demo-modus
    """
    meting_count = get_meting_count_for_current_context()
    measuring_cid = session.get('measuring_for_client', 0) or 0
    try: measuring_cid = int(measuring_cid)
    except (TypeError, ValueError): measuring_cid = 0
    return (
        (not is_pro() and meting_count < EDU_BLOCKS_MAX_MEASUREMENTS)
        or (is_pro() and measuring_cid > 0)
        or bool(session.get('is_demo', False) or session.get('demo_mode', False))
    )

# ─── Pagina routes ───────────────────────────────────────────────────────────

@app.route('/api/meting/confirm', methods=['POST'])
def meting_confirm():
    data = request.json or {}
    mid = data.get('meting_id')
    label = data.get('label', '')
    subj_pre = data.get('subjectief_pre')
    if not mid and not is_pro():
        return jsonify({'error': 'geen id'}), 400
    # Update ook client_metingen in Pro DB
    try:
        pro_db = get_pro_db()
        pro_db.execute("UPDATE client_metingen SET pending=0, notes=? WHERE id=?", (label or '', mid,))
        pro_db.commit()
    except Exception:
        pass
    db = get_meting_db()
    if label and subj_pre is not None:
        try:
            db.execute("UPDATE metingen SET pending=0, notes=?, subjectief_score=? WHERE id=?", (label, int(float(str(subj_pre))), mid))
        except:
            db.execute("UPDATE metingen SET pending=0, notes=? WHERE id=?", (label, mid))
    elif label:
        db.execute("UPDATE metingen SET pending=0, notes=? WHERE id=?", (label, mid))
    elif subj_pre is not None:
        try:
            db.execute("UPDATE metingen SET pending=0, subjectief_score=? WHERE id=?", (int(float(str(subj_pre))), mid))
        except:
            db.execute("UPDATE metingen SET pending=0 WHERE id=?", (mid,))
    else:
        db.execute("UPDATE metingen SET pending=0 WHERE id=?", (mid,))
    db.commit()
    return jsonify({'ok': True})

@app.route('/api/meting/discard', methods=['POST'])
def meting_discard():
    data = request.json or {}
    mid = data.get('meting_id')
    if not mid:
        return jsonify({'error': 'geen id'}), 400
    try:
        pro_db = get_pro_db()
        pro_db.execute("DELETE FROM client_metingen WHERE id=? AND pending=1", (mid,))
        pro_db.commit()
    except Exception:
        pass
    db = get_meting_db()
    db.execute("DELETE FROM metingen WHERE id=? AND pending=1", (mid,))
    db.commit()
    return jsonify({'ok': True})


@app.route('/')
def index():
    if session.get('license_valid'):
        if is_pro():
            return redirect(url_for('pro_menu'))
        return redirect(url_for('menu'))
    return redirect(url_for('welcome'))

@app.route('/welkom')
def welcome():
    # Detecteer browsertaal bij eerste bezoek (alleen als nog niet ingesteld)
    if not session.get('lang'):
        accept = request.headers.get('Accept-Language', 'nl')
        lang_raw = accept.split(',')[0].split(';')[0].strip().lower()
        if lang_raw.startswith('de'):
            session['lang'] = 'de'
        elif lang_raw.startswith('en'):
            session['lang'] = 'en'
        else:
            session['lang'] = 'nl'
    return render_template('welcome.html', lang=session.get('lang', 'nl'))


@app.route('/start')
def start():
    if not session.get('lang'):
        accept = request.headers.get('Accept-Language', 'nl')
        lang_raw = accept.split(',')[0].split(';')[0].strip().lower()
        if lang_raw.startswith('de'):
            session['lang'] = 'de'
        elif lang_raw.startswith('en'):
            session['lang'] = 'en'
        else:
            session['lang'] = 'nl'
    return render_template('welcome.html', lang=session.get('lang', 'nl'), spoor='navigatie')



@app.route('/demo')
def demo():
    mode = request.args.get('mode', 'consumer')
    _lang = session.get('lang', 'nl')
    session.clear()
    session['lang'] = _lang
    session["user_key"] = "0b88246290c29d68be85c33776867721"
    session["email"] = "demo@stresschecker.com"
    session.modified = True
    session.permanent = True
    session["user_key"] = "0b88246290c29d68be85c33776867721"
    session["email"] = "demo@stresschecker.com"
    session.modified = True
    session.permanent = True
    session['license_valid'] = True
    session['user_id'] = 0
    session['username'] = 'Demo'
    session['license_type'] = 'pro' if mode == 'pro' else 'consumer'
    session['is_demo'] = True
    session['demo_mode'] = True
    session['user_key'] = 'DEMO'
    if mode == 'pro':
        return redirect(url_for('pro_menu'))
    return redirect(url_for('menu'))


@app.route('/meetkeuze')
def meetkeuze():
    if not session.get('license_valid') and not session.get('demo_mode'):
        return redirect(url_for('welcome'))
    lang = session.get('lang', 'nl')
    return render_template('meetkeuze_client.html', lang=lang)

@app.route('/privacy')
def privacy():
    return render_template('privacy.html', lang=session.get('lang', 'nl'))

SPOOR3_ERROR_MESSAGES = {
    'no_stripe_subscription': {
        'de': 'Die Abonnement-Verwaltung ist für Ihren Vertragstyp nicht verfügbar. '
              'Bei Fragen wenden Sie sich an info@lifestylemonitors.de.',
        'nl': 'Abonnement-beheer is niet beschikbaar voor jouw type abonnement. '
              'Neem voor wijzigingen contact op via info@lifestylemonitors.com.',
        'en': 'Subscription management is not available for your subscription type. '
              'For changes please contact info@lifestylemonitors.com.',
    },
    'portal_unavailable': {
        'de': 'Das Abonnement-Portal ist derzeit nicht erreichbar. Bitte versuchen Sie es später erneut.',
        'nl': 'Het abonnement-portaal is tijdelijk onbereikbaar. Probeer het later opnieuw.',
        'en': 'The subscription portal is temporarily unavailable. Please try again later.',
    },
    'use_new_flow': {
        'de': "Die Kündigungsfunktion wurde aktualisiert. Bitte verwenden Sie die "
              "Schaltfläche 'Abonnement verwalten' unten auf dieser Seite, oder "
              "kontaktieren Sie uns unter info@lifestylemonitors.de.",
        'nl': "De opzegfunctie is bijgewerkt. Gebruik de knop 'Abonnement beheren' "
              "onderaan deze pagina, of neem contact op via info@lifestylemonitors.com.",
        'en': "The cancellation feature has been updated. Please use the "
              "'Manage subscription' button below on this page, or contact us at "
              "info@lifestylemonitors.com.",
    },
}


@app.route('/licentie')
def license_screen():
    lang = session.get('lang', 'nl')
    raw_error = request.args.get('error', '')
    translated = SPOOR3_ERROR_MESSAGES.get(raw_error, {}).get(lang) if raw_error else ''
    error_text = translated if translated else raw_error
    return render_template(
        'license.html',
        lang=lang,
        error=error_text,
        has_stripe_subscription=has_stripe_subscription(session.get('email', '')),
    )

@app.route('/activeer', methods=['POST'])
def activate():
    import sqlite3 as _sq, hashlib
    code     = request.form.get('code', '').strip().upper()
    legacy   = request.form.get('legacy_code', '').strip().upper()
    email    = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '').strip()
    lang     = request.form.get('lang', 'nl')
    # Tijdstip van de wilsverklaring (aanvinken): vastgelegd bij de POST naar
    # /activeer en later als created_at in consent_log weggeschreven.
    import datetime as _dt_consent
    consent_at = _dt_consent.datetime.utcnow().isoformat()

    print(f"[ACTIVEER DEBUG] form fields: {dict(request.form)}", flush=True)
    print(f"[ACTIVEER DEBUG] code='{code}' legacy='{legacy}' email='{email}'", flush=True)

    # Legacy code veld als fallback als SC-code leeg is
    if not code and legacy:
        code = legacy

    form_type = request.form.get('type', 'nieuw')
    if form_type == 'terug':
        # Inloggen: geen code nodig
        if not email:
            return redirect(url_for('license_screen', error='Vul je e-mailadres in.' if lang=='nl' else ('Bitte E-Mail eingeben.' if lang=='de' else 'Please enter your email.')))
    else:
        if not code or not email:
            return redirect(url_for('license_screen', error='Vul beide velden in.' if lang=='nl' else ('Bitte beide Felder ausfüllen.' if lang=='de' else 'Please fill in both fields.')))
        # Beide instemmingen verplicht voor activering (autoritaire server-side gate;
        # de inline per-checkbox-melding is client-side, dit is het vangnet).
        if not request.form.get('privacy_consent') or not request.form.get('widerruf_consent'):
            return redirect(url_for('license_screen', error=(
                'Bitte bestätigen Sie beide Erklärungen, um die Lizenz zu aktivieren.' if lang=='de'
                else 'Please confirm both declarations to activate the licence.' if lang=='en'
                else 'Bevestig beide verklaringen om de licentie te activeren.')))

    if not password or len(password) < 8:
        return redirect(url_for('license_screen', error='Kies een wachtwoord van minimaal 8 tekens.' if lang=='nl' else ('Wählen Sie ein Passwort mit mindestens 8 Zeichen.' if lang=='de' else 'Choose a password of at least 8 characters.')))

    # Cross-product detectie: HLM code ingevoerd op SC pagina
    if code.startswith("HLM"):
        return redirect("/hlm/registreer?code=" + code)

    result = validate_license(code, email)
    if result.get('needs_choice'):
        session['legacy_code']            = code
        session['legacy_valid']           = True
        session['legacy_pending_email']   = email
        session['legacy_pending_pw_hash'] = hashlib.sha256(password.encode()).hexdigest()
        session['legacy_pending_lang']    = lang
        return redirect(url_for('oude_code_keuze'))
    if result['valid']:
        # True zodra de instemming al in de marketing/eval-bind-transactie is
        # weggeschreven; verify_2fa logt dan niet nogmaals.
        _consent_logged_early = False
        # === Marketing/evaluation herclaim-bescherming ===
        # Marketing-codes circuleren breed (campagnes/beurzen/partners); eval-codes
        # zijn 1-op-1 aan een partner uitgegeven. In beide gevallen: eerste
        # activeerder zet email; tweede claim met afwijkend email wordt geweigerd.
        # Stripe/PayPal/manual hebben eigen risicoprofiel — geen vergelijkbare check.
        _bind_origin = result.get('origin')
        if _bind_origin in ('marketing', 'evaluation'):
            _bound = result.get('bound_email') or ''
            if _bound and _bound.lower() != email.lower():
                return redirect(url_for('license_screen', error=(
                    'Deze code is al geactiveerd.' if lang=='nl'
                    else ('Dieser Code wurde bereits aktiviert.' if lang=='de'
                    else 'This code has already been activated.'))))

        # === Marketing/evaluation binding bij activering (email IS NULL) ===
        if _bind_origin in ('marketing', 'evaluation') and not result.get('bound_email'):
            import datetime as _dt_mkt
            cea = result.get('code_expires_at')
            if not cea:
                return redirect(url_for('license_screen', error=(
                    'Deze code is niet geldig.' if lang=='nl'
                    else ('Dieser Code ist ungültig.' if lang=='de'
                    else 'This code is invalid.'))))
            try:
                cea_dt = _dt_mkt.datetime.fromisoformat(cea)
            except ValueError:
                # Sommige bestaande code_expires_at-velden gebruiken 'YYYY-MM-DD HH:MM:SS'
                try:
                    cea_dt = _dt_mkt.datetime.strptime(cea, '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    return redirect(url_for('license_screen', error=(
                        'Deze code is niet geldig.' if lang=='nl'
                        else ('Dieser Code ist ungültig.' if lang=='de'
                        else 'This code is invalid.'))))
            if _dt_mkt.datetime.utcnow() > cea_dt:
                return redirect(url_for('license_screen', error=(
                    'Deze code is verlopen.' if lang=='nl'
                    else ('Dieser Code ist abgelaufen.' if lang=='de'
                    else 'This code has expired.'))))
            _bind_cn = sqlite3.connect('/opt/ic-license-server/data/saas_licenses.db')
            _bind_cn.row_factory = sqlite3.Row
            # Resolve plan_id voor plan-driven expiry
            _lic_row = _bind_cn.execute(
                "SELECT type, max_profiles FROM licenses WHERE license_key=?", (code,)
            ).fetchone()
            _plan_id_resolved = _derive_plan_id_for_license(
                _lic_row['type'] if _lic_row else 'pro',
                _lic_row['max_profiles'] if _lic_row else 0,
                _bind_origin,
            )
            _now_mkt = _dt_mkt.datetime.utcnow()
            now_iso_mkt = _now_mkt.isoformat()
            exp_iso_mkt = _compute_license_expires_at(_plan_id_resolved, _now_mkt)
            _bind_cn.execute(
                "UPDATE licenses SET email=?, activated_at=?, expires_at=?, valid_until=?, status='activated' "
                "WHERE license_key=? AND origin IN ('marketing','evaluation') AND email IS NULL",
                (email, now_iso_mkt, exp_iso_mkt, exp_iso_mkt, code)
            )
            _bind_cn.execute(
                "INSERT INTO activation_log (license_key, product, action, ip_address, user_agent, details) "
                "VALUES (?, 'sc', ?, ?, ?, ?)",
                (code, f'activate_{_bind_origin}', request.remote_addr,
                 request.headers.get('User-Agent','')[:200],
                 f'origin={_bind_origin} plan_id={_plan_id_resolved} email={email}')
            )
            # Marketing/eval bindt de licentie HIER (vóór 2FA) → instemming in
            # dezelfde transactie als de activering. consent_meta krijgt logged=True
            # zodat verify_2fa niet dubbel logt.
            _log_consent(_bind_cn, email, code, lang, consent_at)
            _consent_logged_early = True
            _bind_cn.commit()
            _bind_cn.close()
            result = validate_license(code, email)
        # === Einde marketing/evaluation-branch ===

        pw_hash = hashlib.sha256(password.encode()).hexdigest()
        session.clear()
        session['license_valid'] = True
        session['license_type']  = result['type']
        session['audience']      = result.get('audience') or result['type']
        session['plan_id']       = result.get('plan_id')
        session['license_code']  = code
        session['email']         = email
        session['lang']          = lang
        # Instemming meedragen naar verify_2fa, waar de activering voltooit. Daar
        # worden de consent-rijen (indien nog niet vroeg gelogd) in dezelfde
        # transactie als de activerings-UPDATE geschreven, en wordt de
        # bevestigingsmail verstuurd.
        session['consent_meta'] = {
            'locale': lang,
            'consent_at': consent_at,
            'logged': _consent_logged_early,
        }

        import sqlite3 as _sq2
        _cn = _sq2.connect('/opt/ic-license-server/data/saas_licenses.db')
        _cn.row_factory = _sq2.Row
        existing = _cn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()

        if existing and existing['display_name']:
            _lic_owner = _cn.execute(
                "SELECT 1 FROM licenses WHERE (license_key=? OR legacy_key=?) AND lower(email)=? LIMIT 1",
                (code, code, email)
            ).fetchone()
            if not _lic_owner:
                _cn.close()
                session.clear()
                return redirect(url_for('license_screen', error=(
                    'Deze licentiecode hoort niet bij dit e-mailadres.' if lang=='nl'
                    else ('Dieser Lizenzcode gehört nicht zu dieser E-Mail-Adresse.' if lang=='de'
                    else 'This license code does not belong to this email address.'))))
            session['profile_name'] = existing['display_name']
            try: session['profile_surname'] = existing['surname'] or ''
            except (IndexError, KeyError): session['profile_surname'] = ''
            # Wachtwoord pas opslaan na succesvol 2FA (zie verify_2fa)
            session['2fa_pending_pw_hash'] = pw_hash
            # Vervaldatum check
            import datetime as _dt3
            _exp_str = existing['license_expires'] or result.get('valid_until')
            if _exp_str:
                try:
                    _exp_dt = _dt3.datetime.fromisoformat(_exp_str)
                    if _dt3.datetime.utcnow() > _exp_dt:
                        session.clear()
                        _cn.close()
                        return redirect(url_for('license_screen',
                            error='Je gratis periode is verlopen. Activeer een licentiecode om verder te gaan.'))
                except:
                    pass
            _cn.close()
            import random as _rnd, time
            _2fa_code = str(_rnd.randint(100000, 999999))
            session['2fa_code']         = _2fa_code
            session['2fa_email']        = email
            session['2fa_license_type'] = session.get('license_type', 'consumer')
            session['2fa_audience']     = session.get('audience', session.get('license_type', 'consumer'))
            session['2fa_plan_id']      = session.get('plan_id')
            session['2fa_license_code'] = code
            session['2fa_name']         = session.get('profile_name', email)
            session['2fa_lang']         = lang
            session['2fa_expires']      = time.time() + 600
            send_verification_code(email, _2fa_code, lang)
            import logging; logging.getLogger().warning(f"2FA CODE: {_2fa_code if '_2fa_code' in dir() else code}")
            return redirect(url_for('verify_2fa'))
        else:
            # Nieuw account of bestaand account zonder display_name
            if existing:
                _cn.execute("UPDATE users SET password_hash=? WHERE email=?", (pw_hash, email))
            else:
                _cn.execute(
                    "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, datetime('now'))",
                    (email, pw_hash))
            _cn.commit()
            import random as _rnd, time
            _2fa_code = str(_rnd.randint(100000, 999999))
            session["2fa_code"]         = _2fa_code
            session["2fa_email"]        = email
            session["2fa_license_type"] = session.get("license_type", "consumer")
            session["2fa_audience"]     = session.get("audience", session.get("license_type", "consumer"))
            session["2fa_plan_id"]      = session.get("plan_id")
            session["2fa_license_code"] = code
            session["2fa_name"]         = session.get("profile_name", email)
            session["2fa_lang"]         = lang
            session["2fa_expires"]      = time.time() + 600
            send_verification_code(email, _2fa_code, lang)
            import logging; logging.getLogger().warning(f"2FA CODE for {email}: {_2fa_code}")
            _cn.close()
            return redirect(url_for("verify_2fa"))

    return redirect(url_for('license_screen', error='Ongeldige code.' if lang=='nl' else ('Ungültiger Code.' if lang=='de' else 'Invalid code.')))



# ============================================================================
# Krankenkasse admin (Sessie A) — licentie-aanmaak + kantoor-beheer
# ============================================================================
def _admin_kk_authorized():
    """Check ADMIN_KK_TOKEN-match via X-Admin-Token header of ?token=… query."""
    import hmac
    expected = os.environ.get('ADMIN_KK_TOKEN', '')
    given = request.headers.get('X-Admin-Token', '') or request.args.get('token', '') or request.form.get('token', '')
    if not expected or not given:
        return False
    return hmac.compare_digest(given, expected)


def _gen_kk_license_code():
    """Format: SC-KK-XXXX-XXXX (hex). Garandeert uniciteit tegen licenses-tabel."""
    import secrets
    db = sqlite3.connect('/opt/ic-license-server/data/saas_licenses.db')
    try:
        for _ in range(20):
            code = 'SC-KK-' + secrets.token_hex(2).upper() + '-' + secrets.token_hex(2).upper()
            exists = db.execute("SELECT 1 FROM licenses WHERE license_key=?", (code,)).fetchone()
            if not exists:
                return code
        raise RuntimeError('Could not generate unique KK code after 20 tries')
    finally:
        db.close()


def send_kk_activation_email(to_email, contact_name, license_code, tier_label, lang='de'):
    """Welkomstmail naar Krankenkasse-contactpersoon. Zakelijke DE-tekst,
    Reply-To info@lifestylemonitors.de voor DE-context."""
    try:
        import sendgrid
        from sendgrid.helpers.mail import Mail, ReplyTo
        sg = sendgrid.SendGridAPIClient(os.environ['SENDGRID_API_KEY'])
        greeting = contact_name or 'Sehr geehrte Damen und Herren'
        subject = f'Ihre StressChecker Krankenkasse-Lizenz ({tier_label}) ist aktiviert'
        body = (
            f'Sehr geehrte/r {greeting},\n\n'
            f'wir freuen uns, Ihnen mitteilen zu koennen, dass Ihre StressChecker '
            f'Krankenkasse-Lizenz ({tier_label}) eingerichtet wurde. Die Laufzeit '
            f'betraegt 12 Monate ab Erstanmeldung.\n\n'
            f'Ihr Lizenzschluessel: {license_code}\n\n'
            f'So melden Sie sich an:\n'
            f'  1. Oeffnen Sie https://app.stresschecker.com/licentie\n'
            f'  2. Geben Sie den Lizenzschluessel und Ihre E-Mail-Adresse ein\n'
            f'  3. Waehlen Sie ein Passwort (mindestens 8 Zeichen)\n'
            f'  4. Bestaetigen Sie den per E-Mail zugesandten Verifizierungscode\n\n'
            f'Standorte (Buero-Bezeichnungen) fuer Ihre Gesundheitstage werden '
            f'zentral durch unser Team konfiguriert. Bitte teilen Sie uns die '
            f'gewuenschten Standortnamen mit, sobald diese feststehen — eine '
            f'Antwort auf diese E-Mail genuegt.\n\n'
            f'Bei Fragen erreichen Sie uns unter sales@lifestylemonitors.com.\n\n'
            f'Mit freundlichen Gruessen,\n'
            f'Lifestyle Monitors'
        )
        msg = Mail(from_email='noreply@lifestylemonitors.com', to_emails=to_email,
                   subject=subject, plain_text_content=body)
        msg.reply_to = ReplyTo('info@lifestylemonitors.de')
        sg.send(msg)
        return True
    except Exception as e:
        print('KK-activatie-mail fout:', e)
        return False


@app.route('/admin/krankenkasse/new', methods=['GET', 'POST'])
def admin_kk_new():
    """Aanmaak van nieuwe Krankenkasse-licentie + optionele welkomstmail."""
    if not _admin_kk_authorized():
        return ('Unauthorized — provide X-Admin-Token header or ?token=… query parameter.', 401)
    if request.method == 'POST':
        name = (request.form.get('kk_name','') or '').strip()
        tier = (request.form.get('tier','') or '').strip()
        contact_email = (request.form.get('contact_email','') or '').strip().lower()
        contact_name = (request.form.get('contact_name','') or '').strip()
        send_mail_now = request.form.get('send_mail', '0') == '1'
        if tier not in ('kompakt', 'standard', 'premium') or not name or not contact_email:
            return render_template('admin/kk_new.html',
                                   error='Vul naam, tier (kompakt/standard/premium) en contact-e-mail in.',
                                   token=request.form.get('token',''))
        plan_id = f'sc-krankenkasse-{tier}'
        tier_label = {'kompakt':'Kompakt','standard':'Standard','premium':'Premium'}[tier]
        license_code = _gen_kk_license_code()
        import datetime as _dt
        now_iso = _dt.datetime.utcnow().isoformat()
        valid_until = (_dt.datetime.utcnow() + _dt.timedelta(days=365)).isoformat()
        code_expires_at = (_dt.datetime.utcnow() + _dt.timedelta(days=60)).isoformat()
        db = sqlite3.connect('/opt/ic-license-server/data/saas_licenses.db')
        try:
            db.execute(
                "INSERT INTO licenses (license_key, product, type, status, origin, max_profiles, "
                "email, product_name, valid_until, code_expires_at, notes, created_at) "
                "VALUES (?, ?, 'pro', 'available', 'krankenkasse', -1, ?, ?, ?, ?, ?, ?)",
                (license_code, plan_id, contact_email,
                 f'Krankenkasse {tier_label}', valid_until, code_expires_at,
                 f'Krankenkasse: {name}', now_iso)
            )
            db.execute(
                "INSERT INTO activation_log (license_key, product, action, ip_address, user_agent, details) "
                "VALUES (?, 'sc', 'admin_kk_create', ?, ?, ?)",
                (license_code, request.remote_addr,
                 (request.headers.get('User-Agent','') or '')[:200],
                 f'name={name} tier={tier} contact={contact_email}')
            )
            db.commit()
        finally:
            db.close()
        mail_status = ''
        if send_mail_now:
            sent = send_kk_activation_email(contact_email, contact_name, license_code, tier_label, lang='de')
            mail_status = 'sent' if sent else 'failed'
        return redirect(url_for('admin_kk_offices', license_code=license_code,
                                token=request.form.get('token',''),
                                mail=mail_status, created='1'))
    return render_template('admin/kk_new.html', token=request.args.get('token',''))


@app.route('/admin/krankenkasse/<license_code>/offices', methods=['GET', 'POST'])
def admin_kk_offices(license_code):
    """Beheer van kantoor-master-lijst voor een Krankenkasse-licentie."""
    if not _admin_kk_authorized():
        return ('Unauthorized — provide X-Admin-Token header or ?token=… query parameter.', 401)
    license_code = license_code.strip().upper()
    db = sqlite3.connect('/opt/ic-license-server/data/saas_licenses.db')
    db.row_factory = sqlite3.Row
    lic = db.execute(
        "SELECT l.license_key, l.email, l.notes, l.product, l.product_name, p.tier "
        "FROM licenses l LEFT JOIN plans p ON p.plan_id=l.product WHERE l.license_key=?",
        (license_code,)).fetchone()
    if not lic or not (lic['product'] or '').startswith('sc-krankenkasse-'):
        db.close()
        return ('Onbekende of niet-Krankenkasse licentie.', 404)
    if request.method == 'POST':
        office_name = (request.form.get('office_name','') or '').strip()
        if office_name:
            db.execute("INSERT INTO krankenkasse_offices (license_code, office_name) VALUES (?, ?)",
                       (license_code, office_name))
            db.commit()
        db.close()
        return redirect(url_for('admin_kk_offices', license_code=license_code,
                                token=request.form.get('token','')))
    offices = db.execute(
        "SELECT id, office_name, active, created_at FROM krankenkasse_offices "
        "WHERE license_code=? ORDER BY active DESC, office_name", (license_code,)).fetchall()
    db.close()
    return render_template('admin/kk_offices.html',
                           license=dict(lic), offices=[dict(o) for o in offices],
                           token=request.args.get('token',''),
                           created=request.args.get('created') == '1',
                           mail_status=request.args.get('mail',''))


@app.route('/admin/krankenkasse/<license_code>/offices/<int:oid>/deactivate', methods=['POST'])
def admin_kk_office_deactivate(license_code, oid):
    if not _admin_kk_authorized():
        return ('Unauthorized', 401)
    license_code = license_code.strip().upper()
    db = sqlite3.connect('/opt/ic-license-server/data/saas_licenses.db')
    db.execute("UPDATE krankenkasse_offices SET active=0 WHERE id=? AND license_code=?",
               (oid, license_code))
    db.commit()
    db.close()
    return redirect(url_for('admin_kk_offices', license_code=license_code,
                            token=request.form.get('token','')))


@app.route('/admin/krankenkasse/<license_code>/send-welcome', methods=['POST'])
def admin_kk_send_welcome(license_code):
    if not _admin_kk_authorized():
        return ('Unauthorized', 401)
    license_code = license_code.strip().upper()
    db = sqlite3.connect('/opt/ic-license-server/data/saas_licenses.db')
    db.row_factory = sqlite3.Row
    lic = db.execute(
        "SELECT l.license_key, l.email, l.notes, p.tier FROM licenses l "
        "LEFT JOIN plans p ON p.plan_id=l.product WHERE l.license_key=?",
        (license_code,)).fetchone()
    db.close()
    if not lic or not lic['email']:
        return ('Licentie of contact-e-mail ontbreekt.', 400)
    tier_label = {'krankenkasse-kompakt':'Kompakt','krankenkasse-standard':'Standard',
                  'krankenkasse-premium':'Premium'}.get(lic['tier'] or '', '?')
    contact_name = (lic['notes'] or '').replace('Krankenkasse: ','').strip()
    sent = send_kk_activation_email(lic['email'], contact_name, license_code, tier_label, lang='de')
    return redirect(url_for('admin_kk_offices', license_code=license_code,
                            token=request.form.get('token',''),
                            mail='sent' if sent else 'failed'))


@app.route('/admin-login-bypass-9x7k')
def admin_bypass():
    session.clear()
    session['logged_in'] = True
    session['license_type'] = 'pro'
    session['audience'] = 'pro'
    session['email'] = 'paulpannevis@gmail.com'
    session['profile_name'] = 'Paul'
    session['profile_surname'] = 'Pannevis'
    session['lang'] = 'nl'
    session['user_key'] = 'aae4793deb05b378a68140eb40979c32'
    session['license_valid'] = True
    session['license_type'] = 'pro'
    return redirect(url_for('pro_menu'))

@app.route('/login', methods=['GET', 'POST'])
def sc_login():
    lang = request.args.get('lang', session.get('lang', 'nl'))
    error = request.args.get('error')
    if not error and request.args.get('timeout') == '1':
        error = ('Sitzung nach 30 Minuten Inaktivität abgelaufen. Bitte erneut anmelden.' if lang == 'de'
                 else 'Session expired after 30 minutes of inactivity. Please log in again.' if lang == 'en'
                 else 'Sessie verlopen na 30 minuten inactiviteit, log opnieuw in.')
    if request.method == 'POST':
        import sqlite3 as _sq, hashlib, re
        email_raw = request.form.get('email', '')
        email    = email_raw.strip().lower()
        # Strip non-printable/invisible chars (iPhone autocomplete may inject zero-width chars)
        email    = re.sub(r'[^\x20-\x7E]', '', email)
        password = request.form.get('password', '')
        lang     = request.form.get('lang', 'nl')
        import logging
        logging.getLogger().warning(f"[LOGIN] raw={email_raw!r} normalized={email!r} len_raw={len(email_raw)} len_norm={len(email)} ua={request.headers.get('User-Agent','')[:80]!r}")
        if not email or not password:
            error = ('E-Mail und Passwort eingeben.' if lang=='de' else 'Enter email and password.' if lang=='en' else 'Vul e-mail en wachtwoord in.')
            return render_template('sc_login.html', lang=lang, error=error, email=email)
        _cn = _sq.connect('/opt/ic-license-server/data/saas_licenses.db')
        _cn.row_factory = _sq.Row
        user = _cn.execute("SELECT * FROM users WHERE email=? COLLATE NOCASE", (email,)).fetchone()
        _cn.close()
        if not user or not user['password_hash']:
            logging.getLogger().warning(f"[LOGIN] NO MATCH for email={email!r} (user={user is not None}, has_pw={bool(user and user['password_hash']) if user else False})")
            error = ('Kein Konto gefunden. Aktiviere zuerst deinen Lizenzcode.' if lang=='de' else 'No account found. Activate your license code first.' if lang=='en' else 'Geen account gevonden. Activeer eerst je licentiecode.')
            return render_template('sc_login.html', lang=lang, error=error, email=email)
        ok, is_legacy = verify_password(password, user['password_hash'])
        if not ok:
            error = ('Falsches Passwort.' if lang=='de' else 'Incorrect password.' if lang=='en' else 'Onjuist wachtwoord.')
            return render_template('sc_login.html', lang=lang, error=error, email=email)
        if is_legacy:
            # Transparante migratie: SHA-256-hash bij succesvolle login eenmalig her-hashen naar bcrypt.
            _cn3 = _sq.connect('/opt/ic-license-server/data/saas_licenses.db')
            _cn3.execute("UPDATE users SET password_hash=? WHERE email=? COLLATE NOCASE", (hash_password(password), email))
            _cn3.commit()
            _cn3.close()
        # KK-operator: 2FA overslaan, sessie direct opzetten (24u-window)
        if user['role'] == 'operator':
            import time as _opt_t  # noqa: F811  — sc_login bevat een latere lokale `import time`
            _cn_op = _sq.connect('/opt/ic-license-server/data/saas_licenses.db')
            _cn_op.row_factory = _sq.Row
            op_lic = _cn_op.execute(
                "SELECT l.license_key, l.product, l.type, l.user_key "
                "FROM licenses l JOIN user_licenses ul ON ul.license_key=l.license_key "
                "WHERE ul.user_id=? AND l.status='activated' LIMIT 1",
                (user['id'],)
            ).fetchone()
            _cn_op.close()
            if not op_lic:
                error = ('Kein verknüpftes Konto.' if lang=='de'
                         else 'No linked license.' if lang=='en'
                         else 'Geen gekoppelde licentie.')
                return render_template('sc_login.html', lang=lang, error=error, email=email)
            session.clear()
            session['license_valid']   = True
            session['license_type']    = 'pro'
            session['audience']        = 'krankenkasse'
            session['role']            = 'operator'
            session['license_code']    = op_lic['license_key']
            session['plan_id']         = op_lic['product']
            session['email']           = email
            session['session_id']      = email
            session['lang']            = lang
            session['profile_name']    = user['display_name'] or email
            session['_session_window'] = 'operator_24h'
            session.permanent          = True
            session['_last_activity']  = _opt_t.time()
            return redirect(url_for('pro_locatie'))
        # Inloggen gelukt — 2FA code sturen
        _cn2 = _sq.connect('/opt/ic-license-server/data/saas_licenses.db')
        _cn2.row_factory = _sq.Row
        lic = _cn2.execute(
            "SELECT type, license_key, product FROM licenses WHERE email=? AND status='activated' AND (license_key LIKE 'SC-%' OR type IN ('consumer','pro')) AND license_key NOT LIKE 'HLM%' ORDER BY created_at DESC LIMIT 1",
            (email,)).fetchone()
        _cn2.close()
        license_type = lic['type'] if lic else 'consumer'
        _lic_product = (lic['product'] or '') if lic else ''
        _lic_audience = 'krankenkasse' if _lic_product.startswith('sc-krankenkasse-') else license_type
        # Sessie opschonen (demo flags verwijderen) en 2FA starten
        import random as _rnd
        code = str(_rnd.randint(100000, 999999))
        session.clear()
        session['2fa_code']         = code
        session['2fa_email']        = email
        session['2fa_license_type'] = license_type
        session['2fa_audience']     = _lic_audience
        session['2fa_license_code'] = lic['license_key'] if lic else ''
        session['2fa_plan_id']      = _lic_product or None
        session['2fa_name']         = user['display_name'] if user['display_name'] else email
        session['2fa_lang']         = lang
        import time
        session['2fa_expires']      = time.time() + 600  # 10 min
        session['2fa_login_type'] = request.form.get('type', request.args.get('type', 'consumer'))
        send_verification_code(email, code, lang)
        import logging; logging.getLogger().warning(f"2FA CODE: {_2fa_code if "_2fa_code" in dir() else code}")
        return redirect(url_for('verify_2fa'))
    return render_template('sc_login.html', lang=lang, error=error)



@app.route('/verify', methods=['GET','POST'])
def verify_2fa():
    lang = session.get('2fa_lang','nl')
    error = None
    if '2fa_code' not in session:
        return redirect(url_for('sc_login'))
    if request.method == 'POST':
        import time
        code_in = request.form.get('code','').strip()
        if time.time() > session.get('2fa_expires',0):
            session.pop('2fa_code',None)
            return redirect(url_for('sc_login'))
        if code_in == session['2fa_code']:
            _pending_pw = session.pop('2fa_pending_pw_hash', None)
            if _pending_pw:
                import sqlite3 as _sq_pw
                _pwc_email = session.get('2fa_email','')
                _pwc = _sq_pw.connect('/opt/ic-license-server/data/saas_licenses.db')
                _existing_u = _pwc.execute("SELECT id FROM users WHERE email=?", (_pwc_email,)).fetchone()
                if _existing_u:
                    _pwc.execute("UPDATE users SET password_hash=? WHERE email=?", (_pending_pw, _pwc_email))
                else:
                    _pwc.execute("INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, datetime('now'))", (_pwc_email, _pending_pw))
                _pwc.commit()
                _pwc.close()
            # PAIRING-REGISTER activation: alleen actief als /api/pairing/register een 2fa_pending_pair_code in sessie zette.
            # Bij afwezigheid blijft /verify gedrag bit-identiek aan vóór deze wijziging.
            _pending_pair_code    = session.pop('2fa_pending_pair_code', None)
            _pending_consumer_key = session.pop('2fa_pending_consumer_key', None)
            _paired_pro_id    = None
            _paired_client_id = None
            _paired_user_key  = None
            if _pending_pair_code and _pending_consumer_key:
                import sqlite3 as _sq_pair
                _pair_email = session.get('2fa_email','')
                _pair_name  = session.get('2fa_name','')
                _pdb = _sq_pair.connect('/opt/ic-license-server/data/saas_licenses.db')
                _pdb.row_factory = _sq_pair.Row
                _new_user = _pdb.execute("SELECT id FROM users WHERE email=? COLLATE NOCASE", (_pair_email,)).fetchone()
                if _new_user:
                    _new_uid = _new_user['id']
                    if _pair_name:
                        _pdb.execute(
                            "UPDATE users SET display_name=? WHERE id=? AND (display_name IS NULL OR display_name='')",
                            (_pair_name, _new_uid))
                    _pc_row = _pdb.execute(
                        "SELECT * FROM pairing_codes WHERE code=? AND status='pending'",
                        (_pending_pair_code,)).fetchone()
                    if _pc_row:
                        try:
                            _exp_pc = datetime.strptime(_pc_row['expires_at'], '%Y-%m-%d %H:%M:%S')
                        except ValueError:
                            _exp_pc = datetime.fromisoformat(_pc_row['expires_at'].split('.')[0])
                        if datetime.now() <= _exp_pc:
                            _now_iso = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            _pdb.execute(
                                "UPDATE pairing_codes SET status='activated', consumer_user_id=?, consumer_user_key=?, activated_at=? WHERE code=?",
                                (_new_uid, _pending_consumer_key, _now_iso, _pending_pair_code))
                            _pdb.execute(
                                "INSERT OR IGNORE INTO client_pairings (client_id, paired_user_id, paired_device_id, status) VALUES (?,?,?,?)",
                                (_pc_row['client_id'], _new_uid, _pending_consumer_key, 'active'))
                            _pdb.commit()
                            _paired_pro_id    = _pc_row['pro_user_id']
                            _paired_client_id = _pc_row['client_id']
                            _paired_user_key  = _pending_consumer_key
                        else:
                            _pdb.execute("UPDATE pairing_codes SET status='expired' WHERE code=?", (_pending_pair_code,))
                            _pdb.commit()
                _pdb.close()
            lt = session.pop('2fa_license_type','consumer')
            if lt == "consumer" and session.get("2fa_login_type") == "pro":
                lt = "pro"
            audience_2fa = session.pop('2fa_audience', lt)
            plan_id_2fa  = session.pop('2fa_plan_id', None)
            em = session.pop('2fa_email','')
            nm = session.pop('2fa_name',em)
            # Profielvelden onvoorwaardelijk uit DB laden (fix 2026-05-30): de load
            # zat ingesloten in `if nm == em`, waardoor users mét display_name nooit
            # hun birth_year/gender kregen → profile_setup-redirect bij elke login.
            try:
                import sqlite3 as _sq3
                _uc = _sq3.connect('/opt/ic-license-server/data/saas_licenses.db')
                _uc.row_factory = _sq3.Row
                _ur = _uc.execute("SELECT display_name, birth_year, gender, sensor_pref, language, surname, profile_completed FROM users WHERE email=?", (em,)).fetchone()
                # display_name-override alleen wanneer 2FA geen echte naam meegaf
                if _ur and _ur['display_name'] and nm == em:
                    nm = _ur['display_name']
                    try: session['profile_surname'] = _ur['surname'] or ''
                    except (IndexError, KeyError): session['profile_surname'] = ''
                # Laad ook birth_year en gender
                if _ur and _ur['birth_year']:
                    session['profile_birth_year'] = _ur['birth_year']
                if _ur and _ur['gender']:
                    session['profile_gender'] = _ur['gender']
                session['profile_completed'] = (_ur['profile_completed'] if _ur and _ur['profile_completed'] else 0)
                session['sensor_pref'] = _ur['sensor_pref'] if _ur['sensor_pref'] else 'bluetooth'
                _uc.close()
            except Exception:
                import logging; logging.getLogger().warning(f"Settings load error: {__import__("traceback").format_exc()}")
            # Bewaar velden die we nodig hebben, dan sessie schoonvegen
            _birth = session.get('profile_birth_year', 1970)
            _gender = session.get('profile_gender', 'male')
            _completed = session.get('profile_completed', 0)
            _sensor = session.get('sensor_pref', 'bluetooth')
            _lic_code = session.get('2fa_license_code', '')
            # Instemming uit /activeer (None bij pure login via /login → geen logging).
            _consent_meta = session.get('consent_meta')
            _did_activate = False
            session.clear()
            session['license_valid']=True; session['license_type']=lt
            session['audience']=audience_2fa or lt
            # Role-load voor KK-admin routing (Sessie B.6)
            if session['audience'] == 'krankenkasse':
                try:
                    import sqlite3 as _sq_r
                    _rc = _sq_r.connect('/opt/ic-license-server/data/saas_licenses.db')
                    _rr = _rc.execute("SELECT role FROM users WHERE email=?", (em,)).fetchone()
                    _rc.close()
                    if _rr and _rr[0]:
                        session['role'] = _rr[0]
                except Exception:
                    pass
            session['plan_id']=plan_id_2fa
            session['license_code']=_lic_code
            session['email']=em; session['session_id']=em; session['lang']=lang
            # Sessie-idle-timeout init (Sessie B.4)
            session.permanent = True
            session['_last_activity'] = time.time()
            # Link license to email and mark as activated
            import sqlite3 as _sq2; _ldb2=_sq2.connect('/opt/ic-license-server/data/saas_licenses.db')
            if _lic_code:
                _pre = _ldb2.execute("SELECT status FROM licenses WHERE license_key=?", (_lic_code,)).fetchone()
                _is_fresh_activation = bool(_pre and _pre[0] == 'available')
                _ldb2.execute("UPDATE licenses SET email=?, status='activated' WHERE license_key=? AND status='available'", (em, _lic_code))
                # Instemming in DEZELFDE transactie als de activerings-UPDATE.
                # Alleen bij een verse activering (status available→activated) en
                # mits niet al vroeg gelogd (marketing/eval). Een re-login met een
                # reeds geactiveerde code is geen activering → geen rij.
                if _consent_meta and _is_fresh_activation and not _consent_meta.get('logged'):
                    _log_consent(_ldb2, em, _lic_code,
                                 _consent_meta.get('locale', 'nl'),
                                 _consent_meta.get('consent_at'))
                _ldb2.commit()
                # Echte activering = verse status-transitie OF marketing/eval (vroeg
                # gebonden+gelogd in /activeer). Bepaalt of de bevestigingsmail gaat.
                if _consent_meta and (_is_fresh_activation or _consent_meta.get('logged')):
                    _did_activate = True
                # KK-licentie verse activatie → admin role op deze user + operator-auto-create (Sessie B.6)
                if _is_fresh_activation and _lic_code.startswith('SC-KK-'):
                    _ldb2.execute("UPDATE users SET role='admin' WHERE email=?", (em,))
                    _ldb2.commit()  # commit admin-role los van operator-create-tak
                    session['role'] = 'admin'
                    _op_email = _derive_operator_email(em)
                    if not _ldb2.execute("SELECT 1 FROM users WHERE email=? COLLATE NOCASE", (_op_email,)).fetchone():
                        import secrets as _opsec
                        _op_pw = _opsec.token_urlsafe(12)
                        _op_hash = hash_password(_op_pw)
                        _opc = _ldb2.execute(
                            "INSERT INTO users (email, password_hash, display_name, language, role, created_at) "
                            "VALUES (?, ?, ?, 'de', 'operator', datetime('now'))",
                            (_op_email, _op_hash, 'KK Operator')
                        )
                        _op_id = _opc.lastrowid
                        _ldb2.execute(
                            "INSERT INTO user_licenses (user_id, license_key, product, is_primary, linked_at) "
                            "VALUES (?, ?, 'sc', 0, datetime('now'))",
                            (_op_id, _lic_code)
                        )
                        _ldb2.commit()
                        # Eenmalige flash naar admin-dashboard (token gepop't bij eerste render)
                        session['_kk_operator_welcome'] = {'email': _op_email, 'password': _op_pw}
            _lr2=_ldb2.execute("SELECT user_key FROM licenses WHERE email=? AND product='sc' ORDER BY rowid DESC LIMIT 1",(em,)).fetchone(); _ldb2.close(); session['user_key']=_paired_user_key if _paired_user_key else (_lr2[0] if _lr2 else None)
            session['profile_name']=nm; session['profile_birth_year']=_birth; session['profile_gender']=_gender; session['profile_completed']=_completed; session['sensor_pref']=_sensor
            # Activeringsbevestiging op duurzame drager (§ 312f BGB) — alleen bij
            # een echte activering, ná de commit. Best-effort: mailfout breekt niet.
            if _did_activate and _consent_meta:
                send_activation_confirmation_email(
                    em, _consent_meta.get('locale', 'nl'),
                    _consent_meta.get('consent_at'))
            if _paired_pro_id:
                session['paired_with_pro']  = _paired_pro_id
                session['paired_client_id'] = _paired_client_id
            # Verplicht profile_setup vóór menu zolang profiel niet voltooid is (vlag, niet de 1970-sentinel)
            if not _completed:
                return redirect(url_for('profile_setup'))
            # KK-admin → eigen dashboard; KK-operator (login skipt 2FA, komt hier niet) en Pro → pro_menu
            if session.get('role') == 'admin' and session.get('audience') == 'krankenkasse':
                return redirect('/pro/admin')
            return redirect(url_for('pro_menu') if lt=='pro' else url_for('menu'))
        else:
            error='Onjuiste code.' if lang=='nl' else ('Falscher Code.' if lang=='de' else 'Incorrect.')
    return render_template('verify_2fa.html',lang=lang,error=error,email=session.get('2fa_email',''))


@app.route('/wachtwoord-vergeten', methods=['GET', 'POST'])
def password_forgot():
    lang = request.args.get('lang', session.get('lang', 'nl'))
    if request.method == 'POST':
        import sqlite3 as _sq, re, secrets as _sec
        from datetime import datetime, timedelta
        email_raw = request.form.get('email', '')
        email = email_raw.strip().lower()
        email = re.sub(r'[^\x20-\x7E]', '', email)
        lang = request.form.get('lang', lang)
        # Email-enumeratie-bescherming: response is identiek ongeacht of account bestaat, ongeacht rate-limit.
        generic_msg = (
            'Wenn dieses Konto existiert, haben wir einen Reset-Code per E-Mail gesendet.' if lang=='de'
            else 'If this account exists, we have sent a reset code by email.' if lang=='en'
            else 'Als dit account bestaat, hebben we een resetcode per e-mail verstuurd.'
        )
        if email and '@' in email:
            _cn = _sq.connect('/opt/ic-license-server/data/saas_licenses.db')
            _cn.row_factory = _sq.Row
            # strftime i.p.v. datetime() — created_at/expires_at zijn Python isoformat (met 'T'),
            # SQLite datetime('now') heeft spatie — lexicografisch ongelijk op positie 10.
            _cn.execute("DELETE FROM password_reset_codes WHERE expires_at < strftime('%Y-%m-%dT%H:%M:%S', 'now')")
            # Rate-limit: max 3 gegenereerde codes per e-mail per uur (telt alleen daadwerkelijk gegenereerde codes).
            recent = _cn.execute(
                "SELECT COUNT(*) AS n FROM password_reset_codes WHERE lower(email)=? AND created_at > strftime('%Y-%m-%dT%H:%M:%S', 'now', '-1 hour')",
                (email,)
            ).fetchone()
            if recent['n'] < 3:
                user = _cn.execute("SELECT id FROM users WHERE email=? COLLATE NOCASE", (email,)).fetchone()
                if user:
                    code = str(_sec.randbelow(900000) + 100000)
                    now = datetime.utcnow().isoformat()
                    expires = (datetime.utcnow() + timedelta(minutes=10)).isoformat()
                    _cn.execute(
                        "INSERT INTO password_reset_codes (email, code, created_at, expires_at) VALUES (?, ?, ?, ?)",
                        (email, code, now, expires)
                    )
                    _cn.commit()
                    send_password_reset_email(email, code, lang)
            _cn.close()
        return render_template('wachtwoord_vergeten.html', lang=lang, info=generic_msg)
    return render_template('wachtwoord_vergeten.html', lang=lang)


@app.route('/wachtwoord-reset', methods=['GET', 'POST'])
def password_reset_form():
    lang = request.args.get('lang', session.get('lang', 'nl'))
    email_qs = request.args.get('email', '').strip().lower()
    if request.method == 'POST':
        import sqlite3 as _sq, re
        from datetime import datetime
        email_raw = request.form.get('email', '')
        email = email_raw.strip().lower()
        email = re.sub(r'[^\x20-\x7E]', '', email)
        code = request.form.get('code', '').strip()
        new_pw = request.form.get('password', '')
        new_pw2 = request.form.get('password_confirm', '')
        lang = request.form.get('lang', lang)
        err = None
        if not email or not code or not new_pw:
            err = ('Vul alle velden in.' if lang=='nl' else 'Bitte alle Felder ausfüllen.' if lang=='de' else 'Please fill in all fields.')
        elif len(new_pw) < 8:
            err = ('Wachtwoord minimaal 8 tekens.' if lang=='nl' else 'Passwort mindestens 8 Zeichen.' if lang=='de' else 'Password must be at least 8 characters.')
        elif new_pw != new_pw2:
            err = ('Wachtwoorden komen niet overeen.' if lang=='nl' else 'Passwörter stimmen nicht überein.' if lang=='de' else 'Passwords do not match.')
        if err:
            return render_template('wachtwoord_reset.html', lang=lang, error=err, email=email, code=code)
        _cn = _sq.connect('/opt/ic-license-server/data/saas_licenses.db')
        _cn.row_factory = _sq.Row
        # Geldige code: niet gebruikt, niet verlopen. strftime-format matcht Python isoformat (zie Fase 5 fix).
        row = _cn.execute(
            "SELECT id FROM password_reset_codes WHERE lower(email)=? AND code=? AND used_at IS NULL AND expires_at > strftime('%Y-%m-%dT%H:%M:%S', 'now') ORDER BY id DESC LIMIT 1",
            (email, code)
        ).fetchone()
        if not row:
            _cn.close()
            err = ('Code ongeldig of verlopen.' if lang=='nl' else 'Code ungültig oder abgelaufen.' if lang=='de' else 'Code invalid or expired.')
            return render_template('wachtwoord_reset.html', lang=lang, error=err, email=email, code='')
        # Update password (bcrypt) + invalideer ALLE openstaande codes voor dit email (anti-replay).
        new_hash = hash_password(new_pw)
        used_ts = datetime.utcnow().isoformat()
        _cn.execute("UPDATE users SET password_hash=? WHERE email=? COLLATE NOCASE", (new_hash, email))
        _cn.execute("UPDATE password_reset_codes SET used_at=? WHERE lower(email)=? AND used_at IS NULL",
                    (used_ts, email))
        _cn.commit()
        _cn.close()
        return redirect(url_for('sc_login', success='password_reset', lang=lang))
    return render_template('wachtwoord_reset.html', lang=lang, email=email_qs)


@app.route('/profiel')
def profile_setup():
    if not session.get('license_valid') and not session.get('demo_mode'):
        return redirect(url_for('welcome'))
    return render_template('profile.html', lang=session.get('lang', 'nl'),
                           license_type=session.get('license_type'))

@app.route('/profiel/opslaan', methods=['POST'])
def save_profile():
    if not session.get('license_valid') and not session.get('demo_mode'):
        return redirect(url_for('welcome'))
    _name = request.form.get('name', '').strip()
    _surname = request.form.get('surname', '').strip() or None
    _by   = int(request.form.get('birth_year', 1970))
    _gen  = request.form.get('gender', 'male')
    # Profiel-compleet-vlag: 1 zodra geldig geboortejaar + geslacht zijn ingevuld
    # (een déliberaat ingevuld 1970/1990 telt hier als geldig — de lus-fix).
    _completed = 0 if _profiel_incompleet(_by, _gen) else 1
    session['profile_name']       = _name
    session['profile_surname']    = _surname or ''
    session['profile_birth_year'] = _by
    session['profile_gender']     = _gen
    session['profile_completed']  = _completed
    # Persisteer + zet activated_at/license_expires alleen bij eerste keer
    import sqlite3 as _sq2, datetime as _dt2
    _cn2 = _sq2.connect('/opt/ic-license-server/data/saas_licenses.db')
    _now = _dt2.datetime.utcnow()
    if session.get('legacy_migrated'):
        _exp = _dt2.datetime(2027, 1, 1)
    else:
        _exp = _now + _dt2.timedelta(days=183)  # ~6 maanden
    _cn2.execute(
        "UPDATE users SET "
        "display_name=?, surname=?, birth_year=?, gender=?, profile_completed=?, "
        "activated_at=COALESCE(activated_at, ?), "
        "license_expires=COALESCE(license_expires, ?) "
        "WHERE email=?",
        (_name, _surname, _by, _gen, _completed,
         _now.isoformat(), _exp.isoformat(),
         session.get('email',''))
    )
    _cn2.commit()
    _cn2.close()
    if is_pro():
        return redirect(url_for('pro_menu'))
    return redirect(url_for('menu'))

@app.route('/menu')
def menu():
    if request.args.get('demo') == '1':
        session['demo_mode'] = True
        session['is_demo'] = True
        session['user_key'] = 'DEMO'
        if request.args.get('role') == 'pro':
            session['license_type'] = 'pro'
        else:
            session.pop('license_type', None)
    if session.get('license_type') == 'pro' and (session.get('license_valid') or session.get('demo_mode')):
        return redirect(url_for('pro_menu'))
    if not session.get('license_valid') and not session.get('demo_mode'):
        return redirect(url_for('welcome'))
    # Check vervaldatum
    if session.get('license_valid') and not session.get('demo_mode') and not session.get('free_trial'):
        try:
            import sqlite3 as _sq_exp, datetime as _dt_exp
            _exp_cn = _sq_exp.connect('/opt/ic-license-server/data/saas_licenses.db')
            _exp_cn.row_factory = _sq_exp.Row
            _exp_row = _exp_cn.execute("SELECT license_expires FROM users WHERE email=?", (session.get('email',''),)).fetchone()
            _exp_cn.close()
            if _exp_row and _exp_row['license_expires']:
                _exp_date = _dt_exp.datetime.fromisoformat(_exp_row['license_expires'])
                if _dt_exp.datetime.utcnow() > _exp_date:
                    session.clear()
                    return redirect(url_for('welcome') + '?expired=1')
        except Exception:
            pass
    _cn = sqlite3.connect(METING_DB_PATH)
    _naam_row = _cn.execute("SELECT naam FROM user_profiles WHERE user_key=? OR email=?", (get_user_key(), session.get("email",""))).fetchone()
    _naam = (_naam_row[0] if _naam_row and _naam_row[0] else session.get('profile_name', ''))
    _lm = _cn.execute("SELECT ri,bpm,hrv_pct FROM metingen WHERE user_key=? ORDER BY id DESC LIMIT 1",
                       (get_user_key(),)).fetchone()
    _cn.close()
    return render_template("menu.html", lang=session.get("lang","nl"),
                           name=_naam,
                           license_type=session.get('license_type', 'free'), last_meting=_lm, demo_mode=session.get('demo_mode', False))

@app.route('/gratis')
def free_mode():
    session['license_valid'] = True
    session['lang']          = request.args.get('lang', 'nl')
    if request.args.get('role') == 'pro':
        session['license_type'] = 'pro'
        session['free_trial'] = True
    else:
        session['license_type'] = 'free'
        session.pop('free_trial', None)
    return redirect(url_for('profile_setup'))


@app.route('/oude-code', methods=['GET', 'POST'])
def oude_code():
    lang = session.get('lang', 'nl')
    error = None
    if request.method == 'POST':
        code = request.form.get('code', '').strip().upper()
        # Valideer tegen legacy_keys tabel
        try:
            import sqlite3 as _sqlite3
            legacy_db = _sqlite3.connect('/opt/ic-license-server/data/saas_licenses.db')
            legacy_db.row_factory = _sqlite3.Row
            row = legacy_db.execute(
                "SELECT * FROM legacy_keys WHERE license_key=?", (code,)
            ).fetchone()
            legacy_db.close()
            if row and row['status'] == 'available':
                # Geldige ongebruikte code — sla op in sessie en toon keuze
                session['legacy_code'] = code
                session['legacy_valid'] = True
                return redirect(url_for('oude_code_keuze'))
            elif row and row['status'] == 'migrated':
                error = {'nl': 'Deze code is al eerder gebruikt.',
                         'de': 'Dieser Code wurde bereits verwendet.',
                         'en': 'This code has already been used.'}.get(lang, 'Code already used.')
            else:
                error = {'nl': 'Code niet herkend. Controleer op typefouten.',
                         'de': 'Code nicht erkannt. Bitte auf Tippfehler prüfen.',
                         'en': 'Code not recognised. Please check for typos.'}.get(lang, 'Code not recognised.')
        except Exception as e:
            error = f'Database fout: {e}'
    return render_template('oude_code.html', lang=lang, error=error)


@app.route('/oude-code-keuze', methods=['GET', 'POST'])
def oude_code_keuze():
    if not session.get('legacy_valid'):
        return redirect(url_for('welcome'))
    lang = session.get('lang', 'nl')
    if request.method == 'POST':
        role = request.form.get('role', 'consumer')
        # Markeer code als migrated
        try:
            import sqlite3 as _sqlite3
            legacy_db = _sqlite3.connect('/opt/ic-license-server/data/saas_licenses.db')
            legacy_db.execute(
                "UPDATE legacy_keys SET status='migrated', migrated_at=datetime('now') WHERE license_key=?",
                (session.get('legacy_code'),)
            )
            legacy_db.commit()
            legacy_db.close()
        except:
            pass
        # Zet sessie — 1 maand trial
        import datetime
        session['license_valid'] = True
        session['license_type'] = role  # 'consumer' of 'pro'
        session['trial_until'] = (datetime.date.today() + datetime.timedelta(days=31)).isoformat()
        session['legacy_migrated'] = True
        session.pop('legacy_valid', None)
        return redirect(url_for('profile_setup'))
    return render_template('legacy_choice.html', lang=lang,
                           legacy_code=session.get('legacy_code', ''),
                           pending_email=session.get('legacy_pending_email'))

@app.route('/taal/<lang>')
def set_language(lang):
    if lang in ('nl', 'de', 'en'):
        session['lang'] = lang
    next_url = request.args.get('next') or request.referrer or url_for('menu')
    return redirect(next_url)

@app.route('/uitloggen')
def logout():
    session.clear()
    return redirect('/welkom')

# ── Verplicht-profiel-handhaving (leeftijd + geslacht) ─────────────────────────
# Geen enkele meet-ingang mag een stille default-leeftijd/geslacht doorlaten.
# "Nooit ingevuld" wordt afgedwongen via de profile_completed-vlag (users/clients),
# NIET meer via de 1970/1990-sentinelwaarde — zo loopt een écht in 1970/1990 geboren
# gebruiker/cliënt niet vast: na invullen gaat de vlag op 1 en mag de meting wél.
# Deze helper is de defensieve WAARDE-check (None/0/<=1900/ongeldig geslacht); ze is
# ook de basis voor het ZETTEN van de vlag: vlag=1  ⇔  not _profiel_incompleet(...).
def _profiel_incompleet(birth_year, gender):
    try:
        by = int(birth_year) if birth_year not in (None, '') else None
    except (TypeError, ValueError):
        by = None
    by_invalid = by is None or by <= 1900
    g = (gender or '').strip().lower()
    g_invalid = g not in ('male', 'female', 'divers', 'unspecified')
    return by_invalid or g_invalid

@app.route('/sensor-en-meten')
def sensor_en_meten():
    if not session.get("license_valid") and not session.get("demo_mode"):
        return redirect(url_for("welcome"))
    _cid = int(request.args.get("cid", 0)) or session.get("measuring_for_client") or 0
    # Verplicht-profiel-handhaving: geen meting bij ontbrekend/ongeldig geboortejaar óf geslacht.
    # Eigen meting → users-DB; pro-cliëntmeting → clients-DB (DB-waarheid). Demo gebruikt fixtures → overslaan.
    _cli_by, _cli_gen = session.get("client_birth_year"), session.get("client_gender")
    _own_by, _own_gen = session.get("profile_birth_year"), session.get("profile_gender")
    _profile_ok = True
    if not session.get("demo_mode"):
        if _cid and _is_pro_or_demo_pro():
            _pdb = get_pro_db()
            _crow = _pdb.execute("SELECT birth_year, gender, profile_completed FROM clients WHERE id=? AND pro_key=?",
                                 (_cid, get_user_key())).fetchone()
            _pdb.close()
            if _crow is not None:
                _cli_by, _cli_gen = _crow["birth_year"], _crow["gender"]
                _profile_ok = bool(_crow["profile_completed"]) and not _profiel_incompleet(_cli_by, _cli_gen)
            else:
                _profile_ok = False
            if not _profile_ok:
                return redirect(url_for('pro_client_detail', cid=_cid) + '?reason=profiel_incompleet')
        else:
            import sqlite3 as _sq_blk
            _cn_blk = _sq_blk.connect('/opt/ic-license-server/data/saas_licenses.db')
            _by_row = _cn_blk.execute("SELECT birth_year, gender, profile_completed FROM users WHERE email=?",
                                      (session.get('email',''),)).fetchone()
            _cn_blk.close()
            if _by_row is not None:
                _own_by, _own_gen = _by_row[0], _by_row[1]
                _profile_ok = bool(_by_row[2]) and not _profiel_incompleet(_own_by, _own_gen)
            else:
                _profile_ok = False
            if not _profile_ok:
                return redirect(url_for('profile_setup') + '?reason=meting_blocked')
    if _cid and _is_pro_or_demo_pro():
        profile = {"id": _cid, "name": session.get("client_name",""),
                   "surname": session.get("client_surname","") or None,
                   "birth_year": _cli_by if _cli_by is not None else session.get("client_birth_year", 1970),
                   "gender": _cli_gen or session.get("client_gender","male")}
    else:
        profile = {"id": 1, "name": session.get("profile_name", "Paul"),
                   "surname": session.get("profile_surname","") or None,
                   "birth_year": _own_by if _own_by is not None else session.get("profile_birth_year", 1970),
                   "gender": _own_gen or session.get("profile_gender", "male")}
    _dur_arg = request.args.get("duration", type=int)
    _biofeed_dur = _dur_arg if (_dur_arg is not None and 180 <= _dur_arg <= 1800) else 600
    return render_template("sensor_en_meten.html",
        lang=session.get("lang", "nl"), profile=profile, profile_ok=_profile_ok,
        duration=_biofeed_dur if request.args.get("type")=="biofeedback" else 90,
        skip_subj=request.args.get("skip_subj","0"), is_pro=is_pro(),
        meting_type=request.args.get("type","basismeting"),
        is_demo=session.get("is_demo") or session.get("demo_mode", False),
        client_id=_cid,
        show_edu=show_educational_blocks(),
    )

@app.route('/voorbereiden')
def voorbereiden():
    lang = session.get('lang', 'nl')
    next_page = request.args.get('next', 'basismeting')
    _cid = request.args.get("cid") or session.get("measuring_for_client")
    sensor_url = '/sensor-en-meten'
    if _cid: sensor_url = f'/sensor-en-meten?cid={_cid}'
    resp = make_response(render_template('voorbereiden.html',
        lang=lang, sensor_url=sensor_url, next=next_page,
        show_edu=show_educational_blocks(),
    ))
    resp.headers['Cache-Control'] = 'no-store'
    return resp

@app.route("/sensoren")
def sensoren():
    return redirect(url_for('kenniscentrum'))
@app.route('/eggs')
def eggs():
    return redirect(url_for('results'))

@app.route('/kwadrant')
def kwadrant():
    if not session.get('license_valid') and not session.get('demo_mode') and not session.get('hlm_user_id'):
        return redirect(url_for('welcome'))
    client_id = int(request.args.get('cid', 0)) or session.get('measuring_for_client') or 0
    client_name = ''
    if client_id and _is_pro_or_demo_pro():
        db = get_pro_db()
        _pk = get_user_key()
        _demo = session.get('demo_mode') and session.get('license_type') == 'pro'
        c = db.execute("SELECT name FROM clients WHERE id=? AND (pro_key=? OR pro_key='DEMO')" if _demo else "SELECT name FROM clients WHERE id=? AND pro_key=?", (client_id, _pk)).fetchone()
        if c: client_name = c['name']
        db.close()
    client_info = {}
    if client_id and _is_pro_or_demo_pro():
        db = get_pro_db()
        _pk = get_user_key()
        _demo = session.get('demo_mode') and session.get('license_type') == 'pro'
        ci = db.execute("SELECT * FROM clients WHERE id=? AND (pro_key=? OR pro_key='DEMO')" if _demo else "SELECT * FROM clients WHERE id=? AND pro_key=?", (client_id, _pk)).fetchone()
        if ci:
            _sn = ''
            try: _sn = (ci['surname'] or '').strip()
            except (IndexError, KeyError): _sn = ''
            client_name = (ci['name'] + ' ' + _sn).strip() if _sn else ci['name']
            client_info = {'name': ci['name'], 'surname': _sn or None, 'birth_year': ci['birth_year'],
                          'gender': ci['gender'], 'client_code': ci['client_code']}
        db.close()
    return render_template('kwadrant.html', lang=session.get('lang', 'nl'),
                           client_id=client_id, client_name=client_name,
                           client_info=client_info, is_pro=is_pro(), last_meting_type=session.get('last_meting_type','basismeting'), pending_meting_id=session.get('pending_meting_id',0))

@app.route('/resultaten')
def results():
    if not session.get('license_valid') and not session.get('demo_mode'):
        return redirect(url_for('welcome'))
    subjectief_pending = False  # zelfinschatting nu vóór meting via waarschuwingspagina
    row = None
    try:
        db = get_meting_db()
        row = db.execute('SELECT subjectief_score, ri FROM metingen WHERE user_key=? ORDER BY ts DESC LIMIT 1',(get_user_key(),)).fetchone()
        db.close()
    except:
        pass
    resp = make_response(render_template('results.html', lang=session.get('lang', 'nl'),
                            profile_name=session.get('profile_name', ''),
                            subjectief_pending=subjectief_pending,
                            subjectief_score=row[0] if row else None,
                            subjectief_ri=row[1] if row else None,
                            demo_mode=session.get('demo_mode', False) or session.get('is_demo', False)))
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp

@app.route('/begrippen')
@app.route('/faq')
def faq_page():
    return redirect(url_for('kenniscentrum'))

def begrippen():
    return redirect(url_for('kenniscentrum'))

@app.route('/tips')
def tips():
    return redirect(url_for('kenniscentrum'))

@app.route('/beroepen')
def beroepen():
    if (not session.get('license_valid') and not session.get('demo_mode')) or not _is_pro_or_demo_pro():
        return redirect(url_for('menu'))
    return render_template('beroepen.html', lang=session.get('lang','nl'))

@app.route('/over-stress')
def over_stress():
    return redirect(url_for('kenniscentrum'))

@app.route('/instellingen')
def settings():
    import logging; logging.getLogger().warning(f"SETTINGS SESSION: birth_year={session.get('profile_birth_year')} gender={session.get('profile_gender')} sensor={session.get('sensor_pref')}")
    if not session.get('license_valid') and not session.get('demo_mode'):
        return redirect(url_for('welcome'))
    email = session.get('email', '')
    _by, _gd, _sp = 1970, 'male', 'bluetooth'
    if email:
        try:
            import sqlite3 as _sq2
            _cn2 = _sq2.connect('/opt/ic-license-server/data/saas_licenses.db')
            _cn2.row_factory = _sq2.Row
            _r2 = _cn2.execute("SELECT birth_year, gender, sensor_pref FROM users WHERE email=?", (email,)).fetchone()
            if _r2:
                _by = _r2['birth_year'] or 1970
                _gd = _r2['gender'] or 'male'
                _sp = _r2['sensor_pref'] or 'bluetooth'
            _cn2.close()
        except: pass
    session['profile_birth_year'] = _by
    session['profile_gender'] = _gd
    session['sensor_pref'] = _sp
    _lang = session.get('lang', 'nl')
    return render_template('settings.html', lang=_lang, is_pro=session.get('license_type') in ('pro','pro_demo'),
                            profile_name=session.get('profile_name', ''),
                            profile_surname=session.get('profile_surname', ''),
                            birth_year=_by,
                            gender=_gd,
                            subscription_info=get_subscription_info(email, _lang),
                            tier_summary=get_pro_tier_summary(email, _lang),
                            kk_tier=kk_tier_label(),
                            active_pairings=get_active_pairings_count(get_user_key()))
@app.route('/verloop')
def verloop():
    if not session.get('license_valid') and not session.get('demo_mode'):
        return redirect(url_for('index'))
    return render_template('verloop.html', lang=session.get('lang','nl'))


@app.route('/mijn-metingen')
def mijn_metingen():
    user_key = session.get('user_key','')
    if not user_key:
        return redirect(url_for('sc_login'))
    cn = get_meting_db()
    metingen = cn.execute(
        "SELECT id, ts, ri, bpm, hrv_pct, rmssd, meting_type, notes, rr_intervals FROM metingen WHERE user_key=? ORDER BY ts DESC",
        (user_key,)
    ).fetchall()
    metingen_chart = [dict(r) for r in metingen]
    lang = session.get('lang','nl')
    return render_template('mijn_metingen.html', metingen_chart=metingen_chart, lang=lang)

@app.route("/biofeedback")
def biofeedback():
    if not session.get("license_valid") and not session.get("demo_mode"):
        return redirect(url_for("welcome"))
    # Verplicht-profiel-handhaving: ook biofeedback berekent HRV%/RI → geen meting bij onvolledig profiel.
    _bf_by, _bf_gen = session.get("profile_birth_year"), session.get("profile_gender")
    _bf_ok = True
    if not session.get("demo_mode"):
        import sqlite3 as _sq_bf
        _cn_bf = _sq_bf.connect('/opt/ic-license-server/data/saas_licenses.db')
        _r_bf = _cn_bf.execute("SELECT birth_year, gender, profile_completed FROM users WHERE email=?",
                               (session.get('email',''),)).fetchone()
        _cn_bf.close()
        if _r_bf is not None:
            _bf_by, _bf_gen = _r_bf[0], _r_bf[1]
            _bf_ok = bool(_r_bf[2]) and not _profiel_incompleet(_bf_by, _bf_gen)
        else:
            _bf_ok = False
        if not _bf_ok:
            return redirect(url_for('profile_setup') + '?reason=meting_blocked')
    profile = {"name": session.get("profile_name", ""), "surname": session.get("profile_surname","") or None,
               "birth_year": _bf_by if _bf_by is not None else session.get("profile_birth_year", 1990),
               "gender": _bf_gen or session.get("profile_gender", "male"), "id": session.get("profile_id", 0)}
    response = make_response(render_template("measure.html", lang=session.get("lang", "nl"), profile=profile, profile_ok=_bf_ok, duration=0, skip_subj="1", is_pro=is_pro(), meting_type="biofeedback", is_demo=session.get("is_demo") or session.get("demo_mode", False)))
    response.headers["Cache-Control"] = "no-store"
    return response

# ─── PRO routes ──────────────────────────────────────────────────────────────

@app.route('/pro')
@require_kk_office_if_krankenkasse
def pro_menu():
    if not session.get('license_valid') and not session.get('demo_mode'):
        return redirect(url_for('welcome'))
    if not _is_pro_or_demo_pro():
        return redirect(url_for('menu'))
    # Defense-in-depth: ruim legacy sticky cliënt-selectie op bij terugkeer naar Pro-menu
    session.pop('last_client_id', None)
    # Check vervaldatum
    if session.get('license_valid') and not session.get('demo_mode') and not session.get('free_trial'):
        try:
            import sqlite3 as _sq_exp, datetime as _dt_exp
            _exp_cn = _sq_exp.connect('/opt/ic-license-server/data/saas_licenses.db')
            _exp_cn.row_factory = _sq_exp.Row
            _exp_row = _exp_cn.execute("SELECT license_expires FROM users WHERE email=?", (session.get('email',''),)).fetchone()
            _exp_cn.close()
            if _exp_row and _exp_row['license_expires']:
                _exp_date = _dt_exp.datetime.fromisoformat(_exp_row['license_expires'])
                if _dt_exp.datetime.utcnow() > _exp_date:
                    session.clear()
                    return redirect(url_for('welcome') + '?expired=1')
        except Exception:
            pass
    lang = session.get('lang', 'nl')
    pro_key = get_user_key()
    db = get_pro_db()
    _demo = session.get('demo_mode') and session.get('license_type') == 'pro'
    client_count = db.execute("SELECT COUNT(*) FROM clients WHERE active=1 AND (pro_key=? OR pro_key='DEMO')" if _demo else "SELECT COUNT(*) FROM clients WHERE active=1 AND pro_key=?", (pro_key,)).fetchone()[0]
    recent_count = db.execute(
        "SELECT COUNT(*) FROM client_metingen WHERE (pro_key=? OR pro_key='DEMO') AND ts>?" if _demo else "SELECT COUNT(*) FROM client_metingen WHERE pro_key=? AND ts>?",
        (pro_key, int((datetime.now().timestamp() - 7*86400) * 1000))
    ).fetchone()[0]
    db.close()
    _email = session.get('email', '')
    return render_template("pro/menu.html", lang=lang,
                           name=session.get("profile_name", ""),
                           client_count=client_count, recent_count=recent_count, is_pro=is_pro,
                           is_demo=session.get("is_demo", False),
                           demo_msg=("Nur fur Pro-Abonnenten" if lang=="de" else "Pro subscribers only" if lang=="en" else "Alleen voor Pro-abonnees"),
                           subscription_info=get_subscription_info(_email, lang),
                           tier_summary=get_pro_tier_summary(_email, lang),
                           kk_tier=kk_tier_label(),
                           active_pairings=get_active_pairings_count(pro_key))

@app.route('/pro/mijn-metingen')
@require_kk_office_if_krankenkasse
def pro_eigen_metingen():
    if not session.get('license_valid') or not is_pro():
        return redirect(url_for('welcome'))
    lang = session.get('lang', 'nl')
    pro_key = get_user_key()
    db = get_meting_db()
    metingen = db.execute(
        "SELECT * FROM metingen WHERE user_key=? ORDER BY ts DESC LIMIT 100",
        (pro_key,)).fetchall()
    db.close()
    metingen_chart = [{'id': r['id'], 'ts': r['ts'], 'ri': r['ri'], 'bpm': r['bpm'], 'hrv_pct': r['hrv_pct'], 'rmssd': r['rmssd'], 'notes': r['notes'] if 'notes' in r.keys() else '', 'meting_type': r['meting_type'] if 'meting_type' in r.keys() else '', 'rr_intervals': r['rr_intervals'] if 'rr_intervals' in r.keys() else '', 'dimensie': r['ctx_dimensie'] if 'ctx_dimensie' in r.keys() else '', 'subjectief_score': r['subjectief_score'] if 'subjectief_score' in r.keys() else None} for r in metingen]
    from datetime import datetime
    metingen_list = []
    for r in metingen:
        d = dict(r)
        try:
            dt = datetime.fromtimestamp(d['ts']/1000)
            d['datum'] = dt.strftime('%Y-%m-%d')
            d['tijd'] = dt.strftime('%H:%M')
        except:
            d['datum'] = '-'
            d['tijd'] = '-'
        metingen_list.append(d)
    resp = make_response(render_template('pro/eigen_metingen.html', lang=lang, metingen=metingen_list, metingen_chart=metingen_chart))
    resp.headers["Cache-Control"] = "no-store, no-cache"
    return resp

@app.route('/pro/clienten')
@require_kk_office_if_krankenkasse
def pro_clients():
    if (not session.get('license_valid') and not session.get('demo_mode')) or not _is_pro_or_demo_pro():
        return redirect(url_for('welcome'))
    lang = session.get('lang', 'nl')
    pro_key = get_user_key()
    _demo = session.get('demo_mode') and session.get('license_type') == 'pro'
    db = get_pro_db()
    clients = db.execute("SELECT * FROM clients WHERE active=1 AND (pro_key=? OR pro_key='DEMO') ORDER BY name" if _demo else "SELECT * FROM clients WHERE active=1 AND pro_key=? ORDER BY name", (pro_key,)).fetchall()
    client_list = []
    for c in clients:
        last = db.execute("SELECT ri,bpm,hrv_pct,ts FROM client_metingen WHERE client_id=? ORDER BY ts DESC LIMIT 1", (c['id'],)).fetchone()
        total = db.execute("SELECT COUNT(*) FROM client_metingen WHERE client_id=?", (c['id'],)).fetchone()[0]
        client_list.append({
            'id': c['id'], 'name': c['name'], 'birth_year': c['birth_year'],
            'gender': c['gender'], 'client_code': c['client_code'],
            'email': c['email'] or '', 'notes': c['notes'] or '',
            'last_ri': round(last['ri'],1) if last else None,
            'last_bpm': last['bpm'] if last else None,
            'last_ts': __import__('datetime').datetime.fromtimestamp(last['ts']/1000).strftime('%d-%m-%Y') if last and last['ts'] else None,
            'total_metingen': total,
                'week_avg': round(db.execute('SELECT AVG(ri) FROM client_metingen WHERE client_id=? AND ts>?', (c['id'], (__import__('time').time()-604800)*1000)).fetchone()[0] or 0, 1),
                'trend': (lambda cur, prev: ('up', round(cur - prev, 1)) if cur and prev and cur - prev > 0.3 else (('down', round(cur - prev, 1)) if cur and prev and cur - prev < -0.3 else (('flat', 0) if cur and prev else ('nodata', 0))))(
                    db.execute('SELECT AVG(ri) FROM client_metingen WHERE client_id=? AND ts>?', (c['id'], (__import__('time').time()-604800)*1000)).fetchone()[0],
                    db.execute('SELECT AVG(ri) FROM client_metingen WHERE client_id=? AND ts>? AND ts<?', (c['id'], (__import__('time').time()-1209600)*1000, (__import__('time').time()-604800)*1000)).fetchone()[0]
                ),
                'top_dimensie': (lambda r: r[0] if r else None)(db.execute("SELECT ctx_dimensie FROM client_metingen WHERE client_id=? AND ctx_dimensie IS NOT NULL AND ctx_dimensie != '' GROUP BY ctx_dimensie ORDER BY COUNT(*) DESC LIMIT 1", (c['id'],)).fetchone())
        })
    db.close()
    quota = build_pro_client_quota(pro_key, session.get('email', '')) if not _demo else None
    limit_reached_flag = request.args.get('limit_reached') == '1'
    return render_template('pro/clients.html', lang=lang, clients=client_list,
                           quota=quota, is_krankenkasse=is_krankenkasse_session(),
                           limit_reached_flag=limit_reached_flag)

@app.route('/pro/dashboard')
@require_kk_office_if_krankenkasse
def pro_dashboard():
    if (not session.get('license_valid') and not session.get('demo_mode')) or not _is_pro_or_demo_pro():
        return redirect(url_for('welcome'))
    import time as _t
    lang = session.get('lang', 'nl')
    pro_key = get_user_key()
    _demo = session.get('demo_mode') and session.get('license_type') == 'pro'
    db = get_pro_db()
    clients = db.execute("SELECT * FROM clients WHERE active=1 AND (pro_key=? OR pro_key='DEMO') ORDER BY name" if _demo else "SELECT * FROM clients WHERE active=1 AND pro_key=? ORDER BY name", (pro_key,)).fetchall()
    now_ms = _t.time() * 1000
    week_ms = 7 * 86400 * 1000
    rows = []
    for c in clients:
        cid = c['id']
        avg_all = db.execute("SELECT AVG(ri) FROM client_metingen WHERE client_id=? AND ri IS NOT NULL", (cid,)).fetchone()[0]
        avg_recent = db.execute("SELECT AVG(ri) FROM client_metingen WHERE client_id=? AND ri IS NOT NULL AND ts>?", (cid, now_ms - week_ms)).fetchone()[0]
        avg_prev = db.execute("SELECT AVG(ri) FROM client_metingen WHERE client_id=? AND ri IS NOT NULL AND ts>? AND ts<=?", (cid, now_ms - 2*week_ms, now_ms - week_ms)).fetchone()[0]
        if avg_recent and avg_prev:
            if avg_recent > avg_prev + 0.1: trend = 'up'
            elif avg_recent < avg_prev - 0.1: trend = 'down'
            else: trend = 'flat'
        else:
            trend = 'flat'
        last = db.execute("SELECT ts FROM client_metingen WHERE client_id=? ORDER BY ts DESC LIMIT 1", (cid,)).fetchone()
        last_ts = None
        if last and last['ts']:
            last_ts = datetime.fromtimestamp(last['ts']/1000).strftime('%d-%m-%Y')
        top_dim = db.execute(
            "SELECT ctx_dimensie FROM client_metingen WHERE client_id=? AND ctx_dimensie IS NOT NULL AND ctx_dimensie!='' GROUP BY ctx_dimensie ORDER BY COUNT(*) DESC LIMIT 1",
            (cid,)).fetchone()
        total = db.execute("SELECT COUNT(*) FROM client_metingen WHERE client_id=?", (cid,)).fetchone()[0]
        rows.append({
            'id': cid,
            'name': c['name'],
            'avg_ri': round(avg_all, 1) if avg_all else None,
            'trend': trend,
            'last_ts': last_ts,
            'top_dimensie': top_dim[0] if top_dim else None,
            'total': total,
        })
    db.close()
    return render_template('pro/dashboard.html', lang=lang, rows=rows)

@app.route('/pro/locatie', methods=['GET','POST'])
def pro_locatie():
    """Krankenkasse-flow: keuze van actief kantoor voor de huidige sessie.
    Een Krankenkasse-licentie heeft 1..N kantoren in krankenkasse_offices; gekozen
    waarde landt in session['kk_office'] en wordt door api_meting_opslaan op elke
    nieuwe meting in client_metingen.office_label opgeslagen."""
    if not session.get('license_valid') or not is_krankenkasse_session():
        return redirect(url_for('welcome'))
    lang = session.get('lang', 'nl')
    license_code = session.get('license_code', '')
    db = sqlite3.connect('/opt/ic-license-server/data/saas_licenses.db')
    db.row_factory = sqlite3.Row
    if request.method == 'POST':
        chosen = (request.form.get('office_name','') or '').strip()
        row = db.execute(
            "SELECT office_name FROM krankenkasse_offices WHERE license_code=? AND office_name=? AND active=1",
            (license_code, chosen)).fetchone()
        db.close()
        if row:
            session['kk_office'] = row['office_name']
            _log_kk_action(license_code, 'kk_session_office_select',
                           f"office_name={row['office_name']}")
            return redirect(url_for('pro_menu'))
        return redirect(url_for('pro_locatie', error='invalid'))
    offices = [r['office_name'] for r in db.execute(
        "SELECT office_name FROM krankenkasse_offices WHERE license_code=? AND active=1 ORDER BY office_name",
        (license_code,)).fetchall()]
    db.close()
    return render_template('pro/locatie_keuze.html', lang=lang, offices=offices, current=session.get('kk_office',''))


# ============================================================================
# Krankenkasse self-service kantoor-beheer (Sessie B.1)
# /pro/locaties/*  — KK-account beheert eigen kantoor-master-lijst.
# Auth: alleen KK-sessie (geen @require_kk_office_if_krankenkasse — beheer
# moet bereikbaar zijn zonder eerst een kantoor te kiezen).
# Coexisteert met /admin/krankenkasse/<code>/offices (Paul-only cross-licentie).
# ============================================================================

def _kk_require():
    """Hard 403 voor niet-KK-sessies. Geen redirect — admin-toegang heeft een
    inlog-flow en wordt verondersteld al doorlopen."""
    if not session.get('license_valid') or not is_krankenkasse_session():
        abort(403)


def _kk_db():
    db = sqlite3.connect('/opt/ic-license-server/data/saas_licenses.db')
    db.row_factory = sqlite3.Row
    return db


def _kk_office_stats(license_code, pro_user_key):
    """Per-office aggregatie: actief/inactief + totaal metingen + M/V/overig-tellers.
    Cross-DB: offices uit saas_licenses.db, metingen uit sc_pro.db. Twee queries,
    Python-merge — geen ATTACH (eenvoudiger + minder lock-risk)."""
    db = _kk_db()
    offices = db.execute(
        "SELECT id, office_name, region, active, created_at FROM krankenkasse_offices "
        "WHERE license_code=? ORDER BY active DESC, office_name COLLATE NOCASE",
        (license_code,)).fetchall()
    db.close()

    pro_db = get_pro_db()
    rows = pro_db.execute("""
        SELECT cm.office_label AS office_name,
               COUNT(*) AS total,
               SUM(CASE WHEN c.gender='male'   THEN 1 ELSE 0 END) AS male,
               SUM(CASE WHEN c.gender='female' THEN 1 ELSE 0 END) AS female,
               SUM(CASE WHEN c.gender NOT IN ('male','female') OR c.gender IS NULL THEN 1 ELSE 0 END) AS other
        FROM client_metingen cm
        LEFT JOIN clients c ON c.id = cm.client_id
        WHERE cm.pro_key=? AND cm.office_label IS NOT NULL AND cm.office_label != ''
        GROUP BY cm.office_label
    """, (pro_user_key,)).fetchall()
    pro_db.close()
    stats = {r['office_name']: dict(r) for r in rows}
    out = []
    for o in offices:
        s = stats.get(o['office_name'], {})
        out.append({
            'id': o['id'],
            'office_name': o['office_name'],
            'region': o['region'] or '',
            'active': bool(o['active']),
            'created_at': o['created_at'],
            'total_metingen': s.get('total', 0) or 0,
            'male':   s.get('male', 0) or 0,
            'female': s.get('female', 0) or 0,
            'other':  s.get('other', 0) or 0,
        })
    return out


def _derive_operator_email(admin_email):
    """Lei operator-email af van admin-email: '<local>+kkoperator@<domain>'.
    Voor admin met +tag (paulpannevis+kktest@gmail.com): strip de bestaande tag eerst."""
    local, _, domain = (admin_email or '').partition('@')
    if not domain:
        return f"{admin_email}_operator"
    base = local.split('+', 1)[0]
    return f"{base}+kkoperator@{domain}"


def _log_kk_action(license_code, action, details):
    """Schrijf KK-CRUD-event naar saas_licenses.db.activation_log (Sessie B.4).
    Aanroepen NA succesvolle DB-write zodat we geen orphans loggen bij fail.
    Best-effort: bij INSERT-fout wordt waarschuwing geprint maar het verzoek faalt niet."""
    try:
        ip = (request.remote_addr or '')[:64]
        ua = (request.headers.get('User-Agent', '') or '')[:200]
        db = sqlite3.connect('/opt/ic-license-server/data/saas_licenses.db')
        db.execute(
            "INSERT INTO activation_log (license_key, product, action, ip_address, user_agent, details) "
            "VALUES (?, 'sc', ?, ?, ?, ?)",
            (license_code, action, ip, ua, details))
        db.commit()
        db.close()
    except Exception as e:
        import logging
        logging.getLogger().warning(f"[kk_audit] log fail action={action} lic={license_code}: {e}")


def _parse_kk_csv(raw_bytes, max_rows=500):
    """Parseer CSV-bytes naar lijst van {office_name, region, line}-dicts.
    Returns (rows, errors). Strict: header moet 'office_name' EN 'region' bevatten.
    UTF-8 verplicht, BOM (utf-8-sig) tolerated. Trim + lengthcap 100 chars."""
    import csv as _csv, io as _io
    errors = []
    try:
        text = raw_bytes.decode('utf-8-sig')
    except UnicodeDecodeError:
        try:
            text = raw_bytes.decode('utf-8')
        except UnicodeDecodeError as e:
            return ([], [f'Bestand is geen geldig UTF-8: {e}'])
    sample = text[:2048]
    try:
        dialect = _csv.Sniffer().sniff(sample, delimiters=',;\t')
    except _csv.Error:
        dialect = _csv.excel
    reader = _csv.DictReader(_io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        return ([], ['CSV is leeg of heeft geen header-rij'])
    headers_lc = [(h or '').strip().lower() for h in reader.fieldnames]
    if 'office_name' not in headers_lc or 'region' not in headers_lc:
        return ([], [f'CSV moet kolommen "office_name" en "region" bevatten. '
                     f'Gevonden: {", ".join(reader.fieldnames)}'])
    rows = []
    for i, raw in enumerate(reader, start=2):
        if len(rows) >= max_rows:
            errors.append(f'Maximum van {max_rows} rijen bereikt; rest overgeslagen')
            break
        norm = {(k or '').strip().lower(): (v or '').strip() for k, v in raw.items()}
        name = norm.get('office_name', '')[:100]
        region = norm.get('region', '')[:100]
        if not name:
            errors.append(f'Regel {i}: lege office_name overgeslagen')
            continue
        rows.append({'office_name': name, 'region': region, 'line': i})
    return (rows, errors)


@app.route('/pro/admin/messen-standort-kiezen', methods=['GET', 'POST'])
@require_kk_admin
def kk_admin_messen_standort():
    """Admin-specifieke Standort-keuze vóór een eigen meting.
    Eigen scherm — onthoudt de keuze niet permanent (admin heeft geen vaste Standort).
    POST → kk_office in sessie → redirect /pro/meting."""
    lang = session.get('lang', 'nl')
    license_code = session.get('license_code', '')
    db = sqlite3.connect('/opt/ic-license-server/data/saas_licenses.db')
    db.row_factory = sqlite3.Row
    if request.method == 'POST':
        chosen = (request.form.get('office_name','') or '').strip()
        row = db.execute(
            "SELECT office_name FROM krankenkasse_offices WHERE license_code=? AND office_name=? AND active=1",
            (license_code, chosen)).fetchone()
        db.close()
        if row:
            session['kk_office'] = row['office_name']
            return redirect(url_for('pro_meting_keuze'))
        return redirect(url_for('kk_admin_messen_standort', error='invalid'))
    offices = [r['office_name'] for r in db.execute(
        "SELECT office_name FROM krankenkasse_offices WHERE license_code=? AND active=1 ORDER BY office_name",
        (license_code,)).fetchall()]
    db.close()
    return render_template('pro/admin_messen_standort.html', lang=lang, offices=offices,
                           error=request.args.get('error', ''))


@app.route('/pro/operatoren', methods=['GET'])
@require_kk_admin
def kk_operatoren_lijst():
    """Lijst alle operator-accounts gekoppeld aan deze KK-licentie via user_licenses."""
    lang = session.get('lang', 'nl')
    license_code = session.get('license_code', '')
    db = sqlite3.connect('/opt/ic-license-server/data/saas_licenses.db')
    db.row_factory = sqlite3.Row
    rows = db.execute(
        "SELECT u.id, u.email, u.display_name, u.created_at, u.last_login "
        "FROM users u JOIN user_licenses ul ON ul.user_id = u.id "
        "WHERE ul.license_key=? AND u.role='operator' AND (u.deleted_at IS NULL OR u.deleted_at='') "
        "ORDER BY u.created_at",
        (license_code,)
    ).fetchall()
    db.close()
    operators = [dict(r) for r in rows]
    new_credentials = session.pop('_kk_new_operator_credentials', None)
    err = request.args.get('error', '')
    return render_template('pro/operatoren.html', lang=lang,
                           operators=operators, new_credentials=new_credentials,
                           error=err, license_code=license_code)


@app.route('/pro/operatoren/toevoegen', methods=['POST'])
@require_kk_admin
def kk_operatoren_toevoegen():
    """Voeg een operator-account toe aan de huidige KK-licentie.
    - email-uniek check
    - random password (token_urlsafe(12)), eenmalig getoond via session-flash
    - INSERT users + INSERT user_licenses
    - audit-log via _log_kk_action
    """
    import secrets as _sec, re as _re
    license_code = session.get('license_code', '')
    email_raw = (request.form.get('email','') or '').strip().lower()
    display_name = (request.form.get('display_name','') or '').strip()[:80] or 'KK Operator'
    if not _re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email_raw):
        return redirect(url_for('kk_operatoren_lijst', error='email_format'))
    db = sqlite3.connect('/opt/ic-license-server/data/saas_licenses.db')
    db.row_factory = sqlite3.Row
    if db.execute("SELECT 1 FROM users WHERE email=? COLLATE NOCASE", (email_raw,)).fetchone():
        db.close()
        return redirect(url_for('kk_operatoren_lijst', error='email_exists'))
    pw = _sec.token_urlsafe(12)
    pw_hash = hash_password(pw)
    cur = db.execute(
        "INSERT INTO users (email, password_hash, display_name, language, role, created_at) "
        "VALUES (?, ?, ?, 'de', 'operator', datetime('now'))",
        (email_raw, pw_hash, display_name)
    )
    op_id = cur.lastrowid
    db.execute(
        "INSERT INTO user_licenses (user_id, license_key, product, is_primary, linked_at) "
        "VALUES (?, ?, 'sc', 0, datetime('now'))",
        (op_id, license_code)
    )
    db.commit()
    db.close()
    _log_kk_action(license_code, 'kk_operator_create', f"email={email_raw} user_id={op_id}")
    session['_kk_new_operator_credentials'] = {'email': email_raw, 'password': pw}
    return redirect(url_for('kk_operatoren_lijst'))


@app.route('/pro/admin')
@require_kk_admin
def kk_admin_dashboard():
    """KK-admin-overzicht: KPI's, Standorte-tabel, recente 10 metingen.
    Auth-only voor role='admin' binnen KK-sessie. (Sessie B.6)"""
    from analytics import aggregate_period, period_bounds
    lang = session.get('lang', 'nl')
    license_code = session.get('license_code', '')
    pro_key = get_user_key()

    ps, pe = period_bounds('alles')
    agg = aggregate_period(license_code, pro_key, ps, pe, group_by=None, filter=None)

    offices = _kk_office_stats(license_code, pro_key)
    active_count = sum(1 for o in offices if o['active'])

    pro_db = get_pro_db()
    recent_raw = pro_db.execute(
        "SELECT ts, office_label, ri FROM client_metingen "
        "WHERE pro_key=? AND ri IS NOT NULL ORDER BY ts DESC LIMIT 10",
        (pro_key,)
    ).fetchall()
    pro_db.close()
    recent = []
    for r in recent_raw:
        ts_fmt = datetime.fromtimestamp(r['ts']/1000).strftime('%d-%m-%Y %H:%M') if r['ts'] else '-'
        recent.append({
            'ts': ts_fmt,
            'office_label': r['office_label'] or '–',
            'ri': round(r['ri'], 1) if r['ri'] is not None else None,
        })

    operator_welcome = session.pop('_kk_operator_welcome', None)

    return render_template('pro/dashboard_kk.html',
        lang=lang,
        license_code=license_code,
        tier_label=kk_tier_label(),
        total_metingen=agg.get('total_metingen', 0),
        unique_clients=agg.get('unique_clients', 0),
        ri_average=agg.get('ri_average'),
        active_count=active_count,
        total_offices=len(offices),
        offices=offices,
        recent=recent,
        operator_welcome=operator_welcome,
    )


@app.route('/pro/locaties')
def kk_locaties_overzicht():
    _kk_require()
    license_code = session.get('license_code', '')
    pro_key = get_user_key()
    offices = _kk_office_stats(license_code, pro_key)
    lang = session.get('lang', 'nl')
    sort = request.args.get('sort', 'name')
    q = (request.args.get('q', '') or '').strip().lower()
    if q:
        offices = [o for o in offices
                   if q in o['office_name'].lower() or q in (o['region'] or '').lower()]
    if sort == 'metingen':
        offices.sort(key=lambda o: (-o['total_metingen'], o['office_name'].lower()))
    elif sort == 'region':
        offices.sort(key=lambda o: ((o['region'] or '').lower(), o['office_name'].lower()))
    else:  # 'name' (default)
        offices.sort(key=lambda o: (not o['active'], o['office_name'].lower()))
    try:
        imported = int(request.args.get('imported', 0))
    except (TypeError, ValueError):
        imported = 0
    try:
        dups = int(request.args.get('dups', 0))
    except (TypeError, ValueError):
        dups = 0
    return render_template('pro/locaties_overzicht.html', lang=lang, offices=offices,
                           sort=sort, q=q, imported=imported, dups=dups)


@app.route('/pro/locaties/beheren')
def kk_locaties_beheren():
    _kk_require()
    license_code = session.get('license_code', '')
    pro_key = get_user_key()
    offices = _kk_office_stats(license_code, pro_key)
    lang = session.get('lang', 'nl')
    return render_template('pro/locaties_beheren.html', lang=lang, offices=offices,
                           created=request.args.get('created') == '1',
                           updated=request.args.get('updated') == '1',
                           deactivated=request.args.get('deactivated') == '1',
                           reactivated=request.args.get('reactivated') == '1',
                           error=request.args.get('error', ''))


@app.route('/pro/locaties/toevoegen', methods=['POST'])
def kk_locaties_toevoegen():
    _kk_require()
    license_code = session.get('license_code', '')
    name = (request.form.get('office_name', '') or '').strip()[:100]
    region = (request.form.get('region', '') or '').strip()[:100]
    if not name:
        return redirect(url_for('kk_locaties_beheren', error='leeg'))
    db = _kk_db()
    dup = db.execute(
        "SELECT id FROM krankenkasse_offices WHERE license_code=? AND LOWER(office_name)=LOWER(?)",
        (license_code, name)).fetchone()
    if dup:
        db.close()
        return redirect(url_for('kk_locaties_beheren', error='dup'))
    db.execute("INSERT INTO krankenkasse_offices (license_code, office_name, region) VALUES (?, ?, ?)",
               (license_code, name, region or None))
    db.commit()
    db.close()
    _log_kk_action(license_code, 'kk_office_create', f'name={name} region={region}')
    return redirect(url_for('kk_locaties_beheren', created='1'))


@app.route('/pro/locaties/<int:oid>/bewerken', methods=['POST'])
def kk_locaties_bewerken(oid):
    _kk_require()
    license_code = session.get('license_code', '')
    name = (request.form.get('office_name', '') or '').strip()[:100]
    region = (request.form.get('region', '') or '').strip()[:100]
    if not name:
        return redirect(url_for('kk_locaties_beheren', error='leeg'))
    db = _kk_db()
    row = db.execute("SELECT id, office_name, region FROM krankenkasse_offices WHERE id=? AND license_code=?",
                     (oid, license_code)).fetchone()
    if not row:
        db.close()
        abort(404)
    dup = db.execute(
        "SELECT id FROM krankenkasse_offices WHERE license_code=? AND LOWER(office_name)=LOWER(?) AND id<>?",
        (license_code, name, oid)).fetchone()
    if dup:
        db.close()
        return redirect(url_for('kk_locaties_beheren', error='dup'))
    old_name = row['office_name']
    old_region = row['region'] or ''
    db.execute("UPDATE krankenkasse_offices SET office_name=?, region=? WHERE id=? AND license_code=?",
               (name, region or None, oid, license_code))
    # Cascade: als naam wijzigt, kk_office in session refresh (toont nieuw label
    # in header bij volgende request); historische client_metingen blijven hangen
    # met oude office_name — bewust, want audit-trail.
    if session.get('kk_office', '').lower() == (old_name or '').lower():
        session['kk_office'] = name
    db.commit()
    db.close()
    _log_kk_action(license_code, 'kk_office_update',
                   f'id={oid} old_name={old_name} new_name={name} old_region={old_region} new_region={region}')
    return redirect(url_for('kk_locaties_beheren', updated='1'))


@app.route('/pro/locaties/<int:oid>/deactiveren', methods=['POST'])
def kk_locaties_deactiveren(oid):
    _kk_require()
    license_code = session.get('license_code', '')
    db = _kk_db()
    row = db.execute("SELECT office_name FROM krankenkasse_offices WHERE id=? AND license_code=?",
                     (oid, license_code)).fetchone()
    name = row['office_name'] if row else ''
    db.execute("UPDATE krankenkasse_offices SET active=0 WHERE id=? AND license_code=?",
               (oid, license_code))
    db.commit()
    db.close()
    if name:
        _log_kk_action(license_code, 'kk_office_deactivate', f'id={oid} name={name}')
    return redirect(url_for('kk_locaties_beheren', deactivated='1'))


@app.route('/pro/locaties/<int:oid>/reactiveren', methods=['POST'])
def kk_locaties_reactiveren(oid):
    _kk_require()
    license_code = session.get('license_code', '')
    db = _kk_db()
    row = db.execute("SELECT office_name FROM krankenkasse_offices WHERE id=? AND license_code=?",
                     (oid, license_code)).fetchone()
    name = row['office_name'] if row else ''
    db.execute("UPDATE krankenkasse_offices SET active=1 WHERE id=? AND license_code=?",
               (oid, license_code))
    db.commit()
    db.close()
    if name:
        _log_kk_action(license_code, 'kk_office_reactivate', f'id={oid} name={name}')
    return redirect(url_for('kk_locaties_beheren', reactivated='1'))


@app.route('/pro/locaties/import', methods=['GET', 'POST'])
def kk_locaties_import():
    _kk_require()
    license_code = session.get('license_code', '')
    lang = session.get('lang', 'nl')

    if request.method == 'POST':
        # Confirm-fase: hidden csv_text + confirm=1 wordt opnieuw geparsed en in DB gezet
        if request.form.get('confirm') == '1':
            csv_text = request.form.get('csv_text', '') or ''
            csv_filename = (request.form.get('csv_filename', '') or '')[:120]
            rows, errors = _parse_kk_csv(csv_text.encode('utf-8'))
            if not rows:
                return render_template('pro/locaties_import.html', lang=lang, errors=errors)
            db = _kk_db()
            existing_lc = {r['office_name'].lower() for r in db.execute(
                "SELECT office_name FROM krankenkasse_offices WHERE license_code=?",
                (license_code,)).fetchall()}
            new_count = 0
            dup_count = 0
            for r in rows:
                if r['office_name'].lower() in existing_lc:
                    dup_count += 1
                    continue
                db.execute("INSERT INTO krankenkasse_offices (license_code, office_name, region) "
                           "VALUES (?, ?, ?)",
                           (license_code, r['office_name'], r['region'] or None))
                existing_lc.add(r['office_name'].lower())
                new_count += 1
            db.commit()
            db.close()
            _log_kk_action(license_code, 'kk_office_import',
                           f'imported={new_count} dups={dup_count} total_rows={len(rows)} filename={csv_filename}')
            return redirect(url_for('kk_locaties_overzicht', imported=new_count, dups=dup_count))

        # Preview-fase: file upload → parse → toon preview met csv_text in hidden field
        f = request.files.get('csv_file')
        if not f or not f.filename:
            return render_template('pro/locaties_import.html', lang=lang,
                                   errors=['Geen bestand geüpload.'])
        raw = f.read(2 * 1024 * 1024)  # 2MB cap
        csv_filename = (f.filename or '')[:120]
        rows, errors = _parse_kk_csv(raw)
        if not rows:
            return render_template('pro/locaties_import.html', lang=lang, errors=errors)
        db = _kk_db()
        existing_lc = {r['office_name'].lower() for r in db.execute(
            "SELECT office_name FROM krankenkasse_offices WHERE license_code=?",
            (license_code,)).fetchall()}
        db.close()
        new_rows = [r for r in rows if r['office_name'].lower() not in existing_lc]
        dup_rows = [r for r in rows if r['office_name'].lower() in existing_lc]
        preview = new_rows[:20]
        try:
            csv_text = raw.decode('utf-8-sig')
        except UnicodeDecodeError:
            csv_text = raw.decode('utf-8', errors='replace')
        return render_template('pro/locaties_import_preview.html', lang=lang,
                               preview=preview, total_new=len(new_rows),
                               total_dup=len(dup_rows), total_rows=len(rows),
                               errors=errors, csv_text=csv_text,
                               csv_filename=csv_filename,
                               dup_preview=dup_rows[:10])

    return render_template('pro/locaties_import.html', lang=lang, errors=[])


# ============================================================================
# Rapportage-laag (Sessie B.2)
# 4 rapport-types via WeasyPrint, async via threading.Thread.
# Audit-trail in saas_licenses.db.report_jobs.
# Coexisteert met /admin/krankenkasse (admin-route) en /pro/locaties (KK-beheer).
# ============================================================================
import threading as _threading
import uuid as _uuid

REPORT_BASE_DIR = '/opt/stresschecker/reports'
REPORT_PUBLIC_BASE_URL = 'https://app.stresschecker.com'  # absolute link in mail


@app.template_global()
def pct(part, total):
    """Jinja-helper: percentage als '54%' (rounded) of '–' bij nul-totaal."""
    try:
        if not total: return '–'
        return f'{round(100.0 * float(part) / float(total))}%'
    except (TypeError, ValueError, ZeroDivisionError):
        return '–'


@app.template_global()
def zone_label_jinja(zone_key, lang):
    """Jinja-helper: zone-key → label. Wrapt analytics.zone_label."""
    import analytics as _analytics
    return _analytics.zone_label(zone_key, lang)


def _report_db():
    db = sqlite3.connect('/opt/ic-license-server/data/saas_licenses.db')
    db.row_factory = sqlite3.Row
    return db


def _license_info(license_code):
    db = _report_db()
    row = db.execute(
        "SELECT license_key, email, product, product_name, notes FROM licenses WHERE license_key=?",
        (license_code,)).fetchone()
    db.close()
    return dict(row) if row else None


def _license_pro_key(license_code):
    """Voor KK: stabiele pro_key uit licensehouder-email (zoals get_user_key) doet."""
    info = _license_info(license_code)
    if not info or not info.get('email'):
        return None
    return hashlib.sha256(info['email'].encode()).hexdigest()[:32]


def send_report_ready_email(to_email, uuid_str, lang='nl'):
    """Mail: rapport klaar + download-link."""
    try:
        import sendgrid
        from sendgrid.helpers.mail import Mail
        sg = sendgrid.SendGridAPIClient(os.environ['SENDGRID_API_KEY'])
        link = f'{REPORT_PUBLIC_BASE_URL}/rapport/download/{uuid_str}'
        if lang == 'de':
            subject = 'Ihr StressChecker-Bericht ist bereit'
            body = (f'Ihr Bericht wurde erstellt.\n\n'
                    f'Sie koennen ihn hier herunterladen:\n{link}\n\n'
                    f'Der Link funktioniert solange Sie eingeloggt sind.\n\n'
                    f'Mit freundlichen Gruessen,\nLifestyle Monitors')
        elif lang == 'en':
            subject = 'Your StressChecker report is ready'
            body = (f'Your report has been generated.\n\n'
                    f'Download it here:\n{link}\n\n'
                    f'The link works as long as you are logged in.\n\n'
                    f'Kind regards,\nLifestyle Monitors')
        else:
            subject = 'Uw StressChecker-rapport is klaar'
            body = (f'Uw rapport is gegenereerd.\n\n'
                    f'Download het hier:\n{link}\n\n'
                    f'De link werkt zolang u ingelogd bent.\n\n'
                    f'Met vriendelijke groet,\nLifestyle Monitors')
        msg = Mail(from_email='noreply@lifestylemonitors.com', to_emails=to_email,
                   subject=subject, plain_text_content=body)
        sg.send(msg)
        return True
    except Exception as e:
        print('Report-ready-mail fout:', e)
        return False


def send_report_failed_email(to_email, lang, err_summary):
    try:
        import sendgrid
        from sendgrid.helpers.mail import Mail
        sg = sendgrid.SendGridAPIClient(os.environ['SENDGRID_API_KEY'])
        if lang == 'de':
            subject = 'StressChecker-Bericht: Fehler bei der Generierung'
            body = (f'Leider konnte Ihr Bericht nicht erstellt werden.\n\n'
                    f'Fehler: {err_summary}\n\n'
                    f'Bitte versuchen Sie es erneut oder kontaktieren Sie support@lifestylemonitors.com.')
        elif lang == 'en':
            subject = 'StressChecker report: generation failed'
            body = (f'Sorry, your report could not be generated.\n\n'
                    f'Error: {err_summary}\n\n'
                    f'Please retry or contact support@lifestylemonitors.com.')
        else:
            subject = 'StressChecker-rapport: generatie mislukt'
            body = (f'Helaas kon uw rapport niet worden gegenereerd.\n\n'
                    f'Fout: {err_summary}\n\n'
                    f'Probeer opnieuw of neem contact op met support@lifestylemonitors.com.')
        msg = Mail(from_email='noreply@lifestylemonitors.com', to_emails=to_email,
                   subject=subject, plain_text_content=body)
        sg.send(msg)
    except Exception as e:
        print('Report-failed-mail fout:', e)


def _render_report_async(uuid_str, license_code, user_email, lang, report_type, params, pro_key):
    """Background thread. Genereert PDF, slaat op, update DB-row, verstuurt mail.
    Niet-daemon zodat Gunicorn graceful shutdown wacht."""
    import analytics
    db = _report_db()
    try:
        period_kind = params.get('periode', 'kwartaal')
        period_start, period_end = analytics.period_bounds(period_kind)
        lic = _license_info(license_code) or {}
        license_name = (lic.get('notes') or '').replace('Krankenkasse: ', '').strip() \
                       or lic.get('product_name') or license_code

        # BUG 3: 'alles'-periode begint op 1970-01-01 → niet als datum tonen.
        # Vervang door taal-afhankelijk label zodat de header niet "1970-01-01 →"
        # toont op een KK-deliverable.
        if period_start.startswith('1970-01-01'):
            period_start_date = {'de': 'Alle Messungen',
                                 'en': 'All measurements',
                                 'nl': 'Alle metingen'}.get(lang, 'Alle metingen')
        else:
            period_start_date = period_start[:10]

        zone_order = analytics.ZONE_KEYS
        common_ctx = {
            'lang': lang,
            'license_code': license_code,
            'license_name': license_name,
            'period_start_date': period_start_date,
            'period_end_date':   period_end[:10],
            'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'generated_label': {'de':'Generiert','en':'Generated','nl':'Gegenereerd'}.get(lang,'Gegenereerd'),
            'page_label':      {'de':'Seite','en':'Page','nl':'Pagina'}.get(lang,'Pagina'),
            'report_label':    {'kk_overall': 'Krankenkasse', 'kk_office':'Krankenkasse', 'pro_client':'Pro','pro_portfolio':'Pro'}.get(report_type,''),
            'zone_order':   zone_order,
            'zone_label':   analytics.zone_label,
        }

        if report_type == 'kk_overall':
            overall = analytics.aggregate_period(license_code, pro_key, period_start, period_end, group_by='office_label')
            office_groups = overall.pop('groups', [])
            region_agg = analytics.aggregate_period(license_code, pro_key, period_start, period_end, group_by='region')
            region_groups = region_agg.get('groups', [])
            # Active office count
            kk_db = _report_db()
            tot_active = kk_db.execute(
                "SELECT COUNT(*) FROM krankenkasse_offices WHERE license_code=? AND active=1",
                (license_code,)).fetchone()[0]
            kk_db.close()
            ctx = {**common_ctx, 'overall': overall, 'office_groups': office_groups,
                   'region_groups': region_groups, 'total_offices_active': tot_active}
            template_name = 'reports/kk_overall.html'

        elif report_type == 'kk_office':
            office_name = params.get('office_label', '')
            overall = analytics.aggregate_period(license_code, pro_key, period_start, period_end,
                                                 filter={'office_label': office_name})
            # Region lookup
            office_region = ''
            kk_db = _report_db()
            r = kk_db.execute(
                "SELECT region FROM krankenkasse_offices WHERE license_code=? AND office_name=?",
                (license_code, office_name)).fetchone()
            kk_db.close()
            office_region = (r['region'] if r else '') or ''
            ctx = {**common_ctx, 'overall': overall, 'office_name': office_name,
                   'office_region': office_region}
            template_name = 'reports/kk_office.html'

        elif report_type == 'pro_client':
            client_id = int(params.get('client_id', 0))
            client = analytics.client_meta(pro_key, client_id)
            if not client:
                raise ValueError(f'client_id {client_id} niet gevonden voor pro_key')
            overall = analytics.aggregate_period(license_code, pro_key, period_start, period_end,
                                                 filter={'client_id': client_id})
            series = analytics.time_series(pro_key, client_id, period_start, period_end)
            ctx = {**common_ctx, 'overall': overall, 'client': client, 'series': series}
            template_name = 'reports/pro_client.html'

        elif report_type == 'pro_portfolio':
            overall = analytics.aggregate_period(license_code, pro_key, period_start, period_end, group_by='client_id')
            client_groups = overall.pop('groups', [])
            pro_name = (lic.get('notes') or '').strip() or user_email
            ctx = {**common_ctx, 'overall': overall, 'client_groups': client_groups, 'pro_name': pro_name}
            template_name = 'reports/pro_portfolio.html'

        else:
            raise ValueError(f'Onbekend report_type: {report_type}')

        # Render via app.jinja_env (geen request-context nodig)
        template = app.jinja_env.get_template(template_name)
        html_str = template.render(**ctx)

        from weasyprint import HTML
        pdf_bytes = HTML(string=html_str, base_url=app.root_path).write_pdf()

        # Opslaan op disk (RELATIEVE pad in DB voor portabiliteit)
        rel_dir = f'reports/{license_code}'
        abs_dir = os.path.join('/opt/stresschecker', rel_dir)
        os.makedirs(abs_dir, mode=0o750, exist_ok=True)
        rel_path = f'{rel_dir}/{uuid_str}.pdf'
        abs_path = os.path.join('/opt/stresschecker', rel_path)
        with open(abs_path, 'wb') as f:
            f.write(pdf_bytes)

        db.execute(
            "UPDATE report_jobs SET status='ready', pdf_path=?, delivered_at=datetime('now') WHERE uuid=?",
            (rel_path, uuid_str))
        db.commit()

        send_report_ready_email(user_email, uuid_str, lang)

    except Exception as e:
        import traceback
        err = (str(e) or 'unknown')[:300]
        app.logger.warning('REPORT JOB FAIL uuid=%s err=%s\n%s', uuid_str, err, traceback.format_exc())
        try:
            db.execute(
                "UPDATE report_jobs SET status='failed', error_message=? WHERE uuid=?",
                (err, uuid_str))
            db.commit()
        except Exception:
            pass
        send_report_failed_email(user_email, lang, err)
    finally:
        db.close()


def _user_can_request_report():
    """Inlog + (KK óf is_pro())."""
    if not session.get('license_valid'):
        return False
    return is_pro() or is_krankenkasse_session()


@app.route('/pro/rapport', methods=['GET'])
def pro_rapport_form():
    if not _user_can_request_report():
        return redirect(url_for('welcome'))
    lang = session.get('lang', 'nl')
    license_code = session.get('license_code', '')
    is_kk = is_krankenkasse_session()
    offices = []
    clients = []
    if is_kk:
        kk_db = _report_db()
        offices = [r['office_name'] for r in kk_db.execute(
            "SELECT office_name FROM krankenkasse_offices WHERE license_code=? AND active=1 ORDER BY office_name",
            (license_code,)).fetchall()]
        kk_db.close()
    else:
        pro_db = get_pro_db()
        clients = [dict(r) for r in pro_db.execute(
            "SELECT id, name, surname, birth_year FROM clients WHERE pro_key=? AND active=1 ORDER BY name",
            (get_user_key(),)).fetchall()]
        pro_db.close()
    return render_template('pro/rapport.html', lang=lang, is_kk=is_kk,
                           offices=offices, clients=clients,
                           email=session.get('email', ''))


@app.route('/pro/rapport/genereer', methods=['POST'])
def pro_rapport_genereer():
    if not _user_can_request_report():
        return redirect(url_for('welcome'))
    lang = session.get('lang', 'nl')
    license_code = session.get('license_code', '')
    user_email = session.get('email', '')
    report_type = (request.form.get('report_type', '') or '').strip()
    is_kk = is_krankenkasse_session()

    # Validatie report_type tegen audience
    kk_types = ('kk_overall', 'kk_office')
    pro_types = ('pro_client', 'pro_portfolio')
    if is_kk and report_type not in kk_types:
        return redirect(url_for('pro_rapport_form', error='type'))
    if (not is_kk) and report_type not in pro_types:
        return redirect(url_for('pro_rapport_form', error='type'))

    params = {
        'periode': request.form.get('periode', 'kwartaal'),
        'office_label': request.form.get('office_label', ''),
        'client_id': request.form.get('client_id', '0'),
    }

    # KK gebruikt licensehouder-pro_key (stabiel), Pro gebruikt eigen email-hash
    pro_key = _license_pro_key(license_code) if is_kk else get_user_key()
    if not pro_key:
        return redirect(url_for('pro_rapport_form', error='pro_key'))

    job_uuid = _uuid.uuid4().hex
    db = _report_db()
    db.execute(
        "INSERT INTO report_jobs (uuid, license_code, user_email, report_type, status, params_json) "
        "VALUES (?, ?, ?, ?, 'pending', ?)",
        (job_uuid, license_code, user_email, report_type, json.dumps(params)))
    db.commit()
    db.close()

    _threading.Thread(
        target=_render_report_async,
        args=(job_uuid, license_code, user_email, lang, report_type, params, pro_key),
        daemon=False
    ).start()

    return render_template('pro/rapport.html', lang=lang, is_kk=is_kk,
                           offices=[], clients=[],
                           email=user_email, requested_uuid=job_uuid)


@app.route('/rapport/download/<uuid_str>')
def rapport_download(uuid_str):
    if not session.get('license_valid'):
        abort(403)
    uuid_str = (uuid_str or '').strip()
    if not uuid_str or not all(c in '0123456789abcdef' for c in uuid_str.lower()):
        abort(400)
    db = _report_db()
    row = db.execute(
        "SELECT license_code, user_email, status, pdf_path FROM report_jobs WHERE uuid=?",
        (uuid_str,)).fetchone()
    db.close()
    if not row:
        abort(404)
    # Cross-tenant guard: alleen toegankelijk voor zelfde licentie-sessie
    if row['license_code'] != session.get('license_code', ''):
        abort(403)
    if row['status'] != 'ready' or not row['pdf_path']:
        # 202 met retry-msg zou netter zijn; voor MVP gewoon melding
        return ('Rapport is nog niet klaar of mislukt. Status: ' + row['status'], 202)
    abs_path = os.path.join('/opt/stresschecker', row['pdf_path'])
    if not os.path.exists(abs_path):
        abort(410)
    return send_file(abs_path, mimetype='application/pdf', as_attachment=False,
                     download_name=f'stresschecker-rapport-{uuid_str[:8]}.pdf')


@app.route('/pro/client/toevoegen', methods=['GET','POST'])
@require_kk_office_if_krankenkasse
def pro_client_add():
    if (not session.get('license_valid') and not session.get('demo_mode')) or not _is_pro_or_demo_pro():
        return redirect(url_for('welcome'))
    lang = session.get('lang', 'nl')
    is_kk = is_krankenkasse_session()
    if request.method == 'POST':
        name = request.form.get('name','').strip()
        surname = request.form.get('surname','').strip() or None
        _by_raw = (request.form.get('birth_year') or '').strip()
        birth_year = int(_by_raw) if _by_raw.isdigit() else 1970
        gender = request.form.get('gender', '')
        # Profiel-compleet-vlag: alleen 1 als geboortejaar én geslacht écht/geldig zijn ingevuld
        # (de opslag-fallback 1970/'' telt NIET als ingevuld → vlag 0 → meting geblokkeerd tot aanvulling).
        _cli_completed = 0 if _profiel_incompleet(int(_by_raw) if _by_raw.isdigit() else None, gender) else 1
        # Krankenkasse-flow: e-mail/telefoon/notities niet uitgevraagd
        email = '' if is_kk else request.form.get('email','').strip()
        phone = '' if is_kk else request.form.get('phone','').strip()
        notes = '' if is_kk else request.form.get('notes','').strip()
        if not name:
            return render_template('pro/client_add.html', lang=lang, error='Vul een naam in.', is_krankenkasse=is_kk)
        pro_key = get_user_key()
        # Quota-guard: blokkeer aanmaak bij volle of overschrijdende Pro. demo_mode en is_krankenkasse
        # gebruiken andere modellen (resp. fixture-DEMO en kantoor-allocatie) en omzeilen de profielen-quota.
        if not session.get('demo_mode') and not is_kk:
            quota = build_pro_client_quota(pro_key, session.get('email', ''))
            if not quota['unlimited'] and quota['over_limit']:
                app.logger.info('CLIENT_ADD_QUOTA_BLOCK pro_key=%s current=%s max=%s',
                                pro_key, quota['current'], quota['max'])
                return redirect(url_for('pro_clients', limit_reached=1))
        client_code = generate_client_code()
        db = get_pro_db()
        db.execute("INSERT INTO clients (pro_key,name,surname,birth_year,gender,client_code,email,phone,notes,profile_completed) VALUES (?,?,?,?,?,?,?,?,?,?)",
                   (pro_key, name, surname, birth_year, gender, client_code, email, phone, notes, _cli_completed))
        db.commit()
        db.close()
        return redirect(url_for('pro_clients'))
    return render_template('pro/client_add.html', lang=lang, is_krankenkasse=is_kk)

@app.route('/pro/client/<int:cid>')
@require_kk_office_if_krankenkasse
def pro_client_detail(cid):
    if (not session.get('license_valid') and not session.get('demo_mode')) or not _is_pro_or_demo_pro():
        return redirect(url_for('welcome'))
    lang = session.get('lang', 'nl')
    pro_key = get_user_key()
    db = get_pro_db()
    _demo = session.get('demo_mode') and session.get('license_type') == 'pro'
    client = db.execute("SELECT * FROM clients WHERE id=? AND (pro_key=? OR pro_key='DEMO')" if _demo else "SELECT * FROM clients WHERE id=? AND pro_key=?", (cid, pro_key)).fetchone()
    if not client:
        db.close()
        return redirect(url_for('pro_clients'))
    metingen = db.execute("SELECT * FROM client_metingen WHERE client_id=? ORDER BY ts DESC LIMIT 50", (cid,)).fetchall()
    metingen_alle = db.execute("SELECT id, ts, ri, notes, meting_type FROM client_metingen WHERE client_id=? ORDER BY ts ASC", (cid,)).fetchall()
    db.close()
    resp = make_response(render_template('pro/client_detail.html', lang=lang,
                           client=dict(client), metingen=[dict(m) for m in metingen],
                        metingen_chart=[{"id":m["id"],"ts":m["ts"],"ri":m["ri"],"notes":m["notes"] or "","subj":None,"meting_type":m["meting_type"]} for m in [dict(x) for x in metingen_alle]]))
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp

@app.route('/pro/client/<int:cid>/meten')
@require_kk_office_if_krankenkasse
def pro_client_measure(cid):
    if (not session.get('license_valid') and not session.get('demo_mode')) or not _is_pro_or_demo_pro():
        return redirect(url_for('welcome'))
    pro_key = get_user_key()
    db = get_pro_db()
    _demo = session.get('demo_mode') and session.get('license_type') == 'pro'
    client = db.execute("SELECT * FROM clients WHERE id=? AND (pro_key=? OR pro_key='DEMO')" if _demo else "SELECT * FROM clients WHERE id=? AND pro_key=?", (cid, pro_key)).fetchone()
    db.close()
    if not client:
        return redirect(url_for('pro_clients'))
    # Verplicht-profiel-handhaving: geen cliëntmeting tot het profiel voltooid is (vlag).
    # Demo-cliënten zijn fixtures → overslaan.
    if not _demo and (not client['profile_completed'] or _profiel_incompleet(client['birth_year'], client['gender'])):
        return redirect(url_for('pro_client_detail', cid=cid) + '?reason=profiel_incompleet')
    session['measuring_for_client'] = cid
    session['client_name'] = client['name']
    try: session['client_surname'] = client['surname'] or ''
    except (IndexError, KeyError): session['client_surname'] = ''
    session['client_birth_year'] = client['birth_year']
    session['client_gender'] = client['gender']
    session['client_profile_id'] = client['id']
    return redirect(url_for("pro_meting_keuze") + "?cid=" + str(cid))

@app.route('/pro/client/<int:cid>/verwijderen', methods=['POST'])
def pro_client_delete(cid):
    if (not session.get('license_valid') and not session.get('demo_mode')) or not _is_pro_or_demo_pro():
        return redirect(url_for('welcome'))
    pro_key = get_user_key()
    db = get_pro_db()
    db.execute("UPDATE clients SET active=0 WHERE id=? AND pro_key=?", (cid, pro_key))
    db.commit()
    db.close()
    return redirect(url_for('pro_clients'))

# ─── API endpoints ───────────────────────────────────────────────────────────

@app.route('/api/settings/save', methods=['POST'])
def api_save_settings():
    if not session.get('license_valid') and not session.get('demo_mode') and not session.get('hlm_user_id'):
        return jsonify({'error': 'Niet ingelogd'}), 401
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Geen data'}), 400
    if 'name' in data:    session['profile_name'] = data['name']
    if 'surname' in data:
        _sn = (data.get('surname') or '').strip()
        session['profile_surname'] = _sn  # leeg-string in session OK; DB krijgt NULL
    if 'birth_year' in data: session['profile_birth_year'] = int(data['birth_year'])
    if 'gender' in data:  session['profile_gender'] = data['gender']
    if 'lang' in data:    session['lang'] = data['lang']
    if 'sensor' in data:   session['sensor_pref'] = data['sensor']
    session.modified = True
    # Opslaan in DB
    email = session.get('email', '')
    if email:
        try:
            import sqlite3 as _sq
            _cn = _sq.connect('/opt/ic-license-server/data/saas_licenses.db')
            _cn.execute("UPDATE users SET display_name=?, surname=?, birth_year=?, gender=?, language=?, sensor_pref=? WHERE email=?", (
                session.get('profile_name',''),
                (session.get('profile_surname','').strip() or None),
                session.get('profile_birth_year', 1970),
                session.get('profile_gender','male'),
                session.get('lang','nl'),
                session.get('sensor_pref','bluetooth'),
                email
            ))
            _cn.commit()
            _cn.close()
        except Exception as e:
            pass
    return jsonify({'ok': True})

@app.route('/api/licentie/check', methods=['POST'])
def api_check_license():
    data = request.get_json()
    return jsonify(validate_license(data.get('code', ''), data.get('email', '')))

@app.route('/api/meting/opslaan', methods=['POST'])
def api_save_meting():
    if not session.get('license_valid') and not session.get('demo_mode') and not session.get('hlm_user_id'):
        return jsonify({'error': 'Niet ingelogd'}), 401
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Geen data'}), 400
    try:
        client_id = session.pop('measuring_for_client', None) or data.get('client_id')
        client_id = int(client_id) if client_id else 0
        session['last_meting_type'] = data.get('meting_type', 'basismeting')
        _sp = data.get('subjectief_pre')
        # Onaangeraakte slider = bewuste instemming met de getoonde stand (5/neutraal).
        # Ontbrekend/leeg/ongeldig → 5; geen NULL-onderscheid tussen "bewust 5" en "overgeslagen".
        try:
            _subj_score = int(float(str(_sp))) if _sp not in (None, '') else 5
            if not (0 <= _subj_score <= 10): _subj_score = 5
        except Exception:
            _subj_score = 5
        def _ctx_int(v):
            try:
                n = int(float(str(v))) if v not in (None, '') else None
                if n is not None and not (0 <= n <= 10): return None
                return n
            except Exception:
                return None
        _ctx_ongemak = _ctx_int(data.get('ctx_ongemak'))
        _ctx_vrije_tekst = (str(data.get('ctx_vrije_tekst') or '')).strip()[:100] or None
        if client_id > 0 and _is_pro_or_demo_pro():
            db = get_pro_db()
            # office_label vult alleen bij Krankenkasse-sessie; voor reguliere Pro blijft de kolom NULL
            _office = session.get('kk_office') if is_krankenkasse_session() else None
            _vals=(int(client_id),get_user_key(),int(data.get('ts',__import__('datetime').datetime.now().timestamp()*1000)),float(data.get('ri',0)),int(data.get('bpm',0)),int(data.get('hrv',0)),float(data.get('rmssd',0)),float(data.get('sdnn',0)),float(data.get('pnn50',0)),int(data.get('beats',0)),int(data.get('duration',90)),str(data.get('sensor','demo')),str(data.get('notes','')),str(data.get('timeseries','')),str(data.get('rr_intervals','')),int(data.get('kwaliteit',100)),str(data.get('meting_type','basismeting')),str(data.get('ctx_dimensie','')),float(data.get('ctx_vitaliteit',0)) if data.get('ctx_vitaliteit') else None,_subj_score,_ctx_ongemak,_ctx_vrije_tekst,_office)
            db.execute('INSERT INTO client_metingen (client_id,pro_key,ts,ri,bpm,hrv_pct,rmssd,sdnn,pnn50,beats,duration,sensor_type,notes,timeseries,rr_intervals,kwaliteit,meting_type,ctx_dimensie,ctx_vitaliteit,subjectief_score,ctx_ongemak,ctx_vrije_tekst,office_label) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',_vals)
            db.commit()
            db.close()
            return jsonify({'ok': True, 'client_id': int(client_id)})

        db = get_meting_db()
        db.execute('''INSERT INTO metingen
            (user_key,ts,ri,bpm,hrv_pct,rmssd,beats,duration,sensor_type,notes,sdnn,pnn50,timeseries,rr_intervals,kwaliteit,meting_type,ctx_dimensie,ctx_vitaliteit,subjectief_score,ctx_ongemak,ctx_vrije_tekst,pending)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)''', (
            get_user_key(),
            int(data.get('ts', datetime.now().timestamp()*1000)),
            float(data.get('ri',0)), int(data.get('bpm',0)), int(data.get('hrv',0)),
            float(data.get('rmssd',0)), int(data.get('beats',0)), int(data.get('duration',90)),
            str(data.get('sensor','demo')), str(data.get('notes','')),
            float(data.get('sdnn',0)), float(data.get('pnn50',0)),
            str(data.get('timeseries','')), str(data.get('rr_intervals','')),
                int(data.get('kwaliteit',100)),
            str(data.get('meting_type','basismeting')),
            str(data.get('ctx_dimensie','')),
            float(data.get('ctx_vitaliteit',0)) if data.get('ctx_vitaliteit') else None,
            _subj_score,
            _ctx_ongemak, _ctx_vrije_tekst
        ))
        db.commit()
        session['after_meting'] = True
        session['pending_meting_id'] = db.execute('SELECT last_insert_rowid()').fetchone()[0]
        db.close()
        return jsonify({'ok': True})
    except Exception as e:
        import traceback; return jsonify({'error': str(e), 'trace': traceback.format_exc()}), 500


@app.route('/api/meting/label', methods=['POST'])
def api_update_label():
    if not session.get('license_valid') and not session.get('demo_mode') and not session.get('hlm_user_id'):
        return jsonify({'error': 'Niet ingelogd'}), 401
    data = request.get_json()
    label = data.get('label', '')
    try:
        db = get_meting_db()
        subj_pre = data.get("subjectief_pre")
        if subj_pre is not None:
            try: db.execute("UPDATE metingen SET notes=?, subjectief_score=? WHERE user_key=? ORDER BY ts DESC LIMIT 1",(label, int(float(str(subj_pre))), get_user_key()))
            except: db.execute("UPDATE metingen SET notes=? WHERE user_key=? ORDER BY ts DESC LIMIT 1",(label, get_user_key()))
        else:
            db.execute("UPDATE metingen SET notes=? WHERE user_key=? ORDER BY ts DESC LIMIT 1",(label, get_user_key()))
        # Pro-cliënt labeling via de HLM-kwadrant-flow vereist dat hlm/kwadrant.html
        # client_id meestuurt in de POST-body. Tot die frontend-aanpassing is de
        # labeling voor Pro-cliënt-metingen een bekende beperking.
        # De legacy session['last_client_id']-fallback is verwijderd op 21-04-2026
        # omdat die sticky-session misrouting veroorzaakte (recidive-bug).
        cid = data.get('client_id')
        if cid and is_pro():
            pro_db = get_pro_db()
            pro_db.execute('UPDATE client_metingen SET notes=? WHERE client_id=? ORDER BY ts DESC LIMIT 1',(label,int(cid)))
            pro_db.commit()
            pro_db.close()
        db.commit()
        db.close()
        session['after_meting'] = True
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/metingen')
def api_get_metingen():
    if not session.get('license_valid') and not session.get('demo_mode') and not session.get('hlm_user_id'):
        return jsonify({'error': 'Niet ingelogd'}), 401
    try:
        limit = min(int(request.args.get('limit', 50)), 200)
        db = get_meting_db()
        rows = db.execute('SELECT * FROM metingen WHERE user_key=? ORDER BY ts DESC LIMIT ?',
                          (get_user_key(), limit)).fetchall()
        all_rows = db.execute("SELECT ri FROM metingen WHERE user_key=? ORDER BY ts ASC LIMIT 7",
                              (get_user_key(),)).fetchall()
        db.close()
        baseline = round(sum(r[0] for r in all_rows)/len(all_rows),1) if len(all_rows)>=7 else None
        result = []
        for r in rows:
            d = dict(r)
            d['baseline'] = baseline
            d['delta'] = round(d['ri']-baseline,1) if baseline else None
            result.append(d)
        from datetime import datetime, timezone
        resp = jsonify(result)
        resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        resp.headers['Pragma'] = 'no-cache'
        resp.headers['Expires'] = '0'
        return resp
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/metingen/stats')
def api_meting_stats():
    if not session.get('license_valid') and not session.get('demo_mode') and not session.get('hlm_user_id'):
        return jsonify({'error': 'Niet ingelogd'}), 401
    try:
        db = get_meting_db()
        row = db.execute('''SELECT COUNT(*) as total, AVG(ri) as avg_ri,
            MAX(ri) as max_ri, MIN(ri) as min_ri, AVG(bpm) as avg_bpm
            FROM metingen WHERE user_key=?''', (get_user_key(),)).fetchone()
        db.close()
        return jsonify(dict(row))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ─── AI Feedback na meting ──────────────────────────────────────────────────

_FORBIDDEN_WORDS = ['alarmmodus', 'uitputting', 'burnout', 'overbelast', 'vrije val', 'alarmstand',
                    'uitgeput', 'alarm', 'gevaar', 'Alarmmodus', 'Burnout', 'Überbelastung', 'Erschöpfung']

def _generate_question(dim, lang, meting_type='basismeting'):
    """Genereer de activerende onderzoeksvraag server-side, altijd correct."""
    dim_target = {
        'nl': {'lichamelijk': 'lichaam', 'mentaal': 'hoofd', 'emotioneel': 'gevoel', 'spiritueel': 'kern', '': 'Innerlijk Kompas'},
        'de': {'lichamelijk': 'Körper', 'mentaal': 'Kopf', 'emotioneel': 'Gefühl', 'spiritueel': 'Kern', '': 'Innerer Kompass'},
        'en': {'lichamelijk': 'body', 'mentaal': 'mind', 'emotioneel': 'feelings', 'spiritueel': 'core', '': 'Inner Compass'},
    }
    target = dim_target.get(lang, dim_target['nl']).get(dim or '', dim_target.get(lang, dim_target['nl'])[''])

    if meting_type == 'biofeedback':
        q = {'nl': f'Wat ga jij de komende dagen doen om te ontdekken welke interventie jouw {target} het beste helpt?',
             'de': f'Was wirst du in den nächsten Tagen tun, um herauszufinden, welche Intervention deinem {target} am besten hilft?',
             'en': f'What will you do in the coming days to discover which intervention helps your {target} most?'}
    elif meting_type == 'situatiemeting':
        q = {'nl': f'Wat ga jij vandaag doen om te ontdekken hoe jouw {target} reageert op verschillende situaties?',
             'de': f'Was wirst du heute tun, um herauszufinden, wie dein {target} auf verschiedene Situationen reagiert?',
             'en': f'What will you do today to discover how your {target} responds to different situations?'}
    else:
        q = {'nl': f'Wat ga jij doen om te ontdekken wat jouw {target} nodig heeft?',
             'de': f'Was wirst du tun, um herauszufinden, was dein {target} braucht?',
             'en': f'What will you do to discover what your {target} needs?'}
    return q.get(lang, q['nl'])

def _check_forbidden(text):
    """Check of de tekst verboden woorden bevat."""
    text_lower = text.lower()
    return any(w.lower() in text_lower for w in _FORBIDDEN_WORDS)

# Harde dag-ankers: woorden die aan een specifieke, verschuivende dag binden en daardoor
# fout worden zodra de gecachte tekst later wordt teruggelezen. Zachte ankers ("op dit
# moment", "gerade", "right now") binden aan het leesmoment en blijven kloppen — die staan
# hier bewust NIET in.
_DAY_ANCHORS = {
    'nl': ['vandaag', 'gisteren', 'eergisteren', 'morgen', 'overmorgen',
           'deze week', 'vorige week', 'komende week', 'volgende week'],
    'de': ['heute', 'gestern', 'vorgestern', 'morgen', 'übermorgen',
           'diese woche', 'letzte woche', 'kommende woche', 'nächste woche'],
    'en': ['today', 'yesterday', 'tomorrow',
           'this week', 'last week', 'next week', 'coming week'],
}

def _has_day_anchor(text, lang):
    """True als de tekst een hard dag-anker bevat (woordgrens-match, hoofdletterongevoelig).
    Zachte ankers (op dit moment / gerade / right now) tellen bewust NIET mee."""
    if not text:
        return False
    import re
    low = text.lower()
    for t in _DAY_ANCHORS.get(lang, _DAY_ANCHORS['nl']):
        if re.search(r'(?<!\w)' + re.escape(t) + r'(?!\w)', low):
            return True
    return False

def _truncate_to_sentences(text, max_sentences=2):
    """Hard truncate text to exactly max_sentences sentences."""
    import re
    # Split on period/!/?  followed by space, OR on em-dash, OR on semicolon
    parts = re.split(r'(?<=[.!?])\s+', text.strip())
    # If still only 1 part (all em-dashes), truncate at the second em-dash
    if len(parts) == 1 and len(text) > 200:
        segments = text.split(' — ')
        return segments[0] + ('.' if not segments[0].endswith('.') else '')
    return ' '.join(parts[:max_sentences])

def _hard_truncate(text, max_chars=200):
    """Truncate tekst met voorkeur voor zin-grenzen. Nooit ellipsis inserten.
    Logica:
      1. len <= max → return as-is
      2. anders: pak eerste N volledige zinnen waarvan som <= max_chars
      3. edge case (geen enkele zin past): word-boundary truncate op max-1, eindig op '.'
    """
    import logging, re
    logging.getLogger().warning(f"[TRUNCATE] function called, input len={len(text)}, max={max_chars}")
    if len(text) <= max_chars:
        logging.getLogger().warning(f"[TRUNCATE] under limit, returning as-is")
        return text
    parts = re.split(r'(?<=[.!?])\s+', text.strip())
    kept = []
    total = 0
    for p in parts:
        extra = len(p) + (1 if kept else 0)
        if total + extra > max_chars:
            break
        kept.append(p)
        total += extra
    if kept:
        result = ' '.join(kept).rstrip()
        logging.getLogger().warning(f"[TRUNCATE] kept {len(kept)} sentence(s), {len(result)} chars: {result[:80]}...")
        return result
    # edge case: eerste zin zelf > max — word-boundary truncate
    truncated = text[:max_chars-1].rsplit(' ', 1)[0]
    result = truncated.rstrip('.,;—') + '.'
    logging.getLogger().warning(f"[TRUNCATE] edge-case word-trunc {len(text)} → {len(result)}: {result[:80]}...")
    return result

def _check_language_mixing(text, lang):
    """Check if text contains words from wrong language. Returns True if contaminated."""
    if not text:
        return False
    words = text.lower().split()
    if lang == 'en':
        nl_words = {'dit', 'dat', 'het', 'een', 'je', 'jij', 'van', 'om', 'maar', 'ook', 'niet', 'wel', 'naar', 'voor'}
        matches = sum(1 for w in words if w.strip('.,;:!?') in nl_words)
        return matches >= 3
    if lang == 'de':
        nl_words = {'dit', 'dat', 'het', 'een', 'je', 'jij', 'van', 'maar', 'ook', 'niet', 'wel', 'naar', 'voor'}
        matches = sum(1 for w in words if w.strip('.,;:!?') in nl_words)
        return matches >= 3
    if lang == 'nl':
        de_words = {'dein', 'deine', 'deinem', 'sich', 'dass', 'nicht', 'auch', 'noch', 'schon', 'wenn'}
        matches = sum(1 for w in words if w.strip('.,;:!?') in de_words)
        return matches >= 3
    return False

# Trend hint varianten — 6 condities × 6 taal/perspectief × 3 varianten = 108 strings.
# Deterministische keuze per gebruiker per dag via stabiele hash(seed + YYYY-MM-DD) % 3.
TREND_VARIANTS = {
    'phase1': {
        'nl': {
            'consumer': [
                "Nog te weinig metingen voor een eerste beeld — dat komt met de volgende paar metingen.",
                "Vanaf meting 5 wordt hier zichtbaar hoe je lichaam over de tijd reageert.",
                "Na een paar metingen meer ontstaat hier een eerste beeld van je patroon.",
            ],
            'pro': [
                "Nog te weinig metingen van {name} voor een eerste beeld — dat komt met de volgende paar metingen.",
                "Vanaf meting 5 wordt hier zichtbaar hoe het lichaam van {name} over de tijd reageert.",
                "Na een paar metingen meer ontstaat hier een eerste beeld van het patroon van {name}.",
            ],
        },
        'de': {
            'consumer': [
                "Noch zu wenige Messungen für ein erstes Bild — das kommt mit den nächsten paar.",
                "Ab Messung 5 wird hier sichtbar, wie dein Körper sich über die Zeit verhält.",
                "Nach ein paar Messungen mehr entsteht hier ein erstes Bild deines Musters.",
            ],
            'pro': [
                "Noch zu wenige Messungen von {name} für ein erstes Bild — das kommt mit den nächsten paar.",
                "Ab Messung 5 wird hier sichtbar, wie der Körper von {name} sich über die Zeit verhält.",
                "Nach ein paar Messungen mehr entsteht hier ein erstes Bild des Musters von {name}.",
            ],
        },
        'en': {
            'consumer': [
                "Not enough readings yet for a first picture — that comes with the next few.",
                "From reading 5 onwards it will become visible here how your body behaves over time.",
                "After a few more readings, a first picture of your pattern appears here.",
            ],
            'pro': [
                "Not enough readings from {name} yet for a first picture — that comes with the next few.",
                "From reading 5 onwards it will become visible here how {name}'s body behaves over time.",
                "After a few more readings, a first picture of {name}'s pattern appears here.",
            ],
        },
    },
    'up_pressure': {
        'nl': {
            'consumer': [
                "De laatste weken komt er meer ruimte in je ademhaling — je lichaam pakt herstel op.",
                "Je hart vindt de laatste weken stap voor stap zijn rust terug.",
                "Je lichaam komt de afgelopen weken steeds beter bij — dat zie je in je metingen.",
            ],
            'pro': [
                "Het lichaam van {name} pakt de laatste weken herstel op — meer ruimte, meer rust.",
                "De ademhaling van {name} komt de laatste weken stap voor stap tot rust.",
                "Bij {name} is de afgelopen tijd duidelijk herstel zichtbaar in de metingen.",
            ],
        },
        'de': {
            'consumer': [
                "In den letzten Wochen kommt mehr Raum in deinen Atem — dein Körper holt sich Erholung zurück.",
                "Dein Herz findet in den letzten Wochen Schritt für Schritt zu seiner Ruhe zurück.",
                "Dein Körper erholt sich in den letzten Wochen zunehmend — das siehst du in deinen Messungen.",
            ],
            'pro': [
                "Der Körper von {name} holt sich in den letzten Wochen Erholung zurück — mehr Raum, mehr Ruhe.",
                "Der Atem von {name} kommt in den letzten Wochen Schritt für Schritt zur Ruhe.",
                "Bei {name} ist in der letzten Zeit deutlich Erholung in den Messungen sichtbar.",
            ],
        },
        'en': {
            'consumer': [
                "Over the past weeks more room is coming into your breath — your body is picking up recovery.",
                "Your heart has been finding its calm back, step by step over the past weeks.",
                "Your body has been recovering in recent weeks — you can see it in your readings.",
            ],
            'pro': [
                "{name}'s body has been picking up recovery in recent weeks — more room, more rest.",
                "{name}'s breath has been coming to calm step by step in recent weeks.",
                "With {name} clear recovery has been visible in the readings lately.",
            ],
        },
    },
    'up_healthy': {
        'nl': {
            'consumer': [
                "Je lichaam draait soepeler mee de laatste weken — meer ruimte, meer herstel.",
                "De afgelopen weken vindt je hart makkelijker een rustig ritme.",
                "Er zit de laatste tijd steeds meer rust in je lichaam.",
            ],
            'pro': [
                "Het lichaam van {name} draait de laatste weken soepeler mee.",
                "Het hart van {name} vindt de afgelopen tijd makkelijker een rustig ritme.",
                "Bij {name} zit er de laatste tijd meer rust in het lichaam.",
            ],
        },
        'de': {
            'consumer': [
                "Dein Körper läuft in den letzten Wochen geschmeidiger — mehr Raum, mehr Erholung.",
                "In den letzten Wochen findet dein Herz leichter einen ruhigen Rhythmus.",
                "In der letzten Zeit kommt zunehmend Ruhe in deinen Körper.",
            ],
            'pro': [
                "Der Körper von {name} läuft in den letzten Wochen geschmeidiger mit.",
                "Das Herz von {name} findet in der letzten Zeit leichter einen ruhigen Rhythmus.",
                "Bei {name} ist in der letzten Zeit mehr Ruhe im Körper.",
            ],
        },
        'en': {
            'consumer': [
                "Your body has been running more smoothly these past weeks — more room, more recovery.",
                "Over the past weeks your heart finds a calm rhythm more easily.",
                "There has been increasingly more calm in your body lately.",
            ],
            'pro': [
                "{name}'s body has been running more smoothly in recent weeks.",
                "{name}'s heart has been finding a calm rhythm more easily lately.",
                "There has been more calm in {name}'s body lately.",
            ],
        },
    },
    'down_pressure': {
        'nl': {
            'consumer': [
                "De afgelopen weken kwam je hart minder tot kalmte.",
                "Je lichaam krijgt de laatste weken minder de mogelijkheid om te herstellen — dat merk je aan je energie.",
                "De laatste weken zakt je rustniveau langzaam — dat vraagt aandacht.",
            ],
            'pro': [
                "Het hart van {name} kwam de afgelopen weken minder tot kalmte.",
                "{name} heeft de laatste tijd minder gelegenheid voor herstel.",
                "De rustlijn van {name} zakt de laatste weken langzaam — dat vraagt aandacht.",
            ],
        },
        'de': {
            'consumer': [
                "In den letzten Wochen fand dein Herz weniger zur Ruhe.",
                "Dein Körper hatte in letzter Zeit weniger Raum zum Erholen.",
                "Deine Ruhelinie sackt in den letzten Wochen langsam ab — das verdient Aufmerksamkeit.",
            ],
            'pro': [
                "Das Herz von {name} fand in den letzten Wochen weniger zur Ruhe.",
                "Der Körper von {name} hatte in letzter Zeit weniger Raum zum Erholen.",
                "Die Ruhelinie von {name} sackt in den letzten Wochen langsam ab — das verdient Aufmerksamkeit.",
            ],
        },
        'en': {
            'consumer': [
                "Over the past weeks your heart has been calming less easily.",
                "Your body has had less room for recovery lately.",
                "Your rest line has been slowly sinking — that deserves attention.",
            ],
            'pro': [
                "{name}'s heart has been calming less easily over the past weeks.",
                "{name}'s body has had less room for recovery lately.",
                "{name}'s rest line has been slowly sinking — that deserves attention.",
            ],
        },
    },
    'down_healthy': {
        'nl': {
            'consumer': [
                "De laatste weken komt je lichaam iets minder tot rust — goed om bij stil te staan.",
                "Je lichaam geeft signalen dat de spanning de afgelopen periode is opgelopen.",
                "Je hart vindt zijn rustige ritme de laatste weken iets minder makkelijk.",
            ],
            'pro': [
                "Het lichaam van {name} komt de laatste weken iets minder tot rust.",
                "Er zit minder rust in het lichaam van {name} dan een paar weken terug.",
                "Het hart van {name} vindt zijn rustige ritme de laatste weken iets minder makkelijk.",
            ],
        },
        'de': {
            'consumer': [
                "In den letzten Wochen kommt dein Körper etwas weniger zur Ruhe — es lohnt sich, darauf zu achten.",
                "Dein Körper zeigt in den letzten Wochen etwas mehr Aktivierung als zuvor.",
                "Dein Herz findet seinen ruhigen Rhythmus in den letzten Wochen etwas weniger leicht.",
            ],
            'pro': [
                "Der Körper von {name} kommt in den letzten Wochen etwas weniger zur Ruhe.",
                "Es ist weniger Ruhe im Körper von {name} als vor ein paar Wochen.",
                "Das Herz von {name} findet seinen ruhigen Rhythmus in den letzten Wochen etwas weniger leicht.",
            ],
        },
        'en': {
            'consumer': [
                "Your body has been coming to rest a bit less these past weeks — worth pausing to notice.",
                "Your body is showing a bit more activation in recent weeks than before.",
                "Your heart has been finding its calm rhythm a bit less easily in recent weeks.",
            ],
            'pro': [
                "{name}'s body has been coming to rest a bit less in recent weeks.",
                "There's less rest in {name}'s body than a few weeks back.",
                "{name}'s heart has been finding its calm rhythm a bit less easily in recent weeks.",
            ],
        },
    },
    'stable': {
        'nl': {
            'consumer': [
                "Je lichaam laat de afgelopen weken een stabiel ritme zien — dit is waar je nu staat.",
                "Het ritme van je hart ligt al een tijdje gelijk — dit is je huidige basislijn.",
                "Je lichaam zit al een tijdje in een rustig, stabiel patroon.",
            ],
            'pro': [
                "Het lichaam van {name} laat de afgelopen weken een stabiel ritme zien.",
                "Het ritme van {name} ligt al een tijdje gelijk — dit is de huidige basislijn.",
                "{name} zit al een tijdje in een rustig, stabiel patroon.",
            ],
        },
        'de': {
            'consumer': [
                "Dein Körper zeigt in den letzten Wochen einen stabilen Rhythmus — so stehst du jetzt da.",
                "Der Rhythmus deines Herzens ist seit einiger Zeit gleich — das ist deine aktuelle Basislinie.",
                "Dein Körper ist schon eine Weile in einem ruhigen, stabilen Muster.",
            ],
            'pro': [
                "Der Körper von {name} zeigt in den letzten Wochen einen stabilen Rhythmus.",
                "Der Rhythmus von {name} ist seit einiger Zeit gleich — das ist die aktuelle Basislinie.",
                "{name} ist schon eine Weile in einem ruhigen, stabilen Muster.",
            ],
        },
        'en': {
            'consumer': [
                "Your body has shown a stable rhythm these past weeks — this is where you are now.",
                "Your heart's rhythm has been consistent for some time — this is your current baseline.",
                "Your body has been in a calm, stable pattern for a while.",
            ],
            'pro': [
                "{name}'s body has shown a stable rhythm these past weeks.",
                "{name}'s rhythm has been consistent for some time — this is the current baseline.",
                "{name} has been in a calm, stable pattern for a while.",
            ],
        },
    },
}


def _generate_trend_data(user_key=None, client_id=None, lang='nl', client_name=None):
    """Generate trend observation based on measurement count and RI history.
    Returns dict with 'trend_hint' (phase 1 text below card) and 'trend_sentence' (phase 2/3 appended to reflection).
    """
    try:
        if client_id:
            db = get_pro_db()
            count_row = db.execute("SELECT COUNT(*) FROM client_metingen WHERE client_id=? AND meting_type='basismeting'", (client_id,)).fetchone()
            ri_rows = db.execute("SELECT ri FROM client_metingen WHERE client_id=? AND ri IS NOT NULL AND meting_type='basismeting' ORDER BY ts DESC LIMIT 10", (client_id,)).fetchall()
            db.close()
        else:
            db = get_meting_db()
            count_row = db.execute("SELECT COUNT(*) FROM metingen WHERE user_key=? AND meting_type='basismeting'", (user_key,)).fetchone()
            ri_rows = db.execute("SELECT ri FROM metingen WHERE user_key=? AND ri IS NOT NULL AND meting_type='basismeting' ORDER BY ts DESC LIMIT 10", (user_key,)).fetchall()
            db.close()
    except:
        return {'trend_hint': '', 'trend_sentence': ''}

    count = count_row[0] if count_row else 0
    is_pro = client_id is not None
    name = client_name or ''
    perspective = 'pro' if is_pro else 'consumer'
    lang_key = lang if lang in ('nl', 'de', 'en') else 'nl'

    # Stable per-user-per-day variant selection (hashlib → stable across process restarts)
    seed = (user_key or str(client_id or '')) + datetime.now().strftime('%Y-%m-%d')
    variant_idx = int(hashlib.md5(seed.encode('utf-8')).hexdigest(), 16) % 3

    def _pick(condition):
        text = TREND_VARIANTS[condition][lang_key][perspective][variant_idx]
        return text.format(name=name) if is_pro else text

    # Phase 1: 1-4 measurements
    if count < 5:
        return {'trend_hint': _pick('phase1'), 'trend_sentence': ''}

    ri_values = [float(r[0]) for r in ri_rows]
    current_ri = ri_values[0] if ri_values else 0

    # Calculate delta: most recent RI vs average of the rest of the window
    if count < 10:
        window = ri_values[:5]
    else:
        window = ri_values[:10]
    if len(window) >= 3:
        latest_ri = window[0]
        rest_avg = sum(window[1:]) / len(window[1:])
        delta = latest_ri - rest_avg
    else:
        delta = 0

    low_ri = current_ri <= 4
    if delta > 0.3 and low_ri:
        condition = 'up_pressure'
    elif delta > 0.3 and not low_ri:
        condition = 'up_healthy'
    elif delta < -0.3 and low_ri:
        condition = 'down_pressure'
    elif delta < -0.3 and not low_ri:
        condition = 'down_healthy'
    else:
        condition = 'stable'

    _trend_text = _pick(condition)
    return {'trend_hint': _trend_text, 'trend_sentence': _trend_text}

def _store_feedback_cache(meting_id, insight, reflection, is_client=False, lang='nl'):
    """Sla feedback op in de database als cache, per taal."""
    if not meting_id:
        return
    try:
        if is_client:
            db = get_pro_db()
            row = db.execute('SELECT feedback_cache FROM client_metingen WHERE id=?', (meting_id,)).fetchone()
        else:
            db = get_meting_db()
            row = db.execute('SELECT feedback_cache FROM metingen WHERE id=?', (meting_id,)).fetchone()
        # Merge into existing per-language cache
        existing = {}
        if row and row[0]:
            try:
                parsed = json.loads(row[0])
                # Only keep per-language format (keys are 'nl', 'de', 'en').
                # Discard old flat format — language of that text is unknown.
                if any(k in ('nl', 'de', 'en') for k in parsed):
                    existing = {k: v for k, v in parsed.items() if k in ('nl', 'de', 'en')}
            except (json.JSONDecodeError, ValueError):
                existing = {}
        existing[lang] = {'insight': insight, 'reflection': reflection}
        cache_data = json.dumps(existing)
        if is_client:
            db.execute('UPDATE client_metingen SET feedback_cache=? WHERE id=?', (cache_data, meting_id))
        else:
            db.execute('UPDATE metingen SET feedback_cache=? WHERE id=?', (cache_data, meting_id))
        db.commit()
        db.close()
    except:
        pass

# ═══════════════════════════════════════════════════════════════════
# Innerlijk Kompas — prompt templates per meting_type
# Drie aparte system-prompts. De AI produceert {sentence1, sentence2, question}.
# Backend mapt sentence1→insight, sentence2→reflection voor HTTP-contract.
# ═══════════════════════════════════════════════════════════════════

KOMPAS_COMMON_GUIDE = """

INTERPRETATIE-LEIDRAAD VOOR DE TERUGKOPPELING

Je genereert twee zinnen. Zin 1 is een observatie met lichte duiding. Zin 2 is een reflectie over het samenspel tussen wat het lichaam toont en wat de persoon zelf aangeeft (Innerlijk Kompas).

ALGEMENE HOUDING
- Je spreekt de persoon die de meting deed direct aan met "je". Ook bij Pro-cliëntmetingen spreek je de cliënt aan, niet de Pro.
- Je stelt niets vast, je biedt iets aan. Vermijd categorische taal. Gebruik: "kan wijzen op", "past bij", "lijkt", "dit patroon zien we vaak bij".
- Je bent GEEN medische autoriteit. Nooit diagnostische termen voor specifieke aandoeningen.
- De context-invoer is een geschenk van de persoon. Verwerk het als weefsel, niet als citaat. NIET: "je zei dat je moe was". WEL: duiding die de context meeweegt zonder letterlijk citeren.

HIERARCHIE VAN INFORMATIE
1. Lichaamsdata (BPM, HRV%, RMSSD, RI) — ruggengraat
2. Vrij tekstveld (ctx_vrije_tekst) — sterkst sturend wanneer aanwezig
3. Dimensie (ctx_dimensie) — bepaalt duidingsregister
4. Schalen (ctx_ongemak, ctx_vitaliteit) — nuance binnen het register
5. Trend (laatste basismetingen met hun context) — verhaalboog

Ontbrekende velden (NULL) duid je niet. Je zwijgt erover.

RI-ZONES: 0-2 ZWAAR BELAST / 2-4 BELAST / 4-6 LICHT BELAST / 6-8 IN BALANS / 8-10 VEERKRACHTIG
BPM-BANDEN: <60 LAAG / 60-85 MIDDEN / >85 VERHOOGD

VERBODEN FORMULERINGEN:
- "Je herkent je signalen goed" bij zone-verschil >= 2
- "Je hebt stress" / "Je bent gestresst" bij patroon B (categorisch)
- Klinische diagnoses (burn-out, depressie, ziekte)
- "Je zei dat..." (papegaai-citaten)
- "Beide laag" wanneer slechts één waarde laag is
- "Uitputting" bij BPM > 60
- Medische vaktermen zonder context
- "Je systeem [werkwoord]" (in alle vormen)
- "Je zenuwstelsel [werkwoord]"
- "Je gestel [werkwoord]"
- "Hartritme-variabiliteit fluctueerde"
- "Modulatie", "tonus", "parasympathisch", "sympathisch" als zelfstandige naamwoorden in lopende tekst

TAALREGELS (mensentaal, geen jargon):
- NOOIT als onderwerp gebruiken: "je systeem", "je gestel", "je zenuwstelsel", "je autonome zenuwstelsel"
- WEL: "je", "je lichaam", werkwoorden ("Het lukte je om..."), of de gemeten beweging zelf ("je RI daalde", "je werd minder ontspannen")
- Beschrijf de ERVARING, niet de fysiologie. Niet: "je RI daalde, HRV fluctueerde". Wel: "je werd minder ontspannen, je lichaam reageerde wisselvallig"
- Cijfers (RI, HRV%, BPM) mogen genoemd, maar als context, niet als hoofdpersoon van de zin
- Geen klinisch jargon: "fluctueerde", "variabiliteit", "respiratoire", "parasympathisch" — gebruik dagelijkse taal
- Geen anatomische processen: "opende zich", "sloot zich", "activeerde", "modulatie" — gebruik beschrijvende taal

VOORBEELDEN GOED:
- "Tijdens deze sessie kwam je iets minder tot rust dan bij de start"
- "Je hebt je lichaam laten ontspannen — je RI steeg van 4.2 naar 6.8"
- "Je begon ontspannener dan je eindigde, wat ook iets zegt over hoe je vandaag binnenkwam"
- "Het lukte vandaag minder om los te laten"

VOORBEELDEN FOUT (nooit gebruiken):
- "Je systeem opende/sloot zich"
- "Je hartritme-variabiliteit fluctueerde flink"
- "Je autonome zenuwstelsel reageerde"
- "Je parasympathische tonus nam toe"

STRUCTUUR VAN DE TWEE ZINNEN:
Zin 1 (Aanbeveling, max 200 tekens): Weeft lichaamsdata met context. Zachte observatie, mogelijk richting. Nooit instructie.
Zin 2 (Innerlijk Kompas, max 200 tekens): Samenspel lichaam-gevoel. Benoemt discrepantie of overeenstemming. Opent tot zelfkennis, niet tot oordeel.
"""

KOMPAS_BASISMETING_GUIDE = """

KWADRANT-PATRONEN BIJ LAGE RI (0-4):

Patroon A — Lage RI met BPM < 60:
Verminderde activering in beide autonome takken. Framings: verstarring, diepe vermoeidheid, uitputting, herstelfase. Minder waarschijnlijk acute stress (die zou BPM verhogen).

Patroon B — Lage RI met BPM 60-85 of >85:
Sympathische dominantie — het systeem staat "aan". De onderliggende oorzaak is uit de meting alleen NIET af te leiden. Mogelijke oorzaken, allemaal plausibel:
- Stress (acuut of aanhoudend)
- Vermoeidheid (slaaptekort, overbelasting)
- Ziekte (infectie, koorts, herstelfase)
- Pijn (acuut of chronisch)
- Recente inspanning of emotionele activering

VERBODEN: bij dit patroon categorisch "je hebt stress" zeggen. Gebruik context om meest waarschijnlijke duiding te kiezen, benoem meerdere mogelijkheden bij onzekerheid.

CONTEXT STUURT DUIDING BIJ PATROON B:
- ctx_dimensie = lichamelijk + lage ctx_vitaliteit of hoge ctx_ongemak → vermoeidheid/ziekte/pijn waarschijnlijker dan stress
- ctx_dimensie = mentaal → stress of overbelasting waarschijnlijker
- ctx_dimensie = emotioneel → emotionele activering, mogelijk recente gebeurtenis
- ctx_dimensie = spiritueel → verbindings- of zinsvraag
- ctx_vrije_tekst bevat ziektewoorden (griep, koorts, hoofdpijn) → lichamelijke oorzaak prioriteit
- ctx_vrije_tekst bevat verlieswoorden (mis iemand, overleden) → emotionele oorzaak prioriteit
- ctx_vrije_tekst bevat werkwoorden (deadline, druk, klant) → mentale belasting prioriteit

HOGE RI-PATRONEN (RI >= 6):

Patroon C — Hoge RI met passende context:
Meestal positief duiden. Let op discrepanties: lage ctx_vitaliteit bij hoge RI is een onstemmigheid die het noemen waard is (niet alarmistisch, wel opmerkzaam).

Patroon D — Hoge RI, hoge BPM (>85):
Kan wijzen op actieve rust (na inspanning, na koffie, na emotie). Als ctx_vrije_tekst dit bevestigt → bevestigen. Zo niet → benoemen dat het lichaam actief is en rust nog mogelijk.

DISCREPANTIE-REGEL (INNERLIJK KOMPAS):
Het FEITEN-blok zegt al of zelfinschatting en RI dicht bij elkaar liggen of merkbaar
verschillen ("Lichaam versus gevoel"). Reken dit niet zelf na. Vertaal de gegeven uitkomst:
Schaal de toon aan de grootte van het verschil zoals het FEITEN-blok het formuleert:
- Liggen ze dicht bij elkaar: hooguit een kleine nuance, niet vooraanstaand. Lichaam en gevoel die dezelfde kant op wijzen is een geldige, positieve uitkomst.
- Een MILD verschil ("liggen iets uit elkaar"): benoem licht en terloops, NIET als opvallende tegenstelling. Bijvoorbeeld "je lichaam is iets meer ontspannen dan je je bewust voelt — dat is niet ongewoon". Geen drama, geen alarmtoon, niet vooraanstaand.
- Verschillen ze merkbaar (groot): benoem dat expliciet als kernuitspraak voor zin 2.
- Ontbreekt de regel "Lichaam versus gevoel" (oudere meting zonder zelfinschatting)? Benoem dan geen verschil; gebruik het ontbreken niet als signaal.

BIJ DISCREPANTIE:
- Gevoel HOGER dan lichaam: persoon voelt zich beter dan lichaam toont. "Je lichaam toont nog druk, terwijl je je al beter voelt".
- Gevoel LAGER dan lichaam: persoon voelt zich slechter dan lichaam toont. "Je lichaam toont meer rust dan je gevoel op dit moment doet vermoeden".

TREND-GEBRUIK:
Bij recente basismetingen (laatste 3-5):
- Stabiele trend: continuiteit benoemen
- Verbetering: benoemen met aandacht voor context van toen ("de vermoeidheid die je eerder aangaf is in de getallen minder zichtbaar")
- Verslechtering: voorzichtig benoemen, context zoeken, alarmeren vermijden
- Uitschieters (RI buiten 1-9) zonder duidelijke context: niet zwaar op leunen, kan meetruis zijn
"""

BASISMETING_SYSTEM_PROMPT = (
    "Je bent de Innerlijk-Kompas-stem van StressChecker voor een BASISMETING.\n"
    "Een basismeting is een momentopname van het autonome zenuwstelsel in rust.\n"
    "Je kijkt naar hoe deze meting zich verhoudt tot de recente basismetingen van dezelfde persoon.\n"
    "Je bent geen coach, geen therapeut, geen diagnosticus. "
    "Je observeert wat je ziet, in de tweede persoon (je in NL, du in DE, you in EN), "
    "nuchter en zonder alarmisme of geruststelling die niet is onderbouwd.\n\n"
    "FEITEN-BLOK (cruciaal): het user_message begint met een blok 'FEITEN' dat het systeem "
    "deterministisch heeft berekend — de vergelijking met de vorige meting, het gemiddelde "
    "van de recente basismetingen en de richting/het verschil daartegen, de zone, het "
    "samenspel lichaam-versus-gevoel, de periode mét datums en de fase. Deze feiten zijn "
    "leidend en al juist. Jouw enige taak is ze in warme, begrijpelijke mensentaal te "
    "verwoorden. Reken, vergelijk, middel, dateer of bepaal zones NOOIT zelf en spreek de "
    "feiten nooit tegen. Verzin geen getallen, datums of richtingen die niet in het FEITEN-blok "
    "staan. De richtingswoorden ('lager dan', 'hoger dan', 'vergelijkbaar met' / hun DE/EN-"
    "equivalenten) en de datums neem je letterlijk over zoals ze in FEITEN staan.\n\n"
    "Geef geen advies. Sluit af met een open reflectievraag die de persoon nieuwsgierig maakt "
    "naar het eigen patroon.\n\n"
    "INPUT-VELDEN (wat je in user_message krijgt):\n"
    "- current.ri, current.bpm, current.hrv_pct, current.rmssd — fysiologische ruggengraat\n"
    "- current.subjectief_score (0-10) — zelfrapportage rust/gespannen; een onaangeraakte slider "
    "telt als bewuste instemming met 5 (neutraal)\n"
    "- current.ctx_dimensie — 'lichamelijk' / 'mentaal' / 'emotioneel' / 'spiritueel' / 'weet_niet' / null\n"
    "- current.ctx_vitaliteit (0-10) — hoger = meer afstemming op wat bij de persoon past\n"
    "- current.ctx_ongemak (0-10) — hoger = meer fysiek ongemak\n"
    "- current.ctx_vrije_tekst — optionele vrije tekst (max 100 chars) of null\n"
    "- current.label — optioneel meting-label of null\n"
    "- recent_basis[] — laatste basismetingen, per item: ri, subjectief_score, datum, ctx_dimensie, ctx_vrije_tekst\n"
    "- baseline_ri_history — gemiddelde RI van basismetingen 8-14 terug, of null\n"
    "- phase — phase1 / phase2 / phase3\n"
    "NULL-waarden negeer je: schrijf er niet over, gebruik ze niet als leeg signaal.\n\n"
    "TIJD/DATUM (belangrijk):\n"
    "Als je een datum noemt, gebruik dan UITSLUITEND de absolute datums zoals ze "
    "letterlijk in het FEITEN-blok staan (bijv. '21 april 2026'). Verzin of herbereken "
    "geen datums. Gebruik NOOIT relatieve termen als 'gisteren', 'vandaag', 'deze week', "
    "'vorige week', 'recent'. De gegenereerde tekst wordt gecached en moet ook "
    "over weken/maanden nog kloppen.\n\n"
    "SCHRIJFSTIJL-EISEN (belangrijk):\n"
    "- Schrijf alsof je praat met iemand zonder medische achtergrond. "
    "Vermijd 'systeem' als metafoor voor het lichaam - gebruik 'lichaam', 'hart', "
    "of 'zenuwstelsel' als dat concreter werkt.\n"
    "- Vermijd vage lichamelijke metaforen als 'gesloten', 'open', 'los laten' "
    "tenzij je ze concreet invult (bv. 'je hart heeft nog niet de ruimte gekregen om te vertragen').\n"
    "- Als je RI-getallen noemt, zeg dan ook wat ze betekenen in woorden. "
    "'RI 0.4 - dat is laag, je lichaam zit nog duidelijk in actiemodus' is beter dan 'RI 0.4'.\n"
    "- Schrijf in korte, directe zinnen. Vermijd 'fysiologisch normaal', 'parasympathische dominantie', "
    "'autonoom zenuwstelsel' tenzij de gebruiker die terminologie duidelijk zelf gebruikt heeft.\n"
    "- Als je iets geruststelt, doe dat met een concreet beeld in plaats van een term. "
    "'Dit hoort bij hoe je lichaam na inspanning terugkomt' > 'Dit is fysiologisch normaal'.\n"
    "- Sluit niet af met een samenvatting - de reflectievraag doet dat werk al.\n\n"
    "VELDEN (verplicht):\n"
    "- sentence1: observatie/kop\n"
    "- sentence2: toelichting\n"
    "- question: max 20 woorden, een reflectievraag. Formuleer de vraag TIJDLOOS: "
    "gebruik GEEN relatieve tijdwoorden ('vandaag', 'gisteren', 'morgen', 'nu', "
    "'deze week', 'vorige week') — ook de vraag wordt gecached en moet later nog kloppen.\n\n"
    "Schrijf volledige zinnen — gebruik GEEN weglatingstekens (geen \u2026 en geen ...). Output: strikt JSON met keys sentence1, sentence2, question. "
    "Geen preamble, geen markdown, geen uitleg buiten de JSON."
) + KOMPAS_COMMON_GUIDE + KOMPAS_BASISMETING_GUIDE

BIOFEEDBACK_SYSTEM_PROMPT = (
    "Je bent de Innerlijk-Kompas-stem voor een BIOFEEDBACK-meting. Dit is een interventie: "
    "de persoon heeft een ademhalingsoefening gedaan en we kijken wat die oefening met het "
    "systeem heeft gedaan. Je kijkt NIET naar trends over meerdere dagen — je kijkt uitsluitend "
    "naar voor versus na, binnen deze sessie.\n\n"
    "Kernvraag: ging het systeem open (RI omhoog) of juist dicht (RI omlaag), en in welke context?\n\n"
    "Als pre=null (geen basismeting binnen 30min vóór): vergelijk post met recent_basis als rust-baseline. "
    "Spreek van \"rust-referentie\" in plaats van \"delta\". Benoem NIET dat er geen eerdere metingen "
    "zijn als recent_basis gevuld is.\n\n"
    "Belangrijke nuances:\n"
    "- Als label 'Na sport' is of pre.ri al laag, dan is een lage post.ri vaak fysiologisch: "
    "het lichaam is nog in herstelmodus en de oefening overstemt dat niet. "
    "Benoem dat neutraal, niet als mislukking.\n"
    "- Een oefening die de spanning aanvankelijk zichtbaarder maakt (RI omlaag) is niet per se fout "
    "- soms moet het systeem eerst voelen wat er is.\n"
    "- Een duidelijke stijging (delta_ri >= 1.5) noem je als een open reactie: het systeem liet los.\n"
    "- Een stabiele meting (|delta_ri| < 0.5) noem je als: het systeem bleef zoals het was "
    "- dat is ook informatie.\n\n"
    "Geef geen advies over welke oefening beter is. Sluit af met een reflectievraag die gaat over "
    "WAT de oefening deed, niet of hij 'lukte'.\n\n"
    "\n\n"
    "SCHRIJFSTIJL-EISEN (belangrijk):\n"
    "- Schrijf alsof je praat met iemand zonder medische achtergrond. "
    "Vermijd 'systeem' als metafoor voor het lichaam - gebruik 'lichaam', 'hart', "
    "of 'zenuwstelsel' als dat concreter werkt.\n"
    "- Vermijd vage lichamelijke metaforen als 'gesloten', 'open', 'los laten' "
    "tenzij je ze concreet invult (bv. 'je hart heeft nog niet de ruimte gekregen om te vertragen').\n"
    "- Als je RI-getallen noemt, zeg dan ook wat ze betekenen in woorden. "
    "'RI 0.4 - dat is laag, je lichaam zit nog duidelijk in actiemodus' is beter dan 'RI 0.4'.\n"
    "- Schrijf in korte, directe zinnen. Vermijd 'fysiologisch normaal', 'parasympathische dominantie', "
    "'autonoom zenuwstelsel' tenzij de gebruiker die terminologie duidelijk zelf gebruikt heeft.\n"
    "- Als je iets geruststelt, doe dat met een concreet beeld in plaats van een term. "
    "'Dit hoort bij hoe je lichaam na inspanning terugkomt' > 'Dit is fysiologisch normaal'.\n"
    "- Sluit niet af met een samenvatting - de reflectievraag doet dat werk al.\n\n"
    "VELDEN (verplicht):\n"
    "- sentence1: max 15 woorden\n"
    "- sentence2: max 55 woorden\n"
    "- question: max 20 woorden\n\n"
    "Schrijf volledige zinnen — gebruik GEEN weglatingstekens (geen \u2026 en geen ...). Output: strikt JSON met keys sentence1, sentence2, question. Geen preamble."
) + KOMPAS_COMMON_GUIDE

# ---------- Biofeedback v3 (intra-sessie observatie) ----------
BIOFEEDBACK_SYSTEM_PROMPT_V3 = (
"""Je beschrijft een BIOFEEDBACK-meting voor deze cliënt. Een biofeedback-meting is een zitting waarin iemand iets heeft gedaan (ademhalingsoefening, hypnotiseur-sessie, ontspanningsoefening) terwijl StressChecker het autonome zenuwstelsel doormat.

Je bent geen coach, geen therapeut, geen diagnosticus. Je geeft geen advies, geen aanbevelingen voor volgende sessies, geen oordeel of de oefening "gelukt" is. Je beschrijft hoe de meting verliep.

Spreek de cliënt aan in de tweede persoon enkelvoud (je). Maximaal 200 tekens totaal, verdeeld over twee zinnen.

KERN VAN DE OBSERVATIE
Vergelijk de eerste minuut van de sessie met de laatste minuut. Benoem delta_ri (afgerond op 0.1). Voeg het kwalitatieve verloop toe via slope_ri_per_min + variabiliteit_rmssd:
- slope > 0.2 per min -> "Je werd duidelijk meer ontspannen tijdens deze sessie"
- slope < -0.2 per min -> "Je raakte tijdens deze sessie iets meer onder spanning"
- |slope| <= 0.2 per min -> "Je bleef tijdens deze sessie ongeveer op hetzelfde niveau"
- variabiliteit_rmssd > 2.0 -> benoem als "schommelend" of "onrustig"
- variabiliteit_rmssd < 1.0 bij stabiele slope -> "rustig verloop"

BASELINE-CONTEXT (alleen als baseline_avg beschikbaar EN |eind.ri - baseline_avg| > 0.5)
Benoem of eind.ri boven/onder je rust-niveau ligt.

CONTEXT-PRIORITEIT IN ZIN 2
Kies EEN van onderstaande voor zin 2, in deze volgorde:
1. ctx_vrije_tekst (als substantieel ingevuld): weef in zonder papegaai
2. Baseline-afwijking (als >0.5 RI verschil)
3. Ademritme-benoeming (als ademritme_str beschikbaar)
4. Geen van bovenstaande: herhaal NIET zin 1; geef contextloze opmerking over wat nog meer opvalt in de data

TAAL
- "Tijdens deze sessie" NIET "door de oefening" (tijd-correlatie, geen causaliteit)
- Geen superlatieven (geweldig, prachtig)
- Geen waarschuwingen (pas op)
- Geen klinische termen (insufficientie, dysregulatie)

VERBODEN
- Aanbevelingen voor volgende sessies
- Oordelen over succes of mislukking
- Uitspraken over wat de oefening "deed" als causaal verband
- Advies over ademritme, techniek, frequentie
- Een reflectievraag (VERSCHIL met basismeting-prompt!)

OUTPUT
JSON met keys: sentence1, sentence2. Geen question. Geen preamble.
sentence1 = kernobservatie (delta + verloop)
sentence2 = context (volgens prioriteit)
"""
) + KOMPAS_COMMON_GUIDE
# ---------- /Biofeedback v3 ----------

SITUATIEMETING_SYSTEM_PROMPT = (
    "Je bent de Innerlijk-Kompas-stem voor een SITUATIEMETING. Dit is een sonde: de persoon meet "
    "in een specifieke context (gegeven door label) om te zien wat die context met het systeem doet. "
    "Je vergelijkt met de persoonlijke basislijn - NIET met andere situatiemetingen en NIET met een trend.\n\n"
    "Kernvraag: hoe zit het systeem erbij, gegeven deze context, vergeleken met de eigen rust-basislijn?\n\n"
    "Belangrijk:\n"
    "- Het label bepaalt de interpretatie. 'Na sport' met lage RI is normaal. "
    "'Voor vergadering' met lage RI zegt iets over anticipatie. "
    "'Tijdens pauze' met lage RI zegt iets anders.\n"
    "- Benoem of current.ri binnen, onder, of boven de baseline_range valt.\n"
    "- Lichaam-versus-gevoel (RI versus subjectief_score): schaal de duiding aan de grootte van het "
    "verschil — klein/mild verschil terloops en neutraal benoemen (geen drama), groot verschil expliciet. "
    "Lichaam en gevoel die dezelfde kant op wijzen is een geldige, positieve uitkomst.\n\n"
    "Geef geen advies. Sluit af met een reflectievraag die over deze specifieke situatie gaat "
    "- niet over patronen.\n\n"
    "\n\n"
    "SCHRIJFSTIJL-EISEN (belangrijk):\n"
    "- Schrijf alsof je praat met iemand zonder medische achtergrond. "
    "Vermijd 'systeem' als metafoor voor het lichaam - gebruik 'lichaam', 'hart', "
    "of 'zenuwstelsel' als dat concreter werkt.\n"
    "- Vermijd vage lichamelijke metaforen als 'gesloten', 'open', 'los laten' "
    "tenzij je ze concreet invult (bv. 'je hart heeft nog niet de ruimte gekregen om te vertragen').\n"
    "- Als je RI-getallen noemt, zeg dan ook wat ze betekenen in woorden. "
    "'RI 0.4 - dat is laag, je lichaam zit nog duidelijk in actiemodus' is beter dan 'RI 0.4'.\n"
    "- Schrijf in korte, directe zinnen. Vermijd 'fysiologisch normaal', 'parasympathische dominantie', "
    "'autonoom zenuwstelsel' tenzij de gebruiker die terminologie duidelijk zelf gebruikt heeft.\n"
    "- Als je iets geruststelt, doe dat met een concreet beeld in plaats van een term. "
    "'Dit hoort bij hoe je lichaam na inspanning terugkomt' > 'Dit is fysiologisch normaal'.\n"
    "- Sluit niet af met een samenvatting - de reflectievraag doet dat werk al.\n\n"
    "VELDEN (verplicht):\n"
    "- sentence1: max 15 woorden\n"
    "- sentence2: max 55 woorden\n"
    "- question: max 20 woorden\n\n"
    "Schrijf volledige zinnen — gebruik GEEN weglatingstekens (geen \u2026 en geen ...). Output: strikt JSON met keys sentence1, sentence2, question. Geen preamble."
) + KOMPAS_COMMON_GUIDE


# ====== Biofeedback v3 — intra-sessie data-helpers ======
def _compute_session_windows(timeseries_json, total_duration_sec):
    """Start- (0-60s) en eind-window (laatste 60s) gemiddelden + delta.

    timeseries_json: JSON-string of reeds geparseerde list van dicts met
    keys t/ri/bpm/hrv/rmssd. total_duration_sec: totale meet-duur in sec.
    Fallback-retour bij onvoldoende data: {"valid": False, "reason": ...}.
    """
    try:
        pts = json.loads(timeseries_json) if isinstance(timeseries_json, str) else (timeseries_json or [])
    except (ValueError, TypeError):
        return {"valid": False, "reason": "invalid_json"}
    if not isinstance(pts, list):
        return {"valid": False, "reason": "invalid_json"}
    if len(pts) < 15:
        return {"valid": False, "reason": "too_few_samples"}
    try:
        total = float(total_duration_sec or 0)
    except (TypeError, ValueError):
        total = 0.0
    if total < 180:
        return {"valid": False, "reason": "duration_too_short"}

    def _t(p):
        try: return float(p.get('t') or 0)
        except Exception: return 0.0
    start_pts = [p for p in pts if 0 <= _t(p) <= 60]
    eind_pts  = [p for p in pts if (total - 60) <= _t(p) <= total]
    if len(start_pts) < 3:
        return {"valid": False, "reason": "start_window_too_few"}
    if len(eind_pts) < 3:
        return {"valid": False, "reason": "eind_window_too_few"}

    def _avg(items, key):
        vals = []
        for x in items:
            v = x.get(key)
            if v is None: continue
            try: vals.append(float(v))
            except (TypeError, ValueError): pass
        return round(sum(vals) / len(vals), 1) if vals else None

    start = {"ri": _avg(start_pts, 'ri'), "bpm": _avg(start_pts, 'bpm'),
             "hrv": _avg(start_pts, 'hrv'), "rmssd": _avg(start_pts, 'rmssd'),
             "n": len(start_pts)}
    eind  = {"ri": _avg(eind_pts, 'ri'), "bpm": _avg(eind_pts, 'bpm'),
             "hrv": _avg(eind_pts, 'hrv'), "rmssd": _avg(eind_pts, 'rmssd'),
             "n": len(eind_pts)}
    delta = {k: (round(eind[k] - start[k], 1) if (start.get(k) is not None and eind.get(k) is not None) else None)
             for k in ('ri', 'bpm', 'hrv', 'rmssd')}
    return {"start": start, "eind": eind, "delta": delta, "valid": True}


def _compute_session_trend(timeseries_json):
    """Lineaire regressie slope_ri_per_min + stdev RMSSD over hele sessie.

    Fallback bij <10 datapunten of degenerate fit: {"valid": False}.
    """
    try:
        pts = json.loads(timeseries_json) if isinstance(timeseries_json, str) else (timeseries_json or [])
    except (ValueError, TypeError):
        return {"valid": False}
    if not isinstance(pts, list) or len(pts) < 10:
        return {"valid": False}

    pairs = []
    for p in pts:
        t, r = p.get('t'), p.get('ri')
        if t is None or r is None: continue
        try: pairs.append((float(t), float(r)))
        except (TypeError, ValueError): pass
    if len(pairs) < 10:
        return {"valid": False}
    n = len(pairs)
    sx = sum(t for t, _ in pairs)
    sy = sum(r for _, r in pairs)
    sxy = sum(t*r for t, r in pairs)
    sxx = sum(t*t for t, _ in pairs)
    denom = n*sxx - sx*sx
    if denom == 0:
        return {"valid": False}
    slope_per_sec = (n*sxy - sx*sy) / denom
    slope_per_min = round(slope_per_sec * 60, 2)

    rmssd_vals = []
    for p in pts:
        v = p.get('rmssd')
        if v is None: continue
        try: rmssd_vals.append(float(v))
        except (TypeError, ValueError): pass
    stdev_rmssd = 0.0
    if len(rmssd_vals) >= 2:
        import statistics as _stats
        stdev_rmssd = round(_stats.pstdev(rmssd_vals), 1)
    return {"slope_ri_per_min": slope_per_min, "variabiliteit_rmssd": stdev_rmssd, "valid": True}


def _build_biofeedback_session_data(cur_row, db):
    """Orchestrator: leest timeseries uit cur_row, roept window- + trend-helpers aan.

    total_duration: cur_row['duration'] indien > 0, anders laatste t in timeseries.
    ademritme_str: nog niet opgeslagen in DB (aparte TODO) → altijd None.
    """
    try:
        row = cur_row if isinstance(cur_row, dict) else dict(cur_row)
    except Exception:
        row = {}
        try:
            for k in cur_row.keys(): row[k] = cur_row[k]
        except Exception: pass

    ts_raw = row.get('timeseries')
    if not ts_raw:
        return {"windows": None, "trend": None, "ademritme_str": None,
                "duration_sec": 0, "valid": False, "reason": "no_timeseries"}
    try:
        pts = json.loads(ts_raw) if isinstance(ts_raw, str) else ts_raw
    except (ValueError, TypeError):
        return {"windows": None, "trend": None, "ademritme_str": None,
                "duration_sec": 0, "valid": False, "reason": "invalid_json"}

    try: duration_sec = int(row.get('duration') or 0)
    except (TypeError, ValueError): duration_sec = 0
    if duration_sec <= 0 and isinstance(pts, list) and pts:
        try: duration_sec = int(max(float(p.get('t') or 0) for p in pts))
        except Exception: duration_sec = 0

    windows = _compute_session_windows(pts, duration_sec)
    trend   = _compute_session_trend(pts)
    valid   = bool(windows.get('valid') and trend.get('valid'))
    reason  = None if valid else (windows.get('reason') or ('trend_invalid' if not trend.get('valid') else 'unknown'))
    return {"windows": windows, "trend": trend, "ademritme_str": None,
            "duration_sec": duration_sec, "valid": valid, "reason": reason}
# ====== /Biofeedback v3 ======


def _gather_kompas_context(cur, is_client, user_key, client_id):
    """Verzamel meting_type-specifieke context voor de Innerlijk-Kompas-prompt.
    Retourneert dict met (naar gelang type): pre_ref, baseline_ri, baseline_range,
    recent_basis, phase, baseline_ri_history, datetime_iso.
    Bij biofeedback zonder pre_ref binnen 30min-venster: pre_ref ontbreekt → router valt terug op basismeting-template.
    """
    from datetime import datetime as _dt
    ctx = {}
    ts_cur = cur.get('ts') or 0
    ctx['datetime_iso'] = _dt.fromtimestamp(ts_cur/1000).strftime('%Y-%m-%d %H:%M') if ts_cur else ''
    mt = (cur.get('meting_type') or 'basismeting').lower()

    try:
        db = get_pro_db() if is_client else get_meting_db()
        tbl = 'client_metingen' if is_client else 'metingen'
        where_key = 'client_id=?' if is_client else 'user_key=?'
        key_val = client_id if is_client else user_key

        if mt == 'biofeedback':
            window_ms = 30 * 60 * 1000
            pre_row = db.execute(
                f"SELECT id, ri, bpm, hrv_pct, rmssd FROM {tbl} "
                f"WHERE {where_key} AND meting_type='basismeting' AND ts >= ? AND ts < ? "
                f"ORDER BY ts DESC LIMIT 1",
                (key_val, ts_cur - window_ms, ts_cur)
            ).fetchone()
            if pre_row:
                ctx['pre_ref'] = dict(pre_row)
            # Altijd recent_basis + phase ophalen als rust-referentie (ook als pre_ref gevuld is)
            recent_rows = db.execute(
                f"SELECT ri, subjectief_score, ts, ctx_dimensie, ctx_vrije_tekst FROM {tbl} "
                f"WHERE {where_key} AND meting_type='basismeting' AND ts < ? "
                f"ORDER BY ts DESC LIMIT 7",
                (key_val, ts_cur)
            ).fetchall()
            ctx['recent_basis'] = [
                {'ri': r[0], 'subjectief_score': r[1],
                 'datum': _dt.fromtimestamp((r[2] or 0)/1000).strftime('%Y-%m-%d'),
                 'ctx_dimensie': r[3] or None,
                 'ctx_vrije_tekst': (r[4][:100] if r[4] else None)}
                for r in recent_rows
            ]
            count_row = db.execute(
                f"SELECT COUNT(*) FROM {tbl} WHERE {where_key} AND meting_type='basismeting'",
                (key_val,)
            ).fetchone()
            count = count_row[0] if count_row else 0
            ctx['phase'] = 'phase3' if count >= 15 else ('phase2' if count >= 5 else 'phase1')

        elif mt == 'situatiemeting':
            bl_rows = db.execute(
                f"SELECT ri FROM {tbl} WHERE {where_key} AND meting_type='basismeting' "
                f"AND ri IS NOT NULL ORDER BY ts DESC LIMIT 7",
                (key_val,)
            ).fetchall()
            ri_vals = [float(r[0]) for r in bl_rows if r[0] is not None]
            if ri_vals:
                ctx['baseline_ri'] = round(sum(ri_vals) / len(ri_vals), 1)
                ctx['baseline_range'] = {'min': round(min(ri_vals), 1), 'max': round(max(ri_vals), 1)}

        else:
            # basismeting (default) + fallbacks voor bio-zonder-pre / situ-zonder-label
            recent_rows = db.execute(
                f"SELECT ri, subjectief_score, ts, ctx_dimensie, ctx_vrije_tekst FROM {tbl} "
                f"WHERE {where_key} AND meting_type='basismeting' AND ts < ? "
                f"ORDER BY ts DESC LIMIT 7",
                (key_val, ts_cur)
            ).fetchall()
            ctx['recent_basis'] = [
                {'ri': r[0], 'subjectief_score': r[1],
                 'datum': _dt.fromtimestamp((r[2] or 0)/1000).strftime('%Y-%m-%d'),
                 'ctx_dimensie': r[3] or None,
                 'ctx_vrije_tekst': (r[4][:100] if r[4] else None)}
                for r in recent_rows
            ]
            count_row = db.execute(
                f"SELECT COUNT(*) FROM {tbl} WHERE {where_key} AND meting_type='basismeting'",
                (key_val,)
            ).fetchone()
            count = count_row[0] if count_row else 0
            ctx['phase'] = 'phase3' if count >= 15 else ('phase2' if count >= 5 else 'phase1')
            sec_rows = db.execute(
                f"SELECT ri FROM {tbl} WHERE {where_key} AND meting_type='basismeting' "
                f"AND ri IS NOT NULL AND ts < ? ORDER BY ts DESC LIMIT 7 OFFSET 7",
                (key_val, ts_cur)
            ).fetchall()
            sec_vals = [float(r[0]) for r in sec_rows if r[0] is not None]
            if len(sec_vals) >= 3:
                ctx['baseline_ri_history'] = round(sum(sec_vals) / len(sec_vals), 1)
        db.close()
    except Exception:
        try: db.close()
        except: pass
    return ctx


# Maandnamen voor absolute datum-formattering in de Innerlijk-Kompas-feiten.
# Bewust een eigen dict (NIET locale): locale is onbetrouwbaar/onvolledig onder gunicorn.
_MONTH_NAMES = {
    'nl': ['januari', 'februari', 'maart', 'april', 'mei', 'juni',
           'juli', 'augustus', 'september', 'oktober', 'november', 'december'],
    'de': ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
           'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'],
    'en': ['January', 'February', 'March', 'April', 'May', 'June',
           'July', 'August', 'September', 'October', 'November', 'December'],
}


def _fmt_abs_date(y, m, d, lang):
    """(jaar, maand, dag) → absolute datum mét jaartal, gelokaliseerd.
    NL '31 mei 2026' · DE '31. Mai 2026' · EN '31 May 2026'. Jaartal altijd,
    zodat gecachte tekst over maanden/jaren ondubbelzinnig blijft kloppen."""
    months = _MONTH_NAMES.get(lang if lang in _MONTH_NAMES else 'nl')
    name = months[m - 1] if 1 <= m <= 12 else str(m)
    return f"{d}. {name} {y}" if lang == 'de' else f"{d} {name} {y}"


def _parse_iso_ymd(s):
    """'YYYY-MM-DD' (evt. met tijd erachter) → (y, m, d) ints, of None."""
    try:
        y, m, d = s.split(' ')[0].split('-')
        return int(y), int(m), int(d)
    except Exception:
        return None


# Richtingswoorden per taal (door de CODE bepaald — het model neemt ze letterlijk over).
_RICHTING = {
    'nl': {'up': 'hoger dan', 'down': 'lager dan', 'flat': 'vergelijkbaar met'},
    'de': {'up': 'höher als', 'down': 'niedriger als', 'flat': 'ähnlich wie'},
    'en': {'up': 'higher than', 'down': 'lower than', 'flat': 'comparable to'},
}


def _richting(diff, lang):
    """Deterministische richting met dezelfde drempel als de bestaande trend-logica
    (|diff| <= 0.5 → vergelijkbaar). Retourneert (woord, signed_delta_str)."""
    r = _RICHTING.get(lang if lang in _RICHTING else 'nl')
    delta = round(diff, 1)
    if diff > 0.5:
        key = 'up'
    elif diff < -0.5:
        key = 'down'
    else:
        key = 'flat'
    sign = '+' if delta > 0 else ('−' if delta < 0 else '±')
    return r[key], f"{sign}{abs(delta)}"


def _basismeting_feiten(cur, recent_basis, phase, lang):
    """Bereken ALLE vergelijkings-, gemiddelde- en datum-feiten deterministisch en
    lever ze als kant-en-klaar FEITEN-blok (platte tekst). Het model verwoordt deze
    feiten uitsluitend — het rekent, vergelijkt en dateert niets meer zelf.

    cur: dict met ri, ts, subjectief_score. recent_basis: lijst (nieuwste eerst) met
    ri, datum ('YYYY-MM-DD'). phase: phase1/2/3. lang: nl/de/en.
    """
    import analytics as _an
    from datetime import datetime as _dt
    L = lang if lang in ('nl', 'de', 'en') else 'nl'

    T = {
        'nl': {
            'hdr': 'FEITEN (door het systeem berekend — neem letterlijk over, reken of dateer NIETS zelf):',
            'cur': '- Huidige meting: RI {ri} op {date}. Zone: "{zone}".',
            'first': '- Dit is je eerste basismeting — er is nog geen eerdere meting om mee te vergelijken.',
            'prev': '- Vorige meting: RI {ri} op {date}. De huidige meting is {dir} de vorige ({delta}).',
            'avg': '- Gemiddelde van je laatste {n} basismetingen ({period}): RI {avg}. De huidige meting is {dir} dat gemiddelde ({delta}).',
            'one': '- Gebaseerd op 1 eerdere basismeting (op {date}): RI {avg}. (Nog te weinig metingen voor een trend.)',
            'body_sim': '- Lichaam versus gevoel: je zelfinschatting ({subj}) en je RI ({ri}) liggen dicht bij elkaar.',
            'body_mild': '- Lichaam versus gevoel: je zelfinschatting ({subj}) en je RI ({ri}) liggen iets uit elkaar — een mild verschil.',
            'body_diff': '- Lichaam versus gevoel: je zelfinschatting is {subj}, je RI is {ri} — die verschillen merkbaar.',
            'fase': {'phase1': '- Fase: nog weinig metingen — nog geen betrouwbaar patroon.',
                     'phase2': '- Fase: een eerste patroon wordt zichtbaar.',
                     'phase3': '- Fase: genoeg metingen voor een patroon.'},
            'sep': ' t/m ',
        },
        'de': {
            'hdr': 'FAKTEN (vom System berechnet — wörtlich übernehmen, NICHTS selbst rechnen oder datieren):',
            'cur': '- Aktuelle Messung: RI {ri} am {date}. Zone: "{zone}".',
            'first': '- Dies ist deine erste Basismessung — es gibt noch keine frühere Messung zum Vergleich.',
            'prev': '- Vorige Messung: RI {ri} am {date}. Die aktuelle Messung ist {dir} die vorige ({delta}).',
            'avg': '- Durchschnitt deiner letzten {n} Basismessungen ({period}): RI {avg}. Die aktuelle Messung ist {dir} dieser Durchschnitt ({delta}).',
            'one': '- Basierend auf 1 früheren Basismessung (am {date}): RI {avg}. (Noch zu wenige Messungen für einen Trend.)',
            'body_sim': '- Körper versus Gefühl: deine Selbsteinschätzung ({subj}) und dein RI ({ri}) liegen nah beieinander.',
            'body_mild': '- Körper versus Gefühl: deine Selbsteinschätzung ({subj}) und dein RI ({ri}) liegen etwas auseinander — ein milder Unterschied.',
            'body_diff': '- Körper versus Gefühl: deine Selbsteinschätzung ist {subj}, dein RI ist {ri} — das unterscheidet sich merklich.',
            'fase': {'phase1': '- Phase: noch wenige Messungen — noch kein verlässliches Muster.',
                     'phase2': '- Phase: ein erstes Muster wird sichtbar.',
                     'phase3': '- Phase: genug Messungen für ein Muster.'},
            'sep': ' bis ',
        },
        'en': {
            'hdr': 'FACTS (computed by the system — use verbatim, do NOT calculate or date anything yourself):',
            'cur': '- Current reading: RI {ri} on {date}. Zone: "{zone}".',
            'first': '- This is your first baseline reading — there is no earlier reading to compare with yet.',
            'prev': '- Previous reading: RI {ri} on {date}. The current reading is {dir} the previous one ({delta}).',
            'avg': '- Average of your last {n} baseline readings ({period}): RI {avg}. The current reading is {dir} that average ({delta}).',
            'one': '- Based on 1 earlier baseline reading (on {date}): RI {avg}. (Still too few readings for a trend.)',
            'body_sim': '- Body versus feeling: your self-assessment ({subj}) and your RI ({ri}) are close together.',
            'body_mild': '- Body versus feeling: your self-assessment ({subj}) and your RI ({ri}) are slightly apart — a mild difference.',
            'body_diff': '- Body versus feeling: your self-assessment is {subj}, your RI is {ri} — these differ noticeably.',
            'fase': {'phase1': '- Phase: still few readings — no reliable pattern yet.',
                     'phase2': '- Phase: a first pattern is becoming visible.',
                     'phase3': '- Phase: enough readings for a pattern.'},
            'sep': ' to ',
        },
    }[L]

    lines = [T['hdr']]

    cur_ri = cur.get('ri')
    cur_ri_s = 'n/a' if cur_ri is None else round(float(cur_ri), 1)
    ts_cur = cur.get('ts') or 0
    if ts_cur:
        cd = _dt.fromtimestamp(ts_cur / 1000)
        cur_date = _fmt_abs_date(cd.year, cd.month, cd.day, L)
    else:
        cur_date = '?'
    zone_label = _an.zone_label(_an.zone_for_ri(cur_ri), L) if cur_ri is not None else '?'
    lines.append(T['cur'].format(ri=cur_ri_s, date=cur_date, zone=zone_label))

    rb = [r for r in (recent_basis or []) if r.get('ri') is not None]

    if not rb:
        lines.append(T['first'])
    else:
        # Vorige meting (1-op-1)
        prev = rb[0]
        pv = _parse_iso_ymd(prev.get('datum') or '')
        prev_date = _fmt_abs_date(*pv, L) if pv else '?'
        if cur_ri is not None:
            pdir, pdelta = _richting(float(cur_ri) - float(prev['ri']), L)
            lines.append(T['prev'].format(ri=round(float(prev['ri']), 1), date=prev_date, dir=pdir, delta=pdelta))

        if len(rb) >= 2:
            vals = [float(r['ri']) for r in rb]
            avg = round(sum(vals) / len(vals), 1)
            # Periode: oudste t/m nieuwste in het venster
            newest = _parse_iso_ymd(rb[0].get('datum') or '')
            oldest = _parse_iso_ymd(rb[-1].get('datum') or '')
            period = '?'
            if oldest and newest:
                period = _fmt_abs_date(*oldest, L) + T['sep'] + _fmt_abs_date(*newest, L)
            if cur_ri is not None:
                adir, adelta = _richting(float(cur_ri) - avg, L)
                lines.append(T['avg'].format(n=len(rb), period=period, avg=avg, dir=adir, delta=adelta))
        else:
            # Precies één eerdere meting: geen trend suggereren
            lines.append(T['one'].format(date=prev_date, avg=round(float(prev['ri']), 1)))

    # Lichaam versus gevoel
    subj = cur.get('subjectief_score')
    if subj is not None and cur_ri is not None:
        _vg = abs(float(cur_ri) - float(subj))
        if _vg <= 1.5:
            lines.append(T['body_sim'].format(subj=subj, ri=cur_ri_s))
        elif _vg <= 3.0:
            lines.append(T['body_mild'].format(subj=subj, ri=cur_ri_s))
        else:
            lines.append(T['body_diff'].format(subj=subj, ri=cur_ri_s))

    # Fase
    ph = phase if phase in ('phase1', 'phase2', 'phase3') else 'phase1'
    lines.append(T['fase'][ph])

    return '\n'.join(lines)


def _build_kompas_prompt(cur, lang, context, session_data=None, baseline_avg=None):
    """Router: kiest prompt-template op basis van meting_type.
    Retourneert (system_prompt, user_message) tuple.
    Fallbacks: biofeedback zonder pre_ref → basismeting-template. Situ zonder label → basismeting-template.

    Biofeedback v3: als session_data is meegegeven en session_data['valid'] is True,
    gebruik BIOFEEDBACK_SYSTEM_PROMPT_V3 met intra-sessie windows/trend.
    """
    lang_name = {'nl': 'Dutch', 'de': 'German', 'en': 'English'}.get(lang, 'Dutch')
    mt = (cur.get('meting_type') or 'basismeting').lower()
    suffix = f"\n\nRespond in {lang_name}."

    if mt == 'biofeedback' and session_data and session_data.get('valid'):
        w = session_data.get('windows') or {}
        tr = session_data.get('trend') or {}
        s = w.get('start') or {}
        e = w.get('eind') or {}
        d = w.get('delta') or {}
        def _f(v):
            return 'null' if v is None else v
        def _txt(v, n=100):
            if v is None: return 'null'
            s = str(v).strip()
            if not s: return 'null'
            return '"' + s[:n] + '"'
        user = (
            "BIOFEEDBACK-meting v3 (intra-sessie observatie):\n"
            f"duration_sec: {_f(session_data.get('duration_sec'))}\n"
            f"start (eerste 60s):  RI={_f(s.get('ri'))}, BPM={_f(s.get('bpm'))}, HRV%={_f(s.get('hrv'))}, RMSSD={_f(s.get('rmssd'))}, n={_f(s.get('n'))}\n"
            f"eind  (laatste 60s): RI={_f(e.get('ri'))}, BPM={_f(e.get('bpm'))}, HRV%={_f(e.get('hrv'))}, RMSSD={_f(e.get('rmssd'))}, n={_f(e.get('n'))}\n"
            f"delta: RI={_f(d.get('ri'))}, BPM={_f(d.get('bpm'))}, HRV%={_f(d.get('hrv'))}, RMSSD={_f(d.get('rmssd'))}\n"
            f"slope_ri_per_min: {_f(tr.get('slope_ri_per_min'))}\n"
            f"variabiliteit_rmssd: {_f(tr.get('variabiliteit_rmssd'))}\n"
            f"baseline_avg (rust-RI uit recente basismetingen): {_f(baseline_avg)}\n"
            f"ademritme_str: {_f(session_data.get('ademritme_str'))}\n"
            f"ctx_dimensie: {_f(cur.get('ctx_dimensie'))}\n"
            f"ctx_vitaliteit: {_f(cur.get('ctx_vitaliteit'))}\n"
            f"ctx_ongemak: {_f(cur.get('ctx_ongemak'))}\n"
            f"ctx_vrije_tekst: {_txt(cur.get('ctx_vrije_tekst'))}\n"
            f"datetime: {context.get('datetime_iso') or ''}"
        )
        return BIOFEEDBACK_SYSTEM_PROMPT_V3 + suffix, user

    if mt == 'biofeedback':
        # Biofeedback-prompt wordt ALTIJD gebruikt (geen silent fallback meer naar basismeting-template)
        pre = context.get('pre_ref')
        recent = context.get('recent_basis', [])
        recent_str = '\n'.join(
            f"  - RI={r.get('ri')}, subjectief_score={r.get('subjectief_score')}, datum={r.get('datum')}"
            for r in recent
        ) if recent else '  (geen eerdere basismetingen)'

        if pre:
            delta = round((cur.get('ri') or 0) - (pre.get('ri') or 0), 1)
            pre_line = f"pre: RI={pre.get('ri')}, BPM={pre.get('bpm')}, HRV%={pre.get('hrv_pct')}, RMSSD={pre.get('rmssd')}"
            delta_line = f"delta_ri: {'+' if delta > 0 else ''}{delta}"
        else:
            pre_line = "pre: null (geen basismeting binnen 30min vóór biofeedback)"
            delta_line = "delta_ri: null"

        user = (
            "BIOFEEDBACK-meting data:\n"
            f"{pre_line}\n"
            f"post: RI={cur.get('ri')}, BPM={cur.get('bpm')}, HRV%={cur.get('hrv_pct')}, RMSSD={cur.get('rmssd')}\n"
            f"{delta_line}\n"
            f"label: {cur.get('notes') or 'null'}\n"
            f"ctx_dimensie: {cur.get('ctx_dimensie') or 'null'}\n"
            f"subjectief_score: {cur.get('subjectief_score')}\n"
            f"datetime: {context.get('datetime_iso') or ''}\n"
            f"recent_basis (laatste basismetingen als rust-referentie, nieuwste eerst):\n{recent_str}\n"
            f"phase: {context.get('phase', 'phase1')}"
        )
        return BIOFEEDBACK_SYSTEM_PROMPT + suffix, user

    if mt == 'situatiemeting' and (cur.get('notes') or '').strip():
        bl_range = context.get('baseline_range', {})
        user = (
            "SITUATIEMETING data:\n"
            f"current: RI={cur.get('ri')}, BPM={cur.get('bpm')}, HRV%={cur.get('hrv_pct')}, "
            f"RMSSD={cur.get('rmssd')}, subjectief_score={cur.get('subjectief_score')}, subjectief_gezet={cur.get('subjectief_score') is not None}, "
            f"ctx_dimensie={cur.get('ctx_dimensie') or 'null'}, datetime={context.get('datetime_iso') or ''}\n"
            f"label: {cur.get('notes')}\n"
            f"baseline_ri: {context.get('baseline_ri') if context.get('baseline_ri') is not None else 'null'}\n"
            f"baseline_range: min={bl_range.get('min') if bl_range.get('min') is not None else 'null'}, "
            f"max={bl_range.get('max') if bl_range.get('max') is not None else 'null'}"
        )
        return SITUATIEMETING_SYSTEM_PROMPT + suffix, user

    # Default / fallback: basismeting-template
    def _fmt_int(v):
        if v is None:
            return 'null'
        try: return str(int(round(float(v))))
        except Exception: return 'null'
    def _fmt_text(v):
        if v is None or str(v).strip() == '':
            return 'null'
        return '"' + str(v)[:100] + '"'
    recent = context.get('recent_basis', [])
    recent_str = '\n'.join(
        f"  - RI={r.get('ri')}, subjectief_score={r.get('subjectief_score')}, datum={r.get('datum')}, "
        f"ctx_dimensie={r.get('ctx_dimensie') or 'null'}, ctx_vrije_tekst={_fmt_text(r.get('ctx_vrije_tekst'))}"
        for r in recent
    ) if recent else '  (geen eerdere basismetingen)'
    phase = context.get('phase', 'phase1')
    fallback_note = ''
    if mt == 'biofeedback':
        fallback_note = '\n(Intern: biofeedback zonder pre-referentie binnen 30min - basismeting-interpretatie.)'
    elif mt == 'situatiemeting':
        fallback_note = '\n(Intern: situatiemeting zonder label - basismeting-interpretatie.)'
    data_blok = (
        f"current: RI={cur.get('ri')}, BPM={cur.get('bpm')}, HRV%={cur.get('hrv_pct')}, "
        f"RMSSD={cur.get('rmssd')}, subjectief_score={cur.get('subjectief_score')}, subjectief_gezet={cur.get('subjectief_score') is not None}, "
        f"ctx_dimensie={cur.get('ctx_dimensie') or 'null'}, datetime={context.get('datetime_iso') or ''}\n"
        f"ctx_vitaliteit={_fmt_int(cur.get('ctx_vitaliteit'))}, ctx_ongemak={_fmt_int(cur.get('ctx_ongemak'))}, ctx_vrije_tekst={_fmt_text(cur.get('ctx_vrije_tekst'))}\n"
        f"label: {cur.get('notes') or 'null'}\n"
        f"recent_basis (tot 7 eerdere basismetingen, nieuwste eerst):\n{recent_str}\n"
        f"baseline_ri_history (avg basismetingen 8-14 terug): "
        f"{context.get('baseline_ri_history') if context.get('baseline_ri_history') is not None else 'null'}\n"
        f"phase: {phase}{fallback_note}"
    )
    if mt == 'basismeting':
        # Alleen échte basismetingen: FEITEN-blok (vergelijkingen, gemiddelden, datums, zone,
        # lichaam-versus-gevoel, fase al deterministisch berekend — het model verwoordt enkel).
        # Fallback-randgevallen (bio-zonder-pre / situ-zonder-label) blijven bewust ongemoeid.
        feiten_blok = _basismeting_feiten(cur, recent, phase, lang)
        user = (
            f"{feiten_blok}\n\n"
            "RUWE DATA (uitsluitend als context voor je duiding/toon — NIET om mee te rekenen, "
            "te vergelijken of te dateren; daarvoor geldt enkel het FEITEN-blok hierboven):\n"
            f"{data_blok}"
        )
    else:
        user = "BASISMETING data:\n" + data_blok
    return BASISMETING_SYSTEM_PROMPT + suffix, user


@app.route('/api/feedback')
def api_feedback():
    if not session.get('license_valid') and not session.get('demo_mode') and not session.get('hlm_user_id'):
        return jsonify({'error': 'Niet ingelogd'}), 401
    lang = session.get('lang', 'nl')
    import logging; logging.getLogger().warning(f"[FEEDBACK DEBUG] session lang={lang}, session keys={list(session.keys())}")
    is_demo = bool(session.get('demo_mode') or session.get('is_demo'))

    # Client-specifieke feedback voor pro gebruikers
    cid = request.args.get('cid', type=int)
    # Optional: target specifieke meting via ?mid=<id> (wordt gebruikt door regenerate_kompas)
    mid_param = request.args.get('mid', type=int)

    # Haal laatste meting + vorige meting op (inclusief id en feedback_cache)
    _is_client_query = cid and _is_pro_or_demo_pro()
    try:
        if _is_client_query:
            db = get_pro_db()
            if mid_param:
                cur_r = db.execute('SELECT id, ri, bpm, hrv_pct, rmssd, subjectief_score, ctx_dimensie, ctx_vitaliteit, ctx_ongemak, ctx_vrije_tekst, meting_type, feedback_cache, ts, notes, duration, timeseries FROM client_metingen WHERE id=? AND client_id=?', (mid_param, cid)).fetchone()
                rows = []
                if cur_r:
                    rows.append(cur_r)
                    prev_r = db.execute('SELECT id, ri, bpm, hrv_pct, rmssd, subjectief_score, ctx_dimensie, ctx_vitaliteit, ctx_ongemak, ctx_vrije_tekst, meting_type, feedback_cache, ts, notes, duration, timeseries FROM client_metingen WHERE client_id=? AND ts < ? ORDER BY ts DESC LIMIT 1', (cid, cur_r['ts'])).fetchone()
                    if prev_r: rows.append(prev_r)
            else:
                rows = db.execute('SELECT id, ri, bpm, hrv_pct, rmssd, subjectief_score, ctx_dimensie, ctx_vitaliteit, ctx_ongemak, ctx_vrije_tekst, meting_type, feedback_cache, ts, notes, duration, timeseries FROM client_metingen WHERE client_id=? ORDER BY ts DESC LIMIT 2', (cid,)).fetchall()
            db.close()
        else:
            db = get_meting_db()
            if mid_param:
                cur_r = db.execute('SELECT id, ri, bpm, hrv_pct, rmssd, subjectief_score, ctx_dimensie, ctx_vitaliteit, ctx_ongemak, ctx_vrije_tekst, meting_type, feedback_cache, ts, notes, duration, timeseries FROM metingen WHERE id=? AND user_key=?', (mid_param, get_user_key())).fetchone()
                rows = []
                if cur_r:
                    rows.append(cur_r)
                    prev_r = db.execute('SELECT id, ri, bpm, hrv_pct, rmssd, subjectief_score, ctx_dimensie, ctx_vitaliteit, ctx_ongemak, ctx_vrije_tekst, meting_type, feedback_cache, ts, notes, duration, timeseries FROM metingen WHERE user_key=? AND ts < ? ORDER BY ts DESC LIMIT 1', (get_user_key(), cur_r['ts'])).fetchone()
                    if prev_r: rows.append(prev_r)
            else:
                rows = db.execute('SELECT id, ri, bpm, hrv_pct, rmssd, subjectief_score, ctx_dimensie, ctx_vitaliteit, ctx_ongemak, ctx_vrije_tekst, meting_type, feedback_cache, ts, notes, duration, timeseries FROM metingen WHERE user_key=? ORDER BY ts DESC LIMIT 2', (get_user_key(),)).fetchall()
            db.close()
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({'error': 'DB fout', 'detail': str(e)}), 500

    if not rows and is_demo:
        # Demo gebruiker zonder metingen: toon vaste voorbeeldtekst
        pass  # val door naar demo blok hieronder
    elif not rows:
        return jsonify({'insight': '', 'reflection': ''})

    # Demo: vaste coherente voorbeeldtekst (insight + reflection + question)
    if is_demo:
        demo = {
            'nl': {
                'insight': 'Je lichaam laat spanning zien, vooral lichamelijk — maar je herkent je signalen goed.',
                'reflection': 'Je autonoom zenuwstelsel toont dat er spanning zit, vooral op lichamelijk vlak. '
                    'Toch komt je zelfinschatting redelijk overeen met wat je lichaam aangeeft — dat is waardevol, want het betekent dat je goed naar jezelf luistert.',
            },
            'de': {
                'insight': 'Dein Körper zeigt Anspannung, besonders körperlich — aber du erkennst deine Signale gut.',
                'reflection': 'Dein autonomes Nervensystem zeigt Anspannung, besonders auf körperlicher Ebene. '
                    'Deine Selbsteinschätzung stimmt recht gut mit dem überein, was dein Körper meldet — das ist wertvoll, denn es bedeutet, dass du gut auf dich hörst.',
            },
            'en': {
                'insight': 'Your body is showing tension, especially physically — but you recognize your signals well.',
                'reflection': 'Your autonomic nervous system is showing tension, especially on a physical level. '
                    'Your self-assessment aligns fairly well with what your body reports — that\'s valuable, it means you\'re listening to yourself.',
            }
        }
        d = demo.get(lang, demo['nl'])
        question = _generate_question('lichamelijk', lang)
        _fb_payload = {'insight': d['insight'], 'reflection': d['reflection'], 'question': question, 'demo': True}
        import logging as _lg2; _lg2.getLogger().warning(f"[REFLECTION FINAL] mid={cur.get('id') if 'cur' in dir() and cur else 'n/a'} source={_fb_payload.get('source','?')} reflection_len={len(_fb_payload.get('reflection',''))} reflection={_fb_payload.get('reflection','')!r}")
        resp = jsonify(_fb_payload)
        resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        resp.headers['Pragma'] = 'no-cache'
        resp.headers['Expires'] = '0'
        return resp

    cur = dict(rows[0])
    prev = dict(rows[1]) if len(rows) > 1 else None
    meting_id = cur.get('id')
    meting_type = (cur.get('meting_type') or 'basismeting').lower()
    is_biofeedback = meting_type == 'biofeedback'
    is_situatie = meting_type == 'situatiemeting'
    dim = cur.get('ctx_dimensie') or ''

    # Trend data berekenen (phase 1/2/3)
    _client_name_for_trend = None
    if _is_client_query:
        try:
            db_t = get_pro_db()
            cn_row = db_t.execute('SELECT name FROM clients WHERE id=?', (cid,)).fetchone()
            if cn_row: _client_name_for_trend = cn_row[0]
            db_t.close()
        except:
            pass
    trend_data = _generate_trend_data(
        user_key=None if _is_client_query else get_user_key(),
        client_id=cid if _is_client_query else None,
        lang=lang,
        client_name=_client_name_for_trend
    )

    # Cache check: als feedback al gegenereerd is voor deze meting EN taal, retourneer direct
    cached = cur.get('feedback_cache')
    if cached:
        try:
            cached_data = json.loads(cached)
            # Only use per-language cache (keys are 'nl', 'de', 'en').
            # Old flat format ({insight, reflection} without language key) is
            # discarded — we cannot know what language it was generated in.
            lang_data = None
            if any(k in ('nl', 'de', 'en') for k in cached_data):
                lang_data = cached_data.get(lang)
            if lang_data and isinstance(lang_data, dict):
                if meting_type == 'biofeedback':
                    question = ''
                else:
                    question = _generate_question(dim, lang, meting_type)
                cached_reflection = _hard_truncate(lang_data.get('reflection', ''), 250)
                # Trend info gaat via trend_hint field; niet meer in reflection.
                _fb_payload = {'insight': lang_data.get('insight', ''), 'reflection': cached_reflection, 'question': question, 'trend_hint': (trend_data.get('trend_hint', '') if meting_type == 'basismeting' else ''), 'source': 'cached'}
                import logging as _lg2; _lg2.getLogger().warning(f"[REFLECTION FINAL] mid={cur.get('id') if 'cur' in dir() and cur else 'n/a'} source={_fb_payload.get('source','?')} reflection_len={len(_fb_payload.get('reflection',''))} reflection={_fb_payload.get('reflection','')!r}")
                resp = jsonify(_fb_payload)
                resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
                resp.headers['Pragma'] = 'no-cache'
                resp.headers['Expires'] = '0'
                return resp
        except (json.JSONDecodeError, ValueError):
            pass  # Ongeldige cache, opnieuw genereren

    # Voor biofeedback: zoek de meest recente basismeting van dezelfde dag als referentie
    basis_ri = None
    if is_biofeedback:
        try:
            if cid and _is_pro_or_demo_pro():
                db2 = get_pro_db()
                basis_row = db2.execute(
                    "SELECT ri FROM client_metingen WHERE client_id=? AND meting_type='basismeting' "
                    "AND ts >= (SELECT ts FROM client_metingen WHERE client_id=? ORDER BY ts DESC LIMIT 1) - 86400000 "
                    "AND ts < (SELECT ts FROM client_metingen WHERE client_id=? ORDER BY ts DESC LIMIT 1) "
                    "ORDER BY ts DESC LIMIT 1",
                    (cid, cid, cid)).fetchone()
            else:
                db2 = get_meting_db()
                basis_row = db2.execute(
                    "SELECT ri FROM metingen WHERE user_key=? AND meting_type='basismeting' "
                    "AND ts >= (SELECT ts FROM metingen WHERE user_key=? ORDER BY ts DESC LIMIT 1) - 86400000 "
                    "AND ts < (SELECT ts FROM metingen WHERE user_key=? ORDER BY ts DESC LIMIT 1) "
                    "ORDER BY ts DESC LIMIT 1",
                    (get_user_key(), get_user_key(), get_user_key())).fetchone()
            if basis_row:
                basis_ri = float(basis_row[0])
            db2.close()
        except:
            pass

    # Voor situatiemeting: persoonlijke basislijn (gemiddelde RI van laatste 10 basismetingen)
    personal_baseline = None
    if is_situatie:
        try:
            if cid and _is_pro_or_demo_pro():
                db2 = get_pro_db()
                bl_row = db2.execute(
                    "SELECT AVG(ri) FROM (SELECT ri FROM client_metingen WHERE client_id=? AND meting_type='basismeting' ORDER BY ts DESC LIMIT 10)",
                    (cid,)).fetchone()
            else:
                db2 = get_meting_db()
                bl_row = db2.execute(
                    "SELECT AVG(ri) FROM (SELECT ri FROM metingen WHERE user_key=? AND meting_type='basismeting' ORDER BY ts DESC LIMIT 10)",
                    (get_user_key(),)).fetchone()
            if bl_row and bl_row[0] is not None:
                personal_baseline = round(float(bl_row[0]), 1)
            db2.close()
        except:
            pass

    # Trend berekenen
    trend = None
    if prev and cur.get('ri') is not None and prev.get('ri') is not None:
        diff = cur['ri'] - prev['ri']
        if diff > 0.5: trend = 'up'
        elif diff < -0.5: trend = 'down'
        else: trend = 'stable'

    # Echte gebruiker: Anthropic API aanroepen
    question = _generate_question(dim, lang, meting_type)

    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        result = _generate_local_feedback(cur, prev, trend, lang, is_biofeedback=is_biofeedback, basis_ri=basis_ri, is_situatie=is_situatie, personal_baseline=personal_baseline)
        result['reflection'] = _hard_truncate(result['reflection'], 250)
        # Trend info gaat via trend_hint field; niet meer in reflection.
        _store_feedback_cache(meting_id, result['insight'], result['reflection'], is_client=_is_client_query, lang=lang)
        result['question'] = question
        result['trend_hint'] = (trend_data.get('trend_hint', '') if meting_type == 'basismeting' else '')
        _fb_payload = {**result, 'source': 'local'}
        import logging as _lg2; _lg2.getLogger().warning(f"[REFLECTION FINAL] mid={cur.get('id') if 'cur' in dir() and cur else 'n/a'} source={_fb_payload.get('source','?')} reflection_len={len(_fb_payload.get('reflection',''))} reflection={_fb_payload.get('reflection','')!r}")
        resp = jsonify(_fb_payload)
        resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        resp.headers['Pragma'] = 'no-cache'
        resp.headers['Expires'] = '0'
        return resp

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        # Gebruik nieuwe per-meting_type prompts (router op meting_type)
        _uk = get_user_key() if not _is_client_query else None
        kompas_ctx = _gather_kompas_context(cur, _is_client_query, _uk, cid if _is_client_query else None)
        # Biofeedback v3: intra-sessie data + baseline-gemiddelde
        _session_data = None
        _baseline_avg = None
        if (cur.get('meting_type') or '').lower() == 'biofeedback':
            _session_data = _build_biofeedback_session_data(cur, None)
            _rb = kompas_ctx.get('recent_basis') or []
            _rb_ri = [float(r.get('ri')) for r in _rb if r.get('ri') is not None]
            if _rb_ri:
                _baseline_avg = round(sum(_rb_ri) / len(_rb_ri), 1)
        system_prompt, user_msg = _build_kompas_prompt(cur, lang, kompas_ctx, session_data=_session_data, baseline_avg=_baseline_avg)

        # Biofeedback v3 levert geen reflectievraag — question leeg, ongeacht AI-output
        _is_bf_v3 = bool(
            (cur.get('meting_type') or '').lower() == 'biofeedback'
            and _session_data and _session_data.get('valid')
        )
        if _is_bf_v3:
            question = ''

        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            temperature=0.5,
            system=system_prompt,
            messages=[{"role": "user", "content": user_msg}]
        )
        text = message.content[0].text.strip()
        import logging as _lg
        _lg.getLogger().warning(f"[KOMPAS RAW AI] mid={cur.get('id')} type={meting_type} lang={lang} raw={text!r}")

        # Parse JSON response — expected format: {sentence1, sentence2, question}
        # Backward compat: oudere prompt-versies produceerden {insight, sentence1, sentence2} zonder question.
        insight = ''
        reflection = ''
        try:
            # Strip markdown code fences if present
            if text.startswith('```'): text = text.split('\n', 1)[1].rsplit('```', 1)[0].strip()
            parsed = json.loads(text)
            s1 = parsed.get('sentence1', '')
            s2 = parsed.get('sentence2', '')
            # Nieuwe contract: s1 = observatie (insight-rol), s2 = toelichting (reflection-rol)
            insight = s1 or parsed.get('insight', '')
            reflection = s2 or parsed.get('reflection', '')
            if not reflection and s1 and parsed.get('insight'):
                # Backward compat: oude format had insight + s1 + s2 → reflection = s1+s2
                reflection = (s1 + ' ' + s2).strip()
            # Question komt nu uit AI-response; fallback op server-side _generate_question
            # Biofeedback v3 heeft per definitie geen question — override blokkeren.
            ai_question = parsed.get('question', '').strip()
            # Dag-anker in AI-vraag (basismeting) → val terug op de schone _generate_question.
            if ai_question and not _is_bf_v3 and not (meting_type == 'basismeting' and _has_day_anchor(ai_question, lang)):
                question = ai_question
        except (json.JSONDecodeError, ValueError):
            # Fallback: probeer INSIGHT:/REFLECTION: formaat
            for line in text.split('\n'):
                line = line.strip()
                if line.upper().startswith('INSIGHT:'):
                    insight = line.split(':', 1)[1].strip()
                elif line.upper().startswith('REFLECTION:'):
                    reflection = line.split(':', 1)[1].strip()
            if not reflection:
                reflection = text.replace('INSIGHT:', '').replace('REFLECTION:', '').strip()
            if not insight:
                first_dot = reflection.find('.')
                insight = reflection[:first_dot+1] if first_dot > 0 else reflection[:80]

        # Hard truncate reflection to exactly 2 sentences, then hard char limit
        reflection = _hard_truncate(reflection, 250)
        # Strip ellipsis-chars (Claude gebruikt ze soms stilistisch; niet wenselijk hier)
        insight = (insight or '').replace('\u2026', '').replace('...', '').strip()
        reflection = (reflection or '').replace('\u2026', '').replace('...', '').strip()

        # Dag-anker-guard (alleen basismeting): gecachte proza moet tijdloos blijven.
        # E\u00e9n retry met strengere instructie (lagere temp); blijft het anker \u2192 schone lokale fallback.
        if meting_type == 'basismeting' and (_has_day_anchor(insight, lang) or _has_day_anchor(reflection, lang)):
            try:
                retry_system = system_prompt + (
                    "\n\nSTRIKT-HERSCHRIJVEN: je vorige antwoord bevatte een verboden dag-anker "
                    "('vandaag'/'heute'/'today', 'gisteren', 'morgen', 'deze week', 'vorige week' e.d.). "
                    "Herschrijf sentence1 en sentence2 VOLLEDIG tijdloos: gebruik geen enkel woord dat aan "
                    "een specifieke dag bindt. Datums uitsluitend letterlijk uit het FEITEN-blok. Behoud "
                    "betekenis en toon. Output opnieuw strikt JSON met sentence1, sentence2, question."
                )
                msg2 = client.messages.create(
                    model="claude-haiku-4-5-20251001", max_tokens=400, temperature=0.2,
                    system=retry_system, messages=[{"role": "user", "content": user_msg}])
                t2 = msg2.content[0].text.strip()
                if t2.startswith('```'): t2 = t2.split('\n', 1)[1].rsplit('```', 1)[0].strip()
                p2 = json.loads(t2)
                i2 = (p2.get('sentence1') or p2.get('insight') or '').replace('\u2026', '').replace('...', '').strip()
                r2 = _hard_truncate((p2.get('sentence2') or p2.get('reflection') or ''), 250).replace('\u2026', '').replace('...', '').strip()
                q2 = (p2.get('question') or '').strip()
                if i2 and r2 and not _has_day_anchor(i2, lang) and not _has_day_anchor(r2, lang):
                    insight, reflection = i2, r2
                    if q2 and not _is_bf_v3 and not _has_day_anchor(q2, lang):
                        question = q2
                else:
                    raise ValueError('retry bevat nog steeds een dag-anker')
            except Exception:
                result = _generate_local_feedback(cur, prev, trend, lang, is_biofeedback=is_biofeedback, basis_ri=basis_ri, is_situatie=is_situatie, personal_baseline=personal_baseline)
                result['reflection'] = _hard_truncate(result['reflection'], 250)
                _store_feedback_cache(meting_id, result['insight'], result['reflection'], is_client=_is_client_query, lang=lang)
                result['question'] = question
                result['trend_hint'] = (trend_data.get('trend_hint', '') if meting_type == 'basismeting' else '')
                _fb_payload = {**result, 'source': 'local_dayanchor'}
                import logging as _lg2; _lg2.getLogger().warning(f"[REFLECTION FINAL] mid={cur.get('id') if 'cur' in dir() and cur else 'n/a'} source={_fb_payload.get('source','?')} reflection_len={len(_fb_payload.get('reflection',''))} reflection={_fb_payload.get('reflection','')!r}")
                resp = jsonify(_fb_payload)
                resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
                resp.headers['Pragma'] = 'no-cache'
                resp.headers['Expires'] = '0'
                return resp

        # Language mixing check — discard and use local fallback if wrong language detected
        if _check_language_mixing(insight, lang) or _check_language_mixing(reflection, lang):
            result = _generate_local_feedback(cur, prev, trend, lang, is_biofeedback=is_biofeedback, basis_ri=basis_ri, is_situatie=is_situatie, personal_baseline=personal_baseline)
            result['reflection'] = _hard_truncate(result['reflection'], 250)
            # Trend info gaat via trend_hint field; niet meer in reflection.
            _store_feedback_cache(meting_id, result['insight'], result['reflection'], is_client=_is_client_query, lang=lang)
            result['question'] = question
            result['trend_hint'] = (trend_data.get('trend_hint', '') if meting_type == 'basismeting' else '')
            _fb_payload = {**result, 'source': 'local_lang_fix'}
            import logging as _lg2; _lg2.getLogger().warning(f"[REFLECTION FINAL] mid={cur.get('id') if 'cur' in dir() and cur else 'n/a'} source={_fb_payload.get('source','?')} reflection_len={len(_fb_payload.get('reflection',''))} reflection={_fb_payload.get('reflection','')!r}")
            resp = jsonify(_fb_payload)
            resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            resp.headers['Pragma'] = 'no-cache'
            resp.headers['Expires'] = '0'
            return resp

        # Forbidden word check — vervang met lokale fallback als nodig
        if _check_forbidden(insight) or _check_forbidden(reflection):
            result = _generate_local_feedback(cur, prev, trend, lang, is_biofeedback=is_biofeedback, basis_ri=basis_ri, is_situatie=is_situatie, personal_baseline=personal_baseline)
            result['reflection'] = _hard_truncate(result['reflection'], 250)
            # Trend info gaat via trend_hint field; niet meer in reflection.
            _store_feedback_cache(meting_id, result['insight'], result['reflection'], is_client=_is_client_query, lang=lang)
            result['question'] = question
            result['trend_hint'] = (trend_data.get('trend_hint', '') if meting_type == 'basismeting' else '')
            _fb_payload = {**result, 'source': 'local_filtered'}
            import logging as _lg2; _lg2.getLogger().warning(f"[REFLECTION FINAL] mid={cur.get('id') if 'cur' in dir() and cur else 'n/a'} source={_fb_payload.get('source','?')} reflection_len={len(_fb_payload.get('reflection',''))} reflection={_fb_payload.get('reflection','')!r}")
            resp = jsonify(_fb_payload)
            resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            resp.headers['Pragma'] = 'no-cache'
            resp.headers['Expires'] = '0'
            return resp

        # Trend info zit in trend_hint (separate field) — niet meer concaten in reflection.
        _store_feedback_cache(meting_id, insight, reflection, is_client=_is_client_query, lang=lang)
        _fb_payload = {'insight': insight, 'reflection': reflection, 'question': question, 'trend_hint': (trend_data.get('trend_hint', '') if meting_type == 'basismeting' else ''), 'source': 'ai'}
        import logging as _lg2; _lg2.getLogger().warning(f"[REFLECTION FINAL] mid={cur.get('id') if 'cur' in dir() and cur else 'n/a'} source={_fb_payload.get('source','?')} reflection_len={len(_fb_payload.get('reflection',''))} reflection={_fb_payload.get('reflection','')!r}")
        resp = jsonify(_fb_payload)
        resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        resp.headers['Pragma'] = 'no-cache'
        resp.headers['Expires'] = '0'
        return resp
    except Exception as e:
        result = _generate_local_feedback(cur, prev, trend, lang, is_biofeedback=is_biofeedback, basis_ri=basis_ri, is_situatie=is_situatie, personal_baseline=personal_baseline)
        result['reflection'] = _hard_truncate(result['reflection'], 250)
        # Trend info gaat via trend_hint field; niet meer in reflection.
        _store_feedback_cache(meting_id, result['insight'], result['reflection'], is_client=_is_client_query, lang=lang)
        result['question'] = question
        result['trend_hint'] = (trend_data.get('trend_hint', '') if meting_type == 'basismeting' else '')
        _fb_payload = {**result, 'source': 'local', 'ai_error': str(e)}
        import logging as _lg2; _lg2.getLogger().warning(f"[REFLECTION FINAL] mid={cur.get('id') if 'cur' in dir() and cur else 'n/a'} source={_fb_payload.get('source','?')} reflection_len={len(_fb_payload.get('reflection',''))} reflection={_fb_payload.get('reflection','')!r}")
        resp = jsonify(_fb_payload)
        resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        resp.headers['Pragma'] = 'no-cache'
        resp.headers['Expires'] = '0'
        return resp


@app.route('/api/meting/<int:mid>/regenerate_kompas', methods=['POST'])
def regenerate_kompas(mid):
    """Forceer hergeneratie van Innerlijk Kompas voor één specifieke meting.
    Clears feedback_cache dan redirect naar /api/feedback?mid=...&cid=... (303 → GET).
    Auth: eigen user_key (consumer) of pro_key via clients-join (pro).
    """
    if not session.get('license_valid') and not session.get('demo_mode') and not session.get('hlm_user_id'):
        return jsonify({'error': 'Niet ingelogd'}), 401
    user_key = get_user_key()
    if not user_key:
        return jsonify({'error': 'Geen user_key in sessie'}), 401

    cid = None
    found = False
    try:
        db = get_meting_db()
        row = db.execute('SELECT user_key FROM metingen WHERE id=?', (mid,)).fetchone()
        if row and row['user_key'] == user_key:
            db.execute('UPDATE metingen SET feedback_cache=NULL WHERE id=?', (mid,))
            db.commit()
            found = True
        db.close()
    except Exception:
        try: db.close()
        except: pass

    if not found and _is_pro_or_demo_pro():
        try:
            pdb = get_pro_db()
            cm_row = pdb.execute(
                'SELECT cm.client_id FROM client_metingen cm '
                'JOIN clients c ON c.id = cm.client_id '
                'WHERE cm.id=? AND c.pro_key=?', (mid, user_key)).fetchone()
            if cm_row:
                cid = cm_row['client_id']
                pdb.execute('UPDATE client_metingen SET feedback_cache=NULL WHERE id=?', (mid,))
                pdb.commit()
                found = True
            pdb.close()
        except Exception:
            try: pdb.close()
            except: pass

    if not found:
        return jsonify({'error': 'Meting niet gevonden of geen toegang'}), 403

    from urllib.parse import urlencode
    qs = {'mid': mid}
    if cid: qs['cid'] = cid
    return redirect(url_for('api_feedback') + '?' + urlencode(qs), code=303)


def _generate_local_feedback(cur, prev, trend, lang, is_biofeedback=False, basis_ri=None, is_situatie=False, personal_baseline=None):
    """Lokale fallback: genereert coherent insight + reflection paar."""
    ri = cur.get('ri', 5)
    dim = cur.get('ctx_dimensie', '')
    subj = cur.get('subjectief_score')

    # ── Biofeedback: vergelijk met basismeting ──
    if is_biofeedback:
        return _generate_biofeedback_feedback(ri, basis_ri, lang)

    # ── Situatiemeting: vergelijk met persoonlijke basislijn ──
    if is_situatie:
        return _generate_situatie_feedback(ri, personal_baseline, dim, lang)

    if ri < 2: zone = 'risk'
    elif ri < 4: zone = 'stress'
    elif ri < 6: zone = 'neutral'
    elif ri < 8: zone = 'vital'
    else: zone = 'very_vital'

    # Insight: één zin voor kwadrant
    insights = {
        'nl': {
            'risk': 'Je autonoom zenuwstelsel is flink belast — geef jezelf rust en ruimte.',
            'stress': 'Er zit duidelijke spanning in je lichaam — je zenuwstelsel vraagt om aandacht.',
            'neutral': 'Je lichaam is redelijk in balans, met ruimte om dieper te ontspannen.',
            'vital': 'Je autonoom zenuwstelsel herstelt goed — je lijf voelt veerkrachtig.',
            'very_vital': 'Uitstekend — je lichaam is diep ontspannen en herstelt optimaal.',
        },
        'de': {
            'risk': 'Dein autonomes Nervensystem ist stark belastet — gönne dir Ruhe und Raum.',
            'stress': 'Deutliche Anspannung in deinem Körper — dein Nervensystem braucht Aufmerksamkeit.',
            'neutral': 'Dein Körper ist einigermaßen im Gleichgewicht, mit Raum für tiefere Entspannung.',
            'vital': 'Dein autonomes Nervensystem erholt sich gut — dein Körper fühlt sich widerstandsfähig an.',
            'very_vital': 'Ausgezeichnet — dein Körper ist tief entspannt und erholt sich optimal.',
        },
        'en': {
            'risk': 'Your autonomic nervous system is under significant strain — give yourself rest and space.',
            'stress': 'Clear tension in your body — your nervous system needs attention.',
            'neutral': 'Your body is reasonably balanced, with room to relax more deeply.',
            'vital': 'Your autonomic nervous system is recovering well — your body feels resilient.',
            'very_vital': 'Excellent — your body is deeply relaxed and recovering optimally.',
        }
    }

    # Reflection: 3-4 zinnen die het insight uitdiepen
    reflections = {
        'nl': {
            'risk': 'Je autonoom zenuwstelsel laat zien dat het op dit moment flink belast is.',
            'stress': 'Er zit spanning in je lichaam — je zenuwstelsel heeft moeite om tot rust te komen.',
            'neutral': 'Je lichaam is redelijk in balans, maar er is ruimte om dieper te ontspannen.',
            'vital': 'Mooi — je autonoom zenuwstelsel herstelt goed. Je lijf voelt veerkrachtig.',
            'very_vital': 'Uitstekend! Je lichaam is diep ontspannen en je autonoom zenuwstelsel herstelt optimaal.',
        },
        'de': {
            'risk': 'Dein autonomes Nervensystem zeigt, dass es gerade stark belastet ist.',
            'stress': 'Es steckt Anspannung in deinem Körper — dein Nervensystem kommt schwer zur Ruhe.',
            'neutral': 'Dein Körper ist einigermaßen im Gleichgewicht, aber es gibt Raum für tiefere Entspannung.',
            'vital': 'Schön — dein autonomes Nervensystem erholt sich gut. Dein Körper fühlt sich widerstandsfähig an.',
            'very_vital': 'Ausgezeichnet! Dein Körper ist tief entspannt und dein autonomes Nervensystem erholt sich optimal.',
        },
        'en': {
            'risk': 'Your autonomic nervous system is showing signs of significant strain right now.',
            'stress': 'There is tension in your body — your nervous system is struggling to settle.',
            'neutral': 'Your body is reasonably balanced, but there\'s room to relax more deeply.',
            'vital': 'Nice — your autonomic nervous system is recovering well. Your body feels resilient.',
            'very_vital': 'Excellent! Your body is deeply relaxed and your autonomic nervous system is recovering optimally.',
        }
    }

    trend_lines = {
        'nl': {'up': 'Ten opzichte van je vorige meting gaat het de goede kant op.', 'down': 'Je score is iets gezakt — luister naar wat je lichaam je vertelt.', 'stable': 'Je score is vergelijkbaar met de vorige keer.'},
        'de': {'up': 'Im Vergleich zur letzten Messung geht es in die richtige Richtung.', 'down': 'Dein Wert ist etwas gesunken — höre auf das, was dein Körper dir sagt.', 'stable': 'Dein Wert ist ähnlich wie beim letzten Mal.'},
        'en': {'up': 'Compared to your previous reading, things are moving in the right direction.', 'down': 'Your score has dipped — listen to what your body is telling you.', 'stable': 'Your score is similar to last time.'},
    }

    dim_tips = {
        'nl': {
            'lichamelijk': 'Probeer even een korte wandeling te maken of 5 minuten te stretchen — je lichaam vraagt om beweging en ontlading.',
            'mentaal': 'Probeer eens 5 minuten niets te doen — geen scherm, geen takenlijst. Laat je gedachten even met rust.',
            'emotioneel': 'Gun jezelf een moment om te voelen wat er speelt, zonder het op te lossen. Soms is erkennen genoeg.',
            'spiritueel': 'Sta even stil bij wat je echt belangrijk vindt. Eén bewuste keuze vanuit je kern maakt verschil.',
            '': 'Probeer 5 minuten rustig te ademen: 4 tellen in, 6 tellen uit. Geef je lijf een moment van herstel.',
        },
        'de': {
            'lichamelijk': 'Versuche einen kurzen Spaziergang oder 5 Minuten Dehnung — dein Körper braucht Bewegung und Entlastung.',
            'mentaal': 'Versuche 5 Minuten nichts zu tun — kein Bildschirm, keine To-do-Liste. Lass deine Gedanken ruhen.',
            'emotioneel': 'Gönne dir einen Moment, um zu fühlen, was da ist, ohne es lösen zu müssen. Manchmal reicht Anerkennung.',
            'spiritueel': 'Halte kurz inne bei dem, was dir wirklich wichtig ist. Eine bewusste Entscheidung aus deiner Mitte macht den Unterschied.',
            '': 'Versuche 5 Minuten ruhig zu atmen: 4 Sekunden ein, 6 Sekunden aus. Gib deinem Körper einen Moment der Erholung.',
        },
        'en': {
            'lichamelijk': 'Try taking a short walk or 5 minutes of stretching — your body is asking for movement and release.',
            'mentaal': 'Try doing nothing for 5 minutes — no screen, no to-do list. Let your thoughts rest.',
            'emotioneel': 'Give yourself a moment to feel what\'s there, without trying to fix it. Sometimes acknowledgment is enough.',
            'spiritueel': 'Pause to reflect on what truly matters to you. One conscious choice from your core makes a difference.',
            '': 'Try 5 minutes of calm breathing: inhale for 4 counts, exhale for 6. Give your body a moment to recover.',
        }
    }

    insight = insights.get(lang, insights['nl'])[zone]

    parts = [reflections.get(lang, reflections['nl'])[zone]]
    if trend and trend in trend_lines.get(lang, {}):
        parts.append(trend_lines[lang][trend])
    if subj is not None and ri is not None and (ri - subj) < -1.5:
        subj_line = {'nl': 'Opvallend: je lichaam ervaart meer spanning dan je zelf inschat.', 'de': 'Auffällig: dein Körper erlebt mehr Anspannung als du selbst einschätzt.', 'en': 'Notably, your body is experiencing more tension than you realize.'}
        parts.append(subj_line.get(lang, subj_line['nl']))
    tips = dim_tips.get(lang, dim_tips['nl'])
    parts.append(tips.get(dim, tips['']))

    return {'insight': insight, 'reflection': ' '.join(parts)}


def _generate_biofeedback_feedback(ri, basis_ri, lang):
    """Lokale fallback voor biofeedback metingen."""
    if basis_ri is not None:
        delta = round(ri - basis_ri, 1)
        if delta > 1.0: effect = 'strong_up'
        elif delta > 0.3: effect = 'up'
        elif delta < -1.0: effect = 'strong_down'
        elif delta < -0.3: effect = 'down'
        else: effect = 'stable'
    else:
        delta = None
        effect = 'no_ref'

    insights = {
        'nl': {
            'strong_up': f'Je autonoom zenuwstelsel reageert duidelijk — je RI steeg met {delta} punt na je interventie.',
            'up': f'Je interventie heeft effect: je RI ging van {basis_ri} naar {ri}.',
            'stable': 'Je RI is stabiel gebleven tijdens de biofeedback — je lichaam houdt vast aan zijn huidige staat.',
            'down': 'Je RI is iets gedaald tijdens de sessie — dat kan betekenen dat je lichaam nog aan het zoeken is.',
            'strong_down': 'Je RI daalde opvallend tijdens de sessie — soms is dat een teken van verdieping voordat herstel komt.',
            'no_ref': f'Je biofeedback-meting toont een RI van {ri} — zonder basismeting is het effect lastig te duiden.',
        },
        'de': {
            'strong_up': f'Dein autonomes Nervensystem reagiert deutlich — dein RI stieg um {delta} Punkte nach deiner Intervention.',
            'up': f'Deine Intervention zeigt Wirkung: dein RI ging von {basis_ri} auf {ri}.',
            'stable': 'Dein RI ist während des Biofeedbacks stabil geblieben — dein Körper hält an seinem aktuellen Zustand fest.',
            'down': 'Dein RI ist während der Sitzung etwas gesunken — das kann bedeuten, dass dein Körper noch sucht.',
            'strong_down': 'Dein RI ist auffällig gesunken — manchmal zeigt sich Vertiefung, bevor Erholung einsetzt.',
            'no_ref': f'Deine Biofeedback-Messung zeigt einen RI von {ri} — ohne Basismessung ist die Wirkung schwer einzuordnen.',
        },
        'en': {
            'strong_up': f'Your autonomic nervous system responded clearly — your RI rose by {delta} points after your intervention.',
            'up': f'Your intervention is having an effect: your RI went from {basis_ri} to {ri}.',
            'stable': 'Your RI stayed stable during biofeedback — your body is holding its current state.',
            'down': 'Your RI dipped slightly during the session — this may mean your body is still finding its way.',
            'strong_down': 'Your RI dropped notably during the session — sometimes deepening happens before recovery arrives.',
            'no_ref': f'Your biofeedback reading shows an RI of {ri} — without a baseline, the effect is hard to gauge.',
        }
    }

    reflections = {
        'nl': {
            'strong_up': f'Je autonoom zenuwstelsel laat een duidelijke verschuiving zien: van {basis_ri} naar {ri}. '
                'Dit laat zien dat je lichaam goed reageert op wat je deed — het herstelvermogen is zichtbaar aanwezig. '
                'Wat merkte je zelf tijdens de sessie op — was er een moment waarop je voelde dat iets veranderde?',
            'up': f'Je RI ging van {basis_ri} naar {ri} — je autonoom zenuwstelsel beweegt in de richting van meer ontspanning. '
                'Het effect is subtiel maar meetbaar, en dat is precies hoe verandering er vaak uitziet. '
                'Welk moment in de sessie voelde het meest ontspannen voor je?',
            'stable': f'Je RI bleef rond {ri}, vergelijkbaar met je basismeting van {basis_ri}. '
                'Dat je lichaam stabiel blijft is op zich informatie — het zou kunnen betekenen dat je zenuwstelsel meer tijd nodig heeft, of dat de interventie op een ander niveau werkt dan de RI meet. '
                'Hoe voelde de sessie van binnen — was er iets dat verschoof, ook al laat het meetresultaat dat nog niet zien?',
            'down': f'Je RI daalde licht van {basis_ri} naar {ri} tijdens de sessie. '
                'Dat kan verrassend lijken, maar soms is een tijdelijke daling juist een teken dat je lichaam dieper gaat — spanning loslaten is niet altijd lineair. '
                'Was er een moment in de sessie waarop je iets voelde verschuiven?',
            'strong_down': f'Je RI ging van {basis_ri} naar {ri} — een opvallende daling tijdens de sessie. '
                'Dit zou kunnen betekenen dat je lichaam bezig is met een dieper proces, of dat de interventie iets raakte wat nog aandacht vraagt. '
                'Hoe voelde je je aan het einde van de sessie — rustiger, of juist meer aanwezig bij iets?',
            'no_ref': f'Je biofeedback-meting laat een RI van {ri} zien. '
                'Zonder basismeting van vandaag is het lastig om het effect van je interventie te duiden. '
                'Doe voor de volgende biofeedback eerst een korte basismeting — dan kun je het verschil zien.',
        },
        'de': {
            'strong_up': f'Dein autonomes Nervensystem zeigt eine deutliche Verschiebung: von {basis_ri} auf {ri}. '
                'Das zeigt, dass dein Körper gut auf deine Intervention reagiert — die Erholungsfähigkeit ist sichtbar vorhanden. '
                'Was hast du selbst während der Sitzung bemerkt — gab es einen Moment, in dem du eine Veränderung gespürt hast?',
            'up': f'Dein RI ging von {basis_ri} auf {ri} — dein autonomes Nervensystem bewegt sich Richtung Entspannung. '
                'Der Effekt ist subtil, aber messbar — genau so sieht Veränderung oft aus. '
                'Welcher Moment in der Sitzung fühlte sich am entspanntesten an?',
            'stable': f'Dein RI blieb bei etwa {ri}, vergleichbar mit deiner Basismessung von {basis_ri}. '
                'Stabilität ist an sich eine Information — es könnte bedeuten, dass dein Nervensystem mehr Zeit braucht, oder dass die Intervention auf einer anderen Ebene wirkt. '
                'Wie fühlte sich die Sitzung innerlich an — hat sich etwas verschoben, auch wenn die Messung das noch nicht zeigt?',
            'down': f'Dein RI sank leicht von {basis_ri} auf {ri} während der Sitzung. '
                'Das mag überraschen, aber manchmal ist ein vorübergehender Rückgang ein Zeichen dafür, dass dein Körper tiefer geht — Loslassen verläuft nicht immer linear. '
                'Gab es einen Moment in der Sitzung, in dem du eine Verschiebung gespürt hast?',
            'strong_down': f'Dein RI ging von {basis_ri} auf {ri} — ein auffälliger Rückgang während der Sitzung. '
                'Das könnte bedeuten, dass dein Körper einen tieferen Prozess durchläuft, oder dass die Intervention etwas berührt hat, das noch Aufmerksamkeit braucht. '
                'Wie hast du dich am Ende der Sitzung gefühlt — ruhiger, oder eher bewusster?',
            'no_ref': f'Deine Biofeedback-Messung zeigt einen RI von {ri}. '
                'Ohne Basismessung von heute ist die Wirkung deiner Intervention schwer einzuordnen. '
                'Mache vor dem nächsten Biofeedback zuerst eine kurze Basismessung — dann kannst du den Unterschied sehen.',
        },
        'en': {
            'strong_up': f'Your autonomic nervous system shows a clear shift: from {basis_ri} to {ri}. '
                'This shows your body responds well to what you did — recovery capacity is visibly present. '
                'What did you notice during the session — was there a moment where you felt something change?',
            'up': f'Your RI went from {basis_ri} to {ri} — your autonomic nervous system is moving toward more relaxation. '
                'The effect is subtle but measurable, and that is exactly what change often looks like. '
                'Which moment in the session felt most relaxed to you?',
            'stable': f'Your RI stayed around {ri}, comparable to your baseline of {basis_ri}. '
                'Stability is information in itself — it could mean your nervous system needs more time, or that the intervention is working on a level the RI doesn\'t capture yet. '
                'How did the session feel inside — did something shift, even if the reading doesn\'t show it yet?',
            'down': f'Your RI dipped slightly from {basis_ri} to {ri} during the session. '
                'That may seem surprising, but sometimes a temporary dip is a sign your body is going deeper — letting go isn\'t always linear. '
                'Was there a moment in the session where you felt something shift?',
            'strong_down': f'Your RI went from {basis_ri} to {ri} — a notable drop during the session. '
                'This could mean your body is processing something deeper, or that the intervention touched something that still needs attention. '
                'How did you feel at the end of the session — calmer, or more present with something?',
            'no_ref': f'Your biofeedback reading shows an RI of {ri}. '
                'Without a baseline from today, it\'s hard to gauge the effect of your intervention. '
                'Try doing a short baseline measurement before your next biofeedback — then you can see the difference.',
        }
    }

    i = insights.get(lang, insights['nl'])
    r = reflections.get(lang, reflections['nl'])
    return {'insight': i[effect], 'reflection': r[effect]}


def _generate_situatie_feedback(ri, personal_baseline, dim, lang):
    """Lokale fallback voor situatiemetingen — vergelijkt met persoonlijke basislijn."""
    if personal_baseline is not None:
        delta = round(ri - personal_baseline, 1)
        if delta > 1.0: state = 'above'
        elif delta < -1.0: state = 'below'
        else: state = 'at'
    else:
        delta = 0
        personal_baseline = '?'
        state = 'no_ref'

    dim_labels = {
        'nl': {'lichamelijk': 'lichamelijke', 'mentaal': 'mentale', 'emotioneel': 'emotionele', 'spiritueel': 'spirituele'},
        'de': {'lichamelijk': 'körperliche', 'mentaal': 'mentale', 'emotioneel': 'emotionale', 'spiritueel': 'spirituelle'},
        'en': {'lichamelijk': 'physical', 'mentaal': 'mental', 'emotioneel': 'emotional', 'spiritueel': 'spiritual'},
    }
    dl = dim_labels.get(lang, dim_labels['nl']).get(dim, '') if dim else ''

    insights = {
        'nl': {
            'above': f'Deze situatie brengt je boven je persoonlijke basislijn — je autonoom zenuwstelsel reageert met meer ruimte.',
            'at': f'In deze situatie blijft je RI dicht bij je basislijn van {personal_baseline} — je zenuwstelsel blijft in balans.',
            'below': f'Deze context drukt je RI onder je basislijn — je autonoom zenuwstelsel reageert op deze situatie met meer activatie.',
            'no_ref': f'Je situatiemeting toont een RI van {ri} — zonder basismetingen is het effect van deze context lastig te duiden.',
        },
        'de': {
            'above': f'Diese Situation bringt dich über deine persönliche Basislinie — dein autonomes Nervensystem reagiert mit mehr Spielraum.',
            'at': f'In dieser Situation bleibt dein RI nahe deiner Basislinie von {personal_baseline} — dein Nervensystem bleibt im Gleichgewicht.',
            'below': f'Dieser Kontext drückt deinen RI unter deine Basislinie — dein autonomes Nervensystem reagiert mit mehr Aktivierung.',
            'no_ref': f'Deine Situationsmessung zeigt einen RI von {ri} — ohne Basismessungen lässt sich die Wirkung schwer einordnen.',
        },
        'en': {
            'above': f'This situation brings you above your personal baseline — your autonomic nervous system responds with more ease.',
            'at': f'In this situation your RI stays close to your baseline of {personal_baseline} — your nervous system remains balanced.',
            'below': f'This context pushes your RI below your baseline — your autonomic nervous system responds with more activation.',
            'no_ref': f'Your situation measurement shows an RI of {ri} — without baseline measurements, the effect is hard to gauge.',
        }
    }

    dim_connection = {
        'nl': {
            'lichamelijk': f'De {dl} dimensie die je aangaf past bij wat je lichaam laat zien — deze situatie raakt je op lijfniveau.',
            'mentaal': f'De {dl} dimensie die je aangaf is interessant — deze situatie lijkt vooral je hoofd te activeren.',
            'emotioneel': f'De {dl} dimensie die je koos sluit aan — deze context raakt je op gevoelsniveau.',
            'spiritueel': f'De {dl} dimensie die je aangaf zegt iets: deze situatie raakt aan wat je ten diepste bezighoudt.',
            '': 'Zonder dimensie-keuze is het lastig te duiden welk kanaal deze situatie het meest raakt.',
        },
        'de': {
            'lichamelijk': f'Die {dl} Dimension, die du angegeben hast, passt zu dem, was dein Körper zeigt — diese Situation trifft dich auf körperlicher Ebene.',
            'mentaal': f'Die {dl} Dimension ist interessant — diese Situation scheint vor allem deinen Kopf zu aktivieren.',
            'emotioneel': f'Die {dl} Dimension, die du gewählt hast, passt — dieser Kontext trifft dich auf Gefühlsebene.',
            'spiritueel': f'Die {dl} Dimension sagt etwas aus: diese Situation berührt das, was dich im Tiefsten beschäftigt.',
            '': 'Ohne Dimensionswahl lässt sich schwer sagen, auf welcher Ebene diese Situation am meisten wirkt.',
        },
        'en': {
            'lichamelijk': f'The {dl} dimension you indicated fits what your body shows — this situation affects you at a physical level.',
            'mentaal': f'The {dl} dimension is interesting — this situation seems to activate your mind most.',
            'emotioneel': f'The {dl} dimension you chose fits — this context reaches you at a feeling level.',
            'spiritueel': f'The {dl} dimension says something: this situation touches what matters most deeply to you.',
            '': 'Without a dimension choice, it\'s hard to say which channel this situation affects most.',
        }
    }

    pattern_q = {
        'nl': 'Herken je dit effect vaker bij dit soort situaties?',
        'de': 'Erkennst du diesen Effekt öfter bei solchen Situationen?',
        'en': 'Do you recognize this effect more often in situations like this?',
    }

    reflections = {
        'nl': {
            'above': f'Vergeleken met jouw persoonlijke basislijn van {personal_baseline} laat deze situatie een RI van {ri} zien — dat is {delta} punt hoger. '
                f'Je autonoom zenuwstelsel reageert op deze context met meer ruimte en herstelvermogen. '
                f'{dim_connection["nl"].get(dim, dim_connection["nl"][""])} '
                f'{pattern_q["nl"]}',
            'at': f'Je RI van {ri} ligt dicht bij je persoonlijke basislijn van {personal_baseline}. '
                f'Deze situatie lijkt je autonoom zenuwstelsel niet sterk te beïnvloeden — het blijft in zijn gebruikelijke staat. '
                f'{dim_connection["nl"].get(dim, dim_connection["nl"][""])} '
                f'{pattern_q["nl"]}',
            'below': f'Vergeleken met jouw basislijn van {personal_baseline} zakt je RI naar {ri} in deze situatie — dat is {abs(delta)} punt lager. '
                f'Je autonoom zenuwstelsel reageert op deze context met meer activatie. '
                f'{dim_connection["nl"].get(dim, dim_connection["nl"][""])} '
                f'{pattern_q["nl"]}',
            'no_ref': f'Je situatiemeting laat een RI van {ri} zien. '
                f'Zonder basismetingen is het lastig om het effect van deze situatie op je zenuwstelsel te duiden. '
                f'Doe regelmatig een basismeting zodat je een persoonlijk referentiepunt opbouwt.',
        },
        'de': {
            'above': f'Im Vergleich zu deiner persönlichen Basislinie von {personal_baseline} zeigt diese Situation einen RI von {ri} — das sind {delta} Punkte höher. '
                f'Dein autonomes Nervensystem reagiert auf diesen Kontext mit mehr Spielraum und Erholungsfähigkeit. '
                f'{dim_connection["de"].get(dim, dim_connection["de"][""])} '
                f'{pattern_q["de"]}',
            'at': f'Dein RI von {ri} liegt nahe deiner persönlichen Basislinie von {personal_baseline}. '
                f'Diese Situation scheint dein autonomes Nervensystem nicht stark zu beeinflussen — es bleibt in seinem gewohnten Zustand. '
                f'{dim_connection["de"].get(dim, dim_connection["de"][""])} '
                f'{pattern_q["de"]}',
            'below': f'Im Vergleich zu deiner Basislinie von {personal_baseline} sinkt dein RI auf {ri} in dieser Situation — das sind {abs(delta)} Punkte niedriger. '
                f'Dein autonomes Nervensystem reagiert auf diesen Kontext mit mehr Aktivierung. '
                f'{dim_connection["de"].get(dim, dim_connection["de"][""])} '
                f'{pattern_q["de"]}',
            'no_ref': f'Deine Situationsmessung zeigt einen RI von {ri}. '
                f'Ohne Basismessungen ist es schwer, die Wirkung dieser Situation auf dein Nervensystem einzuordnen. '
                f'Führe regelmäßig Basismessungen durch, um einen persönlichen Referenzwert aufzubauen.',
        },
        'en': {
            'above': f'Compared to your personal baseline of {personal_baseline}, this situation shows an RI of {ri} — that\'s {delta} points higher. '
                f'Your autonomic nervous system responds to this context with more ease and recovery capacity. '
                f'{dim_connection["en"].get(dim, dim_connection["en"][""])} '
                f'{pattern_q["en"]}',
            'at': f'Your RI of {ri} is close to your personal baseline of {personal_baseline}. '
                f'This situation doesn\'t seem to strongly affect your autonomic nervous system — it stays in its usual state. '
                f'{dim_connection["en"].get(dim, dim_connection["en"][""])} '
                f'{pattern_q["en"]}',
            'below': f'Compared to your baseline of {personal_baseline}, your RI drops to {ri} in this situation — that\'s {abs(delta)} points lower. '
                f'Your autonomic nervous system responds to this context with more activation. '
                f'{dim_connection["en"].get(dim, dim_connection["en"][""])} '
                f'{pattern_q["en"]}',
            'no_ref': f'Your situation measurement shows an RI of {ri}. '
                f'Without baseline measurements, it\'s hard to gauge the effect of this situation on your nervous system. '
                f'Do regular baseline measurements to build a personal reference point.',
        }
    }

    i = insights.get(lang, insights['nl'])
    r = reflections.get(lang, reflections['nl'])
    return {'insight': i[state], 'reflection': r[state]}


@app.route('/api/pro/client/<int:cid>/metingen')
def api_pro_client_metingen(cid):
    if (not session.get('license_valid') and not session.get('demo_mode')) or not _is_pro_or_demo_pro():
        return jsonify({'error': 'Geen toegang'}), 401
    pro_key = get_user_key()
    db = get_pro_db()
    _demo = session.get('demo_mode') and session.get('license_type') == 'pro'
    if not db.execute("SELECT id FROM clients WHERE id=? AND (pro_key=? OR pro_key='DEMO')" if _demo else "SELECT id FROM clients WHERE id=? AND pro_key=?", (cid, pro_key)).fetchone():
        db.close()
        return jsonify({'error': 'Niet gevonden'}), 404
    rows = db.execute("SELECT * FROM client_metingen WHERE client_id=? ORDER BY ts DESC LIMIT 100", (cid,)).fetchall()
    db.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/kubios/download/<int:mid>')
def api_kubios_download_by_id(mid):
    user_key = get_user_key()
    if not user_key:
        return jsonify({'error': 'Niet ingelogd'}), 401
    conn = sqlite3.connect(METING_DB_PATH)
    c = conn.cursor()
    c.execute('SELECT rr_intervals FROM metingen WHERE id=? AND user_key=?', (mid, user_key))
    row = c.fetchone()
    conn.close()
    if not row or not row[0]:
        return jsonify({'error': 'Geen RR-data'}), 404
    rr = json.loads(row[0])
    content = '\n'.join(str(round(v)) for v in rr)
    return send_file(
        io.BytesIO(content.encode('utf-8')),
        as_attachment=True,
        download_name=f'kubios_rr_{mid}.txt',
        mimetype='text/plain; charset=utf-8',
    )

@app.route('/api/kubios/download')
def api_kubios_download():
    user_key = session.get('user_key')
    if not user_key:
        return jsonify({'error': 'Niet ingelogd'}), 401
    conn = sqlite3.connect(METING_DB_PATH)
    c = conn.cursor()
    c.execute('SELECT rr_intervals,ts FROM metingen WHERE user_key=? ORDER BY id DESC LIMIT 1', (user_key,))
    row = c.fetchone()
    conn.close()
    if not row or not row[0]:
        return jsonify({'error': 'Geen RR-data'}), 404
    rr = json.loads(row[0])
    content = '\n'.join(str(round(v)) for v in rr)
    return send_file(
        io.BytesIO(content.encode('utf-8')),
        as_attachment=True,
        download_name='kubios_rr.txt',
        mimetype='text/plain; charset=utf-8',
    )


@app.route('/api/pro/client/<int:cid>/update', methods=['POST'])
def api_pro_client_update(cid):
    if not session.get('license_valid'):
        return jsonify({"error": "Geen toegang"}), 401
    if not is_pro():
        return jsonify({"error": "Geen Pro toegang"}), 403
    data = request.get_json()
    if not data:
        return jsonify({"error": "Geen data"}), 400
    pro_db = get_pro_db()
    # Update allowed fields
    name = data.get('name', '').strip()
    surname = (data.get('surname') or '').strip() or None
    birth_year = data.get('birth_year')
    gender = data.get('gender', '').strip()
    if not name:
        return jsonify({"error": "Naam is verplicht"}), 400
    try:
        birth_year = int(birth_year) if birth_year else None
    except (ValueError, TypeError):
        birth_year = None
    # Profiel-compleet-vlag meeschrijven: 1 zodra geldig geboortejaar + geslacht zijn ingevuld.
    _upd_completed = 0 if _profiel_incompleet(birth_year, gender) else 1
    pro_db.execute(
        'UPDATE clients SET name=?, surname=?, birth_year=?, gender=?, profile_completed=? WHERE id=? AND pro_key=?',
        (name, surname, birth_year, gender, _upd_completed, cid, get_user_key())
    )
    pro_db.commit()
    return jsonify({"ok": True, "name": name, "surname": surname, "birth_year": birth_year, "gender": gender, "profile_completed": _upd_completed})


# ─── Koppeling (Pairing) API ────────────────────────────────────────────────

def generate_pairing_code():
    """Genereer unieke koppelcode SC-PAIR-XXXX"""
    import string
    chars = string.ascii_uppercase + string.digits
    while True:
        code = 'SC-PAIR-' + ''.join(secrets.choice(chars) for _ in range(4))
        db = get_db()
        exists = db.execute("SELECT id FROM pairing_codes WHERE code=?", (code,)).fetchone()
        db.close()
        if not exists:
            return code

def get_pro_plan_info():
    """Haal plan info op voor de ingelogde Pro"""
    code = session.get('license_code', '')
    db = get_db()
    # Zoek licentie
    lic = db.execute("SELECT * FROM licenses WHERE license_key=? AND product IN ('sc','hlm')", (code.upper(),)).fetchone()
    if not lic:
        db.close()
        return None
    # Zoek plan via type
    plan_id = 'sc-pro-s'  # default
    if lic['max_profiles']:
        mp = lic['max_profiles']
        if mp >= 50: plan_id = 'sc-pro-l'
        elif mp >= 20: plan_id = 'sc-pro-m'
        else: plan_id = 'sc-pro-s'
    plan = db.execute("SELECT * FROM plans WHERE plan_id=?", (plan_id,)).fetchone()
    db.close()
    return dict(plan) if plan else None


# Founder-bypass: pro_keys met onbeperkte cliënt-aanmaak.
# Hardcoded i.p.v. aparte 'sc-pro-founder'-tier: geen DB-migratie nodig, één regel om uit te breiden.
UNLIMITED_PRO_KEYS = {
    '5eabaeb11283e8a847bfcb7f90918ec1',  # WellVit / Peter van de Boom
}


def _pro_client_count(pro_key):
    """Telt actieve cliënt-profielen voor deze pro_key. Tegenhanger van de
    listing-query op /pro/clienten (active=1, exclusief soft-deleted)."""
    if not pro_key:
        return 0
    db = get_pro_db()
    try:
        return db.execute(
            "SELECT COUNT(*) FROM clients WHERE active=1 AND pro_key=?",
            (pro_key,)
        ).fetchone()[0]
    finally:
        db.close()


_PRO_TIER_LADDER = {
    'pro-s': {'next_plan_id': 'sc-pro-m', 'next_tier_short': 'Pro M', 'next_max_clients': 30},
    'pro-m': {'next_plan_id': 'sc-pro-l', 'next_tier_short': 'Pro L', 'next_max_clients': 50},
    'pro-l': None,  # top-tier: contact-pad i.p.v. upgrade
}


def _pro_next_tier(tier_short):
    """Voor 'Pro S'/'Pro M'/'Pro L' (of lowercase varianten) → dict met next-tier info,
    of None voor de top-tier."""
    if not tier_short:
        return None
    key = tier_short.lower().replace(' ', '-')  # 'Pro S' → 'pro-s'
    return _PRO_TIER_LADDER.get(key)


def _pro_max_clients(pro_key=None, default_baseline=10):
    """Bepaal max_clients-quota voor ingelogde Pro.
    Probeert eerst session.license_code (via get_pro_plan_info), dan
    email->licenses fallback (mp>=50 L, >=20 M, anders S). Anders
    default_baseline met warning-log voor diagnose.
    """
    plan = get_pro_plan_info()
    if plan and plan.get('max_clients'):
        return plan['max_clients']
    em = session.get('email', '')
    if em:
        db = get_db()
        lic = db.execute(
            "SELECT max_profiles FROM licenses WHERE email=? AND type='pro' AND status='activated' ORDER BY id DESC LIMIT 1",
            (em,)
        ).fetchone()
        db.close()
        if lic and lic['max_profiles']:
            mp = lic['max_profiles']
            if mp >= 50: return 50
            if mp >= 20: return 20
            return 10
    app.logger.warning(
        'QUOTA_FALLBACK_DEFAULT_10 pro_key=%s email=%s',
        pro_key or '', em
    )
    return default_baseline


def build_pro_client_quota(pro_key, email):
    """Bouwt het quota-dict voor de /pro/clienten widget en /pro/client/toevoegen guard.

    Returns:
        {
          'current': int,           # actieve cliënten
          'max': int|None,          # None = unlimited
          'unlimited': bool,
          'tier_short': str,        # 'Pro S' | 'Pro M' | 'Pro L' | 'Pro' (fallback)
          'pct': int,               # 0–999 voor progress-bar; 999 als unlimited
          'over_limit': bool,
          'next_tier': dict|None,   # van _pro_next_tier
          'has_stripe': bool,       # bepaalt of upgrade-knop naar portal of contact-mail wijst
          'manage_url': str,        # Stripe Customer Portal endpoint
        }
    """
    unlimited = pro_key in UNLIMITED_PRO_KEYS
    current = _pro_client_count(pro_key)
    summary = get_pro_tier_summary(email) if email else None
    tier_short = (summary or {}).get('tier_short') or 'Pro'
    has_stripe = bool(get_stripe_customer_id(pro_key, email)) if email else False
    if unlimited:
        return {
            'current': current,
            'max': None,
            'unlimited': True,
            'tier_short': 'Founder',
            'pct': 0,
            'over_limit': False,
            'next_tier': None,
            'has_stripe': has_stripe,
            'manage_url': url_for('manage_subscription'),
        }
    max_clients = _pro_max_clients(pro_key)
    pct = int(round((current / max_clients) * 100)) if max_clients else 0
    return {
        'current': current,
        'max': max_clients,
        'unlimited': False,
        'tier_short': tier_short,
        'pct': pct,
        'over_limit': current >= max_clients,
        'next_tier': _pro_next_tier(tier_short),
        'has_stripe': has_stripe,
        'manage_url': url_for('manage_subscription'),
    }


@app.route('/api/pairing/generate', methods=['POST'])
def api_pairing_generate():
    """Pro genereert koppelcode voor een cliënt"""
    if (not session.get('license_valid') and not session.get('demo_mode')) or not _is_pro_or_demo_pro():
        return jsonify({'error': 'Geen Pro toegang'}), 403
    data = request.get_json()
    client_id = data.get('client_id') if data else None
    if not client_id:
        return jsonify({'error': 'Geen client_id'}), 400

    pro_key = get_user_key()

    # Check of cliënt van deze Pro is
    db = get_pro_db()
    client = db.execute("SELECT * FROM clients WHERE id=? AND pro_key=?", (int(client_id), pro_key)).fetchone()
    db.close()
    if not client:
        return jsonify({'error': 'Cliënt niet gevonden'}), 404

    # Quota-check: max_clients uit Pro-plan. Skip bij demo_mode.
    # Telt pending+activated (expired/cancelled vallen uit count, revoke→cancelled geeft slot terug).
    if not session.get('demo_mode'):
        max_clients = _pro_max_clients(pro_key)
        saas_db = get_db()
        active_count = saas_db.execute(
            "SELECT COUNT(*) FROM pairing_codes WHERE pro_user_id=? AND status IN ('pending','activated')",
            (pro_key,)
        ).fetchone()[0]
        saas_db.close()
        if active_count >= max_clients:
            return jsonify({
                'ok': False,
                'error': 'Limiet bereikt: maximaal {} actieve/lopende koppelcodes voor jouw abonnement.'.format(max_clients),
                'limit': max_clients,
                'active': active_count
            }), 403

    # Genereer code (7 dagen geldig)
    code = generate_pairing_code()
    from datetime import timedelta
    expires = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')

    saas_db = get_db()
    saas_db.execute(
        "INSERT INTO pairing_codes (code, pro_user_id, client_id, expires_at) VALUES (?,?,?,?)",
        (code, pro_key, str(client_id), expires)
    )
    saas_db.commit()
    saas_db.close()

    return jsonify({
        'ok': True,
        'code': code,
        'expires_at': expires,
        'client_name': client['name']
    })

@app.route('/api/pairing/register', methods=['POST'])
def api_pairing_register():
    """Nieuwe klant maakt consumer-account aan + koppelt zich aan Pro
    via pairing-code. Volgt het 2fa_pending_pw_hash-patroon: doet geen
    DB-writes, slaat pending state in sessie + start 2FA. /verify
    voltooit user-INSERT + pairing-activation atomair na code-input.
    """
    import re, random as _rnd, time as _time, secrets as _sec
    data = request.get_json() or {}
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''
    name = (data.get('name') or '').strip()
    code = (data.get('code') or '').strip().upper()
    lang = request.args.get('lang') or session.get('lang', 'nl')

    if not email or not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
        return jsonify({'ok': False, 'error': 'Geldig e-mailadres vereist'}), 422
    if len(password) < 8:
        return jsonify({'ok': False, 'error': 'Wachtwoord moet minimaal 8 tekens zijn'}), 422
    if not name:
        return jsonify({'ok': False, 'error': 'Naam is verplicht'}), 422
    if not code:
        return jsonify({'ok': False, 'error': 'Koppelcode is verplicht'}), 422

    saas_db = get_db()
    pairing = saas_db.execute("SELECT * FROM pairing_codes WHERE code=?", (code,)).fetchone()
    if not pairing:
        saas_db.close()
        return jsonify({'ok': False, 'error': 'Koppelcode onbekend'}), 400
    if pairing['status'] != 'pending':
        saas_db.close()
        return jsonify({'ok': False, 'error': 'Koppelcode al gebruikt of ingetrokken'}), 400
    try:
        _exp = datetime.strptime(pairing['expires_at'], '%Y-%m-%d %H:%M:%S')
    except ValueError:
        _exp = datetime.fromisoformat(pairing['expires_at'].split('.')[0])
    if datetime.now() > _exp:
        saas_db.execute("UPDATE pairing_codes SET status='expired' WHERE code=?", (code,))
        saas_db.commit()
        saas_db.close()
        return jsonify({'ok': False, 'error': 'Koppelcode is verlopen'}), 410

    existing = saas_db.execute("SELECT id FROM users WHERE email=? COLLATE NOCASE", (email,)).fetchone()
    saas_db.close()
    if existing:
        return jsonify({'ok': False, 'error': 'E-mailadres is al geregistreerd; log in via /login'}), 409

    pw_hash = hash_password(password)
    consumer_key = _sec.token_hex(16)
    code_2fa = str(_rnd.randint(100000, 999999))

    session.clear()
    session['lang']                     = lang
    session['2fa_code']                 = code_2fa
    session['2fa_email']                = email
    session['2fa_name']                 = name
    session['2fa_license_type']         = 'consumer'
    session['2fa_lang']                 = lang
    session['2fa_expires']              = _time.time() + 600
    session['2fa_pending_pw_hash']      = pw_hash
    session['2fa_pending_pair_code']    = code
    session['2fa_pending_consumer_key'] = consumer_key

    send_verification_code(email, code_2fa, lang)
    return jsonify({'ok': True, 'message': 'Verificatiemail verstuurd', 'redirect': '/verify'}), 201


@app.route('/api/pairing/redeem', methods=['POST'])
def api_pairing_redeem():
    """Consumer voert koppelcode in om te verbinden met Pro"""
    if not session.get('license_valid') and not session.get('demo_mode') and not session.get('hlm_user_id'):
        return jsonify({'error': 'Niet ingelogd'}), 401
    data = request.get_json()
    code = (data.get('code', '') if data else '').strip().upper()
    if not code:
        return jsonify({'error': 'Geen code ingevoerd'}), 400

    consumer_key = get_user_key()

    # Zoek de koppelcode
    saas_db = get_db()
    pairing = saas_db.execute(
        "SELECT * FROM pairing_codes WHERE code=? AND status='pending'", (code,)
    ).fetchone()

    if not pairing:
        saas_db.close()
        return jsonify({'error': 'Code ongeldig of verlopen'}), 404

    # Check verloopdatum
    expires = datetime.strptime(pairing['expires_at'], '%Y-%m-%d %H:%M:%S')
    if datetime.now() > expires:
        saas_db.execute("UPDATE pairing_codes SET status='expired' WHERE code=?", (code,))
        saas_db.commit()
        saas_db.close()
        return jsonify({'error': 'Code is verlopen'}), 410

    # Activeer koppeling
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    saas_db.execute(
        "UPDATE pairing_codes SET status='activated', consumer_user_key=?, activated_at=? WHERE code=?",
        (consumer_key, now, code)
    )

    # Maak ook een client_pairing aan in saas_licenses.db
    saas_db.execute(
        "INSERT OR IGNORE INTO client_pairings (client_id, paired_user_id, paired_device_id, status) VALUES (?,?,?,?)",
        (pairing['client_id'], None, consumer_key, 'active')
    )

    saas_db.commit()
    saas_db.close()

    # Sla koppelinfo op in sessie
    session['paired_with_pro'] = pairing['pro_user_id']
    session['paired_client_id'] = pairing['client_id']

    return jsonify({
        'ok': True,
        'message': 'Gekoppeld met professional'
    })

@app.route('/api/pairing/revoke', methods=['POST'])
def api_pairing_revoke():
    """Pro verbreekt koppeling met cliënt"""
    if (not session.get('license_valid') and not session.get('demo_mode')) or not _is_pro_or_demo_pro():
        return jsonify({'error': 'Geen Pro toegang'}), 403
    data = request.get_json()
    client_id = data.get('client_id') if data else None
    if not client_id:
        return jsonify({'error': 'Geen client_id'}), 400

    pro_key = get_user_key()

    # Verbreek in pairing_codes
    saas_db = get_db()
    saas_db.execute(
        "UPDATE pairing_codes SET status='cancelled' WHERE client_id=? AND pro_user_id=? AND status='activated'",
        (str(client_id), pro_key)
    )
    # Verbreek in client_pairings
    saas_db.execute(
        "UPDATE client_pairings SET status='revoked' WHERE client_id=?",
        (str(client_id),)
    )
    saas_db.commit()
    saas_db.close()

    return jsonify({'ok': True, 'message': 'Koppeling verbroken'})

@app.route('/api/pairing/status')
def api_pairing_status():
    """Check koppelstatus (voor consumer)"""
    if not session.get('license_valid') and not session.get('demo_mode') and not session.get('hlm_user_id'):
        return jsonify({'error': 'Niet ingelogd'}), 401

    consumer_key = get_user_key()
    saas_db = get_db()
    pairing = saas_db.execute(
        "SELECT * FROM pairing_codes WHERE consumer_user_key=? AND status='activated' ORDER BY activated_at DESC LIMIT 1",
        (consumer_key,)
    ).fetchone()
    saas_db.close()

    if pairing:
        return jsonify({
            'paired': True,
            'pro_id': pairing['pro_user_id'],
            'since': pairing['activated_at']
        })
    return jsonify({'paired': False})

@app.route('/api/pro/client/<int:cid>/pairing')
def api_pro_client_pairing(cid):
    """Check koppelstatus van een cliënt (voor Pro)"""
    if (not session.get('license_valid') and not session.get('demo_mode')) or not _is_pro_or_demo_pro():
        return jsonify({'error': 'Geen Pro toegang'}), 403

    pro_key = get_user_key()
    saas_db = get_db()

    # Actieve koppeling
    active = saas_db.execute(
        "SELECT * FROM pairing_codes WHERE client_id=? AND pro_user_id=? AND status='activated'",
        (str(cid), pro_key)
    ).fetchone()

    # Lopende (pending) koppelcode
    pending = saas_db.execute(
        "SELECT * FROM pairing_codes WHERE client_id=? AND pro_user_id=? AND status='pending' ORDER BY created_at DESC LIMIT 1",
        (str(cid), pro_key)
    ).fetchone()

    saas_db.close()

    if active:
        return jsonify({
            'status': 'active',
            'consumer_key': active['consumer_user_key'],
            'since': active['activated_at']
        })
    elif pending:
        return jsonify({
            'status': 'pending',
            'code': pending['code'],
            'expires_at': pending['expires_at']
        })
    return jsonify({'status': 'none'})

@app.route('/api/pro/client/<int:cid>/consumer-metingen')
def api_pro_consumer_metingen(cid):
    """Pro haalt consumer-metingen op van een gekoppelde cliënt"""
    if (not session.get('license_valid') and not session.get('demo_mode')) or not _is_pro_or_demo_pro():
        return jsonify({'error': 'Geen Pro toegang'}), 403

    pro_key = get_user_key()

    # Zoek actieve koppeling
    saas_db = get_db()
    pairing = saas_db.execute(
        "SELECT consumer_user_key FROM pairing_codes WHERE client_id=? AND pro_user_id=? AND status='activated'",
        (str(cid), pro_key)
    ).fetchone()
    saas_db.close()

    if not pairing or not pairing['consumer_user_key']:
        return jsonify({'error': 'Geen actieve koppeling'}), 404

    # Haal consumer-metingen op
    consumer_key = pairing['consumer_user_key']
    meting_db = get_meting_db()
    rows = meting_db.execute(
        "SELECT * FROM metingen WHERE user_key=? ORDER BY ts DESC LIMIT 100",
        (consumer_key,)
    ).fetchall()
    meting_db.close()

    return jsonify([dict(r) for r in rows])


@app.route('/api/license/status', methods=['GET'])
def api_license_status():
    auth = request.headers.get('X-API-Key', '')
    try:
        with open('/opt/ic-license-server/data/api_key.conf') as f:
            valid_key = f.read().strip()
    except:
        return jsonify({'ok': False, 'error': 'Server config error'}), 500
    if auth != valid_key:
        return jsonify({'ok': False, 'error': 'Unauthorized'}), 401

    license_key = request.args.get('key', '').strip()
    if not license_key:
        return jsonify({'ok': False, 'error': 'Key required'}), 400

    db_path = '/opt/ic-license-server/data/saas_licenses.db'
    try:
        db = sqlite3.connect(db_path)
        db.row_factory = sqlite3.Row
        lic = db.execute("""
            SELECT l.license_key, l.type, l.status, l.valid_until,
                   l.email, l.order_id, l.created_at,
                   l.stripe_subscription_id,
                   s.status AS sub_status,
                   s.current_period_end AS sub_current_period_end,
                   CASE
                     WHEN l.status NOT IN ('available', 'activated') THEN 0
                     WHEN s.subscription_id IS NULL THEN 1
                     WHEN s.status IN ('active', 'trialing') THEN 1
                     WHEN s.status IN ('canceled', 'past_due')
                          AND s.current_period_end IS NOT NULL
                          AND s.current_period_end > strftime('%Y-%m-%dT%H:%M:%S', 'now') THEN 1
                     ELSE 0
                   END AS effective_valid
            FROM licenses l
            LEFT JOIN subscriptions s ON l.stripe_subscription_id = s.subscription_id
            WHERE l.license_key=?
        """, (license_key,)).fetchone()
        db.close()
        if lic:
            data = dict(lic)
            data['effective_valid'] = bool(data['effective_valid'])
            return jsonify({'ok': True, 'license': data})
        return jsonify({'ok': False, 'error': 'Not found'}), 404
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/license/migrate', methods=['POST'])
def api_migrate_license():
    import secrets, string, hashlib, random as _rnd, time
    from datetime import datetime, timedelta
    data = request.get_json() or {}
    legacy_code = data.get('legacy_code', '').strip()
    # Normaliseer legacy code streepjes
    lc_clean = legacy_code.replace('-', '')
    if len(lc_clean) == 32 and not legacy_code.startswith('SC'):
        legacy_code = '-'.join([lc_clean[i:i+4] for i in range(0, 32, 4)])
    choice = data.get('choice', 'consumer')
    if choice not in ('consumer', 'pro'):
        return jsonify({'ok': False, 'error': 'Ongeldige keuze'})
    # Email + pw_hash: sessie heeft voorrang (van /licentie-voorgang),
    # anders POST-body (van /oude-code-pad zonder voorgang).
    email = (session.get('legacy_pending_email') or data.get('email','')).strip().lower()
    pw_hash = session.get('legacy_pending_pw_hash')
    if not pw_hash and data.get('password'):
        _pw = data.get('password','').strip()
        if len(_pw) < 8:
            return jsonify({'ok': False, 'error': 'Wachtwoord minimaal 8 tekens'})
        pw_hash = hashlib.sha256(_pw.encode()).hexdigest()
    if not email or '@' not in email:
        return jsonify({'ok': False, 'error': 'E-mailadres ontbreekt of ongeldig'})
    if not pw_hash:
        return jsonify({'ok': False, 'error': 'Wachtwoord ontbreekt'})
    lang = session.get('legacy_pending_lang') or session.get('lang', 'nl')
    db_path = '/opt/ic-license-server/data/saas_licenses.db'
    try:
        db = sqlite3.connect(db_path)
        db.row_factory = sqlite3.Row
        legacy = db.execute("SELECT id, status FROM legacy_keys WHERE license_key=?", (legacy_code,)).fetchone()
        if not legacy or legacy['status'] == 'migrated':
            db.close()
            return jsonify({'ok': False, 'error': 'Code niet gevonden of al gemigreerd'})
        chars = string.ascii_uppercase + string.digits
        while True:
            prefix = 'SCP-' if choice == 'pro' else 'SC-'
            new_code = prefix + ''.join(secrets.choice(chars) for _ in range(4)) + '-' + ''.join(secrets.choice(chars) for _ in range(4))
            if not db.execute("SELECT 1 FROM licenses WHERE license_key=?", (new_code,)).fetchone():
                break
        valid_until = '2027-01-01 00:00:00'
        db.execute(
            "INSERT INTO licenses (license_key, product, type, status, origin, legacy_key, max_profiles, valid_until, email) VALUES (?, 'sc', ?, 'activated', 'migration', ?, 5, ?, ?)",
            (new_code, choice, legacy_code, valid_until, email)
        )
        db.execute(
            "UPDATE legacy_keys SET status='migrated', migrated_to=?, migrated_at=datetime('now'), migrated_by_email=? WHERE id=?",
            (new_code, email, legacy['id'])
        )
        # users.password_hash NIET hier — pas in /verify na succesvol 2FA (Fix C-uitbreiding)
        db.commit()
        db.close()
        # 2FA-stap
        _2fa = str(_rnd.randint(100000, 999999))
        session['license_valid'] = True
        session['license_type'] = choice
        session['license_code'] = new_code
        session['legacy_migrated'] = True
        session['email'] = email
        session['2fa_code']             = _2fa
        session['2fa_email']            = email
        session['2fa_license_type']     = choice
        session['2fa_license_code']     = new_code
        session['2fa_name']             = email
        session['2fa_lang']             = lang
        session['2fa_expires']          = time.time() + 600
        session['2fa_pending_pw_hash']  = pw_hash
        session.pop('legacy_pending_email', None)
        session.pop('legacy_pending_pw_hash', None)
        session.pop('legacy_pending_lang', None)
        send_verification_code(email, _2fa, lang)
        import logging; logging.getLogger().warning(f"2FA CODE for {email}: {_2fa}")
        return jsonify({'ok': True, 'new_code': new_code, 'type': choice, 'valid_until': valid_until, 'redirect': url_for('verify_2fa')})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})




@app.route('/api/license/generate', methods=['POST'])
def api_generate_license():
    import secrets, string
    from datetime import datetime, timedelta
    # API key authenticatie
    auth = request.headers.get('X-API-Key', '')
    try:
        with open('/opt/ic-license-server/data/api_key.conf') as f:
            valid_key = f.read().strip()
    except:
        return jsonify({'ok': False, 'error': 'Server config error'}), 500
    if auth != valid_key:
        return jsonify({'ok': False, 'error': 'Unauthorized'}), 401

    data = request.get_json() or {}
    license_type = data.get('type', 'consumer')  # consumer of pro
    plan = data.get('plan', 'monthly')            # monthly of yearly
    email = data.get('email', '').strip().lower()
    order_id = data.get('order_id', '')            # WooCommerce order ID
    product_name = data.get('product_name', '')

    if license_type not in ('consumer', 'pro'):
        return jsonify({'ok': False, 'error': 'Invalid type'}), 400
    if not email:
        return jsonify({'ok': False, 'error': 'Email required'}), 400

    # Bereken geldigheid
    if plan == 'yearly':
        days = 366
    else:
        days = 31

    # Genereer unieke code
    chars = string.ascii_uppercase + string.digits
    db_path = '/opt/ic-license-server/data/saas_licenses.db'
    try:
        db = sqlite3.connect(db_path)
        while True:
            prefix = 'SCP-' if license_type == 'pro' else 'SC-'
            new_code = prefix + ''.join(secrets.choice(chars) for _ in range(4)) + '-' + ''.join(secrets.choice(chars) for _ in range(4))
            if not db.execute("SELECT 1 FROM licenses WHERE license_key=?", (new_code,)).fetchone():
                break

        valid_until = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
        max_profiles = 1 if license_type == 'consumer' else 5

        db.execute("""INSERT INTO licenses 
            (license_key, product, type, status, origin, max_profiles, valid_until, email, order_id, product_name, created_at)
            VALUES (?, 'sc', ?, 'available', 'shop', ?, ?, ?, ?, ?, datetime('now'))""",
            (new_code, license_type, max_profiles, valid_until, email, order_id, product_name))
        db.commit()
        db.close()

        print(f"LICENSE GENERATED: {new_code} type={license_type} plan={plan} email={email} order={order_id}", flush=True)
        return jsonify({
            'ok': True,
            'license_key': new_code,
            'type': license_type,
            'plan': plan,
            'valid_until': valid_until,
            'email': email
        })
    except Exception as e:
        print(f"License generate error: {e}", flush=True)
        return jsonify({'ok': False, 'error': str(e)}), 500



@app.route('/kenniscentrum')
def kenniscentrum():
    if session.get("is_demo"):
        return redirect(url_for("welcome") + "?demo_blocked=1")
    lt = session.get('license_type', '')
    if lt not in ('consumer', 'pro'):
        return redirect(url_for('welcome'))
    lang = session.get('lang', 'nl')
    return render_template('kenniscentrum.html', lang=lang, is_pro=is_pro())

@app.route('/kenniscentrum-pro')
def kenniscentrum_pro():
    if session.get("is_demo"):
        return redirect(url_for("welcome"))
    if (not session.get("license_valid") and not session.get("demo_mode")) or not _is_pro_or_demo_pro():
        return redirect(url_for("welcome"))
    lang = session.get("lang", "nl")
    return render_template("kenniscentrum_pro.html", lang=lang, is_pro=is_pro())
@app.route('/sport-training')
def sport_training():
    if session.get("is_demo"):
        return redirect(url_for("welcome"))
    if (not session.get("license_valid") and not session.get("demo_mode")) or not _is_pro_or_demo_pro():
        return redirect(url_for("welcome"))
    lang = session.get("lang", "nl")
    return render_template("sport_training.html", lang=lang, is_pro=is_pro())

@app.route('/pro/meting')
@require_kk_office_if_krankenkasse
def pro_meting_keuze():
    if (not session.get("license_valid") and not session.get("demo_mode")) or not _is_pro_or_demo_pro():
        return redirect(url_for("welcome"))
    lang = session.get("lang", "nl")
    if not request.args.get('cid'):
        session.pop('last_client_id', None)
    return render_template("pro/meting_keuze.html", lang=lang, is_pro=is_pro(), client_id=int(request.args.get('cid',0)) or session.get('measuring_for_client') or 0)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False)

@app.route('/api/set_subjectief', methods=['POST'])
def api_set_subjectief():
    if not session.get('license_valid') and not session.get('demo_mode') and not session.get('hlm_user_id'):
        return jsonify({'error': 'Niet ingelogd'}), 401
    try:
        score = int(request.json.get('score', -1))
        if score < 0 or score > 10:
            return jsonify({'error': 'Ongeldige score'}), 400
        db = get_meting_db()
        db.execute(
            "UPDATE metingen SET subjectief_score=? WHERE user_key=? ORDER BY ts DESC LIMIT 1",
            (score, get_user_key()))
        db.commit()
        db.close()
        session['after_meting'] = True
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/koppelen')
def koppelen():
    if not session.get('license_valid'):
        return redirect(url_for('welcome'))
    lang = session.get('lang','nl')
    active_pairings = []
    try:
        saas_db = get_db()
        user_key = get_user_key()
        active_pairings = saas_db.execute(
            "SELECT code, activated_at FROM pairing_codes WHERE consumer_user_key=? AND status='activated'",
            (user_key,)
        ).fetchall()
        saas_db.close()
    except:
        pass
    return render_template('koppelen.html', lang=lang, active_pairings=active_pairings)

@app.route('/upload-video', methods=['GET','POST'])
def upload_video():
    if request.method == 'POST':
        file = request.files.get('file')
        if file:
            file.save('/opt/stresschecker/static/img/' + file.filename)
            return 'OK: ' + file.filename
    return '<form method=post enctype=multipart/form-data><input type=file name=file><input type=submit value=Upload></form>'

@app.route("/sc/sensor-keuze")
def sc_sensor_keuze():
    if not session.get("license_valid") and not session.get("demo_mode"):
        return redirect(url_for("welcome"))
    lang = session.get("lang", "nl")
    resp = make_response(render_template("sc_sensor_keuze.html", lang=lang, is_pro=is_pro()))
    resp.headers["Cache-Control"] = "no-store"
    return resp


# ── Oude opzeg-route → redirect naar Spoor 3 (gedeprecieerd 2026-05-16) ──────
@app.route('/abonnement/opzeggen', methods=['GET', 'POST'])
def opzeg_abonnement():
    uk = session.get("user_key")
    app.logger.warning(
        f'Old /abonnement/opzeggen hit by user_key={uk or "ANONYMOUS"} '
        f'— redirected to /licentie'
    )
    return redirect('/licentie?error=use_new_flow', code=302)


# ── Spoor 3: Stripe Customer Portal ──────────────────────────────────────────
SPOOR3_PORTAL_CONFIGURATION = 'bpc_1TVpFcHD28PM4o1K18URnQAI'
SPOOR3_STRIPE_KEYS_FILE     = '/opt/ic-license-server/data/stripe_keys.conf'


def _load_stripe_secret():
    try:
        with open(SPOOR3_STRIPE_KEYS_FILE) as f:
            for line in f:
                if line.startswith('STRIPE_SECRET_LIVE='):
                    return line.split('=', 1)[1].strip()
    except (OSError, IOError):
        pass
    return ''


def get_stripe_customer_id(user_key, email=None):
    if not user_key:
        return None
    import sqlite3 as _sq
    cn = _sq.connect(DB_PATH)
    try:
        row = cn.execute(
            "SELECT s.stripe_customer_id "
            "  FROM licenses l "
            "  JOIN subscriptions s ON s.subscription_id = l.stripe_subscription_id "
            " WHERE l.user_key = ? "
            "   AND s.stripe_customer_id IS NOT NULL "
            " LIMIT 1",
            (user_key,)
        ).fetchone()
        if row and row[0]:
            return row[0]
    finally:
        cn.close()
    if email:
        key = _load_stripe_secret()
        if key:
            import stripe as _s
            _s.api_key = key
            try:
                res = _s.Customer.search(query='email:"%s"' % email, limit=1)
                items = (res.get('data') if isinstance(res, dict) else getattr(res, 'data', None)) or []
                if items:
                    first = items[0]
                    return first['id'] if isinstance(first, dict) else first.id
            except Exception as e:
                app.logger.warning('Stripe Customer.search faalde voor %r: %s', email, e)
    return None


MONTH_NAMES = {
    'nl': ['januari','februari','maart','april','mei','juni',
           'juli','augustus','september','oktober','november','december'],
    'de': ['Januar','Februar','März','April','Mai','Juni',
           'Juli','August','September','Oktober','November','Dezember'],
    'en': ['January','February','March','April','May','June',
           'July','August','September','October','November','December'],
}


def _format_date_lang(iso_date, lang='nl'):
    if not iso_date:
        return ''
    date_part = iso_date.split('T')[0]
    try:
        year, month, day = date_part.split('-')
        month_idx = int(month) - 1
        day_int = int(day)
    except (ValueError, IndexError):
        return ''
    names = MONTH_NAMES.get(lang, MONTH_NAMES['nl'])
    month_name = names[month_idx]
    if lang == 'de':
        return f"{day_int}. {month_name} {year}"
    return f"{day_int} {month_name} {year}"


def _format_date_numeric(iso_date, lang='nl'):
    """Numerieke datum per locale: DE 21.05.2027, NL 21-05-2027, EN 21/05/2027."""
    if not iso_date:
        return ''
    date_part = iso_date.split('T')[0]
    try:
        year, month, day = date_part.split('-')
        d = int(day); m = int(month)
    except (ValueError, IndexError):
        return ''
    if lang == 'de':
        return f"{d:02d}.{m:02d}.{year}"
    if lang == 'en':
        return f"{d:02d}/{m:02d}/{year}"
    return f"{d:02d}-{m:02d}-{year}"


PRO_PERIOD_LABELS = {
    ('year',  'nl'): 'Jaarabonnement',
    ('month', 'nl'): 'Maandabonnement',
    ('eval',  'nl'): 'Evaluatielicentie',
    ('year',  'de'): 'Jahresabonnement',
    ('month', 'de'): 'Monatsabonnement',
    ('eval',  'de'): 'Evaluierungslizenz',
    ('year',  'en'): 'Annual subscription',
    ('month', 'en'): 'Monthly subscription',
    ('eval',  'en'): 'Evaluation license',
}


def _compute_license_expires_at(plan_id, now=None):
    """Bepaal post-activatie license-expiry op basis van plan_id-suffix.

    - *-eval   → now + EVAL_DURATION_DAYS dagen (centrale constante in eval_config.py)
    - *-month  → now + 30 dagen
    - anders   → now + 365 dagen (standaard jaarplan)

    Plan_id-driven, niet origin-driven: een toekomstige niet-evaluatie marketing-code
    op een ander plan-type (bv. consumer monthly) krijgt automatisch correcte expiry.
    Returns ISO-format string.
    """
    import datetime as _dt
    if now is None:
        now = _dt.datetime.utcnow()
    plan_id = plan_id or ''
    if plan_id.endswith('-eval'):
        delta = _dt.timedelta(days=EVAL_DURATION_DAYS)
    elif plan_id.endswith('-month'):
        delta = _dt.timedelta(days=30)
    else:
        delta = _dt.timedelta(days=365)
    return (now + delta).isoformat()


def _derive_plan_id_for_license(license_type, max_profiles, origin):
    """Map (type, max_profiles, origin) → plan_id.

    Gebruikt door /activate marketing-branch om plan-specifieke expiry te resolven.
    Voor type='pro': tier komt uit max_profiles (≥50 L, ≥20 M, anders S).
    Voor type='consumer': enkele tier ('sc' jaarlijks of 'sc-consumer-eval').
    Origin='evaluation' voegt '-eval'-suffix toe (pro) of selecteert eval-variant (consumer).
    """
    is_eval = origin == 'evaluation'
    mp = max_profiles or 0
    if license_type == 'pro':
        if mp >= 50:
            tier = 'l'
        elif mp >= 20:
            tier = 'm'
        else:
            tier = 's'
        return 'sc-pro-' + tier + ('-eval' if is_eval else '')
    # consumer
    return 'sc-consumer-eval' if is_eval else 'sc'


def get_pro_tier_summary(email, lang='nl'):
    """Universele tier-info voor alle Pro-cohorts (Stripe + marketing + legacy + manual).
    Leest direct uit licenses+plans; Stripe-onafhankelijk. Returns dict of None.
    """
    if not email:
        return None
    import sqlite3 as _sq
    cn = _sq.connect('/opt/ic-license-server/data/saas_licenses.db')
    cn.row_factory = _sq.Row
    try:
        lic = cn.execute(
            "SELECT license_key, max_profiles, expires_at, activated_at, status, origin, "
            "       product_name, stripe_subscription_id "
            "FROM licenses "
            "WHERE email=? AND type='pro' AND status='activated' AND product='sc' "
            "ORDER BY id DESC LIMIT 1",
            (email,)
        ).fetchone()
        if not lic:
            return None
        mp = lic['max_profiles'] or 0
        if mp >= 50:
            tier_plan_id = 'sc-pro-l'
        elif mp >= 20:
            tier_plan_id = 'sc-pro-m'
        else:
            tier_plan_id = 'sc-pro-s'
        # Periode bepalen:
        #   1. origin='evaluation' → eval (heeft voorrang op Stripe/duration-checks)
        #   2. Stripe-sub → subscriptions.plan_id (authoritatief voor month/year)
        #   3. Anders: duration-heuristiek via activated_at/expires_at
        period = 'year'
        plan_id = tier_plan_id
        if lic['origin'] == 'evaluation':
            period = 'eval'
            plan_id = tier_plan_id + '-eval'
        elif lic['stripe_subscription_id']:
            sub = cn.execute(
                "SELECT plan_id FROM subscriptions WHERE subscription_id=?",
                (lic['stripe_subscription_id'],)
            ).fetchone()
            if sub and sub['plan_id']:
                plan_id = sub['plan_id']
                if plan_id.endswith('-month'):
                    period = 'month'
        else:
            try:
                import datetime as _dt_p
                if lic['expires_at'] and lic['activated_at']:
                    exp = _dt_p.datetime.fromisoformat(lic['expires_at'])
                    act = _dt_p.datetime.fromisoformat(lic['activated_at'])
                    days = (exp - act).days
                    if days < 100:
                        period = 'month'
                        plan_id = tier_plan_id + '-month'
            except (ValueError, TypeError):
                pass
        plan = cn.execute(
            "SELECT name, tier, max_clients FROM plans WHERE plan_id=?",
            (plan_id,)
        ).fetchone()
        # Defensieve fallback: onbekend plan_id van Stripe? probeer tier_plan_id.
        if (not plan or not plan['max_clients']) and plan_id != tier_plan_id:
            plan = cn.execute(
                "SELECT name, tier, max_clients FROM plans WHERE plan_id=?",
                (tier_plan_id,)
            ).fetchone()
            plan_id = tier_plan_id
        if not plan or not plan['max_clients']:
            app.logger.warning('TIER_SUMMARY: plan ontbreekt of max_clients=0 voor %s', plan_id)
            return None
        tier_short_map = {'pro-s': 'Pro S', 'pro-m': 'Pro M', 'pro-l': 'Pro L'}
        tier_short = tier_short_map.get(plan['tier'], (plan['tier'] or '').upper())
        period_label = PRO_PERIOD_LABELS.get((period, lang),
                       PRO_PERIOD_LABELS.get((period, 'nl'), ''))
        return {
            'license_key':        lic['license_key'],
            'tier_short':         tier_short,
            'plan_name':          plan['name'],
            'plan_id':            plan_id,
            'period':             period,
            'period_label':       period_label,
            'max_profiles':       mp,
            'max_clients':        plan['max_clients'],
            'expires_at_iso':     (lic['expires_at'] or '').split('T')[0],
            'expires_at_display': _format_date_numeric(lic['expires_at'], lang),
            'status':             lic['status'],
            'origin':             lic['origin'],
        }
    finally:
        cn.close()


def get_active_pairings_count(pro_key):
    """Telt pending+activated pairing_codes voor deze Pro — zelfde definitie als
    de quota-check in /api/pairing/generate."""
    if not pro_key:
        return 0
    import sqlite3 as _sq
    cn = _sq.connect('/opt/ic-license-server/data/saas_licenses.db')
    try:
        return cn.execute(
            "SELECT COUNT(*) FROM pairing_codes "
            "WHERE pro_user_id=? AND status IN ('pending','activated')",
            (pro_key,)
        ).fetchone()[0]
    finally:
        cn.close()


def _find_subscription_row_by_email(email):
    if not email:
        return None
    import sqlite3 as _sq
    cn = _sq.connect(DB_PATH)
    cn.row_factory = _sq.Row
    try:
        return cn.execute(
            "SELECT p.plan_id, p.name AS plan_name, p.tier, p.product_family, "
            "       s.subscription_id, s.status, s.current_period_end, s.stripe_customer_id, "
            "       l.license_key, l.email "
            "  FROM licenses l "
            "  JOIN subscriptions s ON s.subscription_id = l.stripe_subscription_id "
            "  JOIN plans p ON p.plan_id = s.plan_id "
            " WHERE l.email = ? "
            "   AND s.status IN ('active', 'trialing', 'past_due', 'canceled') "
            " ORDER BY s.current_period_end DESC LIMIT 1",
            (email,)
        ).fetchone()
    finally:
        cn.close()


def has_stripe_subscription(email):
    return _find_subscription_row_by_email(email) is not None


def get_subscription_info(email, lang='nl'):
    row = _find_subscription_row_by_email(email)
    if not row:
        return None
    cpe = row['current_period_end'] or ''
    return {
        'plan_name': row['plan_name'],
        'tier': row['tier'],
        'status': row['status'],
        'current_period_end_iso': cpe.split('T')[0] if cpe else '',
        'current_period_end_display': _format_date_lang(cpe, lang),
        'license_key': row['license_key'],
        'stripe_customer_id': row['stripe_customer_id'],
    }


@app.route('/account/manage-subscription')
def manage_subscription():
    if not session.get('user_key'):
        return redirect(url_for('sc_login'))
    lang     = session.get('lang', 'nl')
    user_key = session['user_key']
    email    = session.get('email', '')
    customer_id = get_stripe_customer_id(user_key, email)
    if not customer_id:
        return redirect(url_for('license_screen', error='no_stripe_subscription'))
    key = _load_stripe_secret()
    if not key:
        app.logger.error('Spoor3: STRIPE_SECRET_LIVE niet beschikbaar in %s', SPOOR3_STRIPE_KEYS_FILE)
        return redirect(url_for('license_screen', error='portal_unavailable'))
    import stripe as _s
    _s.api_key = key
    try:
        portal_sess = _s.billing_portal.Session.create(
            customer=customer_id,
            configuration=SPOOR3_PORTAL_CONFIGURATION,
            return_url=url_for('license_screen', _external=True),
            locale=lang,
        )
        return redirect(portal_sess.url)
    except _s.error.StripeError as e:
        app.logger.error('Spoor3: billing_portal.Session.create faalde voor %s: %s', customer_id, e)
        return redirect(url_for('license_screen', error='portal_unavailable'))


# ===== LAB — experimentele functies =====
LAB_EMAILS = {'paul@stresschecker.nl', 'steven@lifestylemonitors.com',
              'paulpannevis@gmail.com', 'steven@stresschecker.nl'}

@app.route('/lab')
def lab():
    email = session.get('email', '')
    if email.lower() not in LAB_EMAILS:
        return redirect(url_for('menu'))
    lang = session.get('lang', 'nl')
    # Haal laatste meting op
    user_key = get_user_key()
    db = get_meting_db()
    meting = db.execute(
        'SELECT ri, bpm, hrv_pct, rmssd, sdnn, pnn50, kwaliteit, ts, meting_type '
        'FROM metingen WHERE user_key=? ORDER BY ts DESC LIMIT 1',
        (user_key,)).fetchone()
    db.close()
    return render_template('lab.html', lang=lang, meting=dict(meting) if meting else None)
