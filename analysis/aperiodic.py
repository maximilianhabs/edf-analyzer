"""
Aperiodische 1/f-Komponente des EEG-Spektrums (schlanke specparam-Variante).

Ein EEG-Leistungsspektrum ist die Summe aus
  1. einem aperiodischen Anteil  — im log-log-Raum eine fallende Gerade
     L(f) = offset − exponent · log10(f)
  2. periodischen Gipfeln         — echte Oszillationen (Alpha, Beta …), die
     über dem aperiodischen Untergrund herausragen.

Der aperiodische Exponent (Steilheit) ist ein eigenständiger Marker:
- flacher  → relativ mehr Exzitation / höhere Vigilanz
- steiler  → relativ mehr Inhibition / Schläfrigkeit, Sedierung, Schlaf
und flacht physiologisch mit dem Alter ab.

Kein Knee-Term (bewusst schlank gehalten): für den Fit-Bereich 1–40 Hz ist die
log-log-Kurve i.d.R. hinreichend gerade.

Methode (robuster iterativer Fit, „sigma-clipping"):
  1. Gerade per Kleinste-Quadrate an log10(PSD) über log10(f) fitten.
  2. Punkte, die deutlich ÜBER der Geraden liegen (= oszillatorische Gipfel),
     verwerfen und neu fitten. Iterieren, bis stabil.
  → Die Gipfel ziehen die Gerade dadurch nicht künstlich nach oben; der Fit
    beschreibt den echten 1/f-Untergrund.

Quellen:
- Donoghue et al. (2020) Nat Neurosci 23:1655 — specparam / FOOOF
- Gao, Peterson & Voytek (2017) NeuroImage 158:70 — E/I-Balance
- Voytek et al. (2015) J Neurosci 35:13257 — Abflachung mit dem Alter
- He (2014) Trends Cogn Sci 18:480 — scale-free dynamics
"""

from __future__ import annotations

import numpy as np
from typing import Optional


def welch_psd(sig: np.ndarray, fs: float, fmax: float = 45.0):
    """Leistungsspektraldichte via Welch (4-s-Hann-Epochen, 50 % Überlapp).

    Eigenständig gehalten (nicht die 1–30-Hz-begrenzte PSD des Spektrum-Moduls),
    damit der aperiodische Fit bis fmax (> klinische Bänder) reicht.
    """
    from scipy.signal import welch
    nperseg = int(min(len(sig) // 2, max(64, fs * 4)))
    if nperseg < 64:
        return None, None
    freqs, psd = welch(sig, fs=fs, nperseg=nperseg,
                       noverlap=nperseg // 2, scaling="density")
    m = (freqs > 0) & (freqs <= fmax)
    return freqs[m], psd[m]


def fit_aperiodic(freqs: np.ndarray, psd: np.ndarray,
                  fmin: float = 1.0, fmax: float = 40.0,
                  n_iter: int = 6, clip: float = 2.0) -> Optional[dict]:
    """Schätzt Offset + Exponent des aperiodischen Untergrunds (kein Knee).

    Rückgabe-Dict:
      freqs      Frequenzachse im Fit-Bereich (Hz)
      psd        Original-PSD im Fit-Bereich
      aper_psd   aperiodischer Fit als PSD (10**aper_log)
      ratio      PSD / aperiodischer Fit  (>1 = oszillatorischer Gipfel)
      offset     log10-Power-Achsenabschnitt bei 1 Hz
      exponent   Steilheit (positiv; steiler = größer)
      r2         Fit-Güte auf dem Untergrund (peak-bereinigte Punkte), 0–1
      peak_mask  bool-Array: Punkte, die als Gipfel gewertet wurden
    """
    m = (freqs >= fmin) & (freqs <= fmax) & np.isfinite(psd) & (psd > 0)
    f = freqs[m]
    p = psd[m]
    if len(f) < 8:
        return None

    logf = np.log10(f)
    logp = np.log10(p)

    keep = np.ones(len(f), dtype=bool)
    offset, slope = 0.0, 0.0
    for _ in range(n_iter):
        A = np.vstack([np.ones(int(keep.sum())), logf[keep]]).T
        coef, *_ = np.linalg.lstsq(A, logp[keep], rcond=None)
        offset, slope = float(coef[0]), float(coef[1])
        resid = logp - (offset + slope * logf)
        s = float(np.std(resid[keep])) or 1e-9
        new_keep = resid < clip * s          # nur positive Ausreißer (Gipfel) verwerfen
        if int(new_keep.sum()) < 4:
            break
        if np.array_equal(new_keep, keep):
            break
        keep = new_keep

    aper_log = offset + slope * logf
    ss_res = float(np.sum((logp[keep] - aper_log[keep]) ** 2))
    ss_tot = float(np.sum((logp[keep] - np.mean(logp[keep])) ** 2)) or 1e-9
    r2 = 1.0 - ss_res / ss_tot

    return {
        "freqs": f,
        "psd": p,
        "aper_psd": 10 ** aper_log,
        "ratio": p / (10 ** aper_log),
        "offset": offset,
        "exponent": float(-slope),
        "r2": float(r2),
        "peak_mask": ~keep,
    }


def flattened_power(res: dict, lo: float, hi: float) -> float:
    """Fläche unter dem untergrund-bereinigten („flattened") Spektrum im Band [lo,hi].

    Entspricht FOOOF `_spectrum_flat` (Maschke 2025): log10(PSD/aperiodik) über das Band
    integriert. Der 1/f-Untergrund ist entfernt → nur der oszillatorische Gipfel bleibt.
    Werte > 0 zeigen echte Oszillationsleistung über dem Untergrund; ~0 = kein Gipfel.
    """
    f = res["freqs"]
    ratio = res["ratio"]
    band = (f >= lo) & (f < hi)
    if band.sum() < 2:
        return float("nan")
    flat = np.log10(np.clip(ratio[band], 1e-9, None))
    return float(np.trapezoid(flat, f[band]))


def band_power_defs(freqs: np.ndarray, psd: np.ndarray, lo: float, hi: float,
                    full=(1.0, 40.0), res: dict | None = None) -> dict:
    """Drei Standard-Definitionen der Bandleistung (Maschke 2025):
      - absolute: log10(Fläche unter der PSD im Band)
      - relative: Fläche im Band / Fläche im Gesamtspektrum (full) × 100
      - flattened: Fläche unter dem aperiodik-bereinigten Spektrum (nur wenn res übergeben).
    """
    m = (freqs >= lo) & (freqs < hi)
    mf = (freqs >= full[0]) & (freqs < full[1])
    area = float(np.trapezoid(psd[m], freqs[m])) if m.sum() > 1 else 0.0
    total = float(np.trapezoid(psd[mf], freqs[mf])) if mf.sum() > 1 else 0.0
    return {
        "absolute": float(np.log10(area)) if area > 0 else float("nan"),
        "relative": (area / total * 100.0) if total > 0 else float("nan"),
        "flattened": flattened_power(res, lo, hi) if res is not None else float("nan"),
    }


def corrected_peak(res: dict, lo: float, hi: float) -> float:
    """Gipfelfrequenz im Band [lo,hi] aus dem UNTERGRUND-BEREINIGTEN Spektrum.

    Da der aperiodische Anteil abgezogen ist (ratio), ist dies der echte
    oszillatorische Gipfel — robuster als das Maximum des Rohspektrums.
    """
    f = res["freqs"]
    ratio = res["ratio"]
    band = (f >= lo) & (f < hi)
    if band.sum() < 2:
        return float("nan")
    seg = ratio[band]
    if np.max(seg) <= 1.0:          # kein Gipfel über dem Untergrund
        return float("nan")
    return float(f[band][int(np.argmax(seg))])
