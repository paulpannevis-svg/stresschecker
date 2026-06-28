#!/usr/bin/env python3
# ============================================================================
# Data Retention — FASE 2 (DORMANT)
# ----------------------------------------------------------------------------
# Standalone CLI voor de retention-jobs. BEWUST GEEN `import app` — dat zou de
# ALTER-TABLE-importbijwerkingen en prod-DB-paden van app.py triggeren
# (zie geheugen: "import app.py muteert de DB"). Deze module praat rechtstreeks
# met de drie SQLite-DB's en repliceert de GEZAGHEBBENDE verlop-logica van
# `pro_access_state()` / het dry-run-rapport (NIET kaal `license_expires`).
#
# VEILIGHEID:
#   * Default = DRY-RUN. Er wordt NIETS gewijzigd zonder expliciet `--execute`.
#   * `--hard-delete --execute` weigert bovendien zonder de juridische clearing-
#     vlag  RETENTION_HARD_DELETE_CLEARED=1  in de omgeving (code-niveau-grendel).
#   * Deze module staat in GEEN cron. Activering: docs/retention/ACTIVATION.md.
#
# Gebruik:
#   python3 retention.py --auto-soft-delete            # dry-run rapport
#   python3 retention.py --auto-soft-delete --execute  # archiveer verlopen users
#   python3 retention.py --hard-delete                 # dry-run rapport
#   RETENTION_HARD_DELETE_CLEARED=1 python3 retention.py --hard-delete --execute
#   python3 retention.py --anonymize <user_id>            # dry-run
#   python3 retention.py --anonymize <user_id> --execute  # GDPR erasure
# ============================================================================
import os
import sys
import json
import sqlite3
import hashlib
import argparse
import datetime as dt

# ---- DB-paden (zelfde env-conventie + defaults als app.py) -----------------
SAAS_DB = os.environ.get('SC_DB_PATH', '/opt/ic-license-server/data/saas_licenses.db')
PRO_DB = os.environ.get('SC_PRO_DB', '/opt/stresschecker/data/sc_pro.db')
MEAS_DB = os.environ.get('SC_METING_DB', '/opt/stresschecker/data/sc_measurements.db')

RETENTION_SOFT_DELETE_DAYS = 180  # 6 maanden recovery-/downloadvenster na verlop


def _now():
    return dt.datetime.utcnow()


def _parse(v):
    if not v:
        return None
    try:
        return dt.datetime.fromisoformat(str(v).replace('Z', '').strip())
    except Exception:
        return None


def _connect(path):
    cn = sqlite3.connect(path)
    cn.row_factory = sqlite3.Row
    return cn


def _user_key(email):
    """Zelfde derivatie als app.get_user_key() voor de consumer/pro-sleutel."""
    return hashlib.sha256((email or '').strip().lower().encode()).hexdigest()[:32]


def _lifecycle_log(saas, action, user_id=None, reason=None, who='cron', data_type=None, detail=None):
    """Schrijf één audit-regel in data_lifecycle_log (saas_licenses.db). Faalzacht."""
    try:
        saas.execute(
            "INSERT INTO data_lifecycle_log (action,user_id,reason,who,data_type,detail) "
            "VALUES (?,?,?,?,?,?)", (action, user_id, reason, who, data_type, detail))
        saas.commit()
    except Exception:
        pass


def authoritative_expiry(saas, email, now=None):
    """GEZAGHEBBENDE verlop-bepaling — repliceert pro_access_state()/dry-run.
    Returnt (expired_on: datetime|None, source: str|None).

    Stripe-cohort (er bestaat een sub-rij via licenses.stripe_subscription_id):
      * active/trialing + current_period_end in verleden  -> verlopen (stripe)
      * canceled/unpaid/incomplete_expired + cpe           -> verlopen (stripe)
      * past_due                                            -> GEEN kandidaat (betaling loopt)
      * active/trialing + cpe in toekomst                  -> NIET verlopen
    Niet-Stripe-cohort: license_expires in verleden        -> verlopen (license_expires)
    Bij twijfel/ontbrekende data: None (conservatief NIET verwijderen)."""
    now = now or _now()
    sub = saas.execute(
        "SELECT s.status, s.current_period_end "
        "  FROM licenses l "
        "  JOIN subscriptions s ON s.subscription_id = l.stripe_subscription_id "
        " WHERE l.email = ? COLLATE NOCASE "
        "   AND s.status IN ('active','trialing','past_due','canceled','unpaid','incomplete_expired') "
        " ORDER BY CASE s.status WHEN 'active' THEN 1 WHEN 'trialing' THEN 2 "
        "          WHEN 'past_due' THEN 3 ELSE 4 END ASC, s.current_period_end DESC LIMIT 1",
        (email,)).fetchone()
    if sub is not None:
        status = (sub['status'] or '').lower()
        cpe = _parse(sub['current_period_end'])
        if status in ('canceled', 'unpaid', 'incomplete_expired') and cpe:
            return (cpe, 'stripe_subscription')
        if status in ('active', 'trialing') and cpe and cpe < now:
            return (cpe, 'stripe_subscription')
        # active/trialing-toekomst of past_due -> geen kandidaat
        return (None, None)
    # Niet-Stripe-cohort: alleen DENY bij gezette, verlopen license_expires.
    u = saas.execute("SELECT license_expires FROM users WHERE email=? COLLATE NOCASE",
                     (email,)).fetchone()
    le = _parse(u['license_expires']) if u else None
    if le and le < now:
        return (le, 'license_expires')
    return (None, None)


def auto_soft_delete_expired_users(execute=False):
    """Markeer (OMKEERBAAR) users met verlopen toegang als gearchiveerd:
    archived_at=now, retention_until=now+180d, archived_reason=<bron>.
    Slaat reeds-gearchiveerde users over. Gebruikt authoritative_expiry, NIET
    kaal license_expires. Returnt rapport-dict."""
    now = _now()
    saas = _connect(SAAS_DB)
    candidates = []
    for u in saas.execute("SELECT id,email,archived_at FROM users").fetchall():
        email = (u['email'] or '').strip().lower()
        if not email or u['archived_at']:
            continue
        expired_on, source = authoritative_expiry(saas, email, now)
        if not expired_on:
            continue
        candidates.append({'user_id': u['id'], 'email': email,
                           'expired_on': expired_on.date().isoformat(),
                           'source': source, 'days_expired': (now - expired_on).days})
    archived = []
    if execute:
        until = (now + dt.timedelta(days=RETENTION_SOFT_DELETE_DAYS)).isoformat()
        for c in candidates:
            saas.execute(
                "UPDATE users SET archived_at=COALESCE(archived_at,?), retention_until=?, "
                "archived_reason=? WHERE id=? AND archived_at IS NULL",
                (now.isoformat(), until, c['source'], c['user_id']))
            saas.commit()
            _lifecycle_log(saas, 'archived', c['user_id'], c['source'], 'cron_auto',
                           'user', detail=f'retention_until={until}')
            archived.append(c['user_id'])
        _lifecycle_log(saas, 'auto_soft_delete_cron', None,
                       f'archived {len(archived)} users', 'cron_auto', 'report')
    saas.close()
    return {'mode': 'execute' if execute else 'dry-run', 'candidates': candidates,
            'archived_user_ids': archived, 'count': len(candidates)}


def hard_delete_archived_users(execute=False):
    """DESTRUCTIEF (Fase 2): verwijder users die >180d gearchiveerd zijn (retention_until
    voorbij) ÉN nog steeds verlopen toegang hebben. Cascade: sc_pro.clients (pro_key),
    sc_measurements.metingen (user_key), licenses (email), users-rij. Rapporteert eerst,
    verwijdert daarna alleen het gerapporteerde.

    GRENDEL: zelfs met --execute weigert dit zonder RETENTION_HARD_DELETE_CLEARED=1
    (juridische clearing). Standaard dus dormant."""
    now = _now()
    saas = _connect(SAAS_DB)
    candidates = []
    for u in saas.execute(
            "SELECT id,email,archived_at,retention_until,archived_reason FROM users "
            "WHERE archived_at IS NOT NULL").fetchall():
        ru = _parse(u['retention_until'])
        if not ru or ru >= now:
            continue  # nog binnen 180d-venster
        email = (u['email'] or '').strip().lower()
        # her-verifieer: nog steeds verlopen? (toegang heroverd -> NOOIT verwijderen)
        expired_on, source = authoritative_expiry(saas, email, now)
        if not expired_on:
            continue
        candidates.append({'user_id': u['id'], 'email': email,
                           'retention_until': (u['retention_until'] or '')[:10],
                           'source': source})
    cleared = os.environ.get('RETENTION_HARD_DELETE_CLEARED') == '1'
    deleted = []
    blocked = None
    if execute and not cleared:
        blocked = ('GEWEIGERD: hard-delete vereist juridische clearing. Zet '
                   'RETENTION_HARD_DELETE_CLEARED=1 in de omgeving (zie ACTIVATION.md).')
    elif execute and cleared:
        pro = _connect(PRO_DB)
        meas = _connect(MEAS_DB)
        for c in candidates:
            uk = _user_key(c['email'])
            try:
                pro.execute("DELETE FROM clients WHERE pro_key=?", (uk,)); pro.commit()
                meas.execute("DELETE FROM metingen WHERE user_key=?", (uk,)); meas.commit()
                saas.execute("DELETE FROM licenses WHERE email=? COLLATE NOCASE", (c['email'],))
                saas.execute("DELETE FROM users WHERE id=?", (c['user_id'],))
                saas.commit()
                _lifecycle_log(saas, 'deleted', c['user_id'], c['source'], 'cron_hard_delete',
                               'user', detail=f'hard_delete cascade (pro_key={uk[:8]}…)')
                deleted.append(c['user_id'])
            except Exception as e:
                _lifecycle_log(saas, 'deleted_failed', c['user_id'], str(e), 'cron_hard_delete', 'user')
        pro.close(); meas.close()
    saas.close()
    return {'mode': 'execute' if execute else 'dry-run', 'legal_cleared': cleared,
            'blocked': blocked, 'candidates': candidates,
            'deleted_user_ids': deleted, 'count': len(candidates)}


def anonymize_user_at_erasure(user_id, execute=False):
    """GDPR Recht op vergetelheid via ANONIMISERING (geen hard-delete): PII-velden worden
    onleesbaar gemaakt, maar user_id + timestamps + (pseudonieme) metingen blijven voor de
    audit-trail en anonieme analytics. email/password_hash zijn NOT NULL in het schema → we
    zetten een tombstone i.p.v. NULL. Returnt rapport-dict.

    NB facturen: er is GEEN lokale invoices-tabel; facturen leven in Stripe (10jr wettelijke
    bewaring daar). Anonimisering raakt dus geen lokale factuurdata."""
    saas = _connect(SAAS_DB)
    u = saas.execute("SELECT id,email FROM users WHERE id=?", (user_id,)).fetchone()
    if not u:
        saas.close()
        raise ValueError(f"User {user_id} niet gevonden")
    email = (u['email'] or '').strip().lower()
    uk = _user_key(email)
    tombstone = f'anon-{user_id}@deleted.invalid'
    plan = {
        'user_id': user_id,
        'users.email': f'{email!r} -> {tombstone}',
        'users.password_hash': 'DISABLED',
        'users.display_name/surname': 'NULL',
        'licenses.email (zelfde email)': f'-> {tombstone}',
        'sc_pro.clients (pro_key)': 'name->tombstone, email/phone/notes->NULL, archived',
        'metingen (user_key)': 'BEHOUDEN (pseudoniem, anoniem voor analytics)',
    }
    if not execute:
        saas.close()
        return {'mode': 'dry-run', 'plan': plan}
    # 1. users: PII tombstone/NULL, account uitschakelen
    saas.execute(
        "UPDATE users SET email=?, password_hash='ANONYMIZED_DISABLED', display_name=NULL, "
        "surname=NULL, deleted_at=COALESCE(deleted_at,?) WHERE id=?",
        (tombstone, _now().isoformat(), user_id))
    # 2. licenses van deze email: email-PII tombstone (license_key/billing blijven voor reconciliatie)
    saas.execute("UPDATE licenses SET email=? WHERE email=? COLLATE NOCASE", (tombstone, email))
    saas.commit()
    # 3. cascade: Pro-cliënten (deelnemers) anonimiseren + archiveren
    deelnemers = 0
    try:
        pro = _connect(PRO_DB)
        cur = pro.execute(
            "UPDATE clients SET name='anonymized', surname=NULL, email=NULL, phone=NULL, "
            "notes=NULL, archived_at=COALESCE(archived_at,?) WHERE pro_key=?",
            (_now().isoformat(), uk))
        deelnemers = cur.rowcount
        pro.commit(); pro.close()
    except Exception:
        pass
    # 4. audit-trail
    _lifecycle_log(saas, 'anonymized', user_id, 'gdpr_erasure', 'user_request', 'user',
                   detail=f'tombstone={tombstone}; deelnemers={deelnemers}')
    _lifecycle_log(saas, 'deleted', user_id, 'gdpr_erasure_anonymized', 'user_request', 'user')
    saas.close()
    return {'mode': 'execute', 'anonymized_user_id': user_id, 'deelnemers': deelnemers,
            'tombstone': tombstone}


def _main(argv=None):
    ap = argparse.ArgumentParser(description='StressChecker data-retention CLI (Fase 2, dormant)')
    ap.add_argument('--auto-soft-delete', action='store_true', help='archiveer verlopen users')
    ap.add_argument('--hard-delete', action='store_true', help='verwijder >180d gearchiveerde users')
    ap.add_argument('--anonymize', type=int, metavar='USER_ID', help='GDPR-anonimiseer 1 user')
    ap.add_argument('--execute', action='store_true', help='voer daadwerkelijk uit (default=dry-run)')
    args = ap.parse_args(argv)
    if args.auto_soft_delete:
        out = auto_soft_delete_expired_users(execute=args.execute)
    elif args.hard_delete:
        out = hard_delete_archived_users(execute=args.execute)
    elif args.anonymize is not None:
        out = anonymize_user_at_erasure(args.anonymize, execute=args.execute)
    else:
        ap.print_help()
        return 2
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(_main())
