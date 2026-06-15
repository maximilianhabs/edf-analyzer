"""Smoke test: ECG pipeline on real EDF file."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.loader import load_edf, check_privacy, get_channel_groups, extract_channel, get_annotations
from analysis.ecg import run_ecg_analysis

EDF_PATH = os.path.expanduser("~/Downloads/CA177317.edf")


def test_privacy_check():
    result = check_privacy(EDF_PATH)
    print(f"Patient data in header: {result}")
    assert isinstance(result["has_patient_id"], bool)


def test_load_channels():
    raw = load_edf(EDF_PATH, preload=False)
    groups = get_channel_groups(raw)
    print(f"EEG channels: {len(groups['eeg'])}")
    print(f"ECG channels: {groups['ecg']}")
    print(f"Vital channels: {groups['vitals']}")
    assert len(groups["ecg"]) == 2
    assert len(groups["eeg"]) == 19


def test_annotations():
    raw = load_edf(EDF_PATH, preload=False)
    events = get_annotations(raw)
    print(f"Clinical annotations: {len(events)}")
    for e in events[:5]:
        print(f"  {e}")
    assert len(events) > 0


def test_ecg_analysis():
    raw = load_edf(EDF_PATH, preload=True)
    signal, sfreq = extract_channel(raw, "POL $A1")
    print(f"ECG signal: {len(signal)} samples at {sfreq} Hz = {len(signal)/sfreq/60:.1f} min")
    print(f"Raw amplitude range: {signal.min()*1000:.1f} – {signal.max()*1000:.1f} mV")

    result = run_ecg_analysis(signal, sfreq)
    print(f"\nR-Peaks detected: {len(result['r_peaks'])}")
    print(f"RR intervals: {len(result['rr_ms'])} valid beats")
    print(f"\nHRV Time Domain:")
    for k, v in result["hrv_time"].items():
        print(f"  {k}: {v}")
    print(f"\nHRV Frequency Domain:")
    for k, v in result["hrv_freq"].items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    print("=== Privacy Check ===")
    test_privacy_check()
    print("\n=== Channel Groups ===")
    test_load_channels()
    print("\n=== Annotations ===")
    test_annotations()
    print("\n=== ECG Analysis ===")
    test_ecg_analysis()
    print("\n✓ All tests passed")
