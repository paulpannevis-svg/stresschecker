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
