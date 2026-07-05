# StressChecker Phase 2c — Circadian Rhythm

## 1. OBSERVED PATTERNS
Hour 13 (1 PM):  RMSSD 16.25
Hour 20 (8 PM):  RMSSD 13.88 (13% lower)

## 2. CIRCADIAN MULTIPLIERS
Early Morning (4-8 AM):  1.15
Morning (8-12 PM):       1.05
Afternoon (12-6 PM):     1.00
Evening (6-10 PM):       0.90
Late Evening (10-4 AM):  0.85

## 3. FUNCTION: compute_display_state_with_circadian_adjustment()
- Extract hour from timestamp
- Get circadian multiplier
- Calculate: adjusted_rmssd = raw / multiplier
- Apply gender/age thresholds to adjusted value
- Return state + context

Status: Specification ready for implementation
