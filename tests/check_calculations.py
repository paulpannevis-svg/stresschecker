"""Categorie B — kernberekening regressietests.

Vergelijkt de uitkomsten van de productie-HRV-code (JavaScript in
/opt/stresschecker/static/js/hrv.js) met de expected values in
lib/references.json.

De productiecode zit in JS omdat de berekeningen in de browser lopen;
app.py slaat de door de browser gerapporteerde waardes alleen op.
Voor deze tests roepen we de JS aan via Node 18 en vergelijken de
output byte-voor-byte met de gecaptureerde expected values.

Tests:
    B1 — RMSSD op de referentie-RR-set
    B2 — RI via Verveen-lookup (bpm, hrv%)
    B3 — HRV% met age=50, gender=male (÷2,5-factor verwijderd 2026-06-08; nieuwe schaal)
    B4 — Zone-indeling op grens-RI-waardes (1.9, 2.0, 3.9, 4.0, 5.9,
         6.0, 7.9, 8.0) via HRV.getLabel

Harde timeout: 30 seconden per test.
"""

import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REF_PATH = os.path.join(HERE, "lib", "references.json")
HRV_JS = "/opt/stresschecker/static/js/hrv.js"

RMSSD_EPSILON = 1e-6


def _load_references():
    with open(REF_PATH) as fh:
        return json.load(fh)


def _run_node(script):
    """Draait Node-inline met 30s timeout en parseert 'R='-regel."""
    out = subprocess.run(
        ["node", "-e", script],
        capture_output=True, text=True, timeout=30,
    )
    if out.returncode != 0:
        raise RuntimeError(f"Node error: {out.stderr[:400]}")
    for line in out.stdout.splitlines():
        if line.startswith("R="):
            return json.loads(line[2:])
    raise RuntimeError(f"Node output bevat geen R=-regel:\n{out.stdout[:400]}")


def _report(name, ok, reason):
    tag = "PASS" if ok else "FAIL"
    print(f"[{tag}] {name}: {reason}")
    return ok


def b1_rmssd():
    name = "B1 RMSSD op referentie-RR-set"
    ref = _load_references()
    rr = ref["rr_intervals_ms"]
    exp = ref["expected"]["rmssd_ms"]
    script = (
        "var HRV = require('%s');"
        "var rr = %s;"
        "process.stdout.write('R=' + JSON.stringify({rmssd: HRV.calculateRMSSD(rr)}) + '\\n');"
    ) % (HRV_JS, json.dumps(rr))
    got = _run_node(script)["rmssd"]
    diff = abs(got - exp)
    ok = diff < RMSSD_EPSILON
    return _report(name, ok,
                   f"got={got} expected={exp} |Δ|={diff:.2e} (eps={RMSSD_EPSILON:.0e})")


def b2_ri_verveen():
    name = "B2 RI via Verveen-lookup"
    ref = _load_references()
    bpm = ref["expected"]["bpm"]
    hrv_pct = ref["expected"]["hrv_percent"]
    exp = ref["expected"]["ri"]
    script = (
        "var HRV = require('%s');"
        "process.stdout.write('R=' + JSON.stringify({ri: HRV.lookupRelaxIndex(%d, %d)}) + '\\n');"
    ) % (HRV_JS, bpm, hrv_pct)
    got = _run_node(script)["ri"]
    ok = got == exp
    return _report(name, ok, f"got={got} expected={exp}  (bpm={bpm}, hrv%={hrv_pct})")


def b3_hrv_percent():
    name = "B3 HRV% (age=50, male; ÷2,5 verwijderd — nieuwe schaal)"
    ref = _load_references()
    rr = ref["rr_intervals_ms"]
    age = ref["_meta"]["hrv_percent_assumptions"]["age"]
    sex = ref["_meta"]["hrv_percent_assumptions"]["sex"]
    exp = ref["expected"]["hrv_percent"]
    script = (
        "var HRV = require('%s');"
        "var rr = %s;"
        "process.stdout.write('R=' + JSON.stringify("
        "{hrv_pct: HRV.calculateHRVPercent(rr, %d, '%s')}) + '\\n');"
    ) % (HRV_JS, json.dumps(rr), age, sex)
    got = _run_node(script)["hrv_pct"]
    ok = got == exp
    return _report(name, ok, f"got={got} expected={exp}")


def b4_zone_boundaries():
    name = "B4 zone-indeling op grenswaardes (1.9/2.0/3.9/4.0/5.9/6.0/7.9/8.0)"
    ref = _load_references()
    boundary_tests = {float(k): v for k, v in ref["boundary_tests"].items()
                      if not k.startswith("_")}
    # Mapping van productie-NL-label naar Pauls zone-naam
    label_to_zone = {v["production_label_nl"]: k
                     for k, v in ref["zone_boundaries"].items()
                     if not k.startswith("_")}

    # Node met window-shim; lever resultaten als [idx, label]-paren zodat
    # integer-floats (2.0, 4.0, …) niet stilletjes naar "2"/"4" casten.
    values = sorted(boundary_tests.keys())
    script = (
        "global.window = {SC_LANG:'nl'};"
        "var HRV = require('%s');"
        "var vs = %s;"
        "var out = [];"
        "for (var i=0;i<vs.length;i++){ out.push([i, HRV.getLabel(vs[i])]); }"
        "process.stdout.write('R=' + JSON.stringify({labels: out}) + '\\n');"
    ) % (HRV_JS, json.dumps(values))
    got_pairs = _run_node(script)["labels"]
    labels_by_idx = {idx: lbl for idx, lbl in got_pairs}

    failures = []
    for idx, ri_val in enumerate(values):
        expected_zone = boundary_tests[ri_val]
        prod_label = labels_by_idx.get(idx)
        got_zone = label_to_zone.get(prod_label)
        if got_zone != expected_zone:
            failures.append(
                f"RI={ri_val}: productie-label={prod_label!r} → zone={got_zone!r}, "
                f"verwacht {expected_zone!r}"
            )
    if failures:
        return _report(name, False, "; ".join(failures))
    return _report(
        name, True,
        f"alle 8 grenswaardes juist geclassificeerd: " +
        ", ".join(f"{v}→{boundary_tests[v]}" for v in values),
    )


TESTS = [b1_rmssd, b2_ri_verveen, b3_hrv_percent, b4_zone_boundaries]


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
    print(f"\ncategorie B: {passed} passed, {failed} failed  ({dur:.1f}s)")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
