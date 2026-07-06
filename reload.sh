#!/bin/bash
# reload.sh — VEILIGE template/code-reload van de StressChecker-app.
#
# Draait eerst de side-effect-vrije pipeline-gate (parity E + pro-trend F) en HUPt de
# gunicorn app-masters ALLEEN bij groen. Vervangt de kale `kill -HUP <pid>` — dít is het
# echte go-live-moment voor templates, dus de vangnet hoort hier te bijten.
#
# Gebruik:
#   bash reload.sh          # gate -> bij groen: HUP alle app:app-masters
#   bash reload.sh --dry    # gate + toon welke masters ge-HUP't zouden worden (GEEN HUP)
#   bash reload.sh --force  # sla de gate over (noodgeval) en HUP direct
set -u

DRY=0; FORCE=0
for a in "$@"; do
  case "$a" in
    --dry)   DRY=1 ;;
    --force) FORCE=1 ;;
    *) echo "onbekende optie: $a (gebruik --dry / --force)" >&2; exit 2 ;;
  esac
done

if [ "$FORCE" -ne 1 ]; then
  if ! /opt/stresschecker/tests/gate.sh; then
    echo >&2
    echo "RELOAD AFGEBROKEN: gate rood — er is NIETS ge-HUP't." >&2
    echo "Fix de divergentie, of gebruik 'bash reload.sh --force' in een noodgeval." >&2
    exit 1
  fi
  echo
else
  echo "[--force] gate overgeslagen."
fi

# App-masters: gunicorn-processen die app:app draaien en zelf master zijn (ppid==1),
# exclusief de losse ic-license-server. Zelfde detectie als handmatig deze sessie.
MASTERS=$(ps -eo pid,ppid,args | grep -E "gunicorn.*app:app" | grep -v grep \
          | grep -viE "ic-license" | awk '$2==1{print $1}')
if [ -z "$MASTERS" ]; then
  echo "Geen app:app gunicorn-masters gevonden — niets te reloaden." >&2
  exit 1
fi

echo "App-masters:"
for m in $MASTERS; do echo "  $m -> $(ps -o args= -p "$m" | cut -c1-80)"; done

if [ "$DRY" -eq 1 ]; then
  echo "[--dry] zou HUP sturen naar: $MASTERS (niets gedaan)."
  exit 0
fi

# shellcheck disable=SC2086
kill -HUP $MASTERS && echo "Reload (HUP) verstuurd naar: $MASTERS"
