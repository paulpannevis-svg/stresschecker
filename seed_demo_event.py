#!/usr/bin/env python3
"""Seed een realistisch demo-event in sc_event.db.

Maakt één event ("Gezondheidsdag Demo", facilitator Frits, licentie TEST-VB-001 =
de VB-account paulpannevis@lifestylemonitors.com) met 15 deelnemers en per deelnemer
één meting. Afgeleide waarden zijn INTERN CONSISTENT met analytics.py:
  - ri  → gekozen binnen de zone-band (analytics.RI_ZONES / zone_for_ri)
  - kwaliteit → per tier (betrouwbaar 95-100 / indicatief 90-94 / onbetrouwbaar 75-89;
                analytics.quality_tier maakt daar de klasse van)
  - quality_band → AUTHENTIEK via analytics.quality_classify(rr) op de gegenereerde RR
  - bpm/rmssd/sdnn/pnn50 → berekend uit de numpy-gegenereerde RR-reeks

Let op het ECHTE schema (de opdracht-SQL noemt niet-bestaande tabellen):
  events(event_id, event_code, opdrachtgever NOT NULL, naam, datum, facilitator_label,
         status, created_at, license_key)
  event_participants(participant_id, event_id, meting_code UNIQUE, birth_year, gender,
                     created_at, name, tracking_code)
  event_metingen(id, event_id, participant_id, meting_code, ts, ri, bpm, hrv_pct, rmssd,
                 sdnn, pnn50, beats, duration, sensor_type, kwaliteit, rr_intervals,
                 timeseries, quality_band, created_at, subjectief_score, work_stress_score)
Er is GEEN display_state-kolom; de weergavestaat wordt bij het lezen afgeleid uit
ri/kwaliteit/quality_band.

Idempotent: weigert een tweede identiek open demo-event aan te maken.
"""
import os, sys, json, math, random, sqlite3
from datetime import datetime

import analytics   # numpy bewust NIET gebruikt: niet geïnstalleerd op prod en de app zelf
                   # heeft geen numpy-dep — pure-Python RR-generatie voorkomt een systeeminstall.

EVENT_DB = os.environ.get('SC_EVENT_DB', '/opt/stresschecker/data/sc_event.db')
LICENSE_KEY = 'TEST-VB-001'          # login-key voor paulpannevis@lifestylemonitors.com
EVENT_NAAM = 'Gezondheidsdag Demo'
FACILITATOR = 'Frits'
OPDRACHTGEVER = 'Demo BV'
EVENT_DATUM = '2026-07-01'
DAY_START = datetime(2026, 7, 1, 9, 0)

RNG_SEED = 20260701
random.seed(RNG_SEED)

# 15 deelnemers: NL namen, m/v-mix, leeftijden 28-62.
PEOPLE = [
    ('Sanne de Vries', 'female', 34), ('Thomas Bakker', 'male', 41),
    ('Fatima El Amrani', 'female', 29), ('Johan Visser', 'male', 57),
    ('Lisa Jansen', 'female', 46), ('Pieter van Dijk', 'male', 62),
    ('Meike Hofman', 'female', 38), ('Ahmed Yilmaz', 'male', 33),
    ('Carla Smit', 'female', 52), ('Bram Mulder', 'male', 28),
    ('Ingrid Vermeer', 'female', 49), ('Ruben Postma', 'male', 44),
    ('Priya Ramdas', 'female', 31), ('Wouter Groen', 'male', 55),
    ('Els Koning', 'female', 60),
]

# Doelverdeling tier (65/25/10) en zone (20/35/25/15/5) over 15 deelnemers.
TIERS = ['betrouwbaar'] * 10 + ['indicatief'] * 4 + ['onbetrouwbaar'] * 1
ZONES = (['veerkrachtig'] * 3 + ['in_balans'] * 5 + ['licht_belast'] * 4
         + ['belast'] * 2 + ['zwaar_belast'] * 1)
random.shuffle(TIERS)
random.shuffle(ZONES)

ZONE_RI_RANGE = {
    'zwaar_belast': (0.5, 1.9), 'belast': (2.0, 3.9), 'licht_belast': (4.0, 5.9),
    'in_balans': (6.0, 7.9), 'veerkrachtig': (8.0, 9.8),
}
# NB: indicatief = LAGER SIGNAAL (kwaliteit 90-94), GEEN onregelmatig ritme — dus óók een
# schone reeks (band 'goed'), alleen een lagere kwaliteit-score. Alleen onbetrouwbaar krijgt
# ritme-artefacten (ectopie) → band 'slecht'.
KWAL_RANGE = {'betrouwbaar': (95, 100), 'indicatief': (90, 94), 'onbetrouwbaar': (75, 89)}
RMSSD_RANGE = {'betrouwbaar': (35, 55), 'indicatief': (25, 42), 'onbetrouwbaar': (20, 45)}
BPM_RANGE = {'betrouwbaar': (58, 78), 'indicatief': (60, 82), 'onbetrouwbaar': (60, 90)}
ECTOPIC_FRAC = {'betrouwbaar': 0.0, 'indicatief': 0.0, 'onbetrouwbaar': 0.24}


def _rand_hex(n):
    return ''.join(random.choice('0123456789ABCDEF') for _ in range(n))


def _rand_track(n):
    return ''.join(random.choice('ABCDEFGHJKLMNPQRSTUVWXYZ0123456789') for _ in range(n))


def _unique(db, table, col, prefix, gen):
    for _ in range(1000):
        code = prefix + gen(6)
        if not db.execute(f"SELECT 1 FROM {table} WHERE {col}=?", (code,)).fetchone():
            return code
    raise RuntimeError(f"kon geen unieke {col} genereren")


def gen_rr(bpm, rmssd_target, ectopic_frac, dur_s=90):
    """Fysiologisch plausibele RR-reeks (ms) van ~dur_s seconden (pure Python).
    Beat-to-beat ruis afgestemd op rmssd_target (RMSSD≈σ√2 → σ=target/√2) + trage
    respiratoire sinus voor SDNN-realisme. Ectopisch = korte slag + compensatoire lange."""
    mean_rr = 60000.0 / bpm
    n = max(25, int(dur_s * 1000 / mean_rr))
    # Beat-to-beat (bepaalt RMSSD): σ_hf zo dat RMSSD ≈ rmssd_target.
    sigma_hf = rmssd_target / math.sqrt(2)
    # Trage variabiliteit (AR(1), hoog-persistent): verhoogt SDNN/SD2 ZONDER de beat-to-beat
    # (RMSSD/SD1), zodat SD1/SD2 < 0.70 blijft — anders triggert quality_classify Laag2 en
    # wordt een verder schone reeks onterecht 'slecht'.
    phi = 0.92
    eps = (rmssd_target * 1.5) * math.sqrt(1 - phi * phi)     # SD2 ruim > SD1
    rr = []
    s = 0.0
    for i in range(n):
        s = phi * s + random.gauss(0, eps)                   # trage component (SDNN)
        rr.append(mean_rr + s + random.gauss(0, sigma_hf))   # + beat-to-beat (RMSSD)
    # Ectopische slagen: vervang een fractie door kort→lang (compensatoire pauze).
    n_ecto = int(round(ectopic_frac * n))
    if n_ecto > 0:
        cands = list(range(2, n - 2))
        for i in random.sample(cands, min(n_ecto, len(cands))):
            rr[i] = mean_rr * random.uniform(0.55, 0.7)      # premature (kort)
            rr[i + 1] = mean_rr * random.uniform(1.25, 1.45)  # compensatoir (lang)
    rr = [max(350.0, min(1600.0, x)) for x in rr]
    return [int(round(x)) for x in rr]


def hrv_metrics(rr):
    n = len(rr)
    mean = sum(rr) / n
    sdnn = math.sqrt(sum((x - mean) ** 2 for x in rr) / n)
    diffs = [rr[i + 1] - rr[i] for i in range(n - 1)]
    rmssd = math.sqrt(sum(d * d for d in diffs) / len(diffs))
    pnn50 = 100.0 * sum(1 for d in diffs if abs(d) > 50) / len(diffs)
    bpm = 60000.0 / mean
    return bpm, rmssd, sdnn, pnn50, n


def hrv_pct(rmssd, age):
    """Plausibele HRV% (RMSSD t.o.v. een leeftijdsnorm). Benadering — de exacte
    Tegegne-norm zit in hrv.js; voor een demo volstaat een leeftijds-schaling."""
    norm = max(18.0, 45.0 - 0.35 * (age - 25))
    return int(round(max(40, min(200, 100.0 * rmssd / norm))))


def main():
    if not os.path.exists(EVENT_DB):
        sys.exit(f"event-DB niet gevonden: {EVENT_DB}")
    db = sqlite3.connect(EVENT_DB)
    db.row_factory = sqlite3.Row

    dup = db.execute("SELECT event_code FROM events WHERE naam=? AND license_key=? "
                     "AND status='open'", (EVENT_NAAM, LICENSE_KEY)).fetchone()
    if dup:
        print(f"Demo-event bestaat al ({dup['event_code']}) — niets gedaan (idempotent).")
        db.close(); return

    event_code = _unique(db, 'events', 'event_code', 'EV-', _rand_hex)
    cur = db.execute(
        "INSERT INTO events (event_code, opdrachtgever, naam, datum, facilitator_label, "
        "status, license_key) VALUES (?,?,?,?,?, 'open', ?)",
        (event_code, OPDRACHTGEVER, EVENT_NAAM, EVENT_DATUM, FACILITATOR, LICENSE_KEY))
    event_id = cur.lastrowid
    print(f"Event: {event_code} (id={event_id}) '{EVENT_NAAM}' · {FACILITATOR} · {LICENSE_KEY}")

    band_count = {}
    for i, (name, gender, age) in enumerate(PEOPLE):
        tier, zone = TIERS[i], ZONES[i]
        birth_year = 2026 - age
        meting_code = _unique(db, 'event_participants', 'meting_code', 'M-', _rand_hex)
        track = _rand_track(6)
        db.execute("INSERT INTO event_participants (event_id, meting_code, birth_year, "
                   "gender, name, tracking_code) VALUES (?,?,?,?,?,?)",
                   (event_id, meting_code, birth_year, gender, name, track))
        participant_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

        ri = round(random.uniform(*ZONE_RI_RANGE[zone]), 1)
        assert analytics.zone_for_ri(ri) == zone, (ri, zone)
        kwaliteit = random.randint(*KWAL_RANGE[tier])
        bpm_t = random.randint(*BPM_RANGE[tier])
        rmssd_t = random.uniform(*RMSSD_RANGE[tier])
        rr = gen_rr(bpm_t, rmssd_t, ECTOPIC_FRAC[tier])
        bpm, rmssd, sdnn, pnn50, beats = hrv_metrics(rr)
        band = (analytics.quality_classify(rr) or {}).get('band')
        hp = hrv_pct(rmssd, age)
        ts = int((DAY_START.timestamp() + i * 300) * 1000)   # 5 min uit elkaar
        # Realistische zelfinschatting (0-10), los gecorreleerd met RI.
        subj = int(min(10, max(0, round(ri + random.uniform(-1.5, 1.5)))))
        ws = int(min(10, max(0, round((10 - ri) * 0.6 + random.uniform(-1.5, 1.5)))))

        db.execute(
            "INSERT INTO event_metingen (event_id, participant_id, meting_code, ts, ri, bpm, "
            "hrv_pct, rmssd, sdnn, pnn50, beats, duration, sensor_type, kwaliteit, rr_intervals, "
            "timeseries, quality_band, subjectief_score, work_stress_score) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (event_id, participant_id, meting_code, ts, ri, int(round(bpm)), hp,
             round(rmssd, 1), round(sdnn, 1), round(pnn50, 1), beats, 90, 'demo',
             kwaliteit, json.dumps(rr), '', band, subj, ws))
        band_count[band] = band_count.get(band, 0) + 1
        print(f"  {name:20} {gender[0]} a{age} | {tier:12} {zone:13} ri={ri} "
              f"kwal={kwaliteit} bpm={round(bpm)} rmssd={round(rmssd,1)} band={band}")

    db.commit()
    print(f"\n15 deelnemers + 15 metingen weggeschreven. quality_band-verdeling: {band_count}")
    print(f"Event-code: {event_code}")
    db.close()


if __name__ == '__main__':
    main()
