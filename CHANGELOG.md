# StressChecker — Recente wijzigingen

## 2026-05-21

- Nieuw plan-type `sc-{pro-m,pro-s,consumer}-eval` — 90-dagen evaluatielicenties voor partner-outreach (eerste case: Mühlberger DGBfb, later KKH/Barmer pilots). UI-label "Evaluatielicentie/Evaluierungslizenz/Evaluation license" via uitbreiding `PRO_PERIOD_LABELS`. Geen Stripe-koppeling. Data-behoud bij upgrade naar regulier abonnement via e-mail-hash (bestaand model). `origin='evaluation'` als 5e taxonomie-waarde. Marketing-branch in /activate verbreed naar `IN ('marketing','evaluation')` met plan-driven expiry-helper `_compute_license_expires_at()` (vervangt hardcoded 365d). Activation-log gebruikt nu `activate_{origin}` voor cohort-tracking. Generator `/opt/ic-license-server/generate_eval_license.py` (niet in git, naast saas_licenses.db). Centrale constante `EVAL_DURATION_DAYS=90` in `eval_config.py` — single source of truth voor zowel app.py als generator.
- Latente issue gefixt (mede gemerkt tijdens eval-werk): `licenses.expires_at` en `licenses.valid_until` werden inconsistent gevuld door marketing-branch (alleen `expires_at`). Nu beide gesynchroniseerd om validator-pad (dat `valid_until` leest) gelijk te houden met activatieflow (dat `expires_at` schreef).
- Follow-up: consumer-eval UI op /instellingen out-of-scope MVP — `get_pro_tier_summary` blijft `type='pro' AND product='sc'`-gated; consumer-eval-licenties krijgen wel correcte DB-state en activatie maar geen widget. Pas adresseren als concrete consumer-eval-recipiënt zich aandient.
- /instellingen UX-fix — Pro-abonnement label nu taal-consistent (Jaarabonnement/Jahresabonnement/Annual subscription via plan-code mapping i.p.v. Stripe product.name). Licentiecode-label expliciet gemaakt met helptekst voor activatie op nieuw apparaat. NL/DE/EN visueel geverifieerd.
- Pro-tier widget op /pro + /instellingen voor alle Pro-cohorts (was Stripe-only). Toont tier (Pro S/M/L), actieve koppelingen vs. max_clients en geldigheid; afgeleid uit licenses + plans, Stripe-onafhankelijk.
- git init + initial commit op /opt/stresschecker/ (lokale repo, geen remote).
- .gitignore aangemaakt (secrets, backups, databases, CONTEXT.md, .claude/).
- CHANGELOG.md + gen_context.py-integratie: CONTEXT.md krijgt voortaan automatisch een 'Recente wijzigingen'-sectie uit CHANGELOG.md.
- CLEANUP_TODO.md aangemaakt voor latere opruiming root-level artefacten (app.py.current, saas_licenses.db in root, etc.).
