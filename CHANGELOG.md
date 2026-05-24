# StressChecker — Recente wijzigingen

## 2026-05-24 — KKH-zelfbeheer kantoor-master-lijst (Sessie B.1)

Self-service kantoor-beheer voor KK-licenties. Schmidt (KKH-admin) en collega's loggen in op hetzelfde KK-account; één-rol-model. CRUD + CSV-bulk-import + overzicht met meting-counts en M/V-tellers per kantoor. Geen rol-onderscheid, geen aparte logins. Coexisteert met de bestaande Paul-only `/admin/krankenkasse/<code>/offices` (cross-licentie-toegang).

### Migratie

- `saas_licenses.db`: `ALTER TABLE krankenkasse_offices ADD COLUMN region TEXT` — 3 fixtures behouden, region=NULL voor bestaande rijen
- Pre-migratie backup: `/opt/backups/*.20260524-2006`

### Backend (app.py)

Helpers vlak na `pro_locatie`-route:
- `_kk_require()` — `abort(403)` voor anon en niet-KK-sessies
- `_kk_db()` — sqlite3-connect saas_licenses.db met Row-factory
- `_kk_office_stats(license_code, pro_key)` — cross-DB aggregatie (saas_licenses.db.krankenkasse_offices + sc_pro.db.client_metingen∗clients). Twee queries, Python-merge — geen ATTACH
- `_parse_kk_csv(raw_bytes, max_rows=500)` — strikte parser: header verplicht `office_name`+`region`, UTF-8 + BOM, autodetect `,`/`;`/`\t`, 100-char cap, lege names → skip + error

8 nieuwe routes (allemaal `_kk_require()`-gated, géén `@require_kk_office_if_krankenkasse` zodat Schmidt zonder eerst kantoor te kiezen kan importeren):

| Route | Methode | Gedrag |
|---|---|---|
| `/pro/locaties` | GET | Overzicht read-only met sort (`name`/`region`/`metingen`) + zoek-query (`q=`) |
| `/pro/locaties/beheren` | GET | Beheer-UI met form + per-rij always-editable input + acties |
| `/pro/locaties/toevoegen` | POST | INSERT single, case-insensitive dup-check, redirect `?created=1`/`?error=leeg`/`?error=dup` |
| `/pro/locaties/<oid>/bewerken` | POST | UPDATE naam+region, cross-tenant 404-guard, refresh `session['kk_office']` bij naam-wijziging van actief kantoor (historische `client_metingen.office_label`-strings blijven bewaard — audit-trail) |
| `/pro/locaties/<oid>/deactiveren` | POST | `active=0` |
| `/pro/locaties/<oid>/reactiveren` | POST | `active=1` |
| `/pro/locaties/import` | GET | Form |
| `/pro/locaties/import` | POST | 2-staps: upload → preview met `csv_text` hidden field; confirm=1 → batch-INSERT met dup-skip, redirect overzicht met `?imported=X&dups=Y` |

`abort` toegevoegd aan top-level Flask-import (regel 1).

### Templates (4 nieuwe + 2 menu-link-edits)

- `templates/pro/locaties_overzicht.html` — read-only tabel met Naam/Regio/Status/Metingen/M/V/Overig, sort-knoppen (default `name` asc), zoekveld, KK-badge `#1565c0`, empty-state met CSV-importeren-CTA
- `templates/pro/locaties_beheren.html` — flash-messages (created/updated/deactivated/reactivated/error=leeg/dup), add-form bovenaan, lijst met always-editable input-velden per rij + Opslaan/Deact/React-acties + JS `confirm()` voor deactiveren in 3 talen, empty-state
- `templates/pro/locaties_import.html` — file-upload-form, format-uitleg met live CSV-voorbeeld (Hamburg-Mitte / Bayern / Niedersachsen samples)
- `templates/pro/locaties_import_preview.html` — summary (totaal/nieuw/dup-counts), preview-tabel (max 20 nieuwe rijen + max 10 duplicates), warning-list voor parse-errors, "X importeren"-knop met `confirm=1` + hidden `csv_text`, Annuleren-link
- `templates/pro/locatie_keuze.html` — kleine "⚙ Locaties beheren →"-link onderaan (alleen voor KK, niet prominent)
- `templates/settings.html` — KK-tier-widget krijgt extra link "⚙ Locaties beheren →" onder "Huidige locatie"

### Verificatie

- `py_compile app.py`: OK
- Jinja-parse via `app.jinja_env` op 6 templates: OK
- `tests/run_all.sh`: 18/18 groen
- KK-render-smoke: /pro/locaties + /pro/locaties/beheren + /pro/locaties/import alle 200 met verwachte elementen
- **CSV-flow**: upload `office_name,region\nSMOKE_one,RegionA\nSMOKE_two,RegionB\nHannover,Niedersachsen\n` → preview toont 2 nieuw + 1 dup met Hannover in dup-list; confirm → 302 `/pro/locaties?imported=2&dups=1`; DB-state na confirm: SMOKE_one + SMOKE_two ingevoegd, Hannover (case-insensitive dup) overgeslagen
- **Edit-flow**: bewerken → `?updated=1` + flash; deactiveren → `?deactivated=1` + flash zichtbaar; reactiveren → `?reactivated=1`
- **Cross-tenant lek-test** (uit backend-fase): andere licentie's office-id bewerken vanuit KK-sessie → 404
- **Parser-tests**: BOM+semicolon → autodetect; missende `region`-kolom → duidelijke error; lege office_name → skip + warning; >500 rijen → cap
- **Pro-regressie**: niet-KK-sessie → 403 op alle 3 GET-routes; bestaande Pro-flows ongewijzigd
- Journalctl schoon na restart

### Geraakte bestanden

- `app.py` — abort-import + 3 helpers + 8 routes
- `CHANGELOG.md` — deze entry
- `templates/pro/locaties_overzicht.html` (nieuw)
- `templates/pro/locaties_beheren.html` (nieuw)
- `templates/pro/locaties_import.html` (nieuw)
- `templates/pro/locaties_import_preview.html` (nieuw)
- `templates/pro/locatie_keuze.html` — beheer-link onderaan
- `templates/settings.html` — beheer-link in KK-tier-widget

### TODOs / open punten

1. **Cross-DB `_kk_office_stats` is O(licentie-omvang)** — twee queries per render. Voor 80+ kantoren is dit nog OK; bij honderden actieve KK-licenties met elk veel kantoren kan caching nuttig zijn. Out-of-scope voor B.1.
2. **Soft-delete vs hard-delete**: alleen soft (active=0). Historische metingen blijven gekoppeld aan de oude `office_label`-string. Bij hernoeming wordt de nieuwe naam in `session['kk_office']` gezet; nieuwe metingen krijgen nieuwe naam, oude metingen blijven onder oude naam (audit-trail). Geen overschrijving van bestaande `client_metingen.office_label`.
3. **CSV-confirm-flow stuurt `csv_text` via hidden field** — voor 500 rijen × ~50 chars ≈ 25 KB POST-body. Acceptabel; bij groter volume zou je server-side temp-storage of session-based draft willen.
4. **Geen audit-log voor kantoor-wijzigingen** — INSERT/UPDATE/DELETE acties worden niet gelogd in `activation_log` (zoals admin-routes wel doen). Overweeg bij privacy/compliance-eisen vanuit KKH. Out-of-scope nu.
5. **Browser-end-to-end-check** door Paul (zoals Sessie A) — alle paden via Flask-test-client bewezen.

## 2026-05-24 — Krankenkasse-UI-verfijningen (Sessie A.1)

Cleanup na browser-test Sessie A: PRO-badge en consumer-pairing-flow zichtbaar in /pro-context die voor KK-medewerker misleidend zijn. Alleen Jinja-conditionals, geen DB-wijzigingen, geen routes, geen helpers.

### Context-processor

`@app.context_processor _inject_kk_flags()` (app.py vlak na `require_kk_office_if_krankenkasse`) — levert `is_krankenkasse` aan ELKE template, zonder view-functies te hoeven aanpassen. Sluit aan op de bestaande `is_krankenkasse_session()`-helper uit Sessie A. Vier regels.

### Templates aangepast

| Bestand | Wijziging |
|---|---|
| `templates/pro/client_detail.html` | PRO-badge in `.pro-nav` (regel 44) → `{% if not is_krankenkasse %}`; volledige Koppeling-sectie (pairingSection div + script-block met `generatePairingCode`/`revokePairing`/`showConsumerMetingen`) gewrapt in `{% if not is_krankenkasse %}...{% endif %}`. Twee separate Jinja-blocks: één voor de div (regel ~85-91), één voor het script (regel ~93-180). De later JS-block op regel 204 (`var lang = lang || "{{ lang }}"`) gebruikt fallback en blijft werken zonder de eerste script-block. |
| `templates/pro/clients.html` | PRO-badge in header (regel 29) → conditional |
| `templates/pro/dashboard.html` | PRO-badge `<span class="pro-badge">` (regel 31) → conditional |
| `templates/pro/client_add.html` | PRO-badge in screen-title (regel 6) → conditional. Aanvulling op Sessie A waar alleen de form-velden conditioneel waren. |

NIET aangeraakt (must-stay voor KK):
- "Meting kiezen"-knop, "Cliënt verwijderen"-knop, cliënt-info, breadcrumb "← Cliënten / ≡ Pro Menu"
- pro/eigen_metingen.html, pro/verloop.html, pro/meting_keuze.html (geen PRO-badge-instances of misleidende koppeling-refs)
- "Pro Menu" → "KK Menu"-hernoeming overwogen maar afgewezen; valt onder NIET-aanraken-lijst van de spec

### Verificatie

- `py_compile app.py`: OK
- Jinja-parse via `app.jinja_env.get_template()` op 4 templates: OK (vereist app-context vanwege custom `full_name` filter)
- Service restart schoon; geen errors in journal
- `tests/run_all.sh`: 18/18 groen
- Smoke via Flask test-client met temp-cliënten onder correcte pro_key-hash (paulpannevis@gmail.com + paulpannevis+kktest@gmail.com); cliënten direct opgeruimd na test:

**Pro-sessie** (regressie): PRO-badge zichtbaar op /pro/clienten + /pro/client/<id> + /pro/dashboard + /pro/client/toevoegen ✓; Koppeling-blok zichtbaar op /pro/client/<id> ✓; Meting-knop + Verwijderen-knop blijven zichtbaar ✓.

**KK-sessie**: PRO-badge weg op alle 4 plekken ✓; Koppeling-blok volledig uit DOM ✓; Meting-knop + Verwijderen-knop blijven zichtbaar (must-stay) ✓.

### Backup

`/opt/backups/*.20260524-1939`

### Open punten

- Geen TODOs uit deze sub-sessie. Resterende Sessie-A-TODOs blijven open (browser-end-to-end-check door Paul, Reply-To-bevestiging info@lifestylemonitors.de, KK-tier-widget zonder einddatum, 2FA-codes plaintext in journal).

## 2026-05-24 — Krankenkasse-licentie-tier — fundering (Sessie A)

Nieuwe licentie-categorie voor Krankenkassen (gezondheidsdagen, multi-kantoor onder één centraal account). Eerste klant: KKH. Tier-gestaffeld (Kompakt/Standard/Premium) op verzekerden-aantal; handmatige activatie (geen Stripe Payment Link).

### Migraties

- `saas_licenses.db`:
  - 3 nieuwe rijen in `plans`: `sc-krankenkasse-{kompakt,standard,premium}` (audience='krankenkasse', max_profiles=-1, max_clients=-1, stripe_price_id=NULL)
  - Nieuwe tabel `krankenkasse_offices(id, license_code, office_name, active, created_at)` + index `idx_kk_offices_license`
- `sc_pro.db`:
  - `ALTER TABLE client_metingen ADD COLUMN office_label TEXT` — 220 bestaande rijen behouden, allemaal NULL

### Audience-onderscheid

`audience` wordt voor het eerst in code gebruikt. `validate_license()` joint nu `plans.audience` mee; resultaat populeert `session['audience']` + `session['plan_id']` in `/activeer`, `verify_2fa` en `admin_bypass`-paden. Bestaande `is_pro()`-detectie blijft via `session['license_type']='pro'` voor KK-licenties (sub-rol bovenop Pro).

Nieuwe helpers (app.py vlak na `_is_pro_or_demo_pro`):
- `is_krankenkasse_session()` — boolean
- `kk_tier_label()` — 'Kompakt'/'Standard'/'Premium'/'?' uit `session['plan_id']`
- `@require_kk_office_if_krankenkasse` — decorator: KK-sessie zonder `session['kk_office']` → redirect naar `/pro/locatie`

Decorator-coverage: `pro_menu`, `pro_eigen_metingen`, `pro_clients`, `pro_dashboard`, `pro_client_detail`, `pro_client_measure`, `pro_client_add`, `pro_meting_keuze`. NIET op `pro_locatie` zelf, `settings`, `logout` (anders redirect-loop of geen ontsnapping).

### Locatie-keuze-flow

`/pro/locatie` (GET+POST) — leest `krankenkasse_offices` voor `session['license_code']`, dropdown met active=1 rijen, POST verifieert keuze tegen DB en zet `session['kk_office']`. Header in `base.html` toont KK-badge "Locatie: {office} [Wijzigen]" alleen voor KK-sessie. `templates/pro/locatie_keuze.html` (nieuw).

### Verkorte invoer-UI

`templates/pro/client_add.html` — Jinja-conditional `{% if not is_krankenkasse %}`: surname/email/phone/notes + hr-separator volledig weggelaten uit DOM voor KK-sessie. Voornaam blijft verplicht; geboortejaar+geslacht worden verplicht (i.p.v. defaults op 1970/male) zodat HRV-norm-mapping per deelnemer klopt.

### Office-label op meting

`api_meting_opslaan`: INSERT in `client_metingen` uitgebreid met 23e kolom `office_label`. Waarde = `session.get('kk_office')` enkel als `is_krankenkasse_session()` — voor Pro-sessie blijft de kolom NULL (regressie-bewezen via test-client).

### Admin-flow (handmatige activatie)

Nieuwe routes met `X-Admin-Token`/`?token=…` gate (env-var `ADMIN_KK_TOKEN` in `/opt/stresschecker/.env`, 43-char urlsafe):
- `GET/POST /admin/krankenkasse/new` — licentie aanmaken, code-formaat `SC-KK-XXXX-XXXX` (hex), origin='krankenkasse', plan_id-binding, optioneel direct welkomstmail
- `GET/POST /admin/krankenkasse/<code>/offices` — kantoor-master-lijst beheren (toevoegen)
- `POST /admin/krankenkasse/<code>/offices/<id>/deactivate` — soft delete (active=0)
- `POST /admin/krankenkasse/<code>/send-welcome` — welkomstmail (her)verzenden

Nieuwe templates: `admin/kk_new.html`, `admin/kk_offices.html`.

`send_kk_activation_email` (DE zakelijk, Reply-To `info@lifestylemonitors.de`, from `noreply@lifestylemonitors.com`) volgt het patroon van `send_verification_code`. Gebruikt ASCII-fallbacks (ueber/fuer/Gruessen) consistent met bestaand `mail_template_umlauts`-patroon.

### Tier-widget (Pro vs KK)

Bestaande Pro-tier widget op `/pro` (`pro/menu.html`) en `/instellingen` (`settings.html`) toont voor `audience='krankenkasse'` een KK-variant: "Krankenkasse-Lizenz: {Tier}" + "Unbegrenzte Teilnehmerzahl bei Gesundheitstagen" (NL/DE/EN). Reguliere Pro-cohorts behouden Pro S/M/L-rendering (regressie-bewezen via curl).

### Backups + verificatie

- Pre-migratie backup: `/opt/backups/*.20260524-1856`
- `py_compile app.py`: OK
- `tests/run_all.sh`: 18/18 groen (categorie A 6/6, B 4/4, C 8/8)
- Jinja2 parse op 7 geraakte templates: OK
- Smoke-tests admin-flow: 401 zonder token, 200 met token, POST → licentie aangemaakt + kantoren toegevoegd (DB-verificatie)
- KK-flow end-to-end via Flask test-client: validate_license → audience='krankenkasse'; /pro zonder kk_office → redirect /pro/locatie; POST locatie → /pro met KK-widget zichtbaar; client_add toont alleen voornaam/birth_year/gender; api/meting/opslaan vult office_label='Hannover'
- Pro-regressie: alle 4 optionele velden zichtbaar; office_label blijft NULL; bestaande Pro S/M/L tier-widget rendert ongewijzigd

### Test-fixture (per TEST_ACCOUNTS-policy: niet opruimen)

- Licentiecode: `SC-KK-44F6-14A3` (sc-krankenkasse-standard)
- Contact-email: `paulpannevis+kktest@gmail.com`
- 3 kantoren: Hannover, Hamburg, München
- Notes-flag: `Krankenkasse: KKH-Test-<ts>`

### Out-of-scope (komt in Sessie B)

- Rapportage-laag (aggregatie-queries per office, PDF-generatie, async generatie)
- Office-label uitgebreid analytics (per kantoor RI-distributie, etc.)
- Pro-rapportages
- HLM-blueprint blijft ongemoeid (zomer 2026 herbouw)

### Open punten / TODOs

- Welkomstmail-flow: bij POST via `X-Admin-Token` header is `request.form['token']` leeg → redirect-URL bevat `?token=` (leeg). Voor browser-flow met hidden form-veld werkt het correct. Curl-gebruikers moeten handmatig token toevoegen aan vervolgaanroepen.
- KK-tier-widget toont géén einddatum (valid_until ligt 365d weg, geen Stripe-renewal). Eventueel later toevoegen als KK-contracten daadwerkelijk verlopen.
- `templates/pro/locatie_keuze.html` toont "neem contact op met sales"-fallback als offices=0; admin-flow voorziet hier nu in maar de KK-contactpersoon krijgt geen automatische hint. Later: link naar contact-pagina.
- 2FA-codes plaintext in journalctl blijft staan (pre-existing HIGH-PRIORITY follow-up).
- Daadwerkelijke browser-end-to-end (login via /activeer + 2FA-mail) niet tijdens deze sessie uitgevoerd: vereist email-toegang voor verificatiecode. Alle paden zijn via Flask test-client end-to-end bewezen.

## 2026-05-24 — Optioneel achternaam-veld (drie naam-rollen)

Voornaam blijft verplicht, achternaam optioneel toegevoegd aan zowel het profiel van de gebruiker (consument en Pro delen `users.display_name`) als aan Pro-cliëntprofielen (`sc_pro.db.clients`).

### Migraties

Twee `ALTER TABLE … ADD COLUMN surname TEXT`:

- `/opt/ic-license-server/data/saas_licenses.db` → `users` (dekt rol 1 consument en rol 2 Pro eigen profiel — gedeeld pad via `save_profile` + `api_save_settings`)
- `/opt/stresschecker/data/sc_pro.db` → `clients` (dekt rol 3 Pro's cliënt)

De andere kandidaat-tabellen (`sc_measurements.db.user_profiles.naam` en `saas_licenses.db.profiles.name`) zijn ongemoeid gelaten — beide hadden 0 rijen en geen INSERT/UPDATE-pad in app.py (dode schema's).

### Display-logica

Nieuwe Jinja-filter `full_name` (app.py:99) rendert `'voornaam achternaam'` als `surname` aanwezig, anders alleen `voornaam`. Werkt op `sqlite3.Row`, dict, object met `.name`/`.surname`-attrs, of string + optionele 2e arg. Gebruikt in `pro/client_detail.html` (h2, nav-bar, Innerlijk Kompas-kop), `measure.html`, `sensor_en_meten.html`. Voor `kwadrant.html` wordt de full-name server-side in `client_name` gestopt (regel 1267 in app.py).

### Sessie-beleid

- `session['profile_name']` blijft voornaam (compact, header-badge `base.html:51` ongewijzigd).
- `session['profile_surname']` apart bijgehouden, gerenderd op detail-pagina's en meet-schermen.

### Backward compatibility

Bestaande rijen behouden hun string in `name`/`display_name`; `surname=NULL`. Geen auto-split: "Anna de Vries", "Paul Pannevis", "Steven P" worden ongewijzigd weergegeven. Bij volgende edit kan de eigenaar de naam zelf splitsen.

### Templates uitgebreid

- `templates/profile.html` — surname-input onder voornaam (consument + Pro eigen profiel)
- `templates/settings.html` — `inputSurname`-veld + JS-payload uitgebreid
- `templates/pro/client_add.html` — surname-input (Pro nieuwe cliënt)
- `templates/pro/client_detail.html` — `editSurname`-input + display via `{{ client|full_name }}` op 3 locaties

### Routes uitgebreid (app.py)

`save_profile`, `api_save_settings`, `pro_client_add`, `api_pro_client_update`, `pro_client_measure` (session), `sensor_en_meten` (profile-dict), `biofeedback` (profile-dict), `kwadrant` (client_name), `settings` (template-context). Login-paden (regel 644, 856) lezen surname mee. `admin_bypass` splitst Paul/Pannevis.

### Out-of-scope (TODO achtergelaten)

- HLM-blueprint gebruikt aparte `clients`-tabel in saas_licenses.db (schema met `display_name`); wordt zomer-2026 herbouwd. TODO-comment op beide initials-regels in `hlm/meting_src.html` (8449, 8754).
- Pre-existing issues opgemerkt, niet aangeraakt:
  - `/admin-login-bypass-9x7k` zet `user_key` handmatig maar `get_user_key()` overschrijft direct op basis van `sha256(email)[:32]`.
  - Dode `session['pro_display_name']`-fallback in `settings.html:97` — nergens geset.

### Validatie

- Pre-migratie backup: `/opt/backups/*.20260524-1457`
- `py_compile app.py`: OK
- `systemctl restart stresschecker`: workers up, geen errors in journal
- `tests/run_all.sh`: 18/18 groen
- 3-talen smoke (NL/DE/EN): labels correct, full-name rendering correct
- Backward compat: Anna de Vries blijft "Anna de Vries", avatar='A', geen NULL of rare karakters
- Nieuwe cliënt Peter+Pannevis: DB → name='Peter', surname='Pannevis'; rendering → "Peter Pannevis" overal (h2, meting-schermen, kwadrant)

## 2026-05-22 — RI birth_year/gender uitvraag in activatie-flow

Verplichte uitvraag van `birth_year` + `gender` vóór eerste meting, met norm-mapping voor non-binary opties. Fixt drie samenhangende latente bugs en lift de "71% van users heeft default 1970/male"-anomalie.

### Latente bugs gefixt

- **save_profile sloeg birth_year/gender niet op in users-tabel** (`app.py:987-1007`). UPDATE-statement vulde alleen activated_at + license_expires. Birth_year/gender bleven session-only en gingen verloren bij logout. Nu: `display_name`, `birth_year`, `gender` worden gepersisteerd, met `COALESCE(activated_at, ?)` zodat eerste-keer-vulling intact blijft.
- **license_expires-gat** (secundair gefixt): `license_notifications.py:225` filtert renewal-mails op `WHERE license_expires IS NOT NULL`. 71% van users had `license_expires=NULL` en kreeg dus géén 30/7-dagen-vervalwaarschuwing. Save_profile vult license_expires nu wél bij eerste keer.
- **activated_at-gat** (impliciet gefixt door save_profile-COALESCE): users zonder profile_setup hadden `activated_at=NULL`.

### Nieuwe features

- **verify_2fa redirect naar profile_setup** als `users.birth_year IS NULL OR = 1970` (app.py:884).
- **/sensor-en-meten block-check voor eigen-meting** (app.py:1140+): bij `_cid==0` redirect naar `/profiel?reason=meting_blocked` met visuele banner.
- **4 gender-opties** in profile.html: male/female/divers/unspecified, geen default-checked, `placeholder="1985"` ipv `value="1970"`.
- **hrv.js norm-mapping** voor `gender ∈ {divers, unspecified}` → `(n.m+n.f)/2`. Bewezen via node-test: male=78 > divers=74 = unspecified=74 > female=70 (age 41, RMSSD ≈ 28).

### Buiten scope (vastgelegd in CLEANUP_TODO ## TODO)

- HLM-flow: eigen client-side birth_year/gender via localStorage en eigen norm-tabel — meenemen in HLM Pro nieuwe generatie (~1 aug 2026).
- Norm-tabel-consolidatie tussen hrv.js en hlm/meting_src.html (1.3 RI-punten divergentie).
- `profile_completed` boolean-kolom (vervangt 1970-heuristiek).
- activation_log gap voor manual-origin accounts.
- **2FA-codes plaintext in journalctl** — HIGH PRIORITY, herbevestigd vandaag.

### Validatie

- Backup-snapshot vóór wijziging: `/opt/backups/*.20260522-1128`
- `py_compile` na elke .py-Diff: OK
- Jinja2 parse `profile.html`: OK
- `node -c hrv.js`: OK
- HUP gunicorn master: workers respawn zonder errors
- End-to-end curl-flow + 2 test-fixtures (id=25 female 1985, id=26 divers 1990): alle 5 Diffs (A-E) bewezen werkend
- Existing users (Paul 1949, Steven 1982): géén redirect-impact

## 2026-05-22

Codebase cleanup volgens CLEANUP_TODO.md, gefaseerd uitgevoerd met checkpoint-akkoorden (Fase 1 inventarisatie, Fase 2 uitvoering A→H).

### 2-A — Onderzoek `ic_licenses.db`
Verlaten schema-prototype in repo-root (122 KB, 13-05-2026, geen code-refs). Alle 7 tabellen leeg; schema is vroege versie van saas_licenses.db (104 vs 309 schema-regels). Geen tweelingbestand in `/opt/backups/`. Eenmalig handmatig aangemaakt experiment. Gearchiveerd naar `/opt/backups/cleanup_20260522/db_archive/ic_licenses.db`.

### 2-C — Latente bug `gen_context.py:9` gefixt
Regel verwees naar `/opt/stresschecker/data/saas_licenses.db` (0-byte stub) i.p.v. `/opt/ic-license-server/data/saas_licenses.db` (productie). CONTEXT.md `## Databases`-sectie miste hierdoor het 22-tabel overzicht. Eén-regel-fix; gen_context.py-output nu compleet.

### 2-D — Orphan stubs + accidenten verwijderd
- 4 root-level 0-byte DB-stubs: `saas_licenses.db`, `sc_measurements.db`, `sc_pro.db`, `stresschecker.db`
- 3 `data/` 0-byte stubs: `saas_licenses.db`, `metingen.db`, `pro_clients.db`
- `/opt/stresschecker/{templates/` met 5 lege subdirs (bash-brace-expansion accident, 20-02-2026)
- `toegepast` (0-byte mystery file)
- `templates/oude_code_keuze.html` (0-byte placeholder, route gebruikt `legacy_choice.html`)

### 2-E — Archivering naar `/opt/backups/cleanup_20260522/`
153 files / 8.4 MB in 12 submappen:
- `root_app_varianten/` — 29 files (app.py.bak*/.current/.merge_backup), 4.2 MB
- `templates_subtree/{root,pro,hlm}/` — 74 files (60+11+3), 3.0 MB
- `templates_backups/` — 2 dirs (templates_backup_20260224_1406/_1407/), 28 .html, 300 KB
- `data_db_backups/` — 3 DB-snapshots, 612 KB
- `gen_context_varianten/` — 6 files, 48 KB
- `env_context_backups/` — 3 files (.env.bak_sendgrid + 2 CONTEXT.md.bak*), 40 KB
- `static_js/` — 4 hrv.js.bak*, 36 KB
- `db_archive/` — ic_licenses.db, 124 KB
- `docs/` — trend_hint_varianten_review.md, 20 KB
- `hlm_routes/` — routes.py.bak, 20 KB
- `tests_bak/` — 2 files, 20 KB
- `seed_varianten/` — seed_anna.py.v1, 12 KB

Buiten oorspronkelijke Fase 1-scope (alleen root): de 74 templates-baks, 4 hrv.js.bak, hlm/routes.py.bak, 2 tests-bak items. Recursieve find vóór 2-E uitvoering bracht ze aan het licht; met expliciet akkoord toegevoegd aan herzien plan.

### 2-F — `.gitignore` uitgebreid
Nieuwe regels: `/*.db`, `/*.current`, `/*.merge_backup`, `/*.v1`, `/*.pre-leerpunt`, `/templates_backup_*/`, `*.backup`, `*.backup-*`, `toegepast`. Overlap-vrij geverifieerd met `git check-ignore`.

### Verificatie
- File-count root: 76 → 33 entries (`ls -la`); 68 → 26 non-hidden
- `git ls-files | grep -E '\.(db|bak|backup)$'` → leeg
- `git clone /opt/stresschecker /tmp/test-clone` → 0 rommel-hits, clone bevat slechts 7 entries
- Smoke test `/licentie` → HTTP 200
- Productie-DB `/opt/ic-license-server/data/saas_licenses.db` onaangeroerd: **mtime `2026-05-21 19:28:15.812239508` identiek aan baseline begin Fase 2**; rowcounts licenses=35, users=14, subscriptions=11, plans=18 ongewijzigd

Twee backup-snapshots vandaag: `/opt/backups/*.20260522-0741` (pre-Fase-2) en `*.20260522-0803` (pre-2-E mv).

### Correctie op CLEANUP_TODO.md
De waarschuwing "CRITICAL: bevat klantdata + license-keys" bij root-level saas_licenses.db was feitelijk onjuist — het bestand was 0 bytes. De echte productie-DB woont in `/opt/ic-license-server/data/` en zat niet in deze repo. CLEANUP_TODO.md bijgewerkt.

### Leerpunt voor toekomstige cleanup-sessies
Begin een cleanup altijd met een recursieve scan van de hele tree, niet alleen root-niveau. Fase 1 van deze sessie scande alleen `/opt/stresschecker/` root, wat een gefragmenteerd plan opleverde dat tijdens uitvoering 2× herzien moest worden (74 templates-baks + .gitignore-aanpassingen). Eén grondige recursieve find vooraf scheelt twee tussen-revisies achteraf.

## 2026-05-21

- Nieuw plan-type `sc-{pro-m,pro-s,consumer}-eval` — 90-dagen evaluatielicenties voor partner-outreach (eerste case: Mühlberger DGBfb, later KKH/Barmer pilots). UI-label "Evaluatielicentie/Evaluierungslizenz/Evaluation license" via uitbreiding `PRO_PERIOD_LABELS`. Geen Stripe-koppeling. Data-behoud bij upgrade naar regulier abonnement via e-mail-hash (bestaand model). `origin='evaluation'` als 5e taxonomie-waarde. Marketing-branch in /activate verbreed naar `IN ('marketing','evaluation')` met plan-driven expiry-helper `_compute_license_expires_at()` (vervangt hardcoded 365d). Activation-log gebruikt nu `activate_{origin}` voor cohort-tracking. Generator `/opt/ic-license-server/generate_eval_license.py` (niet in git, naast saas_licenses.db). Centrale constante `EVAL_DURATION_DAYS=90` in `eval_config.py` — single source of truth voor zowel app.py als generator.
- Latente issue gefixt (mede gemerkt tijdens eval-werk): `licenses.expires_at` en `licenses.valid_until` werden inconsistent gevuld door marketing-branch (alleen `expires_at`). Nu beide gesynchroniseerd om validator-pad (dat `valid_until` leest) gelijk te houden met activatieflow (dat `expires_at` schreef).
- Follow-up: consumer-eval UI op /instellingen out-of-scope MVP — `get_pro_tier_summary` blijft `type='pro' AND product='sc'`-gated; consumer-eval-licenties krijgen wel correcte DB-state en activatie maar geen widget. Pas adresseren als concrete consumer-eval-recipiënt zich aandient.
- TEST_ACCOUNTS.md aangemaakt — beleid + actieve test-fixtures (paulpannevis+mueh-test + paulpannevis+evaltest). NIET-opruimen-regel vastgelegd; geen staging-omgeving dus deze accounts zijn de enige levende referentie voor regressie-checks. Wegwerp-eval-licentie SC-PRO-F4751519 ge-tagged als INTERNAL TEST FIXTURE in licenses.notes.
- Eerste Mühlberger-codes uitgegeven: SC-PRO-D3AA13C6 (sc-pro-m-eval, Pro 30 clients) + SC-CON-A212404F (sc-consumer-eval, persoonlijk). code_expires_at=2026-08-19 activatie-deadline.
- /instellingen UX-fix — Pro-abonnement label nu taal-consistent (Jaarabonnement/Jahresabonnement/Annual subscription via plan-code mapping i.p.v. Stripe product.name). Licentiecode-label expliciet gemaakt met helptekst voor activatie op nieuw apparaat. NL/DE/EN visueel geverifieerd.
- Pro-tier widget op /pro + /instellingen voor alle Pro-cohorts (was Stripe-only). Toont tier (Pro S/M/L), actieve koppelingen vs. max_clients en geldigheid; afgeleid uit licenses + plans, Stripe-onafhankelijk.
- git init + initial commit op /opt/stresschecker/ (lokale repo, geen remote).
- .gitignore aangemaakt (secrets, backups, databases, CONTEXT.md, .claude/).
- CHANGELOG.md + gen_context.py-integratie: CONTEXT.md krijgt voortaan automatisch een 'Recente wijzigingen'-sectie uit CHANGELOG.md.
- CLEANUP_TODO.md aangemaakt voor latere opruiming root-level artefacten (app.py.current, saas_licenses.db in root, etc.).
