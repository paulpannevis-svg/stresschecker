# StressChecker Phase 2d — Sleep-Aware RMSSD Normalization

## 1. SLEEP & RMSSD CORRELATION

Poor Sleep (1-3):     Lower RMSSD acceptable (fatigue) → mult 0.85
Fair Sleep (4-5):     Slightly reduced → mult 0.95
Good Sleep (6-7):     Standard baseline → mult 1.00
Excellent (8-10):     Higher RMSSD expected → mult 1.10

## 2. ADJUSTMENT LOGIC

Female 60-70, sleep_quality=8, RMSSD=26.0, 8 AM:

1. Baseline threshold: 8.5-30.0
2. Sleep multiplier (8/10): 1.08
3. Sleep-adjusted: (9.2-32.4)
4. Circadian (8 AM): 1.05
5. Adjusted RMSSD: 26.0 / 1.05 = 24.76
6. Result: VALID_GREEN ✅

## 3. FUNCTION: compute_display_state_with_sleep_adjustment()

Input: sleep_quality (1-10), RMSSD, circadian_hour, gender, birth_year
Output: display_state + sleep_context

Logic:
- sleep_mult = 0.85 + (sleep_quality / 10)
- adjusted_thresholds = baseline × sleep_mult
- Apply circadian adjustment
- Check RMSSD against adjusted thresholds

## 4. STATUS

✅ sleep_quality kolom toegevoegd
✅ Specification complete
⏳ Implementation pending

Versie: 0.1 (Phase 2d, 05-07-2026)
