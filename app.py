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

apply_global_style()
inject_arrow_key_nav()
logout_button()

from views import (file_patient, eeg_viewer, ecg_hrv, eeg_spectrum, report,
                   channel_report, aperiodic, artifact_selection, advanced_analysis)

pages = [
    st.Page(file_patient.render, title="Datei & Patient", icon="📂", default=True, url_path="datei-patient"),
    st.Page(channel_report.render, title="Kanal-Identifikation", icon="🔍", url_path="kanaele"),
    st.Page(eeg_viewer.render, title="EEG-Viewer", icon="🧠", url_path="eeg-viewer"),
    st.Page(ecg_hrv.render, title="EKG & HRV", icon="❤️", url_path="ekg-hrv"),
    st.Page(eeg_spectrum.render, title="EEG-Spektrum", icon="📊", url_path="eeg-spektrum"),
    st.Page(aperiodic.render, title="Aperiodisch (1/f)", icon="🌀", url_path="aperiodisch"),
    st.Page(artifact_selection.render, title="Artefaktkorrektur & Selektion", icon="🧹", url_path="artefakt-selektion"),
    st.Page(advanced_analysis.render, title="Erweiterte Analysen & Methodik", icon="🔬", url_path="erweitert"),
    st.Page(report.render, title="Report", icon="📋", url_path="report"),
]

pg = st.navigation(pages, position="sidebar")
render_sidebar_status()
pg.run()
