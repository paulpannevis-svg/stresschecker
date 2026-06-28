# Kill-Switch: Data-Retention-Jobs pauzeren

> **Status (2026-06-28): er draaien NU GEEN automatische retention-jobs.**
> Fase 1 (commit `8cfed45`) is volledig niet-destructief. `soft_delete_user()` bestaat
> als helper maar wordt **nergens automatisch aangeroepen** (geen cron, geen endpoint).
> Er is dus op dit moment niets dat klantdata wijzigt of verwijdert — deze kill-switch
> is een **voorbereiding** voor zodra Fase 2 (hard-delete) cron-jobs installeert.

## Belangrijke feiten (lees eerst)

- De `users`-tabel met `archived_at` staat in **`/opt/ic-license-server/data/saas_licenses.db`**
  (NIET in `sc_pro.db` — die heeft een ándere `users`-tabel zonder `archived_at`).
- "Deelnemers" (Pro-cliënten) met `archived_at` staan in `/opt/stresschecker/data/sc_pro.db` (`clients`).
- Audit-trail: `saas_licenses.db` → tabel `data_lifecycle_log`.
- De app-master draait als root, PID-bestand/proces: `pgrep -f 'gunicorn.*8080'`.

## Snelle pauze (zodra Fase 2-crons bestaan)

Je bent al op de VPS (de app draait hier). De Fase-2-jobs zullen óf in de **root-crontab**
óf als **systemd-timer** geïnstalleerd zijn — controleer beide:

```bash
# crontab-variant
crontab -l | grep -iE "retention|hard_delete|archive_invoice"
# systemd-timer-variant
systemctl list-timers | grep -i retention
```

Pauzeren (crontab-variant): zet `#` voor de retention-regels:
```bash
crontab -e        # comment de retention_* regels uit
crontab -l | grep -iE "retention" | grep -v '^#'   # moet LEEG zijn = gepauzeerd
```

Pauzeren (systemd-variant):
```bash
systemctl stop  retention-hard-delete.timer
systemctl disable retention-hard-delete.timer
systemctl list-timers | grep -i retention          # mag niets actiefs tonen
```

## Draait er nu een job? (vóór pauzeren controleren)

```bash
ps aux | grep -E "retention" | grep -v grep
```
- Geen processen → veilig pauzeren.
- Wel een proces → een hard-delete loopt; **NIET killen midden in een transactie**.
  Wacht tot het klaar is (kijk in het logbestand dat Fase 2 definieert), pauzeer dán de timer.

## Read-only controle: hoeveel users zijn gearchiveerd?

```bash
sqlite3 /opt/ic-license-server/data/saas_licenses.db \
  "SELECT COUNT(*) FROM users WHERE archived_at IS NOT NULL;"
```
Dit verwijdert niets (puur tellen). Gearchiveerd = logisch verborgen, data staat er nog.

Verlopen >180d (Fase-2-hard-delete-kandidaten) bekijken zónder iets te wijzigen — gebruik het
read-only rapport (admin-token vereist, zie `fase2-runbook.md` §"Dry-run"):
```bash
curl -s -H "X-Admin-Token: $ADMIN_KK_TOKEN" http://127.0.0.1:8080/admin/retention-dryrun
```

## Hervatten

Crontab: verwijder de `#` weer (`crontab -e`), controleer:
```bash
crontab -l | grep -iE "retention" | grep -v '^#'
```
Systemd: `systemctl enable --now retention-hard-delete.timer`.

## Noodgeval / twijfel

Bij juridische onzekerheid of een verdachte run: **pauzeer eerst** (bovenstaand), dan onderzoeken.
Soft-delete is omkeerbaar (`restore_user()` zet `archived_at/retention_until/archived_reason` terug
op NULL). Hard-delete (Fase 2) is dat NIET — daar geldt: backup-restore (zie `fase2-runbook.md`
§ROLLBACK).
