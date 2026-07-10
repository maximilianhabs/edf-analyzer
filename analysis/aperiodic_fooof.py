"""W2 — FOOOF/specparam als validierte Aperiodik-Analyse (Add-on, parallel zum eigenen Fit).

Kapselt die Referenz-Implementierung (Donoghue et al. 2020) sauber weg: liefert Exponent,
Offset, optional Knee, R², Fehler, parametrisierte Gipfel (CF/PW/BW) sowie die Fit-Kurven
zum Überlagern. Fällt bei fehlender Lib auf None zurück (dann bleibt nur der eigene Fit).
Verändert die bestehende Analyse NICHT.
"""

from __future__ import annotations

import numpy as np


def fit_fooof(freqs, psd, fmin: float = 1.0, fmax: float = 40.0, knee: bool = False):
    """FOOOF-Fit über [fmin, fmax]. knee=True → aperiodic_mode='knee'. Gibt Dict oder None."""
    try:
        from fooof import FOOOF
    except Exception:
        return None
    mode = "knee" if knee else "fixed"
    fm = FOOOF(peak_width_limits=[1.0, 8.0], max_n_peaks=6,
               aperiodic_mode=mode, verbose=False)
    try:
        fm.fit(np.asarray(freqs, float), np.asarray(psd, float), [float(fmin), float(fmax)])
    except Exception:
        return None
    ap = fm.get_params("aperiodic_params")
    if mode == "knee":
        offset, knee_v, exponent = float(ap[0]), float(ap[1]), float(ap[2])
    else:
        offset, exponent, knee_v = float(ap[0]), float(ap[1]), None
    peaks = (fm.peak_params_.tolist()
             if fm.peak_params_ is not None and len(fm.peak_params_) else [])
    return {
        "mode": mode, "exponent": exponent, "offset": offset, "knee": knee_v,
        "r2": float(fm.r_squared_), "error": float(fm.error_),
        "peaks": peaks,                                   # [[CF Hz, PW, BW Hz], …]
        "fit_freqs": fm.freqs.tolist(),
        "ap_fit_lin": (10 ** fm._ap_fit).tolist(),        # aperiodische Kurve (linear)
        "full_fit_lin": (10 ** fm.fooofed_spectrum_).tolist(),  # Gesamtmodell (linear)
    }
