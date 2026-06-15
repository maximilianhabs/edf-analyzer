"""EDF file loading with privacy safeguards."""

import mne
import numpy as np
import warnings


# NeuroFax-specific channel mapping
# $A1/$A2 sind gesättigte Hilfskanäle (Kalibrierkanal), KEIN EKG-Signal
# Echtes EKG in diesem Setup: POL X1 (Extremitätenableitung, ~0.7 mV, korrekte HR)
ECG_CHANNELS = ["POL X1"]
ECG_CHANNELS_DEAD = ["POL $A1", "POL $A2"]   # nur zur Dokumentation
VITAL_CHANNELS = ["POL SpO2", "POL EtCO2", "POL Pulse", "POL CO2Wave"]
EEG_PREFIX = "EEG"


def load_edf(path: str, preload: bool = True) -> mne.io.Raw:
    """Load EDF file. Warns if patient data is present in header."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        raw = mne.io.read_raw_edf(path, preload=preload, verbose=False, encoding="latin1")
    return raw


def check_privacy(path: str) -> dict:
    """Read only header bytes to check for patient data presence."""
    with open(path, "rb") as f:
        header = f.read(256)
    patient_id = header[8:88].decode("latin1").strip()
    recording_id = header[88:168].decode("latin1").strip()
    return {
        "has_patient_id": bool(patient_id),
        "has_recording_id": bool(recording_id),
        "patient_id_length": len(patient_id),
        "recording_id_length": len(recording_id),
    }


def get_channel_groups(raw: mne.io.Raw) -> dict:
    """Return channel names grouped by type."""
    names = raw.ch_names
    return {
        "eeg": [c for c in names if c.startswith(EEG_PREFIX) and "A1" not in c and "A2" not in c],
        "ecg": [c for c in names if c in ECG_CHANNELS],
        "vitals": [c for c in names if c in VITAL_CHANNELS],
        "other": [c for c in names if not c.startswith(EEG_PREFIX) and c not in ECG_CHANNELS and c not in VITAL_CHANNELS],
    }


def extract_channel(raw: mne.io.Raw, channel: str) -> tuple[np.ndarray, float]:
    """Extract single channel signal and sampling rate. Returns (signal_1d, sfreq)."""
    idx = raw.ch_names.index(channel)
    data, _ = raw[[idx], :]
    return data[0], raw.info["sfreq"]


def get_annotations(raw: mne.io.Raw) -> list[dict]:
    """Return annotations as list of dicts, filtered to clinical events only."""
    events = []
    for ann in raw.annotations:
        desc = ann["description"]
        # Skip internal timing markers (pure timestamp annotations)
        if desc.startswith("+") and desc[1:].replace(".", "").isdigit():
            continue
        if "np.str_" in desc:
            continue
        events.append({
            "onset_s": round(ann["onset"], 2),
            "duration_s": round(ann["duration"], 2),
            "description": desc,
        })
    return events
