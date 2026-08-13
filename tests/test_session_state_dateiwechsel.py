"""Beim Dateiwechsel darf kein Ergebnis der vorherigen Aufnahme überleben.

Hintergrund (User-Fund 2026-08-13): Der Report zeigte Werte einer früher geladenen Datei
unter dem Namen der aktuellen. Ursache war Session-State, der als Cache benutzt wurde, ohne
die Datei zu kennen, zu der er gehört — und der an keiner Ladestelle verworfen wurde.

Diese Fehlerklasse ist die gefährlichste des Projekts: nichts stürzt ab, alle Zahlen sehen
plausibel aus, und der Report trägt sogar den korrekten Dateinamen samt Prüfsumme. Genau
deshalb steht der Test hier und nicht als Sichtprüfung im Handbuch.
"""
import sys, types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def shared(monkeypatch):
    """core.shared mit einem Session-State-Doppel — ohne laufenden Streamlit-Server."""
    import streamlit as st
    zustand = {}

    class Doppel(dict):
        def __getattr__(self, k):
            try:
                return self[k]
            except KeyError as e:
                raise AttributeError(k) from e
        def __setattr__(self, k, v):
            self[k] = v

    monkeypatch.setattr(st, "session_state", Doppel(zustand), raising=False)
    import core.shared as sh
    return sh, st.session_state


def test_ergebnisse_der_vorherigen_datei_werden_verworfen(shared):
    sh, state = shared
    state["edf_path"] = "/tmp/aufnahme_A.edf"
    assert sh.get_edf_path() == "/tmp/aufnahme_A.edf"

    # Zustand, wie ihn eine Auswertung von Datei A hinterlässt
    state["hrv_summary_report"] = {"mean_hr": 62.0}
    state["hrv_summary"] = {"sdnn": 41.0}
    state["eeg_summary"] = {"dominant": 9.5}
    state["_edf_cache_meta"] = {"duration_s": 1200}
    state["hrv_export"] = {"pdf": b"REPORT-A"}
    state["report_export"] = (b"PDF-A", b"XLSX-A", b"MANIFEST-A")
    state["channel_overrides"] = {"POL X1": "ECG"}
    state["patient_age"] = 81
    state["ep_ecg"] = 47

    # Datei B wird aktiv
    state["edf_path"] = "/tmp/aufnahme_B.edf"
    sh.get_edf_path()

    for schluessel in ("hrv_summary_report", "hrv_summary", "eeg_summary", "_edf_cache_meta",
                       "hrv_export", "report_export", "channel_overrides",
                       "patient_age", "ep_ecg"):
        assert schluessel not in state, (
            f"{schluessel!r} hat den Dateiwechsel überlebt — der Report zeigt Werte von "
            f"Aufnahme A unter dem Namen von Aufnahme B")

    # Und das Alter fällt auf die EINE Vorbelegung zurück, nicht auf die 81 des Vorpatienten
    assert sh.get_patient_info()[0] == sh.STANDARD_ALTER


def test_einstellungen_ueberleben_den_wechsel(shared):
    """Die Gegenprobe. Ein Wächter, der ALLES löscht, wäre genauso falsch: Artefakt-Parameter
    und Fensterwahl beschreiben, WIE gerechnet wird, und gelten weiter. Sie hängen zudem an
    Widgets — sie zu entfernen quittiert Streamlit mit einem Fehler."""
    sh, state = shared
    state["edf_path"] = "/tmp/A.edf"; sh.get_edf_path()
    state["art_consensus"] = 3
    state["hrv_window_choice"] = "5 min"
    state["spec_heavy"] = True
    state["lang"] = "en"

    state["edf_path"] = "/tmp/B.edf"; sh.get_edf_path()

    assert state["art_consensus"] == 3
    assert state["hrv_window_choice"] == "5 min"
    assert state["spec_heavy"] is True
    assert state["lang"] == "en"


def test_gleicher_pfad_verwirft_nichts(shared):
    """Sonst würde jeder Seitenwechsel alles neu rechnen — der Cache wäre wirkungslos."""
    sh, state = shared
    state["edf_path"] = "/tmp/A.edf"; sh.get_edf_path()
    state["hrv_summary"] = {"sdnn": 41.0}

    for _ in range(5):
        assert sh.invalidate_file_state("/tmp/A.edf") == 0
    assert state["hrv_summary"] == {"sdnn": 41.0}


def test_datei_entfernen_verwirft_ebenfalls(shared):
    """„Datei entfernen" setzt den Pfad auf leer. Auch dann darf nichts stehen bleiben —
    sonst erbt die nächste Aufnahme die Werte über den Umweg des leeren Zustands."""
    sh, state = shared
    state["edf_path"] = "/tmp/A.edf"; sh.get_edf_path()
    state["hrv_summary"] = {"sdnn": 41.0}
    state["patient_age"] = 81

    state["edf_path"] = ""; sh.get_edf_path()
    assert "hrv_summary" not in state and "patient_age" not in state


def test_alle_abgeleiteten_keys_werden_auch_wirklich_gelistet(shared):
    """Ratsche: Die Liste muss zu dem passen, was der Wächter tut. Ein Schlüssel, der in
    ABGELEITETE_KEYS steht, aber nicht verworfen wird, wäre eine stille Lücke."""
    sh, state = shared
    state["edf_path"] = "/tmp/A.edf"; sh.get_edf_path()
    for k in sh.ABGELEITETE_KEYS:
        state[k] = "belegt"
    n = sh.invalidate_file_state("/tmp/B.edf")
    assert n == len(sh.ABGELEITETE_KEYS)
    assert not [k for k in sh.ABGELEITETE_KEYS if k in state]
