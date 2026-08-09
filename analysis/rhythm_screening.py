"""
Rhythmus-Screening — Stufe ② der Pipeline: Vorhofflimmern-Verdacht via CosEn.

Nutzt `analysis/ecg_quality.py` (Stufe ①, purpose="rhythm_screening") um Segmente mit
echten, aber ggf. unregelmäßigen Schlägen von reinen Signalartefakten zu trennen, dann
CosEn (Coefficient of Sample Entropy) je 30s-Fenster.

Formel nach Lake & Moorman 2011 (zwei unabhängige Sekundärquellen bestätigt):
    COSEn = SampEn(m=1, r=30ms) + ln(2×30) − ln(mittleres RR in ms)
Referenzbereiche (Sarkar et al., IOPscience 2015, Physiol Meas 36:1873):
    AFib: Median −0,5 (−0,8 bis −0,3)
    Normaler Sinusrhythmus: Median −2,1 (−2,3 bis −1,8)
    Sinusrhythmus mit Ektopie: Median −1,7 (−2,0 bis −1,4)

An 2 echten Fällen validiert (siehe [[project_edf_rhythm_screening]]):
    CA1772QO (bestätigtes, durchgehendes AFib): Median CosEn −0,44, alle Fenster AFib-verdächtig
    CA17734W (kein AFib in diesem Fenster, nach Artefaktausschluss): −2,17 bis −2,58, alle "normal"

WICHTIG — Screening-Marker, keine Diagnose. Sensitivität/Spezifität aus der Literatur
(~90er-Bereich), nicht 100%. UI-Texte müssen "Verdacht auf..." sagen, nie "Diagnose:...".
"""
from __future__ import annotations

import numpy as np

from analysis.complexity import sample_entropy
from analysis.ecg_quality import sqi_segments

# Literatur-Referenzbereiche (Sarkar/IOPscience 2015) — als Grenzen für die Ampel-Einordnung
_AFIB_THRESH = -0.8      # >= diese Grenze: "AFib-verdächtig" (Literatur-Range -0.8 bis -0.3)
_ECTOPY_THRESH = -2.0    # >= diese Grenze (aber < AFib): "Ektopie-Richtung"
# < _ECTOPY_THRESH: "normal" (Literatur-Normalbereich -2.3 bis -1.8)

R_TOLERANCE_MS = 30.0    # Lake & Moorman: fester Toleranzwert, NICHT SD-skaliert
EMBEDDING_M = 1
WINDOW_S = 30.0          # "AFib muss klinisch >=30s andauern, um als solches zu gelten"


def cosen(rr_ms: np.ndarray, m: int = EMBEDDING_M, r_ms: float = R_TOLERANCE_MS) -> float:
    """Coefficient of Sample Entropy (Lake & Moorman 2011) einer RR-Serie in ms."""
    rr_ms = np.asarray(rr_ms, dtype=float)
    if len(rr_ms) < 10 or np.any(rr_ms <= 0):
        return float("nan")
    se = sample_entropy(rr_ms, m=m, r=r_ms)
    if se != se:
        return float("nan")
    return float(se + np.log(2 * r_ms) - np.log(np.mean(rr_ms)))


def _zone(c: float) -> str:
    if c != c:
        return "unbestimmt"
    if c >= _AFIB_THRESH:
        return "afib_verdaechtig"
    if c >= _ECTOPY_THRESH:
        return "ektopie_richtung"
    return "normal"


def sliding_cosen(sig: np.ndarray, r_peaks: np.ndarray, fs: float,
                   win_s: float = WINDOW_S, min_beats: int = 10) -> list[dict]:
    """CosEn über nicht-überlappende `win_s`-Fenster, aber NUR für Fenster, die laut
    Stufe ① (purpose="rhythm_screening") als real genug gelten — überschneidet ein
    Fenster eine BAD-Zone, wird es übersprungen statt mit kontaminierten RR gerechnet.

    Rückgabe je Fenster: {"t0","t1","n_beats","cosen","zone"}.
    """
    sqi = sqi_segments(sig, r_peaks, fs, seg_s=10.0, purpose="rhythm_screening")
    bad_zones = [(s["t0"], s["t1"]) for s in sqi if not s["good"]]

    def overlaps_bad(t0: float, t1: float) -> bool:
        return any(not (t1 <= b0 or t0 >= b1) for b0, b1 in bad_zones)

    rr_ms = np.diff(r_peaks) / fs * 1000.0
    rr_times_s = r_peaks[1:] / fs

    out = []
    t0 = 0.0
    dur_s = len(sig) / fs
    while t0 + win_s <= dur_s + 1e-6:
        t1 = t0 + win_s
        if not overlaps_bad(t0, t1):
            m = (rr_times_s >= t0) & (rr_times_s < t1)
            rr_win = rr_ms[m]
            if len(rr_win) >= min_beats:
                c = cosen(rr_win)
                out.append({"t0": t0, "t1": t1, "n_beats": len(rr_win),
                            "cosen": c, "zone": _zone(c)})
        t0 += win_s
    return out


def _afib_confidence(frac_afib: float, median_cosen_afib: float) -> str:
    """Sicherheitsabstufung NUR relevant, wenn verdict=="afib_verdaechtig" bereits feststeht.

    Zwei unabhängige Achsen, beide aus unseren eigenen Daten ableitbar (keine neue Annahme):
    - **Persistenz**: welcher Anteil der auswertbaren 30s-Fenster liegt im AFib-Bereich (ein
      einzelnes Fenster kann paroxysmales AFib sein, viele Fenster sprechen für Dauer-AFib).
    - **Tiefe**: Median-CosEn NUR der betroffenen Fenster — je näher am Literatur-AFib-Median
      (Sarkar/IOPscience 2015: −0,5, Range −0,8 bis −0,3), desto eindeutiger die Signatur,
      statt nur knapp über der −0,8-Schwelle zu liegen.

    Schwellen kalibriert am einzigen bestätigten Volltag-AFib-Referenzfall (CA1772QO: frac=1,0,
    Median −0,42 → "gesichert") — bei weiteren Referenzfällen nachjustieren, siehe
    [[project_edf_rhythm_screening]]. Rein additiv zur bestehenden Verdikt-Logik, ändert NICHTS
    an der binären Verdikt-Schwelle selbst (weiterhin: ein Fenster genügt für "afib_verdaechtig").
    """
    if frac_afib >= 0.75 and median_cosen_afib >= -0.5:
        return "gesichert"
    if frac_afib >= 0.3 or median_cosen_afib >= -0.5:
        return "wahrscheinlich"
    return "verdacht"


def classify_afib_risk(sig: np.ndarray, r_peaks: np.ndarray, fs: float,
                        win_s: float = WINDOW_S) -> dict:
    """Gesamtbewertung einer Aufnahme: Median-CosEn über alle auswertbaren Fenster +
    Ampel-Verdikt + (bei AFib-Verdacht) eine Sicherheits-Abstufung. Rückgabe:
        {"verdict": "afib_verdaechtig"|"ektopie_richtung"|"normal"|"nicht_auswertbar",
         "confidence": "gesichert"|"wahrscheinlich"|"verdacht"|None,
         "median_cosen": float, "n_windows": int, "n_afib_windows": int,
         "windows": [...]}

    `verdict` = "afib_verdaechtig" sobald MINDESTENS EIN Fenster (nicht nur der Median)
    im AFib-Bereich liegt — bewusst konservativ (hohe Sensitivität), da AFib klinisch oft
    paroxysmal auftritt (siehe CA17734W: nur ein 20s-Ausschnitt betroffen hätte im
    Gesamt-Median untergehen können). Einzelne Fenster sind bereits klinisch relevant — die
    binäre Verdikt-Schwelle bleibt UNVERÄNDERT. `confidence` staffelt NUR, wie sicher wir uns
    innerhalb dieses Verdikts sind (User-Anstoß 2026-08-08: "Verdacht auf" ist nicht immer
    gleich sicher — braucht eine Steigerung Richtung "gesichert").
    KEINE eigene Diagnose-Schwelle für "gesichert" — bleibt ein Screening-Marker, auch bei
    höchster Konfidenzstufe (siehe UI-Text-Pflicht im Modul-Docstring oben).
    """
    windows = sliding_cosen(sig, r_peaks, fs, win_s=win_s)
    vals = [w["cosen"] for w in windows if w["cosen"] == w["cosen"]]
    if not vals:
        return {"verdict": "nicht_auswertbar", "confidence": None, "median_cosen": float("nan"),
                "n_windows": 0, "n_afib_windows": 0, "windows": windows}

    afib_windows = [w for w in windows if w["zone"] == "afib_verdaechtig"]
    n_afib = len(afib_windows)
    median_c = float(np.median(vals))
    verdict = "afib_verdaechtig" if n_afib > 0 else _zone(median_c)

    confidence = None
    if verdict == "afib_verdaechtig":
        frac_afib = n_afib / len(vals)
        median_afib = float(np.median([w["cosen"] for w in afib_windows]))
        confidence = _afib_confidence(frac_afib, median_afib)

    return {"verdict": verdict, "confidence": confidence, "median_cosen": median_c,
            "n_windows": len(vals), "n_afib_windows": n_afib, "windows": windows}


def combine_with_pwave(rhythm: dict, pwave_median_coherence: float, pwave_n_windows: int,
                        min_windows: int = 3) -> dict:
    """Kombiniert das CosEn-Verdikt mit der P-Wellen-Kohärenz (Stufe②b, `analysis/
    p_wave_analysis.py`) — zwei UNABHÄNGIGE Evidenzquellen für dieselbe Frage (User-Anstoß
    2026-08-08: "wer eine saubere, sichere P-Welle hat, hat eher kein AFib").

    Nur relevant, wenn bereits `verdict=="afib_verdaechtig"` UND genug P-Wellen-Fenster
    auswertbar sind (`min_windows`, sonst zu unsicher für eine Korrektur). Ändert NICHTS an
    der binären Verdikt-Schwelle (weiterhin CosEn-basiert) — nur an der `confidence`-Stufe:
    - P-Welle NICHT abgrenzbar (Median-Kohärenz < 0,35, wie bei AFib erwartet) → STÜTZT den
      AFib-Verdacht → Confidence eine Stufe anheben (verdacht→wahrscheinlich→gesichert).
    - P-Welle SICHTBAR (Median-Kohärenz ≥ 0,6, wie bei Sinusrhythmus erwartet) → WIDERSPRICHT
      dem AFib-Verdacht (könnte z. B. Ektopie statt AFib sein) → Confidence eine Stufe senken,
      plus explizites Widerspruchs-Flag für die UI.
    - Dazwischen (0,35–0,6, "eingeschränkt beurteilbar") → neutral, keine Änderung.

    Rückgabe: Kopie von `rhythm`, ergänzt um `confidence` (ggf. angepasst), `pwave_note` (str),
    `pwave_contradiction` (bool).
    """
    from analysis.p_wave_analysis import COH_VISIBLE, COH_UNCERTAIN

    out = dict(rhythm)
    out["pwave_note"] = None
    out["pwave_contradiction"] = False

    if rhythm.get("verdict") != "afib_verdaechtig" or pwave_median_coherence != pwave_median_coherence:
        return out
    if pwave_n_windows < min_windows:
        out["pwave_note"] = (f"Zu wenige P-Wellen-Fenster ({pwave_n_windows}) für eine "
                             "verlässliche Zusatzbewertung — Confidence unverändert.")
        return out

    _levels = ["verdacht", "wahrscheinlich", "gesichert"]
    cur = rhythm.get("confidence") or "verdacht"
    idx = _levels.index(cur) if cur in _levels else 0

    if pwave_median_coherence < COH_UNCERTAIN:
        idx = min(idx + 1, len(_levels) - 1)
        out["pwave_note"] = (f"P-Welle über die Aufnahme NICHT abgrenzbar (Median-Kohärenz "
                             f"{pwave_median_coherence:.2f}) — stützt den AFib-Verdacht, "
                             "Sicherheitsstufe angehoben.")
    elif pwave_median_coherence >= COH_VISIBLE:
        idx = max(idx - 1, 0)
        out["pwave_contradiction"] = True
        out["pwave_note"] = (f"P-Welle über die Aufnahme SICHTBAR (Median-Kohärenz "
                             f"{pwave_median_coherence:.2f}) — widerspricht dem CosEn-basierten "
                             "AFib-Verdacht (z. B. Ektopie statt AFib möglich), Sicherheitsstufe "
                             "gesenkt. Bitte Einzelfall genauer prüfen.")
    else:
        out["pwave_note"] = (f"P-Welle eingeschränkt beurteilbar (Median-Kohärenz "
                             f"{pwave_median_coherence:.2f}) — keine Änderung der Confidence.")

    out["confidence"] = _levels[idx]
    return out
