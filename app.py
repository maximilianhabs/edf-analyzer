"""EDF Analyzer — lokale Streamlit-App."""

import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import sys, os

sys.path.insert(0, os.path.dirname(__file__))
from core.loader import load_edf, check_privacy, get_channel_groups, extract_channel, get_annotations

st.set_page_config(page_title="EDF Analyzer", layout="wide", page_icon="🧠")

# ── DGKN-Montagen ────────────────────────────────────────────────────────────
DGKN_MONTAGES = {
    "Bipolar Temporal": {
        "beschreibung": "Temporalreihe li + re — Außenreihe der Doppelten Banane (DGKN)",
        "ketten": {
            "Temporalreihe links":  [("Fp1","F7"),("F7","T3"),("T3","T5"),("T5","O1")],
            "Temporalreihe rechts": [("Fp2","F8"),("F8","T4"),("T4","T6"),("T6","O2")],
        },
    },
    "Bipolar Parasagittal": {
        "beschreibung": "Parasagittalreihe li + re — Innenreihe der Doppelten Banane (DGKN)",
        "ketten": {
            "Parasagittalreihe links":  [("Fp1","F3"),("F3","C3"),("C3","P3"),("P3","O1")],
            "Parasagittalreihe rechts": [("Fp2","F4"),("F4","C4"),("C4","P4"),("P4","O2")],
        },
    },
    "Doppelte Banane (komplett)": {
        "beschreibung": "Vollständige bipolare Längsreihe nach DGKN",
        "ketten": {
            "Temporalreihe links":      [("Fp1","F7"),("F7","T3"),("T3","T5"),("T5","O1")],
            "Parasagittalreihe links":  [("Fp1","F3"),("F3","C3"),("C3","P3"),("P3","O1")],
            "Mittellinie":              [("Fz","Cz"),("Cz","Pz")],
            "Parasagittalreihe rechts": [("Fp2","F4"),("F4","C4"),("C4","P4"),("P4","O2")],
            "Temporalreihe rechts":     [("Fp2","F8"),("F8","T4"),("T4","T6"),("T6","O2")],
        },
    },
    "Referenziell Cz": {
        "beschreibung": "Alle Elektroden gegen Cz (referenzielle Ableitung nach DGKN)",
        "ketten": {
            "Links temporal":      [("Fp1","Cz"),("F7","Cz"),("T3","Cz"),("T5","Cz"),("O1","Cz")],
            "Links parasagittal":  [("F3","Cz"),("C3","Cz"),("P3","Cz")],
            "Rechts parasagittal": [("F4","Cz"),("C4","Cz"),("P4","Cz")],
            "Rechts temporal":     [("Fp2","Cz"),("F8","Cz"),("T4","Cz"),("T6","Cz"),("O2","Cz")],
        },
    },
}

CHAIN_COLORS = ["#1a3a5c", "#1a5276", "#7b241c", "#1e6b3a", "#5b2c6f", "#784212"]


def get_eeg_signal(raw, electrode):
    for ch in raw.ch_names:
        if ch.startswith("EEG") and electrode in ch:
            idx = raw.ch_names.index(ch)
            d, _ = raw[[idx], :]
            return d[0]
    return None


def bipolar_derivations(raw, montage_def):
    """Return list of (label, signal_µV, chain_name) for a montage."""
    result = []
    for chain_name, pairs in montage_def["ketten"].items():
        for anode, cathode in pairs:
            sa = get_eeg_signal(raw, anode)
            sb = get_eeg_signal(raw, cathode)
            if sa is not None and sb is not None:
                result.append((f"{anode}–{cathode}", (sa - sb) * 1e6, chain_name))
            else:
                result.append((f"{anode}–{cathode} (?)", None, chain_name))
    return result


def plot_epoch(derivations, i_s, i_e, sfreq, spacing_uv, annotations, t_offset=0):
    """Build EEG epoch figure. Returns plotly Figure."""
    t = np.arange(i_s, i_e) / sfreq
    n = len(derivations)
    chain_names = []
    for _, _, c in derivations:
        if c not in chain_names:
            chain_names.append(c)

    fig = go.Figure()
    seen_chains = set()
    for idx, (label, sig, chain_name) in enumerate(derivations):
        offset = (n - 1 - idx) * spacing_uv
        color = CHAIN_COLORS[chain_names.index(chain_name) % len(CHAIN_COLORS)]
        show_leg = chain_name not in seen_chains
        seen_chains.add(chain_name)
        if sig is not None:
            seg = sig[i_s:i_e]
            fig.add_trace(go.Scatter(
                x=t, y=seg + offset,
                mode="lines", name=chain_name,
                legendgroup=chain_name, showlegend=show_leg,
                line=dict(width=0.9, color=color),
                hovertemplate=f"<b>{label}</b>: %{{customdata:.1f}} µV<extra></extra>",
                customdata=seg,
            ))
        else:
            fig.add_trace(go.Scatter(
                x=[t[0], t[-1]], y=[offset, offset],
                mode="lines", line=dict(width=0.5, color="#ccc", dash="dot"),
                showlegend=False, hoverinfo="skip",
            ))

    # Kettentrennlinien
    prev_chain = derivations[0][2]
    for idx, (_, _, chain_name) in enumerate(derivations[1:], 1):
        if chain_name != prev_chain:
            y_sep = ((n - idx) * spacing_uv + (n - idx - 1) * spacing_uv) / 2 + spacing_uv / 2
            fig.add_hline(y=y_sep, line_dash="dot", line_color="#ddd", line_width=1)
            prev_chain = chain_name

    # Annotations
    for ann in annotations:
        onset = float(ann["onset_s"])
        if i_s / sfreq <= onset <= i_e / sfreq:
            fig.add_vline(x=onset, line_dash="dot", line_color="#e67e22", line_width=1,
                          annotation_text=ann["description"][:20],
                          annotation_font_size=9, annotation_position="top left")

    fig.update_layout(
        xaxis=dict(title="Zeit (s)", range=[t[0], t[-1]], showgrid=True,
                   gridcolor="#eeeeee", dtick=1),
        yaxis=dict(
            tickvals=[(n - 1 - i) * spacing_uv for i in range(n)],
            ticktext=[label for label, _, _ in derivations],
            showgrid=False, tickfont=dict(size=11),
        ),
        height=max(500, n * 52),
        margin=dict(t=10, b=50, l=130, r=10),
        legend=dict(orientation="h", y=-0.08, x=0),
        plot_bgcolor="#fafafa",
    )
    return fig


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("📂 Datei laden")
    edf_path = st.text_input("Pfad zur EDF-Datei",
                              value=os.path.expanduser("~/Downloads/CA177317.edf"))
    load_btn = st.button("Laden", type="primary", use_container_width=True)
    st.divider()
    st.caption("⚠️ Läuft nur lokal. Keine Datenübertragung.")

# ── Session State Init ────────────────────────────────────────────────────────
for key, default in [("raw", None), ("epoch_eeg", 0), ("epoch_ecg", 0)]:
    if key not in st.session_state:
        st.session_state[key] = default

if load_btn or (st.session_state.raw is None and os.path.exists(edf_path)):
    with st.spinner("Lade EDF..."):
        try:
            st.session_state.raw = load_edf(edf_path, preload=True)
            st.session_state.privacy = check_privacy(edf_path)
            st.session_state.epoch_eeg = 0
            st.session_state.epoch_ecg = 0
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
sfreq = raw.info["sfreq"]
total_duration = raw.times[-1]
EPOCH_SEC = 10
n_epochs = int(total_duration // EPOCH_SEC)

if privacy["has_patient_id"] or privacy["has_recording_id"]:
    st.warning("⚠️ **Patientendaten im Header.** Nur lokal verwenden — nicht weiterleiten.", icon="🔒")

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_eeg, tab_ecg, tab_report = st.tabs(["🧠 EEG", "❤️ EKG", "📋 Datei-Report"])


# ═══════════════════════════════════════════════════════════════════════════
# TAB EEG — Epoch-Viewer
# ═══════════════════════════════════════════════════════════════════════════
with tab_eeg:
    # Montage + Skalierung
    col_mont, col_amp = st.columns([3, 1])
    with col_mont:
        montage_name = st.selectbox("Montage", list(DGKN_MONTAGES.keys()), index=2,
                                    help="Bipolare Montagen nach DGKN-Standard")
        st.caption(f"ℹ️ {DGKN_MONTAGES[montage_name]['beschreibung']}")
    with col_amp:
        spacing_uv = st.number_input("Skalierung (µV)", min_value=20, max_value=500,
                                      value=150, step=10,
                                      help="Vertikaler Abstand zwischen Spuren in µV")

    # Epoch-Navigation
    epoch_eeg = st.session_state.epoch_eeg
    t_s = epoch_eeg * EPOCH_SEC
    t_e = t_s + EPOCH_SEC

    col_prev, col_info, col_next = st.columns([1, 4, 1])
    with col_prev:
        if st.button("◀ Zurück", disabled=(epoch_eeg == 0), use_container_width=True, key="eeg_prev"):
            st.session_state.epoch_eeg -= 1
            st.rerun()
    with col_info:
        st.markdown(
            f"<div style='text-align:center; padding:6px; font-size:14px;'>"
            f"Epoche <b>{epoch_eeg + 1}</b> / {n_epochs} &nbsp;|&nbsp; "
            f"{t_s:.0f}s – {t_e:.0f}s &nbsp;|&nbsp; "
            f"Gesamt: {total_duration/60:.1f} min</div>",
            unsafe_allow_html=True,
        )
    with col_next:
        if st.button("Weiter ▶", disabled=(epoch_eeg >= n_epochs - 1), use_container_width=True, key="eeg_next"):
            st.session_state.epoch_eeg += 1
            st.rerun()

    # Sprung zu Epoch
    jump = st.number_input("Springe zu Epoche", min_value=1, max_value=n_epochs,
                            value=epoch_eeg + 1, step=1, key="eeg_jump",
                            label_visibility="collapsed")
    if jump - 1 != epoch_eeg:
        st.session_state.epoch_eeg = jump - 1
        st.rerun()

    # Plot
    montage_def = DGKN_MONTAGES[montage_name]
    derivs = bipolar_derivations(raw, montage_def)
    i_s = int(t_s * sfreq)
    i_e = int(t_e * sfreq)
    fig = plot_epoch(derivs, i_s, i_e, sfreq, spacing_uv, annotations)
    st.plotly_chart(fig, use_container_width=True)

    # Annotations in dieser Epoche
    epoch_anns = [a for a in annotations if t_s <= float(a["onset_s"]) <= t_e]
    if epoch_anns:
        st.caption("Annotations in dieser Epoche: " +
                   " | ".join(f"{a['onset_s']:.1f}s: {a['description']}" for a in epoch_anns))


# ═══════════════════════════════════════════════════════════════════════════
# TAB EKG — Epoch-Viewer (Rohdaten, kein Peak-Overlay)
# ═══════════════════════════════════════════════════════════════════════════
with tab_ecg:
    col_ch, col_filt = st.columns([2, 2])
    with col_ch:
        if groups["ecg"]:
            ecg_ch = st.selectbox("EKG-Kanal", groups["ecg"], index=0)
        else:
            st.warning("Kein EKG-Kanal gefunden.")
            st.stop()
    with col_filt:
        apply_filter = st.checkbox("Hochpass 0.5 Hz (Baseline-Drift entfernen)", value=True,
                                    help="Entfernt DC-Offset und langsame Drifts. Kein Einfluss auf die Herzform.")

    epoch_ecg = st.session_state.epoch_ecg
    t_s_ecg = epoch_ecg * EPOCH_SEC
    t_e_ecg = t_s_ecg + EPOCH_SEC

    col_prev2, col_info2, col_next2 = st.columns([1, 4, 1])
    with col_prev2:
        if st.button("◀ Zurück", disabled=(epoch_ecg == 0), use_container_width=True, key="ecg_prev"):
            st.session_state.epoch_ecg -= 1
            st.rerun()
    with col_info2:
        st.markdown(
            f"<div style='text-align:center; padding:6px; font-size:14px;'>"
            f"Epoche <b>{epoch_ecg + 1}</b> / {n_epochs} &nbsp;|&nbsp; "
            f"{t_s_ecg:.0f}s – {t_e_ecg:.0f}s</div>",
            unsafe_allow_html=True,
        )
    with col_next2:
        if st.button("Weiter ▶", disabled=(epoch_ecg >= n_epochs - 1), use_container_width=True, key="ecg_next"):
            st.session_state.epoch_ecg += 1
            st.rerun()

    jump_ecg = st.number_input("Springe zu Epoche", min_value=1, max_value=n_epochs,
                                value=epoch_ecg + 1, step=1, key="ecg_jump",
                                label_visibility="collapsed")
    if jump_ecg - 1 != epoch_ecg:
        st.session_state.epoch_ecg = jump_ecg - 1
        st.rerun()

    # Signal laden
    signal_raw, _ = extract_channel(raw, ecg_ch)
    i_s_ecg = int(t_s_ecg * sfreq)
    i_e_ecg = int(t_e_ecg * sfreq)
    t_ecg = np.arange(i_s_ecg, i_e_ecg) / sfreq

    seg = signal_raw[i_s_ecg:i_e_ecg].copy()

    if apply_filter:
        from scipy.signal import butter, filtfilt
        nyq = sfreq / 2
        b, a = butter(4, [0.5 / nyq, min(40.0 / nyq, 0.99)], btype="band")
        seg = filtfilt(b, a, seg)
    else:
        seg = seg - np.mean(seg)  # nur DC-Offset entfernen

    seg_mv = seg * 1e3  # V → mV

    fig_ecg = go.Figure()
    fig_ecg.add_trace(go.Scatter(
        x=t_ecg, y=seg_mv,
        mode="lines",
        name=ecg_ch,
        line=dict(color="#c0392b", width=1.2),
        hovertemplate="%{y:.3f} mV<extra></extra>",
    ))

    # EKG-spezifisches Layout: 1s-Raster (Großkästchen) + 0.2s-Raster (Kleinkästchen)
    fig_ecg.update_layout(
        xaxis=dict(
            title="Zeit (s)",
            range=[t_ecg[0], t_ecg[-1]],
            showgrid=True, gridcolor="#f5a9a9", gridwidth=0.5, dtick=0.2,
            minor=dict(showgrid=True, gridcolor="#fce4e4", gridwidth=0.3, dtick=0.04),
        ),
        yaxis=dict(
            title="Amplitude (mV)",
            showgrid=True, gridcolor="#f5a9a9", gridwidth=0.5, dtick=0.5,
            minor=dict(showgrid=True, gridcolor="#fce4e4", gridwidth=0.3, dtick=0.1),
            zeroline=True, zerolinecolor="#cc0000", zerolinewidth=0.8,
        ),
        height=420,
        margin=dict(t=10, b=50, l=70, r=10),
        plot_bgcolor="#fff8f8",
        showlegend=False,
    )
    st.plotly_chart(fig_ecg, use_container_width=True)

    # Rohwert-Info
    amp_pp = seg_mv.max() - seg_mv.min()
    st.caption(
        f"Kanal: **{ecg_ch}** | "
        f"Amplitude peak-peak: **{amp_pp:.2f} mV** | "
        f"Filter: {'0.5–40 Hz Bandpass' if apply_filter else 'nur DC-Offset entfernt'}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# TAB REPORT
# ═══════════════════════════════════════════════════════════════════════════
with tab_report:
    st.subheader("Aufnahme-Übersicht")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Dauer", f"{total_duration/60:.1f} min")
    c2.metric("Sampling", f"{sfreq:.0f} Hz")
    c3.metric("Kanäle", len(raw.ch_names))
    c4.metric("Epochen (10s)", n_epochs)

    col_l, col_r = st.columns(2)
    with col_l:
        st.markdown("**Kanal-Gruppen**")
        st.dataframe(pd.DataFrame([
            {"Gruppe": "EEG (10-20)", "Anzahl": len(groups["eeg"]),
             "Kanäle": ", ".join(c.replace("EEG ","").replace("-Ref","") for c in groups["eeg"])},
            {"Gruppe": "EKG", "Anzahl": len(groups["ecg"]),
             "Kanäle": ", ".join(groups["ecg"])},
            {"Gruppe": "Vitalparameter", "Anzahl": len(groups["vitals"]),
             "Kanäle": ", ".join(groups["vitals"])},
            {"Gruppe": "Sonstige", "Anzahl": len(groups["other"]),
             "Kanäle": ", ".join(groups["other"][:6]) + ("…" if len(groups["other"]) > 6 else "")},
        ]), hide_index=True, use_container_width=True)

        st.markdown("**Datenschutz**")
        st.dataframe(pd.DataFrame([
            {"Feld": "Patient-ID im Header", "Status": "⚠️ vorhanden" if privacy["has_patient_id"] else "✅ leer"},
            {"Feld": "Recording-ID im Header", "Status": "⚠️ vorhanden" if privacy["has_recording_id"] else "✅ leer"},
            {"Feld": "Format", "Status": "EDF+D (discontinuous)"},
            {"Feld": "Encoding", "Status": "latin1 (NeuroFax)"},
        ]), hide_index=True, use_container_width=True)

    with col_r:
        st.markdown("**Klinische Annotations**")
        if annotations:
            df_ann = pd.DataFrame([
                {"Zeit (s)": f"{a['onset_s']:.1f}", "Ereignis": a["description"]}
                for a in annotations
            ])
            st.dataframe(df_ann, hide_index=True, use_container_width=True, height=420)

    with st.expander("Alle Kanäle mit Signalqualität"):
        ch_data = []
        for i, ch in enumerate(raw.ch_names):
            d, _ = raw[[i], :]
            unit_factor = 1e6 if ch.startswith("EEG") else 1e3
            unit = "µV" if ch.startswith("EEG") else "mV"
            vals = d[0] * unit_factor
            vals_demean = vals - vals.mean()
            ch_data.append({
                "Nr": i, "Kanal": ch,
                f"Min ({unit})": f"{vals_demean.min():.1f}",
                f"Max ({unit})": f"{vals_demean.max():.1f}",
                f"RMS ({unit})": f"{np.sqrt(np.mean(vals_demean**2)):.1f}",
            })
        st.dataframe(pd.DataFrame(ch_data), hide_index=True, use_container_width=True)
