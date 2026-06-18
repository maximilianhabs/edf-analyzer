"""ECG analysis: R-peak detection, RR intervals, HRV metrics."""

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


@dataclass
class RRSeries:
    """
    Träger-Objekt für eine RR-Zeitreihe mit Artefakt-Maske.
    Wird zwischen ecg.py und hrv_freq.py ausgetauscht — niemals rohe Arrays.
    """
    rr_ms:         np.ndarray   # alle RR-Intervalle in ms (inkl. Artefakte)
    rr_times_s:    np.ndarray   # Zeitstempel der R-Peaks (Sekunden)
    artifact_mask: np.ndarray   # bool-Array, True = Artefakt

    @property
    def clean_rr(self) -> np.ndarray:
        """Gefilterte RR-Intervalle (Artefakte ausgeschlossen)."""
        return self.rr_ms[~self.artifact_mask]

    @property
    def clean_times(self) -> np.ndarray:
        """Zeitstempel der sauberen RR-Intervalle."""
        return self.rr_times_s[~self.artifact_mask]

    @property
    def artifact_pct(self) -> float:
        return float(self.artifact_mask.mean() * 100) if len(self.artifact_mask) else 0.0

    @property
    def n_clean(self) -> int:
        return int((~self.artifact_mask).sum())

    @property
    def is_analyzable(self) -> bool:
        """Mindestanforderungen für valide HRV-Analyse (Task Force 1996: ≥ 5 min / ~300 Schläge)."""
        return self.n_clean >= 50 and self.artifact_pct < 30.0


def preprocess_ecg(signal: np.ndarray, sfreq: float) -> np.ndarray:
    """Remove DC offset and normalize ECG signal."""
    from scipy.signal import butter, filtfilt

    # Remove DC offset
    signal = signal - np.mean(signal)

    # Bandpass 0.5–40 Hz (removes baseline wander and high-freq noise)
    nyq = sfreq / 2
    low, high = 0.5 / nyq, min(40.0 / nyq, 0.99)
    b, a = butter(4, [low, high], btype="band")
    signal = filtfilt(b, a, signal)

    return signal


def detect_r_peaks(signal: np.ndarray, sfreq: float) -> np.ndarray:
    """
    Pan-Tompkins QRS-Detektor (vereinfacht): Bandpass 5-15 Hz → Differentiation
    → Squaring → Moving-Window-Integration → adaptive Threshold.
    Robuster gegen T-Wellen und Artefakte als einfaches find_peaks.
    """
    from scipy.signal import butter, filtfilt, find_peaks

    nyq = sfreq / 2

    # 1) Bandpass 5–15 Hz hebt QRS-Komplex hervor, dämpft T-Wellen und Baseline
    b, a = butter(2, [5 / nyq, 15 / nyq], btype="band")
    filtered = filtfilt(b, a, signal)

    # 2) Differentiation (betont Flanken)
    diff = np.diff(filtered, prepend=filtered[0])

    # 3) Squaring (alle positiv, nichtlinear verstärkt)
    squared = diff ** 2

    # 4) Moving-Window-Integration (150 ms Fenster)
    win = max(1, int(sfreq * 0.150))
    integrated = np.convolve(squared, np.ones(win) / win, mode="same")

    # 5) Adaptive Threshold + Mindestabstand 300 ms (max ~200 bpm)
    threshold = np.percentile(integrated, 98) * 0.25
    min_dist = int(sfreq * 0.300)
    candidates, _ = find_peaks(integrated, distance=min_dist, height=threshold)

    # 6) Rückschieben: tatsächlicher R-Peak im Originalsignal (±40 ms)
    window = int(sfreq * 0.040)
    refined = []
    for p in candidates:
        lo = max(0, p - window)
        hi = min(len(signal) - 1, p + window)
        refined.append(lo + int(np.argmax(signal[lo : hi + 1])))
    return np.array(refined, dtype=int)


def compute_rr_intervals(r_peaks: np.ndarray, sfreq: float) -> np.ndarray:
    """Convert R-peak sample indices to RR intervals in milliseconds."""
    rr_ms = np.diff(r_peaks) / sfreq * 1000
    # Remove physiologically implausible values (< 300ms or > 2000ms)
    rr_ms = rr_ms[(rr_ms > 300) & (rr_ms < 2000)]
    return rr_ms


def build_rr_series(r_peaks: np.ndarray, sfreq: float) -> Optional[RRSeries]:
    """
    Erstellt eine RRSeries mit Artefakt-Maske aus R-Peak-Indizes.

    Artefakt-Kriterien (3-stufig):
      1. Physiologisch implausibel: RR < 300 ms oder > 2000 ms
      2. Ektopische Schläge: Abweichung > 20% vom gleitenden Median (Fenster 5)
      3. Signaldropout: aufeinanderfolgende identische RR-Werte
    """
    if len(r_peaks) < 3:
        return None

    rr_ms     = np.diff(r_peaks).astype(float) / sfreq * 1000
    times_s   = r_peaks[:-1].astype(float) / sfreq
    n         = len(rr_ms)
    mask      = np.zeros(n, dtype=bool)

    # Stufe 1: physiologische Grenzen
    mask |= (rr_ms < 300) | (rr_ms > 2000)

    # Stufe 2: ektopische Schläge — gleitender Median (Fenster 5)
    half = 2
    for i in range(n):
        lo, hi = max(0, i - half), min(n, i + half + 1)
        local_median = np.median(rr_ms[lo:hi])
        if local_median > 0 and abs(rr_ms[i] - local_median) / local_median > 0.20:
            mask[i] = True

    # Stufe 3: Signal-Dropout (≥ 3 identische aufeinanderfolgende Werte)
    for i in range(2, n):
        if rr_ms[i] == rr_ms[i - 1] == rr_ms[i - 2]:
            mask[i - 2 : i + 1] = True

    return RRSeries(rr_ms=rr_ms, rr_times_s=times_s, artifact_mask=mask)


def compute_hrv_time_domain(rr_ms: np.ndarray) -> dict:
    """Compute standard time-domain HRV metrics."""
    if len(rr_ms) < 5:
        return {}

    successive_diff = np.diff(rr_ms)

    return {
        "mean_rr_ms": round(float(np.mean(rr_ms)), 1),
        "mean_hr_bpm": round(60000 / float(np.mean(rr_ms)), 1),
        "sdnn_ms": round(float(np.std(rr_ms, ddof=1)), 1),
        "rmssd_ms": round(float(np.sqrt(np.mean(successive_diff**2))), 1),
        "pnn50_pct": round(float(np.sum(np.abs(successive_diff) > 50) / len(successive_diff) * 100), 1),
        "min_rr_ms": round(float(np.min(rr_ms)), 1),
        "max_rr_ms": round(float(np.max(rr_ms)), 1),
        "n_beats": len(rr_ms) + 1,
    }


def compute_hrv_frequency_domain(rr_ms: np.ndarray, sfreq_rr: float = 4.0) -> dict:
    """Compute frequency-domain HRV (LF, HF, LF/HF ratio) via Welch."""
    from scipy.signal import welch
    from scipy.interpolate import interp1d

    if len(rr_ms) < 20:
        return {}

    # Interpolate RR to evenly sampled signal
    t_rr = np.cumsum(rr_ms) / 1000  # seconds
    t_uniform = np.arange(t_rr[0], t_rr[-1], 1.0 / sfreq_rr)
    interpolator = interp1d(t_rr, rr_ms, kind="cubic", bounds_error=False)
    rr_uniform = interpolator(t_uniform)

    # Remove NaN from interpolation boundaries
    valid = ~np.isnan(rr_uniform)
    rr_uniform = rr_uniform[valid]

    if len(rr_uniform) < 20:
        return {}

    freqs, psd = welch(rr_uniform, fs=sfreq_rr, nperseg=min(256, len(rr_uniform)))

    def band_power(f_low, f_high):
        mask = (freqs >= f_low) & (freqs < f_high)
        return float(np.trapz(psd[mask], freqs[mask]))

    vlf = band_power(0.003, 0.04)
    lf = band_power(0.04, 0.15)
    hf = band_power(0.15, 0.4)
    total = vlf + lf + hf

    return {
        "vlf_ms2": round(vlf, 2),
        "lf_ms2": round(lf, 2),
        "hf_ms2": round(hf, 2),
        "lf_hf_ratio": round(lf / hf, 3) if hf > 0 else None,
        "lf_nu": round(lf / (lf + hf) * 100, 1) if (lf + hf) > 0 else None,
        "hf_nu": round(hf / (lf + hf) * 100, 1) if (lf + hf) > 0 else None,
    }


def run_ecg_analysis(signal: np.ndarray, sfreq: float) -> dict:
    """Full ECG analysis pipeline. Returns all metrics and intermediate results."""
    signal_clean = preprocess_ecg(signal, sfreq)
    r_peaks = detect_r_peaks(signal_clean, sfreq)
    rr_ms = compute_rr_intervals(r_peaks, sfreq)
    rr_series = build_rr_series(r_peaks, sfreq)

    time_domain = compute_hrv_time_domain(rr_ms)
    freq_domain = compute_hrv_frequency_domain(rr_ms)

    return {
        "signal_clean": signal_clean,
        "r_peaks": r_peaks,
        "rr_ms": rr_ms,
        "rr_series": rr_series,   # RRSeries mit Artefakt-Maske
        "hrv_time": time_domain,
        "hrv_freq": freq_domain,
    }
