# Week 12 — EEG teaching dataset (notes for staff)

File: `files/data/eeg_oddball.csv` (made by `tools/make_physio_data.py`, numpy, seed 2026; re-running gives the same file).

## Dataset description (Hebrew, for the assignment page)

הקובץ eeg_oddball.csv מכיל הקלטת EEG מדומה של נבדק אחד מאלקטרודה Pz, במשימת oddball שמיעתית.
במשימה הוצגו 100 צלילים בסדר אקראי: 80 צלילים רגילים (standard) ו-20 צלילים נדירים (oddball).
קצב הדגימה הוא 250 הרץ (דגימה כל 4 מילישניות). כל ניסיון נחתך מ-200 מילישניות לפני הופעת הצליל (זמן 0) ועד 796 מילישניות אחריו, כלומר 250 דגימות לניסיון.
הקובץ בפורמט ארוך: 25,000 שורות, שורה לכל דגימה, עם העמודות trial (מספר ניסיון, 1–100), condition (standard או oddball), time_ms (זמן במילישניות) ו-voltage (מתח במיקרו-וולט).
בנתונים יש סחיפה איטית של המתח (ולכן צריך תיקון קו בסיס) וכמה ניסיונות עם ארטיפקט גדול, כמו מצמוץ (ולכן צריך לדחות ניסיונות רועשים).

## What is in the signal (simulation)

- Background noise: 1/f noise (SD 3 µV) + 10 Hz alpha (1.5–3.5 µV) + white noise (SD 1.2 µV).
- All trials: N1 (about −4 µV at 100 ms) and P2 (about +3.5 µV at 190 ms).
- Oddball trials: broad P300, about +9.5 µV peak around 350 ms (Gaussian, width 85 ms); standards get a tiny one (about +1 µV).
- Every trial: a DC offset (session drift from +12 to −8 µV plus a random offset with SD 10 µV) and a small linear drift.
- Blink artifacts (140–220 µV) in 6 trials: 3, 29, 49, 58, 86, 94 (4 standard, 2 oddball).

## Verified key numbers (pipeline from the units)

Pipeline: baseline correction (subtract each trial's mean over time_ms < 0, i.e. −200…−4 ms), then reject trials with max |voltage_bc| > 100 µV.

- Rejected trials: 6 (3, 29, 49, 58, 86, 94). Their max |voltage_bc| is 163–223 µV, and the largest clean trial reaches only 20.5 µV, so any threshold from about 25 to 160 µV rejects the same 6 trials (a threshold of 50 → 6, of 200 → 2). The same 6 trials are rejected if the threshold is applied to the raw voltage.
- Trials left: **standard 76, oddball 18** (94 in all).
- Mean amplitude 250–500 ms (baseline-corrected, one value per trial; samples 252…500 ms, 63 samples):
  - **oddball 6.00 µV (SD 2.42, n = 18)**
  - **standard 0.52 µV (SD 3.08, n = 76)**
  - R `t.test(amplitude ~ condition)` (Welch): t(31.4) = 8.17, p = 2.9e−9.
  - Python `scipy.stats.ttest_ind` (Student, equal variances): t(92) = 7.05, p = 3.2e−10.
- Same analysis **without** baseline correction (after the same rejection): oddball 4.49 µV (SD 9.74), standard 3.56 µV (SD 12.83), Welch p = 0.74 (Student p = 0.77). The effect disappears, which shows why baseline correction matters.
- ERP (baseline-corrected, after rejection): the oddball peaks at +9.31 µV at 384 ms. The standard stays near 0–1 µV after 250 ms. Both show N1 (about −4 µV near 90–100 ms) and P2 (about +3.5 µV near 185–200 ms).
