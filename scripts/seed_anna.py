#!/usr/bin/env python3
"""
seed_anna.py - vult demo-client Anna de Vries (client_id=100) met realistisch verloop.

Verhaal in vier fases over 18 maanden (nov 2024 - apr 2026):
  1. Instap (3 maanden): RI gemiddeld 5.2, lichte variatie
  2. Stress-periode (4 maanden): RI zakt naar gemiddeld 3.5, dippen naar 2.0
  3. Herstel (3 maanden): RI klimt geleidelijk terug naar 5.0
  4. Stabiele fase (8 maanden): RI gemiddeld 5.5, occasionele dippen

Gebruik:
    python3 scripts/seed_anna.py           # uitvoeren
    python3 scripts/seed_anna.py --dry-run # alleen tonen wat zou gebeuren

Idempotent: bestaande metingen voor client_id=100 worden eerst gewist.
"""
import sqlite3
import random
import sys
import shutil
import os
from datetime import datetime, timedelta

DB_PATH = "/opt/stresschecker/data/sc_pro.db"
CLIENT_ID = 100
PRO_KEY = "DEMO"
DRY_RUN = "--dry-run" in sys.argv

NU = datetime(2026, 4, 27, 8, 0, 0)
random.seed(42)

FASES = [
    {
        "naam": "instap",
        "start": NU - timedelta(days=540),
        "eind":  NU - timedelta(days=450),
        "ri_mean": 5.2, "ri_std": 0.6,
        "meas_per_week": 1.5,
    },
    {
        "naam": "stress",
        "start": NU - timedelta(days=450),
        "eind":  NU - timedelta(days=330),
        "ri_mean": 3.5, "ri_std": 0.9,
        "meas_per_week": 2.0,
    },
    {
        "naam": "herstel",
        "start": NU - timedelta(days=330),
        "eind":  NU - timedelta(days=240),
        "ri_mean_start": 3.8,
        "ri_mean_end":   5.0,
        "ri_std": 0.6,
        "meas_per_week": 1.8,
    },
    {
        "naam": "stabiel",
        "start": NU - timedelta(days=240),
        "eind":  NU - timedelta(days=2),
        "ri_mean": 5.5, "ri_std": 0.7,
        "meas_per_week": 1.2,
    },
]


def ri_to_bpm_rmssd(ri):
    bpm_base = 80 - (ri * 2.8)
    bpm = int(round(bpm_base + random.gauss(0, 2.5)))
    bpm = max(55, min(95, bpm))

    rmssd_base = 12 + (ri * 5.5)
    rmssd = round(rmssd_base + random.gauss(0, 3.0), 1)
    rmssd = max(8.0, min(60.0, rmssd))

    hrv_pct = int(round(rmssd * 1.45 + random.gauss(0, 2)))
    hrv_pct = max(15, min(75, hrv_pct))

    sdnn = round(rmssd * 1.3 + random.gauss(0, 2), 1)
    sdnn = max(10.0, min(80.0, sdnn))

    pnn50 = round(max(0, min(50, (rmssd - 10) * 0.8 + random.gauss(0, 2))), 1)
    beats = int(round(bpm * 1.5 + random.gauss(0, 2)))

    return bpm, rmssd, hrv_pct, sdnn, pnn50, beats


def gen_metingen():
    for fase in FASES:
        start = fase["start"]
        eind  = fase["eind"]
        dagen = (eind - start).days
        weken = dagen / 7.0
        n_meas = int(round(weken * fase["meas_per_week"]))

        offsets_dagen = sorted(random.uniform(0, dagen) for _ in range(n_meas))

        for offset in offsets_dagen:
            ts = start + timedelta(days=offset)
            uur = random.choices(
                [7, 8, 9, 12, 17, 18, 21],
                weights=[3, 4, 2, 1, 2, 3, 2]
            )[0]
            minuut = random.randint(0, 59)
            ts = ts.replace(hour=uur, minute=minuut, second=random.randint(0, 59))

            if fase["naam"] == "herstel":
                fractie = offset / dagen
                ri_mean = fase["ri_mean_start"] + (fase["ri_mean_end"] - fase["ri_mean_start"]) * fractie
            else:
                ri_mean = fase["ri_mean"]

            ri = ri_mean + random.gauss(0, fase["ri_std"])
            ri = max(1.0, min(8.5, ri))
            ri = round(ri, 1)

            yield ts, ri, fase["naam"]


def main():
    if not os.path.exists(DB_PATH):
        print(f"FOUT: database niet gevonden op {DB_PATH}")
        sys.exit(1)

    if not DRY_RUN:
        backup_path = DB_PATH + f".bak.before_seed_{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        shutil.copy2(DB_PATH, backup_path)
        print(f"Backup gemaakt: {backup_path}")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT name FROM clients WHERE id=?", (CLIENT_ID,))
    row = cur.fetchone()
    if not row:
        print(f"FOUT: client_id={CLIENT_ID} bestaat niet")
        sys.exit(1)
    print(f"Client gevonden: {row[0]} (id={CLIENT_ID})")

    cur.execute("SELECT COUNT(*) FROM client_metingen WHERE client_id=?", (CLIENT_ID,))
    bestaand = cur.fetchone()[0]
    print(f"Bestaande metingen: {bestaand}")

    metingen = list(gen_metingen())
    print(f"Te genereren: {len(metingen)} metingen")

    fase_telling = {}
    for _, _, fase in metingen:
        fase_telling[fase] = fase_telling.get(fase, 0) + 1
    for fase, n in fase_telling.items():
        print(f"   - {fase}: {n}")

    if DRY_RUN:
        print("\n--- DRY RUN: voorbeeld eerste 5 en laatste 5 metingen ---")
        # Toon 4 voorbeelden uit elke fase
        per_fase = {}
        for m in metingen:
            per_fase.setdefault(m[2], []).append(m)
        showme = []
        for fnaam, lst in per_fase.items():
            # 4 verspreide samples per fase
            n = len(lst)
            indices = [int(i*n/4) for i in range(4)]
            showme.extend([lst[i] for i in indices])
        for ts, ri, fase in showme:
            bpm, rmssd, hrv, sdnn, pnn50, beats = ri_to_bpm_rmssd(ri)
            print(f"  {ts.strftime('%Y-%m-%d %H:%M')} [{fase:8}] RI={ri} BPM={bpm} RMSSD={rmssd} HRV={hrv}%")
        print("\nDry run voltooid. Geen wijzigingen aan database.")
        return

    cur.execute("DELETE FROM client_metingen WHERE client_id=?", (CLIENT_ID,))
    print(f"{cur.rowcount} bestaande metingen verwijderd")

    insert_sql = """
        INSERT INTO client_metingen
        (client_id, pro_key, ts, ri, bpm, hrv_pct, rmssd, sdnn, pnn50,
         beats, duration, sensor_type, kwaliteit, meting_type, pending)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 90, 'demo', 100, 'basismeting', 0)
    """

    for ts, ri, fase in metingen:
        bpm, rmssd, hrv_pct, sdnn, pnn50, beats = ri_to_bpm_rmssd(ri)
        ts_ms = int(ts.timestamp() * 1000)
        cur.execute(insert_sql, (
            CLIENT_ID, PRO_KEY, ts_ms, ri, bpm, hrv_pct, rmssd, sdnn, pnn50, beats
        ))

    conn.commit()
    print(f"{len(metingen)} metingen ingevoegd")

    cur.execute("""
        SELECT COUNT(*),
               MIN(datetime(ts/1000,'unixepoch')),
               MAX(datetime(ts/1000,'unixepoch')),
               ROUND(AVG(ri), 2)
        FROM client_metingen WHERE client_id=?
    """, (CLIENT_ID,))
    n, eerste, laatste, gem_ri = cur.fetchone()
    print(f"\n=== Verificatie ===")
    print(f"  Aantal:      {n}")
    print(f"  Eerste:      {eerste}")
    print(f"  Laatste:     {laatste}")
    print(f"  Gem. RI:     {gem_ri}")

    conn.close()
    print("\nKlaar. Open https://app.stresschecker.com/pro/client/100 om te bekijken.")


if __name__ == "__main__":
    main()
