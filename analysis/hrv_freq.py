"""HRV-Frequenzdomänen-Analyse: Welch (FFT) und Burg-Methode (Maximum Entropy)."""

from typing import Optional

import numpy as np
from scipy.signal import welch
from scipy.interpolate import PchipInterpolator

# Standard-Frequenzbänder für Kurzzeit-HRV (Task Force ESC/NASPE 1996)
VLF_BAND = (0.0033, 0.04)
LF_BAND  = (0.04, 0.15)
HF_BAND  = (0.15, 0.4)

# Ab dieser Lückenlänge gilt ein Interpolationssegment als "erfunden" und wird
# als spektraler Confounder gemeldet (entfernte Schläge / Signal-Dropout).
GAP_WARN_S = 3.0


def resample_rr(rr_ms: np.ndarray, t_s: np.ndarray, fs_interp: float = 4.0):
    """
    Interpoliert die unregelmäßig abgetastete RR-Zeitreihe auf ein gleichmäßiges
    Zeitraster als Voraussetzung für FFT/Burg.

    Verwendet einen **formerhaltenden PCHIP-Interpolator** statt eines kubischen
    Splines: PCHIP überschwingt zwischen Stützstellen nicht (monoton), erfindet
    also über entfernten Schlägen / langen Lücken keine künstlichen Oszillationen,
    die LF/HF verfälschen würden. Genau dort ist ein kubischer Spline gefährlich.
    """
    t_even = np.arange(t_s[0], t_s[-1], 1.0 / fs_interp)
    interp = PchipInterpolator(t_s, rr_ms)
    rr_even = interp(t_even)
    rr_even -= rr_even.mean()
    return rr_even, t_even


def gap_stats(t_s: np.ndarray) -> dict:
    """Kennzahlen zu Zeitlücken in der (bereinigten) RR-Zeitreihe.

    Große zusammenhängende Lücken (entfernte Schläge, Dropout) sind ein
    spektraler Confounder — hier gemessen, damit die UI sie kenntlich machen kann.
    """
    if len(t_s) < 2:
        return {"max_gap_s": 0.0, "n_gaps": 0, "gap_fraction": 0.0}
    dt = np.diff(t_s)
    span = float(t_s[-1] - t_s[0])
    big = dt[dt > GAP_WARN_S]
    return {
        "max_gap_s": float(dt.max()),
        "n_gaps": int(big.size),
        "gap_fraction": float(big.sum() / span) if span > 0 else 0.0,
    }


def psd_welch(rr_even: np.ndarray, fs_interp: float = 4.0):
    """FFT-basierte Power-Spektraldichte via Welch-Methode."""
    nperseg = min(len(rr_even), 256)
    freqs, psd = welch(rr_even, fs=fs_interp, nperseg=nperseg, noverlap=nperseg // 2)
    return freqs, psd


def burg_ar(x: np.ndarray, order: int):
    """
    Burg-Algorithmus: schätzt AR-Modellkoeffizienten direkt aus den Daten,
    ohne Fensterung — daher hohe spektrale Auflösung bei kurzen Segmenten
    (Grundlage der Maximum-Entropy-Spektralschätzung).
    """
    x = np.asarray(x, dtype=np.float64)
    N = len(x)
    f = x.copy()
    b = x.copy()
    a = np.zeros(order + 1)
    a[0] = 1.0
    err = np.sum(x ** 2)
    for m in range(1, order + 1):
        fm = f[m:N]
        bm = b[m - 1:N - 1]
        den = np.dot(fm, fm) + np.dot(bm, bm)
        k = 0.0 if den == 0 else -2.0 * np.dot(fm, bm) / den
        a_prev = a.copy()
        for i in range(1, m):
            a[i] = a_prev[i] + k * a_prev[m - i]
        a[m] = k
        f[m:N] = fm + k * bm
        b[m - 1:N - 1] = bm + k * fm
        err *= (1 - k ** 2)
    return a, err / N


def psd_burg(rr_even: np.ndarray, fs_interp: float = 4.0, order: int = 16, n_freq: int = 512):
    """Maximum-Entropy-PSD über AR-Modell (Burg-Koeffizienten)."""
    order = min(order, len(rr_even) // 3)
    a, p_final = burg_ar(rr_even, order)
    freqs = np.linspace(0.001, fs_interp / 2, n_freq)
    k_arr = np.arange(order + 1)
    psd = np.empty(n_freq)
    for i, fr in enumerate(freqs):
        z = np.exp(-2j * np.pi * fr / fs_interp * k_arr)
        A = np.sum(a * z)
        psd[i] = p_final / (np.abs(A) ** 2)
    return freqs, psd


def band_power(freqs: np.ndarray, psd: np.ndarray, band: tuple) -> float:
    """Integriert die PSD über ein Frequenzband (Trapezregel) → Power in ms²."""
    mask = (freqs >= band[0]) & (freqs < band[1])
    if mask.sum() < 2:
        return 0.0
    return float(np.trapz(psd[mask], freqs[mask]))


def band_peak(freqs: np.ndarray, psd: np.ndarray, band: tuple):
    """
    Gibt Gipfelfrequenz [Hz] und zugehörige PSD [ms²/Hz] im Band zurück.
    Rückgabe: (peak_freq_hz, peak_psd) oder (nan, nan) wenn zu wenige Punkte.
    """
    mask = (freqs >= band[0]) & (freqs < band[1])
    if mask.sum() < 2:
        return float("nan"), float("nan")
    idx = int(np.argmax(psd[mask]))
    peak_freq = float(freqs[mask][idx])
    peak_psd  = float(psd[mask][idx])
    return peak_freq, peak_psd


def compute_frequency_domain(rr_ms: np.ndarray, t_s: np.ndarray, method: str = "welch",
                              fs_interp: float = 4.0, burg_order: int = 16) -> Optional[dict]:
    """
    Vollständige Frequenzdomänen-Analyse einer RR-Zeitreihe.

    method: "welch" (FFT) oder "burg" (Maximum Entropy Method)

    Neue Parameter (NeuroFax-analog):
      lf_peak_freq   Hz  — Gipfelfrequenz im LF-Band (Mayer-Wellen ~0.1 Hz)
      lf_peak_psd    ms²/Hz — PSD-Amplitude am LF-Gipfel
      hf_peak_freq   Hz  — Gipfelfrequenz im HF-Band = respiratorische RSA
      hf_peak_psd    ms²/Hz — PSD-Amplitude am HF-Gipfel
      hf_resp_rate   /min — Atemfrequenzschätzung aus HF-Gipfel (hf_peak_freq × 60)
    """
    # Guard: zu wenige oder ungültige Daten → None statt Crash
    if len(rr_ms) < 20 or len(t_s) < 20:
        return None
    if not np.all(np.isfinite(rr_ms)) or not np.all(np.isfinite(t_s)):
        return None
    if t_s[-1] <= t_s[0]:
        return None

    rr_even, t_even = resample_rr(rr_ms, t_s, fs_interp)

    if len(rr_even) < 20:
        return None

    gaps = gap_stats(t_s)

    if method == "burg":
        freqs, psd = psd_burg(rr_even, fs_interp, order=burg_order)
    else:
        freqs, psd = psd_welch(rr_even, fs_interp)

    vlf = band_power(freqs, psd, VLF_BAND)
    lf  = band_power(freqs, psd, LF_BAND)
    hf  = band_power(freqs, psd, HF_BAND)
    total = vlf + lf + hf
    lf_hf_ratio = lf / hf if hf > 0 else float("nan")

    lf_peak_freq, lf_peak_psd = band_peak(freqs, psd, LF_BAND)
    hf_peak_freq, hf_peak_psd = band_peak(freqs, psd, HF_BAND)
    hf_resp_rate = hf_peak_freq * 60.0 if hf_peak_freq == hf_peak_freq else float("nan")

    return {
        "freqs": freqs, "psd": psd, "method": method,
        "vlf_power": vlf, "lf_power": lf, "hf_power": hf,
        "total_power": total,
        "lf_norm": 100 * lf / (lf + hf) if (lf + hf) > 0 else float("nan"),
        "hf_norm": 100 * hf / (lf + hf) if (lf + hf) > 0 else float("nan"),
        "lf_hf_ratio": lf_hf_ratio,
        # Peak-Frequenzen (NeuroFax-analog: LF/NF Hz, Spitze)
        "lf_peak_freq": lf_peak_freq,
        "lf_peak_psd":  lf_peak_psd,
        "hf_peak_freq": hf_peak_freq,
        "hf_peak_psd":  hf_peak_psd,
        "hf_resp_rate": hf_resp_rate,
        # Lücken-Diagnostik (spektraler Confounder durch entfernte Schläge/Dropout)
        "max_gap_s":     gaps["max_gap_s"],
        "n_gaps":        gaps["n_gaps"],
        "gap_fraction":  gaps["gap_fraction"],
    }
