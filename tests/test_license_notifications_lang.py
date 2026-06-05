"""Tests voor taalkeuze van de licentie-vervalmails (license_notifications.py).

Achtergrond: `get_lang` keek uitsluitend naar het e-maildomein ('.de' → de,
anders nl) en kon daardoor NOOIT 'en' teruggeven — EN-abonnees kregen NL
vervalmails, en een DE-keuzer op een niet-.de adres ook. De fix gebruikt de
opgeslagen voorkeur (users.language) met de domein-heuristiek enkel als fallback.

Tests:
    T1 — get_lang volgt opgeslagen voorkeur nl/de/en (incl. hoofdletters/spaties)
    T2 — get_lang fallback: geen voorkeur → .de-domein → de; anders nl
    T3 — opgeslagen voorkeur wint van domein-heuristiek (en@.de → en; de@gmail → de)
    T4 — regressie: '.dev'-domein geeft niet langer 'de' (oude substring-bug)
    T5 — vervalmail rendert in de taal van de gebruiker (NL/DE/EN) voor alle drie
         de mailtypes (30-dagen, 7-dagen, verwijdering)
    T6 — end-to-end: user met language='en' → get_lang → Engelse 30-dagen-mail

Output: print "test_license_notifications_lang: N passed, M failed (Ts)". Exit 0/1.
"""

import sys
import time

sys.path.insert(0, "/opt/stresschecker")

import license_notifications as ln

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


# Taalmarkers per mailtype (subject + body) — uniek per taal.
_MARKERS = {
    "warning_email_30": {
        "nl": ("Je StressChecker abonnement verloopt over 30 dagen", "Beste "),
        "de": ("Ihr StressChecker Abonnement läuft in 30 Tagen ab", "Guten Tag "),
        "en": ("Your StressChecker subscription expires in 30 days", "Dear "),
    },
    "warning_email_7": {
        "nl": ("Nog 7 dagen", "Beste "),
        "de": ("Noch 7 Tage", "Guten Tag "),
        "en": ("7 days left", "Dear "),
    },
    "deletion_email": {
        "nl": ("Je StressChecker gegevens zijn verwijderd", "Beste "),
        "de": ("Ihre StressChecker Daten wurden gelöscht", "Guten Tag "),
        "en": ("Your StressChecker data has been deleted", "Dear "),
    },
}


def _build(fn_name, lang):
    if fn_name == "deletion_email":
        return ln.deletion_email("Sam Test", "sam@example.test", lang)
    fn = getattr(ln, fn_name)
    return fn("Sam Test", "sam@example.test", "2026-12-31T00:00:00", lang)


def t1_stored_preference():
    bad = []
    for stored, exp in (("nl", "nl"), ("de", "de"), ("en", "en"),
                        ("EN", "en"), (" de ", "de")):
        got = ln.get_lang({"language": stored, "email": "x@gmail.com"})
        if got != exp:
            bad.append(f"language={stored!r}→{got!r}≠{exp!r}")
    if bad:
        _fail("T1 opgeslagen voorkeur", "; ".join(bad))
    else:
        _ok("T1 opgeslagen voorkeur", "nl/de/en incl. case/space")


def t2_fallback_heuristic():
    bad = []
    checks = [
        ({"language": None, "email": "a@firma.de"}, "de"),
        ({"language": "", "email": "a@gmail.com"}, "nl"),
        ({"email": "a@uni.koeln.de"}, "de"),
        ({"email": "noemail"}, "nl"),
        ({}, "nl"),
    ]
    for user, exp in checks:
        got = ln.get_lang(user)
        if got != exp:
            bad.append(f"{user}→{got!r}≠{exp!r}")
    if bad:
        _fail("T2 fallback-heuristiek", "; ".join(bad))
    else:
        _ok("T2 fallback-heuristiek", "geen voorkeur → .de/nl")


def t3_preference_beats_domain():
    bad = []
    if ln.get_lang({"language": "en", "email": "a@firma.de"}) != "en":
        bad.append("en@.de moet en blijven")
    if ln.get_lang({"language": "de", "email": "a@gmail.com"}) != "de":
        bad.append("de@gmail moet de blijven (echte casus)")
    if bad:
        _fail("T3 voorkeur > domein", "; ".join(bad))
    else:
        _ok("T3 voorkeur > domein", "opgeslagen taal overrulet heuristiek")


def t4_regression_dev_domain():
    # Oude bug: '.de' als substring matchte '.dev' → 'de'. Nu: nl.
    got = ln.get_lang({"email": "dev@startup.dev"})
    if got == "nl":
        _ok("T4 regressie '.dev'", "startup.dev → nl (niet de)")
    else:
        _fail("T4 regressie '.dev'", f"startup.dev → {got!r} (verwacht nl)")


def t5_mail_renders_in_lang():
    bad = []
    for fn_name, per_lang in _MARKERS.items():
        for lang, (subj_marker, body_marker) in per_lang.items():
            subject, body = _build(fn_name, lang)
            if subj_marker not in subject:
                bad.append(f"{fn_name}/{lang}: subject mist {subj_marker!r}")
            if body_marker not in body:
                bad.append(f"{fn_name}/{lang}: body mist {body_marker!r}")
            # kruiscontrole: een andere taal mag niet lekken in de body-aanhef
            for other_lang, (_, other_body) in per_lang.items():
                if other_lang != lang and other_body != body_marker and other_body in body:
                    bad.append(f"{fn_name}/{lang}: lekt {other_lang}-aanhef {other_body!r}")
    if bad:
        _fail("T5 mail per taal", "; ".join(bad[:5]))
    else:
        _ok("T5 mail per taal", "3 mailtypes × NL/DE/EN correct")


def t6_end_to_end_en():
    user = {"language": "en", "email": "sam@example.com", "display_name": "Sam Test"}
    lang = ln.get_lang(user)
    subject, body = _build("warning_email_30", lang)
    if lang == "en" and "Your StressChecker subscription expires in 30 days" in subject \
            and "Dear Sam" in body:
        _ok("T6 end-to-end EN", "language=en → Engelse 30-dagen-mail")
    else:
        _fail("T6 end-to-end EN", f"lang={lang!r}; subject={subject[:40]!r}")


def main():
    start = time.time()
    t1_stored_preference()
    t2_fallback_heuristic()
    t3_preference_beats_domain()
    t4_regression_dev_domain()
    t5_mail_renders_in_lang()
    t6_end_to_end_en()
    dt = time.time() - start
    print(f"\ntest_license_notifications_lang: {_passed} passed, {_failed} failed  ({dt:.1f}s)")
    sys.exit(1 if _failed else 0)


if __name__ == "__main__":
    main()
