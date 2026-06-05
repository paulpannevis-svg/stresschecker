# TODO

## Label-consistentie resterende plekken

Na de label-migratie op 2026-04-22 (TOPVORM → VEERKRACHTIG / TOPFORM → WIDERSTANDSFÄHIG / TOP CONDITION/TOP SHAPE → RESILIENT) resteren drie plekken die niet-in-scope waren, maar wel aandacht verdienen:

- `templates/menu.html` regel 31 — `ri_label` bevat `"Veerkrachtig"` voor RI ≥ 8, maar de hele regel is hardcoded NL zonder `{% if lang %}` taal-switch. DE/EN-users zien dus de NL-term.
- `templates/pro/verloop.html` regel 60 — idem: `VEERKRACHTIG` NL-only hardcoded in JS `var lbl=m.ri!=null?(m.ri>=8?'VEERKRACHTIG':...)`. Geen DE/EN-variant.
- `templates/results.html` regel 127 — gebruikt een compleet ander zone-model (`RISICO/STRESS/NIET ONTSPANNEN/VITAAL/ZEER VITAAL`) dan de rest van de app. Verdient een aparte review: is dit legacy, of bewust afwijkend?

## Kleurcoherentie gauge ↔ kwadrant (2026-04-22, na bezinning)

Opgemerkt tijdens stap 3-werk: dezelfde RI-waarde toont een andere kleur in het kwadrant (canvas) dan in de gauge. Canvas-interpolatie mixt kleuren bij zone-grenzen; gauge toont de discrete zone-kleur. Resultaat: cognitieve dissonantie bij de gebruiker.

Drie mogelijke richtingen, volgorde van impact:

- **A) Kleurenvak schuiven (filosofisch)** — herdenk wat elke zone-kleur betekent en pas zone-grenzen of kleurpalet aan zodat de onderliggende boodschap leidend is, niet de technische implementatie.
- **B) Exacte match afdwingen (consistent)** — kwadrant-canvas discreet maken in plaats van geïnterpoleerd; overal precies dezelfde zone-kleur tonen.
- **C) Alleen geel→groen overgang verschuiven (minimaal)** — chirurgische ingreep op één zone-overgang die het meest storend is.

**Beslissing uitgesteld** — Paul wil hier eerst over bezinnen voor een richting gekozen wordt.

## Responsive tabel resultaten.html - mobile check (2026-04-22)

De tabel-layout fix op /resultaten (class `.mt-results` met vaste pixel-breedtes voor numerieke kolommen + bounded max-width voor tekst-kolommen) is gedaan voor desktop (1920px). De `min-width: 900px` uit de `@media (max-width:1024px)`-regel in `static/css/style.css` blijft ongewijzigd — op tablet-portrait en phone scrollt de tabel daardoor horizontaal in `.table-responsive`.

**Te doen**: valideren op tablet-portrait (568-1024px portrait) en phone-portrait (<567px) of de huidige breedtes redelijk renderen of dat per-viewport overrides nodig zijn. Niet urgent tenzij gebruikers daar klachten over melden.

## Slider-defaults — touched-state onderscheid (2026-04-22)

Client-side afdwinging is nu alleen toegepast op dimensie-keuze (`/voorbereiden` + `/waarschuwing`, beide onder `next=basismeting`). Sliders (`subjectief_pre`, `ctx_vitaliteit`) gebruiken default=5 wat niet te onderscheiden is van bewust gekozen 5. Uit diagnose 2026-04-22: 17% van bestaande rijen heeft alle drie defaults. Aparte sessie nodig voor optie B (touched-state tracken) of beslissing om dit als bekende limitatie te accepteren.

## Refactor AI-feedback prompts — shared style-regels extraheren (2026-04-22)

De drie system-prompts (`BASISMETING_SYSTEM_PROMPT`, `BIOFEEDBACK_SYSTEM_PROMPT`, `SITUATIEMETING_SYSTEM_PROMPT`) delen ~85% van hun inhoud (schrijfstijl-eisen, veld-definities, JSON-output-eisen). Bij elke stijl-wijziging moet je drie plaatsen aanpassen — foutgevoelig. Extractie naar een shared `KOMPAS_STYLE_AND_OUTPUT` constant (analoog aan `KOMPAS_INTERPRETATION_GUIDE` die in deze iteratie is toegevoegd) is wenselijk. Niet urgent; doen bij volgende grote feedback-wijziging.

## AI-feedback prompt — observaties voor eventuele toekomstige iteratie (2026-04-22)

- Haiku paraphraseert kwadrant-termen uit `KOMPAS_INTERPRETATION_GUIDE` naar lezer-vriendelijker taal ("gespannen / rustig maar niet flexibel" in plaats van letterlijk "verstarring"). Pragmatisch acceptabel voor consumer-flow. Heroverwegen als Pro-dashboards letterlijke kwadrant-terminologie vereisen — dan kan een expliciete "benoem de kwadrant-term letterlijk"-instructie toegevoegd worden.
- Mogelijk ooit: shared style-regels extraheren uit de drie prompts (nu 85% duplicatie — zie entry hierboven) — voor onderhoud bij volgende grote feedback-wijziging.

## Cache-busting HTML-templates (2026-04-22)

HTML-templates krijgen geen cache-bust versie-suffix terwijl CSS dat wel heeft (`?v=12`). Dit heeft vandaag verwarring veroorzaakt tijdens bug-diagnose — user testte op gecachte versie. Heroverwegen of Flask Cache-Control headers moet sturen op HTML-responses, of versie-suffix ook op templates moet toepassen.

## Openstaand uit sessie 2026-04-22

1. **Acceptatietest scenario's 3-5 nog niet uitgevoerd** door Paul: Pro eigen meting, Pro cliëntmeting, demo-modus. Scenario's 1-2 via consumer-flow zijn wel gevalideerd (start-knop + voorbereiden-instellingen). Voor de drie resterende scenario's moet nog handmatig gecontroleerd worden dat de start-knop-flow, voorbereiden-instellingen en dimensie-verplichting correct werken.
2. **Kolomkop-rename "Wat speelt er" → "Wat er speelt"** (NL/DE/EN) op `/resultaten` was besloten maar werd onderbroken door de dimensie-diagnose. Nog uit te voeren in volgende sessie. Locatie: `templates/results.html` regel 231 (hDim-constant voor NL/DE/EN-headers).

# Openstaande items (stand 23-04-2026 einde middag)

## AI-feedback v3 — restschuld
- Biofeedback-prompt v3-herontwerp (huidig v2, krijgt alleen KOMPAS_COMMON_GUIDE)
- Situatiemeting-prompt v3-herontwerp (idem)
- Beide hebben nog hun oude "max 15/55 woorden" regels die botsen met 200-tekens-regel uit COMMON

## Kwadrant architectonisch
- Hardcoded getRec() verwijderd, feedbackBlock verwijderd — kwadrant is nu puur visueel
- Toekomstige overweging: latentie-shift naar /resultaten is acceptabel, geen actie

## Kleine opruimacties (niet urgent)
- Dead column ctx_ontspanning in sc_measurements.db en sc_pro.db — blijft NULL voor nieuwe rijen
- Legacy cleanup-commit: measure.html + waarschuwing.html verwijderen
- Kolomkop-rename "Wat speelt er" → "Wat er speelt" (NL/DE/EN)
- Kwadrant achtergrond-kleur matcht niet altijd met gauge-zone
- Cosmetisch: recent_basis-serialisatie rendert subjectief_score=None i.p.v. null (pre-M3.2 gedrag)

## Ademritme-bug
- Status: CSS long-hand fix gevonden in huidige code; door CC niet toegepast deze sessie (was al zo)
- Fix-timing: tussen 23-04 13:57 en 14:00
- Openstaand: bevestiging door Steven dat de bug voor hem ook weg is

## Prompt-v3 observatie
- RI=0.1 uitschieter uit 21-04 Pro-bug staat nog in Paul's consumer recent_basis
- Eventuele toekomstige opschoning: die rij uit sc_measurements.db verwijderen

## Demo-rol-isolatie (2026-04-25, AFGEROND vóór ontdekking door prospect)

**Probleem**: oorspronkelijke `is_pro() OR session.get('demo_mode')`-gate liet *elke* demo-gebruiker (ook consumer-demo) Pro-routes binnenkomen. Een "consumer demo"-link voor coach/Krankenkasse/journalist toonde dus Anna/Thomas/Sara — alarmerend en onprofessioneel.

**Fix toegepast**:
- Helper `_is_pro_or_demo_pro()` toegevoegd in `app.py` na `is_pro()` (r.202-209): `is_pro() or (demo_mode and license_type == 'pro')`.
- Alle 22 callsites van `(is_pro() or session.get('demo_mode'))` vervangen door `_is_pro_or_demo_pro()`.
- 8 `_demo = session.get('demo_mode')`-toekenningen vóór DB-OR-DEMO-queries verfijnd naar `... and license_type == 'pro'`.
- 1 inverted gate op r.958 (`/pro` route) ook gemigreerd.

**Geverifieerd via 4×5 matrix + omgekeerde test**:
- A. /demo?mode=pro → ✅ ziet Anna (drie listing-routes)
- B. /menu?demo=1&role=pro → ✅ ziet Anna
- C. /demo?mode=consumer → ✅ 302 redirect op alle Pro-routes (was: zag Anna)
- D. Gewone Pro-login → ✅ ziet Anna niet (eigen pro_key ≠ DEMO)
- Omgekeerd (demo-pro op consumer-routes /, /menu, /resultaten, /voorbereiden, /biofeedback): geen 500-errors, fatsoenlijke redirects of 200.

## Canonical demo-vlag-migratie (uitgesteld, voor BKK-rollout)

Drie parallelle demo-vlaggen bestaan nog: `is_demo`, `demo_mode`, `user_key='DEMO'`. `/demo`-route en `/menu?demo=1` zetten alle drie sinds 2026-04-25.

**Plan**: één canonical vlag (`demo_mode`) houden, `is_demo`-references migreren.

**Risico**:
- 4 templates lezen alleen `is_demo`: `templates/menu.html` (r.55, 57, 59), `templates/pro/menu.html` (r.5, 6, 20, 21, 143, 151), `templates/measure.html` (r.7, 560 via context-var), `templates/sensor_en_meten.html` (r.7, 558 via context-var).
- 3 geïsoleerde Python-checks in `app.py` r.3636, 3646, 3654 — `if session.get("is_demo")` zonder `demo_mode`-fallback.
- Helper-clauses al defensief (`is_demo OR demo_mode` op r.250, 788, 857, 980, 2417) — bij migratie te vereenvoudigen.

**Test-plan**: 4 demo-instappaden × 5 routes-matrix via `app.test_client()` plus rol-isolatie-cellen. Verwacht: alle cellen identiek aan post-2026-04-25-staat.

**Timing**: na eerste demo-uitrol, voor BKK-rollout. Hygiene-traject; rol-isolatie is al productie-klaar.
