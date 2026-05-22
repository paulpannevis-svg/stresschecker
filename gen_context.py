import sqlite3, os

out = []
out.append("# StressChecker Context Document\n")
out.append("Gegenereerd: " + __import__('datetime').datetime.now().strftime("%Y-%m-%d %H:%M") + "\n\n")

out.append("## Databases\n")
dbs = [
    '/opt/ic-license-server/data/saas_licenses.db',
    '/opt/stresschecker/data/sc_measurements.db',
    '/opt/stresschecker/data/sc_pro.db',
]
for db in dbs:
    if os.path.exists(db):
        out.append(f"### {db}\n```\n")
        con = sqlite3.connect(db)
        cur = con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        for (t,) in cur.fetchall():
            cur2 = con.cursor()
            cur2.execute(f"PRAGMA table_info({t})")
            cols = [r[1] for r in cur2.fetchall()]
            out.append(f"{t}: {', '.join(cols)}\n")
        con.close()
        out.append("```\n\n")

out.append("## Routes (app.py)\n```\n")
with open('/opt/stresschecker/app.py') as f:
    for line in f:
        if '@app.route' in line:
            out.append(line.strip() + "\n")
out.append("```\n\n")

out.append("## Templates\n```\n")
for root, dirs, files in os.walk('/opt/stresschecker/templates'):
    for f in sorted(files):
        path = os.path.join(root, f)
        rel = path.replace('/opt/stresschecker/templates/','')
        size = os.path.getsize(path)
        out.append(f"{rel} ({size} bytes)\n")
out.append("```\n\n")



_CHANGELOG_PATH = '/opt/stresschecker/CHANGELOG.md'
if os.path.exists(_CHANGELOG_PATH):
    out.append("## Recente wijzigingen\n")
    with open(_CHANGELOG_PATH) as _ch:
        # Skip top-level H1 (we already have one); preserve rest verbatim
        for _line in _ch:
            if _line.startswith('# '):
                continue
            out.append(_line)
    if not out[-1].endswith('\n'):
        out.append('\n')
    out.append('\n')

out.append("## Werkwijze & Leerpunten\n")
out.append("- Begin elke sessie met upload van CONTEXT.md\n")
out.append("- Backup altijd via: /opt/stresschecker/backup.sh\n")
out.append("- Bij templates: ALLEEN invoegen, nooit verwijderen+vervangen in een stap\n")
out.append("- Bij twijfel: herstel eerst backup, dan minimale ingreep\n")
out.append("- kenniscentrum.html: blokken invoegen direct NA de id=kc-sectie opening\n")
out.append("- 21-04-2026: last_client_id session-fallback volledig verwijderd (recidive van 12-04 fix). Les: bij modus-afhankelijke session-state (cliëntmeting vs. eigen meting) altijd WRITE én alle READs identificeren — een fix die alleen één READ opruimt laat de bug via andere READs terugkeren.\n")
out.append("- 21-04-2026: regressietest-suite in /opt/stresschecker/tests/. Draai run_all.sh na elke fix en aan einde van elke werksessie om data-routing en kernberekeningen te verifiëren. Dekking: consumer-, Pro-cliënt- en Pro-eigen-meting routing (incl. A4 regressie-test voor 21-04 session-state bug); RMSSD/HRV%/RI Verveen-lookup; RI-zone grenswaarden.\n")
out.append("- 22-04-2026: UI-patroon voor inklapbare informatie-blokken (`<details class='edu-block'>`): naast het pijltje hoort een tekstcue in accent-kleur ('meer lezen' ↔ 'inklappen'; 3-taal NL/DE/EN). Pijl 1.4× groter (~1.12rem), accent-kleur i.p.v. grijs, hele summary-regel cursor:pointer + hover. Voor settings-panels variant met 'instellingen tonen ↔ verbergen'. Voor FAQ-accordions (veel items): alleen pijl-vergroting + intro-instructieregel bovenaan de sectie; géén per-item tekstcue (visuele clutter). Achtergrond: users overlezen structureel kleine ▾-pijltjes bij dichtgeklapte blokken.\n\n")

out.append("## Bekende beperkingen\n")
out.append("- Kubios-export op Bluefy (iPad en iPhone): toont inline in plaats van te downloaden, "
           "ondanks text/plain + Content-Disposition: attachment + as_attachment=True. "
           "Werkt wel correct in Safari (iPad/iPhone), Chrome/Edge desktop, Safari macOS. "
           "Bluefy-specifieke quirk met Content-Disposition-handling. "
           "Pro-gebruikers doen exports toch eerder vanuit hun werkomgeving "
           "(laptop/desktop/iPad-Safari), dus impact is minimaal. Geen fix gepland.\n\n")

out.append("## Follow-ups\n")
out.append("- 12-05-2026: /oude-code-keuze flow (app.py, zoek `SELECT type FROM licenses ... status='activated'`): "
           "leest license-state direct, niet via `validate_license`. Bij volgende refactor ook joinen op "
           "subscriptions zodat dezelfde grace-period-semantiek geldt als in de validator (optie-B-uitbreiding).\n")
out.append("- 12-05-2026: 2FA-codes verschijnen plaintext in journalctl-output van stresschecker.service "
           "(bv. `2FA CODE: 767975`). Productie-security-issue: log-redactie of verwijderen van de print-statement nodig.\n")
out.append("- 12-05-2026: `SETTINGS SESSION: birth_year=None gender=None sensor=None` (gezien 11-05-2026 11:09 in journalctl): "
           "mogelijk edge case waar gebruiker instellingen opslaat zonder waarden ingevuld. Onderzoeken of dit pad "
           "een UI-validatie of server-side default mist.\n")
out.append("- 12-05-2026: 12 scenario-tests uit het optie-B-implementatieplan (3 paden × 2 endpoints × deltavarianten) "
           "zijn vandaag als micro-tests gedraaid en groen bevonden, maar nog niet als geautomatiseerde test-suite "
           "toegevoegd aan /opt/stresschecker/tests/. Bij volgende optie-B-uitbreiding (Apple-IAP of andere provider) "
           "is geautomatiseerde dekking aan te raden zodat regressie op de JOIN-logica vroeg gevangen wordt.\n")
out.append("- 12-05-2026: /wachtwoord-vergeten heeft een timing-side-channel voor email-enumeration: SendGrid-call "
           "duurt ~200-500ms en wordt alleen uitgevoerd voor bestaande accounts. Een aanvaller met fijne "
           "response-timing-meting kan 'bekend account' (langzaam pad mét send) onderscheiden van 'onbekend of "
           "rate-limited' (snel pad zonder send). Mitigatie zou een uniforme delay of async send-queue vereisen. "
           "Acceptabel voor huidige user-base (~10 accounts); herzien bij misbruik-signalen.\n\n")

out.append("## Spoor 3 — Stripe Customer Portal\n")
out.append("- 16-05-2026: ingelogde Stripe-Pro-klanten kunnen via knop 'Abonnement beheren' "
           "op /licentie een dynamische Stripe Customer Portal sessie openen "
           "(opzeggen, betaalmethode wijzigen, facturen downloaden). PayPal/manual klanten "
           "zien de knop niet; bij directe URL-toegang krijgen zij een flash + redirect met "
           "verwijzing naar info@lifestylemonitors.{com|de}.\n")
out.append("- Route: GET /account/manage-subscription → endpoint `manage_subscription`. "
           "Auth check (redirect naar /login bij missende user_key); customer_id-lookup; "
           "billing_portal.Session.create met configuration `bpc_1TVpFcHD28PM4o1K18URnQAI`, "
           "locale uit session['lang'], return_url absoluut naar /licentie. StripeError → "
           "redirect /licentie?error=portal_unavailable.\n")
out.append("- /licentie route: helper `has_stripe_subscription(user_key)` aan template-context "
           "toegevoegd. license.html toont knop conditioneel onder de activatie-card (NL "
           "'Abonnement beheren', DE 'Abonnement verwalten', EN 'Manage subscription'). "
           "Error-codes via SPOOR3_ERROR_MESSAGES (`no_stripe_subscription`, "
           "`portal_unavailable`) — DE/NL/EN; backwards compatibel met letterlijke "
           "error-strings via dict.get(code, code).\n")
out.append("- Datamodel-wijzigingen: GEEN. Kolom `subscriptions.stripe_customer_id` "
           "+ index `idx_subs_stripe_customer` waren al aanwezig; webhook-handlers "
           "`_handle_subscription_created` (3c-4) en `_handle_subscription_updated` (3c-6) "
           "in /opt/ic-license-server/server.py persisten customer_id reeds via UPSERT "
           "+ COALESCE. Geen ALTER TABLE, geen webhook-patch.\n")
out.append("- Helpers (app.py, vlak na `opzeg_abonnement`): "
           "`_load_stripe_secret()` leest STRIPE_SECRET_LIVE in-process uit "
           "/opt/ic-license-server/data/stripe_keys.conf (geen argv/env/history). "
           "`get_stripe_customer_id(user_key, email=None)` DB-first via JOIN "
           "licenses.stripe_subscription_id ↔ subscriptions.subscription_id, "
           "Stripe Customer.search fallback op email. "
           "`has_stripe_subscription(user_key)` DB-only wrapper voor template-gate "
           "(geen API-call per page-render).\n")
out.append("- Tests: /opt/stresschecker/tests/test_spoor3_portal.py — 7 mocked assertions "
           "(C1 unauth-redirect, C2 no-customer-flash, C3 portal-redirect, C4 StripeError, "
           "C5 locale-doorgegeven, C6/C7 button visibility). Geïntegreerd als categorie C "
           "in tests/run_all.sh; volledige suite groen 17/17 op 16-05-2026 (~4s).\n")
out.append("- Open punten Spoor 3:\n"
           "  • Handmatige backfill `users.stripe_customer_id` voor testaccount "
           "paulpannevis@lifestylemonitors.com (license SC-PRO-20503ED0 origin='manual'). "
           "Eenmalig via `stripe.Customer.search(query='email:\"…\"')` koppelen aan "
           "subscriptions-rij — alleen nodig als dit testaccount via de portal moet "
           "kunnen beheren; anders niet noodzakelijk.\n"
           "  • 0 webshop-rijen met user_key+stripe_customer_id koppelvolledig op datum-X "
           "(alle webshop-aankopen niet geactiveerd door eindklant; `licenses.user_key` "
           "wordt pas bij /activeer gevuld). End-to-end smoke tegen prod-data pas mogelijk "
           "na eerste geactiveerde Stripe-klant of na handmatige backfill.\n"
           "  • Service-restart vereist na deploy: gunicorn template-cache en route-tabel "
           "moeten opnieuw geladen worden via `kill -HUP <master-pid>` of "
           "`systemctl restart stresschecker`. Was bij implementatie nog niet uitgevoerd "
           "(wachtte op expliciete operator-akkoord).\n\n")

with open('/opt/stresschecker/CONTEXT.md', 'w') as f:
    f.write(''.join(out))
print("CONTEXT.md aangemaakt")
