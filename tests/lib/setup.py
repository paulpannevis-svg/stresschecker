"""Setup-helper: maakt testaccounts en testcliënten aan.

Idempotent: als een testrij uit een eerdere onvolledig opgeruimde run
al bestaat en identiek is aan wat we zouden aanmaken, wordt hij
hergebruikt. Bij CONFLICT (bv. id=999 is al een echte cliënt met
andere pro_key) stopt setup met SetupConflict — nooit overschrijven.

Rationale voor hergebruik-ipv-stop: pre-flight residue_check in
run_all.sh is de primaire barrière tegen stale data. Setup is
daarbinnen de secundaire defensive layer, maar moet standalone
draaien tijdens ontwikkelen zonder te blokkeren op elke hapering.

Aangemaakte objecten:
    saas_licenses.db / licenses:
        license_key='__TEST_LICENSE_CONSUMER__', user_key='__TEST_CONSUMER__', type='consumer'
        license_key='__TEST_LICENSE_PRO__',      user_key='__TEST__',         type='pro'
        license_key='__TEST_LICENSE_PRO2__',     user_key='__TEST2__',        type='pro'
    sc_pro.db / clients (met volledig profiel voor de profiel-gate):
        id=999, pro_key='__TEST__', client_code='__TEST_CLIENT_999__', 1980/male
        id=998, pro_key='__TEST__', client_code='__TEST_CLIENT_998__', 1975/female

Bijwerking: sqlite AUTOINCREMENT bumpt sqlite_sequence.clients naar
999 na eerste setup. Productie-cliënten krijgen daarna id ≥ 1000.
Cosmetisch, niet destructief.

CLI:
    python setup.py    → voert setup uit, exit 0 OK / 4 conflict
"""

import sqlite3
import sys

SC_PRO_DB = "/opt/stresschecker/data/sc_pro.db"
SAAS_LICENSES_DB = "/opt/ic-license-server/data/saas_licenses.db"

LICENSES = [
    {
        "license_key": "__TEST_LICENSE_CONSUMER__",
        "user_key": "__TEST_CONSUMER__",
        "type": "consumer",
    },
    {
        "license_key": "__TEST_LICENSE_PRO__",
        "user_key": "__TEST__",
        "type": "pro",
    },
    {
        "license_key": "__TEST_LICENSE_PRO2__",
        "user_key": "__TEST2__",
        "type": "pro",
    },
]

CLIENTS = [
    # Volledig profiel (birth_year/gender/profile_completed=1) zodat de cliënten
    # de verplicht-profiel-gate in select_client passeren (RMSSD-workstream:
    # leeftijd/geslacht vereist vóór een cliëntmeting). Zonder dit blokkeert de
    # gate de meting en belandt er niets in client_metingen (A2/A4/A5).
    {"id": 999, "pro_key": "__TEST__", "name": "Test Client 999",
     "client_code": "__TEST_CLIENT_999__",
     "birth_year": 1980, "gender": "male", "profile_completed": 1},
    {"id": 998, "pro_key": "__TEST__", "name": "Test Client 998",
     "client_code": "__TEST_CLIENT_998__",
     "birth_year": 1975, "gender": "female", "profile_completed": 1},
]


class SetupConflict(Exception):
    """Hard stop: een doelrij bestaat al met incompatibele inhoud."""


def _setup_license(cur, spec):
    cur.execute(
        "SELECT user_key, type FROM licenses WHERE license_key=?",
        (spec["license_key"],),
    )
    row = cur.fetchone()
    if row is None:
        cur.execute(
            """INSERT INTO licenses
               (license_key, product, type, status, origin, user_key)
               VALUES (?, 'sc', ?, 'activated', 'manual', ?)""",
            (spec["license_key"], spec["type"], spec["user_key"]),
        )
        return "created"
    got_user_key, got_type = row
    if got_user_key == spec["user_key"] and got_type == spec["type"]:
        return "reused"
    raise SetupConflict(
        f"license_key {spec['license_key']} bestaat maar heeft "
        f"user_key={got_user_key!r}, type={got_type!r} "
        f"(verwacht {spec['user_key']!r}, {spec['type']!r})"
    )


def _setup_client(cur, spec):
    cur.execute(
        "SELECT pro_key, client_code FROM clients WHERE id=?",
        (spec["id"],),
    )
    row = cur.fetchone()
    if row is None:
        cur.execute(
            """INSERT INTO clients
               (id, pro_key, name, client_code, birth_year, gender, profile_completed)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (spec["id"], spec["pro_key"], spec["name"], spec["client_code"],
             spec["birth_year"], spec["gender"], spec["profile_completed"]),
        )
        return "created"
    got_pro_key, got_client_code = row
    if got_pro_key == spec["pro_key"] and got_client_code == spec["client_code"]:
        # Hergebruik: ververs het profiel zodat een eventueel stale (incompleet)
        # rij uit een oudere run alsnog de profiel-gate passeert.
        cur.execute(
            "UPDATE clients SET birth_year=?, gender=?, profile_completed=? WHERE id=?",
            (spec["birth_year"], spec["gender"], spec["profile_completed"], spec["id"]),
        )
        return "reused"
    raise SetupConflict(
        f"clients.id={spec['id']} bestaat maar heeft "
        f"pro_key={got_pro_key!r}, client_code={got_client_code!r} "
        f"(verwacht {spec['pro_key']!r}, {spec['client_code']!r}) — "
        f"waarschijnlijk een echte cliënt; NIET overschrijven."
    )


def setup_all():
    """Maakt alle testdata aan. Retourneert dict met per-rij status."""
    summary = {"licenses": {}, "clients": {}}

    with sqlite3.connect(SAAS_LICENSES_DB) as lic:
        cur = lic.cursor()
        for spec in LICENSES:
            status = _setup_license(cur, spec)
            summary["licenses"][spec["license_key"]] = status
            print(f"[setup] license {spec['license_key']}: {status}")
        lic.commit()

    with sqlite3.connect(SC_PRO_DB) as pro:
        cur = pro.cursor()
        for spec in CLIENTS:
            status = _setup_client(cur, spec)
            summary["clients"][spec["id"]] = status
            print(f"[setup] client id={spec['id']}: {status}")
        pro.commit()

    return summary


if __name__ == "__main__":
    try:
        setup_all()
        sys.exit(0)
    except SetupConflict as e:
        print(f"[setup] CONFLICT: {e}", file=sys.stderr)
        sys.exit(4)
