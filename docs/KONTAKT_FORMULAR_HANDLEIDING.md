# Handleiding — Kontaktformular met Fluent Forms

**Site:** lifestylemonitors.de (WordPress) · **Tijd:** ±30–40 min · **Volgorde aanhouden** (stap 5 maakt de Danke-pagina die je in stap 7 nodig hebt)

## Veld-voor-veld mapping (huidig mailto-formulier → Fluent Forms)

| Huidig veld | Fluent Forms element | Label (DE) | Verplicht |
|---|---|---|---|
| Vorname | Simple Text | `Vorname` | Ja |
| Nachname | Simple Text | `Nachname` | Ja |
| Email | **Email** (apart element, voor validatie + Reply-To) | `E-Mail` | Ja |
| Telefonnummer | Simple Text | `Telefonnummer (optional)` | **Nee** |
| Nachricht | Text Area | `Nachricht` | Ja |

> Gebruik voor E-Mail bewust het aparte **Email**-element (niet Simple Text). Dat hebben we in stap 6 nodig om de Reply-To automatisch in te vullen.

---

## 1. Fluent Forms installeren & activeren

1. Log in op `https://lifestylemonitors.de/wp-admin`.
2. Klik in het linkermenu op **Plugins → Installieren** (Add New).
3. Typ rechtsboven in het zoekveld: **`Fluent Forms`**.
   - *Je ziet nu* een kaartje **"Contact Form Plugin – Fluent Forms"** van *WPManageNinja*. (Logo: blauw/wit.)
4. Klik **Jetzt installieren** (Install Now) → wacht → de knop wordt **Aktivieren** (Activate) → klik die.
   - *Je ziet nu* een nieuw menu-item **Fluent Forms** in het linkermenu (meestal met een blauw vinkje-icoon).

---

## 2. Het formulier bouwen

1. Klik linksmenu **Fluent Forms → Neues Formular** (New Form).
   - *Je ziet nu* een keuze tussen sjablonen. Kies **"Leeres Formular erstellen"** / **"Create a Blank Form"** (geen kant-en-klaar sjabloon).
2. Geef het formulier bovenaan een naam: typ **`Kontaktformular`** → bevestig.
   - *Je ziet nu* de **form-editor**: links een leeg canvas, rechts een paneel met velden onder o.a. **"Allgemeine Felder"** (General Fields) en **"Eingabefelder"** (Input Fields).

Nu sleep je 5 velden naar het canvas (van boven naar beneden):

**Veld 1 — Vorname**
3. Sleep **"Simple Text"** (Einzeiliger Text) naar het canvas.
4. Klik op het zojuist geplaatste veld → rechts opent **"Eingabe-Anpassung"** (Input Customization).
5. Bij **Label** typ je: `Vorname`. Zet **"Erforderlich"** (Required) op **AAN** (schuifje blauw).

**Veld 2 — Nachname**
6. Sleep nog een **"Simple Text"** eronder. Label: `Nachname`. **Required: AAN**.

**Veld 3 — E-Mail**
7. Sleep het element **"E-Mail"** (Email) eronder. Label: `E-Mail`. **Required: AAN**.

**Veld 4 — Telefonnummer (optioneel)**
8. Sleep nog een **"Simple Text"** eronder. Label: `Telefonnummer (optional)`. Laat **Required UIT** (schuifje grijs).

**Veld 5 — Nachricht**
9. Sleep **"Text Area"** (Mehrzeiliger Text) onderaan. Label: `Nachricht`. **Required: AAN**.

10. (Optioneel) Klik op de blauwe verzendknop onderaan het formulier → label rechts wijzigen naar **`Schicken`**.
11. Klik rechtsboven op **Speichern** (Save).
    - *Je ziet nu* een bevestiging "Formular erfolgreich gespeichert" / "successfully saved".

---

## 3. Spam-bescherming: honeypot

Honeypot is in Fluent Forms een **globale** instelling (geldt voor alle formulieren) en staat meestal standaard aan — even controleren:

1. Linkermenu **Fluent Forms → Globale Einstellungen** (Global Settings).
2. Open de sectie **"Allgemeine Einstellungen"** (General Settings).
3. Zoek **"Honeypot Security"** → zet het schuifje op **AAN** als dat nog niet zo is.
4. Klik **Einstellungen speichern** (Save Settings).
   - *Je ziet nu* "Settings saved". (Geen captcha nodig — honeypot is onzichtbaar voor bezoekers en blokkeert bots.)

---

## 4. (overslaan — SMTP)

SMTP regelt Hostnet voor lokale mail; hier is niets in te stellen. Door naar de e-mailinhoud.

---

## 5. Bedankpagina maken

1. Linkermenu **Seiten → Erstellen** (Pages → Add New).
2. **Titel** (bovenaan): `Danke`
3. Klik in het tekstvak eronder en typ de inhoud:
   - Koptekst (kies blokstijl "Überschrift" / Heading H1): **`Danke für Ihre Nachricht`**
   - Daaronder een gewone alinea: **`Wir antworten innerhalb von 24 Stunden.`**
4. Klik rechtsboven **Veröffentlichen** (Publish) → nogmaals **Veröffentlichen** bevestigen.
5. **Onthoud de URL.** Hij wordt iets als `https://lifestylemonitors.de/danke`. Klik op **"Seite ansehen"** (View Page) en kopieer de URL uit de adresbalk — die heb je in stap 7 nodig.

---

## 6. E-mail-instellingen (notificatie naar jou)

1. Ga terug naar je formulier: **Fluent Forms → Alle Formulare** → klik **`Kontaktformular`**.
2. Klik bovenin op het tabblad **"Einstellungen & Integrationen"** (Settings & Integrations).
3. Klik links op **"E-Mail-Benachrichtigungen"** (Email Notifications).
   - *Je ziet nu* een bestaande regel **"Admin Notification Email"** → klik erop om te bewerken (of klik **"Benachrichtigung hinzufügen"** als er nog niets staat).
4. Vul in:

| Veld | Waarde |
|---|---|
| **Name der Benachrichtigung** (intern) | `Kontaktanfrage` |
| **Senden an / Send To** | `info@lifestylemonitors.de` |
| **Betreff / Subject** | `Kontaktanfrage über lifestylemonitors.de` |
| **Von Name / From Name** | `Lifestyle Monitors Website` |
| **Von E-Mail / From Email** | `noreply@lifestylemonitors.de` |
| **Antwort an / Reply To** | *het E-Mail-veld van de bezoeker — zie hieronder* |

5. **Reply-To automatisch koppelen:** klik in het veld **"Antwort an / Reply To"**. Rechts ervan staat een klein **`{ }`**-knopje (shortcode-kiezer). Klik dat → kies in de lijst je veld **"E-Mail"**.
   - *Je ziet nu* een code zoals `{inputs.email}` in het veld verschijnen. Dat is goed — zo gaat je *Antwoorden* rechtstreeks naar de bezoeker.

6. **E-mail-body (Duits).** In het grote tekstvak **"E-Mail-Text" / "Email Body"** plak je onderstaande tekst. Voor elke veldwaarde gebruik je weer het **`{ }`**-knopje boven het tekstvak en kies je het juiste veld (typ de codes dus niet zelf — kies ze uit de lijst):

```
Neue Kontaktanfrage über lifestylemonitors.de

Vorname:        {kies: Vorname}
Nachname:       {kies: Nachname}
E-Mail:         {kies: E-Mail}
Telefonnummer:  {kies: Telefonnummer}
Nachricht:
{kies: Nachricht}

—
Diese Nachricht wurde über das Kontaktformular auf lifestylemonitors.de gesendet.
```

   Na het invullen ziet de regel er bijvoorbeeld zo uit: `Vorname: {inputs.vorname}`. De `{...}`-codes worden bij verzending vervangen door wat de bezoeker invulde.

7. Klik **Speichern** (Save).

---

## 7. Redirect-na-verzenden instellen

1. Nog steeds in **"Einstellungen & Integrationen"** → klik links op **"Bestätigungseinstellungen"** / **"Form Confirmation"** (Confirmation Settings).
2. Bij **"Bestätigungstyp" / "Confirmation Type"** (of *"Nach dem Absenden"* / *After form submission*) kies je: **"Zu einer Seite weiterleiten"** / **"Redirect To a Page"**.
   - *Je ziet nu* een keuzelijst met je WordPress-pagina's verschijnen.
3. Selecteer de pagina **`Danke`** (uit stap 5). *(Staat er alleen een "Custom URL"-veld? Plak dan de URL uit stap 5, bijv. `https://lifestylemonitors.de/danke`.)*
4. Klik **Speichern** (Save).

---

## 8. De mailto-knop op /kontakt vervangen

Eerst de shortcode ophalen:
1. **Fluent Forms → Alle Formulare**. Naast **`Kontaktformular`** staat een **Shortcode**, bijv. `[fluentform id="1"]`. Klik erop om te kopiëren (of noteer het `id`-nummer).

Dan de Kontakt-pagina aanpassen:
2. **Seiten → Alle Seiten** → open **`Kontakt`** → **Bearbeiten** (Edit).
3. **Verwijder het oude formulier + de "Schicken"-mailto-knop:**
   - Klik op het oude formulierblok/knop → klik het **⋮ / drie-puntjes**-menu → **"Block entfernen"** (Remove block). Doe dit voor alle oude veld- en knop-onderdelen.
4. **Voeg het nieuwe formulier toe:**
   - Klik op de **`+`** (blok toevoegen) op de plek waar het formulier moet komen → zoek **"Shortcode"** → kies het **Shortcode-blok**.
   - Plak: `[fluentform id="1"]` (gebruik jouw eigen id-nummer).
   - *Werkt de pagina met Elementor i.p.v. de standaard blok-editor?* Sleep dan het **"Shortcode"-widget** op de plek en plak dezelfde code.
5. Klik rechtsboven **Aktualisieren** (Update).
6. Open `https://lifestylemonitors.de/kontakt` in een nieuw tabblad → *je ziet nu* het nieuwe formulier met velden Vorname, Nachname, E-Mail, Telefonnummer (optional), Nachricht en een **Schicken**-knop — **geen** mailto-popup meer.

---

## 9. End-to-end test-checklist

Doe één echte testverzending en vink af:

- [ ] **Formulier toont 5 velden** in juiste volgorde, met de Duitse labels.
- [ ] **Telefonnummer is optioneel** — laat het leeg en verzend: geen foutmelding.
- [ ] **Verplichte velden werken** — laat Nachricht leeg: je krijgt een rode melding, verzenden lukt niet.
- [ ] **E-Mail-validatie** — vul iets ongeldigs in zoals `abc` → foutmelding "ungültige E-Mail".
- [ ] **Verzenden lukt** met geldige gegevens → je wordt doorgestuurd naar **/danke** met de tekst *"Danke für Ihre Nachricht — wir antworten innerhalb von 24 Stunden."*
- [ ] **Mail komt aan** op `info@lifestylemonitors.de` (en, via je forward, op `paulpannevis@lifestylemonitors.com`).
- [ ] **Onderwerp** = `Kontaktanfrage über lifestylemonitors.de`.
- [ ] **Body** bevat alle ingevulde waarden (vooral Nachricht volledig).
- [ ] **Reply-To klopt** — open de ontvangen mail, klik *Antwoorden*: het adres springt op het **e-mailadres dat je in de test invulde**, niet op noreply.
- [ ] **From** = `noreply@lifestylemonitors.de`.
- [ ] **Inzendingen bewaard** — check **Fluent Forms → Einträge** (Entries): je testinzending staat erin (back-up als een mail ooit niet aankomt).

---

**Klein puntje om op te letten bij de test:** controleer of de mail niet in **Spam/ongewenst** belandt (eerste keer kan dat met een nieuw `noreply@`-afzender). Als dat zo is, markeer 'm als "geen spam" en/of laat me weten — dan kijken we of een SPF/DKIM-check op het `.de`-domein bij Hostnet nodig is.
