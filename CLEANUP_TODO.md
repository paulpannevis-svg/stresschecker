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

- [x] **Security-flag `static/backup-download.tar.gz`** — AFGEHANDELD 06-06-2026. Stond publiek
  downloadbaar; verplaatst naar `/root/quarantine/` (0700), URL nu 404. Volledige analyse +
  secret-rotaties in `INCIDENT_2026-06-06_backup_exposure.md`. **Vervolg-opruimacties uit het
  incident (aparte sessie):** dode secrets verwijderen (`INTERNAL_API_KEY` in `ic .env`,
  `/opt/ic-license-server/data/api_key.conf`, ongebruikte `SECRET_KEY` in `ic .env`); 4×
  `/opt/ic-license-server/.env.bak_*` opruimen; wachtwoord-hashing-formaat beoordelen
  (hex-digest zonder salt-prefix); besluit vernietiging tarball + `/root/quarantine/inspect/`.

- [ ] **PayPal-opruiming na app-verwijdering (06-06-2026)** — de Live-app "Lifestyle Monitors"
  is verwijderd (zie incidentdoc). Vervolg:
    - ✅ **GEDAAN 06-06 (optie A2):** dode `PAYPAL_*` (4 regels) uit `/opt/ic-license-server/.env`
      verwijderd + code-routes weg uit `server.py` (`get_paypal_token`, `plan_id_from_paypal`,
      `/api/webhooks/paypal`, `/api/webhooks/paypal/test`) + dode `_requests`-import opgeruimd.
      Getest: beide endpoints → 404, server gezond (admin/stats 200). `cancel_paypal_subscription`
      bewust behouden als self-guarding no-op. (server.py niet in git — zie versiebeheer-gat hieronder.)
    - **22 verweesde PayPal billing plans** opruimen in het PayPal Business Dashboard
      (achtergebleven na app-verwijdering).
    - **Provider-app-inventaris opschonen**: uitzoeken of **Buckaroo** (26-11-22) en **Mollie**
      (24-01-26) nog ergens voor dienen, en of één van de **3× MyApp_WooCommerce** (12-01-26,
      binnen 20 min aangemaakt) een dode dubbele is. Deze apps zijn provider-gegenereerd en
      stonden NIET in de tarball — bewust laten staan tot uitgezocht.

- [ ] **KK-operator-laag — credentialmodel herzien bij heractivering (06-06-2026)**:
  - **Gedaan 06-06:** operator-account id=30 (`paulpannevis+kkoperator@gmail.com`) gedeactiveerd —
    onbekend lang random bcrypt-wachtwoord + `deleted_at` gezet (genoteerde credential was dood-risico,
    operator-login skipt 2FA). DB-wijziging, niet in git.
  - ✅ **GEDAAN 06-06:** feature-flag `KK_OPERATOR_ENABLED=False` (`app.py:18`) over 3 sites —
    operator-login **harde weigering** (geen 2FA-doorval), auto-create overgeslagen, beheerroutes
    `abort(404)`. Getest (run_all 21/1 + test_client: login geweigerd, routes 404). Bij KK-go-live:
    vlag op `True`.
  - **Bij heractivering KK-laag:** het hele operator-credentialmodel herzien — eenmalig gegenereerd
    wachtwoord + 2FA-skip + 24u-sessie is voor een **Krankenkassen-context te mager**; 2FA hoort
    óók voor operators te gelden. Zie [[project_uncommitted_kk_operator_workstream]].

- [ ] **Versiebeheer-gat `/opt/ic-license-server` (06-06-2026)**: de hele license-server-backend
  (`server.py`, `database.py`, confs) staat **niet onder git**. Daardoor zijn wijzigingen daar
  (Stripe-key-rotatie, IC_ADMIN/IC_SECRET, PayPal-uitfasering) alleen in de stresschecker-CHANGELOG
  gedocumenteerd, niet als diff traceerbaar. Overweeg `git init` op ic-license-server (met
  `.gitignore` voor `.env`/`data/*.db`/`*.conf`-secrets) in een aparte sessie.

- [x] **Untracked dirs git-tracken** — UITGEVOERD 06-06-2026 (Fase 1 git-sanering, zie CHANGELOG). Getrackt: `scripts/`, `static/` (excl. video's/backup-tarball), `templates/` (consumer+pro), `tests/`. BEWUST GEPARKEERD: `hlm/`+`templates/hlm/` (apart spoor, beslissen bij HLM-activering), `email_templates/` (verweesd, verwijderkandidaat), `license_notifications.py`+`weekly_email.py` (Fase 2 secrets).
- [x] **Docs-organisatie** — UITGEVOERD 06-06-2026: `LAUNCH_LOG.md`, `PWRESET_PLAN.md`, `RMSSD_HERBEREKENING_OVERZICHT.md`, `STAGING_OPZET_PLAN.md`, `TODO.md` → `docs/`. `SYSTEM_REFERENCE.md` BLIJFT in root (backup.sh:4 kopieert vanaf root-pad) — verplaatskandidaat zodra backup.sh meeverhuist. `docs/kontakt_v3_backup.html` = verwijderkandidaat (J).

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

    **Update 2026-06-06 (Fase 2A — code-zijde UITGEVOERD):** alle hardcoded keys uit de code/crontab verwijderd:
    - `license_notifications.py`: regel 12 → `os.environ['SENDGRID_API_KEY']` + `load_dotenv('/opt/stresschecker/.env')` (expliciet pad: cron-cwd = `/root`).
    - `weekly_email.py`: regel 8 fallback weg → `os.environ['SENDGRID_API_KEY']` + `load_dotenv('/opt/stresschecker/.env')`. (`override=True` bleek niet nodig: de crontab-prefix is óók verwijderd, dus er is geen concurrerende env-var meer.)
    - root crontab: inline `SENDGRID_API_KEY=…9Amg`-prefix uit de weekly_email-regel verwijderd.
    - Geverifieerd zonder verzenden: beide scripts resolven vanuit `/root` de `.env`-key (suffix `8UuY`) via module-import; `main()`/`send_weekly()` staan achter `__main__`-guard.
    - **Nog open (Paul, 2B):** read-only testverzending met `.env`-key + daarna in SendGrid-dashboard (account u60716759) **ALLE** oude keys deactiveren — zowel `…Ixc0` als `…9Amg` (beide stonden plaintext, `…9Amg` ook in crontab + getoond in terminal). Daarna afrondende commit (`license_notifications.py` + `weekly_email.py` nu committen, keys zijn eruit).

    **Update 2026-06-05:** `license_notifications.py:get_lang` is op schijf gefixt (EN-abonnees kregen NL-vervalmails — zie I18N_TODO.md / CHANGELOG). Het bestand blijft **untracked** wegens de hardcoded key op regel 12; de get_lang-fix wordt pas mee-gecommit zodra deze secret-rotatie-sessie de key naar `os.environ` verhuist. Tot dan leeft de fix alleen op schijf (cron draait het schijf-bestand, dus productie is correct).

### Toegevoegd 22-05-2026 na RI birth_year/gender uitvraag-sessie

- [x] **2FA-codes plaintext in journalctl** *(HIGH PRIORITY)* — UITGEVOERD 06-06-2026 (Fase 2D). Bij hercontrole bleken het **4** logsites te zijn (niet 2; de oude regelnummers 671/692 waren verschoven): `app.py:971`, `:994`, `:1304`, `:6082`. Alle vier `logging.getLogger().warning("2FA CODE…{code}")` vervangen door `logging.getLogger().info(f"2FA-code verzonden aan {email}")` — event blijft, code-inhoud weg. 2FA-flow ongewijzigd. **Live-deploy (kill -HUP) gebeurt bij de afrondende Fase 2C/2E-commit ná Paul's 2B**; tot dan draait de oude code nog in geheugen.

- [ ] **Licentiecodes plaintext in logs (06-06-2026)** *(MEDIUM PRIORITY)*: tijdens Fase 2D-2FA-onderzoek aangetroffen, **bewust buiten die commit gehouden** — eigen afweging (debug-nut vs. risico). Licentiecodes zijn ook secrets. Drie debug-`print`-statements loggen de code:
    - `app.py:370` — `print(f"VALIDATE START: code={code}", flush=True)`
    - `app.py:788` — `print(f"[ACTIVEER DEBUG] code='{code}' legacy='{legacy}' email='{email}'", flush=True)`
    - `app.py:6143` — `print(f"LICENSE GENERATED: {new_code} type=… email=… order=…", flush=True)`
    Aparte sessie: per regel beslissen redacten/verwijderen (versus tijdelijk debug-nut). Anders dan 2FA-codes (eenmalig, 10 min geldig) zijn licentiecodes langlevend.

- [ ] **Kompas-tekst basismeting — baseline expliciet benoemen (06-06-2026, GEPARKEERD)**:
  overwegen om in de Innerlijk-Kompas-tekst bij basismetingen de baseline expliciet te noemen
  (bijv. "daarmee zit je net boven je baseline"), zodat de tekst en de grafiek/legenda over
  hetzelfde getal praten. De data is er al (`compute_baseline` voedt `baseline_ri`/`baseline_range`
  + `personal_baseline`); dit is een tekst-/prompt-keuze, geen berekening. Niet bouwen tot besloten.

- [ ] **`_baseline_avg` (biofeedback AI-prompt) consolidatie-restpunt (06-06-2026)**: bij de
  baseline-consolidatie bewust NIET meegenomen — het is het gemiddelde van `recent_basis` (laatste
  basismetingen, niet laatste-per-dag), afgeleid van de bewust-ongemoeide `recent_basis`-prompt-input
  (`app.py:~4894`). Bij een latere Kompas-prompt-herziening overwegen of de biofeedback-baseline
  ook naar `compute_baseline` moet, zodat álle AI-baselines één getal delen.

- [ ] **Norm-tabel-consolidatie**: `hrv.js` N-array (13 buckets, ~5-jarig) en `hlm/meting_src.html` rmssdReference (7 buckets, 10-jarig) divergeren materieel — tot 1.3 RI-punten verschil voor jong-volwassenen bij identieke meting. Beide claimen Lifelines Cohort. Wetenschappelijke beslissing nodig over baseline. Aparte sessie.

- [ ] **kwadrant.html:347-350 referentiewaarde-display gebruikt lokale binary norm-keuze (`female ? f : m`)** terwijl hrv.js Diff E (commit a1107a2 22-05-2026) divers/unspecified als gemiddelde m+f behandelt. Inconsistentie voor display in details-tabel: berekend HRV% klopt, maar getoonde referentiewaarde matcht niet. Aparte fix nodig om kwadrant.html lokale norm-keuze uit te breiden met divers/unspecified-pad. Impact in productie: 1 test-fixture id=26 SC-TEST-RIFIX-002 (geen echte klanten). Past mogelijk in hetzelfde moment als norm-tabel-consolidatie (hrv.js vs hlm/meting_src.html) omdat alle drie norm-tabel-aanrakingen tegelijk genomen kunnen worden.

- [ ] **Profile-completion-tracking**: huidige check `_birth == 1970` triggert profile_setup ook voor echte 1970-geborenen (nu 0 in productie, edge case acceptabel). Voor cleaner design: voeg `profile_completed` boolean-kolom toe aan users-tabel. Vervangt heuristiek die afhangt van schema-defaults (`birth_year DEFAULT 1970`, `gender DEFAULT 'male'`).

- [ ] **activation_log gap voor manual-origin accounts**: log-INSERT zit alleen in marketing/evaluation-branch (`app.py:607-613`), niet in algemene activatie-flow. Handmatig aangemaakte accounts (origin='manual') ontbreken in audit-trail. Niet kritiek, wel relevant voor traceability bij latere klant- of audit-vragen. Aparte sessie.

- [ ] **Notitie HLM-flow (22-05-2026)** *(geen losse fix nodig)*: HLM-flow heeft eigen client-side birth_year/gender via localStorage en eigen norm-tabel in `hlm/meting_src.html` die divergeert van `hrv.js`. Meenemen in HLM Pro nieuwe generatie doorontwikkeling (~1 aug 2026) vanaf de start.

- [ ] **HLM zone-labels oude pré-rebrand terminologie (05-06-2026)**: `templates/hlm/kwadrant.html` regel 107 (`ZL`-array: 'Schwerer Stress'/'Stress'/'Leichter Stress' DE, 'Zware stress'/'Stress'/'Lichte stress' NL) en regel 149 (comment) gebruiken nog de stress-familie i.p.v. de rebrand belast-familie (Zwaar belast/Belast/Licht belast/In balans/Veerkrachtig — DE: Schwer belastet/.../Vital). Bewust **niet** meegenomen in de menu.html-fix van 05-06: HLM is een apart spoor (unproven product-fit, deploy only when ready) in aparte klantcontext. Bij HLM-activering automatisch op tafel; consolideren naar dezelfde canonieke bron (`analytics.py` RI_ZONES / `static/js/hrv.js` getLabel) als de consumer-flow.

## Design-keuzes (geen actie nodig)

- **NL-aanspreekvorm split** (bevestigd 22-05-2026): educatieve templates (`welcome.html`, `faq.html`, `upgrade.html`, `profile.html`, `waarschuwing.html`) hanteren **je-vorm**; juridische/activatie-templates (`privacy.html`, `license.html`, `koppelen.html`, plus de toelichting op `/licentie` onder de submit-knop) hanteren **u/uw-vorm**. Bewuste design-keuze, geen technische schuld. DE-equivalent: consumer-flow gebruikt overal `Sie/Ihr` (formeel), niet `du` zoals oorspronkelijk vermoed.
