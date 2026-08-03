"""W3 — Lomb-Scargle-Periodogramm für HRV (Add-on, parallel zu Welch/Burg).

Interpolationsfreies Spektrum direkt aus den **ungleichmäßig** getakteten RR-Intervallen —
Goldstandard bei Lücken/Ektopie, weil kein Resampling nötig ist (Laguna 1998, Moody 1993).
Verändert die bestehende HRV-Frequenzanalyse NICHT.

Hinweis: Absolute ms²-Kalibrierung ist methodenabhängig; klinisch belastbar und
methodenrobust sind **LF/HF, LFnu, HFnu** (Ratios/normalisierte Einheiten) — die geben wir aus.
Bandpower in relativen Einheiten dient nur der Form/den Ratios.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import lombscargle

VLF_BAND = (0.0033, 0.04)
LF_BAND = (0.04, 0.15)
HF_BAND = (0.15, 0.40)


def lombscargle_hrv(rr_ms, t_s, n_freq: int = 1000):
    """RR-Reihe (ms) an ihren echten Zeitpunkten (s) → Lomb-Scargle-Periodogramm + HRV-Kennzahlen."""
    t = np.asarray(t_s, dtype=float)
    y = np.asarray(rr_ms, dtype=float)
    m = min(len(t), len(y))
    t, y = t[:m], y[:m]
    if m < 20:
        return None
    t = t - t[0]
    y = y - y.mean()                          # Detrend (Mittel entfernen)
    if not np.any(np.abs(y) > 0):
        return None

    freqs = np.linspace(VLF_BAND[0], HF_BAND[1], n_freq)
    ang = 2.0 * np.pi * freqs
    P = lombscargle(t, y, ang, normalize=False)
    psd = P * 2.0 / m                          # rel. PSD (arbiträr, konsistent → für Form+Ratios)

    def _bp(band):
        mk = (freqs >= band[0]) & (freqs < band[1])
        return float(np.trapezoid(psd[mk], freqs[mk])) if mk.sum() > 1 else 0.0

    def _peak(band):
        mk = (freqs >= band[0]) & (freqs < band[1])
        return float(freqs[mk][np.argmax(psd[mk])]) if mk.sum() > 1 else float("nan")

    vlf, lf, hf = _bp(VLF_BAND), _bp(LF_BAND), _bp(HF_BAND)
    lf_hf = lf / hf if hf > 0 else float("nan")
    lf_nu = lf / (lf + hf) * 100 if (lf + hf) > 0 else float("nan")
    hf_nu = hf / (lf + hf) * 100 if (lf + hf) > 0 else float("nan")
    return {
        "freqs": freqs, "psd": psd,
        "vlf": vlf, "lf": lf, "hf": hf, "total": vlf + lf + hf,
        "lf_hf_ratio": lf_hf, "lf_norm": lf_nu, "hf_norm": hf_nu,
        "lf_peak_freq": _peak(LF_BAND), "hf_peak_freq": _peak(HF_BAND),
        "n_beats": m + 1,
    }
