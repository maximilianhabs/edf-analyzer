"""Seite: EEG-Viewer — Montagen, Filter, Kopfdiagramm, optionale EKG-Spur."""

import numpy as np
import streamlit as st

from core.shared import (
    MONTAGES, get_edf_or_stop, get_filtered_eeg, get_bipolar_epoch,
    eeg_figure, render_head_diagram, window_nav_controls,
)


def render():
    st.title(":material/psychology: EEG-Viewer")

    edf, edf_path = get_edf_or_stop()
    sfreq = edf["sfreq"]

    # ── Bedienpanel (links) + eigenständiges Kopfdiagramm-Panel (rechts) ────
    col_panel, col_head = st.columns([3.2, 1])

    with col_panel:
        with st.container(border=True):
            col_m, col_s = st.columns([3.2, 1])
            montage_name = col_m.selectbox("Montage (DGKN)", list(MONTAGES.keys()), index=0)
            spacing = col_s.number_input("µV / Spur", 20, 600, 150, step=10)

            st.markdown(
                "<div style='font-size:12px;color:#888;margin-top:-4px;margin-bottom:2px'>"
                "Frequenzfilter</div>", unsafe_allow_html=True,
            )
            col_lc, col_hc = st.columns([1.4, 1])
            TC_OPTIONS = {
                "0.1 s (≈1.59 Hz)": 1.59,
                "0.3 s (≈0.53 Hz)": 0.53,
                "1.0 s (≈0.16 Hz)": 0.16,
                "3.0 s (≈0.05 Hz)": 0.05,
            }
            tc_label = col_lc.selectbox("Zeitkonstante / untere Grenzfreq.", list(TC_OPTIONS.keys()), index=1)
            low_hz = TC_OPTIONS[tc_label]
            high_hz = col_hc.selectbox("Obere Grenzfreq. (Hz)", [15, 30, 35, 50, 70, 100], index=4)
            # EKG-Spur ist fix unten (kein Umschalter mehr) — wenn ein EKG-Kanal erkannt wurde.
            ecg_channels_avail = edf["ecg_channels"]
            show_ecg_lane = bool(ecg_channels_avail)
            if show_ecg_lane:
                st.caption(f"EKG-Spur fix unten: **{ecg_channels_avail[0]}** (eigene mV-Skala)")

    pairs = MONTAGES[montage_name]

    # Montage-Vollständigkeit: fehlende Elektroden → leere Ableitungen sichtbar machen
    _needed = {e for pair in pairs for e in pair}
    _missing_el = sorted(_needed - set(edf["eeg_map"].keys()))
    if _missing_el:
        st.warning(
            f"Für die Montage **{montage_name}** fehlen "
            f"{len(_missing_el)} Elektrode(n): **{', '.join(_missing_el)}** — die "
            f"betroffenen Ableitungen bleiben leer. Häufig Fehlklassifikation "
            f"(Artefakt/Muskel) → in **Kanal-Identifikation** auf EEG korrigieren."
        )

    with col_head:
        with st.container(border=True):
            st.markdown("<div style='font-size:12px;color:#888;text-align:center'>Aktive Montage</div>",
                        unsafe_allow_html=True)
            fig_head = render_head_diagram(pairs)
            fig_head.update_layout(height=190, margin=dict(t=5, b=5, l=5, r=5))
            st.plotly_chart(fig_head, use_container_width=True)

    # Ganze Aufnahme geplottet (kein Ausschneiden mehr nötig) — zwei einfache Regler
    # (Fensterbreite + Position) steuern die Ansicht zuverlässig; der native Plotly-
    # Rangeslider unter dem Chart bleibt als zusätzliche Scroll-Möglichkeit erhalten.
    t_s_eeg, eeg_window_sec = window_nav_controls(edf, "ep_eeg")
    n_samples = edf["n_samples"]
    t = np.arange(n_samples) / sfreq
    view_range = [t_s_eeg, t_s_eeg + eeg_window_sec]

    # Kalibrier-/Impedanzphase erkennen — Hinweis gilt für die ganze Aufnahme (nicht mehr
    # an ein Fenster gebunden, da man jetzt frei über die komplette Aufzeichnung scrollt).
    _CAL_KEYS = ("CAL", "IMP CHECK", "IMPEDANCE", "A1+A2 OFF", "KALIBR")
    _cal_anns = [a for a in edf["annotations"]
                 if any(k in a["description"].upper() for k in _CAL_KEYS)]
    if _cal_anns:
        _cal_times = ", ".join(f"{a['onset_s']:.0f}s" for a in _cal_anns[:6])
        st.info(
            f"**Kalibrier-/Impedanzphase(n) in dieser Aufnahme** (z. B. REC START · "
            f"IMP CHECK · A1+A2 OFF) bei: {_cal_times} — dort ist das EEG technisch "
            f"bedingt flach bzw. ungültig (gemeinsames Kalibriersignal hebt sich in "
            f"bipolarer Montage auf). Zu diesen Zeitpunkten scrollen, um es zu prüfen."
        )

    filtered_data = get_filtered_eeg(edf["data"], edf["eeg_map"], sfreq, low_hz, high_hz)
    derivs = get_bipolar_epoch(filtered_data, edf["eeg_map"], pairs, 0, n_samples)

    if show_ecg_lane and ecg_channels_avail:
        ecg_ch_lane = ecg_channels_avail[0]
        ecg_sig_mv = edf["ecg_filtered"][ecg_ch_lane] * 1000
        ecg_centered = ecg_sig_mv - np.median(ecg_sig_mv)
        # Auto-Flip: R-Zacke soll positiv oben sein (über die gesamte Aufnahme entschieden)
        if abs(ecg_centered.min()) > abs(ecg_centered.max()):
            ecg_centered = -ecg_centered
        # Robuste Skalierung (99. Perzentil statt Maximum) — bei voller Aufnahme kann ein
        # einzelner Artefakt-Ausschlag sonst die Skala für die gesamte Kurve verzerren.
        ecg_sens_mv = max(np.percentile(np.abs(ecg_centered), 99) * 1.15, 0.3)
        scale_factor = (spacing / 2) / ecg_sens_mv
        ecg_scaled = ecg_centered * scale_factor
        derivs = derivs + [(
            f"EKG ({ecg_ch_lane}, ±{ecg_sens_mv:.1f}mV)", ecg_scaled, "EKG", "#c0392b",
            ecg_sig_mv - np.median(ecg_sig_mv), "mV",
        )]

    # ── EEG-Kurve — volle Breite, kein Platzverlust durch Seitenspalte mehr ──
    fig = eeg_figure(derivs, t, spacing, edf["annotations"], view_range=view_range)
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        f"Bandpass: {low_hz:.2f}–{high_hz} Hz — Fensterbreite/Position oben einstellen, "
        f"oder direkt im Regler unter dem Plot scrollen ({t_s_eeg:.0f}s–{t_s_eeg + eeg_window_sec:.0f}s)."
    )

    if edf["annotations"]:
        st.caption("Annotationen in dieser Aufnahme: " + " | ".join(
            f"{a['onset_s']:.1f}s → {a['description']}" for a in edf["annotations"][:40]))
