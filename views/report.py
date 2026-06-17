"""Seite: Report — Aufnahme-Übersicht, Datenschutz-Status, alle Kanäle."""

import numpy as np
import pandas as pd
import streamlit as st

from core.shared import EPOCH_SEC, get_edf_or_stop


def render():
    st.title("📋 Report")

    edf, edf_path = get_edf_or_stop()
    sfreq = edf["sfreq"]
    n_epochs = edf["n_epochs"]

    st.subheader("Aufnahme-Übersicht")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Dauer", f"{edf['duration_s']/60:.1f} min")
    c2.metric("Sampling", f"{sfreq:.0f} Hz")
    c3.metric("Kanäle", len(edf["ch_names"]))
    c4.metric("Epochen (10 s)", n_epochs)

    col_l, col_r = st.columns(2)
    with col_l:
        st.markdown("**Datenschutz**")
        st.dataframe(pd.DataFrame([
            {"Feld": "Patient-ID im Header",
             "Status": "⚠️ vorhanden" if edf["has_patient_id"] else "✅ leer"},
            {"Feld": "Recording-ID im Header",
             "Status": "⚠️ vorhanden" if edf["has_rec_id"] else "✅ leer"},
            {"Feld": "Format", "Status": "EDF+D (discontinuous)"},
            {"Feld": "Encoding", "Status": "latin1 (NeuroFax)"},
        ]), hide_index=True, use_container_width=True)

    with col_r:
        st.markdown("**Klinische Annotations**")
        if edf["annotations"]:
            st.dataframe(
                pd.DataFrame([{"Zeit (s)": a["onset_s"], "Ereignis": a["description"]}
                              for a in edf["annotations"]]),
                hide_index=True, use_container_width=True, height=380,
            )

    with st.expander("Alle Kanäle"):
        rows = []
        for i, ch in enumerate(edf["ch_names"]):
            sig = edf["data"][i]
            sig_d = (sig - sig.mean())
            unit = "µV" if ch.startswith("EEG") else "mV"
            factor = 1e6 if ch.startswith("EEG") else 1e3
            rows.append({
                "Nr": i, "Kanal": ch,
                f"Min ({unit})": f"{sig_d.min()*factor:.1f}",
                f"Max ({unit})": f"{sig_d.max()*factor:.1f}",
                f"RMS ({unit})": f"{np.sqrt(np.mean(sig_d**2))*factor:.1f}",
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
