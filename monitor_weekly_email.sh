#!/usr/bin/env bash
# Monitor van de wekelijkse-mail-run (cron ma 08:00). Draait ma 08:05.
# READ-ONLY: leest alleen het log + best-effort SendGrid; schrijft enkel een rapport.
set -uo pipefail

LOG=/var/log/weekly_email.log
ENV_FILE=/opt/stresschecker/.env
REPORT_DIR=/opt/stresschecker/reports
TODAY=$(date +%Y-%m-%d)
TS=$(date +%Y%m%d-%H%M%S)
REPORT="$REPORT_DIR/weekly_email_monitor_$(date +%Y%m%d).txt"
mkdir -p "$REPORT_DIR"

# Verwachte ontvangers. Label is INFORMATIEF (overzicht/nudge kan legitiem wisselen
# met meetactiviteit); harde eis is: 3 verzonden naar deze 3 adressen, geen Fout.
declare -A EXPECT=(
  ["paulpannevis@lifestylemonitors.com"]="overzicht (Patroon)"
  ["klantenservice@wellvit.nl"]="nudge"
  ["stevenpannevis@lifestylemonitors.com"]="nudge"
)

{
  echo "=== Weekly-email monitor — $TS ==="; echo

  if [[ ! -f "$LOG" ]]; then
    echo "RESULTAAT: FAAL — logbestand $LOG bestaat niet."; echo "Rapport: $REPORT"; exit 0
  fi

  # Guard: draaide de mail-cron vanochtend? (log voor het laatst gewijzigd vandaag?)
  LOG_MDATE=$(date -r "$LOG" +%Y-%m-%d)
  [[ "$LOG_MDATE" != "$TODAY" ]] && {
    echo "WAARSCHUWING — log laatst gewijzigd op $LOG_MDATE, niet vandaag ($TODAY)."
    echo "De wekelijkse-mail-cron lijkt vanochtend NIET gedraaid te hebben. Controleer handmatig."; echo
  }

  # Laatste run-blok isoleren (vanaf na de voorlaatste 'Klaar:' tot de laatste regel)
  BLOCK=$(tac "$LOG" | awk '/Klaar:/{k++} k>=2{exit} {print}' | tac)
  echo "--- Laatste run-blok ---"; echo "$BLOCK"; echo "------------------------"; echo

  KLAAR=$(echo "$BLOCK" | grep -E "Klaar: [0-9]+ emails verzonden" | tail -1)
  N=$(echo "$KLAAR" | grep -oE "[0-9]+" | head -1)
  echo "Samenvatting: ${KLAAR:-<ontbreekt>}"; echo

  FAIL=0
  echo "Per ontvanger:"
  for email in "${!EXPECT[@]}"; do
    line=$(echo "$BLOCK" | grep -E "verzonden: ${email//./\\.}$" || true)
    if [[ -n "$line" ]]; then
      echo "  OK   $email -> '$(echo "$line" | sed -E 's/ verzonden:.*//')' (verwacht: ${EXPECT[$email]})"
    else
      echo "  FAAL $email -> GEEN 'verzonden:'-regel (verwacht: ${EXPECT[$email]})"; FAIL=1
    fi
  done; echo

  FOUTEN=$(echo "$BLOCK" | grep -E "^Fout " || true)
  [[ -n "$FOUTEN" ]] && { echo "VERZENDFOUTEN:"; echo "$FOUTEN"; FAIL=1; echo; }

  echo "Overgeslagen (filters):"
  echo "$BLOCK" | grep -E "Overgeslagen \(" | sed 's/^/  /' || echo "  (geen)"; echo

  if [[ "$N" == "3" && "$FAIL" == "0" ]]; then
    echo "LOG-OORDEEL: GESLAAGD — 3 mails verzonden naar de 3 verwachte ontvangers."
  else
    echo "LOG-OORDEEL: AANDACHT — verwacht N=3 zonder fouten; gevonden N=${N:-?}, fail=$FAIL."
  fi; echo

  # Best-effort SendGrid Activity (add-on gaf bij bouw 403 -> waarschijnlijk niet beschikbaar)
  echo "--- SendGrid Activity (best-effort) ---"
  KEY=$(sed -nE 's/^SENDGRID_API_KEY=//p' "$ENV_FILE" | head -1 | sed -E 's/^"//; s/"$//')
  if [[ -z "$KEY" ]]; then
    echo "BEZORGING/BOUNCE: NIET geverifieerd — geen SENDGRID_API_KEY. Controleer dashboard handmatig."
  else
    HTTP=$(curl -s -o /tmp/sg_$$ -w "%{http_code}" -H "Authorization: Bearer $KEY" \
           "https://api.sendgrid.com/v3/messages?limit=1")
    if [[ "$HTTP" == "200" ]]; then
      echo "Activity API beschikbaar — bezorgstatus per ontvanger:"
      for email in "${!EXPECT[@]}"; do
        q=$(python3 -c "import urllib.parse;print(urllib.parse.quote('to_email=\"$email\"'))")
        st=$(curl -s -H "Authorization: Bearer $KEY" \
             "https://api.sendgrid.com/v3/messages?limit=5&query=$q" \
             | python3 -c "import sys,json;d=json.load(sys.stdin);m=d.get('messages',[]);print(m[0]['status'] if m else 'geen activiteit')" 2>/dev/null || echo "parse-fout")
        echo "  $email -> $st"
      done
      echo "(delivered=bezorgd; bounce/dropped=probleem.)"
    else
      echo "BEZORGING/BOUNCE: NIET automatisch geverifieerd (Activity API HTTP $HTTP; geen 'Email Activity'-add-on)."
      echo ">>> ACTIE: controleer bounces handmatig in het SendGrid-dashboard (Activity Feed)."
    fi
    rm -f /tmp/sg_$$
  fi
  echo; echo "Rapport opgeslagen: $REPORT"
} | tee "$REPORT"
