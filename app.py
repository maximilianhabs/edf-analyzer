"""EDF Analyzer — lokale Streamlit-App."""

import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import sys, os

sys.path.insert(0, os.path.dirname(__file__))
from core.loader import load_edf, check_privacy, get_channel_groups, extract_channel, get_annotations
from analysis.ecg import preprocess_ecg, detect_r_peaks, compute_rr_intervals, compute_hrv_time_domain, compute_hrv_frequency_domain

st.set_page_config(page_title="EDF Analyzer", layout="wide", page_icon="🧠")
st.title("🧠 EDF Analyzer")
st.caption("Klinische EEG/EKG-Analyse | NeuroFax / Neoncode")

# ── Sidebar: Datei-Auswahl ──────────────────────────────────────────────────
with st.sidebar:
    st.header("Datei laden")
    edf_path = st.text_input(
        "Pfad zur EDF-Datei",
        value=os.path.expanduser("~/Downloads/CA177317.edf"),
        help="Absoluter Pfad zur .edf Datei",
    )
    load_btn = st.button("Laden", type="primary", use_container_width=True)

    st.divider()
    st.caption("⚠️ EDF-Dateien enthalten Patientendaten. Diese App läuft nur lokal und sendet keine Daten.")

# ── Session State ────────────────────────────────────────────────────────────
if "raw" not in st.session_state:
    st.session_state.raw = None

if load_btn or (st.session_state.raw is None and os.path.exists(edf_path)):
    with st.spinner("Lade EDF..."):
        try:
            st.session_state.raw = load_edf(edf_path, preload=True)
            st.session_state.edf_path = edf_path
            st.session_state.privacy = check_privacy(edf_path)
        except Exception as e:
            st.error(f"Fehler beim Laden: {e}")
            st.stop()

if st.session_state.raw is None:
    st.info("Bitte EDF-Datei über die Sidebar laden.")
    st.stop()

raw = st.session_state.raw
privacy = st.session_state.privacy
groups = get_channel_groups(raw)
annotations = get_annotations(raw)

# ── Datenschutz-Banner ───────────────────────────────────────────────────────
if privacy["has_patient_id"] or privacy["has_recording_id"]:
    st.warning(
        "⚠️ **Patientendaten im Header erkannt.** "
        "Diese Datei enthält personenbezogene Daten. Nur lokal verwenden — nicht weiterleiten.",
        icon="🔒",
    )

# ── Tabs ─────────────────────────────────────────────────────────────────────
tab_report, tab_ecg, tab_eeg, tab_vitals = st.tabs(
    ["📋 Datei-Report", "❤️ EKG & HRV", "🧠 EEG-Übersicht", "📊 Vitalparameter"]
)

# ═══════════════════════════════════════════════════════════════════════════
# TAB 1 — DATEI-REPORT
# ═══════════════════════════════════════════════════════════════════════════
with tab_report:
    st.subheader("Aufnahme-Übersicht")

    c1, c2, c3, c4 = st.columns(4)
    duration_min = raw.times[-1] / 60
    c1.metric("Dauer", f"{duration_min:.1f} min")
    c2.metric("Sampling", f"{raw.info['sfreq']:.0f} Hz")
    c3.metric("Kanäle gesamt", len(raw.ch_names))
    c4.metric("Annotations", len(annotations))

    st.divider()

    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown("**Kanal-Übersicht**")
        channel_summary = {
            "EEG (10-20)": len(groups["eeg"]),
            "EKG": len(groups["ecg"]),
            "Vitalparameter": len(groups["vitals"]),
            "Sonstige POL": len(groups["other"]),
        }
        df_channels = pd.DataFrame(
            [{"Gruppe": k, "Anzahl": v, "Kanäle": ", ".join(
                groups["eeg"][:3] + (["…"] if len(groups["eeg"]) > 3 else [])
                if k == "EEG (10-20)" else
                groups["ecg"] if k == "EKG" else
                groups["vitals"] if k == "Vitalparameter" else
                groups["other"][:4]
            )} for k, v in channel_summary.items()]
        )
        st.dataframe(df_channels, hide_index=True, use_container_width=True)

        st.markdown("**Datenschutz-Status**")
        st.dataframe(pd.DataFrame([
            {"Feld": "Patient-ID im Header", "Status": "⚠️ vorhanden" if privacy["has_patient_id"] else "✅ leer"},
            {"Feld": "Recording-ID im Header", "Status": "⚠️ vorhanden" if privacy["has_recording_id"] else "✅ leer"},
            {"Feld": "EDF-Format", "Status": "EDF+D (discontinuous)"},
            {"Feld": "Encoding", "Status": "latin1 (NeuroFax)"},
        ]), hide_index=True, use_container_width=True)

    with col_right:
        st.markdown("**Klinische Annotations**")
        if annotations:
            df_ann = pd.DataFrame(annotations)
            df_ann["onset_s"] = df_ann["onset_s"].apply(lambda x: f"{x:.1f}s")
            df_ann.columns = ["Zeit", "Dauer (s)", "Ereignis"]
            st.dataframe(df_ann, hide_index=True, use_container_width=True, height=400)
        else:
            st.info("Keine Annotations gefunden.")

    # Alle Kanäle
    with st.expander("Alle Kanäle anzeigen"):
        ch_data = []
        for i, ch in enumerate(raw.ch_names):
            d, _ = raw[[i], :]
            d_mv = d[0] * 1e3  # to mV
            ch_data.append({
                "Nr": i,
                "Kanal": ch,
                "Min (mV)": f"{d_mv.min():.2f}",
                "Max (mV)": f"{d_mv.max():.2f}",
                "RMS (mV)": f"{np.sqrt(np.mean(d_mv**2)):.2f}",
            })
        st.dataframe(pd.DataFrame(ch_data), hide_index=True, use_container_width=True)

# ═══════════════════════════════════════════════════════════════════════════
# TAB 2 — EKG & HRV
# ═══════════════════════════════════════════════════════════════════════════
with tab_ecg:
    st.subheader("EKG-Analyse")

    ecg_ch = st.selectbox("EKG-Kanal", groups["ecg"], index=0)
    col_t1, col_t2 = st.columns(2)
    t_start = col_t1.number_input("Von (Sekunde)", min_value=0.0, max_value=raw.times[-1]-10, value=10.0, step=5.0)
    t_end = col_t2.number_input("Bis (Sekunde)", min_value=10.0, max_value=raw.times[-1], value=min(70.0, raw.times[-1]), step=5.0)

    signal_full, sfreq = extract_channel(raw, ecg_ch)
    signal_clean_full = preprocess_ecg(signal_full, sfreq)

    # Segment für Plot
    i_start = int(t_start * sfreq)
    i_end = int(t_end * sfreq)
    t_seg = np.arange(i_start, i_end) / sfreq
    sig_seg = signal_clean_full[i_start:i_end]

    # R-Peaks im Segment
    try:
        r_peaks_full = detect_r_peaks(signal_clean_full, sfreq)
        r_in_seg = r_peaks_full[(r_peaks_full >= i_start) & (r_peaks_full < i_end)]
        r_times = r_in_seg / sfreq
        r_vals = signal_clean_full[r_in_seg]
    except Exception:
        r_times, r_vals = np.array([]), np.array([])

    fig_ecg = go.Figure()
    fig_ecg.add_trace(go.Scatter(
        x=t_seg, y=sig_seg * 1000,
        mode="lines", name="EKG", line=dict(color="#e74c3c", width=1),
    ))
    if len(r_times) > 0:
        fig_ecg.add_trace(go.Scatter(
            x=r_times, y=r_vals * 1000,
            mode="markers", name="R-Peaks",
            marker=dict(color="#2ecc71", size=8, symbol="triangle-up"),
        ))
    fig_ecg.update_layout(
        xaxis_title="Zeit (s)", yaxis_title="Amplitude (mV)",
        height=350, margin=dict(t=20, b=40),
        legend=dict(orientation="h"),
    )
    st.plotly_chart(fig_ecg, use_container_width=True)

    st.caption(f"R-Peaks im Segment: {len(r_times)} | Gesamtaufnahme erkannt: {len(r_peaks_full)}")

    # HRV
    st.divider()
    st.subheader("HRV-Metriken (Gesamtaufnahme)")

    rr_ms = compute_rr_intervals(r_peaks_full, sfreq)
    hrv_time = compute_hrv_time_domain(rr_ms)
    hrv_freq = compute_hrv_frequency_domain(rr_ms)

    if hrv_time:
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Mittlere HR", f"{hrv_time.get('mean_hr_bpm', '–')} bpm")
        c2.metric("Mittleres RR", f"{hrv_time.get('mean_rr_ms', '–')} ms")
        c3.metric("SDNN", f"{hrv_time.get('sdnn_ms', '–')} ms")
        c4.metric("RMSSD", f"{hrv_time.get('rmssd_ms', '–')} ms")
        c5.metric("pNN50", f"{hrv_time.get('pnn50_pct', '–')} %")

    col_rr, col_poin = st.columns(2)

    with col_rr:
        st.markdown("**Tachogramm (RR-Intervalle über Zeit)**")
        rr_times = r_peaks_full[1:len(rr_ms)+1] / sfreq
        fig_rr = go.Figure(go.Scatter(
            x=rr_times, y=rr_ms,
            mode="lines+markers", line=dict(color="#3498db", width=1),
            marker=dict(size=3),
        ))
        fig_rr.update_layout(
            xaxis_title="Zeit (s)", yaxis_title="RR-Intervall (ms)",
            height=280, margin=dict(t=10, b=40),
        )
        st.plotly_chart(fig_rr, use_container_width=True)

    with col_poin:
        st.markdown("**Poincaré-Plot (RR_n vs RR_n+1)**")
        if len(rr_ms) > 2:
            fig_poin = go.Figure(go.Scatter(
                x=rr_ms[:-1], y=rr_ms[1:],
                mode="markers", marker=dict(color="#9b59b6", size=4, opacity=0.6),
            ))
            fig_poin.update_layout(
                xaxis_title="RR_n (ms)", yaxis_title="RR_n+1 (ms)",
                height=280, margin=dict(t=10, b=40),
            )
            st.plotly_chart(fig_poin, use_container_width=True)

    if hrv_freq:
        with st.expander("Frequenzdomäne HRV"):
            df_freq = pd.DataFrame([
                {"Band": "VLF (0.003–0.04 Hz)", "Power (ms²)": hrv_freq.get("vlf_ms2"), "Interpretation": "Langzeit-Regulation"},
                {"Band": "LF (0.04–0.15 Hz)", "Power (ms²)": hrv_freq.get("lf_ms2"), "nu (%)": hrv_freq.get("lf_nu"), "Interpretation": "Sympathisch + Parasympathisch"},
                {"Band": "HF (0.15–0.4 Hz)", "Power (ms²)": hrv_freq.get("hf_ms2"), "nu (%)": hrv_freq.get("hf_nu"), "Interpretation": "Parasympathisch (Atemfrequenz)"},
            ])
            st.dataframe(df_freq, hide_index=True, use_container_width=True)
            st.metric("LF/HF-Ratio", hrv_freq.get("lf_hf_ratio", "–"), help="< 1.0 = parasympathisch dominant, > 2.0 = sympathisch dominant")

# ═══════════════════════════════════════════════════════════════════════════
# TAB 3 — EEG-ÜBERSICHT (DGKN-Montagen)
# ═══════════════════════════════════════════════════════════════════════════

# DGKN-Montagen: Doppelte Banane (bipolare Längsreihe)
# Kanalbezeichnungen im EDF: "EEG Fp1-Ref", "EEG T3-Ref" etc.
# Bipolare Ableitung A-B = Signal(A) - Signal(B)

DGKN_MONTAGES = {
    "Bipolar Temporal (Temporalreihe)": {
        "beschreibung": "Temporale Kette links + rechts — Außenreihe der Doppelten Banane",
        "ketten": {
            "Temporalreihe links": [
                ("Fp1", "F7"), ("F7", "T3"), ("T3", "T5"), ("T5", "O1"),
            ],
            "Temporalreihe rechts": [
                ("Fp2", "F8"), ("F8", "T4"), ("T4", "T6"), ("T6", "O2"),
            ],
        },
    },
    "Bipolar Parasagittal (Parasagittalreihe)": {
        "beschreibung": "Parasagittale Kette links + rechts — Innenreihe der Doppelten Banane",
        "ketten": {
            "Parasagittalreihe links": [
                ("Fp1", "F3"), ("F3", "C3"), ("C3", "P3"), ("P3", "O1"),
            ],
            "Parasagittalreihe rechts": [
                ("Fp2", "F4"), ("F4", "C4"), ("C4", "P4"), ("P4", "O2"),
            ],
        },
    },
    "Doppelte Banane (komplett)": {
        "beschreibung": "Vollständige bipolare Längsreihe nach DGKN — Temporalreihe + Parasagittalreihe + Mittellinie",
        "ketten": {
            "Temporalreihe links": [
                ("Fp1", "F7"), ("F7", "T3"), ("T3", "T5"), ("T5", "O1"),
            ],
            "Parasagittalreihe links": [
                ("Fp1", "F3"), ("F3", "C3"), ("C3", "P3"), ("P3", "O1"),
            ],
            "Mittellinie": [
                ("Fz", "Cz"), ("Cz", "Pz"),
            ],
            "Parasagittalreihe rechts": [
                ("Fp2", "F4"), ("F4", "C4"), ("C4", "P4"), ("P4", "O2"),
            ],
            "Temporalreihe rechts": [
                ("Fp2", "F8"), ("F8", "T4"), ("T4", "T6"), ("T6", "O2"),
            ],
        },
    },
    "Referenziell Cz": {
        "beschreibung": "Alle Kanäle gegen Cz — referenzielle Ableitung nach DGKN",
        "ketten": {
            "Links temporal": [("Fp1", "Cz"), ("F7", "Cz"), ("T3", "Cz"), ("T5", "Cz"), ("O1", "Cz")],
            "Links parasagittal": [("F3", "Cz"), ("C3", "Cz"), ("P3", "Cz")],
            "Rechts parasagittal": [("F4", "Cz"), ("C4", "Cz"), ("P4", "Cz")],
            "Rechts temporal": [("Fp2", "Cz"), ("F8", "Cz"), ("T4", "Cz"), ("T6", "Cz"), ("O2", "Cz")],
        },
    },
}


def get_eeg_signal(raw, electrode_name):
    """Extract signal by short electrode name (e.g. 'Fp1' from 'EEG Fp1-Ref')."""
    for ch in raw.ch_names:
        if ch.startswith("EEG") and electrode_name in ch:
            idx = raw.ch_names.index(ch)
            data, _ = raw[[idx], :]
            return data[0]
    return None


def compute_bipolar(raw, anode, cathode):
    """Compute bipolar derivation: anode - cathode. Returns (signal, label)."""
    sig_a = get_eeg_signal(raw, anode)
    sig_b = get_eeg_signal(raw, cathode)
    if sig_a is None or sig_b is None:
        return None, f"{anode}-{cathode} (fehlt)"
    return (sig_a - sig_b), f"{anode}–{cathode}"


with tab_eeg:
    st.subheader("EEG-Montagen nach DGKN")

    col_mont, col_t1, col_t2, col_amp = st.columns([2, 1, 1, 1])
    montage_name = col_mont.selectbox("Montage", list(DGKN_MONTAGES.keys()), index=0)
    t_start_eeg = col_t1.number_input("Von (s)", min_value=0.0, max_value=raw.times[-1]-5,
                                       value=10.0, step=5.0, key="eeg_start")
    t_end_eeg = col_t2.number_input("Bis (s)", min_value=5.0, max_value=raw.times[-1],
                                     value=min(30.0, raw.times[-1]), step=5.0, key="eeg_end")
    amplitude_scale = col_amp.number_input("Skalierung (µV)", min_value=10, max_value=500,
                                            value=100, step=10)

    montage = DGKN_MONTAGES[montage_name]
    st.caption(f"ℹ️ {montage['beschreibung']}")

    i_s = int(t_start_eeg * sfreq)
    i_e = int(t_end_eeg * sfreq)
    t_eeg = np.arange(i_s, i_e) / sfreq

    # Alle Ableitungen berechnen, Ketten farblich trennen
    chain_colors = ["#2c3e50", "#1a5276", "#7b241c", "#1e8449", "#6c3483"]
    derivations = []  # list of (label, signal, chain_name)

    for chain_name, pairs in montage["ketten"].items():
        for anode, cathode in pairs:
            sig, label = compute_bipolar(raw, anode, cathode)
            derivations.append((label, sig, chain_name))

    n = len(derivations)
    spacing = amplitude_scale * 2
    chain_names = list(montage["ketten"].keys())

    fig_eeg = go.Figure()

    for idx, (label, sig, chain_name) in enumerate(derivations):
        offset = (n - 1 - idx) * spacing
        color = chain_colors[chain_names.index(chain_name) % len(chain_colors)]

        if sig is not None:
            seg = sig[i_s:i_e] * 1e6
            fig_eeg.add_trace(go.Scatter(
                x=t_eeg, y=seg + offset,
                mode="lines", name=chain_name,
                legendgroup=chain_name,
                showlegend=(idx == next(i for i, (_, _, c) in enumerate(derivations) if c == chain_name)),
                line=dict(width=0.9, color=color),
                hovertemplate=f"<b>{label}</b>: %{{customdata:.1f}} µV<extra></extra>",
                customdata=seg,
            ))
        else:
            # Kanal fehlt — leere Linie mit Hinweis
            fig_eeg.add_trace(go.Scatter(
                x=[t_eeg[0], t_eeg[-1]], y=[offset, offset],
                mode="lines", line=dict(width=0.5, color="#cccccc", dash="dot"),
                showlegend=False, hoverinfo="skip",
            ))

    # Annotations als vertikale Marker
    for ann in annotations:
        onset = float(ann["onset_s"])
        if t_start_eeg <= onset <= t_end_eeg:
            fig_eeg.add_vline(
                x=onset, line_dash="dot", line_color="#e67e22", line_width=1,
                annotation_text=ann["description"][:18],
                annotation_font_size=10,
                annotation_position="top left",
            )

    # Kettentrennlinien (horizontale Linie zwischen Ketten)
    chain_boundaries = []
    current_chain = derivations[0][2]
    for idx, (_, _, chain_name) in enumerate(derivations):
        if chain_name != current_chain:
            chain_boundaries.append(idx)
            current_chain = chain_name

    for boundary_idx in chain_boundaries:
        boundary_y = ((n - boundary_idx) * spacing + (n - boundary_idx - 1) * spacing) / 2
        fig_eeg.add_hline(y=boundary_y, line_dash="dot", line_color="#dddddd", line_width=1)

    fig_eeg.update_layout(
        xaxis_title="Zeit (s)",
        yaxis=dict(
            tickvals=[(n - 1 - i) * spacing for i in range(n)],
            ticktext=[label for label, _, _ in derivations],
            showgrid=False,
            tickfont=dict(size=11),
        ),
        height=max(500, n * 55),
        margin=dict(t=30, b=50, l=130, r=20),
        legend=dict(orientation="h", y=-0.07, x=0),
        plot_bgcolor="#fafafa",
    )
    st.plotly_chart(fig_eeg, use_container_width=True)

    # Legende der Ketten
    with st.expander("Ketten-Erklärung"):
        ketten_info = {
            "Temporalreihe links": "Fp1→F7→T3→T5→O1 — Außenreihe links, erfasst temporalen und frontopolaren Kortex",
            "Temporalreihe rechts": "Fp2→F8→T4→T6→O2 — Außenreihe rechts",
            "Parasagittalreihe links": "Fp1→F3→C3→P3→O1 — Innenreihe links, erfasst parasagittalen Kortex",
            "Parasagittalreihe rechts": "Fp2→F4→C4→P4→O2 — Innenreihe rechts",
            "Mittellinie": "Fz→Cz→Pz — Medianer Längsschnitt",
        }
        for name, desc in ketten_info.items():
            if name in montage["ketten"]:
                st.markdown(f"**{name}**: {desc}")

# ═══════════════════════════════════════════════════════════════════════════
# TAB 4 — VITALPARAMETER
# ═══════════════════════════════════════════════════════════════════════════
with tab_vitals:
    st.subheader("Vitalparameter")

    if not groups["vitals"]:
        st.info("Keine Vitalparameter-Kanäle gefunden.")
    else:
        fig_vitals = make_subplots(
            rows=len(groups["vitals"]), cols=1,
            shared_xaxes=True,
            subplot_titles=groups["vitals"],
            vertical_spacing=0.08,
        )
        colors = ["#2ecc71", "#e67e22", "#3498db", "#9b59b6"]
        for idx, ch in enumerate(groups["vitals"]):
            d, _ = raw[[raw.ch_names.index(ch)], :]
            t = raw.times
            fig_vitals.add_trace(
                go.Scatter(x=t, y=d[0], mode="lines", name=ch,
                           line=dict(color=colors[idx % len(colors)], width=1)),
                row=idx + 1, col=1,
            )
        fig_vitals.update_xaxes(title_text="Zeit (s)", row=len(groups["vitals"]), col=1)
        fig_vitals.update_layout(height=250 * len(groups["vitals"]), showlegend=False, margin=dict(t=40, b=40))
        st.plotly_chart(fig_vitals, use_container_width=True)
