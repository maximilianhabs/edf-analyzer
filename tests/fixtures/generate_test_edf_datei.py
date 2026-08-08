"""
Synthetisches Ground-Truth-EDF für den EDF-Analyzer.

Erzeugt eine EDF+-Datei im NeuroFax-Stil (17 EEG-Kanäle 10-20 + POL X1 als EKG,
200 Hz, 10 Minuten) mit mathematisch konstruierten, bekannten Sollwerten für:
  - 1/f-Exponent (Aperiodik)
  - Alpha-Grundrhythmus (Frequenz, A/P-Gradient, L/R-Asymmetrie)
  - Band-Anteile (Delta/Theta/Beta)
  - Ein Artefakt-Burst (bekannte Amplitude/Zeitpunkt/Kanäle)
  - EKG: feste Grundfrequenz + sinusförmige RSA-Modulation + Ausreißer-Schläge

Kein Anspruch auf biologische Exaktheit — dient ausschließlich dazu, die
Analyse-Pipeline gegen bekannte Sollwerte zu prüfen (systematische Fehler finden).

Erzeugt `test_edf_datei.edf` + `test_edf_datei_manifest.json` in diesem Verzeichnis.
Gegen die App-Analysefunktionen verifiziert (2026-08-03): Aperiodik-Exponent, Alpha-Peak,
Asymmetrie-Index, A/P-Gradient, R-Zacken-Erkennung, HRV-Frequenzdomäne (RSA-Peak) —
alle Werte trafen die eingebetteten Sollwerte exakt oder sehr nah. Enthält KEINE
Patientendaten (rein mathematisch generiert) — daher bewusst NICHT von .gitignore
ausgeschlossen, siehe Ausnahme-Regel dort.
"""
import numpy as np
import pyedflib
import json
from datetime import datetime

rng = np.random.default_rng(42)

FS = 200.0
DUR_S = 600  # 10 Minuten
N = int(FS * DUR_S)
t = np.arange(N) / FS

EEG_CHANNELS = ["Fp1", "Fp2", "F7", "F3", "Fz", "F4", "F8",
                "T3", "C3", "Cz", "C4", "T4",
                "T5", "P3", "Pz", "P4", "T6", "O1", "O2"]
# (19 Kanäle — Standard 10-20 ohne A1/A2, deckt alle Montagen im Programm ab)

ALL_LABELS = EEG_CHANNELS + ["POL X1"]

# ── 1/f-Hintergrund: exakter Exponent über Frequenzbereich skaliert ──────────
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

APERIODIC_EXPONENT = 2.20  # Sollwert für ALLE Kanäle identisch

# ── Alpha-Amplituden pro Kanal: klarer A/P-Gradient + definierte L/R-Asymmetrie ──
ALPHA_FREQ_HZ = 10.0
# posterior stark, anterior schwach; O1 20% staerker als O2 (Soll-AI ~ +18%)
ALPHA_AMPLITUDE_UV = {
    "O1": 33.0, "O2": 27.5, "Pz": 24.0, "P3": 22.0, "P4": 21.0,
    "T5": 14.0, "T6": 13.0,
    "Cz": 10.0, "C3": 9.0, "C4": 9.0,
    "Fz": 6.0, "F3": 5.5, "F4": 5.0, "F7": 4.0, "F8": 4.0,
    "Fp1": 3.0, "Fp2": 3.0, "T3": 6.0, "T4": 6.0,
}

# Zusaetzliche feste Band-Beimischungen (alle Kanaele, klein & gleich) fuer Bandpower-Kontrolle
DELTA_FREQ_HZ, DELTA_AMPL_UV = 2.0, 8.0
THETA_FREQ_HZ, THETA_AMPL_UV = 6.0, 5.0
BETA_FREQ_HZ,  BETA_AMPL_UV  = 20.0, 3.0

# ── Artefakt-Burst: bekannte Amplitude/Zeitpunkt/Kanaele ─────────────────────
ARTIFACT_ONSET_S = 240.0
ARTIFACT_DUR_S   = 5.0
ARTIFACT_AMPL_UV = 300.0
ARTIFACT_CHANNELS = ["Fp1", "Fp2", "F7", "F8", "T3", "T4"]  # bewegungs-/EMG-artiger Burst

def build_eeg_signal(ch, rng):
    bg = make_1f_noise(N, FS, APERIODIC_EXPONENT, rng) * 4.0  # Grundrauschen ~4 uV RMS
    sig = bg.copy()
    amp = ALPHA_AMPLITUDE_UV.get(ch, 5.0)
    sig += amp * np.sin(2 * np.pi * ALPHA_FREQ_HZ * t + rng.uniform(0, 2 * np.pi))
    sig += DELTA_AMPL_UV * np.sin(2 * np.pi * DELTA_FREQ_HZ * t + rng.uniform(0, 2 * np.pi))
    sig += THETA_AMPL_UV * np.sin(2 * np.pi * THETA_FREQ_HZ * t + rng.uniform(0, 2 * np.pi))
    sig += BETA_AMPL_UV  * np.sin(2 * np.pi * BETA_FREQ_HZ  * t + rng.uniform(0, 2 * np.pi))
    if ch in ARTIFACT_CHANNELS:
        i0 = int(ARTIFACT_ONSET_S * FS)
        i1 = int((ARTIFACT_ONSET_S + ARTIFACT_DUR_S) * FS)
        burst_t = t[i0:i1] - t[i0]
        burst = ARTIFACT_AMPL_UV * np.sin(2 * np.pi * 3.0 * burst_t) * np.hanning(i1 - i0)
        sig[i0:i1] += burst
    return sig

# ── EKG: feste Grundfrequenz + sinusfoermige RSA-Modulation + Ausreisser ─────
HR_BASE_BPM = 70.0
RSA_FREQ_HZ = 0.25       # "Atemfrequenz" 15/min
RSA_AMPL_MS = 60.0       # RR schwankt +-60 ms um den Mittelwert
OUTLIER_BEAT_TIMES_S = [120.0, 300.0, 450.0]  # bekannte "Extrasystolen"-Zeitpunkte

def build_ecg_signal():
    mean_rr_s = 60.0 / HR_BASE_BPM
    beat_times = [0.30]
    while beat_times[-1] < DUR_S:
        prev = beat_times[-1]
        rsa_offset_s = (RSA_AMPL_MS / 1000.0) * np.sin(2 * np.pi * RSA_FREQ_HZ * prev)
        rr = mean_rr_s + rsa_offset_s
        beat_times.append(prev + rr)
    beat_times = np.array(beat_times[:-1])

    # Ausreisser: an definierten Zeitpunkten den naechsten Schlag um 300ms vorziehen
    for ot in OUTLIER_BEAT_TIMES_S:
        idx = int(np.argmin(np.abs(beat_times - ot)))
        beat_times[idx] -= 0.30

    sig = np.zeros(N)
    # Einfaches, aber klar erkennbares QRST-Template (keine biologische Exaktheit noetig)
    qrs_t = np.linspace(-0.06, 0.06, int(0.12 * FS))
    qrs_template = 1.2 * np.exp(-(qrs_t ** 2) / (2 * 0.008 ** 2))  # R-Zacke
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
        i_t = i_r + int(0.20 * FS)
        j0, j1 = i_t - half_t, i_t - half_t + len(t_wave)
        if 0 <= j0 and j1 <= N:
            sig[j0:j1] += t_wave
    sig_uv = sig * 1000.0  # mV-Groessenordnung -> "uV"-Feld (siehe Kommentar unten)

    # Amplituden-Artefakte (bewusst OHNE Flatline und OHNE Formveraenderung): reine
    # Skalierung im Zeitfenster. Pearson-Korrelation zum Template ist skaleninvariant,
    # d.h. Regel 4 (Template-Match) faengt das NICHT -> testet gezielt nur Regel 6
    # (Amplituden-Plausibilitaet je Schlag) in analysis/ecg_quality.py isoliert.
    WEAK_WINDOW = (330.0, 345.0)   # schwaches Signal / lockere Elektrode, Faktor 0.05
    HIGH_WINDOW = (400.0, 410.0)   # Bewegungsartefakt-Spitzen, Faktor 7.0
    i0, i1 = int(WEAK_WINDOW[0]*FS), int(WEAK_WINDOW[1]*FS)
    sig_uv[i0:i1] *= 0.05
    i0, i1 = int(HIGH_WINDOW[0]*FS), int(HIGH_WINDOW[1]*FS)
    sig_uv[i0:i1] *= 7.0

    return sig_uv, beat_times, WEAK_WINDOW, HIGH_WINDOW


def main():
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    out_path = os.path.join(here, "test_edf_datei.edf")
    manifest_path = os.path.join(here, "test_edf_datei_manifest.json")

    signals = []
    for ch in EEG_CHANNELS:
        signals.append(build_eeg_signal(ch, rng))
    ecg_sig, beat_times, weak_window, high_window = build_ecg_signal()
    signals.append(ecg_sig)

    n_ch = len(ALL_LABELS)
    signal_headers = []
    for i, label in enumerate(ALL_LABELS):
        is_ecg = (label == "POL X1")
        pmax = 2000.0 if is_ecg else 500.0
        signal_headers.append({
            "label": label,
            "dimension": "uV",
            "sample_frequency": FS,
            "physical_max": pmax,
            "physical_min": -pmax,
            "digital_max": 32767,
            "digital_min": -32768,
            "transducer": "",
            "prefilter": "",
        })

    f = pyedflib.EdfWriter(out_path, n_ch, file_type=pyedflib.FILETYPE_EDFPLUS)
    f.setSignalHeaders(signal_headers)
    f.setPatientCode("SYNTH001")
    f.setPatientName("TestSynthetic")
    f.setStartdatetime(datetime(2026, 1, 1, 12, 0, 0))
    f.setEquipment("synthetic-generator")
    f.writeSamples(signals)
    f.close()

    manifest = {
        "created": datetime.now().isoformat(),
        "purpose": "Synthetisches Ground-Truth-EDF zur Pipeline-Validierung — KEIN echter Patient, "
                   "keine biologische Exaktheit beansprucht.",
        "format": {"fs_hz": FS, "duration_s": DUR_S, "n_eeg_channels": len(EEG_CHANNELS),
                   "ecg_channel": "POL X1"},
        "aperiodic": {"exponent_all_channels": APERIODIC_EXPONENT,
                      "note": "1/f-Rauschen per FFT-Skalierung erzeugt — Soll-Exponent für JEDEN "
                              "EEG-Kanal identisch. App sollte in Aperiodik-Seite/FOOOF nahe "
                              f"{APERIODIC_EXPONENT} liegen (± Fit-Rauschen)."},
        "alpha": {"freq_hz": ALPHA_FREQ_HZ, "amplitude_uv_per_channel": ALPHA_AMPLITUDE_UV,
                  "expected_par": "posterior (O1/O2/Pz) >> anterior (Fp1/Fp2/F3/F4) -> PAR deutlich > 1",
                  "expected_asymmetry_o1_o2": "O1 20% staerker als O2 (33.0 vs 27.5 uV Amplitude) "
                                              "-> Alpha-AI ~ +18% (Power-Verhaeltnis, nicht Amplitude-Verhaeltnis "
                                              "-> tatsaechlicher Power-AI hoeher, da AI auf Power=Amplitude^2 wirkt; "
                                              "exakten Wert aus der App-Berechnung gegenchecken)"},
        "bands": {"delta_hz": DELTA_FREQ_HZ, "theta_hz": THETA_FREQ_HZ, "beta_hz": BETA_FREQ_HZ,
                  "note": "Kleine, gleich große Beimischung auf allen Kanälen — Bandpower sollte "
                          "diese Peaks in Delta/Theta/Beta zeigen, unabhängig von Kanal."},
        "artifact_burst": {"onset_s": ARTIFACT_ONSET_S, "duration_s": ARTIFACT_DUR_S,
                            "amplitude_uv": ARTIFACT_AMPL_UV, "channels": ARTIFACT_CHANNELS,
                            "note": "Sollte vom Artefaktdetektor als Multikanal-Konsens-Ereignis "
                                    "bei 240-245s erkannt werden (deutlich über Default-Schwellen)."},
        "ecg": {"mean_hr_bpm": HR_BASE_BPM, "rsa_freq_hz": RSA_FREQ_HZ, "rsa_amplitude_ms": RSA_AMPL_MS,
                "n_beats": len(beat_times),
                "outlier_beat_times_s_approx": OUTLIER_BEAT_TIMES_S,
                "expected_hf_peak_hz": RSA_FREQ_HZ,
                "note": "HRV-Frequenzdomäne (Welch/Burg/Lomb-Scargle) sollte einen HF-Peak sehr "
                        "nahe an genau diesem RSA-Wert zeigen. Die 3 Ausreißer-Zeitpunkte sollten "
                        "von der RR-Bereinigung (Hampel/Median-Filter) entfernt werden, ohne "
                        "echte Nachbarschläge zu verlieren."},
        "ecg_amplitude_artifacts": {
            "weak_signal_window_s": list(weak_window), "weak_signal_factor": 0.05,
            "high_amplitude_window_s": list(high_window), "high_amplitude_factor": 7.0,
            "note": "Reine Amplituden-Skalierung, KEINE Formveränderung, KEINE Flatline -> "
                    "Pearson-Korrelation zum QRS-Template ist skaleninvariant und bleibt hoch. "
                    "Testet gezielt Regel 6 (Amplituden-Plausibilität) in "
                    "analysis/ecg_quality.py isoliert von Regel 4/5."
        },
    }
    with open(manifest_path, "w", encoding="utf-8") as mf:
        json.dump(manifest, mf, indent=2, ensure_ascii=False)

    print(f"EDF geschrieben: {out_path}")
    print(f"Manifest geschrieben: {manifest_path}")
    print(f"Kanäle: {ALL_LABELS}")
    print(f"Anzahl Herzschläge: {len(beat_times)}")


if __name__ == "__main__":
    main()
