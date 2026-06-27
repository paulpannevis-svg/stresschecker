import sqlite3
import sys

# DB-pad als argument: draai eerst staging, dan prod.
#   python3 import_kenniscentrum_direct.py /opt/stresschecker-staging/data/sc_measurements.db
#   python3 import_kenniscentrum_direct.py            # default = prod
DB_PATH = sys.argv[1] if len(sys.argv) > 1 else '/opt/stresschecker/data/sc_measurements.db'

# Alinea's bewaard als \n\n — NIET platgeslagen.
articles = [
    {
        'num': 1,
        'audience': 'consumer',
        'title_nl': 'Stabiele meting — hoe zorg je ervoor?',
        'title_de': 'Stabile Messung — wie sorgen Sie dafür?',
        'title_en': 'Stable Measurement — How to Ensure It?',
        'body_nl': 'Een stabiele meting is cruciaal voor nauwkeurige resultaten. Hartritme-variabiliteit kan schommelen door externe factoren.\n\n1. Zit comfortabel: Kies een stoel met goed rugsteun. Zorg dat je voeten plat op de grond staan.\n2. Rust uit: Meet niet direct na inspanning, stressvolle momenten, of cafeïne. Wacht minstens 5 minuten.\n3. Rustige omgeving: Vermijd lawaai, felle lichten en afleiding.\n4. Adem normaal: Probeer niet bewust je ademhaling te controleren — adem natuurlijk.\n5. Contact: Zorg voor goed contact met de sensor (vingers, pols, oor).\n6. Herhaal als nodig: Krijg je een waarschuwing? Zit even uit en probeer opnieuw.',
        'body_de': 'Eine stabile Messung ist entscheidend für genaue Ergebnisse. Die Herzfrequenzvariabilität kann durch externe Faktoren schwanken.\n\n1. Sitzen Sie bequem: Wählen Sie einen Stuhl mit guter Rückenlehne. Achten Sie darauf, dass Ihre Füße flach auf dem Boden stehen.\n2. Ruhen Sie sich aus: Messen Sie nicht unmittelbar nach körperlicher Anstrengung, stressigen Momenten oder Koffeinkonsum. Warten Sie mindestens 5 Minuten.\n3. Ruhige Umgebung: Vermeiden Sie Lärm, grelle Lichter und Ablenkung.\n4. Atmen Sie normal: Versuchen Sie nicht, Ihre Atmung bewusst zu kontrollieren — atmen Sie natürlich.\n5. Kontakt: Stellen Sie sicher, dass der Sensor gut anliegt (Finger, Handgelenk, Ohr).\n6. Wiederholen Sie bei Bedarf: Erhalten Sie eine Warnung? Ruhen Sie sich aus und versuchen Sie es erneut.',
        'body_en': 'A stable measurement is crucial for accurate results. Heart rate variability can fluctuate due to external factors.\n\n1. Sit comfortably: Choose a chair with good back support. Ensure your feet are flat on the ground.\n2. Rest first: Do not measure immediately after exercise, stressful moments, or caffeine intake. Wait at least 5 minutes.\n3. Quiet environment: Avoid noise, bright lights, and distractions.\n4. Breathe naturally: Try not to consciously control your breathing — just breathe normally.\n5. Good contact: Ensure the sensor has good contact (fingers, wrist, ear).\n6. Repeat if needed: Got a warning? Rest and try again.'
    },
    {
        'num': 2,
        'audience': 'consumer',
        'title_nl': 'Hartritme-variabiliteit — wat is normaal?',
        'title_de': 'Herzfrequenzvariabilität — was ist normal?',
        'title_en': 'Heart Rate Variability — What Is Normal?',
        'body_nl': 'Hartritme-variabiliteit (HRV) is de variatie in tijd tussen hartslag. Dit is NORMAAL en GEZOND.\n\nWat is normaal?\n• Jongeren (18-35): Hogere HRV (meer variatie)\n• Volwassenen (35-55): Gemiddelde HRV\n• Ouderen (55+): Lager HRV (normale leeftijdseffect)\n• Na rust: HRV hoger\n• Na stress: HRV lager (normaal)\n\nWaarom variatie belangrijk is: HRV weerspiegelt hoe flexibel je zenuwstelsel reageert. Hogere HRV = beter vermogen om te herstellen. Lagere HRV kan duiden op stress, vermoeidheid, of ziekte.\n\nNiet paniekeren bij lage HRV: Eenmalig lage HRV is niet alarmerend. Wat telt is de TREND — stijgt je HRV over weken/maanden? Dan herstel je goed.',
        'body_de': 'Herzfrequenzvariabilität (HRV) ist die Variation in der Zeit zwischen Herzschlägen. Dies ist NORMAL und GESUND.\n\nWas ist normal?\n• Junge Menschen (18-35): Höhere HRV (mehr Variation)\n• Erwachsene (35-55): Durchschnittliche HRV\n• Ältere Menschen (55+): Niedrigere HRV (normaler Alterseffekt)\n• Nach Ruhe: HRV höher\n• Nach Stress: HRV niedriger (normal)\n\nWarum Variation wichtig ist: HRV spiegelt wider, wie flexibel Ihr Nervensystem reagiert. Höhere HRV = besseres Erholungsvermögen. Niedrigere HRV kann auf Stress, Müdigkeit oder Krankheit hindeuten.\n\nNicht bei niedriger HRV in Panik geraten: Eine einmalige niedrige HRV ist nicht alarmierend. Was zählt, ist der TREND — steigt Ihre HRV über Wochen/Monate? Dann erholen Sie sich gut.',
        'body_en': 'Heart rate variability (HRV) is the variation in time between heartbeats. This is NORMAL and HEALTHY.\n\nWhat is normal?\n• Young people (18-35): Higher HRV (more variation)\n• Adults (35-55): Average HRV\n• Older adults (55+): Lower HRV (normal age effect)\n• After rest: HRV higher\n• After stress: HRV lower (normal)\n\nWhy variation matters: HRV reflects how flexibly your nervous system responds. Higher HRV = better recovery ability. Lower HRV may indicate stress, fatigue, or illness.\n\nDon\'t panic at low HRV: A single low HRV is not alarming. What matters is the TREND — does your HRV rise over weeks/months? Then you\'re recovering well.'
    },
    {
        'num': 3,
        'audience': 'consumer',
        'title_nl': 'Sensor-problemen — hulp nodig?',
        'title_de': 'Sensorprobleme — benötigen Sie Hilfe?',
        'title_en': 'Sensor Problems — Need Help?',
        'body_nl': 'Als je meting faalt of waarschuwingen toont, kan dit aan de sensor liggen.\n\nStap 1: Controleer het contact\n• Sensor moet rechtstreeks tegen huid aanraken (geen kleding, nagellak, of littekens)\n• Vinger-sensor: Zorg dat de sensor volledig op je vinger rust\n• Pols-sensor: Draag hem strak maar comfortabel\n\nStap 2: Schoon de sensor\n• Gebruik een zachte, schone doek\n• Verwijder vuil, zweet, of residu\'s\n\nStap 3: Herhaal de meting\n• Wacht 2-3 minuten\n• Probeer op een ander moment (ander vinger, ander pols, ander oor)\n\nStap 4: Battery/Bluetooth\n• Battery vol? Laad op\n• Bluetooth verbonden? Verbreek en herverbind\n\nNog steeds problemen? Neem contact op met support.',
        'body_de': 'Wenn Ihre Messung fehlschlägt oder Warnungen anzeigt, kann dies an dem Sensor liegen.\n\nSchritt 1: Überprüfen Sie den Kontakt\n• Sensor muss direkt auf der Haut liegen (ohne Kleidung, Nagellack oder Narben)\n• Finger-Sensor: Stellen Sie sicher, dass der Sensor vollständig auf Ihrem Finger ruht\n• Handgelenk-Sensor: Tragen Sie ihn straff, aber bequem\n\nSchritt 2: Reinigen Sie den Sensor\n• Verwenden Sie ein weiches, sauberes Tuch\n• Entfernen Sie Schmutz, Schweiß oder Rückstände\n\nSchritt 3: Wiederholen Sie die Messung\n• Warten Sie 2-3 Minuten\n• Versuchen Sie es zu einem anderen Zeitpunkt (anderer Finger, anderes Handgelenk, anderes Ohr)\n\nSchritt 4: Akku/Bluetooth\n• Akku voll? Laden Sie auf\n• Bluetooth verbunden? Trennen Sie und verbinden Sie erneut\n\nImmer noch Probleme? Wenden Sie sich an den Support.',
        'body_en': 'If your measurement fails or shows warnings, it may be a sensor issue.\n\nStep 1: Check the contact\n• Sensor must touch skin directly (no clothing, nail polish, or scars)\n• Finger sensor: Ensure the sensor fully rests on your finger\n• Wrist sensor: Wear it snug but comfortable\n\nStep 2: Clean the sensor\n• Use a soft, clean cloth\n• Remove dirt, sweat, or residue\n\nStep 3: Repeat the measurement\n• Wait 2-3 minutes\n• Try at a different time (different finger, different wrist, different ear)\n\nStep 4: Battery/Bluetooth\n• Battery full? Charge it\n• Bluetooth connected? Disconnect and reconnect\n\nStill having issues? Contact support.'
    },
    {
        'num': 4,
        'audience': 'pro',
        'title_nl': 'Borderline HRV-detectie — wat betekent de waarschuwing?',
        'title_de': 'Grenz-HRV-Erkennung — was bedeutet die Warnung?',
        'title_en': 'Borderline HRV Detection — What Does the Warning Mean?',
        'body_nl': 'Soms ziet u een gele/oranje waarschuwing: "⚠️ Meting grenswaarde — herhaal na rust". Dit betekent NIET dat de meting onbruikbaar is, maar wel dat deze voorzichtig moet worden geïnterpreteerd.\n\nWat betekent borderline HRV?\n• SD1/SD2-waarde (Poincaré-analyse) ligt in de grenszone: 0,69-0,70\n• Dit is niet "slecht", maar wel "onzeker"\n• Kan duiden op: mild stress, lichte vermoeidheid, suboptimale meetomstandigheden\n\nWat te doen als u borderline ziet:\n1. HERHAAL na rust: De waarschuwing verdwijnt vaak na 5-10 minuten rustig zitten\n2. CONTROLEER omgeving: Stille plek, geen afleiding, stabiel contact\n3. INTERPRETEER voorzichtig: Eén borderline meting = niet relevant. TREND over dagen/weken = informatief\n4. CLIENT COMMUNICATIE: "Uw meting is marginaal — laten we na rust opnieuw proberen" (geen paniek)\n\nWanneer is borderline INTERESSANT?\n• Herhaald borderline over meerdere sessies = signaal van recovery-noodzaak\n• Plotse verschuiving van "goed" naar "borderline" = verandering in gesteldheid/stress',
        'body_de': 'Manchmal sehen Sie eine gelbe/orangefarbene Warnung: "⚠️ Messung Grenzwert — nach Ruhe wiederholen". Dies bedeutet NICHT, dass die Messung unbrauchbar ist, sondern dass diese vorsichtig interpretiert werden muss.\n\nWas bedeutet Grenz-HRV?\n• SD1/SD2-Wert (Poincaré-Analyse) liegt in der Grenzzone: 0,69-0,70\n• Dies ist nicht "schlecht", aber "unsicher"\n• Kann hindeuten auf: leichte Anspannung, leichte Müdigkeit, suboptimale Messbedingungen\n\nWas tun bei Grenzwert:\n1. WIEDERHOLEN nach Ruhe: Die Warnung verschwindet oft nach 5-10 Minuten ruhigem Sitzen\n2. ÜBERPRÜFEN Sie die Umgebung: Ruhiger Ort, keine Ablenkung, stabiler Kontakt\n3. INTERPRETIEREN Sie vorsichtig: Eine Grenz-Messung = irrelevant. TREND über Tage/Wochen = informativ\n4. CLIENT-KOMMUNIKATION: "Ihre Messung ist marginal — lassen Sie uns nach Ruhe erneut versuchen" (keine Panik)\n\nWann ist Grenzwert INTERESSANT?\n• Wiederholte Grenzwerte über mehrere Sitzungen = Signal für Erholungsbedarf\n• Plötzliche Verschiebung von "gut" zu "Grenzwert" = Veränderung in Zustand/Stress',
        'body_en': 'Sometimes you see a yellow/orange warning: "⚠️ Measurement borderline — repeat after rest". This does NOT mean the measurement is unusable, but rather that it must be interpreted carefully.\n\nWhat does borderline HRV mean?\n• SD1/SD2 value (Poincaré analysis) falls in the borderline zone: 0.69-0.70\n• This is not "bad", but "uncertain"\n• May indicate: mild stress, slight fatigue, suboptimal measurement conditions\n\nWhat to do when you see borderline:\n1. REPEAT after rest: The warning often disappears after 5-10 minutes of quiet sitting\n2. CHECK environment: Quiet place, no distractions, stable contact\n3. INTERPRET carefully: One borderline measurement = irrelevant. TREND over days/weeks = informative\n4. CLIENT COMMUNICATION: "Your measurement is marginal — let\'s try again after rest" (no panic)\n\nWhen is borderline INTERESTING?\n• Repeated borderline over multiple sessions = signal of recovery need\n• Sudden shift from "good" to "borderline" = change in condition/stress'
    },
    # ⚠️ ARTIKEL 5 documenteert de 3-segmenten-★-analyse die NIET in prod/staging-code zit
    #    (afgewezen+verwijderd 2026-06-27). Op staging onschadelijk (geen render-loop). NIET
    #    naar prod/pro-render tot de feature bestaat of de tekst herschreven is. Zie memory.
    {
        'num': 5,
        'audience': 'pro',
        'title_nl': 'Segment-bewuste analyse — methodologie',
        'title_de': 'Segmentbewusste Analyse — Methodik',
        'title_en': 'Segment-Aware Analysis — Methodology',
        'body_nl': 'StressChecker analyzeert hartritme-stabiliteit in DRIE segmenten: begin, midden, einde van de meting. Dit geeft meer detail dan een globale score.\n\nWaarom segmenten?\n• Begin-segment (0-33%): Vertoont stress of ontspanning bij START meting\n• Midden-segment (33-67%): Toont STABILITEIT in kern-meting\n• Einde-segment (67-100%): BELANGRIJK — kan vermoeidheid, afleid of spanning aan einde tonen\n\nSegment-ratings: ★★★ (goed) tot ★ (slecht) per segment. Globale rating = LAAGSTE van drie.\n\nPraktisch voorbeeld:\n• Client: Segment 1 ★★★, Segment 2 ★★★, Segment 3 ★★\n→ Globaal: ★★ (meting matig betrouwbaar, einde-instabiliteit)\n→ Interpretatie: Client was rustig aan START, maar vermoeid/afgeleid aan EINDE\n→ Aanbeveling: Herhaal meting wanneer client volledig rustiger is\n\nVoordeel voor coaching: U ziet WAAR in de meting wat gebeurde, niet alleen globaal cijfer.',
        'body_de': 'StressChecker analysiert die Herzfrequenz-Stabilität in DREI Segmenten: Anfang, Mitte, Ende der Messung. Dies bietet mehr Detail als eine globale Bewertung.\n\nWarum Segmente?\n• Anfang-Segment (0-33%): Zeigt Stress oder Entspannung zu MESSBEGINN\n• Mittelsegment (33-67%): Zeigt STABILITÄT im KERN der Messung\n• End-Segment (67-100%): WICHTIG — kann Müdigkeit, Ablenkung oder Anspannung am Ende zeigen\n\nSegment-Bewertungen: ★★★ (gut) bis ★ (schlecht) pro Segment. Gesamtbewertung = NIEDRIGSTE von drei.\n\nPraktisches Beispiel:\n• Client: Segment 1 ★★★, Segment 2 ★★★, Segment 3 ★★\n→ Gesamt: ★★ (Messung mäßig zuverlässig, End-Instabilität)\n→ Interpretation: Client war ruhig am START, aber müde/abgelenkt am ENDE\n→ Empfehlung: Messung wiederholen, wenn Client vollständig ruhig ist\n\nVorteil für Coaching: Sie sehen WO in der Messung etwas passiert ist, nicht nur eine globale Zahl.',
        'body_en': 'StressChecker analyzes heart rate stability in THREE segments: beginning, middle, end of the measurement. This provides more detail than a global score.\n\nWhy segments?\n• Start segment (0-33%): Shows stress or relaxation at START of measurement\n• Middle segment (33-67%): Shows STABILITY in core of measurement\n• End segment (67-100%): IMPORTANT — can show fatigue, distraction, or tension at the end\n\nSegment ratings: ★★★ (good) to ★ (poor) per segment. Overall rating = LOWEST of three.\n\nPractical example:\n• Client: Segment 1 ★★★, Segment 2 ★★★, Segment 3 ★★\n→ Overall: ★★ (measurement moderately reliable, end-instability)\n→ Interpretation: Client was calm at START, but fatigued/distracted at END\n→ Recommendation: Repeat measurement when client is fully rested\n\nAdvantage for coaching: You see WHERE in the measurement something happened, not just a global score.'
    },
    {
        'num': 6,
        'audience': 'pro',
        'title_nl': 'Meting herhalen — best practices',
        'title_de': 'Messung wiederholen — Best Practices',
        'title_en': 'Retest Measurement — Best Practices',
        'body_nl': 'Als een meting waarschuwingen toont, is herhalen vaak nodig.\n\nTiming:\n• Wacht MINIMAAL 5-10 minuten tussen metingen\n• Client maakt rust: geen gesprekken, geen telefoon, geen spanning\n• Ideaal: volgende meting na 15-20 minuten rust\n\nOmgeving:\n• Hetzelfde stille, afleidingsloze plek\n• Controleer: sensor schoon, contactpunten goed\n\nInstructies geven:\n• "Uw meting was aan het einde onzeker. Laten we na rust opnieuw proberen."\n• NIET: "Uw meting was slecht" (veroorzaakt stress)\n• Leg uit: "Dit helpt ons een beter beeld van uw gesteldheid te krijgen"\n\nInterpretatie herhaling:\n• Beide keren goed → Eerste was mogelijk toevallige schommeling\n• Beide keren borderline → Signaal voor echte rust-noodzaak\n• Eerst slecht, daarna goed → Stress/vermoeidheid was TIJDELIJK\n• Altijd slecht → Medische konsultatie adviseren\n\nFrequentie:\n• Max 2-3 herhaling dezelfde dag (meer leidt tot frustratie)\n• Beter: volgende dag opnieuw proberen',
        'body_de': 'Wenn eine Messung Warnungen anzeigt, ist eine Wiederholung oft erforderlich.\n\nTiming:\n• Warten Sie MINDESTENS 5-10 Minuten zwischen Messungen\n• Client ruht: keine Gespräche, kein Telefon, keine Anspannung\n• Ideal: nächste Messung nach 15-20 Minuten Ruhe\n\nUmgebung:\n• Derselbe ruhige, ablenkungsfreie Ort\n• Überprüfen: Sensor sauber, Kontaktpunkte gut\n\nAnweisungen geben:\n• "Ihre Messung war am Ende unsicher. Lassen Sie uns nach Ruhe erneut versuchen."\n• NICHT: "Ihre Messung war schlecht" (verursacht Stress)\n• Erklären: "Dies hilft uns, ein besseres Bild Ihres Zustands zu bekommen"\n\nInterpretation der Wiederholung:\n• Beide Male gut → Erste war möglicherweise zufällige Schwankung\n• Beide Male Grenzwert → Signal für echten Erholungsbedarf\n• Erst schlecht, dann gut → Stress/Müdigkeit war VORÜBERGEHEND\n• Immer schlecht → Medizinische Beratung empfehlen\n\nHäufigkeit:\n• Max. 2-3 Wiederholungen pro Tag (mehr führt zu Frustration)\n• Besser: nächsten Tag erneut versuchen',
        'body_en': 'If a measurement shows warnings, retesting is often needed.\n\nTiming:\n• Wait AT LEAST 5-10 minutes between measurements\n• Client rests: no conversations, no phone, no stress\n• Ideal: next measurement after 15-20 minutes of rest\n\nEnvironment:\n• Same quiet, distraction-free location\n• Check: sensor clean, contact points good\n\nGiving instructions:\n• "Your measurement was uncertain at the end. Let\'s try again after rest."\n• NOT: "Your measurement was bad" (causes stress)\n• Explain: "This helps us get a better picture of your condition"\n\nInterpreting retests:\n• Both times good → First was likely random fluctuation\n• Both times borderline → Signal of genuine recovery need\n• First bad, then good → Stress/fatigue was TEMPORARY\n• Always bad → Recommend medical consultation\n\nFrequency:\n• Max 2-3 retests per day (more leads to frustration)\n• Better: try again the next day'
    },
    {
        'num': 7,
        'audience': 'pro',
        'title_nl': 'Client-interpretatie — borderline vs. normale variabiliteit',
        'title_de': 'Client-Interpretation — Grenzwert vs. normale Variabilität',
        'title_en': 'Client Interpretation — Borderline vs. Normal Variability',
        'body_nl': 'Als professional moet u borderline HRV (waarschuwing) duidelijk kunnen uitleggen zonder paniek of overdrijving.\n\nWat het NIET betekent:\n• NIET: "U bent ziek"\n• NIET: "U moet direct stoppen met activiteiten"\n• NIET: "Dit is een medische noodtoestand"\n\nWat het WEL betekent:\n• Uw hartritme-variabiliteit is VANDAAG aan de lage kant\n• Dit kan duiden op: mild stress, lichte vermoeidheid, of simpel: pech met timing/omgeving\n• TREND is het belangrijkste: één borderline meting = niets. Vijf op rij = signaal\n\nHoe te communiceren met client:\nStap 1 - NORMALISEER: "Dit gebeurt veel. Hartritme varieert dagelijks."\nStap 2 - ONDERZOEK: "Hoe voelde je je vandaag? Stress? Slecht geslapen? Veel cafeïne?"\nStap 3 - ACTIE: "Laten we rust nemen en volgende week opnieuw meten. Ik verwacht dat het beter gaat."\nStap 4 - FOLLOW-UP: Track de trend. Als borderline herhaald → echte uitdaging, advies aanpassen.\n\nNormale vs. Borderline: Timing-matrix\n• Eenmalig borderline na stress/slaaptekort → NORMAL (verwacht)\n• Herhaald borderline ondanks rust → SIGNAAL (rest-behoefte)\n• Borderline omgewisseld met goed → GEZOND (flexibele respons)\n• Altijd borderline/slecht → AANDACHT (medische konsultatie adviseren)',
        'body_de': 'Als Fachperson müssen Sie Grenz-HRV (Warnung) klar erklären können, ohne Panik oder Übertreibung.\n\nWas es NICHT bedeutet:\n• NICHT: "Sie sind krank"\n• NICHT: "Sie müssen sofort Aktivitäten einstellen"\n• NICHT: "Dies ist ein medizinischer Notfall"\n\nWas es WEL bedeutet:\n• Ihre Herzfrequenzvariabilität ist HEUTE niedrig\n• Dies kann hindeuten auf: leichte Anspannung, leichte Müdigkeit oder einfach: Pech mit Timing/Umgebung\n• TREND ist am wichtigsten: eine Grenz-Messung = nichts. Fünf hintereinander = Signal\n\nWie man mit dem Client kommuniziert:\nSchritt 1 - NORMALISIEREN: "Dies geschieht häufig. Die Herzfrequenz variiert täglich."\nSchritt 2 - ERKUNDEN: "Wie hast du dich heute gefühlt? Stress? Schlecht geschlafen? Viel Koffein?"\nSchritt 3 - HANDLUNG: "Lassen Sie uns ausruhen und nächste Woche erneut messen. Ich erwarte, dass es besser wird."\nSchritt 4 - FOLLOW-UP: Verfolgen Sie den Trend. Wenn Grenzwert wiederholt wird → echte Herausforderung, Rat anpassen.\n\nNormal vs. Grenzwert: Timing-Matrix\n• Einmalig Grenzwert nach Stress/Schlafmangel → NORMAL (erwartet)\n• Wiederholter Grenzwert trotz Ruhe → SIGNAL (Erholungsbedarf)\n• Grenzwert wechselt mit gut → GESUND (flexible Reaktion)\n• Immer Grenzwert/schlecht → AUFMERKSAMKEIT (medizinische Beratung empfehlen)',
        'body_en': 'As a professional, you must be able to clearly explain borderline HRV (warning) without panic or exaggeration.\n\nWhat it does NOT mean:\n• NOT: "You are sick"\n• NOT: "You must immediately stop activities"\n• NOT: "This is a medical emergency"\n\nWhat it DOES mean:\n• Your heart rate variability is LOW TODAY\n• This may indicate: mild stress, slight fatigue, or simply: bad timing/environment luck\n• TREND is most important: one borderline measurement = nothing. Five in a row = signal\n\nHow to communicate with client:\nStep 1 - NORMALIZE: "This happens often. Heart rate varies daily."\nStep 2 - EXPLORE: "How did you feel today? Stressed? Slept poorly? Much caffeine?"\nStep 3 - ACTION: "Let\'s rest and measure again next week. I expect it to be better."\nStep 4 - FOLLOW-UP: Track the trend. If borderline repeats → real challenge, adjust advice.\n\nNormal vs. Borderline: Timing Matrix\n• Single borderline after stress/poor sleep → NORMAL (expected)\n• Repeated borderline despite rest → SIGNAL (recovery need)\n• Borderline alternating with good → HEALTHY (flexible response)\n• Always borderline/poor → ATTENTION (recommend medical consultation)'
    },
]

REQUIRED = ('title_nl', 'title_de', 'title_en', 'body_nl', 'body_de', 'body_en')

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()
inserted = 0
errors = []

for a in articles:
    num = a.get('num')
    missing = [k for k in REQUIRED if not (a.get(k) or '').strip()]
    if missing:
        errors.append(f"Artikel {num}: lege/ontbrekende velden {missing} — overgeslagen")
        continue
    if a.get('audience') not in ('consumer', 'pro'):
        errors.append(f"Artikel {num}: ongeldige audience {a.get('audience')!r} — overgeslagen")
        continue
    slug = f"artikel-{num}"
    try:
        cur.execute(
            """INSERT OR REPLACE INTO kc_articles
               (slug, title_nl, title_de, title_en, body_nl, body_de, body_en, audience, sort_order)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (slug, a['title_nl'], a['title_de'], a['title_en'],
             a['body_nl'], a['body_de'], a['body_en'], a['audience'], num),
        )
        inserted += 1
    except Exception as e:
        errors.append(f"Artikel {num}: {e}")

conn.commit()

# Samenvatting
cur.execute("SELECT audience, COUNT(*) FROM kc_articles GROUP BY audience")
breakdown = ", ".join(f"{aud}={cnt}" for aud, cnt in cur.fetchall())
cur.execute("SELECT COUNT(*) FROM kc_articles")
total = cur.fetchone()[0]
conn.close()

print(f"DB: {DB_PATH}")
print(f"✅ Import klaar: {inserted} artikelen geplaatst, {len(errors)} errors/overgeslagen")
print(f"   Tabel-totaal: {total} rijen ({breakdown})")
for e in errors:
    print(f"  ❌ {e}")
