"""
Manufacturer-independent EDF channel classification.

Signal features are the primary evidence; channel names are secondary hints
that adjust confidence but never override the signal-based verdict.

Supported types: ECG, EEG, EOG, EMG, REF, VITAL, UNKNOWN

Algorithm overview
------------------
1. Compute per-channel feature vector (amplitude, spectral, temporal)
2. Compute cross-channel correlation matrix for REF detection
3. Apply weighted rule-based scoring per type → winner + confidence
4. Post-process: limit ECG to best 2 candidates to suppress artifacts

Usage
-----
    from core.channel_classifier import classify_channels
    results = classify_channels(data, ch_names, sfreq)
    for ch, r in results.items():
        print(f"{ch}: {r.channel_type} ({r.confidence:.0f}%) — {r.reasons[0]}")
"""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List

# ── Type labels ────────────────────────────────────────────────────────────────
ECG   = "ECG"
EEG   = "EEG"
EOG   = "EOG"
EMG   = "EMG"
REF   = "REF"
VITAL = "VITAL"
UNKN  = "UNKNOWN"

# ── Name-based hint tables (upper-case, no spaces/dashes) ──────────────────────
_ECG_HINTS   = ("ECG", "EKG", "EKG1", "EKG2", "CARD", "HEART", "X1", "X2",
                "PULSE", "HERZ", "CARDIAC")
_EOG_HINTS   = ("EOG", "E1", "E2", "LOC", "ROC", "LEOG", "REOG", "EOGL", "EOGR",
                "LEFTEYE", "RIGHTEYE")
_EMG_HINTS   = ("EMG", "CHIN", "CHIN1", "CHIN2", "LEGL", "LEGR", "MUSCLE",
                "MUSC", "MYOG", "SUBMENT")
_REF_HINTS   = ("REF", "A1", "A2", "M1", "M2", "LE", "AVREF", "REST", "MASTOID",
                "LINKED", "IPSI", "CONTRA")
_VITAL_HINTS = ("SPO2", "SAO2", "ETCO2", "CO2WAVE", "RESPIRATION", "AIRFLOW",
                "THERMISTOR", "PIEZO", "SNORE", "POSITION", "ACTIGRAPHY",
                "ACTIVITY", "PLETH", "TIDAL", "OXYGEN", "LIGHT", "PHOTIC",
                "STIM", "TRIGGER", "PULSE_OX", "NASAL", "ORAL", "ABDO",
                "THOR", "EFFORT", "BELT")
# Standard 10-20 / 10-10 electrode labels — used to boost EEG confidence.
# Includes extended high-density systems (64/128/256 ch) used by BCI2000,
# Biosemi ActiveTwo, EGI/Geodesic, and research HDEEG setups.
_EEG_ELECTRODES = (
    # Core 10-20
    "FP1","FP2","F3","F4","C3","C4","P3","P4","O1","O2",
    "F7","F8","T3","T4","T5","T6","T7","T8","P7","P8",
    "FZ","CZ","PZ","OZ",
    # 10-10 intermediates
    "AFZ","FCZ","CPZ","POZ","FPZ","TPZ","IZ",
    "AF3","AF4","AF7","AF8",
    "FC1","FC2","FC3","FC4","FC5","FC6",
    "CP1","CP2","CP3","CP4","CP5","CP6",
    "PO3","PO4","PO7","PO8",
    "FT7","FT8","FT9","FT10","TP7","TP8","TP9","TP10",
    "T9","T10",
    "F1","F2","F5","F6",
    "C1","C2","C5","C6",
    "P1","P2","P5","P6",
    # 10-5 / high-density extensions (Biosemi, EGI)
    "AF1","AF2","AF5","AF6",
    "AFF1","AFF2","AFF5","AFF6","AFFZ",
    "FC1H","FC2H",
    "FCC1","FCC2","FCC3","FCC4","FCC5","FCC6",
    "CCP1","CCP2","CCP3","CCP4","CCP5","CCP6",
    "CPP1","CPP2","CPP3","CPP4","CPP5","CPP6",
    "PPO1","PPO2","PPO3","PPO4","PPO5","PPO6",
    "POO1","POO2","POO3","POO4","POO9","POO10",
    "OI1","OI2",
)

# Channels that are never ECG regardless of signal — common non-ECG names
_ANTI_ECG = ("DC", "SPO2", "ETCO2", "CO2", "$A", "PG", "ANNOT", "STIM",
             "PIEZO", "RESP", "AIRFLOW", "SNORE", "PHOTIC", "TRIGGER",
             "THORAX", "ABDOM", "EFFORT", "POSITION", "ACTI",
             # Wearable EEG electrode types (BTE, nape, crown, ear)
             "BTE", "CROSS", "CROWN", "NAPE", "FOREHEAD", "MASTOID",
             "SENSORDOT", " SD")


# ── Public API ─────────────────────────────────────────────────────────────────

@dataclass
class ChannelResult:
    channel_type: str          # ECG | EEG | EOG | EMG | REF | VITAL | UNKNOWN
    confidence: float          # 0–100 %
    reasons: List[str] = field(default_factory=list)
    features: dict = field(default_factory=dict)

    def __repr__(self) -> str:  # noqa: D105
        rs = "; ".join(self.reasons[:2])
        return f"<{self.channel_type} {self.confidence:.0f}% [{rs}]>"


def classify_channels(
    data: np.ndarray,
    ch_names: List[str],
    sfreq: float,
    max_analysis_sec: float = 120.0,
    filename: str = "",
) -> Dict[str, ChannelResult]:
    """Classify every channel in an EDF recording.

    Parameters
    ----------
    data:             shape (n_channels, n_samples), unit: Volt
    ch_names:         list of channel name strings
    sfreq:            sampling frequency in Hz
    max_analysis_sec: limit analysis to this window for speed

    Returns
    -------
    dict  channel_name → ChannelResult
    """
    n_ch, n_samples = data.shape
    n_use = min(n_samples, max(int(5 * sfreq), int(max_analysis_sec * sfreq)))

    seg = data[:, :n_use].copy().astype(np.float64)
    seg -= seg.mean(axis=1, keepdims=True)

    # Context flags derived from filename / recording type
    fn_up = filename.upper()
    # BIDS _eeg.edf / _eeg.bdf → all channels are EEG (no dedicated ECG lead)
    is_bids_eeg_file = fn_up.endswith("_EEG.EDF") or fn_up.endswith("_EEG.BDF")

    # Per-channel features
    feats = [_compute_features(seg[i], sfreq) for i in range(n_ch)]

    # Cross-channel correlation (capped at 30 s for speed)
    n_corr = min(n_use, int(30 * sfreq))
    corr_mat = _correlation_matrix(seg[:, :n_corr])
    for i in range(n_ch):
        row = np.abs(corr_mat[i]).copy()
        row[i] = 0.0
        feats[i]["mean_abs_corr"] = float(np.mean(row))
        feats[i]["max_abs_corr"]  = float(np.percentile(row, 95))

    # Classify
    results: Dict[str, ChannelResult] = {}
    for i, ch in enumerate(ch_names):
        results[ch] = _classify_one(feats[i], ch, is_bids_eeg_file=is_bids_eeg_file)

    # Post-process: keep at most the best 2 ECG candidates.
    # Quality score = confidence × amplitude, so a weak crosstalk channel (low p2p)
    # loses to a dedicated lead even at equal confidence.
    # A second channel is only kept if it also has strong ECG evidence (p2p > 0.5 mV
    # and confidence > 75 %) — this preserves dual-lead setups (e.g. NeuroFax X + T)
    # while removing low-amplitude ECG-artifact channels.
    ecg_list = [(ch, r) for ch, r in results.items() if r.channel_type == ECG]
    if len(ecg_list) > 1:
        def _ecg_quality(item):
            _, r = item
            p2p = r.features.get("p2p_mv", 0)
            return r.confidence * min(p2p, 3.0)  # cap at 3 mV

        ecg_list.sort(key=lambda x: -_ecg_quality(x))
        for ch, r in ecg_list[1:]:
            p2p = r.features.get("p2p_mv", 0)
            if r.confidence < 75 or p2p < 0.5:
                r.reasons.append("zurückgestuft: kein dedizierter EKG-Kanal (p2p oder Confidence zu niedrig)")
                r.channel_type = UNKN
        # Hard cap at 2
        still_ecg = [(ch, r) for ch, r in ecg_list if r.channel_type == ECG]
        if len(still_ecg) > 2:
            for ch, r in still_ecg[2:]:
                r.reasons.append("zurückgestuft: maximal 2 EKG-Kanäle")
                r.channel_type = UNKN

    # Post-process: limit EOG to at most 4 channels.
    # Real EEG setups have 1–4 dedicated EOG electrodes. If more channels score
    # as EOG, the likely cause is a high-density EEG recording with large frontal
    # or peripheral amplitude (Fp1/Fp2, T7/T9, etc.). Demote low-confidence
    # extras back to EEG.
    eog_list = [(ch, r) for ch, r in results.items() if r.channel_type == EOG]
    if len(eog_list) > 4:
        eog_list.sort(key=lambda x: -x[1].confidence)
        for ch, r in eog_list[4:]:
            if r.confidence < 80:
                r.reasons.append("zurückgestuft: zu viele EOG-Kandidaten (max. 4)")
                r.channel_type = EEG

    # BIDS _eeg.edf: all non-flat channels are EEG by file-format convention.
    # Ambiguous classifications (< 80% confidence) default to EEG.
    # High-confidence EMG/EOG (≥ 80%) survive — they represent contamination,
    # but the user should know about it.
    if is_bids_eeg_file:
        for r in results.values():
            if r.channel_type not in (UNKN, VITAL, EEG) and r.confidence < 80:
                r.reasons.insert(0, "BIDS _eeg.edf: EEG per Dateikennzeichnung")
                r.channel_type = EEG

    return results


def make_short_name(ch: str) -> str:
    """Derive a clean electrode label from any manufacturer naming convention.

    Examples
    --------
    "EEG Fp1-Ref"  → "Fp1"
    "EEG:Fp1"      → "Fp1"
    "POL Fp1"      → "Fp1"
    "Fp1"          → "Fp1"
    "Chan 3"       → "Chan 3"
    """
    s = ch.strip()
    # Strip common prefixes (standard clinical + wearable device prefixes)
    for prefix in ("EEG ", "EEG:", "POL ", "BIP ", "REF ", "MON ",
                   "BTE ", "SD ", "CHAN ", "CHANNEL ", "CH ", "EL "):
        if s.upper().startswith(prefix.upper()):
            s = s[len(prefix):].strip()
            break
    # Strip common suffixes (reference markers)
    for suffix in ("-Ref", "-REF", "-ref", "-A1", "-A2", "-M1", "-M2", "-LE"):
        if s.endswith(suffix):
            s = s[: -len(suffix)].strip()
    # Strip BCI2000-style trailing dot-padding: "Fp1." → "Fp1", "C3.." → "C3"
    s = s.rstrip("._")
    return s or ch


# ── Feature extraction ─────────────────────────────────────────────────────────

def _compute_features(sig: np.ndarray, sfreq: float) -> dict:
    """Return a feature dict for a single zero-mean channel segment (Volt)."""
    from scipy.signal import welch, find_peaks, butter, filtfilt
    from scipy.stats import kurtosis as _kurtosis

    f: dict = {}
    n = len(sig)

    # ── Amplitude (converted to mV for intuitive thresholds) ─────────────────
    sig_mv = sig * 1000.0
    f["std_mv"]  = float(np.std(sig_mv))
    f["p2p_mv"]  = float(np.ptp(sig_mv))
    f["iqr_mv"]  = float(np.percentile(sig_mv, 75) - np.percentile(sig_mv, 25))
    f["rms_mv"]  = float(np.sqrt(np.mean(sig_mv ** 2)))

    # ── Flat / dead channel ───────────────────────────────────────────────────
    # Use std as primary criterion — n_unique can be low for synthetic/integer signals
    # Real ADC output always has many unique values, but we don't rely on that.
    n_unique = len(np.unique(np.round(sig * 1e7)))
    f["is_flat"] = bool(f["std_mv"] < 5e-5)  # < 50 nV std → dead channel
    if f["is_flat"]:
        for k in ("kurtosis","dom_freq","spectral_entropy",
                  "delta_rel","theta_rel","alpha_rel","beta_rel",
                  "gamma_rel","slow_rel","hf_rel","qrs_rate","rhythmicity"):
            f[k] = 0.0
        return f

    # ── Higher-order statistics ───────────────────────────────────────────────
    f["kurtosis"] = float(_kurtosis(sig, fisher=True, bias=False))

    # ── Welch PSD ─────────────────────────────────────────────────────────────
    nperseg = max(8, min(int(sfreq * 4), n // 4))
    freqs, psd = welch(sig, fs=sfreq, nperseg=nperseg, scaling="density")

    def _rel(lo: float, hi: float) -> float:
        mask = (freqs >= lo) & (freqs < hi)
        tot  = psd[freqs >= 0.3].sum()
        return float(psd[mask].sum() / (tot + 1e-30)) if mask.any() else 0.0

    f["delta_rel"] = _rel(0.5,  4.0)
    f["theta_rel"] = _rel(4.0,  8.0)
    f["alpha_rel"] = _rel(8.0, 13.0)
    f["beta_rel"]  = _rel(13.0,30.0)
    f["gamma_rel"] = _rel(30.0, min(70.0, sfreq / 2 - 1))
    f["slow_rel"]  = _rel(0.3,  4.0)
    f["hf_rel"]    = _rel(30.0, min(150.0, sfreq / 2 - 1))

    valid = (freqs >= 0.5) & (freqs < min(100.0, sfreq / 2))
    f["dom_freq"] = float(freqs[valid][np.argmax(psd[valid])]) if valid.any() else 0.0

    # Normalized spectral entropy
    p_hi = psd[freqs >= 0.3]
    p_n  = p_hi / (p_hi.sum() + 1e-30)
    p_n  = p_n[p_n > 0]
    f["spectral_entropy"] = float(
        -np.sum(p_n * np.log2(p_n)) / (np.log2(len(p_n) + 1) + 1e-30)
    )

    # ── QRS / periodicity detection ───────────────────────────────────────────
    # Two filter variants:
    # 1. Narrow 8-20 Hz: isolates QRS complex, strongly attenuates T-waves
    #    (T-waves are 0.5-5 Hz) → high rhythmicity for real ECG with natural HRV
    # 2. Broad 1-40 Hz: fallback for other periodic signals
    # Best rhythmicity across all attempts is kept.
    nyq = sfreq / 2.0
    _filter_configs = [
        (8.0, 20.0, 0.40),   # narrow QRS band, 0.4 s min distance (suppresses T-wave)
        (1.0, 40.0, 0.30),   # broad band fallback
    ]
    _sig_variants: list = []
    for lo, hi, min_d in _filter_configs:
        try:
            f_lo = max(lo / nyq, 0.01)
            f_hi = min(hi / nyq, 0.98)
            if 0 < f_lo < f_hi:
                b, a = butter(4, [f_lo, f_hi], btype="band")
                _sig_variants.append((filtfilt(b, a, sig), min_d))
        except Exception:
            pass
    if not _sig_variants:
        _sig_variants = [(sig.copy(), 0.30)]

    best_rate     = 0.0
    best_rhythmic = 0.0

    for sig_bp, min_dist_s in _sig_variants:
        for polarity in (sig_bp, -sig_bp):
            thresh = np.percentile(np.abs(polarity), 88)
            if thresh < 1e-10:
                continue
            peaks, _ = find_peaks(polarity, height=thresh,
                                   distance=max(1, int(sfreq * min_dist_s)))
            if len(peaks) < 4:
                continue
            rr = np.diff(peaks) / sfreq
            # Robust pass: discard outlier RR intervals (missed beats, T-wave hits)
            if len(rr) >= 5:
                rr_med = np.median(rr)
                rr_filt = rr[(rr > rr_med * 0.5) & (rr < rr_med * 1.7)]
                if len(rr_filt) >= 4:
                    rr = rr_filt
            mean_rr = rr.mean()
            if mean_rr < 0.01:
                continue
            rate = 60.0 / mean_rr
            cv   = rr.std() / (mean_rr + 1e-6)
            if 30 <= rate <= 210:
                rhythmicity = max(0.0, 1.0 - cv)
                if rhythmicity > best_rhythmic:
                    best_rate     = rate
                    best_rhythmic = rhythmicity

    f["qrs_rate"]    = best_rate
    f["rhythmicity"] = best_rhythmic

    return f


def _correlation_matrix(seg: np.ndarray) -> np.ndarray:
    n_ch, n_s = seg.shape
    std = seg.std(axis=1, keepdims=True)
    std[std < 1e-12] = 1.0
    normed = seg / std
    mat = (normed @ normed.T) / n_s
    np.fill_diagonal(mat, 1.0)
    return mat


# ── Classification rules ───────────────────────────────────────────────────────

def _classify_one(f: dict, ch_name: str, is_bids_eeg_file: bool = False) -> ChannelResult:
    # Normalise name for substring matching
    ch_up = (ch_name.upper()
             .replace(" ", "").replace("-", "").replace("_", "")
             .replace(":", "").replace(".", ""))

    # ── VITAL: name-based fast path (signal shape varies wildly) ─────────────
    if any(v in ch_up for v in _VITAL_HINTS):
        # Guard: exact short-name must NOT be a 10-20 electrode (e.g. "O2" in "SpO2")
        short_up = make_short_name(ch_name).upper().replace(" ", "")
        if short_up not in _EEG_ELECTRODES:
            return ChannelResult(
                channel_type=VITAL, confidence=85.0,
                reasons=["Kanalname enthält Vital-Sign-Muster"],
                features=f,
            )

    # ── EDF Annotations channel ───────────────────────────────────────────────
    if "ANNOTATION" in ch_up or "STATUS" in ch_up:
        return ChannelResult(
            channel_type=UNKN, confidence=99.0,
            reasons=["EDF-Annotationskanal"],
            features=f,
        )

    # ── Flat / dead ───────────────────────────────────────────────────────────
    if f.get("is_flat"):
        return ChannelResult(
            channel_type=UNKN, confidence=95.0,
            reasons=["Flacher/toter Kanal — keine Signalvarianz"],
            features=f,
        )

    # Anti-ECG name guard: certain channel names + named 10-20 EEG electrodes
    # Named 10-20 electrodes (Fp1, C3, O2 …) are EEG by definition — never ECG.
    _is_named_eeg_ch = make_short_name(ch_name).upper().replace(" ", "") in _EEG_ELECTRODES
    is_anti_ecg = any(p in ch_up for p in _ANTI_ECG) or _is_named_eeg_ch

    scores: Dict[str, float] = {ECG: 0.0, EEG: 0.0, EOG: 0.0, EMG: 0.0, REF: 0.0}
    reasons: Dict[str, List[str]] = {t: [] for t in scores}

    std_mv = f["std_mv"]
    p2p_mv = f["p2p_mv"]
    kurt   = f["kurtosis"]
    rhyth  = f["rhythmicity"]
    qrs    = f["qrs_rate"]
    dom    = f["dom_freq"]
    slow   = f["slow_rel"]
    hf     = f["hf_rel"]
    gamma  = f["gamma_rel"]
    delta  = f["delta_rel"]
    theta  = f["theta_rel"]
    alpha  = f["alpha_rel"]
    beta   = f["beta_rel"]
    s_ent  = f["spectral_entropy"]
    mac    = f.get("mean_abs_corr", 0.0)

    # ── ECG ───────────────────────────────────────────────────────────────────
    # Key calibration insight (from wearable EEG analysis):
    # Wearable/BTE EEG electrodes pick up ECG artifact → periodic peaks at 80-120 bpm
    # with rhythmicity 0.50-0.70 and kurtosis 2-4. Real ECG leads have:
    #   - p2p > 0.3 mV (wearable artifact: 0.1-0.25 mV)
    #   - rhythmicity > 0.75 (artifact: 0.50-0.70)
    #   - kurtosis > 4 (artifact: 2-4)
    # BIDS _eeg.edf files contain no dedicated ECG lead — override to EEG.
    if not is_anti_ecg and not is_bids_eeg_file:
        # QRS rate — base periodicity score.
        # Note: real ECG with HRV or arrhythmia (AF) can have rhythmicity 0.3-0.6.
        # Wearable EEG artifact has similar rhythmicity but much smaller p2p amplitude.
        # Primary discrimination is p2p amplitude + kurtosis, not rhythmicity alone.
        if 40 <= qrs <= 160:
            rate_score = 35 if rhyth > 0.70 else (22 if rhyth > 0.50 else (12 if rhyth > 0.30 else 5))
            scores[ECG] += rate_score
            reasons[ECG].append(f"QRS-Rate {qrs:.0f} bpm (physiologisch)")
        elif 30 < qrs < 40 or 160 < qrs <= 200:
            rate_score = 15 if rhyth > 0.70 else 5
            scores[ECG] += rate_score
            reasons[ECG].append(f"QRS-Rate {qrs:.0f} bpm (Grenzbereich)")

        # Clinical ECG morphology bonus: large amplitude + leptokurtosis + periodic rate.
        # This combination is near-diagnostic for a real ECG lead, even with irregular rhythm
        # (HRV, AF, sinus arrhythmia). Wearable EEG artifact has p2p < 0.3 mV and is blocked
        # by the p2p gate below; EEG channels have kurtosis < 3.5.
        # Kurt cap at 80: extreme kurtosis (>80) indicates artifact spikes, not QRS complexes.
        if p2p_mv > 0.5 and 3.5 < kurt <= 80 and 40 <= qrs <= 160:
            scores[ECG] += 28
            reasons[ECG].append(f"EKG-Morphologie: p2p {p2p_mv:.2f} mV, Kurtosis {kurt:.1f}")

        # Extreme kurtosis (>100): non-physiological — artifact spikes, pacemaker, electrode pop
        if kurt > 100:
            scores[ECG] -= 20
            reasons[ECG].append(f"Kurtosis {kurt:.0f} (Artefaktspike, kein QRS)")

        # Rhythmicity bonus — additional evidence on top of rate score
        if rhyth > 0.75:
            scores[ECG] += 22 * rhyth
            reasons[ECG].append(f"Rhythmizität {rhyth:.2f} (regelmäßig)")
        elif rhyth > 0.65:
            scores[ECG] += 12 * rhyth
            reasons[ECG].append(f"Rhythmizität {rhyth:.2f}")

        # Kurtosis — raised threshold to exclude wearable ECG-contaminated EEG (kurt ~2-4)
        if 4.0 <= kurt <= 80:
            scores[ECG] += min(20, kurt * 1.5)
            reasons[ECG].append(f"Kurtosis {kurt:.1f} (leptokurtisch/QRS-Spitzen)")
        elif 2.5 <= kurt < 4.0:
            scores[ECG] += 6
            reasons[ECG].append(f"Kurtosis {kurt:.1f} (leicht leptokurtisch)")

        # Amplitude gate — real ECG p2p > 0.3 mV; wearable artifact typically < 0.25 mV
        if p2p_mv > 0.5:
            scores[ECG] += 12
            reasons[ECG].append(f"Peak-to-Peak {p2p_mv:.2f} mV (EKG-Bereich)")
        elif p2p_mv > 0.3:
            scores[ECG] += 6
            reasons[ECG].append(f"Peak-to-Peak {p2p_mv:.2f} mV (EKG-Bereich)")
        elif p2p_mv < 0.3 and qrs > 0:
            scores[ECG] -= 10
            reasons[ECG].append(f"Peak-to-Peak {p2p_mv:.2f} mV (EKG-Artefakt-Verdacht)")

        # Name hints
        if any(n in ch_up for n in _ECG_HINTS):
            scores[ECG] += 20
            reasons[ECG].append("Kanalname: EKG-Bezeichnung erkannt")

        # Penalise: ECG should NOT look like pure EEG spectrum
        if s_ent > 0.92 and qrs == 0.0:
            scores[ECG] -= 20

    elif is_bids_eeg_file:
        # BIDS _eeg.edf: file convention guarantees no dedicated ECG lead
        reasons[ECG].append("BIDS _eeg.edf: kein dedizierter EKG-Kanal erwartet")

    # ── EEG ───────────────────────────────────────────────────────────────────
    # Amplitude in scalp EEG range: std typically 5–200 µV (0.005–0.2 mV)
    if 0.002 < std_mv < 1.5:
        scores[EEG] += 25
        reasons[EEG].append(f"Amplitude EEG-typisch ({std_mv * 1000:.0f} µV std)")
    elif 1.5 <= std_mv < 4.0:
        scores[EEG] += 8
        reasons[EEG].append(f"Amplitude erhöht ({std_mv * 1000:.0f} µV std)")

    # Physiological band distribution
    eeg_band_total = delta + theta + alpha + beta
    if eeg_band_total > 0.75:
        scores[EEG] += 18
        reasons[EEG].append(f"EEG-Bänder {eeg_band_total:.0%} der Energie")

    # High spectral entropy → complex aperiodic signal
    if s_ent > 0.80:
        scores[EEG] += 16
        reasons[EEG].append(f"Spektrale Entropie {s_ent:.2f} (komplex/aperiodisch)")
    elif s_ent > 0.70:
        scores[EEG] += 8

    # Moderate cross-correlation with other channels
    if 0.08 < mac < 0.75:
        scores[EEG] += 10
        reasons[EEG].append(f"Kanalkorrelation {mac:.2f} (EEG-typisch)")

    # Low kurtosis (EEG is approximately Gaussian)
    if -0.5 < kurt < 4:
        scores[EEG] += 8
        reasons[EEG].append(f"Kurtosis {kurt:.1f} (EEG-typisch)")

    # 10-20 electrode name
    short = make_short_name(ch_name).upper().replace(" ", "")
    if short in _EEG_ELECTRODES:
        scores[EEG] += 18
        reasons[EEG].append("10-20-Elektrodenbezeichnung erkannt")
    elif "EEG" in ch_up:
        scores[EEG] += 10
        reasons[EEG].append("Kanalname enthält 'EEG'")

    # Penalise: channel looks like dedicated ECG lead (large amplitude + rhythmic)
    # Requires p2p > 0.4 mV to spare EEG channels that merely carry ECG artifact
    # (EEG artifact from heart has p2p 0.1-0.35 mV; real ECG lead has p2p > 0.5 mV)
    if qrs > 40 and rhyth > 0.6 and kurt > 1.5 and p2p_mv > 0.4:
        scores[EEG] -= 25

    # ── EOG ───────────────────────────────────────────────────────────────────
    # Named 10-20 electrodes are NEVER EOG — they may have slow/large signals
    # (especially frontopolar Fp1/Fp2 or temporal channels) but they are EEG.
    _is_named_eeg = make_short_name(ch_name).upper().replace(" ", "") in _EEG_ELECTRODES

    if not _is_named_eeg:
        # Large amplitude, energy concentrated in very slow waves
        if p2p_mv > 0.3:
            scores[EOG] += 12
            reasons[EOG].append(f"Peak-to-Peak {p2p_mv:.2f} mV (groß)")
        if p2p_mv > 1.0:
            scores[EOG] += 10

        if slow > 0.55:
            scores[EOG] += 22
            reasons[EOG].append(f"Slow-Band-Anteil {slow:.0%} (EOG-typisch)")

        if dom > 0 and dom < 4.0:
            scores[EOG] += 14
            reasons[EOG].append(f"Dominante Frequenz {dom:.1f} Hz (< 4 Hz)")

    if any(n in ch_up for n in _EOG_HINTS):
        scores[EOG] += 25  # name hint always applies — explicitly named EOG channel
        reasons[EOG].append("Kanalname: EOG-Bezeichnung erkannt")

    # ── EMG ───────────────────────────────────────────────────────────────────
    # High-frequency energy dominates
    if gamma > 0.25:
        scores[EMG] += 28
        reasons[EMG].append(f"Gamma-Anteil {gamma:.0%} (EMG-typisch)")
    elif gamma > 0.15:
        scores[EMG] += 14

    if hf > 0.30:
        scores[EMG] += 20
        reasons[EMG].append(f"HF-Anteil (>30 Hz): {hf:.0%}")

    if std_mv > 0.05:
        scores[EMG] += 8
        reasons[EMG].append(f"Amplitude {std_mv * 1000:.0f} µV std")

    if any(n in ch_up for n in _EMG_HINTS):
        scores[EMG] += 22
        reasons[EMG].append("Kanalname: EMG-Bezeichnung erkannt")

    # ── REF ───────────────────────────────────────────────────────────────────
    # Very low variance (near-zero signal when referenced to itself)
    if std_mv < 0.008:
        scores[REF] += 35
        reasons[REF].append(f"Sehr geringe Variabilität ({std_mv * 1000:.2f} µV std)")
    elif std_mv < 0.02:
        scores[REF] += 18
        reasons[REF].append(f"Geringe Variabilität ({std_mv * 1000:.2f} µV std)")

    # High correlation with many channels (reference bleeds into all)
    if mac > 0.5:
        scores[REF] += 22
        reasons[REF].append(f"Hohe mittlere Kanalkorrelation {mac:.2f}")
    elif mac > 0.3:
        scores[REF] += 10

    if any(n in ch_up for n in _REF_HINTS):
        scores[REF] += 16
        reasons[REF].append("Kanalname: Referenz-Bezeichnung erkannt")

    # ── Winner selection ──────────────────────────────────────────────────────
    best_type  = max(scores, key=lambda t: scores[t])
    best_score = scores[best_type]

    if best_score <= 5:
        return ChannelResult(
            channel_type=UNKN, confidence=0.0,
            reasons=["keine eindeutigen Merkmale für Kanaltyp"],
            features=f,
        )

    # Confidence calibration:
    # Raw score of ~35 (textbook ECG with clear QRS) → ~70%
    # Additional features push toward 95%
    # Scale: 0–100 raw → 0–100% confidence (nonlinear, capped at 97%)
    sorted_scores = sorted(scores.values(), reverse=True)
    margin        = sorted_scores[0] - sorted_scores[1] if len(sorted_scores) > 1 else sorted_scores[0]

    confidence = min(97.0, best_score * 1.2)
    if margin > 25:
        confidence = min(97.0, confidence + 8)
    if margin < 10:
        confidence = max(0.0, confidence - 12)

    return ChannelResult(
        channel_type=best_type,
        confidence=round(confidence, 1),
        reasons=reasons[best_type][:4],
        features=f,
    )
