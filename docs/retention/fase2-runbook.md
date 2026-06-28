# Fase 2 Runbook: Hard-Delete activeren (DESTRUCTIEF)

> ⚠️ **Fase 2 verwijdert data PERMANENT en is onomkeerbaar (m.u.v. backup-restore).**
>
> ⚠️ **De scripts/crons in dit runbook BESTAAN NOG NIET.** Dit is het **doelontwerp +
> checklist**; ze worden pas in Fase 2 gebouwd. Onderstaande paden
> (`/opt/stresschecker/cron/retention_*.sh`, `logs/retention.log`) zijn voorgestelde
> conventies, geen bestaande bestanden. Finaliseer dit runbook bij de Fase-2-bouw.

## Openstaande blokkers vóór Fase 2 (niet overslaan)

1. **Juridische/DPO-toets** — 10 jr AO-bewaarplicht voor facturen, erasure-vs-archivering,
   180d soft-delete-venster. Geen code-beslissing.
2. **Betrouwbare verlop-datum-bron.** `users.license_expires` is een **stale activatie-datum**
   die opzegging NIET weerspiegelt (voorbeeld: Paul-M license_expires 2026-09-14 terwijl het
   abonnement op 2026-06-17 is opgezegd). Alleen `subscriptions.current_period_end` is
   gezaghebbend, en alleen voor de Stripe-cohort. De hard-delete-cron MOET dezelfde logica als
   `pro_access_state()` / de dry-run gebruiken, niet kaal `license_expires`.
3. **Gevalideerde dry-run** — weken laten draaien tot bewezen is dat hij nooit een actieve
   klant aanwijst.
4. **Geteste restore** + verplicht "rapporteer-dan-verwijder-alleen-het-gerapporteerde"-patroon
   + werkende kill-switch (zie `kill-switch.md`).

## Pre-check (verplicht)

### Juridisch
- [ ] Juridisch/DPO-advies: "retention-hard-delete mag aktief"
- [ ] Privacy Policy finaal (Paul) + live
- [ ] Offline backup-/archiefstrategie gereed
- [ ] Audit-trail (`data_lifecycle_log`) gereviewd

### Technisch
- [ ] DB-backups actueel (zie `backup.sh`; Fase-1-snapshots `*.bak-retention-*` bestaan al)
- [ ] Dry-run: hoeveel users verlopen >180d? (veld `phase2_hard_delete_candidates`)
- [ ] `data_lifecycle_log`: geen fouten in Fase 1
- [ ] Kill-switch getest

### Communicatie
- [ ] Klanten geïnformeerd ("data wordt na 180d permanent verwijderd")
- [ ] Privacy Policy live ("6 maanden soft-delete, dan permanent")

## Stap 1 — Backup vóór hard-delete

Let op de **juiste paden**: `users`/`subscriptions`/`data_lifecycle_log` in
`/opt/ic-license-server/data/saas_licenses.db`; cliënten/metingen in `/opt/stresschecker/data/`.

```bash
D=$(date +%Y%m%d-%H%M%S)
cp /opt/ic-license-server/data/saas_licenses.db /opt/ic-license-server/data/saas_licenses.db.bak-fase2-$D
cp /opt/stresschecker/data/sc_pro.db            /opt/stresschecker/data/sc_pro.db.bak-fase2-$D
cp /opt/stresschecker/data/sc_measurements.db   /opt/stresschecker/data/sc_measurements.db.bak-fase2-$D
# offline tarball
tar czf /opt/backups/stresschecker-fase2-pre-$D.tar.gz \
  /opt/ic-license-server/data/saas_licenses.db /opt/stresschecker/data/sc_pro.db /opt/stresschecker/data/sc_measurements.db
```

## Stap 2 — Dry-run finale (READ-ONLY, niets wordt verwijderd)

De dry-run vereist een **admin-token** (env `ADMIN_KK_TOKEN`, header `X-Admin-Token` of `?token=`):

```bash
curl -s -H "X-Admin-Token: $ADMIN_KK_TOKEN" http://127.0.0.1:8080/admin/retention-dryrun | python3 -m json.tool
```

**Werkelijke** output-vorm (Fase 1, commit `8cfed45`):
```json
{
  "generated_at": "2026-...",
  "soft_delete_window_days": 180,
  "note": "READ-ONLY rapport. Verwijdert niets. phase2_hard_delete_candidate=verlopen >180d.",
  "total_expired": 1,
  "phase2_hard_delete_candidates": 0,
  "records": [
    {"user_id": 12, "email": "...", "expired_on": "2026-06-17", "source": "stripe_subscription",
     "days_expired": 11, "already_archived": false, "phase2_hard_delete_candidate": false,
     "deelnemers": 3, "metingen": 66}
  ]
}
```
> NB: er is (nog) GEEN `would_archive_invoices`-veld — invoice-archivering is apart Fase-2-werk
> en heeft geen lokale invoices-tabel als bron (facturen leven bij Stripe + `billing_events`).

Controleer: kloppen de users? Kloppen de datums + de `source`? False-positives?
**STOP als íéts raar is.**

## Stap 3 — Hard-delete activeren (nadat de scripts gebouwd zijn)

De Fase-2-cron moet: (a) alleen rijen raken die de dry-run als kandidaat rapporteerde,
(b) per verwijdering een `data_lifecycle_log`-regel `action='deleted'` schrijven, (c) faalzacht +
kill-switch-baar zijn. Voorbeeld-crontab (root):
```cron
# Retention hard-delete: users met retention_until < nu (alleen gerapporteerde kandidaten)
0 3 * * * /opt/stresschecker/cron/retention_hard_delete.sh >> /opt/stresschecker/logs/retention.log 2>&1
```

## Stap 4 — Eerste run + monitoren

```bash
/opt/stresschecker/cron/retention_hard_delete.sh        # handmatige eerste run
tail -f /opt/stresschecker/logs/retention.log
```
Verwacht (doelformaat): `[DATA-DELETED] user=… reason=subscription_expired …` +
`[RETENTION-JOB] hard_delete completed: N users, 0 errors`. Bij fouten → kill-switch (zie
`kill-switch.md`), onderzoek, herstel.

## Stap 5 — Verificatie (read-only)

```bash
# Geen achterstallige kandidaten meer over?
sqlite3 /opt/ic-license-server/data/saas_licenses.db \
  "SELECT COUNT(*) FROM users WHERE archived_at IS NOT NULL AND retention_until < datetime('now');"
# Audit-trail bewaard?
sqlite3 /opt/ic-license-server/data/saas_licenses.db \
  "SELECT COUNT(*) FROM data_lifecycle_log WHERE action='deleted';"
```

## Stap 6 — Audit-trail archiveren

```bash
sqlite3 -header -csv /opt/ic-license-server/data/saas_licenses.db \
  "SELECT * FROM data_lifecycle_log;" > /opt/backups/audit-trail-$(date +%Y%m%d).csv
# offline bewaren (≥3 jaar)
```

## ROLLBACK (nood)

```bash
# 1. pauzeer Fase 2 (zie kill-switch.md)
# 2. restore de JUISTE DB's uit de Fase-2-pre-backup (gebruik de echte bestandsnamen uit Stap 1)
cp /opt/ic-license-server/data/saas_licenses.db.bak-fase2-<D> /opt/ic-license-server/data/saas_licenses.db
cp /opt/stresschecker/data/sc_pro.db.bak-fase2-<D>            /opt/stresschecker/data/sc_pro.db
cp /opt/stresschecker/data/sc_measurements.db.bak-fase2-<D>   /opt/stresschecker/data/sc_measurements.db
# 3. HUP (alleen nodig als ook code wijzigde; de gates lezen de DB live)
kill -HUP $(pgrep -f 'gunicorn.*8080' | head -1)
# 4. verifieer
curl -s -H "X-Admin-Token: $ADMIN_KK_TOKEN" http://127.0.0.1:8080/admin/retention-dryrun | python3 -m json.tool
```
