"""EDF Analyzer — lokale Streamlit-App. Multi-Page mit linker Navigation."""

import sys, os, warnings

import streamlit as st

# Projektwurzel auf den Importpfad: Streamlit startet `app.py` als Skript, nicht als Paket —
# ohne das findet `import core...` in den Seiten nichts.
sys.path.insert(0, os.path.dirname(__file__))

# Nur die EINE bekannte Warnung stummschalten, nicht alle.
#
# Hier stand bis 2026-08-12 ein pauschales `warnings.filterwarnings("ignore")`. Gemessen an
# einem vollständigen Durchlauf (Laden, alle Analysen, alle drei Reports) unterdrückte das
# genau eine Warnung — die fooof-Deprecation — und verdeckte dafür alles, was Abhängigkeiten
# oder eigener Code künftig melden. Die Pillow-Deprecation im visuellen Report fiel uns nur
# deshalb auf, weil wir sie zufällig in einem Skript ausserhalb der App sahen.
#
# Warnungen landen im Server-Log, nicht in der Oberfläche — sie stören also niemanden, der
# die App benutzt, aber sie erreichen den, der sie beheben kann.
warnings.filterwarnings(
    "ignore",
    message=r"The `fooof` package is being deprecated.*",
    category=DeprecationWarning,
)

st.set_page_config(page_title="EDF Analyzer", layout="wide", page_icon=":material/neurology:")

from core.i18n import begin_run, init_lang, tr
begin_run()
init_lang()

from core.auth import require_login, logout_button

if not require_login():
    st.stop()

from core.shared import apply_global_style, inject_arrow_key_nav, render_sidebar_status
from core.cleanup import ensure_cleanup_daemon

# Garantierter Hintergrund-Cleanup: keine hochgeladene EDF bleibt länger als die TTL liegen,
# auch ohne neue Sessions (läuft einmal pro Prozess als Daemon).
ensure_cleanup_daemon()

apply_global_style()
inject_arrow_key_nav()
logout_button()

from views import (file_patient, eeg_viewer, ecg_hrv, eeg_spectrum, report,
                   channel_report, aperiodic, artifact_selection, advanced_analysis,
                   rhythm_screening)


# Phase 1 des GUI-Redesigns (User-Vorgabe 2026-08-08, siehe [[project_edf_ui_redesign]]):
# Material-Icon-Shortcodes statt bunter Emojis — nüchternere, plattformübergreifend
# konsistente Linien-Icons statt Emoji, die je nach OS/Browser unterschiedlich aussehen.
# Reine Text-/Konfigurationsänderung, kein zusätzlicher Rechenaufwand.
# Seitentitel jetzt über core/i18n.py::tr() — Stufe 1 des i18n-Konzepts, siehe
# [[project_edf_i18n_konzept]]. url_path bleibt unverändert (sprachneutral, sonst brechen
# Lesezeichen beim Sprachwechsel).
pages = [
    st.Page(file_patient.render, title=tr("nav.file_patient"), icon=":material/folder_open:", default=True, url_path="datei-patient"),
    st.Page(channel_report.render, title=tr("nav.channel_report"), icon=":material/search:", url_path="kanaele"),
    st.Page(eeg_viewer.render, title=tr("nav.eeg_viewer"), icon=":material/psychology:", url_path="eeg-viewer"),
    st.Page(rhythm_screening.render, title=tr("nav.rhythm_screening"), icon=":material/monitor_heart:", url_path="rhythmus-screening"),
    st.Page(ecg_hrv.render, title=tr("nav.ecg_hrv"), icon=":material/favorite:", url_path="ekg-hrv"),
    st.Page(eeg_spectrum.render, title=tr("nav.eeg_spectrum"), icon=":material/bar_chart:", url_path="eeg-spektrum"),
    st.Page(aperiodic.render, title=tr("nav.aperiodic"), icon=":material/waves:", url_path="aperiodisch"),
    st.Page(artifact_selection.render, title=tr("nav.artifact_selection"), icon=":material/cleaning_services:", url_path="artefakt-selektion"),
    st.Page(advanced_analysis.render, title=tr("nav.advanced_analysis"), icon=":material/science:", url_path="erweitert"),
    st.Page(report.render, title=tr("nav.report"), icon=":material/description:", url_path="report"),
]

pg = st.navigation(pages, position="sidebar")
render_sidebar_status()
from core.i18n import render_lang_switch
render_lang_switch(st.sidebar)
pg.run()
