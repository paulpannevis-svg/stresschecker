# StressChecker — docs

## Data Retention (DSGVO)

- [Compliance-status](./retention/COMPLIANCE.md) — wat is live, wat staat open
- [Fase 1 — Soft-delete & kill-switch (omkeerbaar)](./retention/kill-switch.md)
- [Fase 2 — Hard-delete runbook (destructief, NOG NIET gebouwd)](./retention/fase2-runbook.md)

**Fase 1 live** (commit `8cfed45`, 2026-06-28): audit-trail, GDPR-export, reversibele
soft-delete, dry-run rapport. **Fase 2** (hard-delete) wacht op juridische clearing +
een betrouwbare verlop-datum-bron.

## Overige ontwerp-/runbook-docs

- `ARITMIE_DETECTIE_ONTWERP.md`, `KWALITEITS_GATE_ONTWERP.md`
- `MIGRATIE_PLAN_DIV25_VERWIJDEREN.md`, `PROMOTIE_RUNBOOK_DIV25_GATE.md`
- `IJKMETING_PLAN_SENSORFACTOR.md`, `KONTAKT_FORMULAR_HANDLEIDING.md`, `LAUNCH_LOG.md`

> NB: `CONTEXT.md` (repo-root) is auto-gegenereerd door `gen_context.py` (DB-schema's) en is
> gitignored. Wijzigingshistorie staat in `CHANGELOG.md`.
