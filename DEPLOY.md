# DEPLOY.md — Staging → Productie promotie-procedure

Korte operationele gids. Volledige context in `CONTEXT.md` (sectie *Werkwijze & Leerpunten*)
en `CHANGELOG.md` (entry 06-06-2026 "Staging volledig operationeel").

## Omgevingen

| | Prod | Staging |
|---|---|---|
| Worktree | `/opt/stresschecker` (branch `main`) | `/opt/stresschecker-staging` (branch `staging`) |
| Service | `stresschecker.service` (gunicorn :8080) | `stresschecker-staging.service` (gunicorn :8090) |
| URL | `stresschecker.com` | `test.stresschecker.com` (Basic-Auth, user `paul`) |
| SC_ENV | *afwezig* | `staging` (via `EnvironmentFile=.env.staging`) |
| DB's | live `/opt/stresschecker/data/` + `/opt/ic-license-server/data/` | gescrubde kopieën `/opt/stresschecker-staging/data/` |
| Mail | echte SendGrid-verzending | onderdrukt (`[STAGING-MAIL]`-print via SC_ENV-guard) |

Beide units draaien met `--no-control-socket` (zie CHANGELOG: gunicorn fork-hang).

## Standaard-werkstroom (STAGING-FIRST)

1. **Bouwen + verifiëren op staging** — werk in `/opt/stresschecker-staging` (branch `staging`).
   Draai waar relevant `tests/run_all.sh`. Reload de staging-worker:
   `kill -HUP $(systemctl show stresschecker-staging.service -p MainPID --value)`.
2. **Paul checkt** op `test.stresschecker.com`.
3. **Merge `staging` → `main`** (commit-identity: `git -c user.name='Paul Pannevis' -c user.email='paulpannevis@gmail.com' …`).
4. **Promotie naar prod** — in `/opt/stresschecker`: breng `main` binnen, dan herlaad (zie hieronder).

> Hotfixes direct op prod blijven mogelijk, maar zijn de **uitzondering**, niet de regel.

## HUP vs. restart (prod herladen)

- **`kill -HUP <master-pid>`** — graceful: recyclet workers, herlaadt **templates + route-tabel + Python-code**.
  Voldoende voor template-, route- en app.py-wijzigingen. Geen downtime.
  `kill -HUP $(systemctl show stresschecker.service -p MainPID --value)`
  (`systemctl reload` is **niet** beschikbaar op deze unit.)
- **`systemctl restart stresschecker`** — volledige herstart. Nodig bij: gewijzigde
  `ExecStart`/unit/env, nieuwe dependencies, of wanneer een schone start gewenst is.
  Let op de historische **fork-hang** — `--no-control-socket` staat in de unit en lost dit op.

Na herladen: smoke-check `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/login` → `200`.

## Staging-data verversen

`sudo /opt/stresschecker-staging/refresh_data.sh` — stopt staging, kopieert live-DB's **read-only/eenrichting**,
draait de **verplichte** PII-scrub (`scrub_pii.py`; bij ook maar één echt e-mailadres faalt het script en
blijft de service gestopt), start staging weer. Live-data wordt nooit gewijzigd.

## Prod-only testbaar (kan niet/onvolledig op staging)

- **Echte mailverzending** (SendGrid) — op staging onderdrukt door de SC_ENV-guard.
- **Stripe Customer Portal end-to-end** — vereist echte Stripe-customer/abonnement (zie CONTEXT.md
  *Spoor 3*); staging heeft gescrubde data zonder live customer-koppeling.
- **Inkomende webhooks** (Stripe/PayPal naar de license-server) en andere live externe callbacks.
- **Gedrag op echte productie-datavolumes / echte klantrecords** — staging draait op gescrubde kopieën.
