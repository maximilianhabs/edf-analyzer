"""
Ektopie-Erkennung — Stufe ③ der Rhythmus-Screening-Pipeline.

Erkennt vorzeitige Schläge mit kompensatorischer Pause (kurz-RR gefolgt von langem RR,
Summe ≈ 2× lokaler Median — Standardmuster bei Extrasystolen) und schätzt grob, ob eher
ventrikulären (VES) oder supraventrikulären (SVES) Ursprungs, über die QRS-Breite
(>120ms = klassisches Bündelblock-/VES-Kriterium — Ergänzung aus externer Fachkritik,
siehe [[project_edf_rhythm_screening]]).

WICHTIG — Screening-Hinweis, keine Diagnose. Die genaue VES/SVES-Unterscheidung braucht
eigentlich mehr als 1 Kanal (P-Welle, Vektor); hier nur ein grober, konservativ formulierter
Anhaltspunkt. UI-Text: "SVES-/VES-verdächtig", nie "SVES:"/"VES:" als Befund.

WICHTIG — Detektor-Sensitivität (empirisch geprüft 2026-08-06 an Referenzfall A, Anstoß Kollaborator
Ruhid): die GRUNDSÄTZLICHE RR-Unregelmäßigkeit ist an 4 unabhängigen Detektoren (eigen,
Hamilton, Christov, Pan-Tompkins-Lib) reproduzierbar — aber die EXAKTE Anzahl erkannter
Kompensationspausen und wie sauber sie sich paaren, ist spürbar detektor-abhängig (Hamilton
fand nur 13% "sauber gepaart" vs. ~80% beim eigenen Detektor). Zahlen aus diesem Modul sind
daher als Größenordnung/Hinweis zu verstehen, nicht als exakter Zählwert — bei Unsicherheit im
Einzelfall den Detektor-Vergleich in "Erweiterte Analysen" heranziehen.
"""
from __future__ import annotations

import numpy as np

from analysis.ecg_quality import sqi_segments

VES_QRS_WIDTH_MS = 120.0  # klassisches Bündelblock-/VES-Kriterium (externe Fachkritik, übernommen)
COMPENSATORY_SUM_TOL = 0.15  # kurz+lang darf bis 15% von 2x Median abweichen


def _qrs_width_ms(sig: np.ndarray, peak_idx: int, fs: float,
                   search_ms: float = 100.0, half_max_frac: float = 0.5) -> float:
    """Grobe QRS-Breite: Abstand der Halbwertsbreiten-Kreuzungspunkte um den R-Peak,
    im bandpassgefilterten Signal (5-15 Hz, konsistent mit unserer QRS-Detektion)."""
    from scipy.signal import butter, filtfilt
    win = int(search_ms / 1000.0 * fs)
    lo, hi = max(0, peak_idx - win), min(len(sig), peak_idx + win)
    if hi - lo < 10:
        return float("nan")
    seg = sig[lo:hi]
    nyq = fs / 2
    try:
        b, a = butter(2, [5 / nyq, min(15 / nyq, 0.99)], btype="band")
        filt = filtfilt(b, a, seg)
    except Exception:
        return float("nan")
    p = peak_idx - lo
    if p < 0 or p >= len(filt):
        return float("nan")
    peak_amp = abs(filt[p])
    if peak_amp == 0:
        return float("nan")
    thresh = half_max_frac * peak_amp
    # links vom Peak: letzte Unterschreitung vor dem Peak
    left = p
    while left > 0 and abs(filt[left]) >= thresh:
        left -= 1
    # rechts vom Peak: erste Unterschreitung nach dem Peak
    right = p
    while right < len(filt) - 1 and abs(filt[right]) >= thresh:
        right += 1
    return float((right - left) / fs * 1000.0)


def detect_ectopic_beats(sig: np.ndarray, r_peaks: np.ndarray, fs: float) -> list[dict]:
    """Findet kurz+lang-RR-Paare (Kompensationspause) und schätzt je Ereignis eine grobe
    VES-/SVES-Verdachtsrichtung über die QRS-Breite des VORZEITIGEN (kurzen) Schlags.

    Rückgabe je Ereignis: {"t_s", "rr_short_ms", "rr_long_ms", "sum_ratio",
    "qrs_width_ms", "hint"} — `hint` ∈ {"VES-verdächtig", "SVES-verdächtig", "unklar"}.
    """
    if len(r_peaks) < 4:
        return []
    rr_ms = np.diff(r_peaks) / fs * 1000.0
    median_rr = float(np.median(rr_ms))
    if median_rr <= 0:
        return []

    # Stufe ① vorab (purpose="rhythm_screening", konsistent mit rhythm_screening.py):
    # Ereignisse, deren vorzeitiger Schlag in eine Artefakt-Zone fällt, werden verworfen —
    # sonst könnten Sättigungs-/Diskonnektions-Ränder als SVES/VES fehlgedeutet werden.
    sqi = sqi_segments(sig, r_peaks, fs, seg_s=10.0, purpose="rhythm_screening")
    bad_zones = [(s["t0"], s["t1"]) for s in sqi if not s["good"]]

    def in_bad_zone(t_s: float) -> bool:
        return any(b0 <= t_s < b1 for b0, b1 in bad_zones)

    events = []
    for i in range(1, len(rr_ms)):
        short, long_ = rr_ms[i - 1], rr_ms[i]
        if short >= 0.85 * median_rr:      # Vorgänger muss deutlich kürzer als üblich sein
            continue
        if long_ <= median_rr:             # Nachfolger muss deutlich länger sein
            continue
        expected = 2 * median_rr
        ratio = (short + long_) / expected if expected > 0 else float("nan")
        if abs(ratio - 1.0) > COMPENSATORY_SUM_TOL:
            continue  # keine saubere Kompensationspause

        # Der vorzeitige Schlag ist r_peaks[i] (das Ende des kurzen RR-Intervalls i-1→i)
        beat_idx = r_peaks[i]
        if in_bad_zone(beat_idx / fs):
            continue  # Artefakt-Zone (Stufe ①) — kein plausibler Rhythmus-Befund hier

        width = _qrs_width_ms(sig, beat_idx, fs)
        if width != width:
            hint = "unklar"
        elif width > VES_QRS_WIDTH_MS:
            hint = "VES-verdächtig"
        else:
            hint = "SVES-verdächtig"

        events.append({
            "t_s": float(beat_idx / fs),
            "rr_short_ms": float(short), "rr_long_ms": float(long_),
            "sum_ratio": float(ratio), "qrs_width_ms": float(width), "hint": hint,
        })
    return events


def ectopy_summary(sig: np.ndarray, r_peaks: np.ndarray, fs: float) -> dict:
    """Zusammenfassung für die UI: Anzahl, Anteil, Aufschlüsselung nach Verdachtsrichtung.

    NUR SINNVOLL INTERPRETIERBAR, WENN Stufe ② (`rhythm_screening.classify_afib_risk`)
    KEIN AFib-Verdikt liefert. Bei AFib ist der Rhythmus selbst schon chaotisch — die
    "Kompensationspause"-Heuristik setzt einen grundsätzlich regelmäßigen Rhythmus mit
    gelegentlicher Störung voraus. Getestet an Referenzfall B (bestätigtes AFib): 9,8% "Ereignisse"
    — das ist KEIN echter SVES-Befund, sondern ein Artefakt der Heuristik auf chaotischer
    RR-Basis. Der Aufrufer MUSS Stufe ② zuerst prüfen und diese Zusammenfassung bei
    AFib-Verdacht nicht als Ektopie-Befund anzeigen.
    """
    events = detect_ectopic_beats(sig, r_peaks, fs)
    n_total_beats = max(len(r_peaks) - 1, 1)
    n_ves = sum(1 for e in events if e["hint"] == "VES-verdächtig")
    n_sves = sum(1 for e in events if e["hint"] == "SVES-verdächtig")
    n_unklar = sum(1 for e in events if e["hint"] == "unklar")
    return {
        "n_events": len(events), "fraction_pct": len(events) / n_total_beats * 100.0,
        "n_ves_verdaechtig": n_ves, "n_sves_verdaechtig": n_sves, "n_unklar": n_unklar,
        "events": events,
    }
