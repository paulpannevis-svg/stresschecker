"""Vangnet — de gedeelde pro-trend-drempel (RI week-over-week) blijft 0,3.

WAT DIT BEWAAKT
pro_dashboard (/pro/dashboard) en pro_clients (/pro/clienten) melden een cliënt-trend
"up/down/flat" o.b.v. het verschil tussen het week-gemiddelde en dat van de vorige week.
Beide MOETEN dezelfde drempel gebruiken (anders oordelen de twee B2B-oppervlakken
verschillend op dezelfde data). De drempel is geünificeerd op de canonieke 0,3 via de
module-constante app.PRO_TREND_DELTA. Deze test legt die waarde vast én borgt dat beide
routes de constante gebruiken (geen teruggeslopen hardcoded 0,1/0,3-literal).

Analoog aan de parity-test (categorie E) voor de pipeline; dit is de business/UI-drempel.
Bewust GEEN behandeling van kwaliteitsgate (Fase 3) of ÷2,5 (Fase 4).

Waarom source-inspectie i.p.v. `import app`: app importeren draait ALTER/CREATE op de
prod-DB-paden als bijwerking (zie feedback_schema_migrations_import_side_effect). Deze
test leest app.py via AST — geen import, geen side-effect, suite-veilig.

DRAAIEN:  python3 tests/test_pro_trend_threshold.py   (exit 0 = groen, 1 = rood)
          of via tests/run_all.sh (categorie F).
"""

import ast
import os
import sys
import time

APP_PY = "/opt/stresschecker/app.py"
EXPECTED_DELTA = 0.3


def _report(name, ok, reason):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {reason}")
    return ok


def _load():
    src = open(APP_PY, encoding="utf-8").read()
    tree = ast.parse(src)
    delta = None
    funcs = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "PRO_TREND_DELTA" and isinstance(node.value, ast.Constant):
                    delta = node.value.value
        if isinstance(node, ast.FunctionDef) and node.name in ("pro_dashboard", "pro_clients"):
            funcs[node.name] = ast.get_source_segment(src, node) or ""
    return delta, funcs


def t1_constant_value():
    name = "T1 PRO_TREND_DELTA == 0.3 (canonieke gedeelde drempel)"
    delta, _ = _load()
    ok = (delta == EXPECTED_DELTA)
    return _report(name, ok, f"PRO_TREND_DELTA={delta!r} (verwacht {EXPECTED_DELTA})")


def t2_both_routes_use_constant():
    name = "T2 pro_dashboard + pro_clients gebruiken PRO_TREND_DELTA (geen hardcoded literal)"
    _, funcs = _load()
    fails = []
    for fn in ("pro_dashboard", "pro_clients"):
        body = funcs.get(fn, "")
        if not body:
            fails.append(f"{fn}: functie niet gevonden")
            continue
        if "PRO_TREND_DELTA" not in body:
            fails.append(f"{fn}: gebruikt PRO_TREND_DELTA niet")
        # teruggeslopen bare-literal drempels in de trend-vergelijking
        for bad in ("avg_prev + 0.1", "avg_prev - 0.1", "avg_prev + 0.3", "avg_prev - 0.3",
                    "prev > 0.3", "prev < -0.3", "prev > 0.1", "prev < -0.1"):
            if bad in body:
                fails.append(f"{fn}: bevat hardcoded drempel-literal {bad!r}")
    if fails:
        return _report(name, False, "; ".join(fails))
    return _report(name, True, "beide routes verwijzen naar de gedeelde constante, geen bare literal")


def t3_threshold_semantics():
    name = "T3 drempel-semantiek: |Δ|<=drempel → flat, > drempel → up/down"
    delta, _ = _load()
    if delta is None:
        return _report(name, False, "PRO_TREND_DELTA niet gevonden")

    def classify(d):
        return "up" if d > delta else ("down" if d < -delta else "flat")

    cases = [(0.0, "flat"), (0.1, "flat"), (0.2, "flat"), (delta, "flat"),
             (delta + 0.01, "up"), (0.4, "up"), (-0.2, "flat"), (-(delta + 0.01), "down"), (-0.5, "down")]
    fails = [f"Δ={d}→{classify(d)} (verwacht {exp})" for d, exp in cases if classify(d) != exp]
    if fails:
        return _report(name, False, "; ".join(fails))
    return _report(name, True, f"grenzen kloppen bij drempel {delta} (0.1/0.2→flat, {delta}→flat, >{delta}→up/down)")


TESTS = [t1_constant_value, t2_both_routes_use_constant, t3_threshold_semantics]


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
    print(f"\ntest_pro_trend_threshold: {passed} passed, {failed} failed  ({time.time()-start:.1f}s)")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
