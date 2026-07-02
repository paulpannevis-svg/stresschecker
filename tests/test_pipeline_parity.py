"""Golden CROSS-PIPELINE parity — het vangnet vóór de RI-pipeline-consolidatie.

WAT DIT BEWAAKT
Eén begrip (RI, zone, kwaliteit) heeft in de codebase meerdere implementaties over
drie producten (SC / SC Pro / SC Pro Event). Deze test voert dezelfde bekende inputs
door de drie pipelines en FAALT zodra één pad afwijkt:

  (a) static/js/hrv.js   — lookupRelaxIndex / calculateRMSSD / calculateHRVPercent /
                           getLabel (zone) / qualityClassify (band) / riConfidence (kw-gate)
                           — aangeroepen via Node.
  (b) analytics.py       — quality_classify (band) + zone_for_ri/zone_label (zone).
  (c) event_quadrant.py  — de B/C/T-lookuptabellen die uit hrv.js worden GEPARSED
                           (Event-PDF), plus raw→zone.

De drie moeten het eens zijn over: RI-getal, zone(-label), quality-band en de
kwaliteit-drempels. Het absolute anker (RI + zone) komt uit lib/references.json.
rmssd/hrv% zijn single-source (alleen hrv.js) — hun absolute regressie zit in
check_calculations B1/B3 (momenteel ÷2,5-referentie-drift, Fase 4); hier bewust niet
her-ankeren zodat dit vangnet groen blijft op de huidige code.

DEKKING (zoals afgesproken):
  * één normale meting per zone (Zwaar belast … Veerkrachtig / Stark belastet … Vital)
  * één quality-afgekeurde meting (band='slecht') — in beide band-pipelines
  * één untrusted meting (kwaliteit<70) via de kwaliteit-drempel (riConfidence)
  * de zone-grenzen 2/4/6/8 (hrv.js getLabel ↔ analytics.zone_for_ri)

Noot: hrv.js lookupRelaxIndex kiest de dichtstbijzijnde cel, event_quadrant.get_raw
interpoleert bilineair — dus we borgen dat (1) event de ZELFDE B/C/T-tabellen gebruikt
(byte-identiek geparsed) en (2) event's raw→zone in dezelfde zone valt als de canonieke
RI, NIET dat beide algoritmes hetzelfde getal geven.

De app-laag `_kompas_quality_excluded(rr, kwaliteit)` = is_slecht_rr(rr) OF kwaliteit<70;
beide componenten worden hier los geborgd (analytics.is_slecht_rr + hrv.js riConfidence),
zodat de test geen `import app` nodig heeft (dat muteert prod-DB's — zie
feedback_schema_migrations_import_side_effect).

DRAAIEN:   python3 tests/test_pipeline_parity.py     (exit 0 = groen, 1 = rood)
           of via tests/run_all.sh. Vereist `node` op PATH.
SELF-TEST: SC_PARITY_SELFTEST=1 python3 tests/test_pipeline_parity.py  → forceert één
           afwijking en MOET rood worden (bewijst dat het vangnet bijt).
"""

import json
import os
import subprocess
import sys
import time

sys.path.insert(0, "/opt/stresschecker")
import analytics

HERE = os.path.dirname(os.path.abspath(__file__))
HRV_JS = "/opt/stresschecker/static/js/hrv.js"
REF_PATH = os.path.join(HERE, "lib", "references.json")

# Optionele self-test: forceer één divergentie om te bewijzen dat de test rood wordt.
SELFTEST = os.environ.get("SC_PARITY_SELFTEST") == "1"

# ── Golden cases: één normale meting per zone (bpm, hrv%) → verwachte RI + zone-key ──
# RI-waarden zijn gecaptureerd uit productie-hrv.js (lookupRelaxIndex).
ZONE_CASES = [
    {"bpm": 60, "hrv": 20,  "ri": 1.0, "zone": "zwaar_belast"},
    {"bpm": 60, "hrv": 40,  "ri": 3.5, "zone": "belast"},
    {"bpm": 60, "hrv": 60,  "ri": 5.0, "zone": "licht_belast"},
    {"bpm": 62, "hrv": 100, "ri": 6.7, "zone": "in_balans"},
    {"bpm": 60, "hrv": 160, "ri": 9.6, "zone": "veerkrachtig"},
]

# Zone-grenzen (Pauls spec): exact grens-RI → verwachte zone-key.
BOUNDARY_CASES = [
    (1.9, "zwaar_belast"), (2.0, "belast"), (3.9, "belast"), (4.0, "licht_belast"),
    (5.9, "licht_belast"), (6.0, "in_balans"), (7.9, "in_balans"), (8.0, "veerkrachtig"),
]

# Quality-cases: een sterk onregelmatige reeks (band='slecht') en een schone (band='goed').
RR_SLECHT = [800, 1200, 780, 1250, 760, 1300, 820, 700, 1280, 750, 1290,
             810, 690, 1310, 770, 1270, 800, 720, 1260, 830, 760]
RR_SCHOON = [900, 902, 905, 906, 908, 908, 908, 906, 905, 902, 900, 898, 895, 894,
             892, 892, 892, 894, 895, 898, 900, 902, 905, 906, 908, 908, 908, 906,
             905, 902, 900, 898, 895, 894, 892, 892, 892, 894, 895, 898]


def _run_node(script):
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
    if out.returncode != 0:
        raise RuntimeError(f"Node error: {out.stderr[:400]}")
    for line in out.stdout.splitlines():
        if line.startswith("R="):
            return json.loads(line[2:])
    raise RuntimeError(f"Node output bevat geen R=-regel:\n{out.stdout[:400]}")


def _js(expr_body):
    """Draai hrv.js-expressies met NL-locale-shim; expr_body zet `out`."""
    return _run_node(
        "global.window={SC_LANG:'nl'};"
        "var HRV=require('%s');var out={};%s"
        "process.stdout.write('R='+JSON.stringify(out)+'\\n');" % (HRV_JS, expr_body)
    )


def _report(name, ok, reason):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {reason}")
    return ok


def _zone_label_nl(zone_key):
    return analytics.zone_label(zone_key, "nl")


# ── P1: RI + zone parity per zone (hrv.js ↔ analytics ↔ event) ──────────────────────
def p1_zone_parity():
    name = "P1 RI+zone parity per zone (hrv.js ↔ analytics ↔ event)"
    import event_quadrant as EQ
    cases = json.dumps([[c["bpm"], c["hrv"]] for c in ZONE_CASES])
    got = _js(
        "var cs=%s;out.rows=cs.map(function(c){var ri=HRV.lookupRelaxIndex(c[0],c[1]);"
        "return [ri, HRV.getLabel(ri)];});" % cases
    )["rows"]
    fails = []
    for i, c in enumerate(ZONE_CASES):
        js_ri, js_zone_label = got[i]
        exp_label = _zone_label_nl(c["zone"])
        py_zone_label = _zone_label_nl(analytics.zone_for_ri(js_ri))
        # event: raw→RI→zone (bilineair; mag qua getal iets afwijken, zone moet kloppen)
        ev_ri = EQ.get_raw(c["bpm"], c["hrv"]) / 12.0
        ev_zone_label = _zone_label_nl(analytics.zone_for_ri(ev_ri))
        exp_ri = c["ri"]
        if SELFTEST and i == 0:
            exp_ri = 9.9  # geforceerde afwijking → moet P1 rood maken
        if not (abs(js_ri - exp_ri) < 1e-9 and js_zone_label == exp_label
                and py_zone_label == exp_label and ev_zone_label == exp_label):
            fails.append(
                f"(bpm={c['bpm']},hrv%={c['hrv']}): js_ri={js_ri}(exp {exp_ri}) "
                f"js_zone={js_zone_label!r} py_zone={py_zone_label!r} "
                f"ev_zone={ev_zone_label!r} exp={exp_label!r}"
            )
    if fails:
        return _report(name, False, "; ".join(fails))
    return _report(name, True, f"{len(ZONE_CASES)} zones eensluidend over 3 pipelines")


# ── P2: zone-grenzen 2/4/6/8 (hrv.js getLabel ↔ analytics.zone_for_ri) ──────────────
def p2_boundary_parity():
    name = "P2 zone-grenzen 2/4/6/8 (hrv.js ↔ analytics)"
    ris = json.dumps([r for r, _ in BOUNDARY_CASES])
    got = _js("var rs=%s;out.labels=rs.map(function(r){return HRV.getLabel(r);});" % ris)["labels"]
    fails = []
    for i, (ri, zone) in enumerate(BOUNDARY_CASES):
        exp_label = _zone_label_nl(zone)
        js_label = got[i]
        py_label = _zone_label_nl(analytics.zone_for_ri(ri))
        if not (js_label == exp_label and py_label == exp_label):
            fails.append(f"RI={ri}: js={js_label!r} py={py_label!r} exp={exp_label!r}")
    if fails:
        return _report(name, False, "; ".join(fails))
    return _report(name, True, "alle 8 grenswaardes eensluidend (hrv.js ↔ analytics)")


# ── P3: quality-band parity (hrv.js qualityClassify ↔ analytics.quality_classify) ───
def p3_quality_parity():
    name = "P3 quality-band parity (slecht + schoon)"
    got = _js(
        "out.slecht=HRV.qualityClassify(%s).band;out.schoon=HRV.qualityClassify(%s).band;"
        % (json.dumps(RR_SLECHT), json.dumps(RR_SCHOON))
    )
    py_slecht = analytics.quality_classify(RR_SLECHT)["band"]
    py_schoon = analytics.quality_classify(RR_SCHOON)["band"]
    exp_slecht = "goed" if SELFTEST else "slecht"  # self-test forceert mismatch
    ok = (got["slecht"] == "slecht" == py_slecht
          and got["schoon"] == "goed" == py_schoon
          and py_slecht == exp_slecht)
    return _report(name, ok,
                   f"slecht: js={got['slecht']} py={py_slecht} | "
                   f"schoon: js={got['schoon']} py={py_schoon}")


# ── P4: kwaliteit-drempel / untrusted (hrv.js riConfidence) + is_slecht_rr SSOT ─────
def p4_kwaliteit_gate():
    name = "P4 kwaliteit-drempel (untrusted<70) + is_slecht_rr SSOT"
    got = _js("out.u=HRV.riConfidence(60);out.l=HRV.riConfidence(80);out.t=HRV.riConfidence(90);")
    conf_ok = got["u"] == "untrusted" and got["l"] == "limited" and got["t"] == "trusted"
    # is_slecht_rr = SSOT achter _kompas_quality_excluded (band-component)
    slecht_ok = analytics.is_slecht_rr(RR_SLECHT) is True and analytics.is_slecht_rr(RR_SCHOON) is False
    ok = conf_ok and slecht_ok
    return _report(name, ok,
                   f"riConfidence 60/80/90={got['u']}/{got['l']}/{got['t']} | "
                   f"is_slecht_rr slecht={analytics.is_slecht_rr(RR_SLECHT)} "
                   f"schoon={analytics.is_slecht_rr(RR_SCHOON)}")


# ── P5: event_quadrant B/C/T byte-identiek aan hrv.js (dezelfde lookupbron) ─────────
def p5_event_tables():
    name = "P5 event_quadrant B/C/T == hrv.js (geen overgetikte kopie)"
    import re
    import event_quadrant as EQ
    txt = open(HRV_JS).read()

    def arr(n):
        return json.loads(re.search(r"^var %s=(\[.*\]);" % n, txt, re.M).group(1))

    ok = (EQ.B == arr("B") and EQ.C == arr("C") and EQ.T == arr("T"))
    return _report(name, ok, f"B({len(EQ.B)}) C({len(EQ.C)}) T({len(EQ.T)}x{len(EQ.T[0])}) identiek={ok}")


# ── P6: absolute anker (references.json: RI + zone) ─────────────────────────────────
# BEWUST alleen RI + zone (schaal-invariant). rmssd/hrv% zijn single-source (alleen hrv.js;
# geen analytics/event-twin) en hun ABSOLUTE regressie hoort bij check_calculations B1/B3 —
# die zijn momenteel rood door de openstaande ÷2,5-referentie-drift (Fase 4, buiten scope).
# Hier daarom niet dubbel anker­en op die stale waarden, anders zou dit vangnet altijd rood staan.
def p6_reference_anchors():
    name = "P6 absoluut anker (references.json: RI + zone via hrv.js)"
    ref = json.load(open(REF_PATH))
    exp = ref["expected"]
    got = _js("out.ri=HRV.lookupRelaxIndex(%d,%d);" % (exp["bpm"], exp["hrv_percent"]))
    ri = got["ri"]
    zone_label = _zone_label_nl(analytics.zone_for_ri(ri))
    ok = (ri == exp["ri"] and zone_label == exp["zone_label_nl"])
    return _report(name, ok, f"ri={ri}/{exp['ri']} zone={zone_label!r}/{exp['zone_label_nl']!r}")


TESTS = [p1_zone_parity, p2_boundary_parity, p3_quality_parity,
         p4_kwaliteit_gate, p5_event_tables, p6_reference_anchors]


def main():
    if SELFTEST:
        print(">>> SC_PARITY_SELFTEST actief: één pad is opzettelijk afwijkend; "
              "verwacht MINSTENS één FAIL.\n")
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
    print(f"\ntest_pipeline_parity: {passed} passed, {failed} failed  ({time.time()-start:.1f}s)")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
