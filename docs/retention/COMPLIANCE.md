# Compliance Notes — Data Retention (DSGVO)

## Fase 1 — status (commit `8cfed45`, live 2026-06-28)

| Onderdeel | Status |
|---|---|
| Audit-trail (`data_lifecycle_log`) | ✅ LIVE |
| GDPR data-export (`GET /api/user/data-export`) | ✅ LIVE |
| Reversibele soft-delete (`soft_delete_user`/`restore_user`) | ✅ KLAAR (helper, geen auto-trigger) |
| Dry-run rapport (`GET /admin/retention-dryrun`, admin-token) | ✅ LIVE |
| UI archiverings-banner (`/menu`, `/pro`) | ✅ LIVE |
| Juridische/DPO-clearing | ⏳ PENDING |
| Privacy Policy finaal | ⏳ PENDING (Paul) |

**Bewaartermijn-parameters:** soft-delete-venster = `RETENTION_SOFT_DELETE_DAYS = 180` (app.py).

## Fase 2 — status: SAFE DORMANT (code gebouwd + getest, auto-jobs UIT)

> Code is gebouwd en op kopie-DB's getest; de **automatische** jobs draaien NIET en
> wachten op juridische clearing. Alleen de opt-in GDPR-anonimisering (per gebruiker,
> geen automatiek) is live als API.

| Onderdeel | Status |
|---|---|
| `retention.py` (standalone CLI, géén `import app`) | ✅ GEBOUWD + GETEST (kopie-DB) |
| `auto_soft_delete_expired_users()` (gezaghebbende logica, niet kaal `license_expires`) | ✅ GETEST · ⏸️ dry-run-default, géén cron |
| `hard_delete_archived_users()` (>180d + her-verificatie, cascade) | ✅ GETEST · ⏸️ dubbele grendel (geen cron + `RETENTION_HARD_DELETE_CLEARED=1`) |
| GDPR Right to Erasure — anonimisering (`POST /api/user/delete-me`) | ✅ LIVE (opt-in, eigen account, `confirm`=eigen e-mail; geen UI-knop) |
| `data_lifecycle_log`-acties `anonymized` + `deleted` | ✅ getest (audit-trail compleet) |
| Cron `auto_soft_delete.sh` / `hard_delete.sh` | ⏸️ DORMANT (bestaan, NIET in crontab) |
| Invoice-archief | ➖ N.v.t. — geen lokale `invoices`-tabel; facturen + 10jr-bewaring in Stripe |
| Auto-soft-delete + hard-delete LIVE zetten | ⛔ wacht op juridische clearing (zie `ACTIVATION.md`) |

**Belangrijke correcties t.o.v. het oorspronkelijke spec-concept:**
- Auto-soft-delete gebruikt de **gezaghebbende** verlop-bron (`subscriptions.current_period_end`
  via licenses-join → `license_expires`-fallback), NIET kaal `license_expires`. Een live dry-run
  op de echte data toont op 2026-06-28 reeds **1 reële kandidaat (user 6, verlopen Stripe-sub)** —
  precies waarom de cron dormant blijft tot validatie + clearing.
- `email`/`password_hash` (users) en `name` (clients) zijn `NOT NULL`; anonimisering zet daarom een
  **tombstone** (`anon-<id>@deleted.invalid`, `ANONYMIZED_DISABLED`) i.p.v. `NULL`.
- Er is **geen lokale `invoices`-tabel**; de spec-stap "invoices archiveren" verviel.

**Activering (na clearing):** zie `ACTIVATION.md`. **Pauzeren/rollback:** `kill-switch.md` / `rollback_restore.sh`.

## Waar staat wat (feitelijk)

- `users` (+ `archived_at`, `retention_until`, `archived_reason`), `subscriptions`,
  `data_lifecycle_log`, `licenses`, `billing_events`: **`/opt/ic-license-server/data/saas_licenses.db`**.
- "Deelnemers" = Pro-cliënten (`clients` + `archived_at`), `client_metingen`:
  **`/opt/stresschecker/data/sc_pro.db`**.
- Consumer-metingen (`metingen`, key = `user_key` = sha256(email)[:32]):
  **`/opt/stresschecker/data/sc_measurements.db`**.
- `data_lifecycle_log`-acties: `archived`, `restored`, `exported`, `dryrun` (Fase 1) +
  `anonymized`, `deleted` (Fase 2 — bereikbaar via de live GDPR-erasure-endpoint).

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
