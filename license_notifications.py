#!/usr/bin/env python3
"""
Lifestyle Monitors - Licentie waarschuwings- en opruimscript
Dagelijks uitvoeren via cronjob om 08:00
"""
import os, sqlite3, datetime, sendgrid, logging
from sendgrid.helpers.mail import Mail
from dotenv import load_dotenv

# Expliciet pad: cron draait dit script vanuit /root, niet vanuit /opt/stresschecker.
load_dotenv('/opt/stresschecker/.env')

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger(__name__)

SENDGRID_KEY = os.environ['SENDGRID_API_KEY']
FROM_EMAIL    = 'Lifestyle Monitors <noreply@lifestylemonitors.com>'
DB_PATH       = '/opt/ic-license-server/data/saas_licenses.db'
METING_DB     = '/opt/stresschecker/data/sc_measurements.db'
PRO_DB        = '/opt/stresschecker/data/sc_pro.db'

def send_email(to_email, subject, body):
    try:
        sg = sendgrid.SendGridAPIClient(SENDGRID_KEY)
        msg = Mail(from_email=FROM_EMAIL, to_emails=to_email, subject=subject, plain_text_content=body)
        sg.send(msg)
        log.info(f'Email verstuurd naar {to_email}: {subject}')
        return True
    except Exception as e:
        log.error(f'Email fout naar {to_email}: {e}')
        return False

def get_lang(user):
    """Taalkeuze voor mails: opgeslagen voorkeur (users.language) > e-mail-domein
    (.de) als heuristiek voor oude accounts zonder voorkeur > nl als default.

    De oude versie keek uitsluitend naar het e-maildomein ('.de' → de, anders nl)
    en kon daardoor NOOIT 'en' teruggeven: EN-abonnees kregen NL-vervalmails, en
    een DE-keuzer op een niet-.de adres (bv. @gmail.com) ook. We gebruiken nu de
    expliciet opgeslagen taal en houden de domein-heuristiek enkel als fallback."""
    stored = (user.get('language') or '').strip().lower()
    if stored in ('nl', 'de', 'en'):
        return stored
    email = (user.get('email') or '').lower()
    domain = email.rsplit('@', 1)[-1] if '@' in email else ''
    if domain.endswith('.de'):
        return 'de'
    return 'nl'

def warning_email_30(name, email, exp_date, lang):
    first_name = (name or email).split()[0]
    exp_str = exp_date[:10]
    if lang == 'de':
        subject = 'Ihr StressChecker Abonnement läuft in 30 Tagen ab'
        body = f"""Guten Tag {first_name},

Ihr StressChecker Abonnement läuft am {exp_str} ab.

Bitte verlängern Sie Ihr Abonnement rechtzeitig unter:
https://www.lifestylemonitors.com/my-account/my-subscription/

WICHTIG: Nach Ablauf Ihres Abonnements werden Ihre persönlichen Daten und Messungen nach 30 Tagen dauerhaft aus unseren Systemen gelöscht. Dies kann nicht rückgängig gemacht werden.

Mit freundlichen Grüßen,
Lifestyle Monitors"""
    elif lang == 'en':
        subject = 'Your StressChecker subscription expires in 30 days'
        body = f"""Dear {first_name},

Your StressChecker subscription expires on {exp_str}.

Please renew your subscription at:
https://www.lifestylemonitors.com/my-account/my-subscription/

IMPORTANT: After your subscription expires, your personal data and measurements will be permanently deleted from our systems after 30 days. This cannot be undone.

Kind regards,
Lifestyle Monitors"""
    else:
        subject = 'Je StressChecker abonnement verloopt over 30 dagen'
        body = f"""Beste {first_name},

Je StressChecker abonnement verloopt op {exp_str}.

Verleng je abonnement tijdig via:
https://www.lifestylemonitors.com/my-account/my-subscription/

BELANGRIJK: Na het verlopen van je abonnement worden je persoonlijke gegevens en metingen na 30 dagen definitief uit onze systemen verwijderd. Dit kan niet ongedaan worden gemaakt.

Met vriendelijke groet,
Lifestyle Monitors"""
    return subject, body

def warning_email_7(name, email, exp_date, lang):
    first_name = (name or email).split()[0]
    exp_str = exp_date[:10]
    del_date = (datetime.datetime.fromisoformat(exp_date[:10]) + datetime.timedelta(days=30)).strftime('%Y-%m-%d')
    if lang == 'de':
        subject = '⚠️ Noch 7 Tage – Ihr StressChecker Abonnement läuft ab'
        body = f"""Guten Tag {first_name},

Ihr StressChecker Abonnement läuft in 7 Tagen ab ({exp_str}).

Verlängern Sie jetzt unter:
https://www.lifestylemonitors.com/my-account/my-subscription/

⚠️ LETZTE WARNUNG: Wenn Sie Ihr Abonnement nicht verlängern, werden Ihre Daten am {del_date} dauerhaft gelöscht.

Mit freundlichen Grüßen,
Lifestyle Monitors"""
    elif lang == 'en':
        subject = '⚠️ 7 days left – Your StressChecker subscription expires'
        body = f"""Dear {first_name},

Your StressChecker subscription expires in 7 days ({exp_str}).

Renew now at:
https://www.lifestylemonitors.com/my-account/my-subscription/

⚠️ FINAL WARNING: If you do not renew, your data will be permanently deleted on {del_date}.

Kind regards,
Lifestyle Monitors"""
    else:
        subject = '⚠️ Nog 7 dagen – Je StressChecker abonnement verloopt'
        body = f"""Beste {first_name},

Je StressChecker abonnement verloopt over 7 dagen ({exp_str}).

Verleng nu via:
https://www.lifestylemonitors.com/my-account/my-subscription/

⚠️ LAATSTE WAARSCHUWING: Als je niet verlengt, worden je gegevens op {del_date} definitief verwijderd.

Met vriendelijke groet,
Lifestyle Monitors"""
    return subject, body

def deletion_email(name, email, lang):
    first_name = (name or email).split()[0]
    if lang == 'de':
        subject = 'Ihre StressChecker Daten wurden gelöscht'
        body = f"""Guten Tag {first_name},

Ihr StressChecker Abonnement ist abgelaufen und Ihre persönlichen Daten wurden gemäß unserer Datenschutzrichtlinie dauerhaft aus unseren Systemen gelöscht.

Wenn Sie StressChecker erneut nutzen möchten, können Sie jederzeit ein neues Abonnement abschließen:
https://www.lifestylemonitors.com

Mit freundlichen Grüßen,
Lifestyle Monitors"""
    elif lang == 'en':
        subject = 'Your StressChecker data has been deleted'
        body = f"""Dear {first_name},

Your StressChecker subscription has expired and your personal data has been permanently deleted from our systems in accordance with our privacy policy.

If you wish to use StressChecker again, you can subscribe at any time:
https://www.lifestylemonitors.com

Kind regards,
Lifestyle Monitors"""
    else:
        subject = 'Je StressChecker gegevens zijn verwijderd'
        body = f"""Beste {first_name},

Je StressChecker abonnement is verlopen en je persoonlijke gegevens zijn conform ons privacybeleid definitief uit onze systemen verwijderd.

Als je StressChecker opnieuw wilt gebruiken, kun je altijd een nieuw abonnement afsluiten:
https://www.lifestylemonitors.com

Met vriendelijke groet,
Lifestyle Monitors"""
    return subject, body

def delete_user_data(email):
    """Verwijder alle meetdata en anonimiseer gebruikersprofiel"""
    try:
        # Metingen verwijderen
        mdb = sqlite3.connect(METING_DB)
        mdb.execute("DELETE FROM metingen WHERE user_key IN (SELECT license_code FROM users WHERE email=?)", (email,))
        mdb.commit()
        mdb.close()
        log.info(f'Metingen verwijderd voor {email}')
    except Exception as e:
        log.error(f'Fout bij verwijderen metingen: {e}')

    try:
        # Pro client data verwijderen
        pdb = sqlite3.connect(PRO_DB)
        pdb.execute("DELETE FROM client_metingen WHERE pro_key IN (SELECT license_code FROM users WHERE email=?)", (email,))
        pdb.commit()
        pdb.close()
        log.info(f'Pro data verwijderd voor {email}')
    except Exception as e:
        log.error(f'Fout bij verwijderen pro data: {e}')

    try:
        # Gebruiker anonimiseren
        db = sqlite3.connect(DB_PATH)
        db.execute("""UPDATE users SET
            display_name='[verwijderd]',
            email='deleted_' || id || '@deleted.invalid',
            password_hash='',
            deleted_at=datetime('now')
            WHERE email=?""", (email,))
        db.commit()
        db.close()
        log.info(f'Gebruiker geanonimiseerd: {email}')
    except Exception as e:
        log.error(f'Fout bij anonimiseren: {e}')

def main():
    now = datetime.datetime.utcnow()
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row

    # Check of deleted_at kolom bestaat, anders toevoegen
    try:
        db.execute("ALTER TABLE users ADD COLUMN deleted_at TEXT")
        db.commit()
        log.info('Kolom deleted_at toegevoegd')
    except:
        pass

    # Check of warned_30 en warned_7 kolommen bestaan
    try:
        db.execute("ALTER TABLE users ADD COLUMN warned_30 TEXT")
        db.commit()
    except:
        pass
    try:
        db.execute("ALTER TABLE users ADD COLUMN warned_7 TEXT")
        db.commit()
    except:
        pass

    users = db.execute("""
        SELECT email, display_name, language, license_expires, warned_30, warned_7
        FROM users
        WHERE license_expires IS NOT NULL
        AND email NOT LIKE 'deleted_%'
        AND deleted_at IS NULL
    """).fetchall()

    db.close()

    for user in users:
        email = user['email']
        name = user['display_name'] or email
        exp = user['license_expires']
        lang = get_lang(dict(user))

        try:
            exp_date = datetime.datetime.fromisoformat(exp[:19])
        except:
            continue

        days_left = (exp_date - now).days
        days_since = (now - exp_date).days

        # 30 dagen waarschuwing
        if 28 <= days_left <= 31 and not user['warned_30']:
            subject, body = warning_email_30(name, email, exp, lang)
            if send_email(email, subject, body):
                db2 = sqlite3.connect(DB_PATH)
                db2.execute("UPDATE users SET warned_30=? WHERE email=?", (now.isoformat(), email))
                db2.commit()
                db2.close()

        # 7 dagen waarschuwing
        elif 5 <= days_left <= 8 and not user['warned_7']:
            subject, body = warning_email_7(name, email, exp, lang)
            if send_email(email, subject, body):
                db2 = sqlite3.connect(DB_PATH)
                db2.execute("UPDATE users SET warned_7=? WHERE email=?", (now.isoformat(), email))
                db2.commit()
                db2.close()

        # 30 dagen na verlopen → data verwijderen
        elif days_since >= 30:
            log.info(f'Data verwijderen voor {email} - verlopen {days_since} dagen geleden')
            delete_user_data(email)
            subject, body = deletion_email(name, email, lang)
            send_email(email, subject, body)

    log.info('Script voltooid')

if __name__ == '__main__':
    main()
