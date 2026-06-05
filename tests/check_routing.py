"""Categorie A — data-routing regressietests.

Verifieert dat metingen in de juiste database belanden afhankelijk van
het account-type en de actieve sessie-context.

Zes tests:
    A1 — Consumer-meting → sc_measurements.db onder __TEST_CONSUMER__
    A2 — Pro-cliëntmeting (client 999) → sc_pro.client_metingen
    A3 — Pro eigen meting (client_id=0) → sc_measurements.db
    A4 — REGRESSIE 21-04: A2 en A3 in dezelfde sessie zonder reset
    A5 — Pro wisselcliënt 999 → 998, geen kruisbestuiving
    A6 — Data-isolatie: __TEST2__ ziet meting van __TEST__ niet

Elke test:
    (a) rowcount-baseline in beide DB's
    (b) actie uitvoeren via lib.api_client
    (c) rowcount-delta en inhoud verifiëren
    (d) PASS/FAIL printen en retourneren

Harde timeout: 30 seconden per test (requests-timeout in api_client).
"""

import sqlite3
import sys
import time

sys.path.insert(0, "/opt/stresschecker/tests")
from lib.api_client import ApiClient

SC_MEAS_DB = "/opt/stresschecker/data/sc_measurements.db"
SC_PRO_DB = "/opt/stresschecker/data/sc_pro.db"


def count(db, sql, params=()):
    con = sqlite3.connect(db)
    try:
        return con.execute(sql, params).fetchone()[0]
    finally:
        con.close()


def _meas_count(user_key=None):
    if user_key:
        return count(SC_MEAS_DB, "SELECT COUNT(*) FROM metingen WHERE user_key=?", (user_key,))
    return count(SC_MEAS_DB, "SELECT COUNT(*) FROM metingen")


def _pro_count(client_id=None, pro_key=None):
    if client_id is not None and pro_key is not None:
        return count(
            SC_PRO_DB,
            "SELECT COUNT(*) FROM client_metingen WHERE client_id=? AND pro_key=?",
            (client_id, pro_key),
        )
    if pro_key is not None:
        return count(
            SC_PRO_DB,
            "SELECT COUNT(*) FROM client_metingen WHERE pro_key=?",
            (pro_key,),
        )
    return count(SC_PRO_DB, "SELECT COUNT(*) FROM client_metingen")


def _report(name, ok, reason):
    tag = "PASS" if ok else "FAIL"
    print(f"[{tag}] {name}: {reason}")
    return ok


def a1_consumer_meting():
    name = "A1 consumer-meting → sc_measurements.db"
    meas_before_me = _meas_count("__TEST_CONSUMER__")
    pro_before = _pro_count(pro_key="__TEST__")

    c = ApiClient()
    c.login_consumer("__TEST_CONSUMER__")
    r = c.submit_measurement(client_id=0, ri=5.0, bpm=65, hrv=50)
    if r.status_code != 200:
        return _report(name, False, f"POST status={r.status_code} body={r.text[:200]}")

    meas_after_me = _meas_count("__TEST_CONSUMER__")
    pro_after = _pro_count(pro_key="__TEST__")

    if meas_after_me - meas_before_me != 1:
        return _report(name, False,
                       f"sc_measurements.metingen delta={meas_after_me-meas_before_me}, verwacht 1")
    if pro_after != pro_before:
        return _report(name, False,
                       f"sc_pro delta={pro_after-pro_before}, verwacht 0")
    return _report(name, True,
                   "meting landde in sc_measurements.metingen onder __TEST_CONSUMER__")


def a2_pro_client_meting():
    name = "A2 pro-cliëntmeting client 999 → sc_pro.client_metingen"
    pro_before_999 = _pro_count(client_id=999, pro_key="__TEST__")
    meas_before = _meas_count("__TEST__")

    c = ApiClient()
    c.login_pro("__TEST__")
    r = c.select_client(999)
    if r.status_code not in (200, 302):
        return _report(name, False, f"select_client status={r.status_code}")
    r = c.submit_measurement()  # geen client_id in body, gebruikt measuring_for_client
    if r.status_code != 200:
        return _report(name, False, f"POST status={r.status_code} body={r.text[:200]}")

    pro_after_999 = _pro_count(client_id=999, pro_key="__TEST__")
    meas_after = _meas_count("__TEST__")

    if pro_after_999 - pro_before_999 != 1:
        return _report(name, False,
                       f"sc_pro(client=999) delta={pro_after_999-pro_before_999}, verwacht 1")
    if meas_after != meas_before:
        return _report(name, False,
                       f"sc_measurements(__TEST__) delta={meas_after-meas_before}, verwacht 0")
    return _report(name, True,
                   "meting landde in sc_pro.client_metingen onder client 999/__TEST__")


def a3_pro_eigen_meting():
    name = "A3 pro eigen meting (client_id=0) → sc_measurements.db"
    meas_before = _meas_count("__TEST__")
    pro_before = _pro_count(pro_key="__TEST__")

    c = ApiClient()
    c.login_pro("__TEST__")
    r = c.submit_measurement(client_id=0)
    if r.status_code != 200:
        return _report(name, False, f"POST status={r.status_code} body={r.text[:200]}")

    meas_after = _meas_count("__TEST__")
    pro_after = _pro_count(pro_key="__TEST__")

    if meas_after - meas_before != 1:
        return _report(name, False,
                       f"sc_measurements(__TEST__) delta={meas_after-meas_before}, verwacht 1")
    if pro_after != pro_before:
        return _report(name, False,
                       f"sc_pro delta={pro_after-pro_before}, verwacht 0")
    return _report(name, True,
                   "eigen meting landde in sc_measurements.metingen onder __TEST__")


def a4_regressie_21_april():
    name = "A4 REGRESSIE-21-04: A2→A3 in één sessie zonder reset"
    meas_before = _meas_count("__TEST__")
    pro_before_999 = _pro_count(client_id=999, pro_key="__TEST__")

    c = ApiClient()
    c.login_pro("__TEST__")

    # Stap 1 (A2-flow): cliëntmeting voor 999
    c.select_client(999)
    r1 = c.submit_measurement()
    if r1.status_code != 200:
        return _report(name, False, f"stap-1 POST status={r1.status_code} body={r1.text[:200]}")

    # Stap 2 (A3-flow): ZELFDE sessie, eigen meting met client_id=0
    r2 = c.submit_measurement(client_id=0)
    if r2.status_code != 200:
        return _report(name, False, f"stap-2 POST status={r2.status_code} body={r2.text[:200]}")

    pro_after_999 = _pro_count(client_id=999, pro_key="__TEST__")
    meas_after = _meas_count("__TEST__")

    if pro_after_999 - pro_before_999 != 1:
        return _report(name, False,
                       f"sc_pro(999) delta={pro_after_999-pro_before_999}, verwacht 1 (A2-deel)")
    if meas_after - meas_before != 1:
        return _report(
            name, False,
            f"sc_measurements(__TEST__) delta={meas_after-meas_before}, verwacht 1 "
            f"— A3 is MISROUTED. REGRESSIE van 21-04 ACTIEF!",
        )
    return _report(
        name, True,
        "A2 landde in sc_pro, A3 landde in sc_measurements — regressie-bug vrij",
    )


def a5_pro_wisselclient():
    name = "A5 pro wisselcliënt 999→998, geen kruisbestuiving"
    p999_before = _pro_count(client_id=999, pro_key="__TEST__")
    p998_before = _pro_count(client_id=998, pro_key="__TEST__")

    c = ApiClient()
    c.login_pro("__TEST__")

    c.select_client(999)
    r1 = c.submit_measurement()
    if r1.status_code != 200:
        return _report(name, False, f"999 POST status={r1.status_code}")
    c.select_client(998)
    r2 = c.submit_measurement()
    if r2.status_code != 200:
        return _report(name, False, f"998 POST status={r2.status_code}")

    p999_after = _pro_count(client_id=999, pro_key="__TEST__")
    p998_after = _pro_count(client_id=998, pro_key="__TEST__")

    if p999_after - p999_before != 1:
        return _report(name, False,
                       f"sc_pro(999) delta={p999_after-p999_before}, verwacht 1")
    if p998_after - p998_before != 1:
        return _report(name, False,
                       f"sc_pro(998) delta={p998_after-p998_before}, verwacht 1 "
                       f"— eerste cliënt bleef mogelijk sticky")
    return _report(name, True, "999 +1 en 998 +1, geen kruisbestuiving")


def a6_data_isolatie():
    name = "A6 data-isolatie: __TEST2__ ziet meting van __TEST__ niet"
    # Zorg dat er minstens één meting voor client 999 onder __TEST__ bestaat
    c1 = ApiClient(); c1.login_pro("__TEST__")
    c1.select_client(999)
    r = c1.submit_measurement()
    if r.status_code != 200:
        return _report(name, False, f"voorbereiding: POST status={r.status_code}")

    # Nu als __TEST2__ proberen de metingen voor client 999 op te halen
    c2 = ApiClient(); c2.login_pro("__TEST2__")
    r = c2.list_client_metingen(999)

    if r.status_code == 404:
        return _report(name, True,
                       "endpoint retourneert 404 voor __TEST2__ — isolatie correct")
    if r.status_code == 200:
        try:
            body = r.json()
        except Exception:
            body = r.text[:200]
        return _report(name, False,
                       f"__TEST2__ kreeg 200 met body={body} — LEK!")
    return _report(name, False, f"onverwachte status={r.status_code} body={r.text[:200]}")


TESTS = [a1_consumer_meting, a2_pro_client_meting, a3_pro_eigen_meting,
         a4_regressie_21_april, a5_pro_wisselclient, a6_data_isolatie]


def main():
    passed = failed = 0
    start = time.time()
    for t in TESTS:
        try:
            ok = t()
        except Exception as e:
            import traceback
            print(f"[FAIL] {t.__name__}: onverwachte exception: {e}")
            traceback.print_exc()
            ok = False
        passed += 1 if ok else 0
        failed += 0 if ok else 1
    dur = time.time() - start
    print(f"\ncategorie A: {passed} passed, {failed} failed  ({dur:.1f}s)")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
