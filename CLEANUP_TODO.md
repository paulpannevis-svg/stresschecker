# Opruim-TODO root-level /opt/stresschecker/

Aangemaakt: 21-05-2026 na git init.
Reden: bij git init op 21-05-2026 zijn root-level artefacten geconstateerd die in een latere sessie geadresseerd moeten worden voordat iemand een `git add .` doet die ongewenste bestanden meeneemt.

## UITGEVOERD 22-05-2026

Gefaseerde cleanup met checkpoint-akkoorden. Details: CHANGELOG.md ## 2026-05-22 + archief `/opt/backups/cleanup_20260522/`.

Originele agenda-items:

- [x] `app.py.current` (Mar 2, 1038 regels) — pre-2FA/SendGrid era, gearchiveerd
- [x] `app.py.merge_backup` (Mar 2, 834 regels, byte-identiek aan app.py.bak.legacy*) — gearchiveerd
- [x] `saas_licenses.db` in repo-root — **was 0 bytes**, geen klantdata. De CRITICAL-waarschuwing hierboven was feitelijk onjuist: de echte productie-DB woont in `/opt/ic-license-server/data/saas_licenses.db` en zat niet in deze repo. Root-stub verwijderd.
- [x] Andere root-level `*.db`: `ic_licenses.db` (122 KB, leeg schema-prototype, geen code-refs → gearchiveerd in `db_archive/`); `sc_measurements.db`, `sc_pro.db`, `stresschecker.db` (0-byte stubs → verwijderd)
- [x] Andere root-level `*.bak`/`*.backup`: 29 app.py.bak* + 6 gen_context.py.bak* + .env.bak_sendgrid + 2 CONTEXT.md.bak* — alle gearchiveerd
- [x] `gen_context.py.pre-leerpunt` — gearchiveerd
- [x] `seed_anna.py.v1` — gearchiveerd
- [x] `templates_backup_20260224_*` (2 directories, 28 .html totaal) — gearchiveerd

Niet in oorspronkelijk plan, tijdens recursieve scan vóór Fase 2-E ontdekt en met akkoord toegevoegd:

- [x] 74 backup-files in `templates/`-subtree (60 root + 11 pro/ + 3 hlm/) — Fase 1 scande alleen root-niveau
- [x] 4 `hrv.js.bak*` in `static/js/`
- [x] 1 `routes.py.bak` in `hlm/`
- [x] 2 `.bak`-files in `tests/`
- [x] 3 DB-snapshots in `data/` (sc_measurements.db.bak-live, sc_pro.db.bak.before_seed, sc_measurements_backup_20260412.db)
- [x] `/opt/stresschecker/{templates/` brace-expansion accident (5 lege subdirs) — verwijderd
- [x] `toegepast` 0-byte mystery file — verwijderd
- [x] `templates/oude_code_keuze.html` 0-byte placeholder (niet door route gebruikt; route rendert `legacy_choice.html`) — verwijderd
- [x] Latente bug `gen_context.py:9` (verwees naar 0-byte stub) — gefixt
- [x] `.gitignore` uitbreiding met root-level anchors + brede subdir-patterns — toegevoegd

## TODO — voor latere sessies

- [ ] **Untracked dirs git-tracken**: `hlm/`, `scripts/`, `static/`, `templates/`, `tests/`, `email_templates/`. Aparte sessie nodig: per directory bewust afwegen (secrets? configuratie? testdata?). Tot die sessie blijven deze dirs untracked en gaan ze niet mee met `git add .`.
- [ ] **Docs-organisatie**: `LAUNCH_LOG.md`, `PWRESET_PLAN.md`, `TODO.md` (en eventueel `SYSTEM_REFERENCE.md`) — verplaatsen naar `docs/` subdir of in root laten? Aparte beslissing per file.

- [ ] **SendGrid API-key audit**: drie unieke SendGrid API-keys in vier codebase-locaties gevonden tijdens 22-05-2026 cleanup-sessie (poging tot SendGrid-key-fallback-cleanup geannuleerd omdat scope buiten terminal-context viel):
    - `/opt/stresschecker/.env` SENDGRID_API_KEY — suffix `8UuY` (huidige, post-12-05 rotatie)
    - `weekly_email.py:8` fallback (hardcoded) — suffix `9Amg`
    - `license_notifications.py:12` hardcoded (geen env-var-laag) — suffix `Ixc0` (matcht `.env.bak_sendgrid_20260512` ⇒ pre-12-05 rotatie)
    - root crontab `weekly_email`-regel prefix — suffix `9Amg` (identiek aan `weekly_email.py:8` fallback, geen extra unieke key)

    Status van obsolete keys ONBEKEND zonder SendGrid-dashboard-toegang; vermoeden ≠ bewijs.

    Te doen in aparte sessie:
    a. SendGrid-dashboard openen, lijst active/disabled keys met laatst-gebruikt timestamps
    b. Match elke gevonden key tegen de 4 codebase-locaties (suffix-vergelijking volstaat)
    c. Per locatie beslissen: vervangen door `os.environ`-only (met `load_dotenv("/opt/stresschecker/.env")`), key revoken in SendGrid, of beide. Voor `weekly_email.py` is `load_dotenv(..., override=True)` nodig omdat crontab-prefix anders voorrang krijgt.
    d. Daarna kan **Untracked dirs git-tracken**-sessie (item 1) veilig doorgaan zonder dat hardcoded keys in git-historie belanden.

    Tot die sessie blijven `weekly_email.py` en `license_notifications.py` untracked; geen acute git-leak-risico.

### Toegevoegd 22-05-2026 na RI birth_year/gender uitvraag-sessie

- [ ] **2FA-codes plaintext in journalctl** *(HIGH PRIORITY)*: herbevestigd 22-05; oorspronkelijk gemeld 12-05 in gen_context.py follow-ups. Voorbeeld vandaag: `gunicorn[1369644]: 2FA CODE for test-rifix@lifestylemonitors.com: 902758`. Log-redactie of verwijderen van de print-statement nodig (`app.py:671`, `app.py:692`). Productie-security-issue. Eerstvolgende cleanup-sessie aanpakken.

- [ ] **Norm-tabel-consolidatie**: `hrv.js` N-array (13 buckets, ~5-jarig) en `hlm/meting_src.html` rmssdReference (7 buckets, 10-jarig) divergeren materieel — tot 1.3 RI-punten verschil voor jong-volwassenen bij identieke meting. Beide claimen Lifelines Cohort. Wetenschappelijke beslissing nodig over baseline. Aparte sessie.

- [ ] **kwadrant.html:347-350 referentiewaarde-display gebruikt lokale binary norm-keuze (`female ? f : m`)** terwijl hrv.js Diff E (commit a1107a2 22-05-2026) divers/unspecified als gemiddelde m+f behandelt. Inconsistentie voor display in details-tabel: berekend HRV% klopt, maar getoonde referentiewaarde matcht niet. Aparte fix nodig om kwadrant.html lokale norm-keuze uit te breiden met divers/unspecified-pad. Impact in productie: 1 test-fixture id=26 SC-TEST-RIFIX-002 (geen echte klanten). Past mogelijk in hetzelfde moment als norm-tabel-consolidatie (hrv.js vs hlm/meting_src.html) omdat alle drie norm-tabel-aanrakingen tegelijk genomen kunnen worden.

- [ ] **Profile-completion-tracking**: huidige check `_birth == 1970` triggert profile_setup ook voor echte 1970-geborenen (nu 0 in productie, edge case acceptabel). Voor cleaner design: voeg `profile_completed` boolean-kolom toe aan users-tabel. Vervangt heuristiek die afhangt van schema-defaults (`birth_year DEFAULT 1970`, `gender DEFAULT 'male'`).

- [ ] **activation_log gap voor manual-origin accounts**: log-INSERT zit alleen in marketing/evaluation-branch (`app.py:607-613`), niet in algemene activatie-flow. Handmatig aangemaakte accounts (origin='manual') ontbreken in audit-trail. Niet kritiek, wel relevant voor traceability bij latere klant- of audit-vragen. Aparte sessie.

- [ ] **Notitie HLM-flow (22-05-2026)** *(geen losse fix nodig)*: HLM-flow heeft eigen client-side birth_year/gender via localStorage en eigen norm-tabel in `hlm/meting_src.html` die divergeert van `hrv.js`. Meenemen in HLM Pro nieuwe generatie doorontwikkeling (~1 aug 2026) vanaf de start.

- [ ] **HLM zone-labels oude pré-rebrand terminologie (05-06-2026)**: `templates/hlm/kwadrant.html` regel 107 (`ZL`-array: 'Schwerer Stress'/'Stress'/'Leichter Stress' DE, 'Zware stress'/'Stress'/'Lichte stress' NL) en regel 149 (comment) gebruiken nog de stress-familie i.p.v. de rebrand belast-familie (Zwaar belast/Belast/Licht belast/In balans/Veerkrachtig — DE: Schwer belastet/.../Vital). Bewust **niet** meegenomen in de menu.html-fix van 05-06: HLM is een apart spoor (unproven product-fit, deploy only when ready) in aparte klantcontext. Bij HLM-activering automatisch op tafel; consolideren naar dezelfde canonieke bron (`analytics.py` RI_ZONES / `static/js/hrv.js` getLabel) als de consumer-flow.

## Design-keuzes (geen actie nodig)

- **NL-aanspreekvorm split** (bevestigd 22-05-2026): educatieve templates (`welcome.html`, `faq.html`, `upgrade.html`, `profile.html`, `waarschuwing.html`) hanteren **je-vorm**; juridische/activatie-templates (`privacy.html`, `license.html`, `koppelen.html`, plus de toelichting op `/licentie` onder de submit-knop) hanteren **u/uw-vorm**. Bewuste design-keuze, geen technische schuld. DE-equivalent: consumer-flow gebruikt overal `Sie/Ihr` (formeel), niet `du` zoals oorspronkelijk vermoed.
