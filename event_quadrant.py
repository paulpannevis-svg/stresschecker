#!/usr/bin/env python3
"""Event-modus — statisch tweeassig kwadrant voor het WeasyPrint-PDF.

Getrouwe, JS-vrije reproductie van het kwadrant uit de gewone StressChecker
(templates/kwadrant.html :: drawQuadrant). WeasyPrint voert geen JS uit, dus de
canvas-component is niet herbruikbaar; deze module rendert de gekleurde
zone-achtergrond met PIL (PNG-data-URI) en bouwt de assen/labels/punten als SVG.

Parity-borging: de B/C/T-tabellen worden uit static/js/hrv.js GEPARSED (zelfde bron
als de app), niet overgetikt. getRaw/rawToRGB/grijs-regel zijn 1-op-1 geport.

Event-variant: ALLEEN 'Huidig' (de meting, op bpm×hrv_pct) en 'Zelfinschatting'
(subjectief_score, regel-340-replica: x = gemeten bpm, y = gevoel/10 × hoogte).
GEEN 'Vorig'-punt (momentopname). kwadrant.html/hrv.js blijven onaangeraakt.
"""
import base64
import io
import json
import os
import re

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
_HRV_JS = os.path.join(PROJECT_ROOT, 'static', 'js', 'hrv.js')


def _load_tables():
    txt = open(_HRV_JS).read()
    def arr(name):
        m = re.search(r'^var %s=(\[.*\]);' % name, txt, re.M)
        return json.loads(m.group(1))
    return arr('B'), arr('C'), arr('T')


B, C, T = _load_tables()


def get_raw(bpm, hrv):
    """Bilineaire interpolatie over T (port van kwadrant.html getRaw)."""
    bpm = max(40.0, min(120.0, bpm))
    hrv = max(0.0, min(220.0, hrv))
    br = 0
    for i in range(len(B) - 1):
        if bpm <= B[i + 1]:
            br = i
            break
    br = min(br, len(T) - 2)
    ci = 0
    for j in range(len(C) - 1):
        if hrv <= C[j + 1]:
            ci = j
            break
    ci = min(ci, len(T[br]) - 2)
    ci = min(ci, len(T[0]) - 2)
    bt = (bpm - B[br]) / (B[br + 1] - B[br])
    ct = (hrv - C[ci]) / (C[ci + 1] - C[ci])
    return (T[br][ci] * (1 - bt) * (1 - ct) + T[br][ci + 1] * (1 - bt) * ct +
            T[br + 1][ci] * bt * (1 - ct) + T[br + 1][ci + 1] * bt * ct)


# Kleurstops (port van kwadrant.html rawToRGB): RI-zone-kleuren op raw-schaal (RI×12).
_STOPS = [(0, 192, 57, 43), (23.99, 192, 57, 43), (24.01, 230, 126, 34),
          (47.99, 230, 126, 34), (48.01, 241, 196, 15), (71.99, 241, 196, 15),
          (72.01, 130, 210, 40), (95.99, 130, 210, 40), (96.01, 39, 174, 96),
          (120, 39, 174, 96)]


def raw_to_rgb(v):
    if v <= _STOPS[0][0]:
        return _STOPS[0][1:4]
    if v >= _STOPS[-1][0]:
        return _STOPS[-1][1:4]
    for i in range(len(_STOPS) - 1):
        if _STOPS[i][0] <= v <= _STOPS[i + 1][0]:
            t = (v - _STOPS[i][0]) / (_STOPS[i + 1][0] - _STOPS[i][0])
            return tuple(round(_STOPS[i][1 + k] * (1 - t) + _STOPS[i + 1][1 + k] * t)
                         for k in range(3))
    return (160, 160, 160)


# raw→rgb-LUT (0..160) zodat we 'm niet per pixel hoeven te scannen.
_RGB_LUT = [raw_to_rgb(float(v)) for v in range(0, 161)]
_GREY = (160, 160, 160)


def _render_bg_png(W, H, radius):
    """Gekleurde zone-achtergrond als RGBA-PNG met afgeronde hoeken (alpha-masker)."""
    from PIL import Image, ImageDraw
    img = Image.new('RGB', (W, H))
    px = img.load()
    # Voorberekende bins per kolom (bpm) en rij (hrv).
    col = []
    for x in range(W):
        bpm = 40.0 + (x / (W - 1)) * 80.0
        br = 0
        for i in range(len(B) - 1):
            if bpm <= B[i + 1]:
                br = i
                break
        br = min(br, len(T) - 2)
        bt = (bpm - B[br]) / (B[br + 1] - B[br])
        col.append((bpm, br, bt))
    row = []
    for y in range(H):
        hrv = 220.0 - (y / (H - 1)) * 220.0
        ci = 0
        for j in range(len(C) - 1):
            if hrv <= C[j + 1]:
                ci = j
                break
        ci = min(ci, len(T[0]) - 2)
        ct = (hrv - C[ci]) / (C[ci + 1] - C[ci])
        row.append((hrv, ci, ct))
    for y in range(H):
        hrv, ci, ct = row[y]
        for x in range(W):
            bpm, br, bt = col[x]
            raw = (T[br][ci] * (1 - bt) * (1 - ct) + T[br][ci + 1] * (1 - bt) * ct +
                   T[br + 1][ci] * bt * (1 - ct) + T[br + 1][ci + 1] * bt * ct)
            if (bpm - 70) * (hrv - 60) > 3200 and bpm >= 80 and hrv >= 100:
                px[x, y] = _GREY
            else:
                ri12 = int(raw + 0.5)
                if ri12 < 0:
                    ri12 = 0
                elif ri12 > 160:
                    ri12 = 160
                px[x, y] = _RGB_LUT[ri12]
    img = img.convert('RGBA')
    mask = Image.new('L', (W, H), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, W - 1, H - 1], radius=radius, fill=255)
    img.putalpha(mask)
    buf = io.BytesIO()
    img.save(buf, 'PNG')
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode('ascii')


# Zone-labels (1-op-1 uit kwadrant.html), op (bpm,hrv)-ankers.
_ZONES = {
    'nl': [('VEERKRACHTIG', 75, 170), ('IN BALANS', 75, 110), ('LICHT BELAST', 80, 70),
           ('BELAST', 85, 45), ('ACTIEF BELAST', 100, 175), ('ZWAAR BELAST', 60, 25),
           ('ZWAAR BELAST', 100, 25)],
    'de': [('VITAL', 75, 170), ('IM GLEICHGEWICHT', 75, 110), ('LEICHT BELASTET', 80, 70),
           ('BELASTET', 85, 45), ('AKTIV BELASTET', 100, 175), ('STARK BELASTET', 60, 25),
           ('STARK BELASTET', 100, 25)],
    'en': [('RESILIENT', 75, 170), ('IN BALANCE', 75, 110), ('LIGHTLY STRAINED', 80, 70),
           ('STRAINED', 85, 45), ('ACTIVELY LOADED', 100, 175), ('HEAVILY STRAINED', 60, 25),
           ('HEAVILY STRAINED', 100, 25)],
}

_QUAD_TEXT = {
    'nl': {'heading': 'Kwadrant', 'huidig': 'Huidig (meting)', 'zelf': 'Zelfinschatting',
           'note': 'Zelfinschatting = waar je je voelt op de ontspannings-as; geen aparte meting.'},
    'de': {'heading': 'Quadrant', 'huidig': 'Aktuell (Messung)', 'zelf': 'Selbsteinschätzung',
           'note': 'Selbsteinschätzung = wo Sie sich auf der Erholungsachse fühlen; keine separate Messung.'},
    'en': {'heading': 'Quadrant', 'huidig': 'Current (measurement)', 'zelf': 'Self-assessment',
           'note': 'Self-assessment = where you feel you are on the recovery axis; not a separate measurement.'},
}


def _zone_color(ri):
    r = float(ri)
    return ('#27ae60' if r >= 8 else '#82d228' if r >= 6 else '#f1c40f'
            if r >= 4 else '#e67e22' if r >= 2 else '#c0392b')


# Geometrie (SVG-eenheden). L/Tpad = marges voor de assen.
L, TP, CW, CH, RP, BP = 36, 8, 300, 240, 14, 30
RADIUS = 8
VBW, VBH = L + CW + RP, TP + CH + BP


def _gx(bpm):
    return L + ((bpm - 40) / 80.0) * CW


def _gy_hrv(hrv):
    return TP + CH - (hrv / 220.0) * CH


def _gy_subj(subj):
    return TP + CH - (subj / 10.0) * CH


def build_quadrant(bpm, hrv_pct, subjectief, ri, reliable, lang):
    """Bouw het event-kwadrant. Returns dict met 'show', 'svg' (veilige markup) en labels.
    Geen gevoel/onvolledige meting → felt-punt/connector weg; bpm/hrv ontbreekt → geen kwadrant."""
    txt = _QUAD_TEXT.get(lang, _QUAD_TEXT['nl'])
    if bpm is None or hrv_pct is None:
        return {'show': False}
    W, H = CW, CH  # render op displayresolutie
    bg = _render_bg_png(W, H, RADIUS)
    parts = []
    parts.append(f'<svg viewBox="0 0 {VBW} {VBH}" xmlns="http://www.w3.org/2000/svg" '
                 f'font-family="Helvetica, Arial, sans-serif">')
    parts.append(f'<image href="{bg}" x="{L}" y="{TP}" width="{CW}" height="{CH}" '
                 f'preserveAspectRatio="none"/>')
    parts.append(f'<rect x="{L}" y="{TP}" width="{CW}" height="{CH}" rx="{RADIUS}" '
                 f'fill="none" stroke="#ddd" stroke-width="1"/>')
    # Assen-ticks
    for b in (40, 60, 80, 100, 120):
        parts.append(f'<text x="{_gx(b):.1f}" y="{TP + CH + 13}" font-size="9" fill="#666" '
                     f'text-anchor="middle">{b}</text>')
    parts.append(f'<text x="{_gx(80):.1f}" y="{TP + CH + 25}" font-size="9" fill="#555" '
                 f'text-anchor="middle">BPM</text>')
    for h in (0, 50, 100, 150, 200):
        parts.append(f'<text x="{L - 4}" y="{_gy_hrv(h) + 3:.1f}" font-size="9" fill="#666" '
                     f'text-anchor="end">{h}%</text>')
    parts.append(f'<text x="11" y="{TP + CH * 0.45:.1f}" font-size="9" fill="#555" '
                 f'text-anchor="middle" transform="rotate(-90 11 {TP + CH * 0.45:.1f})">HRV</text>')
    # Zone-labels (wit, met dunne donkere halo voor leesbaarheid)
    for tlabel, zb, zh in _ZONES.get(lang, _ZONES['nl']):
        zx, zy = _gx(zb), _gy_hrv(zh)
        parts.append(f'<text x="{zx:.1f}" y="{zy:.1f}" font-size="10.5" font-weight="bold" '
                     f'text-anchor="middle" fill="#fff" stroke="rgba(0,0,0,0.35)" '
                     f'stroke-width="0.5" paint-order="stroke">{tlabel}</text>')
    # Punten
    hx, hy = _gx(bpm), _gy_hrv(hrv_pct)
    gated = not reliable
    ring = '#cfcfcf' if gated else _zone_color(ri if ri is not None else 0)
    hfill = '#9aa0a6' if gated else '#1a1a1a'
    has_felt = subjectief is not None
    if has_felt:
        sx, sy = _gx(bpm), _gy_subj(subjectief)
        # Verbindingslijntje (verzachting 2): toont 'afstand = gevoel vs meting'.
        parts.append(f'<line x1="{hx:.1f}" y1="{hy:.1f}" x2="{sx:.1f}" y2="{sy:.1f}" '
                     f'stroke="#888" stroke-width="1.4" stroke-dasharray="3 2"/>')
    # Huidig (meting): ring + gevulde stip
    parts.append(f'<circle cx="{hx:.1f}" cy="{hy:.1f}" r="11" fill="none" '
                 f'stroke="{ring}" stroke-width="3"/>')
    parts.append(f'<circle cx="{hx:.1f}" cy="{hy:.1f}" r="8" fill="{hfill}" '
                 f'stroke="#fff" stroke-width="2"/>')
    if has_felt:
        parts.append(f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="7" fill="#0078ff" '
                     f'fill-opacity="0.85" stroke="#fff" stroke-width="2"/>')
    parts.append('</svg>')
    return {
        'show': True, 'svg': ''.join(parts), 'heading': txt['heading'],
        'l_huidig': txt['huidig'], 'l_zelf': txt['zelf'] if has_felt else None,
        'note': txt['note'] if has_felt else None,
    }
