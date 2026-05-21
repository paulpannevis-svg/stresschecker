"""Eval-licenties configuratie — centraal punt.

Centraal punt voor de evaluatielicentie-looptijd in dagen.
Geïmporteerd door:
  - /opt/stresschecker/app.py                            (activatieflow + tier-widget)
  - /opt/ic-license-server/generate_eval_license.py      (code-generatie)

Wijzig de waarde hier en alleen hier — geen kopieën elders. Andere modules
importeren via `from eval_config import EVAL_DURATION_DAYS`.

Reden voor in-code constante i.p.v. een `plans.duration_days`-kolom:
YAGNI + geen ALTER TABLE op live productie-DB zonder concrete
flexibiliteits-eis. Als ooit per-plan variabele duraties nodig zijn:
ALTER TABLE plans ADD COLUMN duration_days INTEGER NULL en deze constante
laten verwijzen naar een fallback voor NULL-rijen.
"""

EVAL_DURATION_DAYS = 90
