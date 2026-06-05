"""
StressChecker rapportage-aggregatie (Sessie B.2).

Pure data-functies. Geen template-rendering, geen PDF, geen output.
Hergebruikbaar voor Krankenkasse-rapporten (overall/per-office/per-region)
en Pro-rapporten (individueel/portefeuille).

DB-paden volgen app.py-conventie (env-overrides toegestaan).
"""
import os
import sqlite3
import datetime

SAAS_DB = os.environ.get('SC_DB_PATH', '/opt/ic-license-server/data/saas_licenses.db')
PRO_DB  = os.environ.get('SC_PRO_DB',  '/opt/stresschecker/data/sc_pro.db')


# ============================================================================
# RI-zone-mapping — single source of truth voor rapport-rendering.
# Drempels overgenomen uit static/js/hrv.js:78-82.
# ============================================================================
RI_ZONES = [
    # key,            min, max(<), nl,                de,                  en
    ('zwaar_belast',  0.0, 2.0,    'Zwaar belast',    'Schwer belastet',   'Heavily strained'),
    ('belast',        2.0, 4.0,    'Belast',          'Belastet',          'Strained'),
    ('licht_belast',  4.0, 6.0,    'Licht belast',    'Leicht belastet',   'Lightly strained'),
    ('in_balans',     6.0, 8.0,    'In balans',       'Im Gleichgewicht',  'In balance'),
    ('veerkrachtig',  8.0, 10.01,  'Veerkrachtig',    'Vital',             'Resilient'),
]
ZONE_KEYS = [z[0] for z in RI_ZONES]


def zone_for_ri(ri):
    """RI (0-10) → zone-key. Out-of-range valt op 'zwaar_belast' resp. 'veerkrachtig'."""
    try:
        r = float(ri)
    except (TypeError, ValueError):
        return 'zwaar_belast'
    if r >= 8.0:
        return 'veerkrachtig'
    if r >= 6.0:
        return 'in_balans'
    if r >= 4.0:
        return 'licht_belast'
    if r >= 2.0:
        return 'belast'
    return 'zwaar_belast'


def zone_label(zone_key, lang='nl'):
    idx = {'nl': 3, 'de': 4, 'en': 5}.get(lang, 3)
    for z in RI_ZONES:
        if z[0] == zone_key:
            return z[idx]
    return zone_key


# Korte ANS-omschrijving per zone, rebrand-consistent (belast-familie).
# NL = je-vorm (consumer), DE = Sie-vorm (consumer-conventie), EN.
ZONE_DESCRIPTIONS = {
    'zwaar_belast': {
        'nl': 'Je autonome zenuwstelsel is zwaar belast.',
        'de': 'Ihr autonomes Nervensystem ist schwer belastet.',
        'en': 'Your autonomic nervous system is heavily strained.',
    },
    'belast': {
        'nl': 'Je autonome zenuwstelsel is belast.',
        'de': 'Ihr autonomes Nervensystem ist belastet.',
        'en': 'Your autonomic nervous system is strained.',
    },
    'licht_belast': {
        'nl': 'Je autonome zenuwstelsel is licht belast.',
        'de': 'Ihr autonomes Nervensystem ist leicht belastet.',
        'en': 'Your autonomic nervous system is lightly strained.',
    },
    'in_balans': {
        'nl': 'Je autonome zenuwstelsel is in balans.',
        'de': 'Ihr autonomes Nervensystem ist im Gleichgewicht.',
        'en': 'Your autonomic nervous system is in balance.',
    },
    'veerkrachtig': {
        'nl': 'Je autonome zenuwstelsel is veerkrachtig en goed hersteld.',
        'de': 'Ihr autonomes Nervensystem ist widerstandsfähig und gut erholt.',
        'en': 'Your autonomic nervous system is resilient and well recovered.',
    },
}


def zone_description(zone_key, lang='nl'):
    """zone-key → korte ANS-omschrijving in de actieve locale (fallback nl)."""
    z = ZONE_DESCRIPTIONS.get(zone_key)
    if not z:
        return ''
    return z.get(lang, z['nl'])


def age_category(birth_year, ref_year=None):
    """birth_year → '<30'|'30-45'|'45-60'|'>60'|'unknown'. ref_year default=huidig jaar."""
    if not birth_year:
        return 'unknown'
    try:
        by = int(birth_year)
    except (TypeError, ValueError):
        return 'unknown'
    if by < 1900 or by > 2030:
        return 'unknown'
    ref = ref_year or datetime.datetime.now().year
    age = ref - by
    if age < 30:  return '<30'
    if age < 45:  return '30-45'
    if age < 60:  return '45-60'
    return '>60'


AGE_CATS = ['<30', '30-45', '45-60', '>60', 'unknown']


def _gender_bucket(g):
    g = (g or '').lower()
    if g == 'male':   return 'M'
    if g == 'female': return 'V'
    if g == 'divers': return 'D'
    return 'unknown'


GENDER_KEYS = ['V', 'M', 'D', 'unknown']


# ============================================================================
# Periode-helpers
# ============================================================================
def period_bounds(kind='kwartaal', ref=None):
    """Returns (start_iso, end_iso) als datetime-strings ('%Y-%m-%d %H:%M:%S').
    kind ∈ {'maand', 'kwartaal', 'jaar', 'alles'}.
    """
    now = ref or datetime.datetime.utcnow()
    if kind == 'alles':
        return ('1970-01-01 00:00:00', now.strftime('%Y-%m-%d %H:%M:%S'))
    if kind == 'jaar':
        start = now - datetime.timedelta(days=365)
    elif kind == 'maand':
        start = now - datetime.timedelta(days=31)
    else:  # kwartaal (default)
        start = now - datetime.timedelta(days=92)
    return (start.strftime('%Y-%m-%d %H:%M:%S'),
            now.strftime('%Y-%m-%d %H:%M:%S'))


def period_bounds_ms(period_start, period_end):
    """Convert iso strings → ms-timestamps (zoals client_metingen.ts gebruikt)."""
    def _to_ms(s):
        try:
            dt = datetime.datetime.strptime(s, '%Y-%m-%d %H:%M:%S')
        except (TypeError, ValueError):
            dt = datetime.datetime.strptime(s.split('.')[0], '%Y-%m-%dT%H:%M:%S')
        return int(dt.timestamp() * 1000)
    return (_to_ms(period_start), _to_ms(period_end))


# ============================================================================
# Aggregatie
# ============================================================================
def _empty_aggregate():
    return {
        'total_metingen': 0,
        'gender_distribution': {k: 0 for k in GENDER_KEYS},
        'age_categories':      {k: 0 for k in AGE_CATS},
        'ri_average': None,
        'zone_distribution':   {k: 0 for k in ZONE_KEYS},
        # Per-klant verdelingen — tellen unieke cliënten, niet metingen.
        # Voor klant-georiënteerde rapporten (KK-overall + Portfolio).
        'unique_clients': 0,
        'gender_distribution_client': {k: 0 for k in GENDER_KEYS},
        'age_categories_client':      {k: 0 for k in AGE_CATS},
        # Zone-per-klant gebruikt de MODALE zone over al hun metingen
        # (bij gelijkspel: best-of-RI-avg, tie-break op zone_order).
        'zone_distribution_client':   {k: 0 for k in ZONE_KEYS},
    }


def _fetch_metingen(pro_key, period_start_ms, period_end_ms, filter=None):
    """Haal metingen + cliënt-attributen op binnen periode + filter.
    Returns list van dicts {ri, gender, birth_year, office_label, ts, client_id}.
    """
    pro_db = sqlite3.connect(PRO_DB)
    pro_db.row_factory = sqlite3.Row
    where = ["cm.pro_key=?", "cm.ts BETWEEN ? AND ?"]
    params = [pro_key, period_start_ms, period_end_ms]
    if filter:
        if 'office_label' in filter and filter['office_label']:
            where.append("cm.office_label=?")
            params.append(filter['office_label'])
        if 'office_labels' in filter and filter['office_labels']:
            placeholders = ','.join('?' * len(filter['office_labels']))
            where.append(f"cm.office_label IN ({placeholders})")
            params.extend(filter['office_labels'])
        if 'client_id' in filter and filter['client_id']:
            where.append("cm.client_id=?")
            params.append(int(filter['client_id']))
    sql = f"""
        SELECT cm.id, cm.client_id, cm.ri, cm.ts, cm.office_label,
               c.gender, c.birth_year, c.name AS client_name, c.surname AS client_surname
        FROM client_metingen cm
        LEFT JOIN clients c ON c.id = cm.client_id
        WHERE {' AND '.join(where)}
        ORDER BY cm.ts ASC
    """
    rows = pro_db.execute(sql, params).fetchall()
    pro_db.close()
    return [dict(r) for r in rows]


def _aggregate_rows(rows):
    """Bereken aggregatie-dict voor een lijst meting-rows.

    Levert zowel meting-gebaseerde tellingen (total_metingen, zone_distribution etc.)
    als klant-gebaseerde tellingen (unique_clients, *_distribution_client). Voor
    klant-tellingen geldt: één rij per uniek client_id (NULL → één 'onbekende klant'-
    bucket per pro_key). Zone-per-klant gebruikt de MODALE zone over al hun
    metingen — zo blijft het rapport robuust voor outliers en uitschieters.
    """
    out = _empty_aggregate()
    if not rows:
        return out
    out['total_metingen'] = len(rows)
    ri_sum = 0.0
    ri_count = 0
    # Per-klant accumulator: client_id → {gender, birth_year, zone_counts: {zone:n}}
    per_client = {}
    for r in rows:
        # Gender
        out['gender_distribution'][_gender_bucket(r.get('gender'))] += 1
        # Age category
        out['age_categories'][age_category(r.get('birth_year'))] += 1
        # Zone
        out['zone_distribution'][zone_for_ri(r.get('ri'))] += 1
        # RI gemiddelde
        try:
            ri_sum += float(r['ri'])
            ri_count += 1
        except (TypeError, ValueError, KeyError):
            pass
        # Per-klant index — None client_id → één bucket
        cid = r.get('client_id')
        if cid not in per_client:
            per_client[cid] = {
                'gender': r.get('gender'),
                'birth_year': r.get('birth_year'),
                'zone_counts': {k: 0 for k in ZONE_KEYS},
            }
        per_client[cid]['zone_counts'][zone_for_ri(r.get('ri'))] += 1
    out['ri_average'] = round(ri_sum / ri_count, 2) if ri_count else None

    # Klant-aggregatie afronden
    out['unique_clients'] = len(per_client)
    for cid, info in per_client.items():
        out['gender_distribution_client'][_gender_bucket(info['gender'])] += 1
        out['age_categories_client'][age_category(info['birth_year'])] += 1
        # Modale zone — bij gelijkspel valt de eerste in ZONE_KEYS-volgorde (van zwaar→vital).
        modal_zone = max(ZONE_KEYS, key=lambda z: info['zone_counts'][z])
        out['zone_distribution_client'][modal_zone] += 1
    return out


def _office_region_map(license_code):
    """Lookup office_name → region voor één KK-licentie. Inactive offices ook meenemen
    omdat historische metingen kunnen verwijzen naar een inmiddels gedeactiveerd kantoor."""
    db = sqlite3.connect(SAAS_DB)
    db.row_factory = sqlite3.Row
    rows = db.execute(
        "SELECT office_name, region, active FROM krankenkasse_offices WHERE license_code=?",
        (license_code,)).fetchall()
    db.close()
    return {r['office_name']: dict(r) for r in rows}


def aggregate_period(license_code, pro_key, period_start, period_end,
                     group_by=None, filter=None):
    """Centrale aggregatie. group_by ∈ {None, 'office_label', 'region', 'client_id'}.

    Returns dict met overall counts + optional 'groups' list als group_by gezet.
    """
    start_ms, end_ms = period_bounds_ms(period_start, period_end)
    rows = _fetch_metingen(pro_key, start_ms, end_ms, filter)
    overall = _aggregate_rows(rows)

    if not group_by:
        return overall

    # Group-by — laad region-map één keer voor zowel office_label als region
    region_map = _office_region_map(license_code) if group_by in ('office_label', 'region') else {}
    groups = {}
    if group_by == 'office_label':
        for r in rows:
            key = r.get('office_label') or '(geen kantoor)'
            groups.setdefault(key, []).append(r)
    elif group_by == 'region':
        for r in rows:
            office = r.get('office_label') or ''
            region = (region_map.get(office, {}).get('region') or '(geen regio)')
            groups.setdefault(region, []).append(r)
    elif group_by == 'client_id':
        for r in rows:
            groups.setdefault(r.get('client_id'), []).append(r)
    else:
        raise ValueError(f'Unknown group_by: {group_by}')

    group_list = []
    for key, grows in groups.items():
        agg = _aggregate_rows(grows)
        item = {'key': key, **agg}
        if group_by == 'office_label':
            item['region'] = (region_map.get(key, {}).get('region') or '')
            item['active'] = bool(region_map.get(key, {}).get('active'))
        elif group_by == 'client_id' and grows:
            item['client_name'] = grows[0].get('client_name', '')
            item['client_surname'] = grows[0].get('client_surname') or ''
            item['birth_year'] = grows[0].get('birth_year')
            item['gender'] = grows[0].get('gender')
        group_list.append(item)

    # Sorteer: per region+naam voor office_label, naam voor region, total desc voor client_id
    if group_by == 'office_label':
        group_list.sort(key=lambda g: ((g.get('region') or '~').lower(), str(g['key']).lower()))
    elif group_by == 'region':
        group_list.sort(key=lambda g: str(g['key']).lower())
    elif group_by == 'client_id':
        group_list.sort(key=lambda g: (-(g.get('total_metingen') or 0), (g.get('client_name') or '').lower()))

    overall['groups'] = group_list
    return overall


def time_series(pro_key, client_id, period_start, period_end):
    """Tijdreeks voor één cliënt — list van metingen ordered ASC."""
    start_ms, end_ms = period_bounds_ms(period_start, period_end)
    rows = _fetch_metingen(pro_key, start_ms, end_ms, filter={'client_id': client_id})
    out = []
    for r in rows:
        ts = r.get('ts') or 0
        try:
            dt = datetime.datetime.fromtimestamp(ts / 1000.0)
            date_str = dt.strftime('%Y-%m-%d %H:%M')
        except (OSError, ValueError):
            date_str = '?'
        ri = r.get('ri')
        out.append({
            'ts': ts,
            'date': date_str,
            'ri': round(float(ri), 1) if ri is not None else None,
            'zone': zone_for_ri(ri),
            'office_label': r.get('office_label') or '',
        })
    return out


def client_meta(pro_key, client_id):
    """Cliënt-info voor pro_client.html header."""
    db = sqlite3.connect(PRO_DB)
    db.row_factory = sqlite3.Row
    row = db.execute(
        "SELECT id, name, surname, birth_year, gender, client_code "
        "FROM clients WHERE id=? AND pro_key=?",
        (client_id, pro_key)).fetchone()
    db.close()
    return dict(row) if row else None
