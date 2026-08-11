"""Tests für analysis/artifacts.py — Zeit-Achse (Segmente) + Kanal-Achse (Bad-Channel).

Synthetische Signale mit bekanntem Soll-Verhalten + Sanity-Check an einer echten EDF.
Ausführen: ~/mne-env/bin/python -m pytest tests/test_artifacts.py -v
(oder direkt: ~/mne-env/bin/python tests/test_artifacts.py)
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from analysis.artifacts import (
    ArtifactParams, compute_artifact_mask, mask_from_edf,
)

FS = 200.0
RNG = np.random.default_rng(42)


def _clean_eeg(nch=19, secs=120, amp_uv=20.0):
    """Ruhiges Mehrkanal-EEG: gefiltertes weißes Rauschen, moderate Amplitude."""
    n = int(secs * FS)
    return RNG.normal(0, amp_uv, size=(nch, n))


def test_clean_recording_keeps_everything():
    eeg = _clean_eeg()
    res = compute_artifact_mask(eeg, FS)
    assert res.clean_frac > 0.98, f"Sauberes EEG darf kaum verworfen werden: {res.clean_frac}"
    assert len(res.segments) == 0
    assert res.bad_channels == []


def test_multichannel_burst_is_flagged():
    """Kurzer Ausschlag in vielen Kanälen gleichzeitig → ein Artefakt-Segment."""
    eeg = _clean_eeg(secs=60)
    t0 = int(30 * FS)
    burst = slice(t0, t0 + int(1.0 * FS))
    eeg[:12, burst] += RNG.normal(0, 300, size=(12, burst.stop - burst.start))  # 12/19 Kanäle
    res = compute_artifact_mask(eeg, FS)
    assert len(res.segments) >= 1
    covered = any(s["start_s"] <= 30.0 <= s["end_s"] for s in res.segments)
    assert covered, "Der Multikanal-Burst bei t=30 s muss in einem Segment liegen"
    assert res.clean_frac > 0.9, "Nur der Burst (~1 s) darf raus, nicht mehr"


def test_single_channel_spike_does_not_reject_epoch():
    """Einzelkanal-Ausschlag (lokal) → KEIN Zeit-Segment (Konsens nicht erreicht)."""
    eeg = _clean_eeg(secs=60)
    t0 = int(30 * FS)
    eeg[3, t0:t0 + int(1.0 * FS)] += RNG.normal(0, 400, size=int(1.0 * FS))  # nur 1 Kanal
    res = compute_artifact_mask(eeg, FS)
    assert len(res.segments) == 0, "Einzelkanal-Spike darf die Epoche nicht verwerfen"


def test_high_amplitude_but_uniform_not_over_rejected():
    """Hochamplitudiges, gleichmäßiges EEG (SWS-artig) → nicht als Artefakt verworfen.

    Baseline ist relativ zum Kanal selbst — flächige, dauerhafte hohe Amplitude hebt die
    Baseline mit an, sodass keine extremen Ratios entstehen."""
    n = int(120 * FS)
    t = np.arange(n) / FS
    sws = np.array([80.0 * np.sin(2 * np.pi * 1.5 * t + ph)
                    for ph in RNG.uniform(0, 2 * np.pi, 19)])
    sws += RNG.normal(0, 10, size=sws.shape)
    res = compute_artifact_mask(sws, FS)
    assert res.clean_frac > 0.95, f"SWS-artiges EEG darf nicht verworfen werden: {res.clean_frac}"


def test_bad_channel_persistent_is_suggested():
    """Ein Kanal ab Minute 2 dauerhaft stark verrauscht → Bad-Channel-Vorschlag ab ~120 s."""
    eeg = _clean_eeg(nch=19, secs=300)
    onset = int(120 * FS)
    eeg[5, onset:] += RNG.normal(0, 250, size=eeg.shape[1] - onset)  # C-artiger Kanal 5
    res = compute_artifact_mask(eeg, FS)
    bad = {b["index"]: b for b in res.bad_channels}
    assert 5 in bad, f"Kanal 5 sollte als Bad-Channel vorgeschlagen werden, war: {res.bad_channels}"
    assert 90 <= bad[5]["since_s"] <= 150, f"Onset ~120 s erwartet, war {bad[5]['since_s']}"
    # Andere Kanäle dürfen NICHT fälschlich vorgeschlagen werden
    assert all(b["index"] == 5 for b in res.bad_channels)


_NAMES19 = ["Fp1", "Fp2", "F7", "F8", "F3", "F4", "Fz", "C3", "C4", "Cz",
            "P3", "P4", "Pz", "O1", "O2", "T3", "T4", "T5", "T6"]


def test_frontal_only_burst_not_flagged():
    """Blinzel-/EOG-artiger Ausschlag NUR in frontalen Kanälen → KEIN Artefakt-Segment.

    Regions-Toleranz (Fp 2,0 / F7F8 1,4) + räumlicher Schutz (braucht nicht-frontale Kanäle)."""
    eeg = _clean_eeg(nch=19, secs=60)
    t0 = int(30 * FS)
    b = slice(t0, t0 + int(1.0 * FS))
    frontal = [0, 1, 2, 3]  # Fp1, Fp2, F7, F8
    eeg[frontal, b] += RNG.normal(0, 250, size=(len(frontal), b.stop - b.start))
    res = compute_artifact_mask(eeg, FS, ch_names=_NAMES19)
    assert len(res.segments) == 0, \
        f"Rein frontaler (Blinzel-)Burst darf nicht als Bewegung geflaggt werden: {res.segments}"


def test_global_burst_still_flagged_with_regions():
    """Derselbe Ausschlag global (auch posterior) → weiterhin erkannt trotz Regions-Toleranz."""
    eeg = _clean_eeg(nch=19, secs=60)
    t0 = int(30 * FS)
    b = slice(t0, t0 + int(1.0 * FS))
    glob = [0, 1, 7, 8, 10, 11, 13, 14]  # Fp1,Fp2,C3,C4,P3,P4,O1,O2
    eeg[glob, b] += RNG.normal(0, 300, size=(len(glob), b.stop - b.start))
    res = compute_artifact_mask(eeg, FS, ch_names=_NAMES19)
    assert any(s["start_s"] <= 30.0 <= s["end_s"] for s in res.segments), \
        "Globale Bewegung (mit posteriorer Beteiligung) muss weiter erkannt werden"


def test_ecg_disturbance_is_confirmatory_not_gate():
    """EKG-Störung markiert Segmente als bestätigt, ist aber kein Muss fürs Flaggen."""
    eeg = _clean_eeg(secs=60)
    t0 = int(30 * FS)
    b = slice(t0, t0 + int(1.0 * FS))
    eeg[:12, b] += RNG.normal(0, 300, size=(12, b.stop - b.start))
    ecg = RNG.normal(0, 1.0, size=eeg.shape[1])
    ecg[b] += RNG.normal(0, 8.0, size=b.stop - b.start)   # EKG im selben Fenster gestört
    res = compute_artifact_mask(eeg, FS, ecg_uv=ecg)
    assert len(res.segments) >= 1
    assert any(s["ecg_disturbed"] for s in res.segments), "EKG-Störung sollte bestätigt werden"

    # Ohne EKG-Störung: Segment trotzdem geflaggt (EKG ist kein Gate)
    res2 = compute_artifact_mask(eeg, FS, ecg_uv=RNG.normal(0, 1.0, size=eeg.shape[1]))
    assert len(res2.segments) >= 1
    assert all(s["ecg_disturbed"] is False for s in res2.segments)


# ── Sanity-Check an einer echten EDF (optional, nur lokal) ───────────────────
# Pfad kommt über die Umgebungsvariable, NICHT fest im Code: vorher stand hier ein fester
# Pfad auf eine echte Aufnahme samt ihrer Fallnummer — in einem öffentlichen Repo unnötig,
# und für alle ausser dem Autor war der Test ohnehin nicht lauffähig.
#
#     EDF_TEST_FILE=~/Downloads/meine.edf pytest tests/
#
# Ohne gesetzte Variable wird der Test übersprungen; die Aussagekraft der Suite hängt nicht
# daran (die synthetischen Fixtures decken die Kette ab, siehe test_ecg_pipeline.py).
_REAL = os.path.expanduser(os.environ.get("EDF_TEST_FILE", ""))


def test_real_edf_conservative():
    if not _REAL or not os.path.exists(_REAL):
        import pytest
        pytest.skip("EDF_TEST_FILE nicht gesetzt oder Datei nicht vorhanden")
    import mne
    raw = mne.io.read_raw_edf(_REAL, preload=True, encoding="latin1", verbose="ERROR")
    eeg_names = [c for c in raw.ch_names if c.startswith("EEG") and "-Ref" in c
                 and "A1" not in c and "A2" not in c]
    eeg_uv = raw.get_data(picks=eeg_names) * 1e6
    ecg = raw.get_data(picks=["POL X1"])[0]
    res = compute_artifact_mask(eeg_uv, raw.info["sfreq"], ecg_uv=ecg, ch_names=eeg_names)
    print(f"Referenzfall D: behalte {res.clean_frac*100:.0f}%, {len(res.segments)} Segmente, "
          f"Bad-Channels={[b['name'] for b in res.bad_channels]}")
    assert 0.90 < res.clean_frac < 1.0, "Mildes Routine-EEG: Großteil erhalten, aber Detektor aktiv"
    # Regionsbewusst: die klar globale Bewegung ~9:23 (563 s) wird erkannt; das temporal-
    # dominierte 10:32 wird durch die F7/F8/T-Toleranz bewusst geschont (kein hartes Muss).
    assert any(s["start_s"] <= 565 <= s["end_s"] for s in res.segments), \
        "Bewegung ~9:23 (posterior beteiligt) sollte erkannt werden"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        try:
            fn()
            print(f"  ✓ {fn.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  ✗ {fn.__name__}: {e}")
        except Exception as e:
            print(f"  ! {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(fns)} Tests bestanden")
