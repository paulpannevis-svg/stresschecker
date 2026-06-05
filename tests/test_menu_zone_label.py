"""Tests voor de zone-label/-omschrijving op de dashboard-welkomstkaart (menu.html).

Achtergrond: de kaart "Letzte Basismessung" toonde hardcoded NL pré-rebrand
terminologie ("Lichte Stress" / "Er is lichte stress aanwezig") ongeacht de
actieve locale. De fix laat de kaart render-time vertalen via de canonieke
zone-bron in analytics.py (zone_for_ri → zone_label/zone_description), zodat
NL/DE/EN correct en in de rebrand-terminologie (belast-familie) tonen.

Belangrijk: de meting wordt numeriek opgeslagen (RI-getal), niet als tekst.
Een meting die onder NL is gedaan, rendert dus automatisch correct onder DE/EN —
dat is precies wat T3 (cross-locale) bevestigt.

Vijf tests:
    T1 — analytics-bron: alle 5 zones × NL/DE/EN label+omschrijving kloppen
    T2 — kaart rendert in DE de rebrand-term "Leicht belastet" + DE-omschrijving,
         en NIET de oude "Lichte Stress"/"lichte stress aanwezig"
    T3 — cross-locale: zelfde numerieke meting (RI=5.0) onder nl/de/en geeft per
         locale het juiste label (storage is locale-onafhankelijk)
    T4 — elke zone-grenswaarde rendert in de kaart het verwachte label (DE)
    T5 — REGRESSIE: oude pré-rebrand strings komen in geen enkele locale meer voor

Output: print "test_menu_zone_label: N passed, M failed (Ts)". Exit 0/1.
"""

import sys
import time

sys.path.insert(0, "/opt/stresschecker")

import analytics
from app import app

# zone-key → (ri-representant, nl_label, de_label, en_label)
_ZONES = [
    ("zwaar_belast", 1.0, "Zwaar belast", "Schwer belastet", "Heavily strained"),
    ("belast",       3.0, "Belast",       "Belastet",        "Strained"),
    ("licht_belast", 5.0, "Licht belast", "Leicht belastet", "Lightly strained"),
    ("in_balans",    7.0, "In balans",    "Im Gleichgewicht", "In balance"),
    ("veerkrachtig", 9.0, "Veerkrachtig", "Vital",           "Resilient"),
]

_OLD_STRINGS = ["Zware Stress", "Lichte Stress", "Er is lichte stress aanwezig.",
                "Je ANS wijst op stress.", "Je bent veerkrachtig en ontspannen."]

_passed = 0
_failed = 0


def _ok(name, detail=""):
    global _passed
    _passed += 1
    print(f"[PASS] {name}{(': ' + detail) if detail else ''}")


def _fail(name, detail=""):
    global _failed
    _failed += 1
    print(f"[FAIL] {name}{(': ' + detail) if detail else ''}")


def _render_card(ri, lang):
    """Render menu.html met één meting (RI=ri) onder de gegeven locale."""
    with app.test_request_context("/menu"):
        return app.jinja_env.get_template("menu.html").render(
            lang=lang, name="Steven",
            license_type="basic",
            last_meting=(ri, 60, 100),
            demo_mode=False,
        )


def t1_analytics_source():
    bad = []
    for key, ri, nl, de, en in _ZONES:
        if analytics.zone_for_ri(ri) != key:
            bad.append(f"zone_for_ri({ri})={analytics.zone_for_ri(ri)}≠{key}")
        for lang, exp in (("nl", nl), ("de", de), ("en", en)):
            got = analytics.zone_label(key, lang)
            if got != exp:
                bad.append(f"label[{key},{lang}]={got!r}≠{exp!r}")
            desc = analytics.zone_description(key, lang)
            if not desc or desc == key:
                bad.append(f"desc[{key},{lang}] leeg")
    if bad:
        _fail("T1 analytics-bron 5 zones × 3 talen", "; ".join(bad[:4]))
    else:
        _ok("T1 analytics-bron 5 zones × 3 talen", "label+omschrijving compleet")


def t2_de_card_rebrand():
    html = _render_card(5.0, "de")
    de_desc = analytics.zone_description("licht_belast", "de")
    if "Leicht belastet" in html and de_desc in html \
            and "Lichte Stress" not in html and "lichte stress aanwezig" not in html:
        _ok("T2 DE-kaart rebrand-term", "toont 'Leicht belastet' + DE-omschrijving")
    else:
        _fail("T2 DE-kaart rebrand-term",
              f"Leicht belastet={'Leicht belastet' in html} desc={de_desc in html}")


def t3_cross_locale():
    bad = []
    for lang, idx in (("nl", 2), ("de", 3), ("en", 4)):
        html = _render_card(5.0, lang)
        exp_label = _ZONES[2][idx]  # licht_belast
        exp_desc = analytics.zone_description("licht_belast", lang)
        if exp_label not in html or exp_desc not in html:
            bad.append(f"{lang}: label/desc ontbreekt")
    if bad:
        _fail("T3 cross-locale (RI=5.0)", "; ".join(bad))
    else:
        _ok("T3 cross-locale (RI=5.0)", "numerieke meting rendert per locale correct")


def t4_zone_boundaries_de():
    bad = []
    for key, ri, nl, de, en in _ZONES:
        html = _render_card(ri, "de")
        if de not in html:
            bad.append(f"RI={ri}: '{de}' ontbreekt")
    if bad:
        _fail("T4 zone-grenzen DE", "; ".join(bad))
    else:
        _ok("T4 zone-grenzen DE", "alle 5 zones tonen juiste DE-label")


def t5_no_old_strings():
    bad = []
    for lang in ("nl", "de", "en"):
        for ri in (1.0, 3.0, 5.0, 7.0, 9.0):
            html = _render_card(ri, lang)
            for old in _OLD_STRINGS:
                if old in html:
                    bad.append(f"{lang}/RI={ri}: '{old}'")
    if bad:
        _fail("T5 regressie oude termen weg", "; ".join(bad[:4]))
    else:
        _ok("T5 regressie oude termen weg", "geen pré-rebrand strings in alle locales")


def main():
    start = time.time()
    t1_analytics_source()
    t2_de_card_rebrand()
    t3_cross_locale()
    t4_zone_boundaries_de()
    t5_no_old_strings()
    dt = time.time() - start
    print(f"\ntest_menu_zone_label: {_passed} passed, {_failed} failed  ({dt:.1f}s)")
    sys.exit(1 if _failed else 0)


if __name__ == "__main__":
    main()
