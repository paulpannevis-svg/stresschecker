#!/usr/bin/env python3
"""Stap 1 — losse test voor analytics.compute_baseline / baseline_day_values.

Eis (spec): baseline = gemiddelde RI van de laatste 7 KALENDERDAGEN met een
basismeting, per dag alleen de LAATSTE basismeting; alleen meting_type
'basismeting' telt; < 7 meetdagen → None.
"""
import sys, os, datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import analytics

passed = failed = 0
def check(name, cond, extra=''):
    global passed, failed
    if cond:
        passed += 1; print(f"[PASS] {name}")
    else:
        failed += 1; print(f"[FAIL] {name} {extra}")

UTC = datetime.timezone.utc
def ts(y, m, d, hh=12, mm=0):
    # 12:00 UTC valt op dezelfde kalenderdag in Europe/Amsterdam → geen dag-shift in de test
    return int(datetime.datetime(y, m, d, hh, mm, tzinfo=UTC).timestamp() * 1000)

def basis(y, m, d, ri, hh=12, mm=0):
    return {'ts': ts(y, m, d, hh, mm), 'ri': ri, 'meting_type': 'basismeting'}

# T1 — 7 dagen, één basismeting per dag → gemiddelde
rows = [basis(2026, 6, d, ri) for d, ri in zip(range(1, 8), [6.0, 7.0, 6.0, 7.0, 6.0, 7.0, 8.0])]
b = analytics.compute_baseline(rows)
check("T1 7 dagen, 1/dag → gemiddelde", b == round(sum([6,7,6,7,6,7,8])/7, 1), f"got={b}")

# T2 — biofeedback/situatiemeting tellen NOOIT mee (extreme RI's mogen niets veranderen)
noise = rows + [
    {'ts': ts(2026, 6, 4, 13), 'ri': 0.1, 'meting_type': 'biofeedback'},
    {'ts': ts(2026, 6, 4, 14), 'ri': 9.9, 'meting_type': 'situatiemeting'},
    {'ts': ts(2026, 6, 9, 12), 'ri': 0.0, 'meting_type': None},
]
check("T2 alleen basismetingen tellen", analytics.compute_baseline(noise) == b, f"got={analytics.compute_baseline(noise)} vs {b}")

# T3 — meerdere basismetingen op één dag → alleen de LAATSTE telt
multi = [basis(2026, 6, d, ri) for d, ri in zip(range(1, 8), [6.0, 7.0, 6.0, 7.0, 6.0, 7.0, 8.0])]
multi += [basis(2026, 6, 7, 2.0, hh=8)]    # eerder op dag 7 → moet genegeerd worden (8.0 is later)
multi += [basis(2026, 6, 1, 1.0, hh=8)]    # eerder op dag 1 → genegeerd (6.0 is later)
check("T3 laatste-per-dag", analytics.compute_baseline(multi) == b, f"got={analytics.compute_baseline(multi)} vs {b}")

# T4 — < 7 meetdagen → None
check("T4 6 dagen → None", analytics.compute_baseline(rows[:6]) is None, f"got={analytics.compute_baseline(rows[:6])}")
check("T4b 7 metingen maar 6 dagen → None",
      analytics.compute_baseline(rows[:6] + [basis(2026, 6, 6, 9.0, hh=20)]) is None)

# T5 — > 7 dagen → alleen de laatste 7 dagen
many = [basis(2026, 6, d, 1.0) for d in range(1, 4)]            # dag 1-3, RI 1.0 (oud, moet wegvallen)
many += [basis(2026, 6, d, 7.0) for d in range(4, 11)]          # dag 4-10, RI 7.0 (laatste 7 dagen)
check("T5 >7 dagen → laatste 7", analytics.compute_baseline(many) == 7.0, f"got={analytics.compute_baseline(many)}")

# T6 — exact 7 dagen grenswaarde
check("T6 exact 7 dagen → waarde (niet None)", analytics.compute_baseline(rows) is not None)

# T7 — baseline_day_values: chronologisch oud→nieuw, lengte 7
vals = analytics.baseline_day_values(many)
check("T7 day_values lengte 7", len(vals) == 7, f"len={len(vals)}")
check("T7b day_values = laatste 7 dagen (allemaal 7.0)", vals == [7.0]*7, f"got={vals}")

print(f"\ntest_baseline: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
