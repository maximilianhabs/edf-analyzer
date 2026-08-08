"""
EKG-Signalqualität / Artefakt-Plausibilität — Stufe ① der Rhythmus-Screening-Pipeline.

Bewertet, ob ein EKG-Segment überhaupt verlässliche R-Zacken für eine Rhythmus-
Beurteilung liefert — VOR jeder AFib-/Ektopie-Klassifikation. Ohne diese Stufe
werden Signalartefakte (Sättigung, Diskonnektion, Bewegung) leicht als schwere
Rhythmusstörung fehlgedeutet (siehe Fall CA17734W: Verstärker-Sättigung erzeugte
scheinbar chaotische RR-Werte, die ohne Prüfung wie AFib ausgesehen hätten).

Regeln 1–4 nach Orphanidou et al. 2015 (IEEE J Biomed Health Inform 19(3):832-838),
validiert an 1500 handklassifizierten 10s-EKG-Segmenten (Sensitivität 94%,
Spezifität 97%). Regeln 5–6 (Flatline, Amplituden-Plausibilität) sind eine eigene
Ergänzung — Orphanidou deckt Sättigung/Diskonnektion nicht zuverlässig ab, wenn
dabei (fälschlich) Peaks an den Klipp-Kanten erkannt werden statt einer Lücke.
"""
from __future__ import annotations

import numpy as np


def _template_correlation(sig: np.ndarray, r_peaks: np.ndarray, fs: float) -> float:
    """Mittlere Korrelation jedes Schlags mit dem Segment-Durchschnitts-QRS
    (Orphanidou Schritt 'Adaptive template matching'). Fensterbreite = Median-RR."""
    if len(r_peaks) < 3:
        return float("nan")
    rr = np.diff(r_peaks)
    half_w = int(np.median(rr) / 2)
    if half_w < 2:
        return float("nan")
    beats = []
    for p in r_peaks:
        lo, hi = p - half_w, p + half_w
        if lo < 0 or hi > len(sig):
            continue
        beats.append(sig[lo:hi])
    if len(beats) < 3:
        return float("nan")
    beats = np.array(beats)
    template = beats.mean(axis=0)
    if np.std(template) == 0:
        return float("nan")
    corrs = [np.corrcoef(b, template)[0, 1] for b in beats if np.std(b) > 0]
    if not corrs:
        return float("nan")
    return float(np.mean(corrs))


def flatline_mask(sig: np.ndarray, fs: float, win_ms: float = 300.0,
                   std_thresh_uv: float = 5.0) -> np.ndarray:
    """Boolesche Maske (Samplerate von `sig`): True = quasi variationslos
    (Sättigung/Diskonnektion), rollierende Std über `win_ms`-Fenster."""
    win = max(1, int(win_ms / 1000.0 * fs))
    n = len(sig)
    flat = np.zeros(n, dtype=bool)
    step = max(1, win // 2)
    for i in range(0, n, step):
        lo, hi = max(0, i - win), min(n, i + win)
        if np.std(sig[lo:hi]) < std_thresh_uv:
            flat[lo:hi] = True
    return flat


def segment_sqi(sig: np.ndarray, r_peaks: np.ndarray, fs: float,
                 seg_start_s: float, seg_end_s: float,
                 corr_threshold: float = 0.66,
                 amp_factor_lo: float = 0.3, amp_factor_hi: float = 3.0,
                 flat_frac_thresh: float = 0.1,
                 baseline_amp: float | None = None,
                 purpose: str = "general") -> dict:
    """Bewertet ein Segment [seg_start_s, seg_end_s) nach Regeln 1–6.

    `baseline_amp`: robuste Amplituden-Referenz über die GANZE Aufnahme (nicht nur
    dieses Segment!) — wichtig, weil ein Artefakt, das ein komplettes 10s-Segment
    gleichmäßig betrifft (z. B. anhaltend schwaches Signal oder Bewegungsartefakt),
    sonst gegen sich selbst verglichen wird und dabei unauffällig erscheint (gefunden
    2026-08 am synthetischen Testfall: 10s durchgehend 4×-Amplitude hatte keinen
    internen Ausreißer). Ohne Angabe fällt die Prüfung auf den Segment-Median zurück
    (schwächer, erkennt nur EINZELNE abweichende Schläge innerhalb eines Segments).

    `purpose`: "general" (Standard, streng — für die normale HRV-Zeit-/Frequenzanalyse,
    die tatsächlich einen regelmäßigen Rhythmus voraussetzt) oder "rhythm_screening"
    (nachsichtiger bei Regel 3/4 — für die Zuführung zur AFib-/Ektopie-Erkennung selbst).

    **Zwei getrennte Kategorien** (User-Feedback 2026-08-08 — "HF außerhalb 40-180 bpm ist bei
    schnellem AFib der eigentliche Befund, kein Artefakt; echte Artefakte sind Wackler/Bewegung/
    EMG/Impedanzprüfung/Eichung/Flatline"):
    - **"artifact"** (`good=False`, wird von CosEn/Ektopie-Erkennung ausgeschlossen): Flatline
      (Regel 5), Lücke >3s (Regel 2), Amplituden-Ausreißer (Regel 6), niedrige Template-
      Korrelation (Regel 4) — echte, rhythmusunabhängige Signalqualitäts-Probleme.
    - **"notable"** (`good=True`, bleibt in der Analyse, wird nur separat markiert/gezeigt):
      HF außerhalb 40–180 bpm (Regel 1) und extreme RR-Variabilität (Regel 3, jetzt in JEDEM
      Modus geprüft statt nur in "general") — beides kann echtes, klinisch relevantes AFib sein
      (z. B. schnelle Kammerüberleitung >180 bpm) und darf nicht aus dem Screening verschwinden.
      **Ausnahme:** im `purpose="general"`-Modus (normale HRV-Seite, braucht echte Regelmäßigkeit)
      bleibt Regel 3 weiterhin ausschließend wie zuvor — nur im `rhythm_screening`-Modus wird sie
      zu "notable" statt zum Ausschlussgrund.

    Rückgabe: {"good": bool, "category": "ok"|"notable"|"artifact", "reason": str,
    "notable_reasons": list[str], "n_beats": int, "template_corr": float}
    """
    lenient = purpose == "rhythm_screening"
    eff_corr_threshold = 0.35 if lenient else corr_threshold
    i0, i1 = int(seg_start_s * fs), int(seg_end_s * fs)
    seg_sig = sig[i0:i1]

    def _artifact(reason):
        return {"good": False, "category": "artifact", "reason": reason,
                "notable_reasons": [], "n_beats": 0, "template_corr": float("nan")}

    if len(seg_sig) == 0:
        return _artifact("leeres Segment")

    # Regel 5 — Flatline: nennenswerter Anteil des Segments variationslos (echtes Artefakt)
    flat = flatline_mask(seg_sig, fs)
    if flat.mean() > flat_frac_thresh:
        return _artifact(f"Flatline/Sättigung ({flat.mean()*100:.0f}% des Segments)")

    seg_peaks = r_peaks[(r_peaks >= i0) & (r_peaks < i1)] - i0
    n_beats = len(seg_peaks)
    if n_beats < 2:
        r = _artifact("zu wenige Schläge im Segment")
        r["n_beats"] = n_beats
        return r

    rr_ms = np.diff(seg_peaks) / fs * 1000.0
    hr_bpm = 60000.0 / rr_ms if len(rr_ms) else np.array([])
    notable_reasons: list[str] = []

    # Regel 1 — HF-Plausibilität 40-180 bpm: AUFFÄLLIG, nicht Artefakt (z. B. schnelles AFib)
    if len(hr_bpm) and (hr_bpm.min() < 40 or hr_bpm.max() > 180):
        notable_reasons.append(f"HF außerhalb 40-180 bpm ({hr_bpm.min():.0f}-{hr_bpm.max():.0f})")

    # Regel 2 — max. Lücke zwischen R-Zacken <= 3s: echtes Artefakt (vermutlich verpasster Schlag)
    if len(rr_ms) and rr_ms.max() > 3000.0:
        r = _artifact(f"Lücke > 3s ({rr_ms.max()/1000:.1f}s) — vermutlich verpasster Schlag")
        r["n_beats"] = n_beats
        return r

    # Regel 3 — max/min RR-Verhältnis < 2.2. Im "general"-Modus weiterhin Ausschlussgrund
    # (normale HRV braucht Regelmäßigkeit); im "rhythm_screening"-Modus AUFFÄLLIG statt Artefakt
    # (extreme RR-Variabilität kann selbst der AFib-Befund sein, User-Feedback 2026-08-08).
    if len(rr_ms) >= 2 and rr_ms.min() > 0:
        ratio = rr_ms.max() / rr_ms.min()
        if ratio >= 2.2:
            if lenient:
                notable_reasons.append(f"extreme RR-Variabilität (Verhältnis max/min={ratio:.1f})")
            else:
                r = _artifact(f"RR-Verhältnis max/min={ratio:.1f} >= 2.2")
                r["n_beats"] = n_beats
                return r

    # Regel 6 — Amplituden-Plausibilität je Schlag (eigene Ergänzung). Referenz ist
    # bevorzugt die GLOBALE Baseline (siehe Docstring) — nur wenn keine übergeben
    # wurde, fällt es auf den (schwächeren) Segment-eigenen Median zurück. Echtes Artefakt.
    if n_beats >= 2:
        half_w = int(np.median(np.diff(seg_peaks)) / 2) if n_beats >= 2 else int(0.1 * fs)
        amps = []
        for p in seg_peaks:
            lo, hi = max(0, p - half_w), min(len(seg_sig), p + half_w)
            if hi > lo:
                amps.append(np.ptp(seg_sig[lo:hi]))
        amps = np.array(amps)
        ref_amp = baseline_amp if baseline_amp is not None else np.median(amps)
        if ref_amp and ref_amp > 0:
            outliers = (amps < amp_factor_lo * ref_amp) | (amps > amp_factor_hi * ref_amp)
            if outliers.mean() > 0.3:  # mehr als 30% der Schläge amplituden-unplausibel
                r = _artifact(f"Amplituden-Ausreißer bei {outliers.mean()*100:.0f}% der Schläge "
                             f"(Referenz {ref_amp:.0f}µV)")
                r["n_beats"] = n_beats
                return r

    # Regel 4 — Template-Korrelation (bei purpose="rhythm_screening" gesenkter
    # Schwellwert 0.35 statt 0.66 — fängt weiterhin "kein echter QRS", toleriert aber
    # die morphologische Variabilität, die AFib selbst mit sich bringt). Echtes Artefakt.
    corr = _template_correlation(seg_sig, seg_peaks, fs)
    if corr != corr or corr < eff_corr_threshold:
        r = _artifact(f"Template-Korrelation {corr:.2f} < {eff_corr_threshold}")
        r["n_beats"] = n_beats
        return r

    return {"good": True, "category": "notable" if notable_reasons else "ok",
            "reason": "; ".join(notable_reasons) if notable_reasons else "ok",
            "notable_reasons": notable_reasons, "n_beats": n_beats, "template_corr": corr}


def _global_baseline_amplitude(sig: np.ndarray, r_peaks: np.ndarray, fs: float) -> float:
    """Robuste Amplituden-Referenz (Median Peak-to-Peak) über ALLE Schläge der
    Aufnahme — Grundlage für Regel 6, damit auch durchgehend betroffene Segmente
    erkannt werden (siehe Docstring von `segment_sqi`)."""
    if len(r_peaks) < 2:
        return float("nan")
    half_w = int(np.median(np.diff(r_peaks)) / 2)
    amps = []
    for p in r_peaks:
        lo, hi = max(0, p - half_w), min(len(sig), p + half_w)
        if hi > lo:
            amps.append(np.ptp(sig[lo:hi]))
    return float(np.median(amps)) if amps else float("nan")


def sqi_segments(sig: np.ndarray, r_peaks: np.ndarray, fs: float,
                  seg_s: float = 10.0, **kwargs) -> list[dict]:
    """Zerlegt die Aufnahme in nicht-überlappende `seg_s`-Segmente und bewertet jedes."""
    dur_s = len(sig) / fs
    if "baseline_amp" not in kwargs:
        kwargs["baseline_amp"] = _global_baseline_amplitude(sig, r_peaks, fs)
    out = []
    t0 = 0.0
    while t0 + seg_s <= dur_s + 1e-6:
        t1 = min(t0 + seg_s, dur_s)
        res = segment_sqi(sig, r_peaks, fs, t0, t1, **kwargs)
        res["t0"], res["t1"] = t0, t1
        out.append(res)
        t0 += seg_s
    return out
