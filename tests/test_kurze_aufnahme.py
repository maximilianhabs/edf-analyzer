"""Sehr kurze Aufnahmen dürfen keine Seite abbrechen lassen.

Anlass (User-Fund 2026-09-29): Eine kurze EDF-Datei brach die Seite „EKG & HRV" mit
`TypeError: 'NoneType' object is not subscriptable` ab. Unter 20 RR-Intervallen liefert
`compute_frequency_domain` bewusst None — eine HRV-Frequenzanalyse braucht Minuten, nicht
Sekunden. Der Code dokumentierte selbst, dass das „überall abgefangen werden" muss; die
Tabelle für den Excel-Export griff trotzdem blind auf `fd["lf_power"]` zu.

Der Test schneidet die synthetische Fixture auf 12 Sekunden (rund 14 Schläge) und rendert die
Seite vollständig. Ohne den Fix schlägt er mit genau der gemeldeten Fehlermeldung fehl
(geprüft).
"""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "test_edf_datei.edf"


@pytest.fixture
def kurze_edf(tmp_path):
    pyedflib = pytest.importorskip("pyedflib")
    r = pyedflib.EdfReader(str(FIXTURE))
    try:
        n = r.signals_in_file
        headers = r.getSignalHeaders()
        samples = int(12 * r.getSampleFrequency(0))
        daten = [r.readSignal(i)[:samples] for i in range(n)]
    finally:
        r.close()
    ziel = tmp_path / "kurz.edf"
    w = pyedflib.EdfWriter(str(ziel), n, file_type=pyedflib.FILETYPE_EDFPLUS)
    try:
        w.setSignalHeaders(headers)
        w.writeSamples(daten)
    finally:
        w.close()
    return ziel


def _seite():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path.cwd()))
    from views import ecg_hrv
    ecg_hrv.render()


def test_ekg_hrv_seite_bricht_bei_kurzer_aufnahme_nicht_ab(kurze_edf, monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("EDF_PASSWORD", "test")
    monkeypatch.chdir(ROOT)
    sys.path.insert(0, str(ROOT))

    at = AppTest.from_function(_seite, default_timeout=300)
    at.session_state["edf_path"] = str(kurze_edf)
    at.session_state["edf_display_name"] = "kurz.edf"
    at.session_state["phi_validated"] = True
    at.run()

    fehler = [str(e.value) for e in at.exception]
    assert not fehler, f"Seite EKG & HRV bricht bei 12-s-Aufnahme ab: {fehler}"
