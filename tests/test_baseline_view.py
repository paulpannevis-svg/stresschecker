#!/usr/bin/env python3
"""Stap 2 — render-test baseline-referentielijn op pro/eigen_metingen.html.

DB-onafhankelijk: rendert de template met gecontroleerde baseline-waarde.
Eisen: label "Baseline" (zelfde term 3 talen), juiste tooltip per taal,
geen lijn bij baseline=None, en de bestaande RI-/Zelfinschatting-datasets
blijven intact (additief).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app as A
from flask import render_template

passed = failed = 0
def check(name, cond, extra=''):
    global passed, failed
    if cond: passed += 1; print(f"[PASS] {name}")
    else: failed += 1; print(f"[FAIL] {name} {extra}")

TIPS = {
    'nl': 'het gemiddelde van je laatste 7 basismetingen (één per dag)',
    'de': 'der Durchschnitt Ihrer letzten 7 Basismessungen (eine pro Tag)',
    'en': 'the average of your last 7 baseline measurements (one per day)',
}

def render(lang, baseline):
    with A.app.test_request_context('/pro/mijn-metingen'):
        from flask import session
        session['license_valid'] = True; session['license_type'] = 'pro'; session['lang'] = lang
        return render_template('pro/eigen_metingen.html', lang=lang,
                               metingen=[], metingen_chart=[], baseline=baseline)

# Baseline aanwezig (3 talen)
for lang in ('nl', 'de', 'en'):
    html = render(lang, 6.5)
    check(f"[{lang}] BASELINE-waarde in JS", 'var BASELINE = 6.5' in html, "")
    check(f"[{lang}] baseline als legenda-dataset (label 'Baseline', zelfde term)",
          "datasets.push" in html and "label:'Baseline'" in html, "")
    check(f"[{lang}] gestippeld + neutrale kleur", 'borderDash:[5,4]' in html and 'rgba(110,110,110' in html, "")
    check(f"[{lang}] toelichting via tooltip-footer", TIPS[lang] in html and 'callbacks.footer' in html, "")
    check(f"[{lang}] additief ná constructie (geen annotation-label)",
          'content:\'Baseline\'' not in html, "")
    # datasets intact
    check(f"[{lang}] RI-dataset intact", "label:'Relax Index'" in html, "")
    check(f"[{lang}] Zelfinschatting-dataset intact",
          ('Selbsteinschätzung' in html or 'Self-assessment' in html or 'Zelfinschatting' in html), "")

# Baseline afwezig → geen waarde, guard houdt lijn weg
html_none = render('nl', None)
check("baseline None → var BASELINE = null", 'var BASELINE = null' in html_none, "")
check("baseline None → guard if(BASELINE != null) aanwezig", 'if(BASELINE != null)' in html_none, "")

print(f"\ntest_baseline_view: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
