# I18N_TODO — verdwaalde NL-strings buiten lang-condities

## Status
- **Inventarisatie:** 2026-06-05 (systematische read-only sweep van alle templates excl. `hlm/`, + mailcode).
- **Testbaseline:** `tests/run_all.sh` = **21/1** (alleen B3 faalt, pre-existent).
- **Al gefixt vandaag:**
  - `templates/menu.html` — zone-label render-time vertaald NL/DE/EN (commit **ed64acf**).
  - `templates/mijn_metingen.html` — meting_type + situatie-label + titel-EN (lopende mijn_metingen-sessie; dekt de Tier 1 EN-gap op regel 2/5/7 hieronder).
  - `license_notifications.py:get_lang` — **OPGELOST** (zie onderaan "Afgehandeld"); EN-abonnees kregen NL-vervalmails. Aparte fix + `tests/test_license_notifications_lang.py`.
- **Scope rest:** geplande fixsessie **vóór de Machtfit-livegang**. `hlm/` is een apart spoor (zie `CLEANUP_TODO.md`).

### Twee terugkerende patronen
- **bare NL** — geen enkele lang-conditie → bereikt DE **én** EN.
- **EN-gap** — `{% if lang=='de' %}…{% else %}NL{% endif %}` zonder `{% elif lang=='en' %}` → DE correct, **EN krijgt NL**.

### Aanbevolen aanpak (consistent met vandaag)
Vertaal render-time via één bron. Voor zone-labels/omschrijvingen bestaat al `analytics.py` (RI_ZONES / zone_label / zone_description / meting_type_label). Overweeg een vergelijkbare centrale tabel voor terugkerende UI-fragmenten (knoppen "Terug/Opslaan/Fout", maand-afkortingen) i.p.v. herhaalde inline-ternari.

---

## TIER 1 — Duitse consument, hoge zichtbaarheid (meetflow, resultaten, kenniscentrum)

| Bestand:regel | String | Bereik | Type |
|---|---|---|---|
| `templates/begrippen.html:17` | hele woordenlijst `var terms=[…]` hardcoded NL | DE+EN | bare NL — `termsDE`/`termsEN` (regel 15/16) bestaan maar zijn **dode code**; glossary toont altijd NL. Fix: `var terms = lang3==='de'?termsDE:lang3==='en'?termsEN:termsNL;` |
| `templates/results.html:331` | "Je lichaam registreert meer stress… Klassiek patroon van onderschatting." | DE+EN | bare NL (insight `submitSubjectief()`) |
| `templates/results.html:334` | "Je overschat je belasting. Je ANS is veerkrachtiger…" | DE+EN | bare NL |
| `templates/results.html:337` | "Goede zelfkennis. Je beleving sluit goed aan…" | DE+EN | bare NL |
| `templates/results.html:90` | `JOUW PATROON` | DE+EN | bare NL kop (`#patroonBlok`) |
| `templates/results.html:54-55,57,64,67,75,80` | "Hoe gestrest voel jij je?", "Los van de meting…", "Totaal ontspannen/gestrest", "Bevestigen", "Lichaam vs. Zelfperceptie", "Zelfgevoel", "Verschil" | EN only | EN-gap (zelfinschatting-kaart; DE wel aanwezig) |
| `templates/results.html:2` | `<title>…Resultaten` | EN only | EN-gap (browser-tabtitel; minor) |
| `templates/measure.html:151` | "Slagen" | DE+EN | bare NL (live metric-label) |
| `templates/measure.html:172` | "Klaar!" | DE+EN | bare NL (zustertemplate gate't dit wél) |
| `templates/measure.html:189` | "Kwaliteit" | DE+EN | bare NL (zustertemplate gate't dit wél) |
| `templates/measure.html:190` | "Slagen" | DE+EN | bare NL |
| `templates/sensor_en_meten.html:123` | "Slagen" | DE+EN | bare NL |
| `templates/sensor_en_meten.html:162` | "Slagen" | DE+EN | bare NL |
| `templates/verloop.html:58` | DE-tak toont `'Ontspanning'` i.p.v. "Entspannung" | DE | foute DE-vertaling in ternair |
| `templates/verloop.html:112` | maand-afk. `['jan','feb','mrt',…'mei'…]` | DE+EN | bare NL op grafiek-as |
| `templates/verloop.html:203` | `'gem '` baseline-label | DE+EN | bare NL op grafiek |
| `templates/verloop.html:187` | "Geen metingen in deze periode" | EN only | EN-gap (lege-grafiekmelding) |
| `templates/kenniscentrum.html:596` | "Let op: nagellak verhindert de doorlating van infrarood licht…" | DE+EN | paragraaf valt ná het `{% if/elif/else %}`-blok (eindigt 595) |

---

## TIER 2 — Consument, lagere zichtbaarheid / fout- en randpaden

| Bestand:regel | String | Bereik |
|---|---|---|
| `templates/welcome.html:135` | "Bekijk de video's" | DE+EN (al met TODO-comment regel 133) |
| `templates/welcome.html:139` | "video's sluiten" | DE+EN |
| `templates/koppelen.html:50` | "ACCOUNT AANMAKEN & KOPPELEN" (knop) | DE+EN |
| `templates/koppelen.html:73` | "Vul alle velden in." (JS-validatie) | DE+EN |
| `templates/koppelen.html:77` | "Account aangemaakt en gekoppeld!" (JS-succes) | DE+EN |
| `templates/koppelen.html:63,78,85` | `'Fout'`-fallbacks (alleen bij server-fout) | DE+EN |
| `templates/license.html:272` | "Migreren…" (JS-spinner legacy-migratie) | DE+EN |
| `templates/license.html:280` | "Geactiveerd! / Nieuwe code: / Geldig tot" (JS) | DE+EN |
| `templates/license.html:282-283` | `'Fout'` / "Fout: " (JS) | DE+EN |
| `templates/settings.html:258` | "Verbinden…" (NL/DE-ambigu; fout voor EN) | DE+EN (non-pro pairing) |
| `templates/settings.html:273` | "Code ongeldig" (JS-fallback) | DE+EN (randpad) |
| `templates/settings.html:278` | "Fout:" (JS-catch) | DE+EN (randpad) |
| `templates/eggs.html:21,74,75` | "lichaam"/"gevoel"-labels | DE+EN (easter-egg, lage traffic) |
| `templates/kwadrant.html:107` | `CLIËNTEN` (terug-knop) | DE+EN (alleen pro-client-context) |

---

## TIER 3 — Pro/KK + rapporten (niet de Machtfit-consument, maar DE-markt)

| Bestand:regel | String | Bereik |
|---|---|---|
| `templates/reports/kk_overall.html:63` | `(inactief)` | **DE KKH-PDF** — NL lekt in Duits klantrapport |
| `templates/pro/verloop.html:60` | zone-labels `VEERKRACHTIG/IN BALANS/LICHTE STRESS/STRESS/ZWARE STRESS` | DE+EN pro — **bare NL én oude pré-rebrand-terminologie** (koppelt aan zone-werk; consolideren naar `analytics.zone_label`) |
| `templates/pro/verloop.html:22` | "JOUW PATROON" | DE+EN pro |
| `templates/pro/verloop.html:63` | "Zelfgevoel: " | DE+EN pro |
| `templates/pro/verloop.html:65` | `'Basismeting'`-fallback | DE+EN pro |
| `templates/pro/verloop.html:182` | "Geen metingen in deze periode" | DE+EN pro |
| `templates/pro/client_detail.html:78-79` | gender-dropdown "Vrouw"/"Man" ("divers" is wél gated) | DE+EN pro |
| `templates/pro/menu.html:30` | "Alleen voor Pro-abonnees" (verborgen div) | DE+EN pro |
| `templates/pro/menu.html:6` | `alert('Alleen voor abonnementhouders')` | dode code (onbereikbare conditie) |

---

## TIER 4 — Admin / intern / dev (LAAGSTE prioriteit, alleen intern zichtbaar)

| Bestand | String | Bereik |
|---|---|---|
| `templates/admin/kk_new.html` (regel 1-57) | **volledige pagina NL, geen lang-logica** | alleen admin (Paul) |
| `templates/admin/kk_offices.html` (regel 1-81) | **volledige pagina NL, geen lang-logica** | alleen admin |
| `templates/lab.html` (regel 33-148) | volledig NL ("Niet zichtbaar voor gebruikers") | intern dev |
| `templates/bttest.html:6` | "Test Bluetooth" / "FOUT:" | dev-probe |

---

## E-mails

| Locatie | Status |
|---|---|
| `license_notifications.py:get_lang` | ✅ **AFGEHANDELD** 2026-06-05 — zie onder |
| `weekly_email.py:39-68` | laag risico: `.get(lang, "Beste …")` met NL-default + `lang = u["lang"] or "nl"` (regel 79). Alleen lek bij lege/onbekende `lang`. Meenemen wanneer weekly_email.py de secret-rotatie-sessie krijgt (CLEANUP_TODO). |
| `app.py` send_*/build_* (7 functies) | ✅ correct de/en/nl |
| `app.py:send_kk_activation_email` | DE-only by design (geen NL-lek) |
| `email_templates/*.txt` | DE-only, **nergens gerefereerd** (verweesd) — kandidaat voor opruimen |

### Afgehandeld — `license_notifications.py:get_lang` (2026-06-05)
**Bug:** `get_lang` keek alleen naar het e-maildomein (`'.de' in email` → de, anders nl) en negeerde de opgeslagen `users.language`; kon nooit `'en'` teruggeven. De `main()`-query selecteerde `language` bovendien niet. Gevolg: **EN-abonnees kregen NL-vervalmails** (30/7-dagen + verwijdering), en een DE-keuzer op niet-`.de` adres ook. Live in cron (dagelijks 08:00).
**Fix:** `get_lang` gebruikt nu opgeslagen voorkeur (nl/de/en) > domein-heuristiek (`.endswith('.de')`, geen substring meer → '.dev' lekt niet) > nl; `language` toegevoegd aan de SELECT. Test: `tests/test_license_notifications_lang.py` (6 tests).
**Let op:** `license_notifications.py` bevat nog een **hardcoded SendGrid-key** (regel 12) en blijft daarom untracked tot de secret-rotatie-sessie (CLEANUP_TODO). De fix leeft op schijf; cron draait het schijf-bestand.

---

## Schoon bevonden (geen stray NL)
`base`, `menu` (na fix), `meetkeuze`, `meetkeuze_client`, `voorbereiden`, `sensoren`, `sc_sensor_keuze`, `waarschuwing`, `sc_waarschuwing`, `profile`, `faq`, `over_stress`, `tips`, `beroepen`, `sport_training`, `kenniscentrum_pro`, `privacy`, `macros`, `sc_login`, `verify_2fa`, `wachtwoord_vergeten`, `wachtwoord_reset`, `gratis`, `oude_code`, `legacy_choice`, `upgrade`, `trial_client`, `opzeg_confirm`, `opzeg_bevestiging`, en ~20 `pro/`+`reports/`-templates.
