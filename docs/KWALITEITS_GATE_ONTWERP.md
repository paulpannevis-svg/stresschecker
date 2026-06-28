# Kwaliteits-gate — ontwerp (nog niet bouwen)

> 🛑 **ONTWERP — niet bouwen.** Apart besluit. Hoort bij de ÷2,5-schaal-fix maar is een
> losse as. Context: `docs/MIGRATIE_PLAN_DIV25_VERWIJDEREN.md` + `project_rmssd_div25_open_kwestie`.
> Opgesteld 2026-06-08 (read-only voorbereid).

## Probleem

De RI/zone wordt nu **altijd getoond**, ongeacht meetkwaliteit. Bij een onregelmatige
(aritmische) hartslag corrigeert de Kubios-filter (`hrv.js:16-75`) ectopische slagen maar
niet volledig; de resterende variabiliteit blaast de **RMSSD kunstmatig op**. Gevolg, vooral
ná de ÷2,5-schaal-fix:

- **Peter 377** (kwaliteit **79** = 21% slagen gecorrigeerd) → na ÷2,5-fix **RI 9,5–10,0
  "Veerkrachtig"**. Een aritmie-meting wordt gepresenteerd als topconditie.
- **Asymmetrisch gevaar:** een vals-positieve "Veerkrachtig" bij iemand met een ritmestoornis
  is klinisch schadelijker dan een vals-lage score. De gate moet vooral voorkomen dat een
  lage-kwaliteit-meting als **positief gezondheidsoordeel** verschijnt.

**Schaalkalibratie lost dit niet op** (bewezen: in álle gecentreerde varianten blijft 377
"Veerkrachtig"). Dit is een aparte as: filteren/gaten op kwaliteit.

## Wat `kwaliteit` is (bestaat al)

- Berekend door `getMeetKwaliteit` (`hrv.js:88`) = `% slagen NIET gecorrigeerd` door `filterRR`.
  Laag = veel ectopische/onregelmatige slagen. Opgeslagen in kolom `kwaliteit`
  (`metingen` + `client_metingen`). **Geen nieuwe meting/berekening nodig.**
- ⚠️ Legacy: metingen zónder ruwe RR kregen de **default `kwaliteit=100`** (veld werd niet
  meegestuurd). Die "100" is dus *onbekend*, niet *uitstekend* — de gate moet dat onderscheiden
  (zie open beslissing 4). Sluit aan op [[project_sensor_type_always_demo]] (zelfde
  default-veld-probleem).

### Verdeling op prod (metingen mét ruwe RR)

| | kw <70 | kw 70–84 | kw ≥85 | totaal |
|---|---|---|---|---|
| pro `client_metingen` | 11 (12%) | 27 (29%) | 54 (59%) | 92 |
| consumer `metingen` | 10 (7%) | 20 (15%) | 104 (78%) | 134 |

**Peter 377 (kw 79) zit in de 70–84-band** → een `<70`-gate mist hem. Aritmie produceert vaak
kw in de 70–85-range (15–30% gecorrigeerd), niet per se <70. De drempel moet daar rekening
mee houden.

## Bestaande kwaliteit-UI (waar de gate op aansluit)

- `kwadrant.html:315-317`: sterren (★★★ ≥90 / ★★☆ ≥70 / ★☆☆ <70), label (Uitstekend ≥90 /
  Goed ≥70 / Matig ≥50 / Onvoldoende <50), en `qualityAdvice` ("raadpleeg arts") **alleen bij
  kw<70**.
- `kwadrant.html:83`: bestaande waarschuwingstekst (NL/DE/EN) "meetkwaliteit onvoldoende …
  incidentele hartritmestoornis … overleg met arts".
- `measure.html:646` / `sensor_en_meten.html:656`: live `if(kwaliteit < 85)`-waarschuwing direct
  na meten.
- **Niets hiervan gate't de RI/zone zelf.** Dat is het gat.

## Ontwerp — getrapte gate op de RI/zone-PRESENTATIE

Kernprincipe: **gate op weergave, overschrijf de opgeslagen RI niet** (ruwe waarde blijft voor
analyse/herberekening behouden, conform "geen stille datavernietiging").

| Tier | kwaliteit | RI/zone-weergave | Boodschap |
|---|---|---|---|
| **Vertrouwd** | ≥ 85 | RI + zone normaal | (huidige UI) |
| **Beperkt** | 70–84 | RI + zone tonen **mét caveat**; **géén positief "Veerkrachtig"-claim** — bij RI in veerkrachtig-zone label terugzetten naar neutrale tekst ("meting onzeker") of ster-confidence tonen | "Meetkwaliteit beperkt — interpreteer met voorzichtigheid" |
| **Onbetrouwbaar** | < 70 | RI/zone **onderdrukken** (niet als score tonen) | "Meting onbetrouwbaar — herhaal onder rustige omstandigheden" + bestaande arts-tekst |

**Asymmetrie ingebouwd:** de "Beperkt"-tier blokkeert specifiek de **bovenkant** (vals-positieve
"Veerkrachtig") — een lage-kwaliteit-"Belast" mag blijven staan (cautious is veilig), een
lage-kwaliteit-"Veerkrachtig" niet. Dit vangt Peter 377 (kw 79 → Beperkt → geen "Veerkrachtig").

### Aanvullend: aritmie als feature, niet alleen guard

Herhaald lage kwaliteit is een **klinisch signaal** (kenniscentrum_pro: "bij aanhoudend
onregelmatige hartslag → verwijs naar arts"). Overweeg: bij ≥N opeenvolgende metingen met
kw<70 een expliciete (niet-diagnostische) "onregelmatig ritme gedetecteerd — overleg met
arts"-melding. Voor pro/KKH waardevoller dan louter verbergen.

## Implementatiepunten (bij bouw)

1. **Centrale helper** in `hrv.js` (bv. `riConfidence(kwaliteit)` → 'trusted'|'limited'|'untrusted'),
   zodat drempels op één plek staan (single source of truth, vermijd de verspreide 70/85/90 nu).
2. **`kwadrant.html`** — RI/zone-render door de gate; "Beperkt"/"Onbetrouwbaar"-toestanden +
   3-talige teksten (NL/DE/EN, naast de bestaande regel 83).
3. **`analytics.py`** — `zone_for_ri` (PDF-rapporten) en vooral **`compute_baseline` /
   `baseline_day_values`**: lage-kwaliteit-metingen **uitsluiten van baseline & trend**, anders
   vervuilt één aritmie-meting de baseline/delta. (Nu gebruikt baseline alle opgeslagen RI.)
4. **Live meet-flow** (`measure.html`/`sensor_en_meten.html`): bestaande `<85`-waarschuwing
   uitlijnen met de nieuwe tiers.
5. **Geen schema-wijziging** — `kwaliteit` bestaat al.

## Interactie met de ÷2,5-schaal-fix

- **Onafhankelijk maar samen wenselijk.** De schaal-fix (variant a, ÷2,5 weg) tilt de hele
  verdeling omhoog → zónder gate verschijnen juist de aritmie-metingen als "Veerkrachtig".
  De gate hoort dus **bij of vóór** de prod-promotie van de schaal-fix, niet erna.
- De DB-herberekening van de schaal-fix raakt de gate niet (gate werkt op weergave + de
  bestaande `kwaliteit`-kolom).

## Peter 377 onder dit ontwerp

ri (na ÷2,5-fix) 9,5–10,0, kwaliteit 79 → tier **Beperkt** → "Veerkrachtig"-claim geblokkeerd,
caveat "meetkwaliteit beperkt" getoond, RI niet als positief gezondheidsoordeel gepresenteerd.
Bij herhaald lage kwaliteit: arts-signaal. ✅ Opgelost zonder de schaal te verbuigen.

## Open beslissingen voor Paul

1. **Drempels** 85 / 70 — overnemen of anders? (85 vangt Peter; 70 zou hem missen.)
2. **"Beperkt"-gedrag:** RI tonen-met-caveat vs RI cappen vs alleen "Veerkrachtig" blokkeren.
   (Voorstel: alleen de positieve bovenkant blokkeren.)
3. **Baseline/trend:** lage-kwaliteit-metingen uitsluiten — ja/nee en vanaf welke drempel.
4. **Legacy default-kwaliteit-100:** hoe behandelen (als 'onbekend' i.p.v. 'vertrouwd')?
   Raakt veel oude rijen; mogelijk gefaseerd of alleen voor nieuwe metingen.
5. **Aritmie-arts-signaal:** wel/niet, en bij hoeveel opeenvolgende lage-kwaliteit-metingen.
6. **Klantcommunicatie:** sommige bestaande "Veerkrachtig"-scores verdwijnen/worden caveated.
