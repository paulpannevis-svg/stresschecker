# Beveiligingsincident — publiek toegankelijke backup-tarball

| Veld | Waarde |
|---|---|
| **Incident-ID** | 2026-06-06_backup_exposure |
| **Classificatie** | Hoog — secrets + bijzondere persoonsgegevens (AVG art. 9) publiek blootgesteld |
| **Status** | In behandeling (containment voltooid, rotatie + AVG-afweging lopend) |
| **Ontdekt** | 2026-06-06 (tijdens Fase 2 opruim-/securitysessie) |
| **Opgesteld** | 2026-06-06, Paul Pannevis |
| **Containment** | Voltooid 2026-06-06 |

## 1. Samenvatting

Het bestand `backup-download.tar.gz` (64 MB) stond onder `/opt/stresschecker/static/`
en was daarmee **publiek downloadbaar** via de nginx-route
`location /static/ { alias /opt/stresschecker/static/; }` op
`https://app.stresschecker.com/static/backup-download.tar.gz`.

De tarball bevat een volledige systeemkopie van zowel `/opt/stresschecker` als
`/opt/ic-license-server`, inclusief **alle applicatie-secrets** (Stripe-keys,
SendGrid-keys, `SC_SECRET_KEY`, IC admin-key) en **productie-databases met
persoons- en gezondheidsgegevens**.

## 2. Tijdlijn (UTC/serverlokaal)

| Tijdstip | Gebeurtenis |
|---|---|
| 2026-04-09 18:14 | Snapshot van `saas_licenses.db` zoals aanwezig in de tarball (file-mtime) |
| 2026-04-10 12:12 | `backup-download.tar.gz` aangemaakt en in `/static/` geplaatst (file-mtime) |
| 2026-04-10 → 2026-05-22 | **Blootstellingsvenster zonder logdekking** (~43 dagen) — nginx-logs reiken niet zo ver terug |
| 2026-05-23 00:02 | Vroegste beschikbare nginx-access-logregel |
| 2026-05-23 → 2026-06-06 | Logdekking: **0 requests** naar de tarball-URL (van geen enkel IP) |
| 2026-06-06 ~09:38 | Ontdekking; bestand verplaatst naar `/root/quarantine/` (dir 0700) → URL geeft HTTP 404 |
| 2026-06-06 | SendGrid-keys reeds geroteerd (Fase 2, dezelfde dag) — toevallig al afgedekt |

## 3. Blootgestelde inhoud

**Secrets — per item geanalyseerd (snapshot 2026-04-09):**

| Bestand / sleutel | In tarball | Echt of placeholder | Nog actief? | Actie |
|---|---|---|---|---|
| `stripe_keys.conf` `STRIPE_SECRET_COM/DE` | ja | **placeholder** (`sk_live_VERVANG_DIT…`) | n.v.t. | geen leak; LIVE-key alsnog gerold |
| `stripe_keys.conf` `STRIPE_WHSEC_COM/DE` | ja | wijkt af van huidige | n.v.t. | whsec_live alsnog gerold |
| `opt/stresschecker/.env` `STRIPE_SECRET_KEY` (test) | ja | echt (test) | **ingetrokken/ongeldig** | reeds dood |
| `opt/stresschecker/.env` `SENDGRID_API_KEY` | ja | echt | ingetrokken (Fase 2) | afgedekt |
| `opt/stresschecker/.env` `SC_SECRET_KEY` | ja | echt | vervangen 06-06 | afgedekt |
| `opt/ic-license-server/.env` `PAYPAL_CLIENT_ID`+`PAYPAL_SECRET` (**live**) | ja | **echt** | **JA, ongewijzigd** ⚠️ | **rotatie open (PayPal-dashboard)** |
| `opt/ic-license-server/.env` `PAYPAL_WEBHOOK_ID` | ja | echt | ja | identifier (geen secret) |
| `opt/ic-license-server/.env` `MAIL_PASS`/`MAIL_DE_PASS` | ja | echt | **nee — sinds gewijzigd** | reeds afgedekt |
| `opt/ic-license-server/.env` `SECRET_KEY` (64) | ja | echt | **niet gebruikt** (code leest `IC_SECRET_KEY`) | exposure moot; IC_SECRET_KEY gezet 06-06 |
| `opt/ic-license-server/.env` `INTERNAL_API_KEY` (64) | ja | echt | **nergens in code gebruikt** | dood; opruimen aanbevolen |
| `opt/ic-license-server/data/api_key.conf` (2845…) | ja | echt | **niet door code gelezen** | dood; opruimen aanbevolen |

**Kerninzicht:** de Stripe-LIVE-secrets waren ten tijde van de snapshot nog *placeholders* —
er zijn **geen werkende live-Stripe-credentials gelekt**. De enige **echte, nog-actieve**
gelekte credential is **PayPal live (`PAYPAL_CLIENT_ID`+`PAYPAL_SECRET`)**. De feitelijk
gebruikte Flask- en admin-sleutels van de license-server stonden op publieke *defaults*
(`change-this-in-production` / `admin-secret`) — los van de tarball een eigen zwakte,
nu verholpen.

**Risicoverlagende indicatoren (Stripe-dashboard, door Paul vastgesteld 06-06):**
de (oude) Stripe-key was *"laatst gebruikt 5 dagen geleden"* en het
webhook-foutpercentage is **0%** — geen aanwijzing voor misbruik via Stripe.

**Databases (snapshot 2026-04-09):**
- `opt/ic-license-server/data/saas_licenses.db` (1,2 MB) — de productie-DB (zie §4)
- 3× gedateerde backups `saas_licenses_2026-02-1x_*.bak.db` + `saas_licenses_backup.db`
- `sc_measurements.db`, `sc_pro.db` (meet-/clientdata)
- `opt/stresschecker/data/saas_licenses.db` = 0-byte stub (geen data)

## 4. Persoonsgegevens in `saas_licenses.db` (snapshot 2026-04-09)

Inspectie van de tarball-kopie (read-only, in `/root/quarantine/inspect/`):

**Omvang persoonsgegevens — beperkt:**
- **~11 distinct e-mailadressen** (users.email = 6, licenses.email = 18 rijen → 11 uniek).
  NB: meerdere hiervan zijn vermoedelijk testaccounts (zie `TEST_ACCOUNTS.md`).
- **6 volledige gebruikersaccounts** met: `email`, `password_hash`, `display_name`,
  `birth_year`, `gender`, `language`, Stripe-IDs (`stripe_customer_id`,
  `stripe_subscription_id`), `last_login`.
- `legacy_keys`: 3999 rijen, maar `migrated_by_email` = **0 gevuld** → bevat
  **geen** e-mails, alleen licentiesleutels.
- `licenses`: 32 rijen (licentiesleutels, e-mail, order-id).

**Bijzondere categorie (AVG art. 9 — gezondheidsgegevens): JA, in beperkte omvang.**
- `measurements`: **3 rijen** met `relax_index`, `rr_intervals` (ruwe HRV-interbeat-intervallen),
  `result_data`, `subjectief_score`, `measurement_type` — dit zijn HRV-/stressmetingen.
- `hlm_morning`: **2 rijen** met `scores_json` (welzijnsscores).
- `hlm_user_questionnaires`: 8 rijen (vragenlijst-definities, geen meetwaarden).

**Wachtwoorden:** 6 `password_hash`-waarden aanwezig. Formaat = hex-digest zonder
herkenbare algoritme-prefix (geen `$2b$`/`pbkdf2`) → vermoedelijk ongesalte hash;
apart te beoordelen als hardening-punt.

## 5. Logbevindingen

- nginx serveert `/static/` direct (alias) en logt naar `/var/log/nginx/access.log`.
- Beschikbare historie: **2026-05-23 00:02 t/m 2026-06-06 09:42** (logrotate, ~14 dagen).
- In die periode: **0 requests** naar `/static/backup-download.tar.gz` (alle access-logs,
  plain + gzip, doorzocht; geen enkel IP, ook niet ons eigen `84.80.70.50`).
- **Kritieke beperking:** het grootste deel van het blootstellingsvenster
  (**2026-04-10 t/m 2026-05-22, ~43 dagen**) valt buiten de logdekking. Een download
  in die periode kan **niet worden uitgesloten noch bevestigd**.

## 6. Oorzaak

Geen route, script of cronjob maakt het bestand aan (geverifieerd in beide codebases
+ crontab). De geautomatiseerde backup-cron schrijft naar `/opt/backups/` met een andere
naam. Conclusie: **handmatig geplaatst** — eenmalige admin-backup die via de browser
gedownload moest worden en daarna niet is opgeruimd. Geen herhalingsmechanisme.

## 7. Genomen maatregelen (containment, 2026-06-06)

- [x] Tarball verplaatst uit `/static/` naar `/root/quarantine/` (dir-permissies 0700);
      publieke URL geeft nu HTTP 404 (https) — niet langer bereikbaar.
- [x] Geverifieerd dat geen script/cron het bestand opnieuw aanmaakt.
- [x] SendGrid-keys geroteerd (al uitgevoerd in Fase 2; oude keys ingetrokken).
- [x] Inhoud geïnventariseerd zonder de volledige tarball uit te pakken in een
      bereikbare locatie.

## 8. Rotaties & hardening — uitgevoerd 2026-06-06

| Tijd-volgorde | Secret / actie | Methode | Test |
|---|---|---|---|
| 1 | **SendGrid-key** (Fase 2, eerder die dag) | `.env`, oude ingetrokken | 2FA-mail via echt pad |
| 2 | **Stripe LIVE secret** (`STRIPE_SECRET_LIVE`) | dashboard-roll → `stripe_keys.conf` (Edit) | `AUTH OK` acct_…o1K, DE, livemode |
| 3 | **Stripe LIVE webhook** (`STRIPE_WHSEC_LIVE`) | dashboard-roll → conf (Edit) | `construct_event`: geldig ✓ / fout ✗. Geen reload (per-request-load) |
| 4 | **`SC_SECRET_KEY`** (stresschecker Flask) | `token_urlsafe(48)` in-process → systemd-unit + `.env`; `daemon-reload`+`restart` | proc draait nieuwe key; `/licentie` 200 |
| 5 | **`IC_ADMIN_KEY`** (was default `admin-secret`) | `token_urlsafe(48)` → `ic .env`; `restart ic-license-server` | `/api/admin/stats`: nieuw=200, default=401 |
| 6 | **`IC_SECRET_KEY`** (was default `change-this-in-production`) | idem, zelfde restart | service active; Flask-sessies nu sterk ondertekend |
| 7 | **Nginx-hardening** | `location ~* ^/static/.*\.(tar\|gz\|zip\|db\|sqlite\|conf\|env\|bak\|…)$ → 404` in vhost; `nginx -t`+reload | `.tar.gz/.db/.conf/.env` → 404; `manifest.json`/`sw.js` → 200 |

Containment (eerder op 06-06): tarball → `/root/quarantine/` (0700), publieke URL 404;
geverifieerd dat geen script/cron de tarball opnieuw aanmaakt.

## 8b. Nog openstaand

- [x] **PayPal LIVE** (`PAYPAL_CLIENT_ID`+`PAYPAL_SECRET`) — **INGETROKKEN i.p.v. geroteerd**
      (2026-06-06): de Live-app "Lifestyle Monitors" (`AbU7cY…`, aangemaakt 19-02-26) is
      verwijderd in het PayPal-dashboard → tarball-credentials definitief ongeldig
      (read-only bevestigd: OAuth-token nu HTTP 401). **Gevolg:** de `PAYPAL_*` in
      `/opt/ic-license-server/.env` zijn nu dood; `get_paypal_token()` faalt. Geen recent
      PayPal-webhookverkeer in de logs (alleen scanner-ruis; Stripe = 124 hits) → integratie
      lijkt dormant. **Open beslissing:** nieuwe PayPal-app aanmaken + creds bedraden, óf
      het PayPal-pad bewust uitfaseren en de dode `PAYPAL_*` uit `.env` verwijderen.
- [ ] **Stripe TEST** (`sk_test`/`whsec_test`) — niet in de tarball, lage prioriteit; rollen
      indien gewenst voor volledigheid.
- [ ] **Dode secrets opruimen**: `INTERNAL_API_KEY` (.env) + `api_key.conf` (beide nergens
      in code gebruikt) verwijderen; de ongebruikte `SECRET_KEY` in `ic .env` opschonen.
- [ ] **`.env`-backups met oude secrets** (`/opt/ic-license-server/.env.bak_*`, 4 stuks) —
      opruimen (secret-sprawl op schijf, niet publiek).
- [ ] **AVG-afweging meldplicht datalek** (§9).
- [ ] Wachtwoord-hashing-formaat beoordelen (apart hardening-punt).
- [ ] Besluit over definitieve vernietiging van de gequarantainede tarball + de
      uitgepakte inspectie-kopieën in `/root/quarantine/inspect/`.

## 9. AVG / DSGVO — afwegingspunten meldplicht datalek

- **Aard**: ongeoorloofde toegang *mogelijk* (publiek bereikbaar), niet bevestigd.
- **Betrokkenen**: klein (~11 e-mails, ≤6 volledige profielen), deels testaccounts.
- **Gegevenscategorieën**: identificerend (e-mail, naam, geboortejaar, geslacht),
  inloggegevens (password_hash), **bijzondere categorie (gezondheid: 3 HRV-metingen +
  2 welzijnsscores)** → verhoogt risicoweging.
- **Bewijslast**: 0 downloads in gedekte 14 dagen; ~43 dagen zonder logbewijs.
- **Risicoverlagend**: kleine populatie (≤6 volledige profielen, deels test); geen
  werkende live-betaal-credentials gelekt (Stripe = placeholders); Stripe-dashboard toont
  geen misbruik-indicatie (0% webhook-fouten, key "5 dagen geleden voor het laatst gebruikt").
- **Risicoverhogend**: bijzondere categorie (gezondheid: 3 HRV-metingen + 2 welzijnsscores);
  password_hashes; ~43 dagen zonder logbewijs.
- **Conclusie-richting**: door de aanwezigheid van gezondheidsgegevens + het niet kunnen
  uitsluiten van toegang, een formele datalek-beoordeling uitvoeren (AVG art. 33/34);
  documenteer de afweging ook als besloten wordt **niet** te melden. De beperkte populatie
  en het ontbreken van misbruik-indicatie wegen mee.

## 10. Betrokkenen-analyse (onderbouwing AVG-conclusie)

Vastgesteld op de tarball-DB-kopie (snapshot 2026-04-09), read-only. Verfijnt de
"deels testaccounts"-inschatting uit §4/§9 met concrete identiteits- en betaalverificatie.

**Volledige profielen (`users`, 6× — mét password_hash, geboortejaar/geslacht):**
uitsluitend eigen / familie / bedrijf — **geen externe betrokkenen**:
- 2× Paul Pannevis (eigen accounts: gmail + lifestylemonitors.com)
- `paul@hlmpro.nl` — **niet-bestaand testadres** (geen echte mailbox)
- 2× Steven Pannevis (familie; lifestylemonitors.com + persoonlijk hotmail)
- 1× `sales@lifestylemonitors.com` (bedrijfsrol-adres)

**Bijzondere categorie (gezondheid):** alle **3 HRV-basismetingen** (15-03-2026) + beide
**hlm_morning-welzijnsscores** (15-03 + 24-03) horen bij **één persoon: Paul Pannevis zelf**
(user_id 1). Geen gezondheidsgegevens van derden.

**License-records (`licenses`, alleen e-mail + sleutel + order-id; geen wachtwoord/gezondheid):**
de drie aanvankelijk ambigue gmail-adressen objectief geverifieerd via order-id/betaalsporen
(gepseudonimiseerd):

| Adres | license_key | origin | order-id | betaling | aangemaakt | conclusie |
|---|---|---|---|---|---|---|
| j***e@gmail.com | TRIAL-… | trial | (leeg) | **nee** | 2026-03-28 09:29 | test/demo |
| j*b@gmail.com | TRIAL-… | trial | (leeg) | **nee** | 2026-03-28 10:20 | test/demo |
| p***r@gmail.com | TRIAL-… | trial | (leeg) | **nee** | 2026-03-28 10:19 | test/demo |

Alle drie zijn **trial-licenties zonder order-id en zonder enige betaling**, aangemaakt binnen
~1 uur in één testsessie op 28-03-2026. In de héle DB: `billing_events` = 0, `subscriptions` = 0,
0 PayPal-subscription-id's. De enige 2 records mét order-id (`origin=shop`) zijn eveneens intern:
`TEST-001` (Paul's gmail, expliciet test) en order `10062` (Paul's eigen lifestylemonitors-adres,
status `available` / nooit geactiveerd).

**Conclusie:** de blootgestelde snapshot bevat **nul externe betrokkenen**. Alle profielen,
inloggegevens en gezondheidsgegevens betreffen de verwerkingsverantwoordelijke zelf, familie en
bedrijfsadressen; alle overige records zijn test/trial zonder betaling. Dit ondersteunt de
afweging dat melding aan de AP (art. 33) én aan betrokkenen (art. 34) **niet vereist** is.
Aanbeveling: deze afweging formeel dateren, ondertekenen en archiveren.

> **Afweging uitgevoerd en geaccordeerd door Paul Pannevis, verwerkingsverantwoordelijke,
> 6 juni 2026, 11:00 CET. Conclusie: geen melding ex art. 33/34 AVG vereist (nul externe
> betrokkenen, onderbouwing §10).**

---
*Dit document bevat bewust geen secret-waarden of individuele persoonsgegevens.*
