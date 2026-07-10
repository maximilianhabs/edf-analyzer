"""
Regelbasierte Artefakt-Markierung für EEG — Zeit-Achse + Kanal-Achse.

Ziel (bewusst KONSERVATIV): nur **grobe** Bewegungs-/Globalartefakte markieren, damit
Frequenz-/HRV-Analysen nicht kompromittiert werden. Sauberes EEG (auch hochamplitudiges
wie Slow-Wave-Sleep oder Blinzeln) wird NICHT verworfen — im Zweifel behalten.

Zwei orthogonale Achsen:
  • ZEIT  : kurze Fenster verwerfen, in denen VIELE Kanäle gleichzeitig extrem ausschlagen
            (Bewegung/global). Einzelkanal-Ausschläge (lokal) verwerfen die Epoche NICHT.
  • KANAL : eine Elektrode, die über einen längeren Abschnitt PERSISTENT isoliert auffällt
            (gelöst/defekt), wird als „ab Zeit t entfernen" VORGESCHLAGEN (kein Auto-Remove).

Das EKG ist ein rein **bestätigendes** Zusatzsignal (Konfidenz), niemals ein Gate:
bewegt die Körperbewegung die EKG-Elektrode mit → EKG-Störung bestätigt Bewegung; bleibt das
EKG ruhig (Blinzeln/SWS/lokal) → Hinweis, eher zu behalten.

Empirisch kalibriert (2026-07-10) an zwei 10-min-Routine-EEGs (GA2410B4, CA177317):
Default win=1 s / 50 % Überlapp / ≥3 Kanäle > 4× Eigen-Baseline / Konsens N=3 → Ruhephasen
blieben in ALLEN getesteten Konfigurationen falschpositiv-frei.

Reines Bibliotheksmodul: keine Streamlit-/UI-Abhängigkeit, keine bestehende Funktion berührt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Optional

import numpy as np
from scipy.signal import butter, filtfilt


# ──────────────────────────────────────────────────────────────────────────────
# Regionsabhängige Toleranz — anfällige Elektroden dürfen mehr (User-Setzung)
# Fp1/Fp2 (über den Augen → Blinzeln/EOG), F7/F8 (M. temporalis → Kau-EMG),
# T3/T4 (mid-temporal) sind physiologisch groß → höhere „heiß"-Schwelle.
# ──────────────────────────────────────────────────────────────────────────────
_REGION_FACTORS_DEFAULT = {
    "FP1": 2.0, "FP2": 2.0,      # frontopolar — höchste Toleranz
    "F7": 1.4, "F8": 1.4,        # frontotemporal
    "T3": 1.2, "T4": 1.2,        # mid-temporal
}
# „Frontal" für den räumlichen Schutz (Blinzeln beleuchtet nur frontal → kein Global-Artefakt)
_FRONTAL_LABELS = {"FP1", "FP2", "F7", "F8", "F3", "F4", "FZ"}


def _norm_ch(name: str) -> str:
    """'EEG Fp2-Ref' / 'Fp2' / 'FP2' → 'FP2'. 'ch0' → 'CH0'."""
    s = name.upper()
    for tok in ("EEG", "REF"):
        s = s.replace(tok, "")
    return re.sub(r"[^A-Z0-9]", "", s)


# ──────────────────────────────────────────────────────────────────────────────
# Parameter (kalibrierbar) — Defaults aus der Kalibrierung 2026-07-10
# ──────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class ArtifactParams:
    hp_hz: float = 1.0            # Hochpass (Drift/Schwitzen raus → Amplitude = echtes Signal)
    win_s: float = 1.0           # Detektor-Fensterlänge
    overlap: float = 0.5         # Fenster-Überlapp (0..1)
    flag_sus: float = 4.0        # „heiß" ab x Eigen-Baseline (verdächtig)
    flag_strong: float = 6.0     # „stark" ab x Eigen-Baseline (nur informativ)
    consensus_n: int = 3         # so viele heiße Kanäle → Bewegungs-/Globalartefakt
    # Regionsabhängige Toleranz: heiß, wenn ratio > flag_sus · region_factor[c].
    # None → _REGION_FACTORS_DEFAULT (Fp 2,0 / F7F8 1,4 / T3T4 1,2 / Rest 1,0).
    region_factors: Optional[dict] = None
    # Räumlicher Schutz: ein Fenster ist nur Global-/Bewegungsartefakt, wenn ≥ so viele
    # NICHT-frontale (zentrale/posteriore) Kanäle heiß sind. Blinzeln (nur frontal) → 0 → kein Flag.
    # Default 1: blockt rein-frontale Blinzler (0 nicht-frontale), erhält aber Bewegungen mit
    # nur geringer posteriorer Beteiligung.
    min_nonfrontal: int = 1
    guard_s: float = 0.5         # Sicherheitsrand um jedes Segment
    # Minimale saubere Insel: liegt zwischen zwei Artefakt-Segmenten weniger als so viel
    # sauberes EEG, wird die Lücke absorbiert (ein Block statt vieler Schnipsel). Verhindert
    # sinnlose Fragmentierung, wenn es real ein großer Artefaktblock ist. Kurze Inseln (<5 s)
    # tragen spektral ohnehin kaum bei (Minuten-Literatur).
    min_clean_island_s: float = 5.0
    # EKG (bestätigend, positiv-only) — Segment gilt als „EKG mitgestört", wenn die
    # Amplitude des EKG-Kanals im Segment über dieser x-Baseline liegt:
    ecg_ptp_ratio: float = 2.5
    # Kanal-Achse (Bad-Channel, A2b) — Vorschlag, kein Auto-Remove. Bewusst KONSERVATIV:
    # ein echt gelöster Kanal ist in ~allen Fenstern auffällig; natürlich zappelige temporale
    # Kanäle (F7/T3, Temporalis-Muskel) nur intermittierend → hohe Schwellen filtern die raus.
    bad_iso_ratio: float = 5.0   # Kanal „isoliert auffällig" ab x (25.-Perzentil-)Baseline …
    bad_min_frac: float = 0.50   # … in ≥ der MEHRHEIT der Fenster einer Minute …
    bad_min_minutes: int = 3     # … über ≥ so viele (aufeinanderfolgende) Minuten.


@dataclass
class ArtifactResult:
    window_t: np.ndarray              # Fenster-Startzeiten (s)
    win_s: float
    n_hot: np.ndarray                 # #Kanäle > flag_sus je Fenster
    max_ratio: np.ndarray             # max Amplituden/Baseline je Fenster (über Kanäle)
    artifact_win: np.ndarray          # bool: Konsens-Artefakt je Fenster (Zeit-Achse)
    segments: list                    # [{start_s, end_s, dur_s, max_ratio, ecg_disturbed}]
    duration_s: float
    clean_s: float
    clean_frac: float                 # Anteil sauberer Zeit (0..1)
    baseline_uv: np.ndarray           # Eigen-Baseline (Median-ptp) je Kanal
    ch_names: list
    bad_channels: list                # [{index, name, since_s, frac}]  (A2b-Vorschläge)
    params: dict = field(default_factory=dict)


def _highpass(x: np.ndarray, fs: float, cutoff: float) -> np.ndarray:
    b, a = butter(4, cutoff / (fs / 2.0), btype="high")
    return filtfilt(b, a, x, axis=-1)


def _window_starts(n: int, win: int, step: int) -> np.ndarray:
    if n < win:
        return np.empty(0, dtype=int)
    return np.arange(0, n - win + 1, step, dtype=int)


def _window_ptp(sig1d: np.ndarray, starts: np.ndarray, win: int) -> np.ndarray:
    return np.array([np.ptp(sig1d[s:s + win]) for s in starts], dtype=float)


# ──────────────────────────────────────────────────────────────────────────────
# Kernfunktion — arbeitet auf reinen Arrays (µV), voll testbar, ohne App-Kontext
# ──────────────────────────────────────────────────────────────────────────────
def compute_artifact_mask(
    eeg_uv: np.ndarray,
    sfreq: float,
    *,
    ecg_uv: Optional[np.ndarray] = None,
    ch_names: Optional[list] = None,
    params: Optional[ArtifactParams] = None,
) -> ArtifactResult:
    """Berechnet Artefakt-Maske (Zeit) + Bad-Channel-Vorschläge (Kanal).

    eeg_uv : (n_channels, n_samples) in µV — bereits als EEG identifizierte Kanäle.
    ecg_uv : optional (n_samples,) EKG-Kanal in beliebiger Einheit (nur relativ genutzt).
    """
    p = params or ArtifactParams()
    if eeg_uv.ndim != 2:
        raise ValueError("eeg_uv muss (n_channels, n_samples) sein")
    nch, n = eeg_uv.shape
    if ch_names is None:
        ch_names = [f"ch{i}" for i in range(nch)]

    fs = float(sfreq)
    win = int(round(p.win_s * fs))
    step = max(1, int(round(win * (1.0 - p.overlap))))
    duration_s = n / fs

    data = _highpass(eeg_uv.astype(float), fs, p.hp_hz)
    starts = _window_starts(n, win, step)
    if starts.size == 0:
        return ArtifactResult(
            window_t=np.empty(0), win_s=p.win_s, n_hot=np.empty(0), max_ratio=np.empty(0),
            artifact_win=np.empty(0, bool), segments=[], duration_s=duration_s,
            clean_s=duration_s, clean_frac=1.0, baseline_uv=np.zeros(nch),
            ch_names=list(ch_names), bad_channels=[], params=asdict(p),
        )
    t = starts / fs

    # ptp je Kanal/Fenster → Eigen-Baseline (Median) → Ratio
    ptp = np.vstack([_window_ptp(data[c], starts, win) for c in range(nch)])   # (nch, nwin)
    base = np.median(ptp, axis=1)
    base_safe = np.where(base > 1e-9, base, 1e-9)[:, None]
    ratio = ptp / base_safe

    # Regionsabhängige „heiß"-Schwelle je Kanal (anfällige Elektroden dürfen mehr)
    rf = dict(_REGION_FACTORS_DEFAULT)
    if p.region_factors:
        rf.update({k.upper(): v for k, v in p.region_factors.items()})
    factors = np.array([rf.get(_norm_ch(nm), 1.0) for nm in ch_names])
    is_frontal = np.array([_norm_ch(nm) in _FRONTAL_LABELS for nm in ch_names])

    hot = ratio > (p.flag_sus * factors)[:, None]   # (nch, nwin)
    n_hot = hot.sum(axis=0)
    n_hot_nonfrontal = hot[~is_frontal].sum(axis=0) if (~is_frontal).any() else n_hot
    max_ratio = ratio.max(axis=0)
    # Zeit-Achse: Konsens UND räumlicher Schutz (nicht rein frontal → keine Blinzel-Fehlflags)
    artifact_win = (n_hot >= p.consensus_n) & (n_hot_nonfrontal >= p.min_nonfrontal)

    # ── EKG-Störung je Fenster (positiv-only) ────────────────────────────────
    ecg_hot = None
    if ecg_uv is not None and ecg_uv.shape[-1] == n:
        e = _highpass(ecg_uv.astype(float), fs, p.hp_hz)
        eptp = _window_ptp(e, starts, win)
        ebase = np.median(eptp)
        ecg_ratio = eptp / (ebase if ebase > 1e-9 else 1e-9)
        ecg_hot = ecg_ratio > p.ecg_ptp_ratio

    # ── Segmentbildung (Guard + Gap-Merge) ───────────────────────────────────
    segments = _build_segments(t, artifact_win, max_ratio, ecg_hot, p)
    disc = sum(s["dur_s"] for s in segments)
    clean_s = max(0.0, duration_s - disc)

    # ── Bad-Channel (Kanal-Achse, A2b) — nur Vorschläge ──────────────────────
    bad = _detect_bad_channels(ptp, n_hot, t, ch_names, p)

    return ArtifactResult(
        window_t=t, win_s=p.win_s, n_hot=n_hot, max_ratio=max_ratio,
        artifact_win=artifact_win, segments=segments, duration_s=duration_s,
        clean_s=clean_s, clean_frac=clean_s / duration_s if duration_s > 0 else 1.0,
        baseline_uv=base, ch_names=list(ch_names), bad_channels=bad, params=asdict(p),
    )


def _build_segments(t, artifact_win, max_ratio, ecg_hot, p: ArtifactParams) -> list:
    win_s, guard, gap = p.win_s, p.guard_s, p.min_clean_island_s
    segs: list = []
    for i, flag in enumerate(artifact_win):
        if not flag:
            continue
        s, e = t[i] - guard, t[i] + win_s + guard
        if segs and s <= segs[-1]["_raw_end"] + gap:
            segs[-1]["_raw_end"] = max(segs[-1]["_raw_end"], e)
            segs[-1]["max_ratio"] = max(segs[-1]["max_ratio"], float(max_ratio[i]))
            segs[-1]["_ecg"] = segs[-1]["_ecg"] or (bool(ecg_hot[i]) if ecg_hot is not None else False)
        else:
            segs.append({"_raw_start": s, "_raw_end": e, "max_ratio": float(max_ratio[i]),
                         "_ecg": (bool(ecg_hot[i]) if ecg_hot is not None else False)})
    out = []
    for sg in segs:
        start = max(0.0, sg["_raw_start"])
        end = sg["_raw_end"]
        out.append({
            "start_s": round(start, 2), "end_s": round(end, 2),
            "dur_s": round(end - start, 2), "max_ratio": round(sg["max_ratio"], 1),
            "ecg_disturbed": (None if ecg_hot is None else sg["_ecg"]),
        })
    return out


def _detect_bad_channels(ptp, n_hot, t, ch_names, p: ArtifactParams) -> list:
    """Kanal, der PERSISTENT isoliert auffällt (bei ruhigem Konsens) → Entfernen VORSCHLAGEN.

    Eigene, robuste Baseline je Kanal = **25. Perzentil** der ptp (nicht Median!): ein Kanal,
    der über weite Strecken defekt ist, würde den Median mit hochziehen; das 25. Perzentil
    bildet dagegen den weiterhin vorhandenen ruhigen Anteil des Kanals ab.
    """
    nch, nwin = ptp.shape
    base_lo = np.percentile(ptp, 25, axis=1)
    base_lo = np.where(base_lo > 1e-9, base_lo, 1e-9)[:, None]
    ratio_lo = ptp / base_lo
    # „isoliert auffällig" = Kanal > bad_iso_ratio, aber Gesamt-Konsens niedrig (keine Bewegung)
    iso = (ratio_lo > p.bad_iso_ratio) & (n_hot < p.consensus_n)[None, :]
    minute = (t // 60).astype(int)
    n_min = int(minute.max()) + 1 if nwin else 0
    suggestions = []
    for c in range(nch):
        # Anteil isoliert-auffälliger Fenster je Minute
        fracs = np.array([iso[c][minute == m].mean() if np.any(minute == m) else 0.0
                          for m in range(n_min)])
        bad_min = fracs > p.bad_min_frac
        # längsten zusammenhängenden Lauf schlechter Minuten finden
        run_start, best = None, None
        run = 0
        for m in range(n_min):
            if bad_min[m]:
                run += 1
                if run == 1:
                    run_start = m
                if run >= p.bad_min_minutes and (best is None or run > best[1]):
                    best = (run_start, run)
            else:
                run = 0
        if best is not None:
            since_m = best[0]
            frac_overall = float(iso[c][minute >= since_m].mean())
            suggestions.append({"index": c, "name": ch_names[c],
                                "since_s": float(since_m * 60),
                                "frac": round(frac_overall, 3)})
    return suggestions


# ──────────────────────────────────────────────────────────────────────────────
# Adapter — nimmt das App-EDF-Dict (load_and_prepare) und ruft die Kernfunktion.
# Berührt nichts Bestehendes; nur bei späterer Integration genutzt.
# ──────────────────────────────────────────────────────────────────────────────
def mask_from_edf(edf: dict, params: Optional[ArtifactParams] = None) -> ArtifactResult:
    """Bequemer Adapter: extrahiert EEG (aus eeg_map) + EKG (ecg_channels) aus dem
    App-Dict und ruft compute_artifact_mask. `edf['data']` ist in Volt → *1e6 → µV."""
    eeg_map = edf["eeg_map"]
    if not eeg_map:
        raise ValueError("Kein EEG-Kanal (eeg_map leer) — erst Kanalidentifikation durchführen.")
    names = list(eeg_map.keys())
    idxs = [eeg_map[k] for k in names]
    eeg_uv = edf["data"][idxs, :] * 1e6

    ecg_uv = None
    ecg_chs = edf.get("ecg_channels") or []
    if ecg_chs:
        ecg_name = ecg_chs[0]
        # bevorzugt das vorgefilterte EKG, sonst Rohkanal über ch_idx
        filt = edf.get("ecg_filtered") or {}
        if ecg_name in filt:
            ecg_uv = np.asarray(filt[ecg_name], dtype=float)
        elif ecg_name in edf.get("ch_idx", {}):
            ecg_uv = edf["data"][edf["ch_idx"][ecg_name], :].astype(float)

    return compute_artifact_mask(eeg_uv, edf["sfreq"], ecg_uv=ecg_uv,
                                 ch_names=names, params=params)
