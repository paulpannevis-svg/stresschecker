# Opruim-TODO root-level /opt/stresschecker/

Aangemaakt: 21-05-2026 na git init.
Reden: bij git init op 21-05-2026 zijn root-level artefacten geconstateerd die in een latere sessie geadresseerd moeten worden voordat iemand een `git add .` doet die ongewenste bestanden meeneemt.

## Te onderzoeken / op te ruimen

- [ ] `app.py.current` — wat is dit? Oud merge-resultaat? Verplaatsen naar `/opt/backups/` of verwijderen.
- [ ] `app.py.merge_backup` — idem.
- [ ] `saas_licenses.db` in repo-root — moet verplaatst worden naar `data/` of een andere niet-getrackte locatie. **CRITICAL: bevat klantdata + license-keys.**
- [ ] Andere root-level `*.db` bestanden inventariseren (`ic_licenses.db`, `sc_measurements.db`, `sc_pro.db`, `stresschecker.db`).
- [ ] Andere root-level `*.bak` / `*.backup` bestanden inventariseren.
- [ ] `gen_context.py.pre-leerpunt` (geen `.bak`-suffix → niet door huidige ignore gedekt).
- [ ] `seed_anna.py.v1` (idem).
- [ ] `templates_backup_20260224_*` directories — horen niet in source-tree; verplaatsen naar `/opt/backups/`.

## .gitignore-uitbreiding na opruiming

Voeg expliciete patronen toe die ook root-level matchen:

    /*.db
    /*.bak
    /*.backup
    /app.py.*
    /*.current
    /*.merge_backup
    /*.v1
    /templates_backup_*

(Voorloop-`/` zorgt voor root-level match in git, in tegenstelling tot onbeperkte recursive patterns.)

## Verificatie na opruiming

- `git status` moet schoon zijn
- `git ls-files | grep -E '\.(db|bak|backup)$'` moet leeg zijn
- Een test-commit met `git add .` mag GEEN ongewenste bestanden meenemen

Niet vandaag uitvoeren — plannen voor een rustig moment.
