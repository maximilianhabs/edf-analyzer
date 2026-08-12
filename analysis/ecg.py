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


# Hier stand bis 2026-08-12 eine zweite, TOTE EKG-Kette: `preprocess_ecg()` (Bandpass
# 0,5–40 Hz), `compute_rr_intervals()`, `compute_hrv_frequency_domain()` und die Klammer
# `run_ecg_analysis()`, die sie zusammensetzte. Sie wurde von niemandem aufgerufen, wich aber
# vom tatsächlich benutzten Weg ab — wer die Datei von oben las, musste schließen, die
# EKG-Kette beginne mit einem 0,5–40-Hz-Vorfilter. Sie tut es nicht.
#
# Der wirkliche Pfad: detect_r_peaks_polarity_safe() → build_rr_series() →
# compute_hrv_time_domain() bzw. analysis/hrv_freq.py::compute_frequency_domain().
# Der einzige Filter darin ist der 5–15-Hz-Bandpass INNERHALB von detect_r_peaks().
# Siehe docs/PREPROCESSING.md.


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
def detect_polarity_flip(signal: np.ndarray, sfreq: float, candidates=None,
                         half_win_ms: float = 60.0) -> bool:
    """Robuste Polaritäts-Entscheidung: vergleicht den Median der lokalen Extremwert-BETRÄGE
    (±half_win_ms um jeden Kandidaten-Peak) statt nur des Vorzeichens am Peak-Sample selbst —
    bei biphasischer QRS-Form kann ein Detektor auf einem kleinen positiven Nebenpunkt sitzen,
    während der dominante Ausschlag (z. B. tiefe S-Zacke) deutlich größer und negativ ist
    (gefunden 2026-08-08 an Referenzfall B). `candidates` = grobe Peak-Kandidaten (z. B. aus
    `detect_r_peaks`); wenn None, wird `detect_r_peaks` intern aufgerufen. Gibt True zurück,
    wenn geflippt werden sollte (R-Zacke ist im Rohsignal negativ dominant). Siehe
    [[project_edf_rhythm_screening]] für die Herleitung und den zugehörigen Nachverfeinerungs-
    Bug in `refine_peaks`/`detect_r_peaks`, den dieser Flip VOR der Verfeinerung vermeidet."""
    if candidates is None:
        candidates = detect_r_peaks(signal, sfreq)
    if len(candidates) == 0:
        return False
    half_w = int(half_win_ms / 1000.0 * sfreq)
    max_amps, min_amps = [], []
    for p in candidates:
        lo, hi = max(0, p - half_w), min(len(signal), p + half_w)
        seg = signal[lo:hi]
        if len(seg):
            max_amps.append(seg.max()); min_amps.append(seg.min())
    if not max_amps:
        return False
    return bool(abs(np.median(min_amps)) > abs(np.median(max_amps)))


def detect_r_peaks_polarity_safe(signal: np.ndarray, sfreq: float) -> tuple:
    """Kompletter, bugfreier Erkennungspfad: grobe Kandidaten (polaritätsunabhängig) → Flip-
    Entscheidung → bei Bedarf flippen → ERST DANACH exakt verfeinern. Vermeidet den Bug, bei
    dem `refine_peaks`/`detect_r_peaks`s interne argmax-Verfeinerung bei invertiertem Kanal
    auf einen Nebenpunkt statt die echte R-Zacke springt (strukturierte statt zufällige
    Zeitfehler → sichtbare Cluster im Tachogramm, siehe [[project_edf_rhythm_screening]]).

    Rückgabe: (signal_polaritaetskorrigiert, peaks, was_flipped).
    """
    candidates = detect_r_peaks(signal, sfreq)
    was_flipped = detect_polarity_flip(signal, sfreq, candidates)
    sig = -signal if was_flipped else signal
    peaks = refine_peaks(sig, candidates, sfreq, win_ms=40.0) if len(candidates) else candidates
    return sig, peaks, was_flipped


def flip_diagnostic(signal: np.ndarray, sfreq: float) -> dict:
    """Diagnose-Hilfsfunktion NUR für die UI-Visualisierung "mit vs. ohne Flip" (User-Anfrage
    2026-08-08) — reproduziert bewusst den alten, fehleranfälligen Pfad (Peak-Erkennung/
    -verfeinerung VOR dem Flip) neben dem korrigierten Pfad, um den Effekt an der konkreten
    Aufnahme sichtbar zu machen. NICHT für die eigentliche Analyse verwenden — dafür
    `detect_r_peaks_polarity_safe()`.

    Rückgabe: {"rr_ohne_ms", "t_ohne_s", "rr_mit_ms", "t_mit_s", "std_ohne", "std_mit",
    "was_flipped"}.
    """
    candidates = detect_r_peaks(signal, sfreq)
    peaks_ohne = refine_peaks(signal, candidates, sfreq, win_ms=40.0) if len(candidates) else candidates
    rr_ohne = np.diff(peaks_ohne) / sfreq * 1000.0
    t_ohne = peaks_ohne[:-1] / sfreq

    sig_mit, peaks_mit, was_flipped = detect_r_peaks_polarity_safe(signal, sfreq)
    rr_mit = np.diff(peaks_mit) / sfreq * 1000.0
    t_mit = peaks_mit[:-1] / sfreq

    return {"rr_ohne_ms": rr_ohne, "t_ohne_s": t_ohne, "rr_mit_ms": rr_mit, "t_mit_s": t_mit,
            "std_ohne": float(np.std(rr_ohne)) if len(rr_ohne) else float("nan"),
            "std_mit": float(np.std(rr_mit)) if len(rr_mit) else float("nan"),
            "was_flipped": was_flipped}


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


#: Rückgabe von :func:`detect_r_peaks_validated_ex` — trägt neben den Peaks IMMER mit, welcher
#: Detektor tatsächlich gelaufen ist. Ohne diese Information beschriften die Aufrufer das
#: Ergebnis falsch: `detect_r_peaks_validated()` fällt in DREI Fällen still auf den eigenen
#: Detektor zurück (Bibliothek fehlt, Detektor wirft, zu wenige Peaks). Vorher stand dann z. B.
#: „Hamilton 2002 (py-ecg-detectors)" über Zahlen des eigenen Detektors, und die
#: Vergleichsspalten „Standard (eigen)" / „Validiert" im Report zeigten identische Werte,
#: obwohl sie einen Methodenvergleich behaupteten.
@dataclass
class DetectorResult:
    peaks: np.ndarray
    method: str        # tatsächlich gelaufen: "hamilton"/"pan_tompkins"/… oder "eigen"
    fell_back: bool    # True = der angeforderte validierte Detektor lief NICHT
    reason: str = ""   # nur bei fell_back gesetzt, für Anzeige/Diagnose
    coverage_gaps: tuple = ()   # ((start_s, end_s), …) Abschnitte ohne einen einzigen Schlag
    coverage_frac: float = 1.0  # Anteil der Aufnahme mit plausibler Schlagfolge

    @property
    def is_validated(self) -> bool:
        return not self.fell_back

    @property
    def has_coverage_gap(self) -> bool:
        """True, wenn der Detektor über einen längeren Abschnitt gar nichts gefunden hat.

        Das ist der gefährlichere Fehlerfall gegenüber `fell_back`: dort weiß man, dass
        etwas anderes gerechnet wurde. Hier liefert der Detektor ein Ergebnis, das plausibel
        AUSSIEHT und dem ein Drittel der Aufnahme fehlt (nachgewiesen für Hamilton und
        Pan-Tompkins nach einem Amplitudensprung, siehe
        tests/test_ecg_pipeline.py::test_hamilton_und_pan_tompkins_brechen_nach_dem_
        amplitudensprung_ab). Eine HRV-Auswertung darauf wäre falsch, ohne dass es auffiele.
        """
        return bool(self.coverage_gaps)


_VALIDATED_METHODS = ("hamilton", "pan_tompkins", "christov", "engzee", "two_average")


def validated_detectors_available() -> bool:
    """True, wenn py-ecg-detectors installiert ist. Für die Oberfläche gedacht, damit sie
    validierte Detektoren gar nicht erst als wählbar anbietet, statt sie anzubieten und dann
    stillschweigend etwas anderes zu rechnen."""
    try:
        import ecgdetectors  # noqa: F401
        return True
    except Exception:
        return False


#: Ab dieser Lücke ohne einen einzigen Schlag gilt ein Abschnitt als nicht abgedeckt.
#: 10 s sind rund 10–15 Schläge — das ist keine Bradykardie mehr und keine einzelne
#: verpasste R-Zacke, sondern ein ausgefallener Detektor. Bewusst großzügig: eine echte
#: Asystolie dieser Länge wäre ebenfalls ein Befund, den man sehen will.
COVERAGE_GAP_S = 10.0


def coverage_gaps(peaks: np.ndarray, sfreq: float, duration_s: float,
                  min_gap_s: float = COVERAGE_GAP_S):
    """Abschnitte, in denen der Detektor über `min_gap_s` hinweg nichts gefunden hat.

    Geprüft wird auch der Anfang und das Ende der Aufnahme, nicht nur die Abstände zwischen
    Schlägen — genau dort trat der reale Fall auf: die Detektoren hörten bei 409 s auf und
    die letzten 190 s blieben leer, ohne dass zwischen zwei Schlägen je eine Lücke stand.
    """
    if duration_s <= 0:
        return ()
    if len(peaks) == 0:
        return ((0.0, float(duration_s)),)
    t = np.asarray(peaks, dtype=float) / float(sfreq)
    grenzen = np.concatenate(([0.0], t, [float(duration_s)]))
    luecken = []
    for a, b in zip(grenzen[:-1], grenzen[1:]):
        if b - a >= min_gap_s:
            luecken.append((round(float(a), 1), round(float(b), 1)))
    return tuple(luecken)


def _with_coverage(res: "DetectorResult", sfreq: float, duration_s: float) -> "DetectorResult":
    luecken = coverage_gaps(res.peaks, sfreq, duration_s)
    fehlend = sum(b - a for a, b in luecken)
    return DetectorResult(res.peaks, res.method, res.fell_back, res.reason,
                          luecken,
                          round(max(0.0, 1.0 - fehlend / duration_s), 4) if duration_s else 1.0)


def detect_r_peaks_validated_ex(signal: np.ndarray, sfreq: float,
                                method: str = "hamilton") -> DetectorResult:
    """Wie :func:`detect_r_peaks_validated`, gibt aber zusätzlich zurück, welcher Detektor
    wirklich gelaufen ist. Für alles verwenden, was das Ergebnis benennt oder es dem eigenen
    Detektor gegenüberstellt.

    Methoden: 'hamilton' (Hamilton 2002, robust — Default), 'pan_tompkins' (Pan-Tompkins 1985),
    'christov' (Christov 2004), 'engzee' (Engelse-Zeelenberg), 'two_average' (Elgendi 2013).
    """
    dauer_s = len(signal) / float(sfreq) if sfreq else 0.0

    def _fallback(reason: str) -> DetectorResult:
        return _with_coverage(
            DetectorResult(detect_r_peaks(signal, sfreq), "eigen", True, reason),
            sfreq, dauer_s)

    try:
        from ecgdetectors import Detectors
    except Exception:
        return _fallback("py-ecg-detectors ist nicht installiert")

    if method not in _VALIDATED_METHODS:
        return _fallback(f"unbekannte Methode {method!r}")

    det = Detectors(float(sfreq))
    fn = {
        "hamilton": det.hamilton_detector, "pan_tompkins": det.pan_tompkins_detector,
        "christov": det.christov_detector, "engzee": det.engzee_detector,
        "two_average": det.two_average_detector,
    }[method]
    try:
        raw = fn(np.asarray(signal, dtype=float))
    except Exception as exc:
        return _fallback(f"Detektor brach ab ({exc.__class__.__name__})")
    if len(raw) < 3:
        return _fallback(f"nur {len(raw)} R-Zacken erkannt (mind. 3 nötig)")
    return _with_coverage(
        DetectorResult(refine_peaks(signal, raw, sfreq), method, False), sfreq, dauer_s)


def detect_r_peaks_validated(signal: np.ndarray, sfreq: float,
                             method: str = "hamilton") -> np.ndarray:
    """Nur die Peaks — für Aufrufer, die das Ergebnis NICHT nach Methode benennen.
    Wer beschriftet oder vergleicht, nimmt :func:`detect_r_peaks_validated_ex`."""
    return detect_r_peaks_validated_ex(signal, sfreq, method).peaks


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


def dfa_alpha12(rr_ms: np.ndarray, scales1=(4, 16), scales2=(16, 64), overlap: float = 0.5):
    """DFA mit **überlappenden** Fenstern und BEIDEN Skalensteigungen (G6, Goldstandard).

    Ergänzt `dfa_alpha1` (nicht überlappend, nur α₁) — diese bleibt Default in den
    bestehenden Seiten. Hier:
      α₁ = Kurzzeit-Steigung (4–16 Schläge)  · vagale/schnelle Regulation
      α₂ = Langzeit-Steigung (16–64 Schläge) · langsame/sympathische & humorale Anteile
    Überlappende Fenster (50 %) verbessern die Statistik je Skala (Peng 1995; Standard-DFA).

    Rückgabe: {alpha1, alpha2, scales, F} oder None (zu kurze Reihe; α₂ braucht ~≥256 Schläge).
    """
    x = np.asarray(rr_ms, dtype=float)
    n_beats = len(x)
    if n_beats < 32:
        return None
    y = np.cumsum(x - x.mean())

    def _F(n: int) -> float:
        step = max(1, int(round(n * (1.0 - overlap))))
        idx = np.arange(n)
        res = []
        for s in range(0, n_beats - n + 1, step):
            seg = y[s:s + n]
            p = np.polyfit(idx, seg, 1)
            res.append(np.mean((seg - np.polyval(p, idx)) ** 2))
        return float(np.sqrt(np.mean(res))) if res else float("nan")

    scales = sorted(set(list(range(scales1[0], scales1[1] + 1)) +
                        list(range(scales2[0], scales2[1] + 1, 2))))
    scales = [n for n in scales if n <= n_beats // 4]
    if len(scales) < 4:
        return None
    F = {n: _F(n) for n in scales}

    def _slope(lo, hi):
        ns = [n for n in scales if lo <= n <= hi and F[n] == F[n] and F[n] > 0]
        if len(ns) < 3:
            return float("nan")
        return float(np.polyfit(np.log10(ns), np.log10([F[n] for n in ns]), 1)[0])

    return {"alpha1": _slope(*scales1), "alpha2": _slope(*scales2),
            "scales": scales, "F": [F[n] for n in scales]}
