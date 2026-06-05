# StressChecker regressietest-suite

Verifieert in één commando dat (a) metingen in de juiste database landen
afhankelijk van consumer-/Pro-account en actieve sessie, en (b) de
kern-HRV-berekeningen (RMSSD, HRV%, Verveen-lookup RI, zone-indeling)
exact dezelfde waardes geven als vastgelegd in `lib/references.json`.

## Aanroep

```
/opt/stresschecker/tests/run_all.sh
```

De tests draaien tegen de live app op `http://localhost:8080` en tegen de
echte productie-databases, met strikte `__TEST__`/`__TEST_CONSUMER__`/
`__TEST2__` markers. Cleanup verwijdert testdata na afloop, óók bij
crash (bash-trap + per-script try/except).

## Wanneer draaien

Na elke inhoudelijke fix én aan het einde van elke werksessie. Runtime
is < 5 seconden — er is geen excuus om 'm over te slaan.

## Exit-codes

| Exit | Betekenis |
| --- | --- |
| 0 | Alle tests PASS |
| 1 | Residu van vorige run OF setup-fout OF minstens één test FAIL |

Output staat direct op de terminal. Er is geen logbestand — scroll terug
om te zien welke test faalde. De laatste blok-samenvatting
(`TOTAAL: X passed, Y failed`) staat boven de cleanup-trap.

## Residu-foutmelding

Als de pre-flight `cleanup --check` residu vindt, stopt het script met:

```
ABORT: residu aanwezig van vorige run.
Controleer handmatig wat er staat (zie output hierboven)
en draai 'python3 lib/cleanup.py cleanup' alléén als je zeker weet
dat het om testdata gaat. Daarna opnieuw run_all.sh.
```

De auto-cleanup-trap is **bewust nog niet geïnstalleerd** tijdens
pre-flight, precies zodat restanten niet stilletjes verdwijnen voordat
je ze hebt gezien. Neem even 30 seconden om in de drie databases te
kijken wat er staat onder de test-markers, dan pas handmatig opruimen.

## references.json

`lib/references.json` bevat de verwachte HRV-uitkomsten voor een
deterministisch gegenereerde synthetische RR-set (seed 42, 90
intervallen rond 65 BPM met RSA-sinusoïde). Inclusief `_meta`-sectie
die de aannames vastlegt: age=50, sex=male, norm=28, sensor correction
factor=2.5.

**Opnieuw genereren alleen bij échte formule-wijzigingen** —
bijvoorbeeld aanpassing van de Kubios-filter, de `/2.5` correction
factor, de Verveen-lookup-tabel of de RMSSD_NORMS-tabel in
`static/js/hrv.js`. Bij een zuivere refactor die de numerieke output
niet verandert: **niet hergenereren**. Dan is test-failure het correcte
signaal dat er toch iets is veranderd.

Hergenereren gaat via de commandoregel die Paul in stap 5 gebruikte
(`random.Random(42).gauss` + RSA-formule, `node -e` om `HRV.*` aan te
roepen). Zie `_meta.generator` in references.json voor exacte params.

## Architectuur

```
tests/
├── run_all.sh                  orchestrator
├── check_routing.py            categorie A (A1–A6)
├── check_calculations.py       categorie B (B1–B4)
├── README.md                   dit bestand
└── lib/
    ├── setup.py                idempotent — maakt test-licenties +
    │                           clients 999/998 aan
    ├── cleanup.py              DELETE's met SELECT-preview + hardstop
    │                           >100 rijen; sequence-reset na DELETE
    ├── api_client.py           mint Flask-session-cookies (SC_SECRET_KEY
    │                           uit /proc/<gunicorn>/environ) en drijft
    │                           de app via HTTP
    └── references.json         verwachte HRV-waardes (B-tests)
```

## Voorbeeld van succesvolle run-output

```
=== pre-flight residu-check ===
[residue_check] {'sc_pro.client_metingen': 0, 'sc_pro.clients': 0,
                 'sc_measurements.metingen': 0, 'saas_licenses.licenses': 0}
[residue_check] totaal: 0

=== setup ===
[setup] license __TEST_LICENSE_CONSUMER__: created
[setup] license __TEST_LICENSE_PRO__: created
[setup] license __TEST_LICENSE_PRO2__: created
[setup] client id=999: created
[setup] client id=998: created

=== categorie A — routing tests ===
[PASS] A1 consumer-meting → sc_measurements.db
[PASS] A2 pro-cliëntmeting client 999 → sc_pro.client_metingen
[PASS] A3 pro eigen meting (client_id=0) → sc_measurements.db
[PASS] A4 REGRESSIE-21-04: A2→A3 in één sessie zonder reset
[PASS] A5 pro wisselcliënt 999→998, geen kruisbestuiving
[PASS] A6 data-isolatie: __TEST2__ ziet meting van __TEST__ niet

categorie A: 6 passed, 0 failed  (0.2s)

=== categorie B — kernberekeningen ===
[PASS] B1 RMSSD op referentie-RR-set
[PASS] B2 RI via Verveen-lookup
[PASS] B3 HRV% (SENSOR_CORRECTION_FACTOR=2.5, age=50, male)
[PASS] B4 zone-indeling op grenswaardes

categorie B: 4 passed, 0 failed  (0.9s)

====================================================
TOTAAL: 10 passed, 0 failed  (2s)
  categorie A (routing):     6/6
  categorie B (berekening):  4/4
====================================================

=== cleanup (trap) ===
[cleanup] ... sequence-reset clients: 999 → 118 ...
[cleanup] totaal verwijderd: 13
```

## Uitbreiden

- Nieuwe routing-test: voeg een `aN_...()` functie toe aan
  `check_routing.py` en regel het op in `TESTS`.
- Nieuwe berekening-test: voeg een `bN_...()` aan
  `check_calculations.py` toe, en zo nodig een `expected`-veld in
  references.json.
- Nieuwe test-user of -client: specs in `lib/setup.py` aanvullen en het
  bijbehorende WHERE-pad in `lib/cleanup.py` toevoegen (met
  marker-check).

Aanpassingen aan `lib/cleanup.py` die rij-selectie uitbreiden: altijd
eerst met een dummy-rij-test verifiëren dat de DELETE uitsluitend
test-markers raakt. De `_safe_delete`-helper met >100-rijen-hardstop
moet de nieuwe tabel blijven afdekken.
