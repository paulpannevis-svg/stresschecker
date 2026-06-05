"""Cleanup: verwijdert alle testdata uit de drie databases.

KRITISCH: mag NOOIT rows raken die niet expliciet de markers __TEST__,
__TEST2__ of __TEST_CONSUMER__ dragen. Tests draaien tegen productie,
dus de WHERE-clauses zijn de enige garantie dat echte gebruikersdata
intact blijft.

Extra veiligheidslaag: elke DELETE wordt voorafgegaan door een
SELECT-preview. Als die >100 rijen raakt (veilige bovengrens — onze
tests produceren <20 rijen) wordt de DELETE afgebroken met een
CleanupAborted-exception.

Volgorde van DELETE's respecteert foreign keys:
    sc_pro.db:  client_metingen  →  clients     (FK client_id → clients.id)
    sc_measurements.db:  metingen     (geen FK's richting andere tabellen)
    saas_licenses.db:    licenses     (noot: tabelnaam is 'licenses',
                                      niet 'saas_licenses')

Na de DELETE's wordt sqlite_sequence teruggezet naar MAX(id) van de
resterende (echte) rijen, zodat test-runs geen gat in de productie-
ID-reeks slaan. Alleen voor tabellen die AUTOINCREMENT gebruiken
(gedetecteerd via sqlite_master.sql). saas_licenses.db wordt niet
meegenomen — bewust, conform opdrachtspec.

CLI:
    python cleanup.py check     → residue_check, exit 0 schoon / 1 residu
    python cleanup.py cleanup   → voert DELETE's uit, exit 0 OK / 3 abort
"""

import sqlite3
import sys

SC_MEASUREMENTS_DB = "/opt/stresschecker/data/sc_measurements.db"
SC_PRO_DB = "/opt/stresschecker/data/sc_pro.db"
SAAS_LICENSES_DB = "/opt/ic-license-server/data/saas_licenses.db"

TEST_MARKERS = ("__TEST_CONSUMER__", "__TEST__", "__TEST2__")
MAX_ROWS_PER_DELETE = 100

SEQUENCE_RESETS = {
    SC_PRO_DB: ("clients", "client_metingen"),
    SC_MEASUREMENTS_DB: ("metingen",),
}


class CleanupAborted(Exception):
    """Hard stop: cleanup heeft een onveilige situatie gedetecteerd."""


def _is_autoincrement(conn, table):
    cur = conn.cursor()
    cur.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    )
    row = cur.fetchone()
    if not row or not row[0]:
        return False
    return "AUTOINCREMENT" in row[0].upper()


def _reset_sequence(conn, table):
    """Zet sqlite_sequence[table] terug naar MAX(id) van resterende rijen.

    Slaat over als de tabel geen AUTOINCREMENT gebruikt (dan bestaat er
    geen sqlite_sequence-rij). Retourneert (old_seq, new_seq) of None.
    """
    if not _is_autoincrement(conn, table):
        print(f"[cleanup] sequence-reset {table}: overgeslagen "
              f"(geen AUTOINCREMENT)")
        return None
    cur = conn.cursor()
    cur.execute(f"SELECT seq FROM sqlite_sequence WHERE name=?", (table,))
    seq_row = cur.fetchone()
    if seq_row is None:
        print(f"[cleanup] sequence-reset {table}: overgeslagen "
              f"(nog geen sqlite_sequence-rij)")
        return None
    old_seq = seq_row[0]
    cur.execute(
        f"UPDATE sqlite_sequence "
        f"SET seq = (SELECT COALESCE(MAX(id), 0) FROM {table}) "
        f"WHERE name = ?",
        (table,),
    )
    cur.execute(f"SELECT seq FROM sqlite_sequence WHERE name=?", (table,))
    new_seq = cur.fetchone()[0]
    print(f"[cleanup] sequence-reset {table}: {old_seq} → {new_seq}")
    return (old_seq, new_seq)


def _safe_delete(conn, label, where_clause, params):
    """Preview via SELECT → veilige-bovengrens-assertie → DELETE.

    where_clause is één string, bv. "pro_key=?" of
    "user_key IN (?,?,?)". Wordt zowel in de SELECT als de DELETE
    gebruikt, zodat er geen mismatch kan ontstaan.
    """
    table = label.split(".", 1)[1]
    cur = conn.cursor()
    cur.execute(f"SELECT rowid FROM {table} WHERE {where_clause}", params)
    rows = cur.fetchall()
    count = len(rows)
    print(f"[cleanup] {label}: {count} rij(en) match voor DELETE "
          f"(marker-filter: {where_clause})")
    if count > MAX_ROWS_PER_DELETE:
        raise CleanupAborted(
            f"VEILIGHEIDSSTOP {label}: {count} rijen > bovengrens "
            f"{MAX_ROWS_PER_DELETE}. Geen DELETE uitgevoerd."
        )
    if count == 0:
        return 0
    cur.execute(f"DELETE FROM {table} WHERE {where_clause}", params)
    conn.commit()
    return cur.rowcount


def cleanup():
    """Voert alle cleanup-DELETE's uit. Retourneert totaal-count."""
    total = 0
    placeholders = ",".join("?" * len(TEST_MARKERS))
    in_clause = f"user_key IN ({placeholders})"

    # 1. sc_pro.db — eerst client_metingen (FK), dan clients
    with sqlite3.connect(SC_PRO_DB) as pro:
        total += _safe_delete(
            pro, "sc_pro.client_metingen",
            "pro_key=?", ("__TEST__",),
        )
        total += _safe_delete(
            pro, "sc_pro.clients",
            "pro_key=?", ("__TEST__",),
        )
        for table in SEQUENCE_RESETS[SC_PRO_DB]:
            _reset_sequence(pro, table)

    # 2. sc_measurements.db — metingen
    with sqlite3.connect(SC_MEASUREMENTS_DB) as meas:
        total += _safe_delete(
            meas, "sc_measurements.metingen",
            in_clause, TEST_MARKERS,
        )
        for table in SEQUENCE_RESETS[SC_MEASUREMENTS_DB]:
            _reset_sequence(meas, table)

    # 3. saas_licenses.db — licenses (feitelijke tabelnaam)
    #    Geen sequence-reset: bewust overgeslagen, conform spec.
    with sqlite3.connect(SAAS_LICENSES_DB) as lic:
        total += _safe_delete(
            lic, "saas_licenses.licenses",
            in_clause, TEST_MARKERS,
        )

    print(f"[cleanup] totaal verwijderd: {total}")
    return total


def residue_check():
    """Telt testrijen in elke tabel. Retourneert dict."""
    counts = {}
    placeholders = ",".join("?" * len(TEST_MARKERS))

    with sqlite3.connect(SC_PRO_DB) as pro:
        cur = pro.cursor()
        cur.execute("SELECT COUNT(*) FROM client_metingen WHERE pro_key=?",
                    ("__TEST__",))
        counts["sc_pro.client_metingen"] = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM clients WHERE pro_key=?",
                    ("__TEST__",))
        counts["sc_pro.clients"] = cur.fetchone()[0]

    with sqlite3.connect(SC_MEASUREMENTS_DB) as meas:
        cur = meas.cursor()
        cur.execute(
            f"SELECT COUNT(*) FROM metingen WHERE user_key IN ({placeholders})",
            TEST_MARKERS,
        )
        counts["sc_measurements.metingen"] = cur.fetchone()[0]

    with sqlite3.connect(SAAS_LICENSES_DB) as lic:
        cur = lic.cursor()
        cur.execute(
            f"SELECT COUNT(*) FROM licenses WHERE user_key IN ({placeholders})",
            TEST_MARKERS,
        )
        counts["saas_licenses.licenses"] = cur.fetchone()[0]

    return counts


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "cleanup"
    try:
        if mode == "check":
            counts = residue_check()
            residue = sum(counts.values())
            print(f"[residue_check] {counts}")
            print(f"[residue_check] totaal: {residue}")
            sys.exit(1 if residue > 0 else 0)
        elif mode == "cleanup":
            cleanup()
            sys.exit(0)
        else:
            print(f"Onbekende modus '{mode}'. Gebruik 'check' of 'cleanup'.",
                  file=sys.stderr)
            sys.exit(2)
    except CleanupAborted as e:
        print(f"[cleanup] ABORTED: {e}", file=sys.stderr)
        sys.exit(3)
