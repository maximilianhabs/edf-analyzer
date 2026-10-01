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

# ── Grenzen für die Streamlit-Zwischenspeicher ────────────────────────────────
# Bis 2026-10-01 hatte keiner der rund 20 Zwischenspeicher eine Grenze. Jeder Upload trägt eine
# zufällige Kennung im Pfad, erzeugte also neue Einträge — gemessen rund +50 MB je Upload, die
# erst ein Neustart freigab, auch nachdem die Datei selbst längst gelöscht war. Das erklärt, warum
# die App im Betrieb immer zäher wurde.
#
# Lebensdauer = Lebensdauer der Datei: Nach MAX_AGE_H ist die Aufnahme gelöscht, jeder Eintrag
# dazu nur noch Ballast. Fällt ein Eintrag vorher heraus, wird neu gerechnet — langsamer, nie
# falsch. tests/test_cache_isolation.py prüft, dass jeder Zwischenspeicher begrenzt ist.
CACHE_TTL_S = int(MAX_AGE_H * 3600)
CACHE_MAX_GROSS = 4    # Einträge mit vollständiger Datenmatrix (Aufnahme, gefilterte EEG-Matrix)
CACHE_MAX = 32         # alles andere (Detektionen, Kennwerte, Exporte)


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
