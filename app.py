"""EDF Analyzer — lokale Streamlit-App. Multi-Page mit linker Navigation."""

import sys, os, warnings
import streamlit as st

sys.path.insert(0, os.path.dirname(__file__))
warnings.filterwarnings("ignore")

st.set_page_config(page_title="EDF Analyzer", layout="wide", page_icon="🧠")

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
pages = [
    st.Page(file_patient.render, title="Datei & Patient", icon=":material/folder_open:", default=True, url_path="datei-patient"),
    st.Page(channel_report.render, title="Kanal-Identifikation", icon=":material/search:", url_path="kanaele"),
    st.Page(eeg_viewer.render, title="EEG-Viewer", icon=":material/psychology:", url_path="eeg-viewer"),
    st.Page(rhythm_screening.render, title="Rhythmus-Screening", icon=":material/monitor_heart:", url_path="rhythmus-screening"),
    st.Page(ecg_hrv.render, title="EKG & HRV", icon=":material/favorite:", url_path="ekg-hrv"),
    st.Page(eeg_spectrum.render, title="EEG-Spektrum", icon=":material/bar_chart:", url_path="eeg-spektrum"),
    st.Page(aperiodic.render, title="Aperiodisch (1/f)", icon=":material/waves:", url_path="aperiodisch"),
    st.Page(artifact_selection.render, title="Artefaktkorrektur & Selektion", icon=":material/cleaning_services:", url_path="artefakt-selektion"),
    st.Page(advanced_analysis.render, title="Erweiterte Analysen & Methodik", icon=":material/science:", url_path="erweitert"),
    st.Page(report.render, title="Report", icon=":material/description:", url_path="report"),
]

pg = st.navigation(pages, position="sidebar")
render_sidebar_status()
pg.run()
