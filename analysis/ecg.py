"""ECG analysis: R-peak detection, RR intervals, HRV metrics."""

import numpy as np
import pandas as pd


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
    """Detect R-peaks using scipy find_peaks with adaptive threshold. Returns sample indices."""
    from scipy.signal import find_peaks

    # Minimum distance: 250ms (max ~240 bpm)
    min_distance = int(sfreq * 0.25)
    # Adaptive threshold: 60% of signal range
    threshold = np.percentile(signal, 95) * 0.5

    peaks, _ = find_peaks(signal, distance=min_distance, height=threshold)
    return peaks


def compute_rr_intervals(r_peaks: np.ndarray, sfreq: float) -> np.ndarray:
    """Convert R-peak sample indices to RR intervals in milliseconds."""
    rr_ms = np.diff(r_peaks) / sfreq * 1000
    # Remove physiologically implausible values (< 300ms or > 2000ms)
    rr_ms = rr_ms[(rr_ms > 300) & (rr_ms < 2000)]
    return rr_ms


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

    time_domain = compute_hrv_time_domain(rr_ms)
    freq_domain = compute_hrv_frequency_domain(rr_ms)

    return {
        "signal_clean": signal_clean,
        "r_peaks": r_peaks,
        "rr_ms": rr_ms,
        "hrv_time": time_domain,
        "hrv_freq": freq_domain,
    }
