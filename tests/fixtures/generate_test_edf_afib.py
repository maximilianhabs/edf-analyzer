"""
Synthetisches Ground-Truth-EDF #2 für den EDF-Analyzer: Vorhofflimmern (AFib).

Ergänzt `generate_test_edf_datei.py` (normaler Sinusrhythmus + normales EEG) um einen
zweiten Referenzfall mit klar definierter, elektrophysiologisch begründeter AFib-Signatur —
zum Prüfen der Rhythmus-Screening-Pipeline (CosEn, `analysis/rhythm_screening.py`) und der
P-Wellen-Kohärenz (`analysis/p_wave_analysis.py`) gegen bekannte Sollwerte, statt nur an
realen (nicht versionierbaren) Patientendateien.

Elektrophysiologische AFib-Charakteristika, die hier gezielt modelliert werden (siehe
[[project_edf_rhythm_screening]] für die Herleitung der Erkennungs-Schwellen):

1. **Absolute Arrhythmie ("irregularly irregular")**: RR-Intervalle werden UNABHÄNGIG
   voneinander gezogen (i.i.d. Normalverteilung, SD 120ms um Mittel 632ms/~95bpm) — KEINE
   sinusoidale RSA-Modulation wie in der Normal-Datei, weil AFib per Definition nicht vom
   Sinusknoten getaktet wird. Kalibriert an `analysis/rhythm_screening.py::cosen()`: SD=120ms
   ergibt CosEn ≈ -0,43 (Zielbereich Sarkar/IOPscience 2015: Median -0,5, Range -0,8 bis -0,3;
   deckungsgleich mit unserem einzigen bestätigten Referenzfall CA1772QO: -0,44).
2. **Keine P-Welle / Flimmerwellen statt geordneter Vorhofaktivität**: statt eines fixen
   PR-Intervalls (wie im Normal-File) wird eine KONTINUIERLICHE, zum R-Zacken-Timing
   UNKORRELIERTE Flimmerwellen-Baseline erzeugt (Bandpass-Rauschen 5-9Hz ≈ 300-540/min,
   Literaturbereich f-Wellen 350-600/min). Da die Ensemble-Mittelung in
   `p_wave_analysis.py` um den R-Zeitpunkt ausrichtet, mittelt sich diese unkorrelierte
   Aktivität heraus → niedrige P-Kohärenz. Verifiziert: Kohärenz ≈ 0,10 (deutlich unter der
   "nicht abgrenzbar"-Schwelle 0,35 aus `p_wave_analysis.COH_UNCERTAIN`).
3. **QRS-Morphologie unverändert** (schmaler Kammerkomplex, normale AV-Überleitung) —
   AFib verändert die Kammer-Erregung selbst nicht, nur die Vorhof-Aktivität und die
   Unregelmäßigkeit der Überleitung. Gleiches QRS-T-Template wie in der Normal-Datei.
4. **Etwas schnellere Kammerfrequenz** (~95 statt 70 bpm) — typisch für unbehandeltes/
   nur teilkontrolliertes AFib, kein zwingendes Kriterium, aber realistischer als eine
   AFib-Datei mit "normaler" Ruheherzfrequenz.

Kein Anspruch auf biologische Exaktheit über diese 4 Punkte hinaus — reine Pipeline-Prüfung.
EEG-Hintergrund unverändert vom Normal-File übernommen (kein eigener EEG-Befund hier von
Interesse, nur als vollständiger 19-Kanal-Datensatz für die App-Kompatibilität).
"""
import numpy as np
import pyedflib
import json
from datetime import datetime
from scipy.signal import butter, filtfilt

rng = np.random.default_rng(43)

FS = 200.0
DUR_S = 600  # 10 Minuten
N = int(FS * DUR_S)
t = np.arange(N) / FS

EEG_CHANNELS = ["Fp1", "Fp2", "F7", "F3", "Fz", "F4", "F8",
                "T3", "C3", "Cz", "C4", "T4",
                "T5", "P3", "Pz", "P4", "T6", "O1", "O2"]
ALL_LABELS = EEG_CHANNELS + ["POL X1"]


def make_1f_noise(n, fs, exponent, rng):
    freqs = np.fft.rfftfreq(n, d=1.0 / fs)
    white = rng.standard_normal(n)
    spec = np.fft.rfft(white)
    scale = np.ones_like(freqs)
    nz = freqs > 0
    scale[nz] = freqs[nz] ** (-exponent / 2.0)
    scale[~nz] = 0.0
    spec *= scale
    sig = np.fft.irfft(spec, n=n)
    return sig / (np.std(sig) or 1.0)


APERIODIC_EXPONENT = 2.20
ALPHA_FREQ_HZ = 10.0
ALPHA_AMPLITUDE_UV = {
    "O1": 33.0, "O2": 27.5, "Pz": 24.0, "P3": 22.0, "P4": 21.0,
    "T5": 14.0, "T6": 13.0,
    "Cz": 10.0, "C3": 9.0, "C4": 9.0,
    "Fz": 6.0, "F3": 5.5, "F4": 5.0, "F7": 4.0, "F8": 4.0,
    "Fp1": 3.0, "Fp2": 3.0, "T3": 6.0, "T4": 6.0,
}
DELTA_FREQ_HZ, DELTA_AMPL_UV = 2.0, 8.0
THETA_FREQ_HZ, THETA_AMPL_UV = 6.0, 5.0
BETA_FREQ_HZ,  BETA_AMPL_UV  = 20.0, 3.0


def build_eeg_signal(ch, rng):
    bg = make_1f_noise(N, FS, APERIODIC_EXPONENT, rng) * 4.0
    sig = bg.copy()
    amp = ALPHA_AMPLITUDE_UV.get(ch, 5.0)
    sig += amp * np.sin(2 * np.pi * ALPHA_FREQ_HZ * t + rng.uniform(0, 2 * np.pi))
    sig += DELTA_AMPL_UV * np.sin(2 * np.pi * DELTA_FREQ_HZ * t + rng.uniform(0, 2 * np.pi))
    sig += THETA_AMPL_UV * np.sin(2 * np.pi * THETA_FREQ_HZ * t + rng.uniform(0, 2 * np.pi))
    sig += BETA_AMPL_UV  * np.sin(2 * np.pi * BETA_FREQ_HZ  * t + rng.uniform(0, 2 * np.pi))
    return sig


# ── EKG: absolute Arrhythmie (i.i.d. RR) + Flimmerwellen statt P-Welle ───────
HR_MEAN_BPM = 95.0
MEAN_RR_S = 60.0 / HR_MEAN_BPM
RR_SD_MS = 120.0          # kalibriert auf CosEn ~ -0.43, siehe Docstring oben
RR_CLIP_S = (0.30, 1.60)  # physiologische Grenzen (harte Tachykardie bis Pause)
FWAVE_LO_HZ, FWAVE_HI_HZ = 5.0, 9.0   # ~300-540/min, im f-Wellen-Literaturbereich 350-600/min
FWAVE_AMPL_MV = 0.08


def build_ecg_signal():
    beat_times = [0.30]
    while beat_times[-1] < DUR_S:
        rr = rng.normal(MEAN_RR_S, RR_SD_MS / 1000.0)
        rr = float(np.clip(rr, *RR_CLIP_S))
        beat_times.append(beat_times[-1] + rr)
    beat_times = np.array(beat_times[:-1])

    sig = np.zeros(N)
    qrs_t = np.linspace(-0.06, 0.06, int(0.12 * FS))
    qrs_template = 1.2 * np.exp(-(qrs_t ** 2) / (2 * 0.008 ** 2))
    q_dip = -0.25 * np.exp(-((qrs_t + 0.02) ** 2) / (2 * 0.006 ** 2))
    s_dip = -0.30 * np.exp(-((qrs_t - 0.025) ** 2) / (2 * 0.007 ** 2))
    qrs_template += q_dip + s_dip
    t_wave_t = np.linspace(-0.12, 0.12, int(0.24 * FS))
    t_wave = 0.35 * np.exp(-(t_wave_t ** 2) / (2 * 0.05 ** 2))
    half_qrs = len(qrs_template) // 2
    half_t = len(t_wave) // 2

    for bt in beat_times:
        i_r = int(bt * FS)
        i0, i1 = i_r - half_qrs, i_r - half_qrs + len(qrs_template)
        if 0 <= i0 and i1 <= N:
            sig[i0:i1] += qrs_template
        # Kein fixes PR-Intervall (P-Welle) — QRS folgt direkt auf die (unregelmaessige)
        # atriale Aktivitaet, T-Welle bleibt unveraendert an den QRS gekoppelt.
        i_t = i_r + int(0.16 * FS)
        j0, j1 = i_t - half_t, i_t - half_t + len(t_wave)
        if 0 <= j0 and j1 <= N:
            sig[j0:j1] += t_wave

    # Flimmerwellen: kontinuierliches, zum R-Timing UNKORRELIERTES Bandpass-Rauschen
    # (siehe Docstring Punkt 2) statt einer an jeden Schlag gekoppelten P-Welle.
    b, a = butter(2, [FWAVE_LO_HZ / (FS / 2), FWAVE_HI_HZ / (FS / 2)], btype="band")
    fwave = filtfilt(b, a, rng.standard_normal(N))
    fwave = fwave / (np.std(fwave) or 1.0) * FWAVE_AMPL_MV
    sig = sig + fwave

    # Geraete-Polaritaetskonvention (siehe generate_test_edf_datei.py, identischer Grund):
    # POL X1 zeigt bei diesem Aufnahmesystem durchgehend negative R-Zacken im Rohsignal.
    sig = -sig
    sig_uv = sig * 1000.0
    return sig_uv, beat_times


def main():
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    out_path = os.path.join(here, "test_edf_afib.edf")
    manifest_path = os.path.join(here, "test_edf_afib_manifest.json")

    signals = [build_eeg_signal(ch, rng) for ch in EEG_CHANNELS]
    ecg_sig, beat_times = build_ecg_signal()
    signals.append(ecg_sig)

    n_ch = len(ALL_LABELS)
    signal_headers = []
    for label in ALL_LABELS:
        is_ecg = (label == "POL X1")
        pmax = 2000.0 if is_ecg else 500.0
        signal_headers.append({
            "label": label, "dimension": "uV", "sample_frequency": FS,
            "physical_max": pmax, "physical_min": -pmax,
            "digital_max": 32767, "digital_min": -32768,
            "transducer": "", "prefilter": "",
        })

    f = pyedflib.EdfWriter(out_path, n_ch, file_type=pyedflib.FILETYPE_EDFPLUS)
    f.setSignalHeaders(signal_headers)
    f.setPatientCode("SYNTH002")
    f.setPatientName("TestSyntheticAFib")
    f.setStartdatetime(datetime(2026, 1, 1, 12, 0, 0))
    f.setEquipment("synthetic-generator")
    f.writeSamples(signals)
    f.close()

    rr_ms = np.diff(beat_times) * 1000.0
    manifest = {
        "created": datetime.now().isoformat(),
        "purpose": "Synthetisches Ground-Truth-EDF #2 (Vorhofflimmern) — KEIN echter Patient. "
                   "Siehe Docstring in generate_test_edf_afib.py für die elektrophysiologische "
                   "Begründung der 4 modellierten AFib-Charakteristika.",
        "format": {"fs_hz": FS, "duration_s": DUR_S, "n_eeg_channels": len(EEG_CHANNELS),
                   "ecg_channel": "POL X1"},
        "afib_rhythm": {
            "model": "i.i.d. RR-Ziehung (KEINE RSA-Modulation, KEIN Trend) — absolute Arrhythmie",
            "mean_rr_ms": float(rr_ms.mean()), "rr_sd_ms": float(rr_ms.std()),
            "mean_hr_bpm": float(60000.0 / rr_ms.mean()), "n_beats": int(len(beat_times)),
            "expected_cosen": "~-0.43 (Literatur AFib-Median -0.5, Range -0.8 bis -0.3; "
                               "Referenzfall CA1772QO: -0.44) -> verdict sollte "
                               "'afib_verdaechtig' sein, in praktisch allen 30s-Fenstern.",
        },
        "p_wave": {
            "model": "Kontinuierliches 5-9Hz-Bandpass-Rauschen (~300-540/min, f-Wellen-Bereich "
                     "350-600/min), UNKORRELIERT zum R-Zacken-Timing -> mittelt sich in der "
                     "Ensemble-Bildung heraus",
            "amplitude_mv": FWAVE_AMPL_MV,
            "expected_coherence": "~0.10 (deutlich unter COH_UNCERTAIN=0.35) -> "
                                   "classify_p_wave sollte 'nicht_abgrenzbar' liefern, "
                                   "combine_with_pwave sollte die AFib-Confidence anheben.",
        },
        "qrs_morphology": "Identisches QRS-T-Template wie test_edf_datei.edf (Normal-Referenz) — "
                           "AFib veraendert die Kammererregung selbst nicht, nur Vorhofaktivitaet "
                           "und Ueberleitungs-Unregelmaessigkeit.",
        "eeg_note": "Identischer EEG-Hintergrund wie test_edf_datei.edf (Alpha 10Hz posterior-"
                    "dominant, Aperiodik-Exponent 2.2) — kein eigener EEG-Befund hier relevant, "
                    "dient nur der App-Kompatibilitaet als vollstaendiger 19-Kanal-Datensatz. "
                    "KEIN Artefakt-Burst in dieser Datei (Fokus liegt auf dem EKG).",
    }
    with open(manifest_path, "w", encoding="utf-8") as mf:
        json.dump(manifest, mf, indent=2, ensure_ascii=False)

    print(f"EDF geschrieben: {out_path}")
    print(f"Manifest geschrieben: {manifest_path}")
    print(f"Anzahl Herzschlaege: {len(beat_times)}, mittlere HF: {60000.0/rr_ms.mean():.1f} bpm")


if __name__ == "__main__":
    main()
