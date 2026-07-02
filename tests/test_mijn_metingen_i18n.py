"""Tests voor de gedeelde meting-i18n (meting_type_label + situation_label_translate).

Deze SSOT-vertaalfuncties in analytics.py voedden de (verwijderde) /mijn-metingen-
detailpagina én voeden nu de metingen-tabel op /resultaten. Opslag is locale-
onafhankelijk (meting_type-code + vrije tekst); render-time vertaling via één bron.

Historie: de detailpagina /mijn-metingen is geconsolideerd op /resultaten
(Kubios-export + vrije tekst overgezet). De page-render-tests (voorheen T4/T5,
die de verwijderde mijn_metingen.html rendeerden) zijn daarbij vervallen; de
page-onafhankelijke unit-tests hieronder blijven de vertaal-SSOT borgen.

Tests:
    T1 — meting_type_label: 3 codes × NL/DE/EN + onbekende code verbatim
    T2 — chip-vertaling: "Na sport" → "Nach Sport" (de) / "After sport" (en);
         omgekeerd "Nach Sport" → "Na sport" (nl); case-insensitive
    T3 — vrije tekst blijft ongewijzigd ("test", "10 min ademoefening", leeg)
    T6 — chip-tabel dekt de meetflow-chips (drift-guard sanity)

Output: print "test_mijn_metingen_i18n: N passed, M failed (Ts)". Exit 0/1.
"""

import sys
import time

sys.path.insert(0, "/opt/stresschecker")

import analytics

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
    t6_chip_table_covers_flow()
    dt = time.time() - start
    print(f"\ntest_mijn_metingen_i18n: {_passed} passed, {_failed} failed  ({dt:.1f}s)")
    sys.exit(1 if _failed else 0)


if __name__ == "__main__":
    main()
