# Promotie-runbook — ÷2,5-fix + kwaliteits-gate + RI-unificatie (zonder vragenstructuur)

> 🛑 **NOG NIET UITVOEREN.** Dit is een leesbaar draaiboek; Paul beslist de promotie als
> aparte, bewuste stap. Brengt het ÷2,5/gate/RI-pakket van `staging` naar `main`/prod
> **zonder** de basismeting-vragenstructuur (V1-V8).
> Opgesteld 2026-06-08 (read-only voorbereid, getest in wegwerp-worktree). Achtergrond:
> `project_rmssd_div25_open_kwestie`, `MIGRATIE_PLAN_DIV25_VERWIJDEREN.md`, `KWALITEITS_GATE_ONTWERP.md`.

## Scope & uitgangspunten

- **Prod = `main` @ `84a06a5`** (worktree `/opt/stresschecker`, service `stresschecker.service` :8080).
- **Bron = `staging` @ `e50d7f1`** (worktree `/opt/stresschecker-staging`).
- **Bewezen:** het pakket is functioneel onafhankelijk van de vragenstructuur (leest geen
  vraag-veld); de vragenstructuur-commits worden NIET meegenomen.
- **Mechanisme = cherry-pick** (geen hele-bestand-kopie — 4 bestanden bevatten op staging
  óók vragenstructuur-code: `app.py`, `analytics.py`, `kwadrant.html`, `sensor_en_meten.html`).
- **Twee losse, expliciete stappen:** (A) code-promotie via cherry-pick; (B) prod-DB-migratie
  (data, ná de code). B is GEEN commit.

## De 8 commits (chronologische cherry-pick-volgorde)

Volgorde is essentieel — chronologisch toepassen geeft een vrijwel conflictvrije pick
(de twee prerequisites brengen de cache-bump-`?v=`-keten en de zone-grenzen mee):

| # | commit | rol |
|---|---|---|
| 1 | `e667e63` | fix: results-stipkleur canonieke zone (prerequisite) |
| 2 | `2b75d4e` | fix: `getColor()` grenzen 2/4/6/8 = getLabel (prerequisite; bevat ook `?v=`-bump) |
| 3 | `eee5ea1` | ÷2,5-factor verwijderd + cache-bump |
| 4 | `d044e78` | kwaliteits-gate v1 (kwadrant RI/zone + baseline) |
| 5 | `b9b03ea` | kwaliteits-gate v2 (stip/naald grijzen + per-meting-lijsten) |
| 6 | `e1b299f` | kwadrant — één RI-systeem-van-record (cur.ri) |
| 7 | `9c27790` | kwaliteits-gate v3 (lijsten A/B + centrale aggregaat-uitsluiting) |
| 8 | `e50d7f1` | .gitignore — `reports/` → `/reports/` |

**Bewust NIET meegenomen** (geen onderdeel van het pakket): de vragenstructuur
(`3486a55`, `aff59cc`, `3fb54f2`, `82d2d80`, `d801bd2`), `6ed3bf8` (dev-login-bypass — prod
heeft dit al via `84a06a5`), `3a40712` (seed-test), `d86be2c`/`25a8205` (kleine UX-teksten;
optioneel later). Het overslaan hiervan gaf in de test geen conflicten.

## Verwachte conflicten (uit wegwerp-test, chronologische volgorde)

Slechts **2, beide niet-code**, bij commit 1 (`e667e63`):
- **`CHANGELOG.md`** (1 blok) → neem staging-versie (`git checkout --theirs CHANGELOG.md`).
- **`tests/smoke_js_syntax.py`** (tree-conflict; bestaat nog niet op main) → neem staging-versie
  (`git checkout --theirs`) — het is een test-helper, prod-functioneel neutraal.

Alle overige 7 commits passen **schoon** toe. (De eerder gevreesde cache-bump-conflicten
verdwijnen doordat `2b75d4e` de `?v=`-keten meebrengt vóór `eee5ea1`.)

---

## STAP 0 — Prod-backup (ALLEREERST, verplicht)

```
/opt/stresschecker/backup.sh          # kopieert app.py/templates/static + alle 3 DB's naar /opt/backups/*.<datum>
# Extra, expliciet voor DB-rollback van de migratie (stap B):
TS=$(date +%Y%m%d-%H%M%S)
cp /opt/stresschecker/data/sc_measurements.db /opt/backups/prepromo-sc_measurements.$TS.db
cp /opt/stresschecker/data/sc_pro.db          /opt/backups/prepromo-sc_pro.$TS.db
# Code-rollback-anker:
cd /opt/stresschecker && git tag prepromo-div25-$TS main
```
Noteer de tagnaam en de DB-backup-paden — die heb je voor rollback.

## STAP A — Code-promotie (cherry-pick op main)

> Werk in de prod-worktree `/opt/stresschecker` op `main`. Werkboom moet schoon zijn
> (`git status` leeg) vóór je begint.

```
cd /opt/stresschecker
git status --short                     # MOET leeg zijn; zo niet: stash/commit eerst, NIET doorgaan
git cherry-pick e667e63 2b75d4e eee5ea1 d044e78 b9b03ea e1b299f 9c27790 e50d7f1
```
Bij de stop op `e667e63` (conflict):
```
git checkout --theirs CHANGELOG.md tests/smoke_js_syntax.py
git add CHANGELOG.md tests/smoke_js_syntax.py
git -c core.editor=true cherry-pick --continue
```
De resterende commits lopen door zonder stop. Eindcontrole:
```
git log --oneline -9                   # 8 nieuwe commits boven 84a06a5
git status --short                     # leeg
```
Commit-identity: niet nodig (cherry-pick behoudt de auteur); committen gebeurt automatisch.

### A-validatie (vóór reload)
```
python3 -c "import ast; ast.parse(open('app.py').read()); ast.parse(open('analytics.py').read()); print('py OK')"
node --check static/js/hrv.js
# JS-syntax 3 talen (na template-JS-wijziging, verplicht):
python3 tests/smoke_js_syntax.py       # verwacht: alle PASS
# Jinja-rapporten parsen:
python3 -c "from jinja2 import Environment,FileSystemLoader as L; e=Environment(loader=L('templates')); [e.get_template('reports/'+t) for t in ['_macros.html','base.html','kk_office.html','kk_overall.html','pro_client.html','pro_portfolio.html']]; print('jinja OK')"
```
Controleer dat de geserveerde `hrv.js` geen `/2.5` meer heeft en `riConfidence` bevat:
```
grep -c '/2\.5' static/js/hrv.js       # 0
grep -c 'riConfidence' static/js/hrv.js # >=2
```

### A-reload
```
kill -HUP $(systemctl show stresschecker.service -p MainPID --value)
sleep 3 && curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8080/login   # 200
```
> Let op cache-bump: `hrv.js?v=` is door de pick opgehoogd; controleer dat de geserveerde
> versie de nieuwe is en houd rekening met de service-worker-cache (zie `project_sw_cache_followup`).

## STAP B — Prod-DB-migratie (DATA — expliciet ná de code, GEEN commit)

> De code rekent na promotie ÷2,5-vrij voor NIEUWE metingen. De BESTAANDE opgeslagen
> RI/HRV%/rmssd staan nog op de oude schaal → eenmalig herberekenen, anders mengt prod oude
> en nieuwe schaal in baseline/trend.

Formule per rij (exact, géén ruwe RR nodig; `import app` VERBODEN — opent DB rechtstreeks):
`hrv_pct = min(220, round(hrv_pct*2,5))` · `rmssd = rmssd*2,5` ·
`ri = lookupRelaxIndex(bpm, hrv_pct_nieuw)` (window-mean-getrouw via `timeseries` waar aanwezig,
anders eindwaarde-fallback). Tabellen B/C/T uit de **gepromote** `static/js/hrv.js`.

1. **Backup is al gemaakt in stap 0.** (Verifieer dat de prepromo-DB-kopieën bestaan.)
2. Schrijf een prod-variant van het migratiescript met **prod-paden**
   (`/opt/stresschecker/data/sc_measurements.db` + `sc_pro.db`) — basis:
   `MIGRATIE_PLAN_DIV25_VERWIJDEREN.md` §2 + het op staging gebruikte script.
3. **Dry-run eerst** (before/after zone-telling tonen, niets schrijven), inspecteer.
4. **Apply** met `--apply`; log before/after per zone op beide tabellen.
5. Verifieer steekproef (bv. een bekende meting): `hrv_pct×2,5`, `ri` her-lookup kloppen.

> De aggregaat-/gate-logica (stap A) leest `kwaliteit` (bestaande kolom) — geen schema-
> wijziging nodig in stap B.

## STAP C — Eindverificatie op prod

- `/kwadrant` bij een bekende meting: getal/gauge/label/stip-ring tonen dezelfde zone;
  lage-kwaliteit-meting toont grijs/"onzeker", geen stellig "Veerkrachtig".
- Een PDF-rapport genereren: zone-% sommeren op 100 en de `quality_note`-regel verschijnt
  als er lage-kwaliteit-metingen zijn.
- `run_all.sh`/relevante tests groen.

---

## ROLLBACK-procedure

**Code terug:**
```
cd /opt/stresschecker
git reset --hard prepromo-div25-<TS>          # de tag uit stap 0
kill -HUP $(systemctl show stresschecker.service -p MainPID --value)
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8080/login   # 200
```
(Alternatief, als er ná promotie al nieuwe prod-commits boven staan: `git revert` de 8
cherry-picks in omgekeerde volgorde i.p.v. reset.)

**Data terug (alleen als stap B al gedraaid was):**
```
systemctl stop stresschecker.service          # voorkom schrijven tijdens restore
cp /opt/backups/prepromo-sc_measurements.<TS>.db /opt/stresschecker/data/sc_measurements.db
cp /opt/backups/prepromo-sc_pro.<TS>.db          /opt/stresschecker/data/sc_pro.db
systemctl start stresschecker.service
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8080/login   # 200
```
**Volgorde bij volledige rollback:** eerst data terug (DB-restore), dan code terug — zodat de
herstelde oude-schaal-DB met de oude-schaal-code draait. (Oude code + nieuwe-schaal-DB = scheef.)

**Cache-kanttekening:** browsers kunnen de nieuwe `hrv.js?v=` gecached hebben; bij rollback
keert het oude `?v=` terug en herladen ze vanzelf. Service-worker eventueel forceren.

## Niet-blokkerende vervolgpunten (na promotie, los)
- Klantcommunicatie: RI-waarden stijgen zichtbaar (schaal-fix) — vooral KKH/PI en bestaande baselines.
- Losse opruimpunten: `pro/dashboard_kk` recent-tabel (kale RI), `weekly_email` (gebruikt aggregaten niet).
- Geparkeerd: biofeedback `displayRi` op `getRaw`; window-mean-vs-eindwaarde RI-definitie.
