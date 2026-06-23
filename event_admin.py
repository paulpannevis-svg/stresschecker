#!/usr/bin/env python3
"""Event-modus — admin-CLI (Fase 1: datamodel + beheer).

Beheert een APART event-datamodel in een eigen DB-bestand (sc_event.db), los van
sc_pro.db / saas_licenses.db. Een vitaliteitsbureau zet een meetdag (event) op en
genereert code-only deelnemers (meting-codes). De identiteit van de deelnemer blijft
bij het bureau: hier slaan we GEEN naam/e-mail op, alleen een code + leeftijd/geslacht
(dat laatste is nodig voor de HRV%-normcorrectie bij de meting in Fase 2).

Veiligheid:
  - DB-pad uit env SC_EVENT_DB, default de STAGING-locatie.
  - Harde weigering als het pad naar de LIVE-data wijst (spiegelt de staging-asserties
    in app.py). Schrijven naar productie vereist later een expliciet pad + --prod-flag
    (nog niet geïmplementeerd in Fase 1).
  - Schema is idempotent (CREATE TABLE IF NOT EXISTS): herhaald draaien is veilig.

Gebruik:
    python3 event_admin.py init
    python3 event_admin.py create-event --opdrachtgever "Krav Maga Global" \
        --naam "Vitaliteitsdag HQ" --datum 2026-07-01 --facilitator "Bureau Vitaal"
    python3 event_admin.py add-participant --event EV-XXXXXX --birth-year 1985 --gender female
    python3 event_admin.py add-participant --event EV-XXXXXX --count 3
    python3 event_admin.py list
    python3 event_admin.py list --event EV-XXXXXX
"""
import argparse
import os
import secrets
import sqlite3
import sys

DEFAULT_DB = '/opt/stresschecker-staging/data/sc_event.db'
# Paden die NOOIT door deze CLI geschreven mogen worden (live productie-data).
_LIVE_PREFIXES = ('/opt/stresschecker/data/', '/opt/ic-license-server/data/')
_GENDERS = ('male', 'female', 'other')
_MAX_GEN_TRIES = 100


def _db_path():
    path = os.environ.get('SC_EVENT_DB', DEFAULT_DB)
    if any(path.startswith(p) for p in _LIVE_PREFIXES):
        sys.exit(f'WEIGERT live-pad voor event-DB: {path!r}\n'
                 'Event-modus draait in Fase 1 uitsluitend op staging '
                 '(SC_EVENT_DB → /opt/stresschecker-staging/data/sc_event.db).')
    return path


def _connect():
    path = _db_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cn = sqlite3.connect(path)
    cn.row_factory = sqlite3.Row
    cn.execute('PRAGMA foreign_keys = ON')
    return cn, path


def _ensure_schema(cn):
    """Idempotent schema-aanmaak. Veilig om elke run te draaien."""
    cn.executescript("""
        CREATE TABLE IF NOT EXISTS events (
            event_id          INTEGER PRIMARY KEY AUTOINCREMENT,
            event_code        TEXT UNIQUE NOT NULL,
            opdrachtgever     TEXT NOT NULL,
            naam              TEXT,
            datum             TEXT,
            facilitator_label TEXT,
            status            TEXT NOT NULL DEFAULT 'open',
            created_at        TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS event_participants (
            participant_id    INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id          INTEGER NOT NULL REFERENCES events(event_id),
            meting_code       TEXT UNIQUE NOT NULL,
            birth_year        INTEGER,
            gender            TEXT,
            created_at        TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_ep_event ON event_participants(event_id);

        CREATE TABLE IF NOT EXISTS event_metingen (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id       INTEGER NOT NULL REFERENCES events(event_id),
            participant_id INTEGER NOT NULL REFERENCES event_participants(participant_id),
            meting_code    TEXT NOT NULL,
            ts             INTEGER NOT NULL,
            ri             REAL,
            bpm            INTEGER,
            hrv_pct        INTEGER,
            rmssd          REAL,
            sdnn           REAL,
            pnn50          REAL,
            beats          INTEGER,
            duration       INTEGER DEFAULT 90,
            sensor_type    TEXT DEFAULT 'unknown',
            kwaliteit      INTEGER,
            rr_intervals   TEXT,
            timeseries     TEXT,
            quality_band   TEXT,
            created_at     TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_em_event ON event_metingen(event_id);
        CREATE INDEX IF NOT EXISTS idx_em_participant ON event_metingen(participant_id);
    """)
    # Additieve kolommen (idempotent), alleen hier in sc_event.db.
    try:
        cn.execute('ALTER TABLE event_participants ADD COLUMN name TEXT')
    except sqlite3.OperationalError:
        pass
    # Ontspanningscijfer (zelfde semantiek als basismeting subjectief_score, 0-10).
    try:
        cn.execute('ALTER TABLE event_metingen ADD COLUMN subjectief_score INTEGER')
    except sqlite3.OperationalError:
        pass
    cn.commit()


def _gen_unique(cn, table, column, prefix):
    for _ in range(_MAX_GEN_TRIES):
        code = prefix + secrets.token_hex(3).upper()
        if not cn.execute(
            f'SELECT 1 FROM {table} WHERE {column}=?', (code,)
        ).fetchone():
            return code
    sys.exit(f'Kon na {_MAX_GEN_TRIES} pogingen geen unieke code genereren.')


def _resolve_event(cn, ref):
    """Accepteert event_code (EV-...) of numeriek event_id."""
    row = cn.execute(
        'SELECT * FROM events WHERE event_code=? OR event_id=?',
        (ref, ref if str(ref).isdigit() else -1)
    ).fetchone()
    if not row:
        sys.exit(f'Event niet gevonden: {ref!r}')
    return row


def cmd_init(args):
    cn, path = _connect()
    _ensure_schema(cn)
    cn.close()
    print(f'Schema OK in {path}')


def cmd_create_event(args):
    cn, _ = _connect()
    _ensure_schema(cn)
    code = _gen_unique(cn, 'events', 'event_code', 'EV-')
    cur = cn.execute(
        'INSERT INTO events (event_code, opdrachtgever, naam, datum, facilitator_label) '
        'VALUES (?, ?, ?, ?, ?)',
        (code, args.opdrachtgever, args.naam, args.datum, args.facilitator)
    )
    cn.commit()
    print(f'event_code   : {code}')
    print(f'event_id     : {cur.lastrowid}')
    print(f'opdrachtgever: {args.opdrachtgever}')
    print(f'naam         : {args.naam or ""}')
    print(f'datum        : {args.datum or ""}')
    print(f'facilitator  : {args.facilitator or ""}')
    cn.close()


def cmd_add_participant(args):
    if args.count < 1:
        sys.exit('--count moet >= 1 zijn.')
    if args.gender and args.gender not in _GENDERS:
        sys.exit(f'--gender moet een van {_GENDERS} zijn.')
    cn, _ = _connect()
    _ensure_schema(cn)
    ev = _resolve_event(cn, args.event)
    _nm = (args.name or '').strip()[:120] or None
    codes = []
    for _ in range(args.count):
        mc = _gen_unique(cn, 'event_participants', 'meting_code', 'M-')
        cn.execute(
            'INSERT INTO event_participants (event_id, meting_code, birth_year, gender, name) '
            'VALUES (?, ?, ?, ?, ?)',
            (ev['event_id'], mc, args.birth_year, args.gender, _nm)
        )
        codes.append(mc)
    cn.commit()
    print(f'event_code : {ev["event_code"]}  ({ev["opdrachtgever"]})')
    print(f'toegevoegd : {len(codes)} deelnemer(s)')
    for mc in codes:
        print(f'  meting_code: {mc}  '
              f'naam={_nm or "-"} birth_year={args.birth_year or "-"} gender={args.gender or "-"}')
    cn.close()


def cmd_list(args):
    cn, path = _connect()
    _ensure_schema(cn)
    if args.event:
        ev = _resolve_event(cn, args.event)
        print(f'Event {ev["event_code"]} — {ev["opdrachtgever"]} '
              f'({ev["naam"] or ""}, {ev["datum"] or ""}) status={ev["status"]}')
        parts = cn.execute(
            'SELECT meting_code, birth_year, gender, name, created_at '
            'FROM event_participants WHERE event_id=? ORDER BY participant_id',
            (ev['event_id'],)
        ).fetchall()
        print(f'Deelnemers: {len(parts)}')
        for p in parts:
            print(f'  {p["meting_code"]}  naam={p["name"] or "-"} '
                  f'birth_year={p["birth_year"] or "-"} '
                  f'gender={p["gender"] or "-"}  {p["created_at"]}')
    else:
        evs = cn.execute(
            'SELECT e.event_code, e.opdrachtgever, e.naam, e.datum, e.status, '
            '  (SELECT COUNT(*) FROM event_participants p WHERE p.event_id=e.event_id) AS n '
            'FROM events e ORDER BY e.event_id'
        ).fetchall()
        print(f'DB: {path}')
        print(f'Events: {len(evs)}')
        for e in evs:
            print(f'  {e["event_code"]}  {e["opdrachtgever"]} '
                  f'({e["naam"] or ""}, {e["datum"] or ""})  '
                  f'status={e["status"]} deelnemers={e["n"]}')
    cn.close()


def cmd_wipe(args):
    """Wis alle deelnemers + metingen van één meetdag (de event-hull blijft).
    Vereist --confirm met de EXACTE event_code; anders dry-run (wist niets)."""
    cn, _ = _connect()
    _ensure_schema(cn)
    ev = _resolve_event(cn, args.event)
    np = cn.execute('SELECT COUNT(*) c FROM event_participants WHERE event_id=?',
                    (ev['event_id'],)).fetchone()['c']
    nm = cn.execute('SELECT COUNT(*) c FROM event_metingen WHERE event_id=?',
                    (ev['event_id'],)).fetchone()['c']
    print(f'Event {ev["event_code"]} — {ev["opdrachtgever"]}: '
          f'{np} deelnemer(s), {nm} meting(en).')
    if (args.confirm or '').strip().upper() != str(ev['event_code']).upper():
        print('DRY-RUN: niets gewist. Geef --confirm <event_code> (exact) om te wissen.')
        cn.close()
        return
    cn.execute('DELETE FROM event_metingen WHERE event_id=?', (ev['event_id'],))
    cn.execute('DELETE FROM event_participants WHERE event_id=?', (ev['event_id'],))
    cn.commit()
    cn.close()
    print(f'GEWIST: {np} deelnemer(s) + {nm} meting(en) van {ev["event_code"]}. '
          'Meetdag (event) behouden.')


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)

    sub.add_parser('init', help='Maak/valideer het event-schema (idempotent).') \
        .set_defaults(func=cmd_init)

    p_ce = sub.add_parser('create-event', help='Maak een nieuwe meetdag aan.')
    p_ce.add_argument('--opdrachtgever', required=True)
    p_ce.add_argument('--naam', default=None)
    p_ce.add_argument('--datum', default=None, help='Meetdag, bv. 2026-07-01')
    p_ce.add_argument('--facilitator', default=None, help='Label van het uitvoerende bureau')
    p_ce.set_defaults(func=cmd_create_event)

    p_ap = sub.add_parser('add-participant', help='Voeg code-only deelnemer(s) toe.')
    p_ap.add_argument('--event', required=True, help='event_code (EV-...) of event_id')
    p_ap.add_argument('--name', default=None, help='Deelnemernaam (alleen in sc_event.db)')
    p_ap.add_argument('--birth-year', type=int, default=None, dest='birth_year')
    p_ap.add_argument('--gender', default=None, help='male | female | other')
    p_ap.add_argument('--count', type=int, default=1)
    p_ap.set_defaults(func=cmd_add_participant)

    p_ls = sub.add_parser('list', help='Toon events of de deelnemers van één event.')
    p_ls.add_argument('--event', default=None, help='event_code (EV-...) of event_id')
    p_ls.set_defaults(func=cmd_list)

    p_wp = sub.add_parser('wipe', help='Wis deelnemers + metingen van één meetdag (vereist --confirm).')
    p_wp.add_argument('--event', required=True, help='event_code (EV-...) of event_id')
    p_wp.add_argument('--confirm', default=None, help='Exacte event_code om de wis te bevestigen')
    p_wp.set_defaults(func=cmd_wipe)

    args = ap.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
