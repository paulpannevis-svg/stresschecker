#!/usr/bin/env python3
import sqlite3, os, hmac, hashlib
from datetime import datetime
from urllib.parse import quote
import sendgrid
from sendgrid.helpers.mail import Mail
from dotenv import load_dotenv

# Env-bestand configureerbaar: cron draait dit script vanuit /root. Default = prod.
# override=False -> reeds gezette env-vars (staging/systemd) winnen van het bestand.
load_dotenv(os.environ.get('SC_ENV_FILE', '/opt/stresschecker/.env'), override=False)

METING_DB  = os.environ.get('SC_METING_DB', '/opt/stresschecker/data/sc_measurements.db')
LICENSE_DB = os.environ.get('SC_DB_PATH',  '/opt/ic-license-server/data/saas_licenses.db')
SG_KEY     = os.environ['SENDGRID_API_KEY']
SECRET     = os.environ.get('SC_SECRET_KEY', 'change-this-in-production')
BASE_URL   = os.environ.get('WEEKLY_BASE_URL', 'https://www.stresschecker.com').rstrip('/')

# --- Veiligheidsschakelaars -------------------------------------------------
# WEEKLY_TEST_RECIPIENT: indien gezet wordt UITSLUITEND dit adres verwerkt/verzonden.
TEST_RECIPIENT = os.environ.get('WEEKLY_TEST_RECIPIENT', '').strip().lower()
IS_STAGING = os.environ.get('SC_ENV') == 'staging'
# STAGING_MAIL_ALLOW: op staging krijgt ALLEEN een adres op deze lijst echte mail.
MAIL_ALLOW = {e.strip().lower() for e in os.environ.get('STAGING_MAIL_ALLOW', '').split(',') if e.strip()}


# Onbestelbare / test-domeinen (RFC 6761 reserved + interne placeholders).
INVALID_DOMAINS = ('.invalid', '.test', '.example')

# Expliciet uitgesloten test-/intern-accounts die niet door de heuristiek worden
# gevangen (geen 'test'/+alias/ongeldig-domein). Alleen uitsluiten van de mail;
# het account blijft in de DB (aparte opruimtaak).
EXCLUDE_EMAILS = {
    'partnerships@lifestylemonitors.com',  # testaccount Paul (geen echte klant)
}


def user_key(email):
    return hashlib.sha256(email.encode()).hexdigest()[:32]


def test_account_reden(email, display_name='', origins=''):
    """None als het adres een gewone klant lijkt; anders de reden waarom het een
    test-/eval-/onbestelbaar adres is. Conservatief: alleen harde fixture-signalen."""
    if email.strip().lower() in EXCLUDE_EMAILS:
        return 'testaccount (handmatig uitgesloten)'
    local = email.split('@')[0]
    dom = email.split('@')[1] if '@' in email else ''
    if any(dom.endswith(s) for s in INVALID_DOMAINS):
        return 'ongeldig adres'
    if 'test' in local or 'test' in (display_name or '').lower():
        return 'testaccount'
    if '+' in local:
        return 'testaccount (+alias-fixture)'
    if origins and 'evaluation' in origins:
        return 'evaluatie-account'
    return None


def unsub_token(email):
    return hmac.new(SECRET.encode(), email.strip().lower().encode(), hashlib.sha256).hexdigest()


def unsub_url(email):
    return f"{BASE_URL}/afmelden?e={quote(email)}&t={unsub_token(email)}"


def afmeld_regel(email, lang):
    url = unsub_url(email)
    t = {
        "nl": f"Geen wekelijkse mail meer ontvangen? Meld je af: {url}",
        "de": f"Keine woechentliche Mail mehr erhalten? Hier abmelden: {url}",
        "en": f"No longer want the weekly email? Unsubscribe here: {url}",
    }.get(lang, "")
    return "\n\n---\n" + t


def get_naam(email, display_name=''):
    # Voorkeur: voornaam uit display_name (eerste woord). Anders nette terugval op
    # het e-mailadres (oude gedrag) zodat er altijd een aanhef is.
    dn = (display_name or '').strip()
    if dn:
        return dn.split()[0]
    return email.split("@")[0].split(".")[0].split("+")[0].capitalize()


def get_patroon(email):
    db = sqlite3.connect(METING_DB)
    db.row_factory = sqlite3.Row
    now = int(datetime.now().timestamp() * 1000)
    week = 7 * 24 * 3600 * 1000
    rows = db.execute("SELECT ri, ctx_dimensie, ts FROM metingen WHERE user_key=? AND pending=0 ORDER BY ts DESC LIMIT 30", (user_key(email),)).fetchall()
    db.close()
    if len(rows) == 0:
        return {'status': 'nieuw'}
    if len(rows) < 3:
        return {'status': 'starter', 'count': len(rows)}
    recent_ts = [r['ts'] for r in rows if r['ts'] and now - r['ts'] < week]
    if not recent_ts:
        return {'status': 'inactief', 'count': len(rows)}
    recent = [r["ri"] for r in rows if r["ts"] and now - r["ts"] < week and r["ri"]]
    older  = [r["ri"] for r in rows if r["ts"] and week <= now - r["ts"] < 2 * week and r["ri"]]
    ar = round(sum(recent) / len(recent), 1) if recent else None
    ao = round(sum(older) / len(older), 1) if older else None
    dims = [r["ctx_dimensie"] for r in rows if r["ctx_dimensie"]]
    dc = {}
    for d in dims: dc[d] = dc.get(d, 0) + 1
    td = max(dc, key=dc.get) if dc else None
    return {"avg_recent": ar, "avg_older": ao, "top_dim": td, "top_dim_count": dc.get(td, 0) if td else 0, "top_dim_total": len(dims), "count": len(rows)}


def build_nudge(email, lang, status="nieuw", count=0, display_name=''):
    naam = get_naam(email, display_name)
    aanhef = {"nl": f"Beste {naam},", "de": f"Liebe/r {naam},", "en": f"Dear {naam},"}.get(lang, f"Beste {naam},")
    subj = {"nl": "Hoe gaat het met je?", "de": "Wie geht es dir?", "en": "How are you doing?"}.get(lang, "Hoe gaat het met je?")
    tekst = {"nl": "Je hebt deze week nog niet gemeten. Neem 90 seconden voor jezelf en ontdek hoe je lichaam er echt voor staat.", "de": "Diese Woche hast du noch keine Messung durchgefuehrt. Nimm dir 90 Sekunden fuer dich und entdecke, wie es deinem Koerper wirklich geht.", "en": "You have not measured this week yet. Take 90 seconds for yourself and find out how your body is really doing."}.get(lang, "")
    groet = {"nl": "Hartelijke groet,\nTeam Lifestyle Monitors", "de": "Herzliche Gruesse,\nTeam Lifestyle Monitors", "en": "Kind regards,\nTeam Lifestyle Monitors"}.get(lang, "")
    return subj, aanhef + "\n\n" + tekst + "\n\n" + groet + afmeld_regel(email, lang)


def build_email(email, lang, p, display_name=''):
    naam = get_naam(email, display_name)
    aanhef = {"nl": f"Beste {naam},", "de": f"Liebe/r {naam},", "en": f"Dear {naam},"}.get(lang, f"Beste {naam},")
    subj = {"nl": "Je weekoverzicht van StressChecker", "de": "Deine Wochenzusammenfassung von StressChecker", "en": "Your weekly StressChecker summary"}.get(lang, "Je weekoverzicht")
    delen = []
    if p["avg_recent"] and p["avg_older"]:
        if p["avg_recent"] > p["avg_older"]:
            t = {"nl": f"Je RI steeg van {p['avg_older']} naar {p['avg_recent']}. Je lichaam ontspant meer deze week.", "de": f"Dein RI stieg von {p['avg_older']} auf {p['avg_recent']}. Dein Koerper erholt sich besser.", "en": f"Your RI rose from {p['avg_older']} to {p['avg_recent']}. Your body is relaxing more this week."}
        else:
            t = {"nl": f"Je RI daalde van {p['avg_older']} naar {p['avg_recent']}. Je lichaam geeft deze week een signaal — een goed moment om even bij jezelf stil te staan.", "de": f"Dein RI sank von {p['avg_older']} auf {p['avg_recent']}. Dein Koerper gibt diese Woche ein Signal — ein guter Moment, um kurz bei dir selbst innezuhalten.", "en": f"Your RI dropped from {p['avg_older']} to {p['avg_recent']}. Your body is giving a signal this week — a good moment to pause and check in with yourself."}
        delen.append(t.get(lang, ""))
    dn_map = {"lichamelijk": {"nl": "lichamelijks", "de": "Koerperliches", "en": "something physical"}, "mentaal": {"nl": "mentaals", "de": "Mentales", "en": "something mental"}, "emotioneel": {"nl": "emotioneeels", "de": "Emotionales", "en": "something emotional"}, "spiritueel": {"nl": "spiritueels", "de": "Spirituelles", "en": "something deeper"}}
    vragen = {"lichamelijk": {"nl": "Wat zegt je lichaam waaraan je aandacht moet besteden?", "de": "Was sagt dir dein Koerper, dem du Aufmerksamkeit schenken solltest?", "en": "What is your body telling you needs attention?"}, "mentaal": {"nl": "Welke gedachte vraagt om aandacht?", "de": "Welcher Gedanke braucht deine Aufmerksamkeit?", "en": "Which thought needs your attention?"}, "emotioneel": {"nl": "Welk gevoel wacht op aandacht?", "de": "Welches Gefuehl wartet auf Aufmerksamkeit?", "en": "Which feeling is waiting for your attention?"}, "spiritueel": {"nl": "Handel je vanuit wat je echt belangrijk vindt?", "de": "Handelst du aus dem, was dir wirklich wichtig ist?", "en": "Are you acting from what truly matters to you?"}}
    v2_map = {"nl": "Wat spreek je met jezelf af om hieraan iets te gaan doen?", "de": "Was nimmst du dir vor, um daran etwas zu aendern?", "en": "What will you commit to doing about this?"}
    if p["top_dim"] and p["top_dim_count"] >= 2:
        dn = dn_map.get(p["top_dim"], {}).get(lang, p["top_dim"])
        t2 = {"nl": f"Bij {p['top_dim_count']} van je {p['top_dim_total']} ingevulde metingen heb je aangegeven dat er iets {dn} speelt.", "de": f"Bei {p['top_dim_count']} deiner {p['top_dim_total']} ausgefuellten Messungen hast du angegeben, dass {dn} eine Rolle spielt.", "en": f"In {p['top_dim_count']} of your {p['top_dim_total']} completed measurements you indicated {dn} is at play."}
        delen.append(t2.get(lang, ""))
    if p["top_dim"]:
        vraag = vragen.get(p["top_dim"], {}).get(lang, "")
        v2 = v2_map.get(lang, "")
        if vraag: delen.append(vraag)
        if v2: delen.append(v2)
    groet = {"nl": "Hartelijke groet,\nTeam Lifestyle Monitors", "de": "Herzliche Gruesse,\nTeam Lifestyle Monitors", "en": "Kind regards,\nTeam Lifestyle Monitors"}.get(lang, "")
    return subj, aanhef + "\n\n" + "\n\n".join(delen) + "\n\n" + groet + afmeld_regel(email, lang)


def load_recipients():
    """Echte ontvangers uit de license-DB: actieve SC-gebruikers (consument + Pro),
    gededupliceerd op e-mail. Koppeling naar metingen via user_key = sha256(email)[:32]."""
    db = sqlite3.connect(LICENSE_DB)
    db.row_factory = sqlite3.Row
    rows = db.execute(
        """SELECT lower(u.email) AS email, COALESCE(u.language,'nl') AS lang,
                  COALESCE(u.display_name,'') AS display_name,
                  group_concat(DISTINCT l.type) AS types,
                  group_concat(DISTINCT l.origin) AS origins
             FROM users u
             JOIN licenses l ON lower(l.email) = lower(u.email)
            WHERE l.product LIKE 'sc%'
              AND l.status = 'activated'
              AND u.deleted_at IS NULL
              AND u.email != ''
            GROUP BY lower(u.email)""").fetchall()
    try:
        optout = {r[0] for r in db.execute("SELECT lower(email) FROM email_optout WHERE list='weekly'")}
    except sqlite3.OperationalError:
        optout = set()
    # Route B: gekoppelde cliënten categorisch uitsluiten (veilige default tot de
    # per-Pro toestemmingsschakelaar er is). Een cliënt is herkenbaar doordat zijn
    # user_key voorkomt als gekoppelde-sleutel in een van de twee koppeltabellen.
    paired = set()
    for q in ("SELECT consumer_user_key FROM pairing_codes WHERE consumer_user_key IS NOT NULL",
              "SELECT paired_device_id FROM client_pairings WHERE paired_device_id IS NOT NULL"):
        try:
            paired |= {r[0] for r in db.execute(q) if r[0]}
        except sqlite3.OperationalError:
            pass
    db.close()
    return rows, optout, paired


def send_weekly():
    recipients, optout, paired = load_recipients()
    sg = sendgrid.SendGridAPIClient(SG_KEY)
    sent = 0
    for u in recipients:
        email = u["email"]
        lang = u["lang"] or "nl"
        # Testmodus: alleen het opgegeven testadres verwerken.
        if TEST_RECIPIENT and email != TEST_RECIPIENT:
            continue
        # AVG: afgemelde adressen overslaan.
        if email in optout:
            print(f"Overgeslagen (afgemeld): {email}")
            continue
        # Route B: gekoppelde cliënten niet mailen (default uit).
        if user_key(email) in paired:
            print(f"Overgeslagen (gekoppelde cliënt): {email}")
            continue
        # Test-/eval-/onbestelbare adressen overslaan.
        reden = test_account_reden(email, u["display_name"], u["origins"])
        if reden:
            print(f"Overgeslagen ({reden}): {email}")
            continue
        # Staging-vangnet: alleen allow-listed adressen krijgen ECHT mail.
        if IS_STAGING and email not in MAIL_ALLOW:
            print(f"[STAGING-MAIL] zou versturen aan {email} (niet op allow-list) -> niet verzonden")
            continue
        dn = u["display_name"]
        p = get_patroon(email)
        if not p or "status" in p:
            status = p["status"] if p else "nieuw"
            count = p.get("count", 0) if p else 0
            subj, body = build_nudge(email, lang, status, count, display_name=dn)
            label = f"Nudge({status})"
        else:
            subj, body = build_email(email, lang, p, display_name=dn)
            label = "Patroon"
        msg = Mail(from_email="noreply@lifestylemonitors.com", to_emails=email, subject=subj, plain_text_content=body)
        try:
            sg.send(msg)
            sent += 1
            print(f"{label} verzonden: {email}")
        except Exception as e:
            print(f"Fout {email}: {e}")
    print(f"Klaar: {sent} emails verzonden")


if __name__ == "__main__":
    send_weekly()
