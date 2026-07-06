#!/usr/bin/env python3
"""Event-modus — individueel momentopname-rapport (Fase 3).

Genereert per meting-code een persoonlijk PDF-rapport (zone-eerst, OP NAAM, met de
meting-code als meelopende identifier). Eén meetmoment — GEEN baseline/trend.

Hergebruikt de bestaande, bewezen logica:
  - RI→zone via analytics.zone_for_ri / zone_label / ZONE_DESCRIPTIONS (GEEN nieuwe berekening)
  - de WeasyPrint-pijplijn (zelfde library/patroon als de Pro/KK-rapporten)
Leest UITSLUITEND sc_event.db (read-only). Importeert app.py NIET (geen schema-side-effect).
Raakt de bestaande consument-/Pro-rapportage niet aan (eigen template + eigen CLI).

DB-pad: SC_EVENT_DB (env) of anders de prod-default — identiek aan app.py's EVENT_DB_PATH.
Event-modus draait sinds 2026-06-23 live op prod; de eerdere staging-only-grendel is vervallen.

Gebruik:
    python3 event_report.py --meting-code M-50B004
    python3 event_report.py --meting-code M-50B004 --lang de --out /tmp/rapport.pdf
"""
import argparse
import math
import os
import sqlite3
import sys
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB = '/opt/stresschecker/data/sc_event.db'
RELIABLE_MIN = 95  # Fase 3: klasse 'betrouwbaar'-grens (= analytics.QUALITY_TIER_BETROUWBAAR_MIN, ≤5% gecorrigeerd)
# Boven deze HRV% is het signaal vrijwel altijd vertekend: ectopische slagen of
# bewegingsartefacten blazen RMSSD (en daarmee de HRV%) kunstmatig op. Zo'n meting mag
# nooit als volledig betrouwbaar (★★★) gepresenteerd worden → aftoppen op ★★ + waarschuwing.
HRV_PCT_MAX_TRUSTED = 160

sys.path.insert(0, PROJECT_ROOT)
import analytics  # noqa: E402  (pure module — geen side-effects)


T = {
    'nl': {
        'title': 'Persoonlijk meetrapport', 'tag': 'Momentopname',
        'code_label': 'Meting-code', 'no_name': '(geen naam)',
        'code_keep': 'Bewaar deze code voor een vervolgmeting.',
        'measured_at': 'Gemeten', 'age': 'Leeftijd', 'ri_label': 'Relax Index',
        'bpm': 'Hartslag', 'quality': 'Kwaliteit',
        'unreliable': 'De signaalkwaliteit was te laag voor een betrouwbare Relax Index. '
                      'De zone is indicatief; overweeg een nieuwe meting.',
        'unreliable_zone_heading': 'Onzeker — meting onbetrouwbaar',
        'unreliable_zone_desc': 'De signaalkwaliteit was te laag voor een betrouwbaar resultaat. '
                                'Deze indicatie is onzeker; overweeg een nieuwe, rustige meting.',
        # Voltooid (>=2 metingen, geen nieuwe meting meer mogelijk) — neutraal, geen
        # gezondheidsconclusie, verwijzing naar de begeleider (aansluitend op de kiosk-slotboodschap).
        'unreliable_zone_desc_completed': 'De signaalkwaliteit was te laag voor een betrouwbaar resultaat. '
                                'Dat zegt niets over jou — vaak komt het door koude handen, beweging of de sensor.',
        'unreliable_completed': 'Vandaag lukte geen betrouwbare meting. Vraag je begeleider om hulp.',
        'gauge_cap_unreliable': 'Richtwaarde',
        'hrv_warning': 'De gemeten HRV% is uitzonderlijk hoog. Dit duidt meestal op een vertekend '
                       'signaal (bv. onregelmatige slagen of beweging). De meetkwaliteit is daarom '
                       'afgetopt op ★★; beschouw dit resultaat met voorbehoud.',
        'method': 'De Relax Index (RI, 0–10) is berekend uit één meting van hartslag en '
                  'hartritmevariabiliteit (HRV/RMSSD) van het autonome zenuwstelsel, '
                  'genormaliseerd naar leeftijd en geslacht. Dit is een momentopname, geen verloop.',
        'generated': 'Gegenereerd', 'snapshot_note': 'Eén meetmoment — geen baseline of trend.',
        'demo_note': 'Demonstratie · gesimuleerd signaal — dit rapport laat zien hoe StressChecker werkt en is geen echte hartslagmeting.',
        'gender': {'male': 'Man', 'female': 'Vrouw', 'other': 'Anders'},
    },
    'de': {
        'title': 'Persönlicher Messbericht', 'tag': 'Momentaufnahme',
        'code_label': 'Mess-Code', 'no_name': '(kein Name)',
        'code_keep': 'Bewahren Sie diesen Code für eine Folgemessung auf.',
        'measured_at': 'Gemessen', 'age': 'Alter', 'ri_label': 'Relax Index',
        'bpm': 'Herzfrequenz', 'quality': 'Qualität',
        'unreliable': 'Die Signalqualität war zu niedrig für einen zuverlässigen Relax Index. '
                      'Die Zone ist orientierend; ggf. erneut messen.',
        'unreliable_zone_heading': 'Unsicher — keine zuverlässige Messung',
        'unreliable_zone_desc': 'Die Signalqualität war zu niedrig für ein zuverlässiges Ergebnis. '
                                'Diese Indikation ist unsicher; erwägen Sie eine neue, ruhige Messung.',
        # Abgeschlossen (>=2 Messungen, keine neue Messung mehr möglich) — neutral, keine
        # Gesundheitsaussage, Verweis auf die Begleitung (passend zur Kiosk-Schlussmeldung).
        'unreliable_zone_desc_completed': 'Die Signalqualität war zu niedrig für ein zuverlässiges Ergebnis. '
                                'Das sagt nichts über Sie aus — oft liegt es an kalten Händen, Bewegung oder dem Sensor.',
        'unreliable_completed': 'Heute war keine zuverlässige Messung möglich. Bitte wenden Sie sich an Ihre Begleitung.',
        'gauge_cap_unreliable': 'Richtwert',
        'hrv_warning': 'Die gemessene HRV% ist außergewöhnlich hoch. Das deutet meist auf ein '
                       'verzerrtes Signal hin (z. B. unregelmäßige Schläge oder Bewegung). Die '
                       'Messqualität wurde daher auf ★★ begrenzt; bitte mit Vorbehalt betrachten.',
        'method': 'Der Relax Index (RI, 0–10) wird aus einer Messung von Herzfrequenz und '
                  'Herzratenvariabilität (HRV/RMSSD) des autonomen Nervensystems berechnet, '
                  'normiert nach Alter und Geschlecht. Dies ist eine Momentaufnahme, kein Verlauf.',
        'generated': 'Erstellt', 'snapshot_note': 'Ein Messzeitpunkt — keine Baseline oder Trend.',
        'demo_note': 'Demonstration · simuliertes Signal — dieser Bericht zeigt, wie StressChecker funktioniert, und ist keine echte Herzschlagmessung.',
        'gender': {'male': 'Mann', 'female': 'Frau', 'other': 'Divers'},
    },
    'en': {
        'title': 'Personal measurement report', 'tag': 'Snapshot',
        'code_label': 'Measurement code', 'no_name': '(no name)',
        'code_keep': 'Keep this code for a follow-up measurement.',
        'measured_at': 'Measured', 'age': 'Age', 'ri_label': 'Relax Index',
        'bpm': 'Heart rate', 'quality': 'Quality',
        'unreliable': 'Signal quality was too low for a reliable Relax Index. '
                      'The zone is indicative; consider a new measurement.',
        'unreliable_zone_heading': 'Uncertain — unreliable measurement',
        'unreliable_zone_desc': 'Signal quality was too low for a reliable result. '
                                'This indication is uncertain; consider a new, calm measurement.',
        # Completed (>=2 measurements, no new measurement possible) — neutral, no health
        # conclusion, referral to the facilitator (matching the kiosk closing message).
        'unreliable_zone_desc_completed': 'Signal quality was too low for a reliable result. '
                                "That doesn't say anything about you — it's often due to cold hands, movement or the sensor.",
        'unreliable_completed': 'No reliable measurement was possible today. Please ask your facilitator for help.',
        'gauge_cap_unreliable': 'Estimate',
        'hrv_warning': 'The measured HRV% is exceptionally high. This usually indicates a distorted '
                       'signal (e.g. irregular beats or movement). Measurement quality has therefore '
                       'been capped at ★★; please treat this result with caution.',
        'method': 'The Relax Index (RI, 0–10) is calculated from a single measurement of heart rate '
                  'and heart rate variability (HRV/RMSSD) of the autonomic nervous system, '
                  'normalized by age and gender. This is a snapshot, not a trend.',
        'generated': 'Generated', 'snapshot_note': 'Single measurement — no baseline or trend.',
        'demo_note': 'Demonstration · simulated signal — this report shows how StressChecker works and is not a real heart-rate measurement.',
        'gender': {'male': 'Male', 'female': 'Female', 'other': 'Other'},
    },
}


GAUGE_HEADING = {
    'nl': 'Positie op de belasting–herstelschaal',
    'de': 'Position auf der Belastungs–Erholungsskala',
    'en': 'Position on the strain–recovery scale',
}


GEVOEL_METING = {
    'nl': {
        'heading': 'Gevoel en meting naast elkaar',
        'feeling': 'Gevoel', 'measurement': 'Meting (RI)',
        'intro': 'Dit rapport toont twee bronnen: je gevoel — hoe ontspannen je je vóór de meting '
                 'voelde — en de meting — wat je hartritme tijdens de meting liet zien. Ze belichten '
                 'elk een andere kant en lopen soms uiteen. Geen van beide is "fout".',
        'higher': 'Je voelde je op dit moment meer ontspannen dan je hartritme liet zien. Dat komt '
                  'vaker voor: je beleving en je autonome zenuwstelsel lopen niet altijd gelijk op. '
                  'Beide kloppen — ze beschrijven elk iets anders.',
        'lower': 'Je voelde je op dit moment minder ontspannen dan je hartritme liet zien. Ook dat '
                 'komt vaker voor: je beleving en je autonome zenuwstelsel lopen niet altijd gelijk op. '
                 'Beide kloppen — ze beschrijven elk iets anders.',
        'equal': 'Je gevoel en de meting liggen dicht bij elkaar. Hoe ontspannen je je voelde komt op '
                 'dit moment overeen met wat je hartritme liet zien. De twee bronnen wijzen nu in '
                 'dezelfde richting.',
        'unreliable': 'De meting was te onzeker voor een vergelijking.',
        'irregular': 'Deze vergelijking is onbetrouwbaar — je meting was te onregelmatig.',
    },
    'de': {
        'heading': 'Gefühl und Messung nebeneinander',
        'feeling': 'Gefühl', 'measurement': 'Messung (RI)',
        'intro': 'Dieser Bericht zeigt zwei Quellen: Ihr Gefühl — wie entspannt Sie sich vor der '
                 'Messung fühlten — und die Messung — was Ihr Herzrhythmus während der Messung zeigte. '
                 'Beide beleuchten eine andere Seite und gehen manchmal auseinander. Keine von beiden '
                 'ist „falsch".',
        'higher': 'Sie fühlten sich in diesem Moment entspannter, als Ihr Herzrhythmus zeigte. Das '
                  'kommt häufiger vor: Ihr Empfinden und Ihr autonomes Nervensystem gehen nicht immer '
                  'Hand in Hand. Beide sind richtig — sie beschreiben jeweils etwas anderes.',
        'lower': 'Sie fühlten sich in diesem Moment weniger entspannt, als Ihr Herzrhythmus zeigte. '
                 'Auch das kommt häufiger vor: Ihr Empfinden und Ihr autonomes Nervensystem gehen nicht '
                 'immer Hand in Hand. Beide sind richtig — sie beschreiben jeweils etwas anderes.',
        'equal': 'Ihr Gefühl und die Messung liegen nahe beieinander. Wie entspannt Sie sich fühlten, '
                 'entspricht in diesem Moment dem, was Ihr Herzrhythmus zeigte. Die beiden Quellen '
                 'weisen jetzt in dieselbe Richtung.',
        'unreliable': 'Die Messung war zu unsicher für einen Vergleich.',
        'irregular': 'Dieser Vergleich ist unzuverlässig — Ihre Messung war zu unregelmäßig.',
    },
    'en': {
        'heading': 'Feeling and measurement side by side',
        'feeling': 'Feeling', 'measurement': 'Measurement (RI)',
        'intro': 'This report shows two sources: your feeling — how relaxed you felt before the '
                 'measurement — and the measurement — what your heart rhythm showed during the '
                 'measurement. Each highlights a different side, and they sometimes differ. Neither one '
                 'is "wrong".',
        'higher': 'You felt more relaxed at this moment than your heart rhythm showed. This is common: '
                  'your experience and your autonomic nervous system don\'t always move in step. Both '
                  'are right — each describes something different.',
        'lower': 'You felt less relaxed at this moment than your heart rhythm showed. This too is '
                 'common: your experience and your autonomic nervous system don\'t always move in step. '
                 'Both are right — each describes something different.',
        'equal': 'Your feeling and the measurement are close together. How relaxed you felt matches, at '
                 'this moment, what your heart rhythm showed. The two sources now point in the same '
                 'direction.',
        'unreliable': 'The measurement was too uncertain for a comparison.',
        'irregular': 'This comparison is unreliable — your measurement was too irregular.',
    },
}

GEVOEL_METING_TOL = 2  # |gevoel - RI| <= 2 → "ongeveer gelijk"


def gevoel_meting(subjectief, ri, reliable, lang, irregular=False):
    """Gevoel (subjectief_score 0-10) vs. meting (RI 0-10). Beschrijvend, niet-oordelend.
    Onbetrouwbaar (kwaliteit<85) → neutrale regel; te onregelmatig (quality_band 'slecht')
    → specifieke onregelmatigheid-regel; geen subjectief → blok weglaten."""
    g = GEVOEL_METING.get(lang, GEVOEL_METING['nl'])
    if subjectief is None:
        return {'show': False}
    # Te onregelmatig: aparte, specifiekere boodschap dan de generieke 'te onzeker' (krijgt
    # voorrang). We herhalen het onbetrouwbare RI-getal NIET — consistent met de Onzeker-gate.
    if irregular:
        return {'show': True, 'reliable': False, 'heading': g['heading'], 'text': g['irregular']}
    if not reliable or ri is None:
        return {'show': True, 'reliable': False, 'heading': g['heading'], 'text': g['unreliable']}
    diff = float(subjectief) - float(ri)
    if diff > GEVOEL_METING_TOL:
        key = 'higher'
    elif diff < -GEVOEL_METING_TOL:
        key = 'lower'
    else:
        key = 'equal'
    return {
        'show': True, 'reliable': True, 'case': key,
        'heading': g['heading'], 'intro': g['intro'], 'text': g[key],
        'feeling_label': g['feeling'], 'meas_label': g['measurement'],
        'feeling': int(subjectief), 'measurement': f"{float(ri):.1f}",
    }


# ── Werkstress vs. meting (event-intake work_stress_score 0-10) ──────────────
# Beschrijvend, niet-oordelend — zelfde toon als gevoel_meting. Archetype uit de combinatie
# van werkstress-beleving, ontspanning-beleving en de gemeten RI. GEEN diagnose: de 'onder-
# liggende'-tekst claimt NIET "verborgen stress", maar benoemt het verschil + andere oorzaken.
_WS_RI_HIGH_ZONES = {'in balans', 'veerkrachtig', 'im gleichgewicht', 'vital', 'in balance', 'resilient'}
_WS_STRESS_HIGH, _WS_STRESS_LOW = 7, 3
_WS_COMFORT_HIGH, _WS_COMFORT_LOW = 6, 3

def _ws_ri_is_high(ri):
    if ri is None:
        return None
    if isinstance(ri, str):
        return ri.strip().lower() in _WS_RI_HIGH_ZONES
    try:
        return float(ri) >= 6.0
    except (TypeError, ValueError):
        return None

def classify_werkstress_archetype(werk, ontspa, ri):
    """werkstress (0-10), ontspanning (0-10), ri (numeriek of zone-string) -> archetype-sleutel."""
    if werk is None or ontspa is None:
        return 'default'
    hi = _ws_ri_is_high(ri)
    if werk >= _WS_STRESS_HIGH and ontspa <= _WS_COMFORT_LOW and hi is False:
        return 'congruent_belast'
    if werk <= _WS_STRESS_LOW and ontspa >= _WS_COMFORT_HIGH and hi is True:
        return 'congruent_evenwicht'
    if werk >= _WS_STRESS_HIGH and ontspa >= _WS_COMFORT_HIGH and hi is True:
        return 'dissonantie_resilience'
    if werk <= _WS_STRESS_LOW and ontspa <= _WS_COMFORT_LOW and hi is False:
        return 'dissonantie_onderliggende'
    return 'default'

WERKSTRESS_METING = {
    'nl': {
        'heading': 'Werkstress en meting naast elkaar', 'ws_label': 'Werkstress',
        'congruent_belast': 'Je gaf aan behoorlijk wat werkstress te ervaren, en de meting laat op '
            'dit moment ook een belast beeld zien. Je beleving en je hartritme wijzen nu dezelfde kant op.',
        'congruent_evenwicht': 'Je gaf aan weinig werkstress te ervaren, en de meting laat op dit '
            'moment een ontspannen beeld zien. Je beleving en je hartritme sluiten mooi op elkaar aan.',
        'dissonantie_resilience': 'Je gaf aan werkstress te ervaren, terwijl de meting op dit moment '
            'een relatief kalm beeld laat zien. Je lichaam lijkt de belasting nu goed op te vangen — '
            'beleving en meting belichten elk een andere kant.',
        'dissonantie_onderliggende': 'Je gaf aan weinig werkstress te ervaren, terwijl de meting op dit '
            'moment een wat meer belast beeld laat zien. Zo\'n verschil kan allerlei oorzaken hebben — '
            'denk aan slaap, inspanning vlak vóór de meting, cafeïne of iets anders — en zegt op zichzelf '
            'niets zekers. Het kan een rustig aanknopingspunt zijn om even bij stil te staan.',
        'default': 'Je beleving van werkstress en de meting liggen dicht bij elkaar of geven samen een '
            'gemengd beeld. Geen van beide is "fout" — ze belichten elk een andere kant.',
        'unreliable': 'De meting was te onzeker om naast je werkstress-beleving te leggen.',
        'irregular': 'Deze vergelijking is onbetrouwbaar — je meting was te onregelmatig.',
    },
    'de': {
        'heading': 'Arbeitsstress und Messung nebeneinander', 'ws_label': 'Arbeitsstress',
        'congruent_belast': 'Sie gaben an, spürbar Arbeitsstress zu erleben, und die Messung zeigt in '
            'diesem Moment ebenfalls ein belastetes Bild. Ihr Empfinden und Ihr Herzrhythmus weisen '
            'jetzt in dieselbe Richtung.',
        'congruent_evenwicht': 'Sie gaben an, wenig Arbeitsstress zu erleben, und die Messung zeigt in '
            'diesem Moment ein entspanntes Bild. Empfinden und Herzrhythmus passen gut zusammen.',
        'dissonantie_resilience': 'Sie gaben Arbeitsstress an, während die Messung in diesem Moment ein '
            'relativ ruhiges Bild zeigt. Ihr Körper scheint die Belastung derzeit gut aufzufangen — beide '
            'beleuchten eine andere Seite.',
        'dissonantie_onderliggende': 'Sie gaben wenig Arbeitsstress an, während die Messung in diesem '
            'Moment ein etwas belasteteres Bild zeigt. Ein solcher Unterschied kann viele Ursachen haben '
            '— etwa Schlaf, Anstrengung kurz vor der Messung, Koffein oder anderes — und sagt für sich '
            'genommen nichts Sicheres. Es kann ein ruhiger Anlass sein, kurz innezuhalten.',
        'default': 'Ihr Empfinden von Arbeitsstress und die Messung liegen nahe beieinander oder ergeben '
            'zusammen ein gemischtes Bild. Keine von beiden ist „falsch" — sie beleuchten jeweils eine andere Seite.',
        'unreliable': 'Die Messung war zu unsicher, um sie neben Ihr Arbeitsstress-Empfinden zu legen.',
        'irregular': 'Dieser Vergleich ist unzuverlässig — Ihre Messung war zu unregelmäßig.',
    },
    'en': {
        'heading': 'Work stress and measurement side by side', 'ws_label': 'Work stress',
        'congruent_belast': 'You indicated noticeable work stress, and the reading currently also shows '
            'a strained picture. Your experience and your heart rhythm point the same way right now.',
        'congruent_evenwicht': 'You indicated little work stress, and the reading currently shows a '
            'relaxed picture. Experience and heart rhythm line up well.',
        'dissonantie_resilience': 'You indicated work stress, while the reading currently shows a '
            'relatively calm picture. Your body seems to be absorbing the load well right now — each '
            'highlights a different side.',
        'dissonantie_onderliggende': 'You indicated little work stress, while the reading currently shows '
            'a somewhat more strained picture. Such a difference can have many causes — sleep, exertion '
            'just before the reading, caffeine or something else — and on its own says nothing certain. '
            'It can be a gentle prompt to pause and reflect.',
        'default': 'Your sense of work stress and the reading are close together, or together give a mixed '
            'picture. Neither is "wrong" — each highlights a different side.',
        'unreliable': 'The reading was too uncertain to compare with your sense of work stress.',
        'irregular': 'This comparison is unreliable — your reading was too irregular.',
    },
}

# Alias voor externe validatiescripts die WERKSTRESS_COMMENTARY verwachten.
WERKSTRESS_COMMENTARY = WERKSTRESS_METING

def werkstress_meting(work, ontspa, ri, reliable, lang, irregular=False):
    """Werkstress-beleving (0-10) vs. meting (RI). Beschrijvend blok; geen werkstress -> blok weg."""
    w = WERKSTRESS_METING.get(lang, WERKSTRESS_METING['nl'])
    if work is None:
        return {'show': False}
    if irregular:
        return {'show': True, 'reliable': False, 'heading': w['heading'], 'text': w['irregular']}
    if not reliable or ri is None:
        return {'show': True, 'reliable': False, 'heading': w['heading'], 'text': w['unreliable']}
    arch = classify_werkstress_archetype(work, ontspa, ri)
    return {'show': True, 'reliable': True, 'heading': w['heading'], 'archetype': arch,
            'ws_label': w['ws_label'], 'werkstress': int(work), 'text': w[arch]}


def quality_stars(kwaliteit, hrv_pct=None):
    """Meetkwaliteit → sterren (max 3). Grenzen = riConfidence (85/70), consistent met de
    afkeurlijn (<85). Presentatie-only, GEEN nieuwe berekening:
      >=85 → ★★★ (trusted) · 70-84 → ★★ (limited) · <70 → ★ (untrusted) · ontbrekend → geen rating.
    Extra borg: een extreem hoge HRV% (> HRV_PCT_MAX_TRUSTED) duidt vrijwel altijd op een
    vertekend signaal; dan nooit ★★★ toekennen → aftoppen op ★★ + 'hrv_warning' zetten zodat
    het rapport een waarschuwing kan tonen. Verandert de RI/HRV-berekening niet."""
    try:
        kw = float(kwaliteit) if kwaliteit not in (None, '') else None
    except (TypeError, ValueError):
        kw = None
    try:
        hrv = float(hrv_pct) if hrv_pct not in (None, '') else None
    except (TypeError, ValueError):
        hrv = None
    if kw is None:
        return {'filled': 0, 'total': 3, 'tier': 'onbepaald', 'rated': False, 'hrv_warning': False}
    if kw >= 85:
        res = {'filled': 3, 'total': 3, 'tier': 'trusted', 'rated': True, 'hrv_warning': False}
    elif kw >= 70:
        res = {'filled': 2, 'total': 3, 'tier': 'limited', 'rated': True, 'hrv_warning': False}
    else:
        res = {'filled': 1, 'total': 3, 'tier': 'untrusted', 'rated': True, 'hrv_warning': False}
    # Aftoppen op ★★ (downgrade) bij verdacht hoge HRV% — nooit opwaarderen.
    if hrv is not None and hrv > HRV_PCT_MAX_TRUSTED:
        res['filled'] = min(res['filled'], 2)
        if res['filled'] == 2:
            res['tier'] = 'limited'
        res['hrv_warning'] = True
    return res


def build_gauge(ri, tier):
    """Statische SVG-gauge die de bestaande /kwadrant-gauge spiegelt: 5 zonebanden
    (RI-grenzen 2/4/6/8) met dezelfde kleuren, naald op PI + ri/10·PI. Weerspiegelt de 3
    kwaliteitsklassen (tier, = analytics.quality_tier + ritme-'slecht'): betrouwbaar → volle
    kleur + volle naald; indicatief → GEDEMPTE kleur (opacity) + STIPPEL-naald; onbetrouwbaar
    → grijs + grijze naald. GEEN nieuwe RI/zone-berekening — alleen tekengeometrie."""
    grey = (tier == 'onbetrouwbaar')
    indicatief = (tier == 'indicatief')
    cx, cy, r = 100.0, 104.0, 92.0
    bands = [
        (math.pi,        1.2 * math.pi, '#c0392b'),  # RI 0-2  zwaar belast
        (1.2 * math.pi,  1.4 * math.pi, '#e67e22'),  # RI 2-4  belast
        (1.4 * math.pi,  1.6 * math.pi, '#f1c40f'),  # RI 4-6  licht belast
        (1.6 * math.pi,  1.8 * math.pi, '#82d228'),  # RI 6-8  in balans
        (1.8 * math.pi,  2.0 * math.pi, '#27ae60'),  # RI 8-10 veerkrachtig
    ]
    arcs = []
    for a0, a1, col in bands:
        x0, y0 = cx + r * math.cos(a0), cy + r * math.sin(a0)
        x1, y1 = cx + r * math.cos(a1), cy + r * math.sin(a1)
        arcs.append({
            'd': f'M {x0:.2f} {y0:.2f} A {r:.0f} {r:.0f} 0 0 1 {x1:.2f} {y1:.2f}',
            'color': '#cfcfcf' if grey else col,
            'opacity': 0.4 if indicatief else 1,
        })
    rr = max(0.0, min(10.0, float(ri)))
    ang = math.pi + (rr / 10.0) * math.pi
    needle = {
        'x1': round(cx - math.cos(ang) * 12, 2), 'y1': round(cy - math.sin(ang) * 12, 2),
        'x2': round(cx + math.cos(ang) * (r - 10), 2), 'y2': round(cy + math.sin(ang) * (r - 10), 2),
        'color': '#bbbbbb' if grey else '#333333',
        'dash': '5 4' if indicatief else '',
    }
    return {'cx': cx, 'cy': cy, 'sw': 16, 'arcs': arcs, 'needle': needle}


def _db_path():
    # SC_EVENT_DB (staging zet dit in .env.staging) of anders de prod-default —
    # zelfde resolutie als app.py's EVENT_DB_PATH. Event-modus is live op prod, dus
    # het live-DB-pad is hier nu juist gewenst (geen staging-only-grendel meer).
    return os.environ.get('SC_EVENT_DB', DEFAULT_DB)


def render_report(meting_code, lang='nl', as_html=False, screen_mode=False, back_url=None, print_url=None):
    """Genereer het momentopname-rapport. Standaard → (pdf_bytes, info) via WeasyPrint.
    Met as_html=True → (html_str, info): exact DEZELFDE template als HTML-string, voor de
    responsieve schermweergave; screen_mode/back_url/print_url voeden de scherm-only actiebalk
    (WeasyPrint negeert @media screen, dus de PDF blijft byte-identiek). Leest sc_event.db
    read-only. Raise ValueError bij onbekende code / geen meting. Herbruikbaar vanuit CLI én app.py."""
    code = (meting_code or '').strip().upper()
    if lang not in T:
        lang = 'nl'
    t = T[lang]

    path = _db_path()
    cn = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
    cn.row_factory = sqlite3.Row
    # DOEL B-individueel (afleiden bij read — niets verwijderen/markeren): kies per persoon de
    # MEEST RECENTE GESLAAGDE meting (kwaliteit >= RELIABLE_MIN EN niet 'slecht'-geclassificeerd).
    # Is er geen geslaagde, dan de LAATSTE meting (allemaal afgekeurd → de bestaande onzeker-banner
    # verschijnt vanzelf). NULL-kwaliteit telt als afgekeurd; quality_band 'slecht' (te onregelmatig)
    # diskwalificeert ook bij hoog signaal-%, gelijk aan de has_reliable-gate in app.py.
    # NULL/'onbepaald' quality_band telt wél als geslaagd; gelijke ts wordt op id gebroken.
    row = cn.execute(
        "SELECT p.meting_code, p.name, p.birth_year, p.gender, "
        "       e.event_code, e.opdrachtgever, e.naam AS event_naam, e.datum AS event_datum, "
        "       m.ri, m.bpm, m.hrv_pct, m.rmssd, m.kwaliteit, m.quality_band, m.sensor_type, m.ts, m.created_at, "
        "       m.subjectief_score, m.work_stress_score, "
        "       (SELECT COUNT(*) FROM event_metingen m2 WHERE m2.participant_id = p.participant_id) AS n_metingen "
        "FROM event_participants p "
        "JOIN events e ON e.event_id = p.event_id "
        "LEFT JOIN event_metingen m ON m.participant_id = p.participant_id "
        "WHERE p.meting_code = ? "
        "ORDER BY CASE WHEN m.kwaliteit IS NOT NULL AND m.kwaliteit >= ? "
        "               AND (m.quality_band IS NULL OR m.quality_band <> 'slecht') THEN 1 ELSE 0 END DESC, "
        "         m.ts DESC, m.id DESC "
        "LIMIT 1",
        (code, RELIABLE_MIN)
    ).fetchone()
    cn.close()
    if not row:
        raise ValueError(f'Onbekende meting-code: {code}')
    if row['ri'] is None:
        raise ValueError(f'Nog geen meting voor {code} — kan geen momentopname-rapport maken.')

    p = dict(row)

    # Fase 4: label het rapport als demonstratie zolang het een gesimuleerd signaal is (de event-
    # kiosk heeft geen fysieke sensor). Conditioneel op sensor_type -> verdwijnt vanzelf als er
    # ooit een echte sensor wordt gekoppeld. sensor_type is momenteel altijd 'demo'.
    is_demo = (str(p.get('sensor_type') or '').lower() == 'demo')

    # RI → zone via de canonieke analytics-functies (GEEN eigen berekening).
    zone_key = analytics.zone_for_ri(p['ri'])
    zone_label = analytics.zone_label(zone_key, lang)
    zone_desc = analytics.ZONE_DESCRIPTIONS.get(zone_key, {}).get(lang, '')

    # Onregelmatigheidsgate meegerekend: een 'slecht'-geclassificeerde meting (variant-B
    # qualityClassify, server-side opgeslagen in event_metingen.quality_band) is NOOIT
    # betrouwbaar — ook niet bij hoge signaal-kwaliteit. Door dit in de ENE master-flag te
    # vouwen vallen zone-banner, gauge-kleur, RI-getal, onbetrouwbaar-advies en gevoel-vs-meting
    # consistent terug op de 'Onzeker'-weergave (geen halve PDF: grijze banner + gekleurde gauge).
    reliable = (p['kwaliteit'] is not None and p['kwaliteit'] >= RELIABLE_MIN
                and (p['quality_band'] or '') != 'slecht')
    # Gauge-KLEUR volgt de 3 kwaliteitsklassen (los van de binaire reliable-vlag die de tekst/
    # zone-banner stuurt): ritme-'slecht' → grijs; anders canonieke quality_tier(kwaliteit).
    # NB: 90-94% (indicatief) wordt hierdoor GEDEMPT getoond i.p.v. grijs — bewuste consistentie
    # met /kwadrant. De reliable-vlag (en dus de "Richtwaarde"-caption + zone-banner) blijft.
    gauge_tier = ('onbetrouwbaar' if (p['quality_band'] or '') == 'slecht'
                  else analytics.quality_tier(p['kwaliteit']))
    # Voltooide deelnemer (>=2 metingen → geen nieuwe meting meer mogelijk): bij een AFGEKEURDE
    # meting vervalt het "overweeg een nieuwe meting"-advies; in plaats daarvan een neutrale
    # begeleider-verwijzing (sluit aan op de kiosk-slotboodschap). Hergebruikt de bestaande
    # n_metingen-telling, geen nieuwe DB-logica. Geen effect op een geslaagd rapport (reliable).
    completed = (p.get('n_metingen') or 0) >= 2
    ri_str = f"{float(p['ri']):.1f}"

    # Gemeten-tijdstip uit ts (epoch ms) of created_at.
    measured_at_str = ''
    if p['ts']:
        try:
            measured_at_str = datetime.fromtimestamp(int(p['ts']) / 1000).strftime('%Y-%m-%d %H:%M')
        except (ValueError, OSError):
            measured_at_str = ''
    if not measured_at_str:
        measured_at_str = (p['created_at'] or '')[:16]

    age = None
    if p['birth_year']:
        age = datetime.now().year - int(p['birth_year'])
    gender_label = t['gender'].get((p['gender'] or '').lower()) if p['gender'] else None

    from jinja2 import Environment, FileSystemLoader, select_autoescape
    env = Environment(
        loader=FileSystemLoader(os.path.join(PROJECT_ROOT, 'templates')),
        autoescape=select_autoescape(['html']),
    )
    tmpl = env.get_template('reports/event_participant.html')
    html_str = tmpl.render(
        p=p, t=t, lang=lang,
        zone_key=zone_key, zone_label=zone_label, zone_desc=zone_desc,
        reliable=reliable, completed=completed, ri_str=ri_str, age=age, gender_label=gender_label,
        measured_at_str=measured_at_str,
        gauge=build_gauge(p['ri'], gauge_tier), gauge_heading=GAUGE_HEADING[lang],
        stars=quality_stars(p['kwaliteit'], p['hrv_pct']),
        gm=gevoel_meting(p['subjectief_score'], p['ri'], reliable, lang,
                         irregular=((p['quality_band'] or '') == 'slecht')),
        wm=werkstress_meting(p.get('work_stress_score'), p['subjectief_score'], p['ri'], reliable, lang,
                             irregular=((p['quality_band'] or '') == 'slecht')),
        quad=__import__('event_quadrant').build_quadrant(
            p['bpm'], p['hrv_pct'], p['subjectief_score'], p['ri'], reliable, lang),
        generated_at=datetime.now().strftime('%Y-%m-%d %H:%M'),
        screen_mode=screen_mode, back_url=back_url, print_url=print_url, is_demo=is_demo,
    )

    info = {'name': p['name'], 'code': code, 'event_code': p['event_code'],
            'zone_label': zone_label, 'zone_key': zone_key, 'ri': ri_str,
            'reliable': reliable, 'lang': lang}
    if as_html:
        return html_str, info
    from weasyprint import HTML
    pdf_bytes = HTML(string=html_str, base_url=PROJECT_ROOT).write_pdf()
    return pdf_bytes, info


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--meting-code', required=True, dest='meting_code')
    ap.add_argument('--lang', default='nl', choices=('nl', 'de', 'en'))
    ap.add_argument('--out', default=None, help='PDF-uitvoerpad (default reports/event/<event>/<code>.pdf)')
    args = ap.parse_args()
    try:
        pdf_bytes, info = render_report(args.meting_code, args.lang)
    except ValueError as e:
        sys.exit(str(e))
    out = args.out
    if not out:
        out_dir = os.path.join(PROJECT_ROOT, 'reports', 'event', info['event_code'])
        os.makedirs(out_dir, exist_ok=True)
        out = os.path.join(out_dir, f"{info['code']}.pdf")
    with open(out, 'wb') as f:
        f.write(pdf_bytes)
    print(f"OK rapport: {out}")
    print(f"  naam        : {info['name'] or '(geen naam)'}")
    print(f"  meting-code : {info['code']}")
    print(f"  zone        : {info['zone_label']} ({info['zone_key']})")
    print(f"  RI          : {info['ri']}{'' if info['reliable'] else '  (onbetrouwbaar, kwaliteit < %d%%)' % RELIABLE_MIN}")
    print(f"  taal        : {info['lang']}")


if __name__ == '__main__':
    main()
