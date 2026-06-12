#!/usr/bin/env python3
"""Parity-test meetkwaliteit/onregelmatigheid-gates: één bron van waarheid in twee talen
(server-aggregaten draaien Python; de meetschermen draaien JS) — deze test bewaakt dat ze
niet uiteenlopen. Faalt (exit 1) bij elke divergentie.

PROD-BEWAKING (altijd actief): variant-B meetkwaliteit — analytics.quality_classify (Python)
MOET exact == static/js/hrv.js :: HRV.qualityClassify (JS): band + tussenwaarden, op 221
RR-reeksen (synthetisch + 68 echte PI-Zwolle).

EMBARGO/DORMANT (overgeslagen zolang afwezig): de oude onregelmatigheid-gate
(analytics.rr_irregular <-> HRV.rrIrregularity). Die functies staan NIET op deze branch
(embargo, wacht >=2026-06-22). De test slaat die helft automatisch over zolang
analytics.rr_irregular ontbreekt en herleeft zodra de gate landt — zonder aanpassing.

Deterministisch (geen random): RR-reeksen met variërende gemiddelden/variabiliteit,
inclusief vlak-kalme (SD1/SD2->1 maar lage RMSSD) en hoog-variabele reeksen rond de drempels.
"""
import os, sys, json, math, subprocess, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import analytics  # noqa: E402


def make_rr(n, base, amp, period, drift):
    """Deterministische RR-reeks (ms): basislijn + sinus-variatie + lichte drift. Geen random."""
    out = []
    for i in range(n):
        v = base + amp * math.sin(2 * math.pi * i / period) + drift * i
        # afwisselende kleine sprong zodat opeenvolgende verschillen niet triviaal 0 zijn
        v += (amp * 0.25) * (1 if i % 2 else -1)
        out.append(round(v, 1))
    return out


def build_cases():
    cases = []
    for n in (25, 60, 100):
        for base in (700, 850, 1000):
            for amp in (3, 12, 28, 55, 110):
                for period in (4, 9, 20):
                    cases.append(make_rr(n, base, amp, period, drift=0.0))
    # paar randgevallen: te kort, en vlak (amp 0)
    cases.append(make_rr(10, 800, 40, 8, 0.0))     # < 20 -> beide False
    cases.append(make_rr(40, 900, 0, 8, 0.0))      # vlak -> lage RMSSD
    return cases


def _base_series(n, base=820, amp=18, period=9):
    out = []
    for i in range(n):
        v = base + amp * math.sin(2 * math.pi * i / period)
        v += (amp * 0.25) * (1 if i % 2 else -1)
        out.append(round(v, 1))
    return out


def make_artifact_cases():
    """Grensgevallen rond de variant-B-beslisranden: artefact-% ~5%/15%,
    run-lengte 1/2/3 (los/burst), en hoge variabiliteit (SD1/SD2 rond 0,70)."""
    cases, n = [], 100
    for k in (3, 5, 8, 15, 16, 20):            # losse spikes (run 1), oplopende dichtheid
        s = _base_series(n)
        for j in range(k):
            idx = 3 + j * (n // (k + 1))
            if 0 < idx < n:
                s[idx] = round(s[idx] * 1.6, 1)
        cases.append(s)
    for k in (2, 4, 6):                         # paren (run 2 → interpoleren)
        s = _base_series(n)
        for j in range(k):
            idx = 4 + j * (n // (k + 1))
            if 0 < idx < n - 1:
                s[idx] = round(s[idx] * 1.6, 1)
                s[idx + 1] = round(s[idx + 1] * 1.6, 1)
        cases.append(s)
    for k in (1, 2, 3):                         # triples (run 3 → consecutive/slecht)
        s = _base_series(n)
        for j in range(k):
            idx = 5 + j * (n // (k + 1))
            if 0 < idx < n - 2:
                for o in range(3):
                    s[idx + o] = round(s[idx + o] * 1.6, 1)
        cases.append(s)
    for delta in (40, 80, 160, 240):           # hoge variabiliteit → Laag2 rond 0,70
        cases.append([round(800 + (delta if i % 2 else -delta) * 0.5
                            + 30 * math.sin(2 * math.pi * i / 13), 1) for i in range(n)])
    return cases


def load_pi68():
    """68 echte PI-Zwolle-RR-reeksen (fixture); leeg bij ontbreken."""
    try:
        with open(os.path.join(ROOT, 'tests/lib/pi68_rr.json')) as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def check_quality_parity(cases):
    """quality_classify (Python) MOET == HRV.qualityClassify (JS): band + tussenwaarden."""
    FIELDS = ('artefactPct', 'maxRun', 'sd1sd2', 'rmssd')
    py = [analytics.quality_classify(c) for c in cases]
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as f:
        json.dump(cases, f)
        cases_path = f.name
    node_src = (
        "const HRV=require(%r);"
        "const cs=JSON.parse(require('fs').readFileSync(%r,'utf8'));"
        "console.log(JSON.stringify(cs.map(function(a){var q=HRV.qualityClassify(a);"
        "return {band:q.band,"
        "artefactPct:q.artefactPct===undefined?null:q.artefactPct,"
        "maxRun:q.maxRun===undefined?null:q.maxRun,"
        "sd1sd2:q.sd1sd2===undefined?null:q.sd1sd2,"
        "rmssd:q.rmssd===undefined?null:q.rmssd};})));"
        % (os.path.join(ROOT, 'static/js/hrv.js'), cases_path)
    )
    res = subprocess.run(['node', '-e', node_src], capture_output=True, text=True)
    os.unlink(cases_path)
    if res.returncode != 0:
        print("node-fout (quality):", res.stderr); sys.exit(1)
    js = json.loads(res.stdout.strip())
    if not (len(py) == len(js) == len(cases)):
        print("lengte-mismatch quality"); sys.exit(1)
    TOL = 1e-9
    mism = []
    for i, (p, j) in enumerate(zip(py, js)):
        if p.get('band') != j.get('band'):
            mism.append((i, 'band', p.get('band'), j.get('band'))); continue
        if p.get('band') == 'onbepaald':
            continue
        for fld in FIELDS:
            pv, jv = p.get(fld), j.get(fld)
            if pv is None or jv is None:
                if pv != jv:
                    mism.append((i, fld, pv, jv))
            elif abs(float(pv) - float(jv)) > TOL:
                mism.append((i, fld, pv, jv))
    if mism:
        print("DIVERGENTIE quality_classify Python vs JS op %d punt(en):" % len(mism))
        for i, fld, p, j in mism[:15]:
            print("  case %d veld %s: python=%s js=%s (n=%d)" % (i, fld, p, j, len(cases[i])))
        sys.exit(1)
    nb = sum(1 for p in py if p.get('band') == 'slecht')
    print("quality_parity: %d reeksen — band + tussenwaarden IDENTIEK (Python==JS), %d 'slecht'. GROEN"
          % (len(cases), nb))


def check_irregularity_parity(cases):
    """EMBARGO/dormant: oude onregelmatigheid-gate analytics.rr_irregular <-> HRV.rrIrregularity.
    Alleen aangeroepen wanneer analytics.rr_irregular bestaat (zie main)."""
    py = [bool(analytics.rr_irregular(c)) for c in cases]

    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as f:
        json.dump(cases, f)
        cases_path = f.name
    node_src = (
        "const HRV=require(%r);"
        "const cs=JSON.parse(require('fs').readFileSync(%r,'utf8'));"
        "console.log(JSON.stringify(cs.map(function(a){return !!HRV.rrIrregularity(a).flag;})));"
        % (os.path.join(ROOT, 'static/js/hrv.js'), cases_path)
    )
    res = subprocess.run(['node', '-e', node_src], capture_output=True, text=True)
    os.unlink(cases_path)
    if res.returncode != 0:
        print("node-fout:", res.stderr); sys.exit(1)
    js = json.loads(res.stdout.strip())

    assert len(py) == len(js) == len(cases), "lengte-mismatch"
    mism = [(i, py[i], js[i]) for i in range(len(cases)) if py[i] != js[i]]
    if mism:
        print("DIVERGENTIE Python vs JS op %d/%d reeksen:" % (len(mism), len(cases)))
        for i, p, j in mism[:10]:
            print("  case %d: python=%s js=%s (n=%d)" % (i, p, j, len(cases[i])))
        sys.exit(1)
    print("irrgate_parity: %d/%d reeksen — Python- en JS-gate IDENTIEK. GROEN" % (len(cases), len(cases)))


def main():
    # PROD-BEWAKING: variant-B-twin quality_classify (Python) == HRV.qualityClassify (JS)
    qcases = build_cases() + make_artifact_cases() + load_pi68()
    check_quality_parity(qcases)

    # EMBARGO/dormant: oude onregelmatigheid-gate. Overslaan zolang de functies niet op
    # deze branch staan; herleeft automatisch zodra de gate landt (>=2026-06-22).
    if hasattr(analytics, 'rr_irregular'):
        check_irregularity_parity(build_cases())
    else:
        print("irrgate_parity: OVERGESLAGEN (analytics.rr_irregular afwezig — "
              "embargo-gate niet op deze branch).")


if __name__ == '__main__':
    main()
