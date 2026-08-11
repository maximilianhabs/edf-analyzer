"""Seite: EEG-Viewer — Montagen, Filter, Kopfdiagramm, optionale EKG-Spur."""

import numpy as np
import streamlit as st

from core.i18n import tr
from core.shared import (
    MONTAGES, get_edf_or_stop, get_filtered_eeg, get_bipolar_epoch,
    eeg_figure, render_head_diagram, epoch_nav,
)


def render():
    st.title(":material/psychology: " + tr("eeg_viewer.title"))

    edf, edf_path = get_edf_or_stop()
    sfreq = edf["sfreq"]

    # ── Bedienpanel (links) + eigenständiges Kopfdiagramm-Panel (rechts) ────
    col_panel, col_head = st.columns([3.2, 1])

    with col_panel:
        with st.container(border=True):
            col_m, col_ep, col_s = st.columns([2.2, 1, 1])
            montage_name = col_m.selectbox(tr("eeg_viewer.montage"), list(MONTAGES.keys()), index=0)
            eeg_epoch_sec = col_ep.selectbox(tr("eeg_viewer.epoch_length"), [5, 10, 20, 30], index=1,
                                              format_func=lambda v: f"{v} s")
            spacing = col_s.number_input(tr("eeg_viewer.uv_per_trace"), 20, 600, 150, step=10)

            st.markdown(
                "<div style='font-size:12px;color:#888;margin-top:-4px;margin-bottom:2px'>"
                + tr("eeg_viewer.freq_filter") + "</div>", unsafe_allow_html=True,
            )
            col_lc, col_hc = st.columns([1.4, 1])
            TC_OPTIONS = {
                "0.1 s (≈1.59 Hz)": 1.59,
                "0.3 s (≈0.53 Hz)": 0.53,
                "1.0 s (≈0.16 Hz)": 0.16,
                "3.0 s (≈0.05 Hz)": 0.05,
            }
            tc_label = col_lc.selectbox(tr("eeg_viewer.time_constant"), list(TC_OPTIONS.keys()), index=1)
            low_hz = TC_OPTIONS[tc_label]
            high_hz = col_hc.selectbox(tr("eeg_viewer.upper_cutoff"), [15, 30, 35, 50, 70, 100], index=4)
            # EKG-Spur ist fix unten (kein Umschalter mehr) — wenn ein EKG-Kanal erkannt wurde.
            ecg_channels_avail = edf["ecg_channels"]
            show_ecg_lane = bool(ecg_channels_avail)
            if show_ecg_lane:
                st.caption(tr("eeg_viewer.ecg_lane_note", ch=ecg_channels_avail[0]))

    pairs = MONTAGES[montage_name]

    # Montage-Vollständigkeit: fehlende Elektroden → leere Ableitungen sichtbar machen
    _needed = {e for pair in pairs for e in pair}
    _missing_el = sorted(_needed - set(edf["eeg_map"].keys()))
    if _missing_el:
        st.warning(tr("eeg_viewer.missing_electrodes", montage=montage_name,
                      n=len(_missing_el), list=", ".join(_missing_el)))

    with col_head:
        with st.container(border=True):
            st.markdown("<div style='font-size:12px;color:#888;text-align:center'>"
                        + tr("eeg_viewer.active_montage") + "</div>",
                        unsafe_allow_html=True)
            fig_head = render_head_diagram(pairs)
            fig_head.update_layout(height=190, margin=dict(t=5, b=5, l=5, r=5))
            st.plotly_chart(fig_head, use_container_width=True)

    ep = epoch_nav(edf, "ep_eeg", "EEG", epoch_sec=eeg_epoch_sec)
    t_s = ep * eeg_epoch_sec
    i_s, i_e = int(t_s * sfreq), int((t_s + eeg_epoch_sec) * sfreq)
    t = np.arange(i_s, i_e) / sfreq

    # Kalibrier-/Impedanzphase erkennen — dort ist das EEG technisch bedingt flach
    _CAL_KEYS = ("CAL", "IMP CHECK", "IMPEDANCE", "A1+A2 OFF", "KALIBR")
    _ep_anns = [a for a in edf["annotations"] if t_s <= a["onset_s"] <= t_s + eeg_epoch_sec]
    if any(any(k in a["description"].upper() for k in _CAL_KEYS) for a in _ep_anns):
        st.info(tr("eeg_viewer.calibration_phase"))

    with st.spinner(tr("shared.filtering_eeg")):
        filtered_data = get_filtered_eeg(edf["data"], edf["eeg_map"], sfreq, low_hz, high_hz)
    derivs = get_bipolar_epoch(filtered_data, edf["eeg_map"], pairs, i_s, i_e)

    if show_ecg_lane and ecg_channels_avail:
        ecg_ch_lane = ecg_channels_avail[0]
        ecg_sig_mv = edf["ecg_filtered"][ecg_ch_lane][i_s:i_e] * 1000
        ecg_centered = ecg_sig_mv - np.median(ecg_sig_mv)
        # Auto-Flip: R-Zacke soll positiv oben sein
        if abs(ecg_centered.min()) > abs(ecg_centered.max()):
            ecg_centered = -ecg_centered
        ecg_sens_mv = max(np.abs(ecg_centered).max() * 1.15, 0.3)
        scale_factor = (spacing / 2) / ecg_sens_mv
        ecg_scaled = ecg_centered * scale_factor
        derivs = derivs + [(
            f"EKG ({ecg_ch_lane}, ±{ecg_sens_mv:.1f}mV)", ecg_scaled, "EKG", "#c0392b",
            ecg_sig_mv - np.median(ecg_sig_mv), "mV",
        )]

    # ── EEG-Kurve — volle Breite, kein Platzverlust durch Seitenspalte mehr ──
    fig = eeg_figure(derivs, t, spacing, edf["annotations"], t_s, t_s + eeg_epoch_sec)
    st.plotly_chart(fig, use_container_width=True)
    st.caption(tr("eeg_viewer.bandpass", low=low_hz, high=high_hz))

    epoch_anns = [a for a in edf["annotations"] if t_s <= a["onset_s"] <= t_s + eeg_epoch_sec]
    if epoch_anns:
        st.caption(tr("eeg_viewer.annotations_prefix") + " | ".join(
            f"{a['onset_s']:.1f}s → {a['description']}" for a in epoch_anns))
