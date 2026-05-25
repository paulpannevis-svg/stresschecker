#!/usr/bin/env python3
"""
seed_kk_test.py — KKH-Test-1779642625 fixture voor rapport-verificatie.

Vult sc_pro.db met 6 SMOKE_-cliënten onder de KK-license-pro_key
(SC-KK-44F6-14A3, paulpannevis+kktest@gmail.com), 3 metingen per cliënt
verdeeld over Hannover / Hamburg / München (één meting per kantoor).

Per-cliënt-aggregatie (Bug 2-verificatie) verwacht:
  6 cliënten, 2 V / 3 M / 1 D, ages <30:1 30-45:2 45-60:1 >60:2.

Per-meting-aggregatie verwacht:
  18 metingen, gem. RI ~4.59.

Idempotent: wist bestaande SMOKE_*-cliënten + hun metingen vóór insert.
"""
import os
import sqlite3
import sys
from datetime import datetime, timedelta

PRO_DB = '/opt/stresschecker/data/sc_pro.db'
PRO_KEY = '2f2930462d21870da10942410870c20e'  # sha256(paulpannevis+kktest@gmail.com)[:32]

# Cliënten + birth_year + gender + RI-array per kantoor (Hannover, Hamburg, München)
SMOKES = [
    # name,            byr,  gender,   RI per kantoor [Hannover, Hamburg, München]
    ('SMOKE_Anna',   1988, 'female', [6.6, 1.7, 3.7]),
    ('SMOKE_Bert',   1962, 'male',   [4.5, 7.5, 5.6]),
    ('SMOKE_Carla',  1995, 'female', [4.0, 8.5, 3.2]),
    ('SMOKE_Dirk',   1975, 'male',   [3.5, 5.0, 1.9]),
    ('SMOKE_Eef',    2001, 'divers', [5.0, 4.5, 2.0]),
    ('SMOKE_Frans',  1955, 'male',   [4.0, 7.0, 4.4]),
]
OFFICES = ['Hannover', 'Hamburg', 'München']

BASE_DT = datetime(2026, 5, 14, 18, 41, 0)  # eerste meting Anna in legacy fixture


def ri_to_supporting(ri):
    """RI → (bpm, hrv_pct, rmssd, sdnn, pnn50, beats). Deterministisch (geen random)."""
    rmssd = round(12 + ri * 5.5, 1)
    bpm = int(round(80 - ri * 2.8))
    hrv_pct = int(round(rmssd * 1.45))
    sdnn = round(rmssd * 1.3, 1)
    pnn50 = round(max(0.0, (rmssd - 10) * 0.8), 1)
    beats = int(round(bpm * 1.5))
    return bpm, hrv_pct, rmssd, sdnn, pnn50, beats


def main():
    dry = '--dry-run' in sys.argv
    if not os.path.exists(PRO_DB):
        print(f'FOUT: {PRO_DB} bestaat niet'); sys.exit(1)

    db = sqlite3.connect(PRO_DB)
    cur = db.cursor()

    # Wis oude SMOKE-fixture
    cur.execute("SELECT id FROM clients WHERE pro_key=? AND name LIKE 'SMOKE_%'", (PRO_KEY,))
    old_ids = [r[0] for r in cur.fetchall()]
    if old_ids:
        print(f'Bestaande SMOKE_-cliënten gevonden: {len(old_ids)}')
        if not dry:
            placeholders = ','.join('?' * len(old_ids))
            cur.execute(f'DELETE FROM client_metingen WHERE client_id IN ({placeholders})', old_ids)
            print(f'  - {cur.rowcount} oude metingen verwijderd')
            cur.execute(f'DELETE FROM clients WHERE id IN ({placeholders})', old_ids)
            print(f'  - {cur.rowcount} oude cliënten verwijderd')

    # Insert cliënten + metingen
    inserted_ids = []
    for ci, (name, byr, gender, ris) in enumerate(SMOKES):
        if dry:
            print(f'[dry] cliënt {name} (byr={byr}, gender={gender}); RIs={ris}')
            continue
        cur.execute(
            "INSERT INTO clients (pro_key, name, birth_year, gender, active, created_at) "
            "VALUES (?, ?, ?, ?, 1, datetime('now'))",
            (PRO_KEY, name, byr, gender))
        cid = cur.lastrowid
        inserted_ids.append(cid)
        # 3 metingen, 1 per kantoor, gespreid over 3 dagen vanaf BASE_DT
        for oi, (office, ri) in enumerate(zip(OFFICES, ris)):
            ts_dt = BASE_DT + timedelta(days=ci * 0 + oi)  # 14, 15, 16 mei
            ts_ms = int(ts_dt.timestamp() * 1000)
            bpm, hrv_pct, rmssd, sdnn, pnn50, beats = ri_to_supporting(ri)
            cur.execute("""
                INSERT INTO client_metingen
                (client_id, pro_key, ts, ri, bpm, hrv_pct, rmssd, sdnn, pnn50,
                 beats, duration, sensor_type, kwaliteit, meting_type, pending, office_label)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 90, 'seed', 100, 'basismeting', 0, ?)
            """, (cid, PRO_KEY, ts_ms, ri, bpm, hrv_pct, rmssd, sdnn, pnn50, beats, office))

    if not dry:
        db.commit()
        print(f'\nInsert klaar: {len(inserted_ids)} cliënten, {len(inserted_ids)*3} metingen')
        # Verificatie
        cur.execute("""SELECT COUNT(*), ROUND(AVG(ri),2)
                       FROM client_metingen WHERE pro_key=?""", (PRO_KEY,))
        n, avg = cur.fetchone()
        print(f'  Totaal voor pro_key: {n} metingen, gem. RI {avg}')

    db.close()


if __name__ == '__main__':
    main()
