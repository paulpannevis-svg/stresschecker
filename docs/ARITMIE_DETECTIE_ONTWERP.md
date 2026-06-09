# Aritmie-/onregelmatigheidsdetectie op RR-niveau — ontwerp

> ✅ **GEBOUWD op staging 2026-06-08, niet gepromoveerd naar prod** (promotie-voorwaarden:
> zie sectie "VERFIJNING v2" — min. 2 weken dagelijks staging-gebruik + herijking op een
> representatieve gezonde + bekend-onregelmatige referentie). Implementatie: `static/js/hrv.js`
> (`rrIrregularity`) + inline op `kwadrant.html`/`results.html`/`pro/eigen_metingen.html`.
> Read-only voorbereid 2026-06-08. Context: `project_rmssd_div25_open_kwestie`,
> `KWALITEITS_GATE_ONTWERP.md`. **Strikt los van de norm-helling (75+) — dat is een
> aparte fix.**

> ⚠️ **VOORLOPIG CONSERVATIEF VOORSCHOT OP PROD (2026-06-09) — GEEN definitieve drempel.**
> Op prod (main) staat sinds 2026-06-09 een minimale **tabel-markering** (⚠️ + neutrale regel op
> `/resultaten` + `/pro/eigen_metingen`) die ALLEEN de evidente plafond-onzin vangt:
> `SD1/SD2 >= 1.05` **ÉN** `HRV% >= 200`. Bewust streng (3.0% van de prod-populatie, alleen 220%-
> plafond + extreme vorm). **Dit is een voorschot, geen eindkeuze:** GEEN aggregaat-uitsluiting,
> GEEN rode trendlijn, GEEN Kompas op prod. De **definitieve drempel** (SD1/SD2 + RMSSD-vloer) volgt
> uit de **30-06-herijking** op de opgebouwde prod-`gate_metrics`. De staging-gate (0.55/25) blijft
> de te-herijken kandidaat; 0.55 was op de echte prod-verdeling onbruikbaar (~62%, geen kloof).

## Probleem (waarom dit nodig is)

De huidige kwaliteits-gate (`getMeetKwaliteit`/`filterRR`, grijs bij kwaliteit <85) is een
**artefact-detector**, geen aritmie-detector. Hij markeert slagen die ver van hun **lokale
mediaan** liggen (sensorruis, losse ectopie, dropouts) maar meet **geen** algehele
ritme-onregelmatigheid. Empirisch bewijs (prod, Paul's eigen metingen):
- id458: hrv% 213 (zeer hoge RMSSD) maar **0 slagen gecorrigeerd → kwaliteit 100%**.
- id526: 8 beat-to-beat-sprongen >100 ms blazen RMSSD op tot hrv% 220, maar slechts 3
  uitschieters → **kwaliteit 96%**.

→ Aanhoudende onregelmatigheid (mogelijk boezemfibrilleren) die zich uit als **hoge,
vloeiende variabiliteit zonder scherpe spikes** krijgt "★★★ Uitstekend" en wordt door de
gate **niet** gegrijsd. De gate vangt aritmie dus alleen **indirect/toevallig**.

## De maat + drempels

**Hoofdindicator: nRMSSD = RMSSD / gem.RR** (genormaliseerde RMSSD; gevalideerde real-time
AF-indicator, Dash e.a.). Op onze data de beste enkele discriminator.
**Bevestiging: pNN50** (% opeenvolgende |ΔRR| >50 ms) — sluit losse spikes uit: pNN50 ≥ 50
betekent dat >helft van de slagen afwijkt = *aanhoudend*, niet 1–2 ectopische slagen.
**Ondersteunend/uitleg: SD1/SD2** (Poincaré) — AF-patroon → 1 of >1. **Niet als harde
poort** gebruiken: id331 (nRMSSD 0,339, pNN50 78, evident aritmie) viel anders af op
SD1/SD2 0,84.

Andere overwogen maten en waarom niet als hoofd: sample-entropy (op korte opnames zwak —
discrimineerde niet, id524 had juist lage SampEn); CV van RR (correleert met nRMSSD, minder
specifiek); enkel de Kubios-drempelcorrectie (= wat we al hebben, mist aanhoudende
onregelmatigheid).

## Hybride tiers (vanaf welke last (a) corrigeren vs (b) markeren)

| Tier | Regel | Actie |
|---|---|---|
| **Schoon** | nRMSSD < 0,07 | normale HRV; bestaande lichte artefactcorrectie |
| **Corrigeer-spikes (a)** | nRMSSD ≥ 0,10 **maar** pNN50 < 50 | losse ectopie/spikes → `filterRR` interpoleert (bestaand), toon gecorrigeerde HRV |
| **Caveat (midden, conservatief)** | nRMSSD 0,07–0,10 én pNN50 ≥ 30 | toon score **met voorbehoud** ("verhoogde onregelmatigheid") |
| **MARKEREN (b)** | **nRMSSD ≥ 0,10 én pNN50 ≥ 50** | géén stellige score: *"te onregelmatig voor een betrouwbare HRV-meting; mogelijk een onregelmatig hartritme — bij herhaling raadpleeg een arts"* |

**CCC-lijn:** lichte ruis/spikes wegcorrigeren (a) is legitiem; **aanhoudende** onregelmatigheid
**spiegelen** (b) — niet een verzonnen "Veerkrachtig" tonen en niet stil grijzen. De
caveat-band is **bewust conservatief** (een matig-verhoogde meting krijgt voorzichtigheid,
geen markering).

## Validatiecijfers (read-only, tegen alle metingen mét RR)

| | n (mét RR) | MARKEREN (b) | caveat | corrigeer-spikes (a) | schoon | vals-positief |
|---|---|---|---|---|---|---|
| Consumer | 120 | 18 (15%) | 11 | 12 | 79 | **0** |
| Pro | 87 | 12 (14%) | 8 | 17 | 50 | **0** |

- **0 vals-positieven** (geen schone/laag-variabele meting gemarkeerd).
- **527 + 432 blijven SCHOON** (nRMSSD 0,018/0,019) — hoge RI puur door 75+-norm, terecht
  niet als onregelmatig gemarkeerd → bevestigt scheiding van de norm-helling.
- 526 (kw96) / 458 (kw100): schoon (nRMSSD 0,054/0,036) — slechts matig verhoogd.
- Paul's MARKEREN-gevallen: 331, 333, 337, 457, 523, 524 (allemaal aanhoudend onregelmatig).
- Losse-spike-gevallen (bv. 360: nRMSSD 0,138 maar pNN50 5) → correct (a), niet markeren.
- **Gat t.o.v. huidige kw-gate:** 2 consumer-metingen met kwaliteit ≥85 én aanhoudend
  onregelmatig worden door de nieuwe maat wél gevangen, door de kw-gate niet. (Paul's eigen
  zware gevallen hadden toevallig óók kw<85 → die ving de gate al; de directe maat is de
  *principiële* fix en sluit het resterende gat.)

## Kanttekeningen (verplicht vóór productie)

1. **Eerste ijk op één populatie.** De drempels (nRMSSD 0,07/0,10; pNN50 30/50) zijn afgeleid
   op één dataset: Paul + Peter + PI-Zwolle. **Vóór productie breder tunen** tegen bekende
   **AF-opnames** én bekende **gezonde hoge-HRV-opnames** (fitte/jonge mensen), zodat de grens
   tussen "echte hoge HRV" en aritmie hard onderbouwd is.
2. **Markeren (b) is de CCC-lijn voor zware gevallen; lichte ectopie corrigeren (a).** De
   caveat-band is bewust conservatief.
3. **Strikt los van de norm-helling (75+).** Deze maat raakt 527/432 niet; de lage
   75+-norm (14,9 ms) blijft een aparte fix. Niet samen wijzigen.
4. **Non-diagnostisch formuleren.** Geen "u heeft aritmie/boezemfibrilleren"; wel "te
   onregelmatig voor een betrouwbare meting — bij herhaling raadpleeg een arts".

## Haalbaarheid

`rr_intervals` (JSON) wordt opgeslagen sinds ~2026-04-10 → de maat is **retroactief** te
backfillen op alle ~226 metingen mét RR én **live** op nieuwe metingen. Legacy zonder RR:
niet mogelijk (blijven "onbekend"). Pure RR-berekening; geen `import app` (DB-mutatie-risico).

## Relatie tot bestaande gate

Aanvulling/vervanging van de kwaliteits-gate-laag, niet van de schaal-fix. Aanbevolen
implementatieplek: centrale helper naast `riConfidence` in `hrv.js` (bv. `rrIrregularity(rr)`
→ {tier, nrmssd, pnn50}), plus dezelfde getrapte weergave-logica als de kwaliteits-gate
(kwadrant/lijsten/aggregaten). Aggregaten: MARKEREN-metingen net als lage-kwaliteit uitsluiten
+ tellen ("op X van Y te onregelmatig").

---

## VERFIJNING 2026-06-08 (v2) — gekozen gate na data-validatie. GEBOUWD op staging 2026-06-08 (niet op prod).

> Taal: **noem dit GEEN "aritmie"** — het is **ongestructureerde onregelmatigheid (hart óf sensor)**,
> niet bewezen aritmie (uit RR alleen niet te scheiden van PPG-ruis). KK-materiaal baseert hierop.
> Neutraal label: **"meting te onregelmatig om betrouwbaar te scoren"** (geen diagnose).

**ONTWERPKEUZE (in changelog vastleggen):** MARKEREN, niet corrigeren. Bij onregelmatigheid GEEN
score tonen maar de neutrale melding. Reden: wellness-app, geen CE-MDR; we weten niet of het hart
of PPG-ruis is, dus claimen geen van beide.

**GEKOZEN GATE:** markeer als `SD1/SD2 >= ARR_SD1SD2 (0.55)` **EN** `RMSSD >= ARR_RMSSD_FLOOR (25 ms)`.
- Benoemde constanten, niet hardcoded. Berekenen op de **VOLLEDIGE RR** (geen slice-15) — anders
  wijken de waarden af van Kubios (geverifieerd: op volledige RR matchen 641/644/645/682 exact).
- **pNN50-OF-tak GESCHRAPT:** die vlagde 38 metingen extra die SD1/SD2<0.55 (= gestructureerd =
  genuine hoge HRV/RSA) hadden — dat zijn juist de béste metingen, fout om te markeren.
- **RMSSD-vloer 25** weert het vlak-kalme SD1/SD2-artefact (bij lage variabiliteit loopt SD1/SD2→1).
  Natuurlijke kloof in de data: RMSSD onder SD1/SD2>=0.55 = 21,21,24,⟨kloof⟩26,26,27,30...; vloer 25
  zit in de kloof; markeringsgraad stabiel 47–52% over vloer 25–35 (geen overfit).

**VALIDATIE (read-only, op de scheve staging-set Paul+Peter+PI):**
- IJk (Kubios-geverifieerd): 641 (SD1/SD2 0.89, RMSSD 60.9) → VANG; 644 (0.43/25.5), 645 (0.32/14.2),
  682 (0.36/17.7) → spaar; FP's 365/426/305 (SD1/SD2 0.59–0.74 maar RMSSD 20–24) → spaar. ✓
- Markeringsgraad 52% — op een onregelmatigheid-zware set, GEEN algemene rate. Drempel+vloer vóór
  brede uitrol herijken op representatieve gezonde + bekende-onregelmatige referentie.

**CONSISTENTIE (besluit B, niet A):** dezelfde gate op ALLE surfaces. Kwadrant + results gebruiken
nu nog de OUDE maat (nRMSSD>=0.10 && pNN50>=50, slice-15) die 641 NIET vangt. STAP 3 vervangt die
overal door deze gate — geen pagina mag "te onregelmatig" zeggen terwijl een andere "veerkrachtig" toont.

**STAP 3 — UITGEVOERD op staging 2026-06-08** (branch `staging`, commits 506636e→4835f24):
1. ✅ backup.sh ; staging-branch ; per-fix commit + changelog (incl. ontwerpkeuze + taal-afspraak).
2. ✅ Constanten (`ARR_SD1SD2=0.55`, `ARR_RMSSD_MIN=25`) + gate centraal in `hrv.js`
   (`rrIrregularity`, binair flag/clean); inline op eigen_metingen + kwadrant + results — oude
   nRMSSD/pNN50-gate vervangen. Volledige RR. Gevlagd → neutrale melding i.p.v. score; kwadrant-
   melding herschreven naar v2-taal ("hart óf sensor", geen "onregelmatige hartslag").
3. ✅ Smoke (node --check + smoke_js_syntax 18/18, 3 talen) ; acceptatie: gate uit de live templates
   beslist op alle 3 surfaces eensluidend — 641 gemarkeerd, 644/645/682 + FP's 365/426/305 normaal.

**RESTEERT vóór prod-promotie:** min. 2 weken dagelijks staging-gebruik (vanaf 2026-06-08 → ≥2026-06-22)
ÉN drempel+vloer herijken op een representatieve gezonde + bekend-onregelmatige referentie (de
ijkset hierboven is onregelmatigheid-zwaar, ~53% gemarkeerd — geen algemene populatie).
