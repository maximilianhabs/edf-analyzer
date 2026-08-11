"""Pipeline-Test gegen die SYNTHETISCHE Ground-Truth-Datei.

Vorher hing dieser Test an einem festen Pfad auf eine echte Patientenaufnahme, die nur auf
dem Rechner des Autors liegt. Für alle anderen war er nicht lauffähig, und die Fallnummer
stand im Repository. Ausserdem war eine Erwartung veraltet (2 EKG-Kanäle, der
nachgeschärfte Klassifizierer findet 1) — unbemerkt, weil die Tests nie automatisch liefen.

Jetzt gegen `tests/fixtures/test_edf_datei.edf`: rein mathematisch erzeugt, keine
Patientendaten, im Repo versioniert. Die Sollwerte stehen im zugehörigen Manifest — die
Erwartungen hier sind also belegt und nicht geraten.

Geprüft wird bewusst der Pfad, den die App WIRKLICH nutzt (`load_and_prepare` mit dem
signalbasierten Klassifizierer), nicht der namensbasierte Alt-Helfer `get_channel_groups()`:
der erkennt EEG am Präfix „EEG …-Ref" des Aufnahmesystems und findet in einer Datei mit
schlichten Elektrodennamen (Fp1, F3, …) folgerichtig nichts.
"""
import json
import os
import sys
import warnings

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
warnings.filterwarnings("ignore")

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "test_edf_datei.edf")
MANIFEST = os.path.join(os.path.dirname(__file__), "fixtures", "test_edf_datei_manifest.json")


def _manifest():
    with open(MANIFEST, encoding="utf-8") as fh:
        return json.load(fh)


def test_fixture_vorhanden():
    """Ohne die Fixture ist alles Weitere sinnlos — dann lieber hier klar scheitern."""
    assert os.path.exists(FIXTURE), f"Fixture fehlt: {FIXTURE}"
    assert os.path.exists(MANIFEST), f"Manifest fehlt: {MANIFEST}"


def test_fixture_enthaelt_keine_patientendaten():
    """Die Fixture liegt öffentlich im Repo — sie darf keine echten Kopfdaten tragen."""
    from core.loader import check_privacy
    with open(FIXTURE, "rb") as fh:
        header = fh.read(256)
    patient = header[8:88].decode("latin1").strip()
    assert "SYNTH" in patient.upper() or "TEST" in patient.upper(), \
        f"Patientenfeld sieht nicht synthetisch aus: {patient!r}"
    assert isinstance(check_privacy(FIXTURE)["has_patient_id"], bool)


def test_format_und_kanalerkennung():
    from core.shared import load_and_prepare
    edf = load_and_prepare(FIXTURE)
    m = _manifest()["format"]
    assert edf["sfreq"] == m["fs_hz"]
    assert abs(edf["duration_s"] - m["duration_s"]) < 1.0
    # Signalbasierter Klassifizierer: findet alle 19 EEG-Kanäle trotz herstellerfremder Namen
    assert len(edf["eeg_map"]) == m["n_eeg_channels"], \
        f"erwartet {m['n_eeg_channels']} EEG-Kanäle, erkannt {len(edf['eeg_map'])}"
    assert edf["ecg_channels"] == [m["ecg_channel"]]


def test_ekg_kennwerte_treffen_die_sollwerte():
    """HR und HF-Peak sind im Manifest exakt festgelegt — hier wird die ganze Kette geprüft:
    Polaritätskorrektur → R-Zacken → RR-Serie → Zeit-/Frequenzbereich."""
    from core.shared import load_and_prepare
    from analysis.ecg import (detect_r_peaks_polarity_safe, build_rr_series,
                              compute_hrv_time_domain)
    from analysis.hrv_freq import compute_frequency_domain

    m = _manifest()["ecg"]
    edf = load_and_prepare(FIXTURE)
    sig = edf["data"][edf["ch_idx"][_manifest()["format"]["ecg_channel"]]].astype(float)
    _, peaks, _ = detect_r_peaks_polarity_safe(sig, edf["sfreq"])

    # Toleranz statt exakter Zahl mit Grund: die Datei enthält ABSICHTLICH ein
    # Schwachsignal-Fenster (330–345 s, 5 % Amplitude). Dass dort einzelne Schläge nicht
    # erkannt werden, ist gewolltes Verhalten — 685 von 702 gemessen (2,4 % Ausfall).
    assert 0.93 * m["n_beats"] <= len(peaks) <= 1.02 * m["n_beats"], \
        f"R-Zacken {len(peaks)}, erwartet ~{m['n_beats']}"

    rr = build_rr_series(peaks, edf["sfreq"])
    clean = rr.rr_ms[~rr.artifact_mask]
    td = compute_hrv_time_domain(clean)
    assert abs(td["mean_hr_bpm"] - m["mean_hr_bpm"]) < 2.0, \
        f"HR {td['mean_hr_bpm']:.1f}, erwartet {m['mean_hr_bpm']}"

    fd = compute_frequency_domain(clean, rr.rr_times_s[~rr.artifact_mask], method="welch")
    assert abs(fd["hf_peak_freq"] - m["expected_hf_peak_hz"]) < 0.02, \
        f"HF-Peak {fd['hf_peak_freq']:.3f} Hz, erwartet {m['expected_hf_peak_hz']}"


def test_afib_fixture_laedt():
    """Die zweite Fixture deckt den unregelmässigen Rhythmus ab."""
    from core.shared import load_and_prepare
    afib = os.path.join(os.path.dirname(__file__), "fixtures", "test_edf_afib.edf")
    if not os.path.exists(afib):
        import pytest
        pytest.skip("AFib-Fixture nicht vorhanden")
    edf = load_and_prepare(afib)
    assert edf["ecg_channels"], "kein EKG-Kanal in der AFib-Fixture erkannt"
