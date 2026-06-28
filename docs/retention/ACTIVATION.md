# Fase 2 — Cron-activering (ná juridische clearing)

> **Status 2026-06-28: DORMANT.** `retention.py` is gebouwd + getest, maar er draait
> **geen** automatische job. De crons hieronder staan **niet** in de crontab. De
> GDPR-anonimisering (`POST /api/user/delete-me`) is wél live, maar opt-in per gebruiker
> (geen automatiek, geen UI-knop bedraad).

## Voorwaarden vóór activering (niet overslaan)

- [ ] Juridische/DPO-clearing: "retention auto-soft-delete + hard-delete mag actief"
- [ ] Privacy Policy finaal + live ("6 maanden soft-delete, dan permanent")
- [ ] Dry-run wekenlang gevalideerd: nooit een actieve klant geflagd
      (`python3 retention.py --auto-soft-delete` toont 0 valse kandidaten)
- [ ] Verse backups aanwezig (`backup.sh`)
- [ ] Kill-switch getest (`docs/retention/kill-switch.md`)

## Stap 1 — auto-soft-delete activeren (OMKEERBAAR)

Eerst dry-run inspecteren:
```bash
cd /opt/stresschecker
python3 retention.py --auto-soft-delete            # rapport, wijzigt niets
```
Daarna in crontab opnemen:
```bash
crontab -e
# voeg toe (UTC):
0 2 * * * /opt/stresschecker/cron/auto_soft_delete.sh
```
Verifiëren:
```bash
crontab -l | grep auto_soft_delete
tail -f /opt/stresschecker/logs/retention.log
```
Een per ongeluk gearchiveerde user is te herstellen via `restore_user(user_id)` (app.py)
of door `archived_at/retention_until/archived_reason` op NULL te zetten.

## Stap 2 — hard-delete activeren (ONOMKEERBAAR — laatste stap)

Hard-delete heeft een **dubbele grendel**: het script staat in geen cron, én
`retention.py` weigert te verwijderen zonder `RETENTION_HARD_DELETE_CLEARED=1`.

Eerst dry-run:
```bash
python3 retention.py --hard-delete                 # rapport, verwijdert niets
```
Pas ná expliciete clearing in crontab (let op de env-var op de regel):
```bash
crontab -e
0 3 * * * RETENTION_HARD_DELETE_CLEARED=1 /opt/stresschecker/cron/hard_delete.sh
```
`hard_delete.sh` maakt vóór elke run automatisch een `*.bak-fase2-<ts>` snapshot.

## Stap 3 — na activering

```bash
kill -HUP <gunicorn-master-pid>     # alleen nodig bij app.py-wijziging, niet voor cron
```
Monitor `logs/retention.log` en `data_lifecycle_log` (acties `archived`, `deleted`).

## Pauzeren / rollback

- Pauzeren: comment de regels in `crontab -e` (zie `kill-switch.md`).
- Herstel uit backup: `docs/retention/rollback_restore.sh <suffix> --confirm`.
