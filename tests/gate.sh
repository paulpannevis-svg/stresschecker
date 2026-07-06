#!/bin/bash
# gate.sh — side-effect-VRIJE pipeline-consistentiepoort.
#
# Draait UITSLUITEND de categorieën die GEEN prod-DB muteren en GEEN `import app` doen:
#   E = test_pipeline_parity.py   (RI/zone/quality parity SC·Pro·Event, laadt hrv.js via node)
#   F = test_pro_trend_threshold.py (pro-trend-drempel, AST-source-inspectie)
# BEWUST NIET de volle run_all.sh: categorieën A-D draaien setup.py en schrijven test-
# data in de prod-DB's (met cleanup-trap) — ongeschikt als lichte deploy-poort.
#
# Exit 0 = pipeline consistent, 1 = divergentie, 2 = kan niet toetsen (node ontbreekt).
# Gebruikt door .git/hooks/pre-commit én reload.sh. Vereist `node` op PATH (categorie E).
set -u
cd /opt/stresschecker/tests || { echo "gate: tests-dir niet gevonden" >&2; exit 2; }

command -v node >/dev/null 2>&1 || {
  echo "GATE KAN NIET TOETSEN: 'node' ontbreekt op PATH (categorie E laadt hrv.js via node)." >&2
  exit 2
}

rc=0
echo "=== gate: categorie E — cross-pipeline parity (RI/zone/quality) ==="
python3 test_pipeline_parity.py || rc=1
echo
echo "=== gate: categorie F — pro-trend-drempel (gedeelde 0,3) ==="
python3 test_pro_trend_threshold.py || rc=1
echo
if [ "$rc" -ne 0 ]; then
  echo "GATE ROOD: pipeline-divergentie — zie hierboven. Niets doorgezet." >&2
else
  echo "GATE GROEN: pipeline consistent (E+F)."
fi
exit $rc
