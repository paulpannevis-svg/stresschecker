# Migratieplan — ÷2,5-factor verwijderen (uitvoeringsklaar)

> 🛑 **NOG NIET UITVOEREN OP PROD.** Paul beslist de timing.
>
> ⚠️ **STAGING-BEVINDING 2026-06-08 — ÷2,5 VERWIJDEREN ALLÉÉN OVERCORRIGEERT.**
> De migratie is op staging uitgevoerd (branch `staging`, commit `eee5ea1`; DB's herberekend;
> backup `/opt/backups/div25-staging-20260608-083953`). Resultaat: de scores schieten door
> naar boven. **Peter 377: ri 5,4 → 9,5 ("Veerkrachtig")** terwijl zijn hoge RMSSD juist
> aritmie-artefact is. Populatie kantelt naar de top: pro veerkrachtig 1 → 100 (van 239),
> consumer 3 → 57 (van 141); mediaan RI pro ~7,7. Geen rekenbug (eindwaarde- en
> window-mean-methode identiek; 377 met huidige Tegegne-norm berekend).
>
> **VERFIJNING (2026-06-08, ankerpunt-analyse op schone basis) — de tabel/zones zijn TOCH
> correct; ÷2,5 is de ENIGE verstoring.** Een norm-persoon (ware RMSSD = norm) toont onder
> ÷2,5 HRV% 40% → RI 3,8 "Belast" (te streng, verklaart 15 jaar "te streng"-ervaring);
> zónder ÷2,5 toont diezelfde persoon 100% → RI 6,7 "In balans" — het anker klopt. De
> Verveen-tabel + zonegrenzen (2/4/6/8) zijn dus correct geijkt voor de échte HRV%-schaal en
> hoeven NIET herijkt. Op de **schone subset** (n=61, kwaliteit>80, huidige Tegegne-norm)
> geeft ÷2,5 weghalen een mediaan RI **6,0 = "In balans"** (kwartielen 4,8/6,0/7,9) — GEEN
> wilde overshoot. De eerder gerapporteerde 7,7/42%-veerkrachtig kwam uit de **volledige
> rommelige staging-mix** (oude norm, legacy default-kwaliteit-100-rijen, artefacten) — geen
> ontwerpbasis. De echte uitschieter is Peter 377 → 10,0, en dat is **artefact (aritmie)**,
> geen schaalprobleem.
>
> **DUS: variant (a) — ÷2,5 weg (f=1,0), tabel/zones ONGEMOEID — is de schone, principiële
> keuze.** Een coaching-mediaan lager dan 6,0 forceren via een residu-factor (b) of een
> RI-deler-aanpassing (c) herintroduceert óf een onverklaarde constante óf breekt het anker
> (norm-persoon zakt naar "Licht belast") → afgeraden. Twee zaken blijven APARTE assen, niet
> nu: **(1) Peter / aritmie → kwaliteits-gating** (zie `docs/KWALITEITS_GATE_ONTWERP.md`);
> **(2) leeftijds-residu → norm-helling `N`**. Variantcijfers: zie verkenning onderaan /
> `project_rmssd_div25_open_kwestie`.
>
> Het onderstaande oorspronkelijke plan (enkele edit + volledige herberekening) is hiermee
> WEER de hoofdroute voor de schaal-fix; de DB-herberekening blijft nodig, maar overweeg
> kwaliteits-gating mee te nemen zodat aritmie-metingen niet als "Veerkrachtig" tonen.
>
> ✅ **SCHAAL GEVALIDEERD op staging (2026-06-08).** Schone PI-cliëntgroep (pro_key 5eabaeb,
> excl. Peter/client 121, kwaliteit >85, mét ruwe RR, n=43) na ÷2,5-verwijdering:
> **mediaan RI ~5 ("Licht belast"), 58% in Licht belast/In balans**, onderkant zwaar/belast
> (gem. hrv% 45–59), en slechts **12% (5/43) Veerkrachtig — terecht** (gem. hrv% **166**, écht
> boven leeftijdsnorm). De hele gradient is fysiologisch logisch. **Variant (a) is dus correct
> gekalibreerd; de schaal hoeft niet verder bijgesteld.** De eerder gevreesde overshoot zat
> alleen bij aritmie-/lage-kwaliteit-metingen (Pauls eigen metingen 9–10 = artefact, niet de
> schaal; bevestigd als ongeschikt als toets). **Kwaliteits-gate blijft de aparte vervolgstap**
> (`docs/KWALITEITS_GATE_ONTWERP.md`).

*Opgesteld 2026-06-08. Read-only voorbereid: geen code/data gewijzigd. Achtergrond,
bewijsketen en open punten: zie `project_rmssd_div25_open_kwestie` (CC-geheugen),
`docs/RMSSD_HERBEREKENING_OVERZICHT.md` en `docs/IJKMETING_PLAN_SENSORFACTOR.md` (dat
laatste vervalt grotendeels — zie onder).*

## Waarom (bewijsketen — gesloten zonder ECG-ijkmeting)

- De ÷2,5 is bevestigd als exacte constante (2,50× in alle nagerekende metingen) en
  gedocumenteerd als "PPG→ECG sensorcorrectie" — maar de **waarde 2,5 heeft nooit een
  bron/berekening/validatie** gehad en predateert git.
- Twee onafhankelijke bronnen ontkrachten de sensor-rationale: **TNO** toetste de
  USB-sensor op **~5% afwijking van ECG**; **Verveen** stelde vast dat **ECG≈PPG**. Een
  sensorverschil van ~5% rechtvaardigt ~1,05, geen 2,5. → De factor is **sensor-onafhankelijk**;
  het per-sensor-ijkplan vervalt.
- **Norm-centrering-toets (hardste niet-ECG-bewijs, 51 cliënten, kwaliteit>80):** de norm
  is gedefinieerd als gezonde mediaan = 100%. MÉT ÷2,5 zakt de mediaan naar **37% (pro) /
  49% (consumer)** — fysiologisch onhoudbaar. ZONDER ÷2,5 landt hij op **93% / 122%** ≈ 100%.
  In 16/20 leeftijdsgroepen en beide aggregaten wint "zonder".
- **Sanity Verveen-tabel:** hrv%=100 → RI ~6,7 ("In balans"); hrv%=40 (huidig) → RI ~3,8
  ("Belast"). Norm én tabel zijn onderling consistent — alleen als hrv% zónder ÷2,5 wordt
  ingevoerd. De ÷2,5 brak beide tegelijk.

Conclusie: de ÷2,5 is **spurieus**. Verwijderen herstelt de bedoelde kalibratie.

## 1. De code-ingreep (minimaal)

| Plek | Actie |
|---|---|
| `static/js/hrv.js:77` (`calculateRMSSD`, de `…/2.5`) | **`/2.5` verwijderen** (enige live SC-toepassing) |
| `static/js/hrv.js:78` (`_removed`) | dode functie opruimen (hygiëne) |
| `hlm/meting_src.html:6094` (`SENSOR_CORRECTION_FACTOR = 2.5`) | → `1.0`, of deling in `6185`/`6190` verwijderen (HLM inactief, voor consistentie) |
| `templates/measure.html:280`, `sensor_en_meten.html:270`, `lab.html:58` | **`hrv.js?v=4` → `?v=5`** (cache-bump, anders krijgen browsers de oude versie) |

Bijvangst: SC deelde `calculateSDNN` niet door 2,5 maar RMSSD wél — die inconsistentie
verdwijnt; RMSSD en SDNN staan daarna beide op ruwe (ECG-)schaal.

Let op de **service-worker-cache** (`project_sw_cache_followup`): cache-bump moet ook daar
doorkomen, anders zien klanten de oude UI/JS.

## 2. Data-migratie — HERBEREKENEN (niet versioneren)

**Waarom geen versie-overgang (v1 bevroren, v2 alleen nieuw):** de ÷2,5 zit op de gedeelde
trend-schaal. Baseline (`analytics.compute_baseline`), delta en verloopgrafieken worden
live uit opgeslagen RI berekend. Bij mengen van v1-historie en v2-nieuw toont elke nieuwe
meting een **nep-"verbetering" van ~+2,5 RI** en knikt de grafiek op de overgangsdatum.
Versioneren breekt juist de kernfunctie. **Daarom: volledig herberekenen.**

**Het kan exact, zónder ruwe RR** (de norm valt weg in de breuk). Voor élke opgeslagen rij
in `metingen` (consumer) en `client_metingen` (pro):

```
hrv_pct_nieuw = min(220, round(hrv_pct_oud * 2.5))      # exact
rmssd_nieuw   = rmssd_oud * 2.5                          # exact
ri_nieuw      = lookupRelaxIndex(bpm_opgeslagen, hrv_pct_nieuw)   # bpm+hrv_pct staan als kolom
```

Dus **alle ~373 metingen** (incl. de 147 oudere pro-rijen zónder ruwe RR) zijn
deterministisch om te zetten. Elke gebruiker blijft op één coherente schaal → baseline/
delta/grafieken blijven kloppen.

**Dit is geen *silent* recompute:** expliciet, gedocumenteerd, met backup vooraf, na akkoord.

**Twee subpunten:**
- ~1 consumer-meting met `hrv_pct` al op de 220-clamp is niet exact terug te rekenen
  (blijft 220). Verwaarloosbaar.
- **RI-definitiekeuze (apart):** opgeslagen `ri` = venstergemiddelde (`measure.html:711`);
  een her-lookup geeft de eind-RI. Wil je de venster-aard behouden, herschaal dan per
  venster via de `timeseries`-kolom (bevat per venster `ri`) en middel opnieuw. Koppelt
  aan het bekende venster-vs-eindwaarde-artefact; hoeft de ÷2,5-beslissing niet op te houden.

### Impact (verse herberekening, schone pro-subset n=61)

| | med RI | Zwaar belast | Belast | Licht belast | In balans | Veerkrachtig |
|---|---|---|---|---|---|---|
| MÉT ÷2,5 (huidig) | 3,5 | 16 | 22 | 18 | 5 | 0 |
| ZONDER ÷2,5 | 6,0 | 2 | 6 | 22 | 18 | 13 |

Gem. \|ΔRI\| = 2,9, max +5,3. Verdeling kantelt van "62% belast-of-erger, niemand
veerkrachtig" naar "mediaan in balans". **Klanten zien hun RI fors stijgen** — dit is
communicatie-gevoelig (zie timing/persbericht).

## 3. Wat NIET hoeft te veranderen

- **Zonegrenzen 2/4/6/8** — leven op twee plekken (`hrv.js:86` getLabel én
  `analytics.py:33` zone_for_ri voor PDF-rapporten); **beide ongewijzigd**, worden juist
  correcter (mediaan-persoon → "In balans").
- **Kleurzones** (`hrv.js:87`, 3/5/7/8,5) — ongewijzigd.
- **220-clamp / Verveen-tabel** — ongewijzigd; slechts ~4–9% tikt de bovengrens aan.
- **Baseline** — niet apart opgeslagen, schuift mee mits herberekend.

## 4. Buiten scope — secundair leeftijds-residu (aparte stap, later)

Zonder ÷2,5 landt het aggregaat goed, maar er blijft leeftijdsscheefte (18–29 onder 100%;
55–69 erover). Dat raakt de **leeftijdshelling van norm-tabel `N`** (`hrv.js:12`), niet de
constante. **Apart beoordelen, met eigen bewijs; nooit constante én norm-helling tegelijk
wijzigen** (anders niet toe te schrijven).

## Uitrol-checklist

1. **Timing-akkoord van Paul** (i.v.m. Duits persbericht van morgen) — blokkerend.
2. Backup (`backup.sh`).
3. Code-edits (§1) op **staging eerst** (STAGING-FIRST, `project_staging_setup_plan`).
4. `node --check` op gerenderde inline-JS (`tests/smoke_js_syntax.py`).
5. Migratiescript (§2) op staging draaien, met before/after-telling per zone.
6. Tests herijken: `tests/lib/references.json` (`sensor_correction_factor`),
   `tests/check_calculations.py:93` (B3).
7. Klantteksten: ÷2,5-uitleg weg + twee bestaande fouten (`kenniscentrum.html:237`
   "2,5 SD-filter", `:169` HRV%-formule).
8. Paul checkt op test.stresschecker.com → merge `staging`→`main` → promotie prod.
9. **Klantcommunicatie** overwegen: RI-waarden stijgen zichtbaar; vooral voor PI-Zwolle/KKH
   en bestaande gebruikers met lopende baselines.
```
