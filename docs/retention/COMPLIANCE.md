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

## Support / verwijzingen

- Jobs pauzeren? → `kill-switch.md`
- Fase 2 activeren? → `fase2-runbook.md`
- Audit-trail inzien (read-only):
  `sqlite3 /opt/ic-license-server/data/saas_licenses.db "SELECT * FROM data_lifecycle_log ORDER BY id DESC LIMIT 50;"`
