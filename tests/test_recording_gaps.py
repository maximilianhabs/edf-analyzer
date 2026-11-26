"""Aufnahmelücken aus Annotationen (Nihon Kohden "Recording Gap HHHH:MM:SS") und die
Raten-Plausibilität Klassifizierer vs. Detektor.

Alles synthetisch bzw. aus der vorhandenen synthetischen Fixture — keine Patientendatei.
"""
import os
import sys
import warnings

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
warnings.filterwarnings("ignore")

from core.edf_validation import recording_gaps  # noqa: E402


def test_dauer_wird_geparst():
    res = recording_gaps([{"onset_s": 140.08, "description": "Recording Gap 0000:00:20"}])
    assert res == [{"onset_s": 140.08, "gap_s": 20.0,
                    "description": "Recording Gap 0000:00:20"}]


def test_stunden_minuten_sekunden():
    res = recording_gaps([{"onset_s": 1.0, "description": "Recording Gap 0001:02:03"}])
    assert res[0]["gap_s"] == 3600 + 120 + 3


def test_nicht_parsebare_dauer_wird_trotzdem_gemeldet():
    res = recording_gaps([{"onset_s": 5.0, "description": "Recording Gap ???"},
                          {"onset_s": 9.0, "description": "recording gap"}])
    assert [g["gap_s"] for g in res] == [None, None]
    assert [g["onset_s"] for g in res] == [5.0, 9.0]


def test_keine_luecke_vorhanden():
    anns = [{"onset_s": 10.0, "description": "Eyes closed"},
            {"onset_s": 20.0, "description": "Photic 10 Hz"}]
    assert recording_gaps(anns) == []
    assert recording_gaps([]) == []


def test_mehrere_luecken_in_eingabereihenfolge():
    anns = [{"onset_s": 140.08, "description": "Recording Gap 0000:00:20"},
            {"onset_s": 200.0, "description": "Eyes open"},
            {"onset_s": 253.0, "description": "Recording Gap 0000:00:12"}]
    res = recording_gaps(anns)
    assert [(g["onset_s"], g["gap_s"]) for g in res] == [(140.08, 20.0), (253.0, 12.0)]


def test_defekte_eintraege_stuerzen_nicht_ab():
    anns = [{"description": "Recording Gap 0000:00:20"}, {"onset_s": "x", "description": "Recording Gap"},
            None, {"onset_s": 3.0, "description": "Recording Gap 0000:00:05"}]
    assert [g["onset_s"] for g in recording_gaps(anns)] == [3.0]


def test_fixture_ohne_luecken_annotation():
    from core.loader import load_edf, get_annotations
    fx = os.path.join(os.path.dirname(__file__), "fixtures", "test_edf_datei.edf")
    assert recording_gaps(get_annotations(load_edf(fx, preload=False))) == []


# ── Raten-Plausibilität ──────────────────────────────────────────────────────────────────

def test_detektorrate_regelmaessig():
    from analysis.ecg import detector_rate_bpm
    assert abs(detector_rate_bpm(np.full(100, 800.0)) - 75.0) < 1e-6


def test_detektorrate_naht_stoert_nicht():
    from analysis.ecg import detector_rate_bpm
    rr = np.full(100, 800.0)
    rr[50] = 2300.0
    assert abs(detector_rate_bpm(rr) - 75.0) < 1e-6


def test_detektorrate_doppelzaehlung_gibt_doppelte_rate():
    from analysis.ecg import detector_rate_bpm
    rr = np.tile([300.0, 500.0], 50)   # Schlag + T-Welle -> 75/min wird zu 150/min
    assert abs(detector_rate_bpm(rr) - 150.0) < 1e-6


def test_detektorrate_zu_wenig_daten():
    from analysis.ecg import detector_rate_bpm
    assert detector_rate_bpm([800.0, 800.0]) == 0.0


def test_rate_mismatch_schwelle():
    from analysis.ecg import rate_mismatch
    assert rate_mismatch(136.0, 92.0)          # realer Fall: +48 %
    assert not rate_mismatch(74.0, 92.0)       # -20 %
    assert not rate_mismatch(115.0, 92.0)      # +25 % ist noch kein Befund (> 25 %)
    assert not rate_mismatch(0.0, 92.0)        # fehlende Rate -> kein Hinweis
    assert not rate_mismatch(80.0, 0.0)
