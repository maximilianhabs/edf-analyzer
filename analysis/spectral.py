"""Spektrale Grundrechnungen — die Schicht unter der Oberfläche.

Diese Funktionen lagen bis 2026-08-12 in `views/eeg_spectrum.py`, also in der UI-Schicht.
Das war nicht bloss unordentlich: `analysis/report_export.py` und `analysis/glory_report.py`
importierten sie von dort — die Analyseschicht hing damit an der Oberfläche, und ein Lauf
ohne Streamlit (CLI, Batch, fremdes Notebook) war unmöglich.

Beim Herausziehen hat sich gezeigt, wie oberflächlich die Verflechtung war: **keine einzige
dieser Funktionen benutzt Streamlit**. Es war reine Signalverarbeitung in der falschen Datei.
Entsprechend ist hier nichts umgeschrieben, nur verschoben — die Zeilen sind identisch, und
die Sektionswerte des Reports wurden vor und nach dem Verschieben verglichen.

`views/eeg_spectrum.py` importiert die Namen weiterhin, damit dortiger Code unverändert
bleibt; wer neu schreibt, nimmt sie von hier.

Regel für dieses Verzeichnis: `analysis/` darf nichts aus `views/` importieren und nichts
über Streamlit wissen. `tools/check_layering.py` prüft das.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, filtfilt
from scipy.signal.windows import dpss

#: Obergrenze des Ausgabebandes. Delta beginnt bei 1 Hz — bewusst, siehe
#: docs/PREPROCESSING.md (Schwitz-/Driftartefakte unterhalb 1 Hz).
FREQ_MAX = 30.0


def _highpass(sig: np.ndarray, fs: float, cutoff: float = 1.0) -> np.ndarray:
    """1 Hz Hochpassfilter — entfernt DC-Drift und Bewegungsartefakte."""
    nyq = fs / 2
    b, a = butter(4, cutoff / nyq, btype="high")
    return filtfilt(b, a, sig)


def _band_power(freqs, psd, lo, hi):
    mask = (freqs >= lo) & (freqs < hi)
    return float(np.trapezoid(psd[mask], freqs[mask])) if mask.sum() > 1 else 0.0


def _peak_freq(freqs, psd, lo, hi):
    mask = (freqs >= lo) & (freqs < hi)
    return float(freqs[mask][np.argmax(psd[mask])]) if mask.sum() > 1 else float("nan")


# Bänder für die dominanzabhängige Peak-Erkennung (User-Konzept 2026-08-08): Delta-
# Untergrenze bewusst 0,5Hz statt der 1,0Hz-Grenze in BANDS/BAND_DICT (dort für Bandpower-
# Ratios etabliert, hier NICHT verändert) — sonst ließe sich ein sehr langsames Delta
# (z. B. 0,5-0,8Hz bei schwerer Enzephalopathie/Koma) nicht von einem saubereren 1,5-2Hz-
# Delta unterscheiden, genau der vom User genannte Anwendungsfall.


def _spectral_edge(freqs, psd, pct):
    """Spektrale Edge-Frequenz: Frequenz, unter der pct der Gesamtleistung liegt.

    pct=0.95 → SEF95 (Vigilanz-/Sedierungs-/Enzephalopathie-Marker), pct=0.50 →
    Medianfrequenz. Sinkt bei Verlangsamung. Berechnet über das Analyseband (1–30 Hz)
    per kumulierter Leistung mit linearer Interpolation zwischen den Bins.
    """
    if len(freqs) < 2:
        return float("nan")
    cum = np.cumsum(psd)
    tot = cum[-1]
    if tot <= 0:
        return float("nan")
    cum = cum / tot
    idx = int(np.searchsorted(cum, pct))
    if idx == 0:
        return float(freqs[0])
    if idx >= len(freqs):
        return float(freqs[-1])
    # lineare Interpolation zwischen idx-1 und idx für Sub-Bin-Genauigkeit
    c0, c1 = cum[idx - 1], cum[idx]
    f0, f1 = freqs[idx - 1], freqs[idx]
    if c1 == c0:
        return float(f1)
    return float(f0 + (pct - c0) / (c1 - c0) * (f1 - f0))


def _peak_freq_cog(freqs, psd, lo, hi):
    """Alpha-Peak per Schwerpunkt (Center of Gravity / Individual Alpha Frequency).

    Robuster als roher argmax: bei bimodalem Alpha (z.B. Gipfel bei 9 und 11 Hz)
    springt argmax instabil, der Schwerpunkt liefert einen stabilen Mittelwert.

    Vor der Schwerpunktbildung wird eine **lineare Baseline** zwischen den
    Bandrändern abgezogen (Näherung des 1/f-Untergrunds + Theta-Ausläufer),
    damit die absteigende Flanke des Theta-Bandes den Schwerpunkt nicht
    künstlich nach unten zieht (Klimesch, Individual Alpha Frequency).

    CoG = Σ(fᵢ·Pᵢ) / Σ(Pᵢ)  über das (baseline-korrigierte) Alpha-Band.
    """
    mask = (freqs >= lo) & (freqs < hi)
    if mask.sum() < 3:
        return float("nan")
    f = freqs[mask]
    p = psd[mask].astype(float).copy()
    # 1/f-/Theta-Untergrund als Gerade zwischen den Bandrändern approximieren
    baseline = np.linspace(p[0], p[-1], len(p))
    p = p - baseline
    p[p < 0] = 0.0
    if p.sum() <= 0:
        return float("nan")
    return float(np.sum(f * p) / np.sum(p))


def _epoch_starts(n: int, nperseg: int):
    """Startindizes überlappender Epochen (50 % Überlapp)."""
    step = nperseg // 2
    return list(range(0, n - nperseg + 1, step))


def _compute_psd(sig, fs, nperseg=None, multitaper=False, amp_thresh_uv=9999.0):
    """Leistungsspektraldichte (Welch oder Multitaper), epochenweise gemittelt.

    Artefaktbehandlung: Epochen, deren Peak-to-Peak-Amplitude > amp_thresh_uv liegt,
    werden **komplett aus dem Mittel weggelassen** (statt per linearer Brücke
    interpoliert — das erzeugte Steigungssprünge und spektrales Splatter). Bleiben
    zu wenige saubere Epochen übrig (< 1), wird ausnahmsweise die gesamte (auch
    artefaktbehaftete) Epochenmenge verwendet, damit weiterhin ein Spektrum entsteht.
    """
    nperseg = nperseg or min(int(fs * 4), len(sig) // 2, 1024)
    if nperseg < 64:
        return None, None

    starts = _epoch_starts(len(sig), nperseg)
    if not starts:
        return None, None

    # Saubere Epochen selektieren (ptp <= Schwelle); Fallback auf alle Epochen
    clean_starts = [i for i in starts if np.ptp(sig[i:i + nperseg]) <= amp_thresh_uv]
    if not clean_starts:
        clean_starts = starts

    freqs = np.fft.rfftfreq(nperseg, d=1.0 / fs)

    if multitaper:
        # Thomson (1982) DPSS — NW=3, K=5 gut für Alpha-Detektion (bandwidth ≈ 1.5 Hz)
        NW, K = 3, 5
        tapers, eigs = dpss(nperseg, NW, K, return_ratios=True)
        psds = []
        for i in clean_starts:
            epoch = sig[i:i + nperseg]
            epoch = epoch - epoch.mean()
            ep_psd = np.zeros(len(freqs))
            w_sum = 0.0
            for taper, eig in zip(tapers, eigs):
                if eig < 0.9:
                    continue
                tapered = epoch * taper
                fft_coeffs = np.fft.rfft(tapered)
                ep_psd += eig * (np.abs(fft_coeffs) ** 2) / (fs * np.sum(taper ** 2))
                w_sum += eig
            if w_sum > 0:
                psds.append(ep_psd / w_sum)
    else:
        # Welch, epochenweise (Hann-Fenster, Density-Skalierung wie scipy.welch)
        win = np.hanning(nperseg)
        U = np.sum(win ** 2)                       # Fensterleistung
        scale_2s = np.full(len(freqs), 2.0)        # einseitiges Spektrum: ×2 …
        scale_2s[0] = 1.0                          # … außer DC
        if nperseg % 2 == 0:
            scale_2s[-1] = 1.0                     # … und Nyquist (bei gerader Länge)
        psds = []
        for i in clean_starts:
            epoch = sig[i:i + nperseg]
            epoch = epoch - epoch.mean()           # detrend='constant'
            X = np.fft.rfft(epoch * win)
            psds.append(scale_2s * (np.abs(X) ** 2) / (fs * U))

    if not psds:
        return None, None
    psd = np.mean(psds, axis=0)

    mask = (freqs >= 1.0) & (freqs <= FREQ_MAX)
    return freqs[mask], psd[mask]
