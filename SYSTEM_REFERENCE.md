# StressChecker — SYSTEM REFERENCE

**Versie:** 1.1
**Laatste update:** 2026-05-20 (marketing-codes feature)
**Onderhouden door:** Claude Code (op verzoek)
**Bron-DB-snapshot:** `/opt/ic-license-server/data/saas_licenses.db` (1.5 MB, 2026-05-18 21:07)

---

## 0. Gebruiksaanwijzing

### Doel van dit document
Overkoepelend systeem-overzicht van de StressChecker SaaS-stack, bedoeld om te **delen met de Claude chat-versie** voor strategische besprekingen. Geeft de chat-Claude voldoende context om mee te denken zonder dat er live toegang tot de VPS nodig is.

### Update-conventie
- Geüpdatet door Claude Code bij **significante wijzigingen** in datamodel, webhook-flow, plan-id-namen, licentiecode-format, of activatie-pad.
- Versie-nummer ophogen + datum bovenaan aanpassen.
- Bestand staat in dagelijkse backup (`/opt/stresschecker/backup.sh`).

### Wat NIET in dit document hoort
- **Secrets**: Stripe keys, SMTP wachtwoorden, API-tokens (staan in `/opt/ic-license-server/data/stripe_keys.conf` en `/opt/stresschecker/.env`).
- **Productie-data**: concrete licentiecodes van klanten, e-mailadressen, subscription-IDs.
- **Klant-PII**: namen, IP-adressen, betaaldata.

Als zo'n waarde nodig is voor uitleg: gebruik een **placeholder** (bv. `SC-XXXX-XXXX-XXXX`, `klant@voorbeeld.nl`).

### Te verifiëren elementen
Items waar bij schrijven nog onduidelijkheid was, zijn gemarkeerd met **⚠️ TE VERIFIËREN** en onderaan opgesomd.

---

## 1. Architectuuroverzicht

### Twee codebases, één DB voor licenties

```
┌─────────────────────────────┐         ┌────────────────────────────────┐
│  /opt/stresschecker         │         │  /opt/ic-license-server        │
│  (Flask, gunicorn)          │         │  (Flask, gunicorn op :5000)    │
│                             │         │                                │
│  - SC web-app + Pro UI      │         │  - Stripe/PayPal webhooks      │
│  - /licentie + /activeer    │         │  - Licentie-aanmaak            │
│  - Login + 2FA              │         │  - Activatie-mail (SendGrid)   │
│  - Metingen UI              │         │  - Customer Portal sessies     │
│                             │         │                                │
│  Service:                   │         │  Service:                      │
│   stresschecker.service     │         │   ic-license-server.service    │
│                             │         │                                │
│  Eigen DB's:                │         │  Eigen DB:                     │
│   data/sc_measurements.db   │         │   data/saas_licenses.db        │
│   data/sc_pro.db            │         │   ↑                            │
│                             │ ──────► │   ↑ wordt direct gelezen       │
└─────────────────────────────┘  read   └────────────────────────────────┘
```

De StressChecker web-app **leest direct** uit `saas_licenses.db` (via `sqlite3.connect()` in `app.py`), niet via een HTTP-API. Dat is bewust: minimaliseert latency op `/activeer` en `/login`.

### Service-management

| Service | Pad | Reload-pad |
|---|---|---|
| `stresschecker.service` | `/opt/stresschecker` | `kill -HUP <gunicorn-master-pid>` voor templates/code; `systemctl restart` voor env-changes |
| `ic-license-server.service` | `/opt/ic-license-server` | `systemctl restart` na server.py wijziging |

Verkrijg master-PID: `systemctl show stresschecker.service -p MainPID --value`.

### Externe endpoints

- **`https://stresschecker.lifestylemonitors.com`** — consumer + Pro UI (DE + NL + EN)
- **`https://api.lifestylemonitors.com/api/webhooks/stripe`** — Stripe webhook (proxied → `127.0.0.1:5000`)
- **`https://api.lifestylemonitors.com/api/webhooks/paypal`** — PayPal webhook

---

## 2. Database-schema

DB-bestand: `/opt/ic-license-server/data/saas_licenses.db`
(owner `www-data:www-data`, mode 664)

### Kerntabellen — minimal columns

```
plans
  plan_id (PK)              -- 'sc', 'sc-month', 'sc-pro-m', 'sc-pro-m-month', etc.
  name, audience            -- 'consumer' | 'pro'
  product_family            -- 'sc' | 'hlm'
  tier                      -- 'base' | 'pro-s' | 'pro-m' | 'pro-l' | 'sport-*'
  max_profiles, max_clients
  paypal_plan_id_monthly, paypal_plan_id_yearly
  stripe_price_id
  is_active

licenses
  license_key (UNIQUE)      -- bv 'SC-A3K2-9PQX-MN4B' (consumer) of 'SC-PRO-9F4E2A1B' (pro)
  product                   -- 'sc' | 'hlm'
  type                      -- 'consumer' | 'pro' | 'krankenkasse' | 'migration'
  status                    -- 'available' | 'activated' | 'suspended' | 'expired'
  origin                    -- 'migration' | 'webshop' | 'amazon' | 'manual' | 'paypal'
  max_profiles
  created_at, activated_at, expires_at
  email                     -- ⚠️ binding bij INSERT, niet bij activering (zie §6)
  user_key                  -- SHA256(email)[:32], gevuld door invoice.paid handler
  stripe_subscription_id
  paypal_subscription_id
  order_id, product_name, notes
  cancelled_at, cancel_reason, valid_until

subscriptions
  subscription_id (UNIQUE)  -- stripe sub_xxx of paypal I-xxx
  user_id (text, optioneel)
  plan_id (FK plans)
  status                    -- 'trialing' | 'active' | 'past_due' | 'canceled' | 'expired'
  provider                  -- 'stripe' | 'paypal' | 'webshop' | 'manual' | 'migration'
  provider_ref              -- voor stripe: checkout-session id
  trial_end, current_period_end
  stripe_customer_id        -- cus_xxx, voor Customer Portal lookup

users
  email (UNIQUE)
  password_hash             -- sha256 hex (geen bcrypt) ⚠️ TE VERIFIËREN of dit ok blijft
  display_name, language
  birth_year, gender, sensor_pref
  activated_at, last_login
  license_expires
  stripe_subscription_id, stripe_customer_id
  deleted_at, warned_30, warned_7

user_licenses
  user_id (FK users)
  license_key (FK licenses)
  product
  is_primary

billing_events
  provider (stripe/paypal)
  event_id (UNIQUE per provider)
  event_type
  payload_json
  status                    -- 'processed' | 'plan_failed'

redeem_codes                -- nieuwe webshop-stijl codes (post-2026-02)
  code (PK)
  plan_id (FK plans)
  code_type                 -- 'legacy' | 'webshop' | 'manual'
  trial_months
  status                    -- 'unused' | 'redeemed' | 'blocked'
  redeemed_at, redeemed_by_user_id, redeemed_by_device_id

legacy_keys / legacy_codes  -- migratie-tabellen (3999 oude codes pre-2026)

activation_log              -- audit-trail voor /api/license/validate + /activate
devices, backups            -- device-binding + JSON snapshot upload (HLM)
profiles, measurements      -- minimal multi-product schema (niet gebruikt door SC web)
reflections                 -- HLM-specifiek
```

### Plans (snapshot 2026-05-20)

| plan_id | audience | tier | max_profiles | stripe_price_id | paypal monthly | paypal yearly |
|---|---|---|---|---|---|---|
| `sc` | consumer | base | 5 | `price_1TTJpt...` | ✓ | ✓ |
| `sc-month` | consumer | base | 5 | `price_1TY6BX...` | — | — |
| `sc-komplett` | consumer | base | 5 | — | — | — |
| `sc-pro-s` | pro | pro-s | 10 | `price_1TTJxc...` | ✓ | ✓ |
| `sc-pro-s-month` | pro | pro-s | 10 | `price_1TUqWW...` | — | — |
| `sc-pro-m` | pro | pro-m | 30 | `price_1TXyBl...` | ✓ | ✓ |
| `sc-pro-m-month` | pro | pro-m | 30 | `price_1TXxxQ...` | — | — |
| `sc-pro-l` | pro | pro-l | 75 | `price_1TTJxe...` | ✓ | ✓ |
| `hlm`, `hlm-pro-s/m/l`, `hlm-sport-s/m/l` | — | — | — | — | ✓ | ✓ |

**Naming-conventie plan_id:**
- Product-family prefix: `sc-` of `hlm-`
- Tier-suffix bij Pro: `-s`, `-m`, `-l`, `-sport-{s,m,l}` (HLM)
- Cycle-suffix bij Stripe-only monthly: `-month`
- Consumer base zonder tier-suffix: `sc`, `sc-month`, `sc-komplett`
- **Geen `-year` suffix**: de yearly-variant is het *default* plan; monthly krijgt `-month` als toevoeging.

### Indexen (high-value)

```
idx_license_key            licenses(license_key)
idx_license_status         licenses(status)
idx_user_email             users(email)
idx_subs_user/device/plan/status   subscriptions(...)
idx_redeem_status          redeem_codes(status)
idx_plans_family/audience  plans(...)
```

---

## 3. Flask routes — overzicht

### `/opt/stresschecker/app.py` (consumer + Pro UI)

**Publieke routes (no auth required):**
```
GET  /                       — landing
GET  /welkom, /start, /demo  — onboarding
GET  /licentie               — activatie/inlog-scherm
POST /activeer               — code+email+wachtwoord submit
GET  /privacy, /faq, /tips, /kenniscentrum, /sport-training
GET  /taal/<lang>            — taal-switch in session
GET  /eggs                   — easter-egg
```

**Auth-pad:**
```
GET/POST /login              — email + wachtwoord
GET/POST /verify             — 2FA-code uit mail
GET/POST /wachtwoord-vergeten + /wachtwoord-reset
GET     /uitloggen
```

**Consumer hoofd-flow (vereist session.license_valid):**
```
GET  /menu                   — hoofdmenu
GET  /sensoren, /sensor-en-meten, /voorbereiden
GET  /meetkeuze              — kies meet-type
GET  /biofeedback            — biofeedback-meting
GET  /resultaten             — resultaat na meting
GET  /mijn-metingen, /verloop, /kwadrant
GET  /profiel + POST /profiel/opslaan
GET  /instellingen           — taal, sensor, abonnement-widget
GET  /sc/sensor-keuze        — UX: sensortype-keuze
GET  /koppelen               — pairing-code voor Pro→consumer link
GET  /oude-code, /oude-code-keuze   — legacy-migratie pad
```

**Pro-flow (vereist session.license_type=='pro'):**
```
GET  /pro                    — Pro hoofdmenu
GET  /pro/dashboard          — overzicht laatste sessies
GET  /pro/clienten           — cliëntlijst
GET  /pro/client/<cid>       — cliënt-detail
GET  /pro/client/<cid>/meten — meting voor cliënt
POST /pro/client/toevoegen
POST /pro/client/<cid>/verwijderen
GET  /pro/mijn-metingen      — Pro's eigen metingen
GET  /pro/meting             — Pro eigen meting (geen cliënt)
```

**JSON API's:**
```
POST /api/meting/opslaan, /confirm, /discard, /label, /<mid>/regenerate_kompas
GET  /api/metingen, /api/metingen/stats, /api/meting/<id>
POST /api/feedback, /api/set_subjectief, /api/settings/save
GET  /api/license/status     — sessie-licentie-info
POST /api/license/migrate    — legacy → nieuwe code
POST /api/license/generate   — admin: nieuwe code aanmaken
POST /api/licentie/check     — license-validatie zonder commit
POST /api/pairing/{generate,register,redeem,revoke}
GET  /api/pairing/status
POST /api/pro/client/<cid>/{update,pairing}
GET  /api/pro/client/<cid>/{metingen,consumer-metingen}
GET  /api/kubios/download/<mid>, /api/kubios/download
```

**Abonnementbeheer:**
```
GET/POST /abonnement/opzeggen           — opzegformulier
GET      /account/manage-subscription   — Stripe Customer Portal redirect
```

### `/opt/ic-license-server/server.py` (Stripe/PayPal backend)

```
POST /api/webhooks/stripe              — Stripe webhook entrypoint
POST /api/webhooks/paypal              — PayPal webhook entrypoint
POST /api/license/validate             — nieuwe + legacy code-check
POST /api/license/migrate              — legacy → nieuw + account
POST /api/account/register, /login
POST /api/redeem                       — redeem_codes flow (post-2026-02 webshop)
GET  /api/entitlements                 — wat mag deze user
POST /api/admin/generate-keys          — admin: batch nieuwe codes
GET  /api/admin/{stats,recent-migrations}
POST /api/subscriptions/cancel
POST /api/backup/upload                — JSON snapshot (HLM device-backup)
GET  /api/backup/latest
POST /api/pairing/link, /unlink
GET  /api/pairing/config + PUT
GET  /api/clients, POST/PUT/DELETE     — Pro cliëntlijst
GET  /api/clients/<id>/data
POST /api/measurements, GET
POST /api/profiles, GET
POST /api/reflections, GET             — HLM
GET  /api/products, /api/health
```

---

## 4. UI-flow `/licentie` (activatiescherm)

Route: `app.py:493-504` → renders `templates/license.html`.

### Velden in `license.html`

| Veld | Naam | Verplicht | Validatie |
|---|---|---|---|
| Licentiecode | `code` | Ja (nieuw account) | Geen client-side; server matcht in DB |
| Legacy code | `legacy_code` | Nee | Fallback als `code` leeg |
| E-mail | `email` | Ja | Lowercase server-side |
| Wachtwoord | `password` | Ja | Min. 8 tekens (server-side) |
| Verborgen | `lang` | Auto | `nl` / `de` / `en` uit session |
| Verborgen | `type` | Auto | `'nieuw'` of `'terug'` (login zonder code) |

### Conditioneel: Stripe Customer Portal-knop

Wordt **alleen getoond** als `has_stripe_subscription(session['email'])` true is (DB-only check, geen API-call per page-render). Stuurt naar `/account/manage-subscription` → Stripe billing portal sessie.

### Submit-flow (`/activeer`, POST, `app.py:506-624`)

```
[1] Form-data parsen + lowercasen email
[2] Cross-product check: code start met "HLM" → redirect /hlm/registreer
[3] validate_license(code, email)   (zie §6)
[4] Bij legacy_code + needs_choice → /oude-code-keuze
[5] Bij valid + bestaande user (with display_name):
      - controleer dat licenses.email == ingevoerd email (case-insensitive)
      - bij mismatch: redirect /licentie?error=email_mismatch
      - bij match: genereer 2FA-code, mail, redirect /verify
[6] Bij valid + nieuwe user:
      - UPDATE/INSERT users (password_hash = sha256 hex)
      - genereer 2FA-code, mail, redirect /verify
```

`/verify` (2FA) zet uiteindelijk `session.license_valid=True` en stuurt naar `/menu` (consumer) of `/pro` (pro).

---

## 5. Webhook-events: Stripe → DB-mutaties

### Entry: `/api/webhooks/stripe` (`server.py:2499`)

Authenticatie: HMAC via `STRIPE_WHSEC_LIVE/TEST`. Verwerkt:

| Event | Handler | DB-effect |
|---|---|---|
| `checkout.session.completed` (mode='subscription') | `_handle_checkout_session_completed` | UPSERT `subscriptions` (provider_ref=session_id, customer_id). **Geen license** in deze handler — wordt door `invoice.paid` aangemaakt. |
| `checkout.session.completed` (mode='payment') | idem | INSERT `licenses` direct met email, status='available'; verzendt activatie-mail; admin-notificatie. |
| `customer.subscription.created` | `_handle_subscription_created` | UPSERT `subscriptions` (status, trial_end, current_period_end, plan_id, stripe_customer_id). |
| `customer.subscription.updated` | `_handle_subscription_updated` | UPDATE `subscriptions` (status-mapping via `_map_stripe_sub_status`); update `licenses.cancelled_at` bij `cancel_at_period_end=true`. |
| `customer.subscription.deleted` | `_handle_subscription_deleted` | UPDATE `subscriptions.status='canceled'`; `licenses.cancelled_at`. |
| `invoice.paid` | `_handle_invoice_paid` | **INSERT OR IGNORE `licenses`** (status='available', user_key=sha256(email)[:32], stripe_subscription_id, expires_at=+365d); verzendt activatie-mail. Idempotent: bij bestaande sub-license → alleen `current_period_end` UPDATE. |
| `invoice.payment_failed` | `_handle_invoice_payment_failed` | UPDATE `subscriptions.status='past_due'`; admin-alert. Geen license-mutatie. |

### Plan-resolution

`plan_id_from_stripe(price_id, metadata)` → eerst lookup in `plans.stripe_price_id`, fallback `metadata['plan_id']`. Bij faal:
- `billing_events.status = 'plan_failed'`
- `send_admin_alert_plan_fail(...)` met line_items + metadata-dump
- Webhook retourneert 200 (Stripe stopt retries, admin handelt handmatig af)

**Bekende issue** ([[project_stripe_plans_sync]]): elke nieuwe Stripe price vereist handmatige rij in `plans`-tabel + event-resend; 3× plan_failed in 8 dagen rond rollout van `sc-pro-m-month` en `sc-month`. Fix-opties: webhook auto-create / cron-sync / deploy-checklist — nog niet geïmplementeerd.

### Out-of-order tolerantie

Stripe levert events soms niet in chronologische volgorde. De handlers zijn **idempotent** ontworpen:

- `INSERT OR IGNORE` op `licenses.license_key` (UNIQUE)
- `INSERT ... ON CONFLICT(subscription_id) DO UPDATE SET ...` met COALESCE op customer_id
- `invoice.paid` rowcount==0 → license bestaat al → skip mail
- `subscription.created` mag eerder of later komen dan `invoice.paid`

---

## 6. Licentie-aanmaak en activatie — stap voor stap

### Pad A: Stripe-checkout (consumer of pro abonnement)

```
[1] Klant doet checkout op stresschecker.lifestylemonitors.com (NL of DE)
    → Stripe Checkout sessie met metadata.webshop='nl'|'de'
[2] Bij betaling: Stripe stuurt 3-4 webhooks in willekeurige volgorde:
    - checkout.session.completed (mode='subscription')
    - customer.subscription.created
    - invoice.paid                         ← LICENSE WORDT HIER AANGEMAAKT
    - (later: customer.subscription.updated als status verandert)
[3] _handle_invoice_paid:
    - plan_id_from_stripe(price_id) → plan_id
    - license_key = SC-PRO-XXXXXXXX (pro) of SC-XXXX-XXXX-XXXX (consumer)
    - INSERT OR IGNORE INTO licenses (license_key, email, status='available',
        origin='webshop', user_key=sha256(email)[:32], stripe_subscription_id, ...)
    - send_activation_email(email, code, product_name, lang)
[4] Klant ontvangt mail met SC-code
[5] Klant gaat naar /licentie, vult code + email + (nieuw) wachtwoord in
[6] /activeer → validate_license() checkt licenses.email == form.email
[7] Bij match: 2FA-code per mail → /verify → session.license_valid=True
```

### Pad B: PayPal-subscription (HLM + sommige SC-klanten pre-2026-02)

```
[1] PayPal sub_id 'I-...' arriveert via /api/webhooks/paypal
[2] _handle_paypal_subscription_created (analoog aan Stripe-pad)
[3] INSERT licenses met paypal_subscription_id, email; status='available'
[4] Klant pad identiek aan Pad A vanaf stap [4]
```

### Pad C: WooCommerce-shop (eenmalige aankoop)

```
[1] WooCommerce-order op .nl of .de shop
[2] Plugin POSTs naar /api/...  ⚠️ TE VERIFIËREN: exacte endpoint
[3] redeem_codes.code aangemaakt met code_type='webshop', plan_id, status='unused'
[4] Klant ontvangt code per mail
[5] Bij /activeer → /api/redeem flow zet redeem_codes.status='redeemed'
    + INSERT licenses + INSERT user_licenses
```

**Note** ([[project_code_inconsistency_max_profiles]]): WooCommerce-pad geeft `max_profiles=5` (Stripe-pad) maar `app.py:4078` zet bij directe license-create `consumer=1`. Open inconsistentie — klantbeleving wijkt af tussen aankooppaden.

### Pad D: Handmatige aanmaak

Zie §7.

### Pad E: Marketing-code (unbound, nieuw 2026-05-20)

```
[1] Admin draait CLI:
    python3 /opt/stresschecker/scripts/create_marketing_code.py \
        --plan sc-pro-m --notes "Campagne X" [--valid-days 90]
[2] INSERT licenses (license_key, status='available', origin='marketing',
       email=NULL, expires_at=NULL, activated_at=NULL,
       code_expires_at = now + 90 days, plan-specifieke max_profiles)
[3] Admin deelt de code (mondeling, mail, beurs-flyer, partner-pakket)
    — geen mail-send via systeem, geen klant-email vooraf bekend
[4] Prospect ontvangt code, gaat naar /licentie, vult eigen email + code +
    nieuw wachtwoord in
[5] /activeer detecteert origin='marketing' AND email IS NULL:
       - Controleert code_expires_at >= nu (anders: weiger met "code verlopen")
       - UPDATE licenses SET email=<form>, activated_at=now,
                            expires_at = now + 365 days,
                            status='activated'
       - INSERT activation_log (action='activate_marketing', details)
[6] Standaard 2FA-flow → /verify → session.license_valid=True
```

**Belangrijk over de twee klokken:**
- `code_expires_at` (gevuld bij INSERT, default +90d): hoe lang kan de code worden geactiveerd?
- `expires_at` (NULL tot activering, dan +365d): hoe lang werkt de licentie nadat geactiveerd?

Eenmaal geactiveerd is het verschil met een reguliere Stripe-license verwaarloosbaar — behalve dat `origin='marketing'` zichtbaar blijft voor audit.

### Email-binding — antwoord op de hoofdvraag

> **Wordt `licenses.email` gezet bij INSERT of pas bij activering?**

**Antwoord: BIJ INSERT** voor Stripe/PayPal/WooCommerce/handmatige paden. **BIJ ACTIVERING** voor marketing-codes (origin='marketing') — zie Pad E hierboven.

Bewijs:
- `_handle_checkout_session_completed` mode='payment' (`server.py:1798-1805`): `INSERT INTO licenses (..., email, ...) VALUES (..., ?, ...)` — email-veld direct gevuld.
- `_handle_invoice_paid` (`server.py:2321-2332`): `INSERT OR IGNORE INTO licenses (..., email, user_key, ...) VALUES (..., ?, ..., ?, ...)` — email + user_key (sha256[:32]) beide direct gevuld.
- `new_customer.sql.template` (`/opt/ic-license-server/new_customer.sql.template`): `INSERT INTO licenses (..., email) VALUES (..., :EMAIL)` — handmatig pad doet hetzelfde.

`/activeer` (`app.py:561-571`) **leest** `licenses.email` om te valideren dat de ingevoerde email matcht; doet geen UPDATE van email. Bij mismatch wordt activatie geweigerd.

**Uitzonderingen:**
1. `_handle_invoice_paid` bij ontbrekende email-bron (line 2330): `email='unknown'` wordt opgeslagen, admin kan later via SQL UPDATE patchen.
2. Stripe mode='subscription' checkout: alleen `subscriptions` UPSERT, geen license-INSERT — license komt later via `invoice.paid`.

**Gevolg voor strategie:** een verkeerd ingevoerd email-adres bij checkout = klant kan niet activeren tot admin handmatig `licenses.email` corrigeert. Geen self-service correctie-flow.

---

## 7. Handmatige licentie-aanmaak

### Wanneer in te zetten

- **Support-recovery**: klant betaalde wel maar webhook-pad faalde (bv. `plan_failed`)
- **Migratie**: legacy PayPal-klant overzetten naar nieuwe plan-structuur
- **Krankenkasse-bulk**: vooraf gebonden codes voor Duitse verzekeraars (`origin='krankenkasse'`, `type='krankenkasse'`)

Voor **demo's, beurzen, partner-distributie, heropeningscampagnes** (codes zonder vooraf bekend e-mailadres): gebruik **marketing-codes** via `/opt/stresschecker/scripts/create_marketing_code.py` — zie §7b en Pad E in §6.

Pad: **direct SQL** tegen `/opt/ic-license-server/data/saas_licenses.db`. **Stop ic-license-server NIET** — SQLite writes blokkeren elkaar maar zijn kort. Maak wel een backup voor de mutatie.

### Code-format conventies

Bron: `database.py:175-181` (consumer) + `server.py:1777,2291` (pro).

| Plan-familie | Format | Voorbeeld | Generatie |
|---|---|---|---|
| Consumer (`sc`, `sc-month`, `sc-komplett`) | `SC-XXXX-XXXX-XXXX` | `SC-A3K2-9PQX-MN4B` | 3× 4-char uit KEY_CHARS, via `generate_unique_key(db, 'SC')` |
| Pro (`sc-pro-{s,m,l}` + `-month`-varianten) | `SC-PRO-XXXXXXXX` | `SC-PRO-9F4E2A1B` | `'SC-PRO-' + secrets.token_hex(4).upper()` (8 hex chars) |
| HLM Consumer | `HLM-XXXX-XXXX-XXXX` | `HLM-K7P3-MN21-ABCD` | analoog aan SC consumer |
| HLM Pro | `HLM-PRO-XXXXXXXX` | `HLM-PRO-1A2B3C4D` | analoog aan SC Pro |
| Handmatige bulk (legacy) | `SC-LL-YYYYMMDD-NNN` | `SC-DE-20260520-001` | per conventie, geen automatische generator |

### Default-waarden voor handmatige licenties

| Veld | Default | Toelichting |
|---|---|---|
| `product` | `'sc'` | `'hlm'` voor Lifestyle Monitor |
| `type` | `'consumer'` of `'pro'` | volgt plan-audience |
| `status` | `'available'` (klant moet zelf /activeer doen) **of** `'activated'` (directe handmatige) | bij `'activated'` ook `user_licenses`-rij aanmaken |
| `origin` | `'manual'` | onderscheidt van webshop/paypal/stripe |
| `email` | klant-email (lowercase) | **verplicht** voor binding |
| `max_profiles` | volgt `plans.max_profiles` (5 / 10 / 30 / 75) | |
| `max_clients` | 0 voor consumer; 10/25/100/500 Pro per tier | |
| `expires_at` | `datetime('now', '+1 year')` (jaarlijks) of `'+1 month'` (maandelijks) | ISO-8601 |
| `notes` | bv. `'Handmatig - demo voor Hans Mueller'` | audit-trail |

### Concrete SQL — SC Pro M (yearly)

```sql
BEGIN TRANSACTION;

-- 1. License-record
INSERT INTO licenses (
    license_key, product, type, status, origin,
    max_profiles, created_at, expires_at,
    email, product_name, notes
) VALUES (
    'SC-PRO-' || upper(hex(randomblob(4))),   -- of handmatig: 'SC-PRO-9F4E2A1B'
    'sc',
    'pro',
    'activated',                              -- direct actief (geen /activeer-stap)
    'manual',
    30,                                       -- max_profiles uit plans.sc-pro-m
    datetime('now'),
    datetime('now', '+1 year'),
    'klant@voorbeeld.de',
    'StressChecker Pro M Jahresabonnement',
    'Handmatig aangemaakt - reden: demo/support/partner'
);

-- 2. User-record (skip bij verlenging bestaand account)
INSERT OR IGNORE INTO users (
    email, password_hash, display_name, language,
    activated_at, license_expires
) VALUES (
    'klant@voorbeeld.de',
    'CHANGE_ON_FIRST_LOGIN',                  -- klant zet wachtwoord bij /activeer of /wachtwoord-vergeten
    'Klant Naam',
    'de',
    datetime('now'),
    datetime('now', '+1 year')
);

-- 3. Koppeling user ↔ license
INSERT INTO user_licenses (user_id, license_key, product, is_primary)
VALUES (
    (SELECT id FROM users WHERE email='klant@voorbeeld.de'),
    (SELECT license_key FROM licenses WHERE email='klant@voorbeeld.de' ORDER BY id DESC LIMIT 1),
    'sc',
    1
);

-- 4. (Optioneel) Subscription-record voor portal-tracking
INSERT INTO subscriptions (
    subscription_id, user_id, plan_id, status,
    current_period_end, provider, provider_ref
) VALUES (
    'manual-' || strftime('%s','now'),
    (SELECT id FROM users WHERE email='klant@voorbeeld.de'),
    'sc-pro-m',
    'active',
    datetime('now', '+1 year'),
    'manual',
    'Handmatige aanmaak 2026-05-20'
);

COMMIT;
```

### Concrete SQL — SC Pro M Monatsabonnement

Verschil met yearly: `plan_id='sc-pro-m-month'`, `expires_at = datetime('now', '+1 month')`, `current_period_end` idem. Status verder identiek.

### Concrete SQL — SC Jahresabonnement (consumer, `sc`)

```sql
BEGIN TRANSACTION;

INSERT INTO licenses (
    license_key, product, type, status, origin,
    max_profiles, created_at, expires_at,
    email, product_name, notes
) VALUES (
    'SC-' || substr(upper(hex(randomblob(2))),1,4)
        || '-' || substr(upper(hex(randomblob(2))),1,4)
        || '-' || substr(upper(hex(randomblob(2))),1,4),
    'sc',
    'consumer',
    'activated',
    'manual',
    5,                                        -- consumer default
    datetime('now'),
    datetime('now', '+1 year'),
    'consument@voorbeeld.nl',
    'StressChecker Jahresabonnement',
    'Handmatig - demo'
);

INSERT OR IGNORE INTO users (email, password_hash, display_name, language,
                              activated_at, license_expires)
VALUES ('consument@voorbeeld.nl', 'CHANGE_ON_FIRST_LOGIN', 'Naam',
        'nl', datetime('now'), datetime('now', '+1 year'));

INSERT INTO user_licenses (user_id, license_key, product, is_primary)
VALUES (
    (SELECT id FROM users WHERE email='consument@voorbeeld.nl'),
    (SELECT license_key FROM licenses WHERE email='consument@voorbeeld.nl' ORDER BY id DESC LIMIT 1),
    'sc', 1
);

COMMIT;
```

### Verificatie na handmatige aanmaak

```sql
SELECT u.email, u.display_name, u.language,
       l.license_key, l.type, l.status, l.expires_at, l.origin,
       s.plan_id, s.status AS sub_status, s.provider
FROM users u
LEFT JOIN user_licenses ul ON ul.user_id = u.id
LEFT JOIN licenses l ON l.license_key = ul.license_key
LEFT JOIN subscriptions s ON s.user_id = u.id
WHERE u.email = 'klant@voorbeeld.de';
```

Daarna **vertel de klant** welke code is uitgegeven (mail handmatig, niet via systeem-mail want dat triggert geen send_activation_email-pad).

---

## 7b. Marketing-codes (unbound) — aanmaak

Sinds 2026-05-20. Gebruik dit voor **codes zonder vooraf bekend e-mailadres**: prospect-demo's, beurs-uitdeling, partner-distributie, heropeningscampagnes.

Verschil met §7 (pre-bound handmatig): de prospect kiest **zelf** zijn e-mailadres bij activering. Geen mail-send vanuit het systeem; admin deelt de code via eigen kanaal.

### CLI

```bash
sudo -u www-data python3 /opt/stresschecker/scripts/create_marketing_code.py \
    --plan sc-pro-m \
    --notes "Heropeningscampagne Manuela Mühlberger 2026-05-20" \
    --valid-days 90
```

Parameters:
| Optie | Vereist | Default | Toelichting |
|---|---|---|---|
| `--plan` | ja | — | plan_id uit `plans`-tabel (sc / sc-month / sc-pro-s / sc-pro-m / sc-pro-l / ...) |
| `--notes` | ja | — | Campagne-aanduiding, komt in `licenses.notes` |
| `--valid-days` | nee | 90 | Hoeveel dagen mag code worden geactiveerd (1..3650) |

### Output

```
================================================================
Code:             SC-PRO-93CA4C99
Plan:             StressChecker Pro M Jahresabonnement
Type:             pro (max_profiles=30)
Aangemaakt:       2026-05-20 07:33:41 UTC
Code activeerbaar tot: 2026-08-18 07:33:41 UTC  (90 dagen)
Notes:            Heropeningscampagne Manuela Mühlberger 2026-05-20
Activatie:        https://stresschecker.lifestylemonitors.com/licentie
================================================================
DB-id:            268
```

### Wat er gebeurt in de DB

`INSERT INTO licenses` met:
- `status='available'`, `origin='marketing'`
- `email = NULL`, `activated_at = NULL`, `expires_at = NULL`
- `code_expires_at = datetime('now', '+N days')`
- `max_profiles` overgenomen uit `plans`-rij
- `product_name` = leesbare plan-naam
- `notes` = campagne-aanduiding

### Aktiverings-flow (kant van prospect)

Identiek aan reguliere `/licentie`-flow: code + e-mailadres + wachtwoord. De server-side branch in `app.py` (regels ±548-587) detecteert `origin='marketing' AND email IS NULL` en:
1. Controleert `code_expires_at >= nu` (anders weigering met "Deze code is verlopen")
2. `UPDATE licenses SET email=<form>, activated_at=now, expires_at=now+365d, status='activated'`
3. Logt `INSERT activation_log` met `action='activate_marketing'`
4. Vervolgt standaard 2FA-flow

### SQL-template (alternatief voor CLI)

`/opt/ic-license-server/marketing_code.sql.template` — voor handmatige aanmaak via sqlite3 als CLI niet beschikbaar is. Vereist eigen license_key + max_profiles + product_name + valid-days invullen.

### Audit-trail

Twee plekken:
- `licenses.notes` — campagne-naam, vrij tekstveld
- `activation_log` — `action='activate_marketing'`, `details='origin=marketing email=<bound>'`, met IP + UA

Voor uitgebreide attribution (welke distributiepartner, conversie-tracking): aparte tabel kan later worden toegevoegd. Nu: notes-veld volstaat.

### Beperkingen

- Geen self-service correctie als prospect een typo maakt in e-mailadres — license is bound aan eerste-getypte adres
- Code blijft activeerbaar door **iedereen** die hem kent (zoals een legacy-code) — geen domein- of identiteits-binding vooraf
- Bij verloren code: admin moet via SQL inspecteren (`SELECT ... WHERE notes LIKE '%Campagne X%'`) en eventueel `status='suspended'` zetten

---

## 8. Pairing (consumer ↔ Pro-cliënt koppeling)

Pro kan een consument als "cliënt" koppelen zodat de Pro de metingen van die consument ziet.

### Flow

```
[1] Pro voegt cliënt toe in /pro/clienten → POST /pro/client/toevoegen
[2] /api/pairing/generate              → 6-char code (token_hex(3).upper())
[3] Pro deelt code mondeling/per mail met cliënt
[4] Consumer logt in op zijn eigen account → /koppelen
[5] /api/pairing/redeem (consumer) → verzilvert code → link consumer.user_key ↔ pro.client_id
[6] Pro ziet consumer-metingen in /pro/client/<cid>/consumer-metingen
[7] Bij wens: /api/pairing/revoke om link te verbreken
```

Codes zitten in `pairing_codes`-tabel (kortlevend, eenmalig).

---

## 9. SendGrid + SMTP (transactional mail)

- **Activatie-mails**: `send_activation_email(to, code, product_name, lang)` in `server.py:1236`. Sjabloon NL/DE/EN inline in Python.
- **2FA-mails**: vanuit `app.py` (consumer-app), via SMTP-relay van Hostnet.
- **Admin-notificaties**: `send_admin_notification(...)` voor elke succesvolle aankoop; `send_admin_alert_plan_fail()` bij webhook-fail.
- **Cancel-bevestigingen**: `send_cancel_email(...)` in `server.py:2844`.

**Provider-keuze:**
- Consumer-app 2FA + password-reset → SMTP (Hostnet mailbox `noreply@lifestylemonitors.{com,de}`)
- License-server activatie + admin-mails → SendGrid (sinds 2026-05-13 sprint 1 deels gemigreerd; nog niet bedraad — zie [[project_ic_license_sendgrid_sprint1]])

**Bekende DMARC-issue:** DE-domein blokkeert SendGrid deliverability tot Domain Authentication in DNS staat ingericht. Open ticket.

---

## 10. Stripe Customer Portal

Spoor 3 (live sinds 2026-05-16):

- Ingelogde Stripe-klanten zien knop "Abonnement beheren" op `/licentie`
- Knop alleen zichtbaar als `subscriptions.stripe_customer_id IS NOT NULL` voor user
- Klik → `/account/manage-subscription` → `stripe.billing_portal.Session.create(...)` met configuration `bpc_1TVpFcHD28PM4o1K18URnQAI`, locale uit session
- Klant kan opzeggen, betaalmethode wijzigen, facturen downloaden in Stripe-hosted UI
- Return-URL: `/licentie`

PayPal- en handmatige-licentie klanten zien de knop niet. Bij directe URL-toegang → flash + redirect met info-mail-verwijzing.

---

## 11. Veiligheid & known issues

### Productie-issues (open)

- **2FA-codes in journalctl** (12-05-2026): `logging.warning("2FA CODE: ...")` lekt codes plaintext naar systeemlog. Mitigatie: redactie of verwijderen log-statement.
- **Email-enumeration timing-side-channel** in `/wachtwoord-vergeten`: SendGrid-call alleen voor bestaande accounts, ~200-500ms verschil.
- **Wachtwoord-hash = sha256 hex** (geen bcrypt/argon2/salt). ⚠️ Bij scaling overwegen te migreren.
- **Service worker cachet HTML** ([[project_sw_cache_followup]]): klanten zien oude UI na deploy. Open fix.

### DB-integriteit

- `licenses.license_key` UNIQUE — botsing onmogelijk
- `licenses.email` **niet UNIQUE** — een email kan meerdere licenses bezitten (consumer + pro, of na verlenging)
- `subscriptions.subscription_id` UNIQUE — borgt UPSERT-veiligheid
- `users.email` UNIQUE, COLLATE NOCASE in queries — geen duplicaten door case-mismatch
- **Belangrijk** ([[feedback_no_email_merge]]): consumer en Pro-accounts moeten gescheiden blijven; `user_keys` mogen niet auto-mergen.

### Backups

- `/opt/stresschecker/backup.sh` draait dagelijks (cron); backups in `/opt/backups/*.YYYYMMDD-HHMM`
- DB-backup: `saas_licenses.db.backup-YYYYMMDD-HHMM`
- Ad-hoc backup voor riskante mutaties: `cp data/saas_licenses.db data/saas_licenses.db.bak_<reden>_<timestamp>`

---

## 12. Code-zonder-email patronen

Drie verschillende unbound-flows bestaan parallel in het systeem. Ze lijken op elkaar maar zijn architectonisch gescheiden — een wijziging in één pad raakt de andere niet.

### 1. Legacy-keys

**Tabel:** `legacy_keys`, status `'available'` / `'issued'` / `'unknown'`
**Doel:** Oude StressChecker Amazon-aankopen pre-2026
**Karakter:** Migration-tool met einddatum (target sluiting 31 december 2026)
**Activering:** via `/oude-code-keuze` pad — user kiest consumer/pro at-activation, nieuwe `licenses`-rij wordt aangemaakt met `origin='migration'`
**Omvang:** 3999 stuks bij intake; 9 inmiddels gemigreerd

### 2. Marketing-codes (nieuw 2026-05-20)

**Tabel:** `licenses`, `origin='marketing'`, `email IS NULL`
**Doel:** Campagne-codes voor prospects, beurzen, partners, heropeningscampagnes
**Karakter:** Doorlopende feature, geen einddatum
**Activering:** via `/activeer` met email-binding-bij-activatie (`UPDATE licenses SET email=?, expires_at=?, status='activated'`)
**Houdbaarheid pre-activatie:** `code_expires_at` (default +90 dagen) controleert of code nog activeerbaar is
**Aanmaak-pad:** `/opt/stresschecker/scripts/create_marketing_code.py` (CLI)

### 3. Verloren ad-hoc rijen

**Tabel:** `licenses`, `origin='manual'`, `email IS NULL`
**Doel:** Historische ad-hoc aanmaken zonder email-binding
**Voorbeeld:** `SC-CON-8F4B1135` (id=44, aangemaakt 2026-04-13, herkomst onbekend, status='available')
**Status:** Niet door actuele marketing-flow geaccepteerd (strikte filter `origin='marketing'`)
**Beleid:** Laten staan tenzij specifieke business-reden voor opruiming

### Belangrijk

De marketing-flow heeft een **strikte filter** `origin='marketing' AND email IS NULL` in `/activeer`. Categorie (1) en (3) blijven daardoor ongemoeid bij activatie via de nieuwe flow. Bij elk van de drie categorieën een wijziging maken vereist expliciete acties op die specifieke tabel/conditie.

### Marketing-code herclaim-bescherming

Sinds 2026-05-20: marketing-codes hebben een aparte guard tegen herclaim:

- **Eerste activeerder** (form-email = X, license.email = NULL): UPDATE bindt email X aan license, status='activated'
- **Tweede claim met afwijkend email** (form-email = Y, license.email = X): geweigerd met "Deze code is al geactiveerd" / "Dieser Code wurde bereits aktiviert" / "This code has already been activated"
- **Hercontact zelfde email** (form-email = X, license.email = X): doorgelaten naar standaard herlogin-pad (2FA)

Rationale: marketing-codes circuleren breed (campagnes, beurzen, partner-distributie). Zonder vooraf-bekende email is "wie eerst is, krijgt 'm" de gewenste semantiek.

**Stripe/PayPal/manual hebben deze guard NIET** — eigen risicoprofiel met "betaal-ownership" maakt het minder relevant. Bestaande pre-existing-zwakheid in `/activeer` else-branch (app.py:601-622, geen email-match check voor nieuwe-user-pad) blijft van toepassing voor die origins en is opgemerkt als follow-up — eigen iteratie indien gewenst.

Toekomstige consolidatie naar één gedeelde "unbound-activate"-handler is mogelijk maar **niet aanbevolen** zolang legacy-pad nog actief is — zou risico introduceren op de 3990 nog-te-migreren legacy-codes.

---

## 13. Open vragen / inconsistenties (TE VERIFIËREN)

1. **max_profiles inconsistentie** ([[project_code_inconsistency_max_profiles]]): `app.py:4078` zet bij directe license-create `consumer=1`, terwijl Stripe-pad + plans-DB `consumer=5` zetten. WooCommerce-aankoop geeft mogelijk andere ervaring dan Stripe-aankoop.
2. **Stripe plans-tabel sync gap** ([[project_stripe_plans_sync]]): nieuwe Stripe prices vereisen handmatige `plans`-rij + event-resend. 3× fout in 8 dagen. Geen geautomatiseerde oplossing.
3. **WooCommerce → license-server endpoint**: welke endpoint exact wordt aangeroepen door de WC-plugin (`/api/redeem`? `/api/license/create`?) is in deze sessie niet bevestigd.
4. **Wachtwoord-hash**: sha256 hex zonder salt — bewuste keuze of legacy? Migratie naar bcrypt overwegen.
5. **`licenses.user_key` field**: gevuld door invoice.paid (Stripe), maar niet door checkout.session.completed (mode=payment) en niet door handmatige SQL-template. Mogelijke gap bij oude licenties → portal-knop werkt niet.
6. **Mail-template umlauts** ([[project_mail_template_umlauts]]): DE-template gebruikt ASCII-fallbacks (fuer/ueber/Gruessen); Kunde/Kundin inconsistent. Cosmetisch maar maakt mail "amateurish".

---

## 14. Referenties — bestanden om te raadplegen

| Doel | Bestand |
|---|---|
| Volledige route-lijst app.py | `/opt/stresschecker/CONTEXT.md` (auto-gegenereerd) |
| Webhook-handlers | `/opt/ic-license-server/server.py:1629-2497` |
| DB-schema | `sqlite3 /opt/ic-license-server/data/saas_licenses.db ".schema"` |
| Plans-tabel | `sqlite3 /opt/ic-license-server/data/saas_licenses.db "SELECT * FROM plans;"` |
| Handmatige aanmaak SQL-template | `/opt/ic-license-server/new_customer.sql.template` |
| License-server deploy | `/opt/ic-license-server/DEPLOYMENT.md` |
| Backup-script | `/opt/stresschecker/backup.sh` |
| Tests | `/opt/stresschecker/tests/run_all.sh` |
| Service-units | `systemctl cat stresschecker.service`, `systemctl cat ic-license-server.service` |

---

*Einde document. Versie 1.0, 2026-05-20.*
