"""
P-Wellen-Nachweis via Ensemble-Mittelung (Schlag-Summation) — Stufe②b, Vorhofflimmern-Schwerpunkt.

Zweite, von der RR-Irregularität (CosEn, siehe rhythm_screening.py) UNABHÄNGIGE Evidenzquelle:
Vorhofflimmern ist per Definition durch das Fehlen einer regelmäßigen P-Welle vor dem QRS-Komplex
gekennzeichnet (Vorhofflattern/-flimmern statt organisierter atrialer Depolarisation). Reduziert
vor allem Fehlalarme durch Ektopie (unregelmäßige RR, aber P-Welle vorhanden — siehe GA2410DH).

Methode: alle R-Zacken eines Zeitfensters werden auf den R-Zeitpunkt ausgerichtet und per Median
zu einem "Ensemble-Schlag" zusammengefasst (Summation/Mittelung mehrerer QRS-Komplexe, wie vom
User angeregt) — analog Signal-Averaged-ECG. Bei Sinusrhythmus hat die P-Welle eine feste
zeitliche Beziehung zum QRS (PR-Intervall) und überlebt die Mittelung; bei AFib ist die atriale
Aktivität (Flimmerwellen) zum R-Timing UNKORRELIERT und mittelt sich heraus.

Kohärenz-Metrik statt fixer µV-Schwelle: wir messen, wie stark jeder EINZELNE Schlag im
P-Fenster mit dem Ensemble-Mittel korreliert (Pearson) — analog unserer bestehenden
Template-Korrelation in ecg_quality.py Regel 4. Hoch = zeitlich fixiertes, wiederkehrendes
Signal (P-Welle plausibel); niedrig/~0 = inkohärent (f-Wellen/Rauschen, AFib-typisch). Das
umgeht bewusst eine feste µV-Schwelle (Literaturwerte ~10-35µV sind nicht ohne Weiteres auf
unsere heterogenen Klinik-Verstärker übertragbar, vgl. Kalibrierungsproblem bei Regel 6) UND
das Problem eines RR-adaptiven "stillen" Referenzfensters (bei schnellem AFib gibt es kaum noch
echte isoelektrische TP-Strecke).

WICHTIGER FIX gegenüber der ersten Version (POC 2026-08-08): ungefiltertes Rohsignal vor der
Mittelung zeigte bei einem artefaktbehafteten Fall (GA2410DH, GBS-Patient mit EMG-Kontamination)
eine durchgehende ~15-20Hz-Sägezahnschwingung über den GESAMTEN Vor-QRS-Bereich, die wie P-Wellen-
Aktivität aussah, aber Muskelartefakt war — UND bei CA1772QO (echtes AFib) wusch die starke
RR-Variabilität dieses Ringing beim Mitteln zufällig heraus, was den Fall fälschlich "sauberer"
aussehen ließ als den Ektopie-Fall. Fix: 0.5-30Hz-Bandpass VOR der Mittelung (schmaler als die
0.5-40Hz-Anzeigefilterung in ecg_hrv.py, um mehr EMG fernzuhalten, ohne die P-Welle selbst
wegzufiltern).

Validiert an allen 3 Referenzfällen (siehe [[project_edf_rhythm_screening]]):
    CA17734W (Sinusrhythmus, kein AFib):     Median P-Kohärenz 0,99 — P-Welle klar sichtbar
    GA2410DH (Ektopie, KEIN AFib):            Median P-Kohärenz 0,83 — P-Welle sichtbar
    CA1772QO (bestätigtes, durchgehendes AFib): Median P-Kohärenz 0,41 — deutlich abgesetzt

WICHTIG — Screening-Marker, keine Diagnose. Läuft NICHT nur bei AFib-Verdacht, sondern auf
JEDEM Rhythmus-Fenster (User-Vorgabe 2026-08-08: "egal welchen Rhythmus wir uns anschauen") —
liefert auch bei unauffälligem Befund eine zusätzliche, schöne Visualisierung des Ensemble-Schlags
(P-QRS-T), nicht nur eine binäre AFib-Zusatzevidenz.
"""
from __future__ import annotations

import numpy as np
from scipy.signal import butter, filtfilt

PRE_MS = 450.0   # Ensemble-Fenster für die Visualisierung: -450ms
POST_MS = 450.0  # bis +450ms um R (zeigt P-QRS-T bei üblichen RR-Intervallen)
P_WIN = (-250.0, -60.0)  # P-Wellen-Suchfenster rel. zu R (PR 120-200ms + P-Dauer 80-110ms)

COH_VISIBLE = 0.6     # >= : "sichtbar"
COH_UNCERTAIN = 0.35  # >= : "eingeschränkt beurteilbar", darunter "nicht abgrenzbar"

MIN_BEATS = 5  # zu wenige Schläge -> Ensemble statistisch nicht belastbar


def bandpass_ecg(sig: np.ndarray, fs: float, lo: float = 0.5, hi: float = 30.0) -> np.ndarray:
    """EINMAL über das gesamte Signal aufrufen, nicht pro Fenster (filtfilt ist nicht billig)."""
    nyq = fs / 2
    b, a = butter(2, [lo / nyq, min(hi / nyq, 0.99)], btype="band")
    return filtfilt(b, a, sig)


BEAT_SELECT_CORR = 0.5  # Mindest-Korrelation mit dem Vorab-Ensemble, um als "schöner" Schlag zu gelten


def ensemble_beat(sig_filt: np.ndarray, peaks: np.ndarray, fs: float,
                   t0_s: float, t1_s: float, pre_ms: float = PRE_MS,
                   post_ms: float = POST_MS, min_beats: int = MIN_BEATS,
                   select_clean: bool = True) -> dict | None:
    """Richtet alle R-Zacken im Fenster [t0_s, t1_s) aus und bildet das Median-Ensemble.

    Bei `select_clean=True` (Default, User-Anregung 2026-08-08 — "ausgewählte schöne QRS
    Komplexe"): 2-Pass-Verfahren. Pass 1 bildet ein Vorab-Ensemble aus ALLEN Schlägen; Pass 2
    verwirft Schläge, die schlecht mit diesem Vorab-Ensemble korrelieren (Bewegungsartefakt,
    Fehldetektion, atypischer Einzelschlag) und bildet das finale Ensemble nur aus den
    verbleibenden "sauberen" Schlägen — schärft P-Welle/QRS/T-Welle zusätzlich, weil
    Restrauschen nicht nur gemittelt, sondern aktiv aussortiert wird. Fällt automatisch auf
    "alle Schläge" zurück, wenn nach der Auswahl zu wenige übrig blieben.

    Rückgabe: {"t_ms": Zeitachse (ms rel. R), "ensemble": Median-Schlag,
    "beats": Matrix DER VERWENDETEN Einzelschläge (n_beats × n_samples), "n_beats": int,
    "n_beats_total": int (vor Auswahl), "n_excluded": int} oder None.
    """
    win_peaks = peaks[(peaks / fs >= t0_s) & (peaks / fs < t1_s)]
    pre_n, post_n = int(pre_ms / 1000 * fs), int(post_ms / 1000 * fs)
    beats = []
    for p in win_peaks:
        lo, hi = p - pre_n, p + post_n
        if lo < 0 or hi > len(sig_filt):
            continue
        beats.append(sig_filt[lo:hi])
    if len(beats) < min_beats:
        return None
    beats = np.array(beats)
    n_total = len(beats)
    t_ms = np.arange(-pre_n, post_n) / fs * 1000.0

    n_excluded = 0
    if select_clean and n_total >= min_beats * 2:
        pre_ensemble = np.median(beats, axis=0)
        pre_c = pre_ensemble - pre_ensemble.mean()
        pre_std = np.std(pre_c)
        if pre_std > 0:
            corrs = np.array([
                float(np.mean((b - b.mean()) * pre_c) / (np.std(b) * pre_std))
                if np.std(b) > 0 else 0.0
                for b in beats
            ])
            keep = corrs >= BEAT_SELECT_CORR
            if keep.sum() >= min_beats:
                n_excluded = int((~keep).sum())
                beats = beats[keep]

    ensemble = np.median(beats, axis=0)
    return {"t_ms": t_ms, "ensemble": ensemble, "beats": beats, "n_beats": len(beats),
            "n_beats_total": n_total, "n_excluded": n_excluded}


def p_wave_coherence(t_ms: np.ndarray, ensemble: np.ndarray, beats: np.ndarray,
                      p_win: tuple = P_WIN) -> tuple:
    """Median Pearson-Korrelation jedes Einzelschlags mit dem Ensemble-Mittel, NUR im
    P-Fenster. Rückgabe (coherence, amplitude_uv) — amplitude ist Peak-to-Peak des
    Ensemble-P-Fensters (deskriptiv, nicht die primäre Entscheidungsgröße)."""
    p_mask = (t_ms >= p_win[0]) & (t_ms < p_win[1])
    if p_mask.sum() < 3:
        return float("nan"), float("nan")
    template = ensemble[p_mask]
    template_c = template - template.mean()
    if np.std(template_c) == 0:
        return float("nan"), float("nan")
    corrs = []
    for beat in beats:
        seg = beat[p_mask] - beat[p_mask].mean()
        denom = np.std(seg) * np.std(template_c)
        if denom > 0:
            corrs.append(float(np.mean(seg * template_c) / denom))
    amp = float(np.ptp(template))
    return (float(np.median(corrs)) if corrs else float("nan")), amp


def classify_p_wave(coherence: float) -> str:
    """"sichtbar" | "eingeschraenkt" | "nicht_abgrenzbar" | "nicht_auswertbar" """
    if coherence != coherence:
        return "nicht_auswertbar"
    if coherence >= COH_VISIBLE:
        return "sichtbar"
    if coherence >= COH_UNCERTAIN:
        return "eingeschraenkt"
    return "nicht_abgrenzbar"


def analyze_window(sig_filt: np.ndarray, peaks: np.ndarray, fs: float,
                    t0_s: float, t1_s: float) -> dict | None:
    """Komplettanalyse für ein Fenster: Ensemble + Kohärenz + Verdikt. `sig_filt` MUSS bereits
    bandpassgefiltert sein (einmal über die ganze Aufnahme via `bandpass_ecg`)."""
    eb = ensemble_beat(sig_filt, peaks, fs, t0_s, t1_s)
    if eb is None:
        return None
    coh, amp = p_wave_coherence(eb["t_ms"], eb["ensemble"], eb["beats"])
    return {**eb, "coherence": coh, "amplitude_uv": amp, "verdict": classify_p_wave(coh)}
