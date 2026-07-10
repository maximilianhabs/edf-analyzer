"""Garantierter Hintergrund-Cleanup hochgeladener EDF-Dateien.

Anforderung: KEINE hochgeladene EDF-Datei darf länger als die TTL auf dem Server liegen —
unabhängig davon, ob neue Sessions gestartet werden. Ein Daemon-Thread kehrt periodisch das
Upload-Verzeichnis und löscht Session-Ordner, die älter als MAX_AGE_H sind.

Ergänzt das opportunistische Aufräumen beim Session-Start (views/file_patient.py) um eine
harte Garantie im laufenden Container. (Bei Container-Neustart/Deploy ist /tmp ohnehin weg.)
"""

import os
import shutil
import tempfile
import threading
import time

import streamlit as st

_BASE = os.path.join(tempfile.gettempdir(), "edf_analyzer")
MAX_AGE_H = 4.0            # Dateien älter als 4 h werden gelöscht (deutlich < 24 h)
SWEEP_INTERVAL_S = 600     # alle 10 min kehren → spätestens 4 h 10 min bis zur Löschung


def sweep_once(max_age_h: float = MAX_AGE_H) -> int:
    """Löscht alle Session-Ordner älter als max_age_h. Gibt Anzahl gelöschter Ordner zurück."""
    if not os.path.isdir(_BASE):
        return 0
    cutoff = time.time() - max_age_h * 3600
    removed = 0
    for entry in os.scandir(_BASE):
        try:
            if entry.is_dir() and entry.stat().st_mtime < cutoff:
                shutil.rmtree(entry.path, ignore_errors=True)
                removed += 1
        except OSError:
            pass
    return removed


def _loop():
    while True:
        try:
            sweep_once()
        except Exception:
            pass
        time.sleep(SWEEP_INTERVAL_S)


@st.cache_resource
def ensure_cleanup_daemon():
    """Startet den Cleanup-Daemon EINMAL pro Prozess (st.cache_resource = Prozess-Singleton)."""
    sweep_once()  # sofort einmal kehren beim Start
    t = threading.Thread(target=_loop, name="edf-tmp-cleanup", daemon=True)
    t.start()
    return t
