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


# ── W1: validierte R-Zacken-Detektion (publizierte Algorithmen) ────────────────
def refine_peaks(signal: np.ndarray, peaks, sfreq: float, win_ms: float = 50.0) -> np.ndarray:
    """Schiebt jede Detektion auf das echte R-Zacken-Maximum im ±win_ms-Fenster.

    Entscheidend für HRV: konsistente Fiducial-Punkte reduzieren Timing-Jitter (sonst
    stark überschätztes RMSSD/pNN50). Wird auf ALLE Detektoren gleich angewandt.
    """
    w = int(sfreq * win_ms / 1000.0)
    out = []
    for p in peaks:
        p = int(p)
        lo, hi = max(0, p - w), min(len(signal), p + w + 1)
        if hi > lo:
            out.append(lo + int(np.argmax(signal[lo:hi])))
    return np.array(sorted(set(out)), dtype=int)


def detect_r_peaks_validated(signal: np.ndarray, sfreq: float,
                             method: str = "hamilton") -> np.ndarray:
    """R-Zacken über einen **validierten, publizierten** Detektor (py-ecg-detectors) +
    konsistente Maximum-Verfeinerung. Fällt bei fehlender Lib/Fehler auf detect_r_peaks zurück.

    Methoden: 'hamilton' (Hamilton 2002, robust — Default), 'pan_tompkins' (Pan-Tompkins 1985),
    'christov' (Christov 2004), 'engzee' (Engelse-Zeelenberg), 'two_average' (Elgendi 2013).
    """
    try:
        from ecgdetectors import Detectors
    except Exception:
        return detect_r_peaks(signal, sfreq)
    det = Detectors(float(sfreq))
    fn = {
        "hamilton": det.hamilton_detector, "pan_tompkins": det.pan_tompkins_detector,
        "christov": det.christov_detector, "engzee": det.engzee_detector,
        "two_average": det.two_average_detector,
    }.get(method, det.hamilton_detector)
    try:
        raw = fn(np.asarray(signal, dtype=float))
    except Exception:
        return detect_r_peaks(signal, sfreq)
    if len(raw) < 3:
        return detect_r_peaks(signal, sfreq)
    return refine_peaks(signal, raw, sfreq)


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

    mean_rr = float(np.mean(rr_ms))
    sdnn    = float(np.std(rr_ms, ddof=1))
    # NN50: Absolutzahl aufeinanderfolgender NN-Intervalle mit Differenz > 50 ms.
    # NeuroFax gibt sowohl Absolutzahl (RR50) als auch Prozent (pNN50) aus.
    nn50    = int(np.sum(np.abs(successive_diff) > 50))
    # CV% = Variationskoeffizient direkt aus der RR-Zeitreihe (SDNN/mean_RR × 100).
    # Direkt aus float-Werten gerechnet, damit sich keine Rundungsfehler aus den
    # bereits gerundeten Anzeigewerten SDNN und mean_RR aufsummieren.
    cv_pct  = (sdnn / mean_rr * 100.0) if mean_rr > 0 else 0.0
    # pNN20 (Schwelle 20 ms) — sensitiver als pNN50 bei geringer Variabilität.
    nn20    = int(np.sum(np.abs(successive_diff) > 20))
    # Poincaré-Deskriptoren: SD1 (kurzfristig/vagal), SD2 (langfristig).
    sdsd    = float(np.std(successive_diff, ddof=1)) if len(successive_diff) > 1 else 0.0
    sd1     = float(np.sqrt(0.5) * sdsd)
    sd2     = float(np.sqrt(max(2.0 * sdnn**2 - 0.5 * sdsd**2, 0.0)))

    return {
        "mean_rr_ms": round(mean_rr, 1),
        "mean_hr_bpm": round(60000 / mean_rr, 1),
        "sdnn_ms": round(sdnn, 1),
        "cv_pct": round(cv_pct, 2),
        "rmssd_ms": round(float(np.sqrt(np.mean(successive_diff**2))), 1),
        "pnn50_pct": round(float(nn50 / len(successive_diff) * 100), 1),
        "nn50_count": nn50,
        "pnn20_pct": round(float(nn20 / len(successive_diff) * 100), 1),
        "sd1_ms": round(sd1, 1),
        "sd2_ms": round(sd2, 1),
        "sd2_sd1_ratio": round(sd2 / sd1, 2) if sd1 > 0 else None,
        "min_rr_ms": round(float(np.min(rr_ms)), 1),
        "max_rr_ms": round(float(np.max(rr_ms)), 1),
        "n_beats": len(rr_ms) + 1,
    }


def dfa_alpha1(rr_ms: np.ndarray, scale_min: int = 4, scale_max: int = 16):
    """Detrended Fluctuation Analysis — Kurzzeit-Skalenexponent α₁ (Peng et al. 1995).

    Misst die **fraktale Korrelationsstruktur** der RR-Reihe, nicht ihre Größe:
      α₁ ≈ 1.0  → gesunde 1/f-Dynamik („pink noise"), langreichweitig korreliert
      α₁ → 0.5  → unkorreliertes weißes Rauschen (Verlust der Korrelation:
                  Fatigue, autonome Dysregulation, hohe Belastung)
      α₁ → 1.5  → Brown'sches Rauschen (integriertes weißes Rauschen)

    Ablauf: (1) integriertes Profil y(k)=Σ(RR−mean); (2) in nicht überlappende
    Fenster der Länge n zerlegen; (3) je Fenster linearen Trend abziehen, RMS bilden;
    (4) F(n)=RMS über alle Fenster; (5) α₁ = Steigung von log F(n) über log n
    im Skalenbereich 4–16 Schläge.

    Rückgabe: dict(alpha1, scales, F) oder None (zu wenige Schläge).
    """
    x = np.asarray(rr_ms, dtype=float)
    N = len(x)
    if N < max(30, scale_max * 2):
        return None
    y = np.cumsum(x - x.mean())
    scales, F = [], []
    for n in range(scale_min, scale_max + 1):
        n_win = N // n
        if n_win < 1:
            continue
        t = np.arange(n)
        var_list = []
        for w in range(n_win):
            seg = y[w * n:(w + 1) * n]
            coef = np.polyfit(t, seg, 1)
            trend = np.polyval(coef, t)
            var_list.append(np.mean((seg - trend) ** 2))
        if var_list:
            F.append(float(np.sqrt(np.mean(var_list))))
            scales.append(n)
    if len(F) < 4:
        return None
    logn = np.log10(scales)
    logF = np.log10(F)
    alpha1 = float(np.polyfit(logn, logF, 1)[0])
    return {"alpha1": alpha1, "scales": np.array(scales), "F": np.array(F)}


def edr_from_ecg(ecg: np.ndarray, r_peaks: np.ndarray, fs: float,
                 resp_band=(0.1, 0.5), fs_interp: float = 4.0):
    """ECG-Derived Respiration (EDR) aus der R-Zacken-Amplituden-Modulation.

    Die Atmung verschiebt die elektrische Herzachse (Zwerchfell-/Thoraxbewegung) →
    die **R-Zacken-Amplitude** schwankt mit dem Atemzyklus. Aus dieser Modulation
    lässt sich ein Atemsignal rekonstruieren — auch wenn die respiratorische
    Sinusarrhythmie (RSA/HF-Peak) schwach ist. Einkanal-Ansatz (Moody et al. 1985).

    Ablauf: R-Amplituden je Schlag → PCHIP-Interpolation auf gleichmäßiges Raster →
    Bandpass 0.1–0.5 Hz (6–30 /min) → dominante Frequenz (Welch) = Atemfrequenz.

    Rückgabe: dict(t, edr, resp_freq_hz, resp_rate_bpm, quality, amp_t, amp) oder None.
    """
    from scipy.interpolate import PchipInterpolator
    from scipy.signal import butter, filtfilt, welch

    r_peaks = np.asarray(r_peaks)
    if len(r_peaks) < 8:
        return None
    amps = np.asarray(ecg, dtype=float)[r_peaks]
    t = r_peaks / fs
    if t[-1] - t[0] < 20:                      # < 20 s → Atemfrequenz nicht robust
        return None

    t_even = np.arange(t[0], t[-1], 1.0 / fs_interp)
    if len(t_even) < 32:
        return None
    edr = PchipInterpolator(t, amps)(t_even)
    edr = edr - edr.mean()

    nyq = fs_interp / 2.0
    try:
        b, a = butter(2, [resp_band[0] / nyq, min(resp_band[1] / nyq, 0.99)], btype="band")
        edr_bp = filtfilt(b, a, edr)
    except Exception:
        edr_bp = edr

    nperseg = int(min(len(edr_bp), fs_interp * 60))
    freqs, psd = welch(edr_bp, fs=fs_interp, nperseg=nperseg)
    band = (freqs >= resp_band[0]) & (freqs <= resp_band[1])
    if band.sum() < 2:
        return None
    fpk = float(freqs[band][np.argmax(psd[band])])
    # Qualität: spektrale Konzentration am Gipfel (Peak vs. Median im Atemband)
    _med = float(np.median(psd[band])) or 1e-30
    quality = float(np.max(psd[band]) / _med)

    return {
        "t": t_even, "edr": edr_bp,
        "resp_freq_hz": fpk, "resp_rate_bpm": fpk * 60.0,
        "quality": quality,
        "amp_t": t, "amp": amps - amps.mean(),
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
