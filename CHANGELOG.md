# StressChecker — Recente wijzigingen

## 2026-06-05 — Dashboard-welkomstkaart: zone-label render-time vertaald (NL/DE/EN, rebrand)

De kaart "Letzte Basismessung" op het consumer-dashboard (`templates/menu.html`)
toonde hardcoded Nederlands + pré-rebrand terminologie ("Lichte Stress" / "Er is
lichte stress aanwezig") ongeacht de actieve locale — een gemist code-pad uit de
mensentaal-rebrand van 25 april. Steven P (DE) zag NL + oude woorden.

### Root cause
`menu.html:31-32` berekende label én omschrijving zelf uit het RI-getal met twee
hardcoded `{% set %}`-regels, zónder `lang`-conditie en in de oude stress-familie.
De `/menu`-route geeft alleen het **numerieke** RI door (`SELECT ri,bpm,hrv_pct`),
dus de opslag was al locale-onafhankelijk — er is nergens labeltekst opgeslagen.
Conclusie: **geen DB-migratie nodig**; historische metingen renderen automatisch
correct zodra de kaart render-time vertaalt.

### Fix (single source of truth)
- `analytics.py` — nieuwe `zone_description(zone_key, lang)` + `ZONE_DESCRIPTIONS`
  (NL/DE/EN, rebrand-consistent belast-familie; DE in Sie-vorm conform consumer-conventie).
  Bestaande `RI_ZONES`/`zone_for_ri`/`zone_label` waren al de canonieke bron.
- `app.py` — twee Jinja-globals naast `zone_label_jinja`: `zone_key_jinja(ri)` en
  `zone_desc_jinja(zone_key, lang)`.
- `templates/menu.html:31-33` — de twee hardcoded regels vervangen door
  `zone_key_jinja` → `zone_label_jinja`/`zone_desc_jinja` (kleur-logica ongewijzigd).

### Scope (bewust beperkt)
Alleen de consumer-dashboardkaart (`menu.html`). `templates/kwadrant.html` was al
correct (rebrand, 3 talen). `templates/hlm/kwadrant.html` (regel 107 + 149) heeft
nog oude terminologie maar is een apart HLM-spoor in aparte klantcontext — genoteerd
als open punt in `CLEANUP_TODO.md`, op te pakken bij HLM-activering.

### Verificatie
- `python3 -m py_compile app.py analytics.py` — schoon
- `tests/test_menu_zone_label.py` (nieuw, 5 tests) — **5/5 groen**: analytics-bron
  5 zones × 3 talen, DE-kaart rebrand-term, cross-locale (meting onder NL → correct
  onder DE/EN want numerieke opslag), zone-grenzen DE, regressie oude termen weg.
- `tests/run_all.sh` — **21/1** (alleen B3, pre-existent), geen regressie.
- `kill -HUP` gunicorn-master 1523232 → workers gerecycled; `GET /menu` → 302.

### Geraakte bestanden
- `analytics.py`, `app.py`, `templates/menu.html`
- `tests/test_menu_zone_label.py` (nieuw)
- `CLEANUP_TODO.md` (HLM open punt), `CHANGELOG.md` (deze entry)

Pre-fix backup: `/opt/backups/{menu.html,analytics.py,app.py}.20260605-1548`.

## 2026-06-05 — Test-fixture: volledig cliëntprofiel voor 999/998

`tests/lib/setup.py` gaf de testcliënten 999/998 alleen id/pro_key/name/client_code.
De verplicht-profiel-gate in `select_client` (RMSSD-workstream: leeftijd/geslacht
vereist vóór een cliëntmeting) blokkeerde daardoor de meting → niets in
`client_metingen` → A2/A4/A5 rood. Geen productiebug: echte Pro-cliënten met
volledig profiel landen wél (read-only geverifieerd: laatste echte rij id=377,
client 121, 2026-06-01).

- Fixtures krijgen nu `birth_year`/`gender`/`profile_completed=1` (999=1980/male,
  998=1975/female) zodat ze de gate passeren. De reuse-tak ververst deze velden
  ook, zodat een stale incomplete rij uit een oudere run alsnog slaagt.
- Alleen `tests/lib/setup.py` — geen productiecode.
- `run_all.sh`: A 6/6, C 8/8, D 4/4 groen. Resteert B3 (HRV%=146 vs 124, bekende
  `hrv.js`-vs-`references.json`-normtabel-divergentie, tot de RMSSD-consolidatiesessie).

## 2026-06-05 — Widerruf-instemming op activeringspagina (/licentie)

Juridisch verval van het herroepingsrecht voor de digitale dienst (§ 356 Abs. 5
BGB / art. 6:230p BW) wordt nu kanaal-onafhankelijk vastgelegd bij elke echte
licentie-activering. Sluit aan op de nieuwe AGB § 12 (Stand 5 juni 2026).
Pre-fix backup: `/opt/backups/*.20260605-0912`.

### Tweede checkbox + validatie (`templates/license.html`)
- Nieuwe gele box `widerruf_consent` direct onder de gezondheidsdata-box, niet
  voorgevinkt, NL/DE/EN (u-vorm NL). Beide boxen tonen alleen in de
  activeringstab ("Neuer Nutzer"); de login-tab (/login) activeert niets en
  toont geen checkbox.
- `validateActivation()`: knop blijft actief; bij submit zonder vinkje een
  inline foutmelding bij de betreffende checkbox (3 talen). Server-side gate in
  `/activeer` is de autoritaire controle (beide verplicht voor activering).
- Typo-fix: DE `Datenschutzerklaerung` → `Datenschutzerklärung`, nu hyperlink
  naar https://lifestylemonitors.de/datenschutz-dsvgo/ (target=_blank). NL/EN
  blijven bewust naar interne `/privacy` (DSGVO-pagina is Duitstalig).

### Consent-logging (`app.py` + nieuwe tabel)
- Nieuwe tabel `consent_log` in `saas_licenses.db` (id, email, license_code,
  consent_type, text_version, locale, created_at). Bewaartermijn: niet opruimen
  (juridisch bewijs).
- Tekstversie-constanten `CONSENT_TEXT_VERSIONS` (widerruf/gezondheidsdata ×
  nl/de/en, suffix `-v1-20260605`). Latere tekstwijziging = nieuwe version-string.
- Bij succesvolle activering twee rijen (één per checkbox) in dezelfde transactie
  als de activerings-UPDATE: regulier in `verify_2fa` (status available→activated),
  marketing/eval in de bind-transactie van `/activeer`. `created_at` = tijdstip
  van aanvinken (vastgelegd bij de POST naar `/activeer`, meegedragen via sessie).
  Re-login met reeds geactiveerde code = geen activering → geen rij.

### Bevestigingsmail op duurzame drager (§ 312f BGB)
- Nieuwe `send_activation_confirmation_email` + pure builder
  `build_activation_confirmation_body` (testbaar). Verstuurd ná succesvolle
  activering (na 2FA), alleen bij echte activeringen, met de consent-alinea +
  tijdstip van instemming. Er bestond nog géén activeringsbevestiging — dit is
  nieuw (de enige mails waren 2FA-code en wachtwoord-reset).

### Tests
- `tests/test_consent_widerruf.py` (categorie D, 4/4 groen), gewired in
  `run_all.sh`: D1 zonder widerruf geblokkeerd (geen rij), D2 beide → activated +
  2 rijen (juiste text_version/locale/created_at) + mail, D3 consent-alinea in 3
  talen, D4 regressie login zonder checkbox/zonder rij. Eigen fixture-licentie,
  SendGrid gemockt; productie-fixtures (o.a. id=25/26) onaangeroerd.

### Verificatie
- `py_compile app.py` schoon; Jinja-render `/licentie` NL/DE/EN OK.
- `kill -HUP` graceful reload (workers 1538591/1538592); live `/licentie` (DE)
  toont checkbox + umlaut-fix + DSGVO-link + validatie.
- `run_all.sh`: categorie C 8/8 + D 4/4 groen. **Pre-existent en niet door deze
  wijziging veroorzaakt:** A2/A4/A5 (pro-cliëntmeting-routing, live server) en B3
  (HRV%=146 vs 124, `hrv.js` vs `references.json` — RMSSD-herberekening-workstream).
  Beide subsystemen liggen buiten deze diff.

### Buiten scope (zoals opgedragen)
- 2FA-codes uit journalctl (apart ticket, vóór Machtfit-livegang).
- AGB-pagina op lifestylemonitors.de (via WordPress).

## 2026-05-25 — Methodische rapport-tekst herzien (Sessie B.5 / Pass 3)

Voor de KKH-propositie moet de naam **Verveen** uit alle klantzichtbare rapport-tekst verdwijnen (eigennaam wekt de indruk dat essentiële knowhow uit het bedrijf weg is). Vervangende tekst behoudt de wetenschappelijke onderbouwing via de gehanteerde **methode**: HRV/RMSSD per Task Force ESC (1996), Kubios-standaard voor artefactcorrectie, leeftijd/geslacht-genormaliseerde populatiereferenties.

### Onderzoek vooraf (geen wijzigingen)

Code-verificatie van wat de Relax Index feitelijk doet, vóór de tekst werd herschreven:

- **Meting-duur**: Basismeting + Situatiemeting = hard 90 s (`app.py:1513`, DB-default in `app.py:158, 200`). Biofeedback = 180–1800 s, default 600 s (`app.py:1510`).
- **Input**: alleen RR-intervallen via Bluetooth-borstsensor of USB-vingersensor. BPM/RMSSD/HRV% allemaal afgeleid (`sensor_en_meten.html:735–740`).
- **Voorbewerking**: eerste 15 RR-intervallen weg (warm-up), hard-clamp 300–2000 ms (`hrv.js:20`).
- **Filter**: Kubios "Strong+"-methode met adaptieve mediaan-drempel (`hrv.js:12–71`, comment regel 28). 100 ms drempel, geschaald naar `meanRR/1000`. Ongeldige samples → lineair geïnterpoleerd, niet weggegooid. Geen vast percentage.
- **RMSSD**: `sqrt(mean(ΔRR²)) / 2.5` (sensor-correctie, `hrv.js:73`).
- **HRV%**: `RMSSD / norm[age,gender] × 100`, clamp 0–220. Norm-tabel `N` (13 leeftijdsgroepen × man/vrouw, `hrv.js:8`).
- **RI**: 2D-lookup in tabel `T` (16×42, `hrv.js:7`) op BPM-bucket × HRV%-bucket. **Stap-functie**, geen bilineaire interpolatie.
- **Geslacht-paden** (`hrv.js:75`): `female`→f, `divers`/`unspecified`→(m+f)/2, overige (incl. leeg)→m.

Referentie-meting in `tests/lib/references.json` bevestigt: BPM=65, RMSSD=34.67 ms, HRV%=124, RI=7.7 (age=50, male).

### Tekstuele wijziging

`templates/reports/base.html:217` — één regel met drie inline-taalvarianten (NL/DE/EN ternair via `lang`). Vervangt de hele "Methodik & Erläuterung" / "Methodische toelichting" / "Methodology" eerste-paragraaf. Geen wijziging aan de "Zonen:" / "Zones:"-regel daarna of aan de anonimiteits-disclaimer.

**Definitieve formulering, drie talen:**

- **NL**: "De Relax Index (RI) is een score van 0 tot 10, berekend uit een meting van 90 seconden waarbij de gemiddelde hartslag en de hartritmevariabiliteit (HRV/RMSSD) van het autonome zenuwstelsel worden vastgesteld. Artefactcorrectie volgens de Kubios-standaard zorgt voor robuuste meetwaarden. De score wordt genormaliseerd naar leeftijd en geslacht op basis van gepubliceerde populatiestudies, conform de HRV-richtlijnen van de Task Force ESC (1996)."
- **DE**: "Der Relax Index (RI) ist ein Wert zwischen 0 und 10, berechnet aus einer 90-sekündigen Messung von durchschnittlicher Herzfrequenz und Herzratenvariabilität (HRV/RMSSD) des autonomen Nervensystems. Eine Artefaktkorrektur nach Kubios-Standard sorgt für robuste Messwerte. Die Normierung erfolgt nach Alter und Geschlecht auf Grundlage publizierter Populationsstudien, gemäß den HRV-Richtlinien der Task Force ESC (1996)."
- **EN**: "The Relax Index (RI) is a score from 0 to 10, calculated from a 90-second measurement of average heart rate and heart rate variability (HRV/RMSSD) of the autonomic nervous system. Artifact correction according to the Kubios standard ensures robust measurement values. Normalization is performed by age and gender based on published population studies, in accordance with the HRV guidelines of the Task Force ESC (1996)."

### Scope (bewust beperkt)

Alleen rapport-templates (`templates/reports/`). NIET aangeraakt — bewust buiten scope:

- `templates/kenniscentrum.html`, `templates/kenniscentrum_pro.html`, `templates/hlm/kenniscentrum.html`, `templates/hlm/meting_src.html` — kennis-pagina's en HLM-blueprint. Verveen-vermelding daar blijft staan (verschillende klant-context, separate decision).
- Code-comments en `gen_context.py:65` — interne documentatie, niet klantzichtbaar.

### Verificatie

- `python3 -m py_compile app.py` — schoon
- `systemctl restart stresschecker` — clean restart (workers 1410225/1410226 booten zonder warnings)
- 5 Pass-3-PDFs gegenereerd in `/opt/stresschecker/reports/SC-KK-44F6-14A3/pass3/`:
  - `kk_overall_nl.pdf` (50 520 B), `kk_overall_de.pdf` (51 043 B), `kk_office_hamburg_de.pdf` (49 585 B), `pro_portfolio_de.pdf` (50 437 B), `pro_client_anna_de.pdf` (46 952 B)
- Verveen-check (via `pypdf`-tekstextractie; `pdftotext` ontbreekt op deze VPS): **0 hits in alle 5 PDFs** — `grep -l "Verveen" pass3/*.pdf` equivalent leeg.
- Visuele controle van Methodik-sectie in `kk_overall_de.pdf` + `kk_overall_nl.pdf`: definitieve tekst correct gerenderd (Kubios-Standard / Kubios-standaard + Task Force ESC (1996) zichtbaar; pypdf-letter-spacing artefact "T ask Force" is alleen tekstextractie, niet visueel).
- `tests/run_all.sh` — **18/18 groen** (cat A 6/6, B 4/4, C 8/8). Pass 1 + 2 + B.4 intact, geen regressie.

### Open punten

- **Verveen-vermelding intern blijft staan** in code-comments (`gen_context.py:65`) en kennis-pagina-templates voor methodologische traceerbaarheid. Niet klantzichtbaar in KKH-rapporten. Aparte beslissing nodig of de kennis-pagina's later ook herzien moeten worden (consumer-context, andere persona).

### Geraakte bestanden

- `templates/reports/base.html` — één regel vervangen (drie talen inline)
- `CHANGELOG.md` — deze entry
- `/opt/stresschecker/reports/SC-KK-44F6-14A3/pass3/*.pdf` — 5 PDFs hergegenereerd (niet in git — runtime-output)

Pre-fix backup: `/opt/backups/*.20260525-1034`.

## 2026-05-25 — KKH Datenschutz-hardening (Sessie B.4)

Twee Datenschutz-gaten dichten die door `schmidt_bijlage_brondoc.md` waren geïdentificeerd, vóór de KKH-mail. Geen scope-creep: alleen `app.py` (+ één hidden-input in `pro/locaties_import_preview.html` voor filename-doorgift). Pre-fix backup: `/opt/backups/*.20260525-0809`.

### Fix 1 — Sessie-idle-timeout (30 minuten)

`app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)` + nieuwe `before_request`-hook `_enforce_session_idle_timeout`. Hook draait alleen voor authenticated sessies (`session.get('license_valid')`), skipt de exempt-prefixen (`/static/`, `/login`, `/licentie`, `/verify`, `/wachtwoord-*`, `/logout`, `/api/licentie/`, `/api/pairing/`), refresht `_last_activity` bij elke hit, en clearet de sessie + redirect naar `/login?timeout=1&lang=…` zodra `now - _last_activity > 1800s`. JSON/API-requests krijgen `401 {error: session_expired}` ipv HTML-redirect.

Login-completion (`verify_2fa`-success-pad) zet expliciet `session.permanent = True` + `session['_last_activity'] = time.time()`. Hook initialiseert deze velden ook bij eerste hit (defensive fallback voor login-paden die buiten `verify_2fa` om license_valid zetten — bv. `demo()`).

`sc_login` rendert NL/DE/EN-flash uit `?timeout=1` via bestaande `error`-mechaniek (geen template-edit nodig).

2FA-expiry (`session['2fa_expires']`, 10 min) blijft volledig onafhankelijk — de hook raakt het verify-pad niet aan.

### Fix 2 — KK-CRUD audit-logging

Nieuwe helper `_log_kk_action(license_code, action, details)` (`app.py` direct vóór `_parse_kk_csv`). INSERT in `saas_licenses.db.activation_log` met `license_key`, `product='sc'`, `action`, `ip_address` (uit `request.remote_addr`), `user_agent` (uit `request.headers.get('User-Agent')[:200]` — `request.user_agent.string` gaf lege string op deze Werkzeug-versie), `details`. Best-effort: bij INSERT-fout logging.warning, geen HTTP-fail.

Aanroep NA succesvolle DB-write in zes KK-routes:

| Route | action | details-format |
|---|---|---|
| `POST /pro/locaties/toevoegen` | `kk_office_create` | `name=… region=…` |
| `POST /pro/locaties/<id>/bewerken` | `kk_office_update` | `id=… old_name=… new_name=… old_region=… new_region=…` |
| `POST /pro/locaties/<id>/deactiveren` | `kk_office_deactivate` | `id=… name=…` |
| `POST /pro/locaties/<id>/reactiveren` | `kk_office_reactivate` | `id=… name=…` |
| `POST /pro/locaties/import` (confirm) | `kk_office_import` | `imported=N dups=X total_rows=Y filename=…` |
| `POST /pro/locatie` (kantoor-keuze) | `kk_session_office_select` | `office_name=…` |

Filename-doorgift import: `pro/locaties_import_preview.html` kreeg één extra `<input type="hidden" name="csv_filename">` zodat de confirm-POST de originele bestandsnaam meekrijgt voor het log-record. Preview-render geeft `csv_filename` mee aan template.

`bewerken` neemt nu ook `region` mee in de SELECT-pre-read zodat oude waarden voor het log beschikbaar zijn (was eerder alleen `office_name`).

### Verificatie

- `python3 -m py_compile app.py` — schoon
- `systemctl restart stresschecker` — clean restart, workers booten zonder warnings (journalctl)
- `tests/run_all.sh` — 18/18 groen, geen regressie (cat A 6/6, B 4/4, C 8/8, in 2s)
- `tests/test_session_timeout.py` — **5/5 groen** in 0.1s:
  - T1 active_under_30min, T2 expired_after_30min, T3 activity_refreshes, T4 login_endpoint_excluded, T5 2fa_flow_independent
- `tests/test_kk_audit_log.py` — **6/6 groen** in 0.1s:
  - T1 create_logs_action, T2 update_logs_old_and_new, T3 deactivate_logs, T4 import_logs_with_counts, T5 failed_create_no_log, T6 log_includes_ip_and_ua
- Smoke: `GET /login?timeout=1` rendert NL-flash "Sessie verlopen na 30 minuten inactiviteit, log opnieuw in." correct.

Tests gebruiken eigen mint-helper (Flask `SecureCookieSessionInterface` met SC_SECRET_KEY uit gunicorn-proces), fictieve `license_code='__TEST_TIMEOUT_KK__'`/`'__TEST_AUDIT_KK__'`, en cleanup-block dat eigen rijen verwijdert uit `krankenkasse_offices` + `activation_log`. Geen impact op productie-fixtures (SC-KK-44F6-14A3 onaangeroerd).

### Niet gedaan (manueel-only)

- Live KKH-Test-login + kantoor toevoegen — kan niet zonder echte 2FA-mail; codepad volledig gedekt door T1–T6.
- 31-min wait op /pro/locaties + refresh — niet praktisch in geautomatiseerde test, gedekt door T2 met geforceerde `_last_activity`-timestamp.

### B.1-open-issues gesloten

- **Sessie-timeout (Datenschutz-gap uit brondocument)** — gesloten in Fix 1.
- **B.1 #4 (CRUD-audit-logging ontbreekt)** — gesloten in Fix 2.

### Nieuwe open issues

- **Per-medewerker-login** — KK-account blijft één gedeelde sessie; audit-log toont licentie + IP + UA maar niet welke medewerker. Vereist sub-account-model onder hoofdlicentie (DB-migratie + login-flow + beheer-UI). Geschat **12–20 uur**, alleen oppakken als KKH dit contractueel eist.
- **2FA-code in journalctl plaintext** — bestaand probleem (`logging.warning(f"2FA CODE: ...")` op regels ~745, 768, 1037). Niet in B.4-scope; apart project. Datenschutz-impact: 2FA-codes in systemd-journal zichtbaar voor root+adm.

### Geraakte bestanden

- `app.py` — top-imports (`time`, `timedelta`), `PERMANENT_SESSION_LIFETIME`, `_TIMEOUT_EXEMPT_PREFIXES`, `_enforce_session_idle_timeout` hook, `_log_kk_action` helper, 6 audit-aanroepen, `sc_login` flash-handling, `verify_2fa` session-init, `bewerken`-SELECT-uitbreiding, `import`-filename-doorgift
- `templates/pro/locaties_import_preview.html` — één hidden input `csv_filename`
- `tests/test_session_timeout.py` (nieuw, 5 tests)
- `tests/test_kk_audit_log.py` (nieuw, 6 tests)
- `CHANGELOG.md` — deze entry

## 2026-05-25 — KKH-rapport visuele finishing Pass 2 (Sessie B.3.2)

Pass 2 = visuele polish bovenop Pass 1-data-fixes. Pre-Pass2 backup: `/opt/backups/*.20260525-0656`. PDFs voor finale review in `/opt/stresschecker/reports/SC-KK-44F6-14A3/pass2/`.

### Files aangepast

- `templates/reports/base.html` — `#pageheader` toont nu Lifestyle Monitors-logo (`static/img/sc_logo_full.png`, 27 KB, 1000×220, hoogte 1cm) links, report-tag in midden, lege `.cobrand-slot` rechts (min 2.5cm gereserveerd voor KK-co-branding). Nieuwe CSS-klassen voor stacked-bar Zonenverteilung: `.zone-bar`, `.zone-seg`, `.zone-bg-{zone}`, `.zone-legend`, `.zone-swatch`.
- `templates/reports/_macros.html` (nieuw) — `zone_stacked_bar(distribution, total, zone_order, zone_label, lang)`-macro. Bar-segmenten op proportionele width, %-label in segment alleen bij >5%. Legenda toont alle 5 zones zonder onderdrukking bij n=0.
- `templates/reports/kk_overall.html` + `pro_portfolio.html` + `kk_office.html` — Zonenverteilung-tabel vervangen door stacked-bar-macro. Klientenbericht (`pro_client.html`) blijft tabel (spec: 1-cliënt-view).
- `kk_overall.html` — kopjes "Pro Standort"/"Per kantoor" → "Standortübersicht"/"Kantooroverzicht"/"Locations overview". "Pro Region"/"Per regio" → "Regionalübersicht"/"Regio-overzicht"/"Regional overview". M/V-kolommen samengevoegd tot één compacte "M / W / D" (DE) / "M / V / D" (NL) / "M / F / D" (EN) kolom met waarden zoals "3 / 2 / 1" — Divers nu zichtbaar in overzicht (was eerder onzichtbaar).
- `kk_office.html` — derde KPI-block: "M / V" → "M / W / D" (DE) / "M / V / D" (NL) / "M / F / D" (EN); waarde "3 / 2 / 1".
- `pro_portfolio.html` — "Pro Klient"/"Per cliënt" kopje → "Klientenübersicht"/"Cliëntenoverzicht"/"Clients overview". Geslacht-kolom logic gefixt: female→W (DE)/V (NL)/F (EN); divers→D in alle talen; male→M.

### Logo-keuze

`sc_logo_full.png` (1000×220 PNG, 26.9 KB). SVG-variant (`sc_logo_full.svg`) afgewezen wegens malformed `@keyframes` (lines 7-19) en `var(--red)`-CSS-vars die WeasyPrint niet resolveert. PNG geeft consistente rendering ongeacht renderer.

### Stacked-bar kleuren (uit spec, consistent met app-palet)

- `zwaar_belast`: #c0392b · `belast`: #e67e22 · `licht_belast`: #f1c40f · `in_balans`: #6fcf7a · `veerkrachtig`: #27ae60

### Bestandsgrootte

Pass 1 PDFs: 18-21 KB. Pass 2 PDFs: 46-50 KB (logo embedded éénmalig in PDF-resource-pool). Onderkant van spec-verwachting (80-300 KB), klopt: WeasyPrint dedupliceert images. Geen impact op kwaliteit.

### Eindverificatie checklist (pass2/)

- [x] Logo zichtbaar bovenaan elke pagina van alle 5 rapporten
- [x] Stacked-bar Zonenverteilung: KK-overall, Portfolio, Standort
- [x] Klientenbericht blijft tabel (regressie ok)
- [x] DE: W i.p.v. V; Divers (D) zichtbaar in Standortübersicht + KPI + Klientenübersicht
- [x] Kopjes: Klientenübersicht / Standortübersicht (DE), Kantooroverzicht / Cliëntenoverzicht (NL)
- [x] Pass 1 data-regressie: 18 metingen, RI 4.59, F2-M3-D1, geen 1970-01-01
- [x] `tests/run_all.sh`: 18/18 groen

### Niet gedaan (uit spec scope)

- **Mobiel-rendering check via Chrome DevTools:** kan niet vanuit deze sessie (geen browser-toegang). PDFs zijn A4-formaat met print-CSS — natuurlijke mobiel-view is "pinch & zoom" op renderer-niveau, niet template-niveau. Verzoek aan Paul: open één PDF op iPhone-viewport en bevestig leesbaarheid; eventuele aanpassingen volgen in volgende sessie als nodig.

### Open punten — meegenomen uit Pass 1

- Tie-break voor modale zone-per-klant (Anna in 'zwaar' i.p.v. 'licht'); beslissing volgt na Schmidt-feedback. Neiging: meest recente meting.
- KKH-Test-1779642625 fixture toevoegen aan `TEST_ACCOUNTS.md` na groen licht.

## 2026-05-25 — KKH-rapport data-fixes Pass 1 (Sessie B.3)

Drie data-aggregatie-bugs gefixt in de KK/Pro-rapport-laag, vóór Schmidt-demo dinsdag. Pre-fix backup: `/opt/backups/*.20260525-0622`. PDFs voor Paul's review in `/opt/stresschecker/reports/SC-KK-44F6-14A3/pass1/`.

### Files aangepast
- `analytics.py:124-188` — `_aggregate_rows()` levert nu zowel meting- als cliënt-niveau aggregaties. `_empty_aggregate()` uitgebreid met `unique_clients`, `gender_distribution_client`, `age_categories_client`, `zone_distribution_client`. Zone-per-klant gebruikt MODALE zone over al hun metingen (max-count met tie-break op `ZONE_KEYS`-volgorde zwaar→vital).
- `app.py:2219-2241` — `_render_report_async` detecteert `period_start.startswith('1970-01-01')` en vervangt door taal-afhankelijk label ("Alle metingen" / "Alle Messungen" / "All measurements"). Andere periodes (maand/kwartaal/jaar) blijven datum-formaat.
- `templates/reports/kk_overall.html` — Geslacht-, Leeftijd- en Zoneverdeling-tabellen lezen nu `*_distribution_client` met `unique_clients` als noemer. Per-office-tabel (M/V-counts) blijft per-meting (telt verbruik per kantoor).
- `templates/reports/pro_portfolio.html` — idem voor Geslacht- en Zone-tabellen. "(alle Klienten)" notitie achter Zonenverteilung verwijderd; titel nu enkel "Zonenverteilung".
- `scripts/seed_kk_test.py` (nieuw) — idempotente fixture voor 6 SMOKE_-cliënten met 18 metingen, 1 per kantoor, gem RI 4.59.
- `scripts/run_pass1_reports.py` (nieuw) — synchrone PDF-generator-helper voor verificatie (omzeilt UI/2FA/threading/mailbezorging).

### Root cause BUG 1 (NL toont 0 metingen waar DE 18 toont)

Spec-hypothese (vertaalde zone-namen in WHERE/GROUP BY) **niet bevestigd**. `analytics.aggregate_period` neemt geen `lang`-parameter en gebruikt alleen interne keys (`zwaar_belast`/`belast`/.../`veerkrachtig`, `M`/`V`/`D`/`unknown`, `<30`/.../`>60`/`unknown`). Geen taal-afhankelijke SQL.

Wat wél gebeurde: f3f3793 (DE, 20:41:10) en d2126979 (NL, 20:42:52) van 24-05 hadden verschillende `params_json` (`kwartaal` resp. `alles`) en — bevestigd door backup-snapshots `sc_pro.db.20260524-{1939,2006,2031}` — de KK-pro_key had op het moment van NL-run géén rij in `client_metingen`. Tijdens DE-run waren de 18 SMOKE_-metingen er nog (of via test-injectie aanwezig); ze waren verdwenen tegen NL-run. De NL-uitkomst was dus correct gegeven de DB-state op dat moment.

Verificatie met verse seed (`scripts/seed_kk_test.py`): NL- en DE-kk_overall produceren **identieke kerncijfers** (18 metingen, gem. RI 4.59, F2/M3/D1, age <30:1/30-45:2/45-60:1/>60:2, zone-per-klant zwaar:2 belast:1 licht:3).

### Aggregatie-keuze Zone-per-klant

Modale zone over al hun metingen. Bij gelijkspel (bv. SMOKE_Anna [balans, zwaar, belast] elk 1×) valt de eerste zone in `ZONE_KEYS`-volgorde (zwaar→belast→licht→balans→vital). Toegelicht in code-comment `analytics.py:_aggregate_rows`. Alternatief 'meest recente meting' afgewezen omdat één outlier dan een klant's zone bepaalt voor het hele rapport.

Consistentie: zelfde modale-methode in KK-overall en Portfolio-Bericht. Standort-Bericht is niet aangepast (per-office is intrinsiek per-meting; spec adresseerde dit niet expliciet). Klientenbericht (`pro_client.html`) blijft per-meting (één cliënt — verdelingstabel telt zijn eigen metingen, niet zinvol om als 1 modale zone weer te geven).

### Eindverificatie checklist (pass1/)

- [x] NL en DE KK-overall identieke kerncijfers (18 metingen, RI 4.59)
- [x] Som Geslechtsverteilung Portfolio = 6 (F2+M3+D1)
- [x] Som Zonenverteilung Portfolio = 6 (zwaar2+belast1+licht3+balans0+vital0)
- [x] Klientenbericht SMOKE_Anna: 3 metingen, RI 4.0, verloop 14/15/16-mei
- [x] Geen "1970-01-01" in headers (alle 5 PDFs tonen "Alle metingen"/"Alle Messungen")
- [x] Regressietests: `tests/run_all.sh` 18/18 groen

### Open punten

- KKH-Test-1779642625 fixture nog niet in `TEST_ACCOUNTS.md` — toevoegen na Paul's groen licht.
- Pass 2 (visueel: logo, kleuren, charts) wacht op Paul's review van pass1-PDFs.

### Open beslissingen

- **Tie-break voor modale zone-per-klant.** Huidige implementatie (`analytics.py:_aggregate_rows`) kiest bij gelijkspel de eerste zone in `ZONE_KEYS`-volgorde (zwaar→belast→licht→balans→vital). Bijwerking: SMOKE_Anna's metingen [balans, zwaar, belast] (elk 1×) → modal valt op 'zwaar', terwijl haar gem. RI = 4.0 'licht_belast' is. Niet kritiek voor demo (1 cliënt op 6). Beslissing volgt na Schmidt-feedback. Paul's neiging: tie-break = **meest recente meting** (gebruikt de laatste zone bij gelijke counts). Eventuele alternatieven: zone-dichtbij-avg-RI, of zone uit avg-RI direct.

## 2026-05-24 — Rapportage-laag Krankenkasse + Pro (Sessie B.2)

Vier PDF-rapport-types via WeasyPrint, async generatie via threading, mail-bezorging met download-link. Hergebruikbare `analytics.py`-module voor aggregatie. Audit-trail in `report_jobs`-tabel.

### System dependencies
- `pip install --break-system-packages weasyprint` (v68.1) + deps (brotli, zopfli, tinyhtml5, Pyphen, pydyf, fonttools)
- `apt-get install -y --no-install-recommends libpango-1.0-0 libpangoft2-1.0-0` (runtime-libs voor weasyprint)

### Schema
- `saas_licenses.db`: `CREATE TABLE report_jobs (uuid TEXT PK, license_code TEXT, user_email TEXT, report_type TEXT, status TEXT, pdf_path TEXT, error_message TEXT, params_json TEXT, created_at, delivered_at)`
- `pdf_path` opgeslagen als **RELATIEF** pad (`reports/<license_code>/<uuid>.pdf`) voor portabiliteit

### Storage
- `/opt/stresschecker/reports/<license_code>/<uuid>.pdf` (owner www-data, 0750)
- Pre-migratie backup: `/opt/backups/*.20260524-2031`

### Nieuwe module: `analytics.py`

Pure data-functies (geen template-rendering, geen DB-writes):
- `zone_for_ri(ri)` + `zone_label(zone_key, lang)` — RI→zone-mapping (drempels 2/4/6/8 uit `static/js/hrv.js:78-82`). 5-zone-systeem; EN-strings nieuw toegevoegd (ontbraken in hrv.js).
- `age_category(birth_year, ref_year=current)` — '<30'/'30-45'/'45-60'/'>60'/'unknown'
- `period_bounds(kind)` — maand/kwartaal/jaar/alles → ISO-strings
- `aggregate_period(license_code, pro_key, start, end, group_by, filter)` — centrale aggregatie met optionele groep-by ('office_label', 'region', 'client_id'). Cross-DB merge (saas_licenses.db.krankenkasse_offices voor region-lookup + sc_pro.db.client_metingen ⨝ clients voor M/V/age).
- `time_series(pro_key, client_id, start, end)` — tijdreeks voor pro_client-rapport
- `client_meta(pro_key, client_id)` — cliënt-info voor rapport-header

### Backend (app.py)

Plek: na `/pro/locaties/import`-route, vóór `pro_client_add`. Imports: `threading`, `uuid`.

Helpers:
- `pct()` + `zone_label_jinja()` als `@app.template_global()` voor PDF-templates
- `_report_db()`, `_license_info()`, `_license_pro_key()` — voor stabiele KK-pro_key (sha256 van `licenses.email`, niet huidige session-email — meerdere KK-collega's loggen in onder hetzelfde adres)
- `send_report_ready_email(to, uuid, lang)` + `send_report_failed_email(to, lang, err)` — NL/DE/EN, from `noreply@lifestylemonitors.com`
- `_render_report_async(uuid, license_code, user_email, lang, report_type, params, pro_key)` — background worker, niet-daemon thread, render via `app.jinja_env.get_template(...).render(...)` (geen request-context nodig), WeasyPrint `HTML(string=..., base_url=app.root_path).write_pdf()`, opslag op disk, UPDATE report_jobs, mail. Errors → log + status='failed' + foutmail.

Routes:
- `GET /pro/rapport` — formulier (conditioneel KK vs Pro via `is_krankenkasse_session()` flag)
- `POST /pro/rapport/genereer` — INSERT report_jobs pending + `Thread(target=_render_report_async, daemon=False).start()`; rendert dezelfde template met `requested_uuid` flash
- `GET /rapport/download/<uuid>` — session-licensie-gate + cross-tenant guard + `send_file(application/pdf)`. UUID-format validatie (hex). 202 als nog niet `ready`, 404 onbekend, 410 als bestand weg.

### Templates

Rapport-templates (`templates/reports/`):
- `base.html` — A4 met @page-CSS (margin, header-element via `position:running()`, footer met `counter(page)/counter(pages)`), method-block, Lifestyle Monitors footer
- `kk_overall.html` — overall stats (kantoor-count + metingen + ri-avg) + M/V + leeftijd + zone-verdeling + per-kantoor tabel + per-region tabel
- `kk_office.html` — één-kantoor variant zonder cross-kantoor tabellen
- `pro_client.html` — cliënt-meta + zone-verdeling + tijdreeks-tabel
- `pro_portfolio.html` — portefeuille-stats + zone-verdeling + per-cliënt tabel

UI:
- `templates/pro/rapport.html` — radio-buttons voor report_type, conditional dropdown voor kantoor/cliënt, periode-select (maand/kwartaal/jaar/alles), JS-toggle voor afhankelijke velden, flash-melding "wordt gegenereerd" met job-uuid

### Verificatie

- `pip3 install weasyprint` + `apt install libpango-1.0-0 libpangoft2-1.0-0` → minimal HTML→PDF render produceert PDF-1.7 (4854 bytes voor smoke-string)
- `py_compile app.py` + `py_compile analytics.py`: OK
- Jinja-parse op 6 templates via app.jinja_env: OK
- `tests/run_all.sh`: 18/18 groen
- **End-to-end** met seeded test-data (6 cliënten × 3 metingen × 3 kantoren = 18 rijen): alle 4 rapport-types renderen succesvol; aggregatie correct (Hamburg n=6 ri_avg=4.57, Hannover n=6 ri_avg=5.7, München n=6 ri_avg=3.5; M/V/D-counts kloppen)
- **Thread-pad**: POST → thread → status='ready' binnen 2 seconden → download 200 met %PDF-1.7 magic (19106 bytes)
- **Cross-tenant guard**: andere licentie-sessie download → 403
- **Consumer-sessie** → 302 redirect /welkom
- **KK probeert pro_portfolio** → 302 redirect met `error=type`
- **Onbekende UUID** → 404
- **Schone journal** na restart

### Inspectie-PDFs (blijven voor visuele check)

`/opt/stresschecker/reports/SC-KK-44F6-14A3/`:
- KK Overall: ~21 KB
- KK Office (Hamburg): ~19 KB
- Pro Client: ~18 KB
- Pro Portfolio: ~20 KB

### TODOs / latente optimalisaties

1. **`CREATE INDEX idx_report_jobs_license_created ON report_jobs(license_code, created_at)`** — niet gebouwd nu; nodig zodra rapport-geschiedenis-pagina komt (Sessie B.3?) en `WHERE license_code=? ORDER BY created_at DESC`-queries normaal worden.
2. **Mail-link-cookie-afhankelijkheid**: `/rapport/download/<uuid>` werkt alleen bij actieve session. Gebruiker uit-en-in-loggen tussen "mail ontvangen" en "klikken" verliest niet de toegang (de UUID is stabiel), maar wel als session-cookie verlopen is. Voor lange retentie eventueel signed-token-link.
3. **Geen scheduling/recurring** — alleen on-demand. Voor maand/kwartaal-recurring overweeg later cron met service-account-sessie.
4. **WeasyPrint UTC-deprecation warning** in stdlib (analytics.py:datetime.utcnow). Werkt nog onder Python 3.12; toekomstige Python kan dit verwijderen → toen vervangen met `datetime.now(tz=timezone.utc)`.
5. **PDF-size optimalisatie**: huidige rapporten 18-21 KB, prima. Geen Brotli-compressie nodig.
6. **Audit-trail** voor INSERT/UPDATE in `report_jobs` zit in tabel zelf (created_at, delivered_at, status); geen apart log nodig.
7. **Test-fixtures behouden**: PDFs uit smoke-test blijven in `/opt/stresschecker/reports/SC-KK-44F6-14A3/` voor Paul's visuele inspectie.

### Geraakte bestanden

- `analytics.py` (NIEUW, 230 regels)
- `app.py` — imports (threading, uuid), helpers, 3 routes, 2 mail-functies, 1 async worker
- `templates/reports/base.html` (NIEUW)
- `templates/reports/kk_overall.html` (NIEUW)
- `templates/reports/kk_office.html` (NIEUW)
- `templates/reports/pro_client.html` (NIEUW)
- `templates/reports/pro_portfolio.html` (NIEUW)
- `templates/pro/rapport.html` (NIEUW)
- `CHANGELOG.md` — deze entry

## 2026-05-24 — KKH-zelfbeheer kantoor-master-lijst (Sessie B.1)

Self-service kantoor-beheer voor KK-licenties. Schmidt (KKH-admin) en collega's loggen in op hetzelfde KK-account; één-rol-model. CRUD + CSV-bulk-import + overzicht met meting-counts en M/V-tellers per kantoor. Geen rol-onderscheid, geen aparte logins. Coexisteert met de bestaande Paul-only `/admin/krankenkasse/<code>/offices` (cross-licentie-toegang).

### Migratie

- `saas_licenses.db`: `ALTER TABLE krankenkasse_offices ADD COLUMN region TEXT` — 3 fixtures behouden, region=NULL voor bestaande rijen
- Pre-migratie backup: `/opt/backups/*.20260524-2006`

### Backend (app.py)

Helpers vlak na `pro_locatie`-route:
- `_kk_require()` — `abort(403)` voor anon en niet-KK-sessies
- `_kk_db()` — sqlite3-connect saas_licenses.db met Row-factory
- `_kk_office_stats(license_code, pro_key)` — cross-DB aggregatie (saas_licenses.db.krankenkasse_offices + sc_pro.db.client_metingen∗clients). Twee queries, Python-merge — geen ATTACH
- `_parse_kk_csv(raw_bytes, max_rows=500)` — strikte parser: header verplicht `office_name`+`region`, UTF-8 + BOM, autodetect `,`/`;`/`\t`, 100-char cap, lege names → skip + error

8 nieuwe routes (allemaal `_kk_require()`-gated, géén `@require_kk_office_if_krankenkasse` zodat Schmidt zonder eerst kantoor te kiezen kan importeren):

| Route | Methode | Gedrag |
|---|---|---|
| `/pro/locaties` | GET | Overzicht read-only met sort (`name`/`region`/`metingen`) + zoek-query (`q=`) |
| `/pro/locaties/beheren` | GET | Beheer-UI met form + per-rij always-editable input + acties |
| `/pro/locaties/toevoegen` | POST | INSERT single, case-insensitive dup-check, redirect `?created=1`/`?error=leeg`/`?error=dup` |
| `/pro/locaties/<oid>/bewerken` | POST | UPDATE naam+region, cross-tenant 404-guard, refresh `session['kk_office']` bij naam-wijziging van actief kantoor (historische `client_metingen.office_label`-strings blijven bewaard — audit-trail) |
| `/pro/locaties/<oid>/deactiveren` | POST | `active=0` |
| `/pro/locaties/<oid>/reactiveren` | POST | `active=1` |
| `/pro/locaties/import` | GET | Form |
| `/pro/locaties/import` | POST | 2-staps: upload → preview met `csv_text` hidden field; confirm=1 → batch-INSERT met dup-skip, redirect overzicht met `?imported=X&dups=Y` |

`abort` toegevoegd aan top-level Flask-import (regel 1).

### Templates (4 nieuwe + 2 menu-link-edits)

- `templates/pro/locaties_overzicht.html` — read-only tabel met Naam/Regio/Status/Metingen/M/V/Overig, sort-knoppen (default `name` asc), zoekveld, KK-badge `#1565c0`, empty-state met CSV-importeren-CTA
- `templates/pro/locaties_beheren.html` — flash-messages (created/updated/deactivated/reactivated/error=leeg/dup), add-form bovenaan, lijst met always-editable input-velden per rij + Opslaan/Deact/React-acties + JS `confirm()` voor deactiveren in 3 talen, empty-state
- `templates/pro/locaties_import.html` — file-upload-form, format-uitleg met live CSV-voorbeeld (Hamburg-Mitte / Bayern / Niedersachsen samples)
- `templates/pro/locaties_import_preview.html` — summary (totaal/nieuw/dup-counts), preview-tabel (max 20 nieuwe rijen + max 10 duplicates), warning-list voor parse-errors, "X importeren"-knop met `confirm=1` + hidden `csv_text`, Annuleren-link
- `templates/pro/locatie_keuze.html` — kleine "⚙ Locaties beheren →"-link onderaan (alleen voor KK, niet prominent)
- `templates/settings.html` — KK-tier-widget krijgt extra link "⚙ Locaties beheren →" onder "Huidige locatie"

### Verificatie

- `py_compile app.py`: OK
- Jinja-parse via `app.jinja_env` op 6 templates: OK
- `tests/run_all.sh`: 18/18 groen
- KK-render-smoke: /pro/locaties + /pro/locaties/beheren + /pro/locaties/import alle 200 met verwachte elementen
- **CSV-flow**: upload `office_name,region\nSMOKE_one,RegionA\nSMOKE_two,RegionB\nHannover,Niedersachsen\n` → preview toont 2 nieuw + 1 dup met Hannover in dup-list; confirm → 302 `/pro/locaties?imported=2&dups=1`; DB-state na confirm: SMOKE_one + SMOKE_two ingevoegd, Hannover (case-insensitive dup) overgeslagen
- **Edit-flow**: bewerken → `?updated=1` + flash; deactiveren → `?deactivated=1` + flash zichtbaar; reactiveren → `?reactivated=1`
- **Cross-tenant lek-test** (uit backend-fase): andere licentie's office-id bewerken vanuit KK-sessie → 404
- **Parser-tests**: BOM+semicolon → autodetect; missende `region`-kolom → duidelijke error; lege office_name → skip + warning; >500 rijen → cap
- **Pro-regressie**: niet-KK-sessie → 403 op alle 3 GET-routes; bestaande Pro-flows ongewijzigd
- Journalctl schoon na restart

### Geraakte bestanden

- `app.py` — abort-import + 3 helpers + 8 routes
- `CHANGELOG.md` — deze entry
- `templates/pro/locaties_overzicht.html` (nieuw)
- `templates/pro/locaties_beheren.html` (nieuw)
- `templates/pro/locaties_import.html` (nieuw)
- `templates/pro/locaties_import_preview.html` (nieuw)
- `templates/pro/locatie_keuze.html` — beheer-link onderaan
- `templates/settings.html` — beheer-link in KK-tier-widget

### TODOs / open punten

1. **Cross-DB `_kk_office_stats` is O(licentie-omvang)** — twee queries per render. Voor 80+ kantoren is dit nog OK; bij honderden actieve KK-licenties met elk veel kantoren kan caching nuttig zijn. Out-of-scope voor B.1.
2. **Soft-delete vs hard-delete**: alleen soft (active=0). Historische metingen blijven gekoppeld aan de oude `office_label`-string. Bij hernoeming wordt de nieuwe naam in `session['kk_office']` gezet; nieuwe metingen krijgen nieuwe naam, oude metingen blijven onder oude naam (audit-trail). Geen overschrijving van bestaande `client_metingen.office_label`.
3. **CSV-confirm-flow stuurt `csv_text` via hidden field** — voor 500 rijen × ~50 chars ≈ 25 KB POST-body. Acceptabel; bij groter volume zou je server-side temp-storage of session-based draft willen.
4. **Geen audit-log voor kantoor-wijzigingen** — INSERT/UPDATE/DELETE acties worden niet gelogd in `activation_log` (zoals admin-routes wel doen). Overweeg bij privacy/compliance-eisen vanuit KKH. Out-of-scope nu. → **GESLOTEN in Sessie B.4 (2026-05-25): `_log_kk_action` helper + 6 aanroepen.**
5. **Browser-end-to-end-check** door Paul (zoals Sessie A) — alle paden via Flask-test-client bewezen.

## 2026-05-24 — Krankenkasse-UI-verfijningen (Sessie A.1)

Cleanup na browser-test Sessie A: PRO-badge en consumer-pairing-flow zichtbaar in /pro-context die voor KK-medewerker misleidend zijn. Alleen Jinja-conditionals, geen DB-wijzigingen, geen routes, geen helpers.

### Context-processor

`@app.context_processor _inject_kk_flags()` (app.py vlak na `require_kk_office_if_krankenkasse`) — levert `is_krankenkasse` aan ELKE template, zonder view-functies te hoeven aanpassen. Sluit aan op de bestaande `is_krankenkasse_session()`-helper uit Sessie A. Vier regels.

### Templates aangepast

| Bestand | Wijziging |
|---|---|
| `templates/pro/client_detail.html` | PRO-badge in `.pro-nav` (regel 44) → `{% if not is_krankenkasse %}`; volledige Koppeling-sectie (pairingSection div + script-block met `generatePairingCode`/`revokePairing`/`showConsumerMetingen`) gewrapt in `{% if not is_krankenkasse %}...{% endif %}`. Twee separate Jinja-blocks: één voor de div (regel ~85-91), één voor het script (regel ~93-180). De later JS-block op regel 204 (`var lang = lang || "{{ lang }}"`) gebruikt fallback en blijft werken zonder de eerste script-block. |
| `templates/pro/clients.html` | PRO-badge in header (regel 29) → conditional |
| `templates/pro/dashboard.html` | PRO-badge `<span class="pro-badge">` (regel 31) → conditional |
| `templates/pro/client_add.html` | PRO-badge in screen-title (regel 6) → conditional. Aanvulling op Sessie A waar alleen de form-velden conditioneel waren. |

NIET aangeraakt (must-stay voor KK):
- "Meting kiezen"-knop, "Cliënt verwijderen"-knop, cliënt-info, breadcrumb "← Cliënten / ≡ Pro Menu"
- pro/eigen_metingen.html, pro/verloop.html, pro/meting_keuze.html (geen PRO-badge-instances of misleidende koppeling-refs)
- "Pro Menu" → "KK Menu"-hernoeming overwogen maar afgewezen; valt onder NIET-aanraken-lijst van de spec

### Verificatie

- `py_compile app.py`: OK
- Jinja-parse via `app.jinja_env.get_template()` op 4 templates: OK (vereist app-context vanwege custom `full_name` filter)
- Service restart schoon; geen errors in journal
- `tests/run_all.sh`: 18/18 groen
- Smoke via Flask test-client met temp-cliënten onder correcte pro_key-hash (paulpannevis@gmail.com + paulpannevis+kktest@gmail.com); cliënten direct opgeruimd na test:

**Pro-sessie** (regressie): PRO-badge zichtbaar op /pro/clienten + /pro/client/<id> + /pro/dashboard + /pro/client/toevoegen ✓; Koppeling-blok zichtbaar op /pro/client/<id> ✓; Meting-knop + Verwijderen-knop blijven zichtbaar ✓.

**KK-sessie**: PRO-badge weg op alle 4 plekken ✓; Koppeling-blok volledig uit DOM ✓; Meting-knop + Verwijderen-knop blijven zichtbaar (must-stay) ✓.

### Backup

`/opt/backups/*.20260524-1939`

### Open punten

- Geen TODOs uit deze sub-sessie. Resterende Sessie-A-TODOs blijven open (browser-end-to-end-check door Paul, Reply-To-bevestiging info@lifestylemonitors.de, KK-tier-widget zonder einddatum, 2FA-codes plaintext in journal).

## 2026-05-24 — Krankenkasse-licentie-tier — fundering (Sessie A)

Nieuwe licentie-categorie voor Krankenkassen (gezondheidsdagen, multi-kantoor onder één centraal account). Eerste klant: KKH. Tier-gestaffeld (Kompakt/Standard/Premium) op verzekerden-aantal; handmatige activatie (geen Stripe Payment Link).

### Migraties

- `saas_licenses.db`:
  - 3 nieuwe rijen in `plans`: `sc-krankenkasse-{kompakt,standard,premium}` (audience='krankenkasse', max_profiles=-1, max_clients=-1, stripe_price_id=NULL)
  - Nieuwe tabel `krankenkasse_offices(id, license_code, office_name, active, created_at)` + index `idx_kk_offices_license`
- `sc_pro.db`:
  - `ALTER TABLE client_metingen ADD COLUMN office_label TEXT` — 220 bestaande rijen behouden, allemaal NULL

### Audience-onderscheid

`audience` wordt voor het eerst in code gebruikt. `validate_license()` joint nu `plans.audience` mee; resultaat populeert `session['audience']` + `session['plan_id']` in `/activeer`, `verify_2fa` en `admin_bypass`-paden. Bestaande `is_pro()`-detectie blijft via `session['license_type']='pro'` voor KK-licenties (sub-rol bovenop Pro).

Nieuwe helpers (app.py vlak na `_is_pro_or_demo_pro`):
- `is_krankenkasse_session()` — boolean
- `kk_tier_label()` — 'Kompakt'/'Standard'/'Premium'/'?' uit `session['plan_id']`
- `@require_kk_office_if_krankenkasse` — decorator: KK-sessie zonder `session['kk_office']` → redirect naar `/pro/locatie`

Decorator-coverage: `pro_menu`, `pro_eigen_metingen`, `pro_clients`, `pro_dashboard`, `pro_client_detail`, `pro_client_measure`, `pro_client_add`, `pro_meting_keuze`. NIET op `pro_locatie` zelf, `settings`, `logout` (anders redirect-loop of geen ontsnapping).

### Locatie-keuze-flow

`/pro/locatie` (GET+POST) — leest `krankenkasse_offices` voor `session['license_code']`, dropdown met active=1 rijen, POST verifieert keuze tegen DB en zet `session['kk_office']`. Header in `base.html` toont KK-badge "Locatie: {office} [Wijzigen]" alleen voor KK-sessie. `templates/pro/locatie_keuze.html` (nieuw).

### Verkorte invoer-UI

`templates/pro/client_add.html` — Jinja-conditional `{% if not is_krankenkasse %}`: surname/email/phone/notes + hr-separator volledig weggelaten uit DOM voor KK-sessie. Voornaam blijft verplicht; geboortejaar+geslacht worden verplicht (i.p.v. defaults op 1970/male) zodat HRV-norm-mapping per deelnemer klopt.

### Office-label op meting

`api_meting_opslaan`: INSERT in `client_metingen` uitgebreid met 23e kolom `office_label`. Waarde = `session.get('kk_office')` enkel als `is_krankenkasse_session()` — voor Pro-sessie blijft de kolom NULL (regressie-bewezen via test-client).

### Admin-flow (handmatige activatie)

Nieuwe routes met `X-Admin-Token`/`?token=…` gate (env-var `ADMIN_KK_TOKEN` in `/opt/stresschecker/.env`, 43-char urlsafe):
- `GET/POST /admin/krankenkasse/new` — licentie aanmaken, code-formaat `SC-KK-XXXX-XXXX` (hex), origin='krankenkasse', plan_id-binding, optioneel direct welkomstmail
- `GET/POST /admin/krankenkasse/<code>/offices` — kantoor-master-lijst beheren (toevoegen)
- `POST /admin/krankenkasse/<code>/offices/<id>/deactivate` — soft delete (active=0)
- `POST /admin/krankenkasse/<code>/send-welcome` — welkomstmail (her)verzenden

Nieuwe templates: `admin/kk_new.html`, `admin/kk_offices.html`.

`send_kk_activation_email` (DE zakelijk, Reply-To `info@lifestylemonitors.de`, from `noreply@lifestylemonitors.com`) volgt het patroon van `send_verification_code`. Gebruikt ASCII-fallbacks (ueber/fuer/Gruessen) consistent met bestaand `mail_template_umlauts`-patroon.

### Tier-widget (Pro vs KK)

Bestaande Pro-tier widget op `/pro` (`pro/menu.html`) en `/instellingen` (`settings.html`) toont voor `audience='krankenkasse'` een KK-variant: "Krankenkasse-Lizenz: {Tier}" + "Unbegrenzte Teilnehmerzahl bei Gesundheitstagen" (NL/DE/EN). Reguliere Pro-cohorts behouden Pro S/M/L-rendering (regressie-bewezen via curl).

### Backups + verificatie

- Pre-migratie backup: `/opt/backups/*.20260524-1856`
- `py_compile app.py`: OK
- `tests/run_all.sh`: 18/18 groen (categorie A 6/6, B 4/4, C 8/8)
- Jinja2 parse op 7 geraakte templates: OK
- Smoke-tests admin-flow: 401 zonder token, 200 met token, POST → licentie aangemaakt + kantoren toegevoegd (DB-verificatie)
- KK-flow end-to-end via Flask test-client: validate_license → audience='krankenkasse'; /pro zonder kk_office → redirect /pro/locatie; POST locatie → /pro met KK-widget zichtbaar; client_add toont alleen voornaam/birth_year/gender; api/meting/opslaan vult office_label='Hannover'
- Pro-regressie: alle 4 optionele velden zichtbaar; office_label blijft NULL; bestaande Pro S/M/L tier-widget rendert ongewijzigd

### Test-fixture (per TEST_ACCOUNTS-policy: niet opruimen)

- Licentiecode: `SC-KK-44F6-14A3` (sc-krankenkasse-standard)
- Contact-email: `paulpannevis+kktest@gmail.com`
- 3 kantoren: Hannover, Hamburg, München
- Notes-flag: `Krankenkasse: KKH-Test-<ts>`

### Out-of-scope (komt in Sessie B)

- Rapportage-laag (aggregatie-queries per office, PDF-generatie, async generatie)
- Office-label uitgebreid analytics (per kantoor RI-distributie, etc.)
- Pro-rapportages
- HLM-blueprint blijft ongemoeid (zomer 2026 herbouw)

### Open punten / TODOs

- Welkomstmail-flow: bij POST via `X-Admin-Token` header is `request.form['token']` leeg → redirect-URL bevat `?token=` (leeg). Voor browser-flow met hidden form-veld werkt het correct. Curl-gebruikers moeten handmatig token toevoegen aan vervolgaanroepen.
- KK-tier-widget toont géén einddatum (valid_until ligt 365d weg, geen Stripe-renewal). Eventueel later toevoegen als KK-contracten daadwerkelijk verlopen.
- `templates/pro/locatie_keuze.html` toont "neem contact op met sales"-fallback als offices=0; admin-flow voorziet hier nu in maar de KK-contactpersoon krijgt geen automatische hint. Later: link naar contact-pagina.
- 2FA-codes plaintext in journalctl blijft staan (pre-existing HIGH-PRIORITY follow-up).
- Daadwerkelijke browser-end-to-end (login via /activeer + 2FA-mail) niet tijdens deze sessie uitgevoerd: vereist email-toegang voor verificatiecode. Alle paden zijn via Flask test-client end-to-end bewezen.

## 2026-05-24 — Optioneel achternaam-veld (drie naam-rollen)

Voornaam blijft verplicht, achternaam optioneel toegevoegd aan zowel het profiel van de gebruiker (consument en Pro delen `users.display_name`) als aan Pro-cliëntprofielen (`sc_pro.db.clients`).

### Migraties

Twee `ALTER TABLE … ADD COLUMN surname TEXT`:

- `/opt/ic-license-server/data/saas_licenses.db` → `users` (dekt rol 1 consument en rol 2 Pro eigen profiel — gedeeld pad via `save_profile` + `api_save_settings`)
- `/opt/stresschecker/data/sc_pro.db` → `clients` (dekt rol 3 Pro's cliënt)

De andere kandidaat-tabellen (`sc_measurements.db.user_profiles.naam` en `saas_licenses.db.profiles.name`) zijn ongemoeid gelaten — beide hadden 0 rijen en geen INSERT/UPDATE-pad in app.py (dode schema's).

### Display-logica

Nieuwe Jinja-filter `full_name` (app.py:99) rendert `'voornaam achternaam'` als `surname` aanwezig, anders alleen `voornaam`. Werkt op `sqlite3.Row`, dict, object met `.name`/`.surname`-attrs, of string + optionele 2e arg. Gebruikt in `pro/client_detail.html` (h2, nav-bar, Innerlijk Kompas-kop), `measure.html`, `sensor_en_meten.html`. Voor `kwadrant.html` wordt de full-name server-side in `client_name` gestopt (regel 1267 in app.py).

### Sessie-beleid

- `session['profile_name']` blijft voornaam (compact, header-badge `base.html:51` ongewijzigd).
- `session['profile_surname']` apart bijgehouden, gerenderd op detail-pagina's en meet-schermen.

### Backward compatibility

Bestaande rijen behouden hun string in `name`/`display_name`; `surname=NULL`. Geen auto-split: "Anna de Vries", "Paul Pannevis", "Steven P" worden ongewijzigd weergegeven. Bij volgende edit kan de eigenaar de naam zelf splitsen.

### Templates uitgebreid

- `templates/profile.html` — surname-input onder voornaam (consument + Pro eigen profiel)
- `templates/settings.html` — `inputSurname`-veld + JS-payload uitgebreid
- `templates/pro/client_add.html` — surname-input (Pro nieuwe cliënt)
- `templates/pro/client_detail.html` — `editSurname`-input + display via `{{ client|full_name }}` op 3 locaties

### Routes uitgebreid (app.py)

`save_profile`, `api_save_settings`, `pro_client_add`, `api_pro_client_update`, `pro_client_measure` (session), `sensor_en_meten` (profile-dict), `biofeedback` (profile-dict), `kwadrant` (client_name), `settings` (template-context). Login-paden (regel 644, 856) lezen surname mee. `admin_bypass` splitst Paul/Pannevis.

### Out-of-scope (TODO achtergelaten)

- HLM-blueprint gebruikt aparte `clients`-tabel in saas_licenses.db (schema met `display_name`); wordt zomer-2026 herbouwd. TODO-comment op beide initials-regels in `hlm/meting_src.html` (8449, 8754).
- Pre-existing issues opgemerkt, niet aangeraakt:
  - `/admin-login-bypass-9x7k` zet `user_key` handmatig maar `get_user_key()` overschrijft direct op basis van `sha256(email)[:32]`.
  - Dode `session['pro_display_name']`-fallback in `settings.html:97` — nergens geset.

### Validatie

- Pre-migratie backup: `/opt/backups/*.20260524-1457`
- `py_compile app.py`: OK
- `systemctl restart stresschecker`: workers up, geen errors in journal
- `tests/run_all.sh`: 18/18 groen
- 3-talen smoke (NL/DE/EN): labels correct, full-name rendering correct
- Backward compat: Anna de Vries blijft "Anna de Vries", avatar='A', geen NULL of rare karakters
- Nieuwe cliënt Peter+Pannevis: DB → name='Peter', surname='Pannevis'; rendering → "Peter Pannevis" overal (h2, meting-schermen, kwadrant)

## 2026-05-22 — RI birth_year/gender uitvraag in activatie-flow

Verplichte uitvraag van `birth_year` + `gender` vóór eerste meting, met norm-mapping voor non-binary opties. Fixt drie samenhangende latente bugs en lift de "71% van users heeft default 1970/male"-anomalie.

### Latente bugs gefixt

- **save_profile sloeg birth_year/gender niet op in users-tabel** (`app.py:987-1007`). UPDATE-statement vulde alleen activated_at + license_expires. Birth_year/gender bleven session-only en gingen verloren bij logout. Nu: `display_name`, `birth_year`, `gender` worden gepersisteerd, met `COALESCE(activated_at, ?)` zodat eerste-keer-vulling intact blijft.
- **license_expires-gat** (secundair gefixt): `license_notifications.py:225` filtert renewal-mails op `WHERE license_expires IS NOT NULL`. 71% van users had `license_expires=NULL` en kreeg dus géén 30/7-dagen-vervalwaarschuwing. Save_profile vult license_expires nu wél bij eerste keer.
- **activated_at-gat** (impliciet gefixt door save_profile-COALESCE): users zonder profile_setup hadden `activated_at=NULL`.

### Nieuwe features

- **verify_2fa redirect naar profile_setup** als `users.birth_year IS NULL OR = 1970` (app.py:884).
- **/sensor-en-meten block-check voor eigen-meting** (app.py:1140+): bij `_cid==0` redirect naar `/profiel?reason=meting_blocked` met visuele banner.
- **4 gender-opties** in profile.html: male/female/divers/unspecified, geen default-checked, `placeholder="1985"` ipv `value="1970"`.
- **hrv.js norm-mapping** voor `gender ∈ {divers, unspecified}` → `(n.m+n.f)/2`. Bewezen via node-test: male=78 > divers=74 = unspecified=74 > female=70 (age 41, RMSSD ≈ 28).

### Buiten scope (vastgelegd in CLEANUP_TODO ## TODO)

- HLM-flow: eigen client-side birth_year/gender via localStorage en eigen norm-tabel — meenemen in HLM Pro nieuwe generatie (~1 aug 2026).
- Norm-tabel-consolidatie tussen hrv.js en hlm/meting_src.html (1.3 RI-punten divergentie).
- `profile_completed` boolean-kolom (vervangt 1970-heuristiek).
- activation_log gap voor manual-origin accounts.
- **2FA-codes plaintext in journalctl** — HIGH PRIORITY, herbevestigd vandaag.

### Validatie

- Backup-snapshot vóór wijziging: `/opt/backups/*.20260522-1128`
- `py_compile` na elke .py-Diff: OK
- Jinja2 parse `profile.html`: OK
- `node -c hrv.js`: OK
- HUP gunicorn master: workers respawn zonder errors
- End-to-end curl-flow + 2 test-fixtures (id=25 female 1985, id=26 divers 1990): alle 5 Diffs (A-E) bewezen werkend
- Existing users (Paul 1949, Steven 1982): géén redirect-impact

## 2026-05-22

Codebase cleanup volgens CLEANUP_TODO.md, gefaseerd uitgevoerd met checkpoint-akkoorden (Fase 1 inventarisatie, Fase 2 uitvoering A→H).

### 2-A — Onderzoek `ic_licenses.db`
Verlaten schema-prototype in repo-root (122 KB, 13-05-2026, geen code-refs). Alle 7 tabellen leeg; schema is vroege versie van saas_licenses.db (104 vs 309 schema-regels). Geen tweelingbestand in `/opt/backups/`. Eenmalig handmatig aangemaakt experiment. Gearchiveerd naar `/opt/backups/cleanup_20260522/db_archive/ic_licenses.db`.

### 2-C — Latente bug `gen_context.py:9` gefixt
Regel verwees naar `/opt/stresschecker/data/saas_licenses.db` (0-byte stub) i.p.v. `/opt/ic-license-server/data/saas_licenses.db` (productie). CONTEXT.md `## Databases`-sectie miste hierdoor het 22-tabel overzicht. Eén-regel-fix; gen_context.py-output nu compleet.

### 2-D — Orphan stubs + accidenten verwijderd
- 4 root-level 0-byte DB-stubs: `saas_licenses.db`, `sc_measurements.db`, `sc_pro.db`, `stresschecker.db`
- 3 `data/` 0-byte stubs: `saas_licenses.db`, `metingen.db`, `pro_clients.db`
- `/opt/stresschecker/{templates/` met 5 lege subdirs (bash-brace-expansion accident, 20-02-2026)
- `toegepast` (0-byte mystery file)
- `templates/oude_code_keuze.html` (0-byte placeholder, route gebruikt `legacy_choice.html`)

### 2-E — Archivering naar `/opt/backups/cleanup_20260522/`
153 files / 8.4 MB in 12 submappen:
- `root_app_varianten/` — 29 files (app.py.bak*/.current/.merge_backup), 4.2 MB
- `templates_subtree/{root,pro,hlm}/` — 74 files (60+11+3), 3.0 MB
- `templates_backups/` — 2 dirs (templates_backup_20260224_1406/_1407/), 28 .html, 300 KB
- `data_db_backups/` — 3 DB-snapshots, 612 KB
- `gen_context_varianten/` — 6 files, 48 KB
- `env_context_backups/` — 3 files (.env.bak_sendgrid + 2 CONTEXT.md.bak*), 40 KB
- `static_js/` — 4 hrv.js.bak*, 36 KB
- `db_archive/` — ic_licenses.db, 124 KB
- `docs/` — trend_hint_varianten_review.md, 20 KB
- `hlm_routes/` — routes.py.bak, 20 KB
- `tests_bak/` — 2 files, 20 KB
- `seed_varianten/` — seed_anna.py.v1, 12 KB

Buiten oorspronkelijke Fase 1-scope (alleen root): de 74 templates-baks, 4 hrv.js.bak, hlm/routes.py.bak, 2 tests-bak items. Recursieve find vóór 2-E uitvoering bracht ze aan het licht; met expliciet akkoord toegevoegd aan herzien plan.

### 2-F — `.gitignore` uitgebreid
Nieuwe regels: `/*.db`, `/*.current`, `/*.merge_backup`, `/*.v1`, `/*.pre-leerpunt`, `/templates_backup_*/`, `*.backup`, `*.backup-*`, `toegepast`. Overlap-vrij geverifieerd met `git check-ignore`.

### Verificatie
- File-count root: 76 → 33 entries (`ls -la`); 68 → 26 non-hidden
- `git ls-files | grep -E '\.(db|bak|backup)$'` → leeg
- `git clone /opt/stresschecker /tmp/test-clone` → 0 rommel-hits, clone bevat slechts 7 entries
- Smoke test `/licentie` → HTTP 200
- Productie-DB `/opt/ic-license-server/data/saas_licenses.db` onaangeroerd: **mtime `2026-05-21 19:28:15.812239508` identiek aan baseline begin Fase 2**; rowcounts licenses=35, users=14, subscriptions=11, plans=18 ongewijzigd

Twee backup-snapshots vandaag: `/opt/backups/*.20260522-0741` (pre-Fase-2) en `*.20260522-0803` (pre-2-E mv).

### Correctie op CLEANUP_TODO.md
De waarschuwing "CRITICAL: bevat klantdata + license-keys" bij root-level saas_licenses.db was feitelijk onjuist — het bestand was 0 bytes. De echte productie-DB woont in `/opt/ic-license-server/data/` en zat niet in deze repo. CLEANUP_TODO.md bijgewerkt.

### Leerpunt voor toekomstige cleanup-sessies
Begin een cleanup altijd met een recursieve scan van de hele tree, niet alleen root-niveau. Fase 1 van deze sessie scande alleen `/opt/stresschecker/` root, wat een gefragmenteerd plan opleverde dat tijdens uitvoering 2× herzien moest worden (74 templates-baks + .gitignore-aanpassingen). Eén grondige recursieve find vooraf scheelt twee tussen-revisies achteraf.

## 2026-05-21

- Nieuw plan-type `sc-{pro-m,pro-s,consumer}-eval` — 90-dagen evaluatielicenties voor partner-outreach (eerste case: Mühlberger DGBfb, later KKH/Barmer pilots). UI-label "Evaluatielicentie/Evaluierungslizenz/Evaluation license" via uitbreiding `PRO_PERIOD_LABELS`. Geen Stripe-koppeling. Data-behoud bij upgrade naar regulier abonnement via e-mail-hash (bestaand model). `origin='evaluation'` als 5e taxonomie-waarde. Marketing-branch in /activate verbreed naar `IN ('marketing','evaluation')` met plan-driven expiry-helper `_compute_license_expires_at()` (vervangt hardcoded 365d). Activation-log gebruikt nu `activate_{origin}` voor cohort-tracking. Generator `/opt/ic-license-server/generate_eval_license.py` (niet in git, naast saas_licenses.db). Centrale constante `EVAL_DURATION_DAYS=90` in `eval_config.py` — single source of truth voor zowel app.py als generator.
- Latente issue gefixt (mede gemerkt tijdens eval-werk): `licenses.expires_at` en `licenses.valid_until` werden inconsistent gevuld door marketing-branch (alleen `expires_at`). Nu beide gesynchroniseerd om validator-pad (dat `valid_until` leest) gelijk te houden met activatieflow (dat `expires_at` schreef).
- Follow-up: consumer-eval UI op /instellingen out-of-scope MVP — `get_pro_tier_summary` blijft `type='pro' AND product='sc'`-gated; consumer-eval-licenties krijgen wel correcte DB-state en activatie maar geen widget. Pas adresseren als concrete consumer-eval-recipiënt zich aandient.
- TEST_ACCOUNTS.md aangemaakt — beleid + actieve test-fixtures (paulpannevis+mueh-test + paulpannevis+evaltest). NIET-opruimen-regel vastgelegd; geen staging-omgeving dus deze accounts zijn de enige levende referentie voor regressie-checks. Wegwerp-eval-licentie SC-PRO-F4751519 ge-tagged als INTERNAL TEST FIXTURE in licenses.notes.
- Eerste Mühlberger-codes uitgegeven: SC-PRO-D3AA13C6 (sc-pro-m-eval, Pro 30 clients) + SC-CON-A212404F (sc-consumer-eval, persoonlijk). code_expires_at=2026-08-19 activatie-deadline.
- /instellingen UX-fix — Pro-abonnement label nu taal-consistent (Jaarabonnement/Jahresabonnement/Annual subscription via plan-code mapping i.p.v. Stripe product.name). Licentiecode-label expliciet gemaakt met helptekst voor activatie op nieuw apparaat. NL/DE/EN visueel geverifieerd.
- Pro-tier widget op /pro + /instellingen voor alle Pro-cohorts (was Stripe-only). Toont tier (Pro S/M/L), actieve koppelingen vs. max_clients en geldigheid; afgeleid uit licenses + plans, Stripe-onafhankelijk.
- git init + initial commit op /opt/stresschecker/ (lokale repo, geen remote).
- .gitignore aangemaakt (secrets, backups, databases, CONTEXT.md, .claude/).
- CHANGELOG.md + gen_context.py-integratie: CONTEXT.md krijgt voortaan automatisch een 'Recente wijzigingen'-sectie uit CHANGELOG.md.
- CLEANUP_TODO.md aangemaakt voor latere opruiming root-level artefacten (app.py.current, saas_licenses.db in root, etc.).
