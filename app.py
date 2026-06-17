"""EDF Analyzer — lokale Streamlit-App. Multi-Page mit linker Navigation."""

import sys, os, warnings
import streamlit as st

sys.path.insert(0, os.path.dirname(__file__))
warnings.filterwarnings("ignore")

st.set_page_config(page_title="EDF Analyzer", layout="wide", page_icon="🧠")

from core.shared import apply_global_style, inject_arrow_key_nav

apply_global_style()
inject_arrow_key_nav()

from views import file_patient, eeg_viewer, ecg_hrv, eeg_spectrum, report

pages = [
    st.Page(file_patient.render, title="Datei & Patient", icon="📂", default=True, url_path="datei-patient"),
    st.Page(eeg_viewer.render, title="EEG-Viewer", icon="🧠", url_path="eeg-viewer"),
    st.Page(ecg_hrv.render, title="EKG & HRV", icon="❤️", url_path="ekg-hrv"),
    st.Page(eeg_spectrum.render, title="EEG-Spektrum", icon="📊", url_path="eeg-spektrum"),
    st.Page(report.render, title="Report", icon="📋", url_path="report"),
]

pg = st.navigation(pages, position="sidebar")
pg.run()
