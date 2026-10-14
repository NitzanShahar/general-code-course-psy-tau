"""Simulate the teaching EEG dataset for the physiological-data units and week 12 (oddball task, one participant).

Electrode Pz, 250 Hz, epochs from -200 to 796 ms (4 ms steps), 100 trials: 80 "standard" and 20 "oddball" in random order.
Every trial has background noise (1/f + 10 Hz alpha + white), a small N1/P2 and a random DC offset plus a slow drift
(so baseline correction matters). Oddball trials add a broad P300 (~+9 uV around 350 ms). Six trials (mixed conditions)
carry a blink-like artifact above 100 uV (so artifact rejection matters).
Writes files/data/eeg_oddball.csv in long format: trial, condition, time_ms, voltage (uV, 2 decimals).

Usage: python tools/make_physio_data.py
"""
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "files" / "data" / "eeg_oddball.csv"

SEED = 2026
SRATE = 250                                  # Hz
TIME_MS = np.arange(-200, 800, 1000 // SRATE)  # -200, -196, ..., 796  (250 samples)
N_STANDARD, N_ODDBALL = 80, 20
ARTIFACT_TRIALS = {"standard": 4, "oddball": 2}


def bump(t, center, width, amplitude):
    """A Gaussian-shaped component (amplitude in uV, center and width in ms)."""
    return amplitude * np.exp(-0.5 * ((t - center) / width) ** 2)


def pink_noise(rng, n, sd):
    """1/f noise: white noise shaped in the frequency domain, scaled to the requested SD."""
    spectrum = np.fft.rfft(rng.normal(size=n))
    freqs = np.fft.rfftfreq(n, d=1 / SRATE)
    freqs[0] = freqs[1]
    noise = np.fft.irfft(spectrum / np.sqrt(freqs), n)
    return sd * (noise - noise.mean()) / noise.std()


def simulate_trial(rng, condition, trial_index, n_trials):
    t = TIME_MS
    seconds = t / 1000
    signal = (pink_noise(rng, t.size, 3.0)
              + rng.uniform(1.5, 3.5) * np.sin(2 * np.pi * rng.normal(10, 0.5) * seconds + rng.uniform(0, 2 * np.pi))
              + rng.normal(0, 1.2, t.size))
    signal += bump(t, rng.normal(100, 8), 22, -rng.normal(4, 1))       # N1
    signal += bump(t, rng.normal(190, 10), 30, rng.normal(3.5, 1))     # P2
    if condition == "oddball":
        signal += bump(t, rng.normal(350, 25), 85, rng.normal(9.5, 2))  # P300
    else:
        signal += bump(t, rng.normal(350, 25), 85, rng.normal(1.0, 1))  # tiny P300 to frequent tones
    session_drift = 12 - 20 * trial_index / n_trials                    # electrode drifts slowly during the session
    signal += session_drift + rng.normal(0, 10)                          # DC offset of the trial
    signal += rng.normal(0, 3) * (t - t.min()) / np.ptp(t)               # slow linear drift within the epoch
    return signal


def add_blink(rng, signal):
    center = rng.uniform(50, 650)
    return signal + bump(TIME_MS, center, rng.uniform(40, 70), rng.uniform(140, 220))


def main():
    rng = np.random.default_rng(SEED)
    conditions = np.array(["standard"] * N_STANDARD + ["oddball"] * N_ODDBALL)
    rng.shuffle(conditions)
    n_trials = conditions.size

    blink_trials = set()
    for condition, n in ARTIFACT_TRIALS.items():
        candidates = np.flatnonzero(conditions == condition)
        blink_trials.update(rng.choice(candidates, n, replace=False).tolist())

    lines = ["trial,condition,time_ms,voltage"]
    for i, condition in enumerate(conditions):
        signal = simulate_trial(rng, condition, i, n_trials)
        if i in blink_trials:
            signal = add_blink(rng, signal)
        lines += [f"{i + 1},{condition},{t},{v:.2f}" for t, v in zip(TIME_MS, signal)]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{OUT.relative_to(ROOT)}: {n_trials} trials x {TIME_MS.size} samples = {len(lines) - 1} rows; "
          f"blink trials: {sorted(t + 1 for t in blink_trials)}")


if __name__ == "__main__":
    main()
