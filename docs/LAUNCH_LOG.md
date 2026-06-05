# StressChecker / Lifestyle Monitors — Launch Log

Bijgehouden vanaf: 30-04-2026
Laatst bijgewerkt: 30-04-2026
Onderhouden door: Paul Pannevis (samen met Claude)

Doel: één plek voor strategische beslissingen, open issues, en context die niet in code/DB staat. Aanvulling op `/opt/stresschecker/CONTEXT.md` (auto-gegenereerd via gen_context.py).


================================================================
SECTIE A — OPEN BESLISSINGEN
================================================================

[OPEN-001] Recurring billing-platform na launch
Status: te beslissen tussen 5-15 mei (na launch-rust)
Achtergrond: PayPal Subscriptions Hermes-flow blokkeert (zie ISSUE-001).
WP Swings + Stripe Gateway heeft één "Pending" test-abonnement (#4285,
StressChecker Pro Monatsabonnement €8,25 via Kredit-/Debitkarte op
paulpannevis@lifestylemonitors.com) maar geen bewezen end-to-end recurring.

Opties:
  1. WooPayments (Automattic Stripe-laag) — Claude voorkeur
     + Eén partij, native WC-integratie
     + Recurring ingebouwd, geen extra plugin nodig
     + Native SEPA-incasso (belangrijk voor DE-markt)
     - ~2,9% + €0,30 per transactie (iets hoger dan Stripe direct)
  2. WP Swings + Stripe Gateway (gratis, huidig ingericht)
     + €0/maand, alleen Stripe-fees
     - Gratis versie heeft beperkingen, ondersteuning mager
     - Eén pending test bleef hangen, end-to-end ongetest
  3. WooCommerce Subscriptions (officieel Automattic, €199/jr)
     + Industrie-standaard, beste documentatie
     - €199/jaar voor features mogelijk niet meteen nodig
  4. Stripe Billing direct (zonder WP-plugin)
     + Meest robuust, klant-portal van Stripe is uitstekend
     - Maatwerk-koppeling via Flask webhooks nodig
     - Klant koopt buiten WC-shop om

Beslismoment: na mei 1 launch, geen tijdsdruk.
Volgende stap: één optie kiezen → één weekend grondige test → live.


================================================================
SECTIE B — OPEN ISSUES BIJ DERDEN
================================================================

[ISSUE-001] PayPal Subscriptions checkout faalt (Hermes-flow)
Datum geopend: 30-04-2026
Kanaal: PayPal Business chat → ticket bij integratieafdeling
Eerste-lijns medewerker: Klaasjan
Verwacht antwoord: uiterlijk 3-5-2026 (72 uur)
Status: wachtend op PayPal

Bevinding:
- createSubscription succesvol → Subscription ID gegenereerd in PayPal
- Hermes-checkout-popup laadt → toont "Onze excuses, niet alles werkt
  naar behoren op het moment"
- Geen klant-login mogelijk, flow breekt af vóór betaling
- Reproduceerbaar met 2 verschillende Plan-IDs, in verse browser-sessie
- Reproduceerbaar op desktop én mobiel

Bewijs / ticket-data:
- Failed Subscription IDs: I-FC6NDJDTXRMS, I-5S3XLHVU8DHB
- Order IDs bij cancel: 06D70349VF084922L, 30V61059HH954331K
- Tijdstippen: 30-04-2026, 08:53 en 10:43 CEST
- App: Lifestyle Monitors (Live)
- Live Client-ID:
  AbU7cYCxE_q43Sup6Q3nQso2N81tbbtUne8y9rjiqQfF7k8qNjojeMHw2SWphYDQiSJHsRW6G4l7Ekae
- Domein: app.stresschecker.com
- Plan-IDs getest: P-64B76075EV0502904NHY7ZSY (oud, nu gedeactiveerd)
  en P-35C94676VY535342ANHZRFNI (nieuw, actief)

Configuratie geverifieerd correct (geen mismatch):
- Subscriptions feature aangevinkt in app
- Save payment methods (Vault) aangevinkt
- Payment links and buttons aangevinkt
- Live Client-ID hoort bij dezelfde account als Live Plan-IDs

Vermoedelijke oorzaken (niet bevestigd, PayPal moet diagnose stellen):
- Account-eligibility issue voor recurring billing
- Mogelijk anti-fraud / self-purchase block
- Mogelijk extra verificatie nodig voor NL business + recurring

Test-bestand staat klaar voor herhaling als PayPal antwoordt:
/opt/stresschecker/static/paypal_test.html


================================================================
SECTIE C — GENOMEN BESLISSINGEN
================================================================

[2026-04-30] Mei 1 launch-strategie
Voor mei 1 alleen jaarabonnementen via WooCommerce eenmalige PayPal
Checkout (geen Subscriptions). Manuele licentie via SQL-template,
email-reminder na 12 maanden voor verlenging.
Reden: PayPal Subscriptions blokkeert (ISSUE-001), recurring-flow
ongetest, geen tijd voor risico's vóór launch.

[2026-04-30] 8 PayPal Plans aangemaakt en database gesynchroniseerd
Ondanks Hermes-fout staan plans klaar voor eventuele latere reactivering.
Drie oude plans gedeactiveerd (rommelige product-namen), structuur opgeruimd.

Plan-IDs (saas_licenses.db, plans-tabel):
  sc          monthly  P-35C94676VY535342ANHZRFNI  €6,95
  sc          yearly   P-56Y69361M1245315SNHZQQJA  €69,00
  sc-pro-s    monthly  P-5MM45397BR7978332NHZQTDY  €9,95
  sc-pro-s    yearly   P-0U6284555F377331UNHZQVIA  €99,00
  sc-pro-m    monthly  P-22483577VE530272UNHZQWTI  €19,95
  sc-pro-m    yearly   P-53G37968PN296663TNHZQX6Q  €199,00
  sc-pro-l    monthly  P-65E1478504890982HNHZQZJY  €29,95
  sc-pro-l    yearly   P-02Y331255M350421MNHZRDEQ  €299,00

PayPal-producten (4 stuks): StressChecker, StressChecker Pro S,
StressChecker Pro M, StressChecker Pro L.
Database backup vóór update:
  /opt/ic-license-server/data/saas_licenses.db.backup-20260430-1037

[2026-04-30] SQL-template voor manuele klant-aanmaak
Bestand: /opt/ic-license-server/new_customer.sql.template
Werkproces: cp template → /tmp/klant_<naam>.sql → sed-replace placeholders
→ sqlite3 ... < bestand → verifieer → ruim /tmp op.
Werkproces getest met fictieve "Hans Mueller", testdata opgeruimd.

Placeholders: :EMAIL :NAAM :LANG :PLAN_ID :TYPE :PAYPAL_SUB
              :LICENSE_KEY :ORIGIN :EXPIRES

[2026-04-30] Welkomstmail-templates DE
/opt/stresschecker/email_templates/welcome_de_abo.txt
/opt/stresschecker/email_templates/welcome_de_komplett.txt
Toon: Sie-vorm + "Hallo {VOORNAAM}". Afzender: "Ihr Lifestyle Monitors Team".
Umlauten als ae/oe/ue/ss in opslag (copy-paste-veilig) — bij verzending
in Gmail handmatig terugzetten of via autocorrect.

[2026-04-30] Vocabulaire-afspraak
Naar klant: "abonnement" / "Abonnement" / "subscription" (alle talen).
Naar klant in DE: Sie-vorm, niet Du-vorm.
Intern (code, DB): "license" mag, technische naam.
App-teksten "Lizenzcode" / "licentiecode" blijven voor mei 1 zoals ze zijn
— opruimen ná launch in een rustige sessie (287 hits in app.py + templates,
veel zal in technische context zitten en moet ongemoeid blijven).

[2026-04-30] SC Komplett-flow vastgesteld
Aankoop: €99 eenmalig in WooCommerce (.de) — Bluetooth-sensor +
12 mnd SC software inbegrepen. Verzending hardware uit Oosterhout.
Maand 11 (dag 335): cron-job stuurt email-reminder met verleng-link
naar StressChecker Jaarlijks (€69/jr).
Klant moet zelfde e-mailadres gebruiken bij verlenging — meetdata blijft
gekoppeld via users.email match (user_id ongewijzigd).
Welkomstmail vermeldt deze e-mail-continuïteit expliciet.

[2026-04-30] WooCommerce .de — productenstructuur voor mei 1
Aan te maken / aan te passen:
  - StressChecker Jahresabonnement       €69,00  virtueel  (was €69,95)
  - StressChecker Pro S Jahresabonnement €99,00  virtueel  (was €89,95)
  - StressChecker Pro M Jahresabonnement €199,00 virtueel  (nieuw)
  - StressChecker Pro L Jahresabonnement €299,00 virtueel  (nieuw)
  - StressChecker Komplett               €99,00  fysiek    (nieuw)
Geen "Abonnement"-checkbox aanvinken (= eenmalige aankoop voor mei 1).
HLM-producten: Privé blijven, niet voor mei 1 launch.
Hardware (USB/Bluetooth/Finger-Hülle): al gepubliceerd, ongewijzigd.

[2026-04-30] BTW-instellingen WooCommerce .de geverifieerd
Prijzen invoeren incl. BTW: aan.
Per land juiste BTW automatisch (DE 19%, BE 21%, NL 21%, etc.).
OSS One Stop Shop voor EU-grensoverschrijdende verkoop ingericht.
Productbeschrijving-tekst: "Alle Preise inkl. gesetzlicher MwSt. — der
genaue Steuersatz richtet sich nach dem Lieferland." (niet land-specifiek).


================================================================
SECTIE D — KORTE-TERMIJN OPENSTAANDE TAKEN (vóór mei 1)
================================================================

[ ] StressChecker product .de afronden:
    - Abonnement-checkbox uitvinken
    - Korte productbeschrijving vervangen (tekst klaar)
    - Lange productbeschrijving plakken (HTML klaar)
    - Producttype "Eenvoudig product", Virtueel aangevinkt
    - Reguliere prijs 69,00
    - Status Privé blijven (publiceren op 1 mei)
    - Update klikken

[ ] StressChecker Pro S product .de aanpassen:
    - Hernoemen naar "StressChecker Pro S Jahresabonnement"
    - Prijs €99,00
    - Productbeschrijving aanpassen voor Pro S-context

[ ] StressChecker Pro M Jahresabonnement aanmaken (€199,00, virtueel)
[ ] StressChecker Pro L Jahresabonnement aanmaken (€299,00, virtueel)
[ ] StressChecker Komplett product aanmaken (€99,00, fysiek, verzending)

[ ] Landing pages .de in Elementor aanpassen voor mei 1 launch

[ ] Op 1 mei: status alle 5 launch-producten van Privé naar Gepubliceerd

[ ] backup.sh checken: staat LAUNCH_LOG.md in de backup-paden?
    Zo niet, regel toevoegen.


================================================================
SECTIE E — NA-LAUNCH AGENDA (mei/juni)
================================================================

Week 1 mei (1-7):
  - Eerste klanten manueel verwerken via SQL-template + welkomstmail
  - Monitoring: gaan aankopen goed? komen welkomstmails aan?
  - Eventueel reageren op PayPal-ticket (ISSUE-001)
  - Cleanup: het Pending test-abonnement #4285 verwijderen

Week 2-3 mei (8-15):
  - Beslissing OPEN-001: recurring billing-platform kiezen
  - Eén product converteren als test (jaarabonnement)
  - Echte test met eigen creditcard, één-maand-cyclus afwachten

Week 3-4 mei (15-31):
  - Klant-portal-pagina bouwen (afhankelijk van platform-keuze)
    Shortcode beschikbaar als WP Swings: [wps-subscription-dashboard]
  - Webhook-koppeling naar Flask voor automatische licentie-aanmaak
  - Welkomstmail-automatisering via SendGrid (SendGrid + 2FA-flow staat al)

Juni:
  - Pro S/M/L recurring uitrollen als jaarabonnement consumer werkt
  - SC Komplett dag-335-reminder cron-job activeren
  - App-teksten Lizenzcode → Abonnementscode (alleen klant-zichtbare hits)
  - Resterende customer base verification DE (342 klanten)


================================================================
WERKWIJZE VOOR ONDERHOUD
================================================================

Bij elke nieuwe Claude-sessie eerst uploaden:
  /opt/stresschecker/CONTEXT.md       (auto-gegenereerd door gen_context.py)
  /opt/stresschecker/LAUNCH_LOG.md    (dit bestand)
Daarna is Claude direct up-to-date — geen herhaling van context nodig.

Tijdens sessie: bij beslissing of nieuw issue, regel toevoegen aan dit
bestand met datum [YYYY-MM-DD] + korte rationale. Reden van beslissing
meeschrijven, niet alleen de uitkomst — anders weet niemand later waarom
iets zo is gedaan.

Bestanden:
  /opt/stresschecker/CONTEXT.md          — architectuur (auto)
  /opt/stresschecker/LAUNCH_LOG.md       — strategie (handmatig)
  /opt/stresschecker/backup.sh           — backup-script
  /opt/stresschecker/gen_context.py      — context-generator
  /opt/stresschecker/email_templates/    — welkomstmails
  /opt/ic-license-server/new_customer.sql.template — manuele klantaanmaak
  /opt/ic-license-server/data/saas_licenses.db     — licentie-database
