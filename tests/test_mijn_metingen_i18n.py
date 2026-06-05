"""Tests voor de i18n van de Detail-Info Messungen-pagina (/mijn-metingen).

Achtergrond: de pagina toonde NL-tekst op de DE/EN-UI:
1. paginatitel/kop/Terug zonder EN-tak,
2. kolom MESSUNG via een incomplete client-side JS-map (geen biofeedback, geen EN),
3. situatie-label (notes) als rauwe opgeslagen NL-tekst ("Na sport").

De fix vertaalt render-time via één bron (analytics.py): meting_type_label +
situation_label_translate (best-effort chip-mapping). Opslag is locale-onafhankelijk
(meting_type-code + vrije tekst), dus geen DB-migratie.

Tests:
    T1 — meting_type_label: 3 codes × NL/DE/EN + onbekende code verbatim
    T2 — chip-vertaling: "Na sport" → "Nach Sport" (de) / "After sport" (en);
         omgekeerd "Nach Sport" → "Na sport" (nl); case-insensitive
    T3 — vrije tekst blijft ongewijzigd ("test", "10 min ademoefening", leeg)
    T4 — pagina-render DE: titel Duits + kolom toont "Basismessung" (niet "basismeting")
    T5 — pagina-render EN: titel/kop/Terug Engels; kolom "Baseline"
    T6 — chip-tabel dekt de meetflow-chips (drift-guard sanity)

Output: print "test_mijn_metingen_i18n: N passed, M failed (Ts)". Exit 0/1.
"""

import sys
import time

sys.path.insert(0, "/opt/stresschecker")

import analytics
from app import app

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


def _render(lang, notes="Na sport", meting_type="basismeting"):
    with app.test_request_context("/mijn-metingen"):
        row = {
            "id": 1, "ts": 1717000000000, "ri": 5.0, "bpm": 60, "hrv_pct": 100,
            "rmssd": 34.0, "meting_type": meting_type, "notes": notes,
            "dimensie": "", "rr_intervals": "",
            "meting_type_label": analytics.meting_type_label(meting_type, lang),
        }
        row["notes"] = analytics.situation_label_translate(notes, lang)
        return app.jinja_env.get_template("mijn_metingen.html").render(
            lang=lang, metingen_chart=[row], session={"lang": lang})


def t1_meting_type_label():
    exp = {
        "basismeting":    {"nl": "Basismeting", "de": "Basismessung", "en": "Baseline"},
        "situatiemeting": {"nl": "Situatiemeting", "de": "Situationsmessung", "en": "Situational"},
        "biofeedback":    {"nl": "Biofeedback", "de": "Biofeedback", "en": "Biofeedback"},
    }
    bad = []
    for code, per in exp.items():
        for lang, label in per.items():
            got = analytics.meting_type_label(code, lang)
            if got != label:
                bad.append(f"{code}/{lang}={got!r}≠{label!r}")
    if analytics.meting_type_label("ietsraars", "de") != "ietsraars":
        bad.append("onbekende code niet verbatim")
    if analytics.meting_type_label("", "de") != "-":
        bad.append("lege code niet '-'")
    if bad:
        _fail("T1 meting_type_label", "; ".join(bad[:4]))
    else:
        _ok("T1 meting_type_label", "3 codes × NL/DE/EN + edge")


def t2_chip_translate():
    bad = []
    if analytics.situation_label_translate("Na sport", "de") != "Nach Sport":
        bad.append("Na sport→de")
    if analytics.situation_label_translate("Na sport", "en") != "After sport":
        bad.append("Na sport→en")
    if analytics.situation_label_translate("Nach Sport", "nl") != "Na sport":
        bad.append("Nach Sport→nl (omgekeerd)")
    if analytics.situation_label_translate("na sport", "de") != "Nach Sport":
        bad.append("case-insensitive")
    if analytics.situation_label_translate("Na meditatie", "de") != "Nach Meditation":
        bad.append("Na meditatie→de")
    if bad:
        _fail("T2 chip-vertaling", "; ".join(bad))
    else:
        _ok("T2 chip-vertaling", "bekende chips vertalen bidirectioneel")


def t3_free_text_verbatim():
    bad = []
    for txt in ("test", "10 min ademoefening", "Na visite"):
        if analytics.situation_label_translate(txt, "de") != txt:
            bad.append(f"{txt!r} gewijzigd")
    for empty in ("", None):
        if analytics.situation_label_translate(empty, "de") != empty:
            bad.append(f"leeg {empty!r} gewijzigd")
    if bad:
        _fail("T3 vrije tekst verbatim", "; ".join(bad))
    else:
        _ok("T3 vrije tekst verbatim", "onbekend/leeg ongewijzigd")


def t4_render_de():
    # De tabel wordt client-side uit het tojson-datablok (regel 10) gebouwd; de
    # server-side vertaalde waarden zitten dus in die JSON, niet als <td> in de HTML.
    # We controleren: drietalige chrome (Jinja), vertaalde velden in de data, en
    # dat de oude mtMap/mtLabel-JS weg is.
    html = _render("de", notes="Na sport", meting_type="basismeting")
    ok = ("VERLAUF BASISMESSUNG" in html and "VERLOOP BASISMETING" not in html
          and '"meting_type_label": "Basismessung"' in html
          and '"notes": "Nach Sport"' in html and '"notes": "Na sport"' not in html
          and "mtMap" not in html and "mtLabel" not in html)
    if ok:
        _ok("T4 render DE", "DE-titel + data 'Basismessung'/'Nach Sport' + geen mtMap")
    else:
        _fail("T4 render DE",
              f"de_titel={'VERLAUF BASISMESSUNG' in html} "
              f"label={'\"meting_type_label\": \"Basismessung\"' in html} "
              f"notes={'\"notes\": \"Nach Sport\"' in html} mtMap_weg={'mtMap' not in html}")


def t5_render_en():
    html = _render("en", notes="Na sport", meting_type="basismeting")
    ok = ("BASELINE TREND" in html and "Detail Info Measurements" in html
          and "Back" in html and "Terug" not in html
          and '"meting_type_label": "Baseline"' in html
          and '"notes": "After sport"' in html and "VERLOOP BASISMETING" not in html)
    if ok:
        _ok("T5 render EN", "EN titel/kop/Back + data 'Baseline'/'After sport'")
    else:
        _fail("T5 render EN",
              f"trend={'BASELINE TREND' in html} title={'Detail Info Measurements' in html} "
              f"back={'Back' in html and 'Terug' not in html} "
              f"label={'\"meting_type_label\": \"Baseline\"' in html} "
              f"notes={'\"notes\": \"After sport\"' in html}")


def t6_chip_table_covers_flow():
    # Drift-guard sanity: de chips uit de meetflow moeten in de tabel staan.
    flow_chips_nl = ["Voor activiteit", "Na activiteit", "Ochtend", "Avond",
                     "Na sport", "Na meditatie"]
    known = {c["nl"] for c in analytics.SITUATION_CHIP_LABELS}
    missing = [c for c in flow_chips_nl if c not in known]
    if missing:
        _fail("T6 chip-tabel dekt flow", f"ontbreekt: {missing}")
    else:
        _ok("T6 chip-tabel dekt flow", f"{len(flow_chips_nl)} chips aanwezig")


def main():
    start = time.time()
    t1_meting_type_label()
    t2_chip_translate()
    t3_free_text_verbatim()
    t4_render_de()
    t5_render_en()
    t6_chip_table_covers_flow()
    dt = time.time() - start
    print(f"\ntest_mijn_metingen_i18n: {_passed} passed, {_failed} failed  ({dt:.1f}s)")
    sys.exit(1 if _failed else 0)


if __name__ == "__main__":
    main()
