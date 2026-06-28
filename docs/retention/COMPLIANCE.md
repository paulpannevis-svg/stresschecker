# Compliance Notes — Data Retention (DSGVO)

## Fase 1 — status (commit `8cfed45`, live 2026-06-28)

| Onderdeel | Status |
|---|---|
| Audit-trail (`data_lifecycle_log`) | ✅ LIVE |
| GDPR data-export (`GET /api/user/data-export`) | ✅ LIVE |
| Reversibele soft-delete (`soft_delete_user`/`restore_user`) | ✅ KLAAR (helper, geen auto-trigger) |
| Dry-run rapport (`GET /admin/retention-dryrun`, admin-token) | ✅ LIVE |
| UI archiverings-banner (`/menu`, `/pro`) | ✅ LIVE |
| Hard-delete / cron / cascade / anonimisering / invoice-archief | ⛔ Fase 2 (niet gebouwd) |
| Juridische/DPO-clearing | ⏳ PENDING |
| Privacy Policy finaal | ⏳ PENDING (Paul) |

**Bewaartermijn-parameters:** soft-delete-venster = `RETENTION_SOFT_DELETE_DAYS = 180` (app.py).

## Waar staat wat (feitelijk)

- `users` (+ `archived_at`, `retention_until`, `archived_reason`), `subscriptions`,
  `data_lifecycle_log`, `licenses`, `billing_events`: **`/opt/ic-license-server/data/saas_licenses.db`**.
- "Deelnemers" = Pro-cliënten (`clients` + `archived_at`), `client_metingen`:
  **`/opt/stresschecker/data/sc_pro.db`**.
- Consumer-metingen (`metingen`, key = `user_key` = sha256(email)[:32]):
  **`/opt/stresschecker/data/sc_measurements.db`**.
- `data_lifecycle_log`-acties nu: `archived`, `restored`, `exported`, `dryrun`.
  Fase 2 voegt toe: `deleted`, `anonymized`.

## Wat moet nog (vóór Fase 2)

- [ ] Juridische/DPO-clearing (Paul)
- [ ] Privacy Policy finaal + live (Paul)
- [ ] Betrouwbare verlop-datum-bron vaststellen (NIET `license_expires`; zie runbook §blokkers)
- [ ] Dry-run weken valideren (nooit een actieve klant flaggen)
- [ ] Fase-2-scripts bouwen + kill-switch end-to-end testen

## Blocker-audit 2026-06-28 (5 punten gereviewd vóór Fase 2)

1. **DB-pad** — ⚠️ De aanname "users staat in sc_pro.db / saas_licenses.db users verwijderen" is
   **ONJUIST en gevaarlijk**. Geverifieerd: `saas_licenses.db.users` is gezaghebbend (20 rijen, volledig
   schema incl. password_hash/license_expires/stripe_*; `DB_PATH` wijst hier; 18 auth-queries lezen het)
   en bevat de retentie-kolommen. `sc_pro.db.users` = vestigiale 1-rij-stub, **nergens gelezen**. De
   retentie-code leest al de juiste DB. **NOOIT de saas_licenses.db users-tabel verwijderen/migreren.**
   (Losse opruimkandidaat: de 1-rij `sc_pro.db.users` — apart, met back-up, niet nu.)
2. **Kill-switch** — Fase 1 heeft GEEN crons (niets te pauzeren); docs benoemen dit. ✅
3. **Dry-run auth** — `/admin/retention-dryrun` is token-gegate via `_admin_kk_authorized()` (fail-closed,
   constant-time); anoniem → 403 (getest). Logt `[DRY-RUN]`. ✅
4. **Rollback** — corrigeerd: `rollback_restore.sh` (juiste paden, integrity_check, pre-rollback-snapshot,
   graceful HUP i.p.v. kill -9, dynamische master-PID, `--confirm`-vereist). Inert tot handmatig gebruik. ✅
5. **Hard-delete-logica** — pure beslissingshelper `should_hard_delete(email, retention_until)` in app.py
   hergebruikt `pro_access_state` (Stripe `current_period_end` → `license_expires`-fallback), NIET kaal
   `license_expires`. 5 testgevallen groen (o.a. canceled sub + license_expires-toekomst → DELETE).
   **Executie blijft ongebouwd** tot juridische clearing. ✅

## Support / verwijzingen

- Jobs pauzeren? → `kill-switch.md`
- Fase 2 activeren? → `fase2-runbook.md`
- Audit-trail inzien (read-only):
  `sqlite3 /opt/ic-license-server/data/saas_licenses.db "SELECT * FROM data_lifecycle_log ORDER BY id DESC LIMIT 50;"`
