# StressChecker — Uitvoeringsplan staging-/ontwikkelomgeving op de VPS

*Opgesteld 2026-06-03. **STATUS: PLAN — nog niet uitgevoerd.** Dit document beschrijft de stappen; er is niets aan het draaiende systeem gewijzigd. Voer pas uit na akkoord ([[feedback_plan_review_workflow]]).*

---

## 0. Uitgangssituatie (vastgesteld, read-only)

| Component | Hoe het nu draait |
|-----------|-------------------|
| Live app | gunicorn `app:app`, `127.0.0.1:8080`, systemd `stresschecker.service`, WorkingDirectory `/opt/stresschecker` |
| License-server | gunicorn `server:app`, `127.0.0.1:5000`, systemd `ic-license-server.service`, `/opt/ic-license-server` |
| nginx | `app.stresschecker.com` → 8080 · `api.stresschecker.com` + `api.lifestylemonitors.com` → 5000 |
| Live DB's | meting: `/opt/stresschecker/data/sc_measurements.db` · pro: `/opt/stresschecker/data/sc_pro.db` · license: `/opt/ic-license-server/data/saas_licenses.db` |
| DB-config | `app.py:131-133`: `SC_DB_PATH`, `SC_METING_DB`, `SC_PRO_DB` — alle drie env-overridebaar |
| Git | repo in `/opt/stresschecker`, branch `main`, **geen remote** (lokaal) |
| Mail | SendGrid via `os.environ['SENDGRID_API_KEY']` in `send_verification_code`/`send_password_reset_email` (app.py:23,45,…), in try/except |
| Stripe | secret uit bestand `SPOOR3_STRIPE_KEYS_FILE = '/opt/ic-license-server/data/stripe_keys.conf'` (app.py:6100-6109, **hardcoded constante**) |
| Secrets (.env) | `ADMIN_KK_TOKEN`, `ANTHROPIC_API_KEY`, `MAIL_FROM`, `SC_SECRET_KEY`, `SENDGRID_API_KEY`, `STRIPE_SECRET_KEY` |

### ⚠ Het allerbelangrijkste gevaar (stuurt het hele ontwerp)
De **defaults** in `app.py:132-133` wijzen naar de **live** databases:
```python
METING_DB_PATH = os.environ.get('SC_METING_DB', '/opt/stresschecker/data/sc_measurements.db')
PRO_DB_PATH    = os.environ.get('SC_PRO_DB',    '/opt/stresschecker/data/sc_pro.db')
```
→ Als staging een env-var vergeet te zetten, valt het **stilzwijgend terug op de live-DB**. Eén ontbrekende `Environment=`-regel = staging schrijft in productie. Het ontwerp hieronder maakt dat **fysiek onmogelijk** via een aparte OS-gebruiker + startup-guard, niet alleen via "goed opletten".

---

## 1. Architectuur

**Principe:** staging is een **tweede, volledig losstaande instantie** op dezelfde VPS — eigen map, eigen poort, eigen systemd-unit, eigen DB-kopieën, eigen OS-gebruiker. De live-processen (8080, 5000) worden niet aangeraakt.

| Aspect | Live | Staging |
|--------|------|---------|
| Map | `/opt/stresschecker` | `/opt/stresschecker-staging` (git **worktree**, zie §4) |
| Poort | 8080 | **8090** (vrij; 80/443/5000/8080 zijn bezet) |
| systemd | `stresschecker.service` | `stresschecker-staging.service` (nieuw) |
| OS-gebruiker | root | **`scstaging`** (nieuw, geen schrijfrechten op live-mappen) |
| Data | `/opt/stresschecker/data` | `/opt/stresschecker-staging/data` (kopieën) |
| Bereikbaar | `app.stresschecker.com` (publiek) | intern `127.0.0.1:8090` (default), optioneel `staging.stresschecker.com` met Basic-Auth |

### 1a. Aparte OS-gebruiker (waterdichte scheiding-laag)
```bash
# Later uitvoeren:
useradd --system --home /opt/stresschecker-staging --shell /usr/sbin/nologin scstaging
# scstaging krijgt schrijfrechten ALLEEN op de staging-mappen:
chown -R scstaging:scstaging /opt/stresschecker-staging
# Live-datamappen blijven van root en blijven voor scstaging read-only:
chmod 0755 /opt/stresschecker/data /opt/ic-license-server/data   # geen world-write
# (scstaging is niet de eigenaar en zit niet in een groep met schrijfrecht → kan live-DB's
#  hooguit LEZEN, nooit schrijven. Een verkeerd pad faalt dan met "readonly database".)
```

### 1b. Staging systemd-unit (nieuw bestand, raakt live niet)
`/etc/systemd/system/stresschecker-staging.service`:
```ini
[Unit]
Description=StressChecker STAGING
After=network.target

[Service]
User=scstaging
Group=scstaging
WorkingDirectory=/opt/stresschecker-staging
EnvironmentFile=/opt/stresschecker-staging/.env.staging
ExecStart=/usr/local/bin/gunicorn --workers 1 --bind 127.0.0.1:8090 --timeout 600 app:app
Restart=always

[Install]
WantedBy=multi-user.target
```
Beheer uitsluitend via `systemctl start/stop/restart stresschecker-staging` — **nooit** `stresschecker` (zonder suffix).

### 1c. nginx (optioneel, alleen als web-toegang gewenst)
Nieuw bestand `/etc/nginx/sites-available/stresschecker-staging` (apart van de live-site), met **Basic-Auth** zodat het niet publiek/geïndexeerd is:
```nginx
server {
    listen 443 ssl;
    server_name staging.stresschecker.com;
    ssl_certificate     /etc/letsencrypt/live/staging.stresschecker.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/staging.stresschecker.com/privkey.pem;
    auth_basic "staging"; auth_basic_user_file /etc/nginx/.htpasswd-staging;
    add_header X-Robots-Tag "noindex, nofollow" always;
    location /static/ { alias /opt/stresschecker-staging/static/; expires 0; }
    location / { proxy_pass http://127.0.0.1:8090; proxy_set_header Host $host; add_header Permissions-Policy "bluetooth=*"; }
}
```
**Eenvoudigste/veiligste variant:** sla nginx over en bereik staging via een SSH-tunnel: `ssh -L 8090:127.0.0.1:8090 root@<vps>` → open `http://localhost:8090`. Geen publieke blootstelling, geen extra cert. *(Let op: Web Bluetooth vereist HTTPS of localhost — een SSH-tunnel naar `localhost:8090` voldoet aan de localhost-uitzondering; de demo-sensor werkt sowieso zonder Bluetooth.)*

---

## 2. Database-scheiding (kritisch)

### 2a. Staging-datamap + eenmalige kopie
```bash
mkdir -p /opt/stresschecker-staging/data
# Gebruik de SQLite backup-API, NIET `cp` — cp op een live-DB die midden in een
# schrijfactie zit kan een corrupte kopie geven. .backup is transactioneel-consistent.
sqlite3 "file:/opt/stresschecker/data/sc_measurements.db?mode=ro" \
        ".backup '/opt/stresschecker-staging/data/sc_measurements.db'"
sqlite3 "file:/opt/stresschecker/data/sc_pro.db?mode=ro" \
        ".backup '/opt/stresschecker-staging/data/sc_pro.db'"
sqlite3 "file:/opt/ic-license-server/data/saas_licenses.db?mode=ro" \
        ".backup '/opt/stresschecker-staging/data/saas_licenses.db'"
chown -R scstaging:scstaging /opt/stresschecker-staging/data
```
De bron wordt **read-only** (`mode=ro`) geopend → de kopieer-actie kán de live-DB technisch niet wijzigen. De richting is per constructie productie→staging.

### 2b. License-DB: kopie vs mock
- **Kopie** (aanbevolen voor realistische tests): zoals hierboven. Bevat echte PII → zie 2d (anonimiseren).
- **Mock** (als je geen echte license-data nodig hebt): genereer een lege `saas_licenses.db` met hetzelfde schema (`sqlite3 staging.db < schema.sql`) plus een handvol test-licenties. Veiliger qua PII, maar minder realistisch.

### 2c. Configuratiemechanisme: aparte `.env.staging`
`/opt/stresschecker-staging/.env.staging` (eigenaar `scstaging`, `chmod 600`) — **alle** paden expliciet naar staging, géén gok op defaults:
```bash
SC_ENV=staging                      # nieuwe vlag (zie §3), de hoofdschakelaar
SC_SECRET_KEY=staging-only-key
SC_METING_DB=/opt/stresschecker-staging/data/sc_measurements.db
SC_PRO_DB=/opt/stresschecker-staging/data/sc_pro.db
SC_DB_PATH=/opt/stresschecker-staging/data/saas_licenses.db
SC_STRIPE_KEYS_FILE=/opt/stresschecker-staging/data/stripe_keys.staging.conf   # zie §3
# BEWUST NIET gezet: SENDGRID_API_KEY, STRIPE_SECRET_KEY, ANTHROPIC_API_KEY
```

### 2d. Startup-guard in code (staging-branch, niet in main vereist)
Bovenaan `app.py`, direct na het inlezen van de paden — een harde assertie die staging weigert te booten als een pad naar live wijst:
```python
if os.environ.get('SC_ENV') == 'staging':
    _live = ('/opt/stresschecker/data/', '/opt/ic-license-server/data/')
    for _p in (DB_PATH, METING_DB_PATH, PRO_DB_PATH):
        assert not any(_p.startswith(x) for x in _live), f"STAGING WEIGERT live-pad: {_p}"
```
Drie onafhankelijke lagen beschermen de live-DB's nu: **(1)** expliciete env-paden, **(2)** OS-gebruiker zonder schrijfrecht op live-mappen, **(3)** deze startup-assertie. Eén laag mag falen zonder dat productie geraakt wordt.

### 2e. Eenrichting gegarandeerd
- Kopieer-/verversscripts lezen bron altijd met `mode=ro` en schrijven uitsluitend in `/opt/stresschecker-staging/`.
- `scstaging` kan niet naar live-mappen schrijven.
- Er bestaat **geen** script dat staging→productie kopieert; dat wordt ook nooit gemaakt. Code gaat alleen via git (§4), data gaat alleen via kopie heen (§5).

---

## 3. Externe diensten uitschakelen

Eén centrale schakelaar `SC_ENV=staging` gate't alle uitgaande effecten. Onderstaande guards komen op de **staging-branch** te staan en mergen mee naar main (ze zijn no-ops zolang `SC_ENV` niet 'staging' is, dus veilig in productie).

| Dienst | Aanroeppunt | Maatregel in staging |
|--------|-------------|----------------------|
| **E-mail (SendGrid)** | `send_verification_code`, `send_password_reset_email` (app.py:23,45) e.a. | Guard bovenaan elke send-functie: `if os.environ.get('SC_ENV')=='staging': print(f'[STAGING-MAIL] to={email} code={code}'); return True`. → Geen echte mail; de 2FA-/resetcode wordt naar het staging-log geschreven zodat testers tóch kunnen inloggen. `SENDGRID_API_KEY` wordt in staging niet gezet (de bestaande try/except vangt het sowieso af, maar de guard voorkomt dat het zover komt). |
| **Betalingen (Stripe)** | `_load_stripe_secret` leest hardcoded `/opt/ic-license-server/data/stripe_keys.conf` (app.py:6100) | Env-var-ize de constante: `SPOOR3_STRIPE_KEYS_FILE = os.environ.get('SC_STRIPE_KEYS_FILE', '/opt/ic-license-server/data/stripe_keys.conf')`. Staging wijst die naar een eigen conf met **Stripe TEST-keys** (`sk_test_…`) of een leeg bestand → lege secret → checkout faalt netjes. Nooit live `sk_live_…` in staging. |
| **License-server** | app.py benadert license-DB **direct via bestandspad** (geen HTTP); de echte license-server draait op 5000 | Staging draait **geen** eigen license-server. `SC_DB_PATH` wijst naar de **kopie** → elke "license-actie" schrijft alleen in de staging-kopie. Stripe-webhooks bereiken staging niet (die gaan naar `api.* → 5000` live). |
| **AI-feedback (Anthropic)** | `os.environ.get('ANTHROPIC_API_KEY')` (app.py:4664) | `ANTHROPIC_API_KEY` niet zetten in staging → AI-calls vallen terug op de bestaande lege-key-afhandeling (verifiëren), of guard met `SC_ENV` om kosten/externe calls te vermijden. |

**Regel:** geen enkele staging-env-var bevat een `*_live`-key of het echte `SENDGRID_API_KEY`. Wat niet aanwezig is, kan niet afvuren.

---

## 4. Code-workflow (git, geen handmatig kopiëren)

Omdat er **geen remote** is, gebruiken we een **git worktree** binnen dezelfde repo — geen kloon, geen scp.

### 4a. Eenmalige opzet
```bash
cd /opt/stresschecker
git branch staging main                                   # staging-branch vanaf main
git worktree add /opt/stresschecker-staging staging       # tweede werkmap op branch 'staging'
```
Resultaat: live = `/opt/stresschecker` op `main`; staging = `/opt/stresschecker-staging` op `staging`. Ze delen één `.git` maar hebben gescheiden working trees. *(Een branch kan niet in twee worktrees tegelijk uitgecheckt staan — main blijft in live, staging in de staging-map; precies wat we willen.)*

### 4b. Iteratie (per wijziging)
```bash
# 1. feature-branch vanaf main
cd /opt/stresschecker && git fetch . && git branch feat/ri-eindwaarde main
# 2. die branch in de staging-worktree zetten
cd /opt/stresschecker-staging && git checkout feat/ri-eindwaarde
# 3. wijzigen + committen (Paul Pannevis-identity, zie [[reference_git_identity_inline]])
git -c user.name='Paul Pannevis' -c user.email='paulpannevis@gmail.com' commit -am "..."
# 4. staging herstarten en testen op :8090
sudo systemctl restart stresschecker-staging
# 5. NA verificatie: merge naar main in de live-worktree
cd /opt/stresschecker && git merge --no-ff feat/ri-eindwaarde
# 6. live activeren: template-only → HUP; code (app.py) → service-restart
kill -HUP $(cat /run/.../master.pid)   # [[reference_template_reload_hup]] voor template-edits
#   of: sudo systemctl restart stresschecker   (bij app.py-wijziging)
```
**Nooit** bestanden tussen `/opt/stresschecker` en `/opt/stresschecker-staging` kopiëren — alle codeoverdracht loopt via git merge. Houd `deploy.sh` (scp-based) buiten deze flow; die is voor de oude losse-VPS-upload en zou de git-historie omzeilen.

---

## 5. Data-verversing (periodiek, veilig, eenrichting)

Script `/opt/stresschecker-staging/refresh_data.sh` (eigenaar `scstaging`):
```bash
#!/bin/bash
set -euo pipefail
STAG=/opt/stresschecker-staging/data
sudo systemctl stop stresschecker-staging          # voorkom schrijven tijdens kopie
for pair in \
  "/opt/stresschecker/data/sc_measurements.db:$STAG/sc_measurements.db" \
  "/opt/stresschecker/data/sc_pro.db:$STAG/sc_pro.db" \
  "/opt/ic-license-server/data/saas_licenses.db:$STAG/saas_licenses.db"; do
    SRC=${pair%%:*}; DST=${pair##*:}
    sqlite3 "file:$SRC?mode=ro" ".backup '$DST'"     # bron read-only → eenrichting
done
# OPTIONEEL: PII-scrub op de kopie (zie §5a)
python3 /opt/stresschecker-staging/scrub_pii.py "$STAG" || true
sudo systemctl start stresschecker-staging
echo "Staging-data ververst: $(date)"
```
- Draai op aanvraag, of via cron (bijv. wekelijks) — **niet** vaker dan nodig (PII-minimalisatie).
- Bron altijd `mode=ro`; doel altijd onder staging. Geen pad wijst terug naar live.
- Verversen overschrijft staging-testdata; communiceer dat lopende staging-experimenten dan weg zijn.

### 5a. PII-scrub (sterk aanbevolen bij license-kopie)
Aparte `scrub_pii.py` die in de **staging-kopie** e-mailadressen/namen anonimiseert (bijv. `gebruiker<id>@staging.local`), behalve de bewuste +alias-testfixtures ([[reference_test_accounts_policy]]). Draait alleen op staging-bestanden; raakt live nooit.

---

## 6. Risico's en checks

| # | Risico (hoe staging per ongeluk live raakt) | Controle die het voorkomt |
|---|---------------------------------------------|---------------------------|
| R1 | `.env.staging` mist een `SC_*_DB`-var → val terug op live-default (app.py:132-133) | Startup-guard §2d (assert geen live-pad) **én** OS-gebruiker zonder schrijfrecht §1a |
| R2 | Staging draait per ongeluk als root → mag wél in live schrijven | Unit forceert `User=scstaging` (§1b); controleer met `ps -o user= -C gunicorn` |
| R3 | Live `SENDGRID_API_KEY`/Stripe-`sk_live` lekt in staging-env → echte mail/betaling | `.env.staging` bevat deze keys niet; `SC_ENV`-guards §3; grep-check in de checklist |
| R4 | `sudo systemctl restart stresschecker` i.p.v. `…-staging` → live herstart | Naamdiscipline; aparte unit-naam met `-staging`-suffix |
| R5 | `cp` van live-DB tijdens schrijven → corruptie | Altijd `sqlite3 .backup` met `mode=ro`-bron (§2a, §5) |
| R6 | Iemand kopieert staging-bestanden naar live | Verboden; uitsluitend `git merge` (§4); er bestaat geen omgekeerd script |
| R7 | nginx routeert `app.stresschecker.com` naar 8090 | Gescheiden site-bestanden; staging-site heeft eigen `server_name staging.*` + Basic-Auth |
| R8 | Webhook/cron van live raakt staging-DB | Staging deelt geen poort/socket met live; webhooks gaan naar 5000 (live), niet 8090 |

### Checklist vóór elke staging-sessie
```
[ ] Welke service? → `systemctl status stresschecker-staging` actief, `stresschecker` (live) ongemoeid
[ ] Draait als juiste user? → `ps -o user=,args= -C gunicorn | grep 8090` toont `scstaging`
[ ] Wijzen de paden naar staging? → `systemctl show stresschecker-staging -p Environment`
    of in het log de startup-guard-regel; GEEN `/opt/stresschecker/data` of `/opt/ic-license-server/data`
[ ] Externe diensten uit? → `grep -E 'SENDGRID|sk_live|STRIPE_SECRET' /opt/stresschecker-staging/.env.staging` == leeg
[ ] SC_ENV=staging gezet? → zo niet, mail/Stripe-guards staan uit → NIET starten
[ ] Op welke git-branch? → `git -C /opt/stresschecker-staging branch --show-current` ≠ `main`
[ ] Live-DB read-only voor staging-user? → `sudo -u scstaging test -w /opt/stresschecker/data/sc_measurements.db && echo FOUT || echo OK`
```

---

## 7. Eerste toepassing: de RI-opslagkwestie

**Doel:** opgeslagen `ri` gelijktrekken aan de canonieke eind-RI i.p.v. het venstergemiddelde — de dominante bron van RI-drift uit de vorige analyse (`measure.html:711` slaat nu `mean(timeseriesData.ri)` op, terwijl `finishMeasure` op `measure.html:752` de eind-RI `lookupRelaxIndex(avgBpm, hrv)` berekent).

**Stap voor stap op staging:**
1. `git branch feat/ri-eindwaarde main`; checkout in de staging-worktree (§4b).
2. Wijzig in `measure.html` (en identiek `sensor_en_meten.html`) regel ~711: stuur de eind-RI `ri` mee i.p.v. het `timeseriesData`-gemiddelde. Laat de live-timeseries (de grafiekpunten) intact.
3. `systemctl restart stresschecker-staging`; test op `:8090` met de gekopieerde data.
4. **Verificatie-oracle:** voer een demo-meting uit en bevestig dat de opgeslagen `ri` nu exact gelijk is aan de eind-RI op het resultaatscherm. Vergelijk daarnaast met de read-only herberekening uit de vorige sessie (`RMSSD_HERBEREKENING_OVERZICHT.md`) — de "herberekend"-kolom is de verwachte uitkomst.
5. Controleer regressie: `/kwadrant`-pagina, verloopgrafiek, en dat bestaande (oude) metingen in staging niet verminkt tonen (de wijziging raakt alleen nieuw-opgeslagen metingen; oude `ri`-waarden blijven historisch).
6. Beslis apart of historische metingen herijkt worden (zie de opties uit `RMSSD_RI`-analyse) — dat is een DB-migratie en valt buiten deze eerste, veilige stap.
7. Pas na groen licht: `git merge --no-ff feat/ri-eindwaarde` in main + live activeren (template-only → HUP).

**Waarom dit een goede eerste casus is:** het is een template-only wijziging (geen schema, geen DB-migratie), het effect is meetbaar tegen een bestaande oracle, en het raakt uitsluitend nieuw op te slaan data — laag risico, hoge leerwaarde om de staging-pijplijn zelf te valideren.

---

## Samenvatting van de te maken artefacten (bij uitvoering)
1. OS-gebruiker `scstaging` + rechten (§1a)
2. `/etc/systemd/system/stresschecker-staging.service` (§1b)
3. git worktree `/opt/stresschecker-staging` op branch `staging` (§4a)
4. `/opt/stresschecker-staging/.env.staging` (§2c)
5. DB-kopieën in `/opt/stresschecker-staging/data` (§2a)
6. Staging-Stripe-conf met test-keys (§3)
7. Code-guards op staging-branch: startup-assertie (§2d) + mail/Stripe `SC_ENV`-guards (§3)
8. `refresh_data.sh` (+ optioneel `scrub_pii.py`) (§5)
9. Optioneel: nginx `stresschecker-staging` + Basic-Auth, of SSH-tunnel (§1c)
