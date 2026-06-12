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
import json
import math

SAAS_DB = os.environ.get('SC_DB_PATH', '/opt/ic-license-server/data/saas_licenses.db')
PRO_DB  = os.environ.get('SC_PRO_DB',  '/opt/stresschecker/data/sc_pro.db')


# ============================================================================
# RUWE GATE-MATEN-LOGGING (alleen opslag — GEEN gate-evaluatie/markering op prod).
# gate_metrics() berekent op de VOLLEDIGE RR exact dezelfde maten als de staging-gate
# (static/js/hrv.js::rrIrregularity / staging analytics.rr_irregular: sd1/sd2/rmssd) +
# pNN50. Per nieuwe meting weggeschreven in kolom gate_metrics (JSON), zodat dagelijkse
# prod-data de drempel-herijking kan voeden i.p.v. de bestaande slice-15-kolommen
# (rmssd/pnn50), die op de afgekapte reeks staan en de full-RR-gate niet representeren.
# ============================================================================
def gate_metrics(rr):
    """Full-RR gate-maten {sd1sd2, rmssd_full, pnn50_full} of None bij < 20 RR-intervallen.
    rr: list van RR (ms) of JSON-string. Identieke full-RR-berekening als de onregelmatigheid-gate."""
    if isinstance(rr, str):
        try:
            rr = json.loads(rr)
        except (ValueError, TypeError):
            return None
    if not rr or len(rr) < 20:
        return None
    try:
        rr = [float(x) for x in rr if x is not None]
    except (ValueError, TypeError):
        return None
    n = len(rr)
    if n < 20:
        return None
    mean = sum(rr) / n
    sdnn = math.sqrt(sum((x - mean) ** 2 for x in rr) / n)
    diffs = [rr[i + 1] - rr[i] for i in range(n - 1)]
    nd = len(diffs)
    rmssd = math.sqrt(sum(d * d for d in diffs) / nd)
    md = sum(diffs) / nd
    sdsd = math.sqrt(sum((d - md) ** 2 for d in diffs) / nd)
    sd1 = math.sqrt(0.5) * sdsd
    sd2 = math.sqrt(max(2 * sdnn * sdnn - 0.5 * sdsd * sdsd, 0))
    ratio = sd1 / sd2 if sd2 > 0 else 99
    pnn50 = 100.0 * sum(1 for d in diffs if abs(d) > 50) / nd
    return {'sd1sd2': round(ratio, 4), 'rmssd_full': round(rmssd, 2), 'pnn50_full': round(pnn50, 2)}


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


# Meting-type: opgeslagen code (metingen.meting_type) → label per locale.
MEASUREMENT_TYPE_LABELS = {
    'basismeting':    {'nl': 'Basismeting',    'de': 'Basismessung',      'en': 'Baseline'},
    'situatiemeting': {'nl': 'Situatiemeting', 'de': 'Situationsmessung', 'en': 'Situational'},
    'biofeedback':    {'nl': 'Biofeedback',    'de': 'Biofeedback',       'en': 'Biofeedback'},
}


def meting_type_label(code, lang='nl'):
    """metingen.meting_type-code → label in actieve locale. Onbekende code verbatim."""
    if not code:
        return '-'
    m = MEASUREMENT_TYPE_LABELS.get(str(code).strip().lower())
    if not m:
        return str(code)
    return m.get(lang, m['nl'])


# Situatie-label is een VRIJ TEKSTVELD met snelkeuze-chips. De chips vullen
# locale-tekst in op het moment van meten, dus een meting onder NL slaat "Na sport"
# op, onder DE "Nach Sport". Best-effort: herken de bekende chip-frases in elke
# taalvariant en toon ze in de actieve locale; alles wat geen chip is (echte vrije
# tekst zoals "test", "10 min ademoefening") blijft verbatim staan.
#
# SINGLE SOURCE OF TRUTH voor de chip-frases. Deze lijst MOET synchroon blijven met
# de snelkeuze-knoppen in templates/sensor_en_meten.html en templates/measure.html
# (setBiofeedLabel-chips). Voeg een nieuwe/gewijzigde chip hier óók toe, anders
# drift de vertaling weg.
SITUATION_CHIP_LABELS = [
    {'nl': 'Voor activiteit', 'de': 'Vor Aktivität',  'en': 'Before activity'},
    {'nl': 'Na activiteit',   'de': 'Nach Aktivität', 'en': 'After activity'},
    {'nl': 'Ochtend',         'de': 'Morgens',        'en': 'Morning'},
    {'nl': 'Avond',           'de': 'Abends',         'en': 'Evening'},
    {'nl': 'Na sport',        'de': 'Nach Sport',     'en': 'After sport'},
    {'nl': 'Na meditatie',    'de': 'Nach Meditation', 'en': 'After meditation'},
]

# Opgebouwde lookup: genormaliseerde frase (elke taal) → chip-rij.
_SITUATION_CHIP_INDEX = {
    chip[l].strip().lower(): chip
    for chip in SITUATION_CHIP_LABELS
    for l in ('nl', 'de', 'en')
}


def situation_label_translate(notes, lang='nl'):
    """Best-effort: herken een bekende chip-frase (in welke taal dan ook) en geef
    die terug in de actieve locale. Vrije tekst / onbekend → ongewijzigd terug."""
    if not notes:
        return notes
    chip = _SITUATION_CHIP_INDEX.get(str(notes).strip().lower())
    if not chip:
        return notes
    return chip.get(lang, chip['nl'])


# ============================================================================
# Baseline-referentielijn — canonieke berekening (single source of truth).
#
# Baseline = gemiddelde RI van de laatste BASELINE_MIN_DAYS kalenderdagen met een
# basismeting, waarbij per dag uitsluitend de LAATSTE basismeting van die dag telt.
# Alleen meting_type 'basismeting' telt mee (biofeedback/situatiemeting nooit —
# zelfde filterles als de grafiekfix van 21 april). Pas vanaf >= BASELINE_MIN_DAYS
# zulke meetdagen een waarde; daaronder None (geen lijn).
#
# Eén bron voor: /api/metingen (baseline+delta → /resultaten-stat + /kwadrant),
# de RI-verloop-referentielijnen (consumer + pro) en de Kompas baseline_ri.
# Dagindeling in Europe/Amsterdam (operationele tijdzone), overschrijfbaar.
# NB: vervangt de oude berekening (oudste 7 metingen, geen type-/per-dag-filter).
# ============================================================================
BASELINE_MIN_DAYS = 7
_BASELINE_TZ = 'Europe/Amsterdam'


# ---------------------------------------------------------------------------
# Tweelaags-meetkwaliteit (variant B) — Python-twin van static/js/hrv.js ::
# HRV.qualityClassify. MOET bit-voor-bit hetzelfde oordeel geven als de JS
# (bewaakt door tests/test_irrgate_parity.py). De oude rr_irregular/
# row_is_irregular hierboven blijven als REFERENTIE staan. NB: deze twin is
# (nog) NIET in de aggregaten bedraad — dat is een aparte stap die op echte
# productie-meetreeksen wacht (zie project_quality_aggregation_gate_parity).
# ---------------------------------------------------------------------------
QUAL_W = 21
QUAL_ART_REL = 0.25
QUAL_BAND_GOED = 5
QUAL_BAND_SLECHT = 15
QUAL_L2_SD1SD2 = 0.70
QUAL_L2_RMSSD_MIN = 25


def _jsround(x):
    """Repliceert JS Math.round (half naar +inf); alle inputs hier zijn >= 0."""
    return math.floor(x + 0.5)


def _quality_poincare(rr):
    n = len(rr)
    mean = sum(rr) / n
    ss = sum((x - mean) ** 2 for x in rr)
    sdnn = math.sqrt(ss / n)
    s = 0.0
    md = 0.0
    for i in range(1, n):
        d = rr[i] - rr[i - 1]
        s += d * d
        md += d
    nd = n - 1
    rmssd = math.sqrt(s / nd)
    md /= nd
    sx = 0.0
    for i in range(1, n):
        d2 = (rr[i] - rr[i - 1]) - md
        sx += d2 * d2
    sdsd = math.sqrt(sx / nd)
    sd1 = math.sqrt(0.5) * sdsd
    sd2 = math.sqrt(max(2 * sdnn * sdnn - 0.5 * sdsd * sdsd, 0))
    ratio = (sd1 / sd2) if sd2 > 0 else 99
    return ratio, rmssd


def quality_classify(rr):
    """Variant-B-meetkwaliteit, 1-op-1 met HRV.qualityClassify (hrv.js)."""
    if isinstance(rr, str):
        try:
            rr = json.loads(rr)
        except (ValueError, TypeError):
            return {'band': 'onbepaald', 'reason': 'parse'}
    if not rr or len(rr) < 20:
        return {'band': 'onbepaald', 'reason': 'te kort (<20 RR)'}
    rr = [float(x) for x in rr]
    n = len(rr)
    half = QUAL_W // 2
    # LAAG 1 — puntartefact-detectie
    flag = [False] * n
    for i in range(n):
        lo = max(0, i - half)
        hi = min(n - 1, i + half)
        s = 0.0
        cnt = 0
        for j in range(lo, hi + 1):
            if j != i:
                s += rr[j]
                cnt += 1
        lm = (s / cnt) if cnt > 0 else rr[i]
        flag[i] = abs(rr[i] - lm) > QUAL_ART_REL * lm
    art_count = sum(1 for f in flag if f)
    run_len = [0] * n
    max_run = 0
    k = 0
    while k < n:
        if flag[k]:
            st = k
            while k < n and flag[k]:
                k += 1
            length = k - st
            for p in range(st, k):
                run_len[p] = length
            if length > max_run:
                max_run = length
        else:
            k += 1
    art_pct = 100.0 * art_count / n
    consecutive = max_run >= 3
    # CORRECTIE — run-lengte 1 en 2 lineair interpoleren tussen geldige buren; run>=3 niet
    corr = list(rr)
    for i in range(n):
        if not flag[i] or run_len[i] > 2:
            continue
        left = i - 1
        right = i + 1
        while left >= 0 and flag[left]:
            left -= 1
        while right < n and flag[right]:
            right += 1
        if left >= 0 and right < n:
            corr[i] = rr[left] + (rr[right] - rr[left]) * ((i - left) / (right - left))
        elif left >= 0:
            corr[i] = rr[left]
        elif right < n:
            corr[i] = rr[right]
    # LAAG 2 — Poincaré-vorm op de GECORRIGEERDE RR
    ratio, rmssd = _quality_poincare(corr)
    laag2 = (ratio >= QUAL_L2_SD1SD2 and rmssd >= QUAL_L2_RMSSD_MIN)
    # LABEL
    if art_pct > QUAL_BAND_SLECHT:
        band, reason = 'slecht', 'Laag1 artefact %s%% > 15%%' % (_jsround(art_pct * 10) / 10)
    elif consecutive:
        band, reason = 'slecht', 'aaneengesloten artefacten (run=%d), niet interpoleerbaar' % max_run
    elif laag2:
        band, reason = 'slecht', 'Laag2 SD1/SD2 %s >= 0.70' % (_jsround(ratio * 100) / 100)
    elif art_pct > QUAL_BAND_GOED:
        band, reason = 'redelijk', 'Laag1 artefact %s%% (5-15%%)' % (_jsround(art_pct * 10) / 10)
    else:
        band, reason = 'goed', 'schoon'
    return {
        'band': band, 'reason': reason,
        'artefactPct': _jsround(art_pct * 10) / 10, 'artefactCount': art_count, 'maxRun': max_run,
        'sd1sd2': _jsround(ratio * 1000) / 1000, 'rmssd': _jsround(rmssd * 10) / 10,
        'laag1Slecht': (art_pct > QUAL_BAND_SLECHT or consecutive), 'laag2': laag2,
        'corrected': corr, 'scoreOK': (band in ('goed', 'redelijk')),
    }


def is_slecht_rr(rr):
    """True als variant-B de reeks 'slecht' noemt (raw RR of JSON-string)."""
    return quality_classify(rr).get('band') == 'slecht'


def is_slecht(row):
    """is_slecht op een meting-row (leest 'rr_intervals')."""
    return is_slecht_rr(_g(row, 'rr_intervals'))


def _g(row, key):
    """Veilige veld-toegang voor dict én sqlite3.Row (mist → None)."""
    try:
        return row[key]
    except (KeyError, IndexError):
        return None


def _day_key(ts_ms, tz_name=_BASELINE_TZ):
    """Kalenderdag 'YYYY-MM-DD' voor epoch-milliseconden in tijdzone tz_name."""
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = datetime.timezone.utc
    return datetime.datetime.fromtimestamp(ts_ms / 1000, tz).strftime('%Y-%m-%d')


def baseline_day_values(rows, max_days=BASELINE_MIN_DAYS, tz_name=_BASELINE_TZ):
    """rows: iterable van dict/sqlite3.Row met 'ts' (epoch ms), 'ri', 'meting_type'.
    Geeft de RI's van de laatste `max_days` kalenderdagen met een basismeting,
    één per dag (de laatste meting van die dag), chronologisch (oud→nieuw)."""
    per_day = {}  # day_key -> (ts, ri) van de laatste basismeting die dag
    for r in rows:
        if str(_g(r, 'meting_type') or '').lower() != 'basismeting':
            continue
        # Kwaliteits-gate (besluit 3): alleen VERTROUWDE metingen (kwaliteit >= 85) in de
        # baseline/trend, anders vervuilt één aritmie-/lage-kwaliteit-meting de baseline.
        # Ontbrekende kwaliteit (legacy/niet meegegeven) telt as-is mee (besluit 5: legacy=vertrouwd).
        _kw = _g(r, 'kwaliteit')
        if _kw is not None:
            try:
                if float(_kw) < 85:
                    continue
            except (TypeError, ValueError):
                pass
        ri, ts = _g(r, 'ri'), _g(r, 'ts')
        if ri is None or ts is None:
            continue
        ts = int(ts)
        day = _day_key(ts, tz_name)
        prev = per_day.get(day)
        if prev is None or ts >= prev[0]:
            per_day[day] = (ts, float(ri))
    last_days = sorted(per_day)[-max_days:]
    return [per_day[d][1] for d in last_days]


def compute_baseline(rows, min_days=BASELINE_MIN_DAYS, tz_name=_BASELINE_TZ):
    """Canonieke baseline-waarde (RI, 1 decimaal) of None bij < min_days meetdagen."""
    vals = baseline_day_values(rows, max_days=min_days, tz_name=tz_name)
    if len(vals) < min_days:
        return None
    return round(sum(vals) / len(vals), 1)


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
        # Kwaliteits-gate (besluit C/D/E optie i): lage-kwaliteit-metingen tellen NIET mee in
        # zone-distributie / RI-gemiddelde / modale klant-zone, maar worden WEL geteld + gerapporteerd.
        'reliable_metingen': 0,
        'low_quality_excluded': 0,
        'clients_no_reliable': 0,
        'reliable_clients': 0,
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
        SELECT cm.id, cm.client_id, cm.ri, cm.ts, cm.office_label, cm.kwaliteit,
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
    low_q = 0
    # Per-klant accumulator: client_id → {gender, birth_year, zone_counts, reliable}
    per_client = {}
    for r in rows:
        # Gender + leeftijd = demografie van wie gemeten is → ALLE metingen (kwaliteit-onafhankelijk).
        out['gender_distribution'][_gender_bucket(r.get('gender'))] += 1
        out['age_categories'][age_category(r.get('birth_year'))] += 1
        # Per-klant index (demografie) — None client_id → één bucket
        cid = r.get('client_id')
        if cid not in per_client:
            per_client[cid] = {
                'gender': r.get('gender'),
                'birth_year': r.get('birth_year'),
                'zone_counts': {k: 0 for k in ZONE_KEYS},
                'reliable': 0,
            }
        # Kwaliteits-gate: zone/RI-oordeel alleen op VERTROUWDE metingen (kwaliteit >= 85).
        # Ontbrekende kwaliteit telt as-is mee (besluit 5: legacy = vertrouwd).
        _kw = r.get('kwaliteit')
        try:
            _low = (_kw is not None and float(_kw) < 85)
        except (TypeError, ValueError):
            _low = False
        if _low:
            low_q += 1
            continue
        # Zone + RI-gemiddelde (alleen betrouwbaar)
        out['zone_distribution'][zone_for_ri(r.get('ri'))] += 1
        try:
            ri_sum += float(r['ri'])
            ri_count += 1
        except (TypeError, ValueError, KeyError):
            pass
        per_client[cid]['zone_counts'][zone_for_ri(r.get('ri'))] += 1
        per_client[cid]['reliable'] += 1
    out['low_quality_excluded'] = low_q
    out['reliable_metingen'] = len(rows) - low_q
    out['ri_average'] = round(ri_sum / ri_count, 2) if ri_count else None

    # Klant-aggregatie afronden
    out['unique_clients'] = len(per_client)
    clients_no_reliable = 0
    for cid, info in per_client.items():
        out['gender_distribution_client'][_gender_bucket(info['gender'])] += 1
        out['age_categories_client'][age_category(info['birth_year'])] += 1
        if info['reliable'] == 0:
            # Geen enkele betrouwbare meting → niet in zone-per-klant classificeren.
            clients_no_reliable += 1
            continue
        # Modale zone over de BETROUWBARE metingen — bij gelijkspel eerste in ZONE_KEYS-volgorde.
        modal_zone = max(ZONE_KEYS, key=lambda z: info['zone_counts'][z])
        out['zone_distribution_client'][modal_zone] += 1
    out['clients_no_reliable'] = clients_no_reliable
    out['reliable_clients'] = out['unique_clients'] - clients_no_reliable
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
