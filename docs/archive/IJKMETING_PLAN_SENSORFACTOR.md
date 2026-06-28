# IJkmeting-plan — sensorcorrectiefactor (÷2,5) per sensortype

*Opgesteld 2026-06-08. **PLAN — niet uitvoeren.** Geen code- of datawijziging bij het
schrijven van dit document. Achtergrond en bevindingen: zie
`project_rmssd_div25_open_kwestie` en `project_sensor_type_always_demo` in het
CC-geheugen, en `docs/RMSSD_HERBEREKENING_OVERZICHT.md`.*

## Kernvraag van de ijking

> Klopt het dat de ÷2,5 bedoeld was voor een **optische (PPG) sensor**, en dat hij voor
> een **electrode-borstband** (Kyto/Polar, ECG-achtig RR) eigenlijk **≈1,0** had moeten
> zijn?

De code past `RMSSD/2,5` **uniform** toe in `static/js/hrv.js:77` (`calculateRMSSD`),
ongeacht de sensor. Maar de twee ondersteunde sensoren leveren fysisch verschillende
signalen:

- **USB-vingersensor** = optische PPG → overschat RMSSD plausibel (pulse-transit-jitter)
  → een correctiefactor >1 is verdedigbaar.
- **Bluetooth-borstband** (Kyto HRM-2937 / Polar H10, `0x180D` Heart Rate Service) =
  electrode-gebaseerd, levert ECG-equivalent RR → correcte factor is vermoedelijk ≈1,0;
  ÷2,5 zou hier RMSSD structureel met factor 2,5 **onderschatten**.

De ijking moet deze hypothese **per sensortype** bevestigen of verwerpen. Eén factor voor
beide types is de aanname die ter discussie staat.

---

## STAP 0 (los uitvoerbaar, kleinste stap) — sensor_type betrouwbaar vastleggen

**Waarom eerst:** ijking per sensortype is zinloos zolang het systeem niet registreert
welke sensor een meting maakte. Vandaag staat `sensor_type` repo-breed op de
opslag-default `'demo'` omdat het frontend het type nooit meestuurt — zie
`project_sensor_type_always_demo`. Dit is ook op zichzelf een datakwaliteitsfix en kan
**volledig los** van het hele ijkproject.

**Goede nieuws — het type is al bekend in de browser, alleen niet doorgegeven:**

- `static/js/sensor.js`: `_type` wordt al gezet op `'bluetooth'` (regel 32), `'usb'`
  (regel 65) of `'demo'` (regel 94), en via `onConnect(type, name)` naar buiten gegeven
  (regels 33 / 66 / 96).
- `templates/measure.html`: `selectSensor(type)` (regel 597) en `onConnect(sensorType,…)`
  (regel 608) kénnen het type al — het wordt alleen niet bewaard.
- Opslag leest het al: `app.py:3280` (pro) en `app.py:3294` (consumer) doen
  `str(data.get('sensor','demo'))`. **De kolom bestaat** in beide tabellen
  (`metingen.sensor_type`, `client_metingen.sensor_type`). **Geen schema-migratie nodig.**

**Wat de fix behelst (later, bij akkoord — hier alleen beschreven):**

1. In `selectSensor(type)` het gekozen type in een variabele vastleggen
   (bijv. `window._scSensorType = type;`).
2. In de POST-body van beide meet-templates het veld meesturen:
   - `templates/measure.html` rond regel 721 (naast `rr_intervals`).
   - `templates/sensor_en_meten.html` (zelfde patroon, ~regel 740).
   - Sleutel: `sensor: window._scSensorType` — sluit aan op `data.get('sensor', …)`.
3. **Opslag-default wijzigen van `'demo'` → `'unknown'`** (sluit aan op de
   CREATE-default `app.py:304/346`), zodat een ontbrekend veld niet langer ten onrechte
   "demo" registreert. Echte demo-metingen krijgen dan expliciet `'demo'`.
4. Na deploy: alleen ná deze fix gemaakte metingen hebben betrouwbaar sensortype.
   Historische metingen blijven herkomst-loos (niet reconstrueerbaar).

**Validatie van stap 0 (read-only):** maak één meting per sensortype en controleer dat
`sensor_type` correct landt; controleer dat `node --check` op de gerenderde inline-JS
slaagt (`tests/smoke_js_syntax.py`, zie `feedback_render_js_syntax_check`).

> Pas wanneer stap 0 live is en nieuwe metingen een betrouwbaar sensortype dragen, heeft
> het ijkproject (stap 1+) zin. Stap 0 levert ook meteen losse waarde: sensor-herkomst
> wordt analyseerbaar.

---

## STAP 1 — Protocol gelijktijdige ECG-referentiemeting

Doel: per sensortype de empirische schaalfactor `f_type = RMSSD_sensor_ruw / RMSSD_ref`
bepalen, waarbij `RMSSD_sensor_ruw` de RMSSD is **vóór** de ÷2,5
(d.w.z. `calculateRMSSD` zonder de deler), zodat we de zuivere schaalverhouding meten.

### Referentieapparaat

- **Voorkeur:** medisch-gevalideerde ECG met RR-export, óf **Polar H10** als
  RR-referentie (in onderzoek breed geaccepteerd als ECG-equivalente RR-bron).
- **Let op de cirkel:** als de StressChecker-borstband zélf een Polar H10 is, dan is voor
  dát type referentie ≈ apparaat-onder-test en valt `f_borstband ≈ 1,0` per definitie uit
  — dat is op zichzelf al een bevestiging van de kernhypothese. Gebruik dan een
  *onafhankelijk* ECG als referentie en de Kyto HRM-2937 als apparaat-onder-test, om
  niet tegen jezelf te meten.

### Apparaten-onder-test (per type)

1. **USB-vingersensor** (optische PPG).
2. **Bluetooth-borstband** (Kyto HRM-2937 — de electrode-variant).
3. **Demo** — **uitgesloten** van ijking (synthetisch signaal, geen fysiologische bron;
   alleen relevant om uit te sluiten van klinische aggregaten).

### Proefpersonen en aantallen

- **N ≥ 10–15 gezonde volwassenen**, gespreid over leeftijd en geslacht. (De factor zelf
  hoort leeftijd-onafhankelijk te zijn; spreiding dient om dat te toetsen, niet om de norm
  te ijken.)
- Per persoon **per sensortype ≥ 3 gelijktijdige opnames** van 90 s in rust →
  ~30–45 gepaarde observaties per type. Genoeg voor een robuuste mediaan + spreiding.
- **Gelijktijdig** = sensor-onder-test én referentie tegelijk op dezelfde persoon, zelfde
  90-s-venster (zelfde hartslagen). Beat-tot-beat-uitlijning is niet vereist — RMSSD is
  een samenvattende maat over het venster — maar de vensters moeten dezelfde periode
  beslaan.

### Condities / controles

- Zittend, in rust, na ≥2 min settelen; rustige spontane ademhaling; geen beweging/praten.
- Sensoren goed contact (vinger warm/schoon; borstband bevochtigd).
- Noteer per opname: persoon, leeftijd, geslacht, sensortype, ruwe RR-reeks (beide bronnen),
  starttijd. Bewaar de **ruwe RR** zodat herberekening mogelijk blijft.

### Afleiding van de factor (isoleer schaal, niet filter)

Per gepaarde opname:

1. Pas op **beide** RR-reeksen **identieke** voorbewerking toe: warm-up-trim `slice(15)` +
   `filterRR` (Kubios-mediaan, 100 ms-drempel, `hrv.js:16-75`). Zo meet je het
   **schaalverschil**, niet het filterverschil.
2. Bereken `RMSSD_sensor_ruw` (zónder ÷2,5) en `RMSSD_ref`.
3. `ratio = RMSSD_sensor_ruw / RMSSD_ref`.

Per sensortype: `f_type = mediaan(ratio's)` (mediaan = robuust tegen uitschieters),
rapporteer ook spreiding en een betrouwbaarheidsinterval, en toets op
leeftijd-/geslacht-afhankelijkheid (zou er niet moeten zijn).

### Uitkomst-interpretatie (de hypothese expliciet)

- **f_USB ≈ 2,5** en **f_borstband ≈ 1,0** → hypothese **bevestigd**: de ÷2,5 hoort bij de
  optische sensor; voor de borstband is hij onterecht en moet hij ~1,0 zijn.
- **f_USB duidelijk ≠ 2,5** → de waarde 2,5 zelf is mis-gekalibreerd (ook voor PPG).
- **f_borstband ≈ 2,5** → tegen de verwachting in; dan klopt de uniforme factor wél en
  vervalt de sensor-specifieke zorg.

---

## STAP 2 — Versie-overgang (als de uitkomst een andere factor vraagt)

**Principe: geen stille herberekening van bestaande data.** De hele bestaande dataset
(alle baselines, PI-Zwolle-cijfers, RI 3,13) is gekalibreerd op de huidige uniforme ÷2,5.
Een nieuwe factor is een **schaal-overgang met terugwerkende kracht** — behandel het als
versionering, niet als bugfix.

### Aanpak

1. **Schaal v1 = huidige toestand**: uniforme ÷2,5, herkomst-loos. Alle metingen t/m de
   overgangsdatum blijven v1 en worden **niet** herberekend of overschreven. (Historische
   per-sensor-herijking is sowieso onmogelijk: sensor_type ontbreekt vóór stap 0.)
2. **Schaal v2 = per-sensor factor**: vanaf de overgang past `calculateRMSSD` de
   sensor-specifieke `f_type` toe (bijv. via een `SENSOR_CORRECTION_FACTOR[type]`-map, in
   plaats van de inline-`/2,5`; let op de tweede plek `hlm/meting_src.html:6094` en de
   dode kopie `_removed` in `hrv.js:78`).
3. **Markeer de versie per meting**: leg bij nieuwe metingen vast met welke schaal+factor
   gerekend is (kleinste vorm: een `scale_version`-kolom of het opgeslagen factorgetal;
   de ruwe RR is er al, dus elke v1-meting blijft achteraf herrekenbaar mocht dat ooit
   gewenst zijn — als *aparte* weergave, niet als overschrijving).
4. **Baselines**: een baseline die in v1 is opgebouwd blijft v1; meng geen v1- en
   v2-waarden in één trend. Definieer expliciet hoe een lopende cliënt overgaat.
5. **Communicatie**: als absolute waarden/zone-labels verschuiven, informeer pro-gebruikers
   (KKH/PI) vóór de overgang; relatieve historie blijft geldig, absolute niveaus niet.

### Bijwerken bij de overgang (anders dan code)

- Kenniscentrum-teksten die de ÷2,5 uitleggen worden **sensor-specifiek**
  (`kenniscentrum.html:217/226/235` en HLM-variant).
- Twee bestaande documentatiefouten meteen meenemen (staan los van de schaalvraag en
  mogen ook eerder gefixt):
  - `kenniscentrum.html:237` zegt "2,5 SD-filter" — de code gebruikt een
    Kubios-mediaanfilter (100 ms), géén 2,5-SD-filter.
  - `kenniscentrum.html:169` definieert HRV% als "RMSSD/gemiddelde hartslag × 100" — de
    code rekent `RMSSD/leeftijdsnorm × 100`.
- `tests/lib/references.json` (`sensor_correction_factor`) en testcase B3
  (`tests/check_calculations.py:93`) herijken op de nieuwe factor(en).

---

## Volgorde-samenvatting

| Stap | Inhoud | Afhankelijkheid | Reversibel? |
|---|---|---|---|
| 0 | sensor_type betrouwbaar vastleggen (frontend → POST) | geen — los uitvoerbaar | ja, klein |
| 1 | gelijktijdige ECG-ijkmeting per sensortype, factor afleiden | vereist stap 0 voor nieuwe data | n.v.t. (meetwerk) |
| 2 | versie-overgang v1→v2 áls factor verandert | vereist stap 1-uitkomst | ja, mits geen stille herberekening |

**Niet doen:** de 2,5 nu aanpassen zonder ijkmeting; bestaande opgeslagen RI's
herberekenen/overschrijven; factor én Tegegne-norm tegelijk wijzigen; de
Peter-225%-vs-72%-casus als bewijs voor een foute 2,5 gebruiken (die toont de factor
+ de filter, niet dat 2,5 verkeerd is).
