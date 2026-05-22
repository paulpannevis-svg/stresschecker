# StressChecker — Recente wijzigingen

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
