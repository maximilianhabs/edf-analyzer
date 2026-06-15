"""EDF Analyzer — lokale Streamlit-App. Epoch-Viewer mit DGKN-Montagen."""

import streamlit as st
import numpy as np
import plotly.graph_objects as go
import pandas as pd
import sys, os, warnings

sys.path.insert(0, os.path.dirname(__file__))
warnings.filterwarnings("ignore")

st.set_page_config(page_title="EDF Analyzer", layout="wide", page_icon="🧠")

# ── DGKN-Montagen ─────────────────────────────────────────────────────────────
MONTAGES = {
    "Doppelte Banane": [
        ("Fp1","F7"),("F7","T3"),("T3","T5"),("T5","O1"),
        ("Fp1","F3"),("F3","C3"),("C3","P3"),("P3","O1"),
        ("Fz","Cz"),("Cz","Pz"),
        ("Fp2","F4"),("F4","C4"),("C4","P4"),("P4","O2"),
        ("Fp2","F8"),("F8","T4"),("T4","T6"),("T6","O2"),
    ],
    "Temporal": [
        ("Fp1","F7"),("F7","T3"),("T3","T5"),("T5","O1"),
        ("Fp2","F8"),("F8","T4"),("T4","T6"),("T6","O2"),
    ],
    "Parasagittal": [
        ("Fp1","F3"),("F3","C3"),("C3","P3"),("P3","O1"),
        ("Fp2","F4"),("F4","C4"),("C4","P4"),("P4","O2"),
    ],
    "Referenziell Cz": [
        ("Fp1","Cz"),("F7","Cz"),("T3","Cz"),("T5","Cz"),("O1","Cz"),
        ("F3","Cz"),("C3","Cz"),("P3","Cz"),
        ("Fz","Cz"),
        ("F4","Cz"),("C4","Cz"),("P4","Cz"),
        ("Fp2","Cz"),("F8","Cz"),("T4","Cz"),("T6","Cz"),("O2","Cz"),
    ],
}

# Kette pro Ableitungspaar für Farbgebung
CHAIN_OF = {
    ("Fp1","F7"):("Temporal li","#1a3a5c"), ("F7","T3"):("Temporal li","#1a3a5c"),
    ("T3","T5"):("Temporal li","#1a3a5c"),  ("T5","O1"):("Temporal li","#1a3a5c"),
    ("Fp1","F3"):("Parasagittal li","#7b241c"), ("F3","C3"):("Parasagittal li","#7b241c"),
    ("C3","P3"):("Parasagittal li","#7b241c"), ("P3","O1"):("Parasagittal li","#7b241c"),
    ("Fz","Cz"):("Mittellinie","#1e6b3a"),  ("Cz","Pz"):("Mittellinie","#1e6b3a"),
    ("Fp2","F4"):("Parasagittal re","#6c3483"), ("F4","C4"):("Parasagittal re","#6c3483"),
    ("C4","P4"):("Parasagittal re","#6c3483"), ("P4","O2"):("Parasagittal re","#6c3483"),
    ("Fp2","F8"):("Temporal re","#0e6655"),  ("F8","T4"):("Temporal re","#0e6655"),
    ("T4","T6"):("Temporal re","#0e6655"),   ("T6","O2"):("Temporal re","#0e6655"),
}

EPOCH_SEC = 10


# ── Daten-Laden + Vorberechnung (einmalig, gecacht) ────────────────────────────
@st.cache_data(show_spinner="Lade und verarbeite EDF…")
def load_and_prepare(path: str):
    """Lädt EDF, extrahiert alle Kanäle als numpy-Matrix, filtert ECG vorab."""
    import mne
    from scipy.signal import butter, filtfilt

    raw = mne.io.read_raw_edf(path, preload=True, verbose=False, encoding="latin1")
    sfreq = raw.info["sfreq"]
    data, _ = raw[:]                          # (n_ch, n_samples) — einmalig!
    ch_names = raw.ch_names
    n_samples = data.shape[1]
    duration_s = n_samples / sfreq

    # Channel-Index-Map
    ch_idx = {ch: i for i, ch in enumerate(ch_names)}

    # EEG-Lookup: Kurzname → Index (z.B. "Fp1" → Index von "EEG Fp1-Ref")
    eeg_map = {}
    for ch in ch_names:
        if ch.startswith("EEG"):
            short = ch.replace("EEG ", "").replace("-Ref", "").strip()
            eeg_map[short] = ch_idx[ch]

    # ECG-Kanäle — einmalig filtern (Bandpass 0.5–40 Hz)
    ecg_channels = [c for c in ch_names if "$A" in c]
    ecg_filtered = {}
    nyq = sfreq / 2
    b, a = butter(4, [0.5 / nyq, min(40.0 / nyq, 0.99)], btype="band")
    for ch in ecg_channels:
        idx = ch_idx[ch]
        sig = data[idx].copy().astype(np.float64)
        sig -= sig.mean()                     # DC-Offset entfernen
        sig = filtfilt(b, a, sig)             # Bandpass auf gesamtem Signal
        ecg_filtered[ch] = sig               # in Volt, nach Filter

    # Privacy
    with open(path, "rb") as f:
        hdr = f.read(256)
    patient_id = hdr[8:88].decode("latin1").strip()
    rec_id = hdr[88:168].decode("latin1").strip()

    # Annotations
    annotations = []
    for ann in raw.annotations:
        desc = ann["description"]
        if "np.str_" in desc:
            desc = desc.replace("np.str_('", "").rstrip("')")
        if desc.startswith("+") and desc[1:].replace(".", "").isdigit():
            continue
        annotations.append({"onset_s": round(float(ann["onset"]), 2), "description": desc})

    return {
        "data": data,
        "ch_names": ch_names,
        "ch_idx": ch_idx,
        "eeg_map": eeg_map,
        "ecg_filtered": ecg_filtered,
        "ecg_channels": ecg_channels,
        "sfreq": sfreq,
        "n_samples": n_samples,
        "duration_s": duration_s,
        "n_epochs": int(duration_s // EPOCH_SEC),
        "annotations": annotations,
        "has_patient_id": bool(patient_id),
        "has_rec_id": bool(rec_id),
    }


def get_bipolar_epoch(d, eeg_map, pairs, i_s, i_e):
    """Berechnet bipolare Ableitungen nur für die Epoche — reine numpy-Ops."""
    result = []
    for anode, cathode in pairs:
        ia, ib = eeg_map.get(anode), eeg_map.get(cathode)
        label = f"{anode}–{cathode}"
        chain, color = CHAIN_OF.get((anode, cathode), ("andere", "#555"))
        if ia is not None and ib is not None:
            seg = (d[ia, i_s:i_e] - d[ib, i_s:i_e]) * 1e6   # V → µV
            result.append((label, seg, chain, color))
        else:
            result.append((label, None, chain, color))
    return result


def eeg_figure(derivs, t, spacing, annotations, t_s, t_e):
    n = len(derivs)
    seen = set()
    fig = go.Figure()

    for idx, (label, seg, chain, color) in enumerate(derivs):
        offset = (n - 1 - idx) * spacing
        show_leg = chain not in seen; seen.add(chain)
        if seg is not None:
            fig.add_trace(go.Scatter(
                x=t, y=seg + offset, mode="lines",
                name=chain, legendgroup=chain, showlegend=show_leg,
                line=dict(width=0.85, color=color),
                hovertemplate=f"<b>{label}</b>: %{{customdata:.1f}} µV<extra></extra>",
                customdata=seg,
            ))
        else:
            fig.add_trace(go.Scatter(
                x=[t[0], t[-1]], y=[offset, offset], mode="lines",
                line=dict(width=0.5, color="#ccc", dash="dot"),
                showlegend=False, hoverinfo="skip",
            ))

    # Kettentrennlinien
    prev_chain = derivs[0][2]
    for i, (_, _, chain, _) in enumerate(derivs[1:], 1):
        if chain != prev_chain:
            sep_y = (n - i) * spacing - spacing * 0.3
            fig.add_hline(y=sep_y, line_dash="dot", line_color="#ddd", line_width=1)
        prev_chain = chain

    # Annotations
    for ann in annotations:
        o = ann["onset_s"]
        if t_s <= o <= t_e:
            fig.add_vline(x=o, line_dash="dot", line_color="#e67e22", line_width=1.2,
                          annotation_text=ann["description"][:22],
                          annotation_font_size=9, annotation_position="top left")

    fig.update_layout(
        xaxis=dict(title="Zeit (s)", range=[t[0], t[-1]],
                   showgrid=True, gridcolor="#ebebeb", dtick=1),
        yaxis=dict(
            tickvals=[(n - 1 - i) * spacing for i in range(n)],
            ticktext=[lbl for lbl, _, _, _ in derivs],
            showgrid=False, tickfont=dict(size=10),
        ),
        height=max(480, n * 50),
        margin=dict(t=8, b=48, l=120, r=8),
        legend=dict(orientation="h", y=-0.07, x=0, font=dict(size=11)),
        plot_bgcolor="#f9f9f9",
    )
    return fig


def ecg_figure(t, sig_mv, t_s, t_e, channel_name):
    # Auto-Scaling: 1. und 99. Perzentil für y-Achse
    p1, p99 = np.percentile(sig_mv, 1), np.percentile(sig_mv, 99)
    margin = (p99 - p1) * 0.3
    y_min, y_max = p1 - margin, p99 + margin

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=t, y=sig_mv, mode="lines",
        line=dict(color="#c0392b", width=1.2),
        hovertemplate="%{y:.3f} mV<extra></extra>",
    ))
    fig.update_layout(
        xaxis=dict(
            title="Zeit (s)", range=[t[0], t[-1]],
            showgrid=True, gridcolor="#f5c6c6", gridwidth=0.8, dtick=0.2,
            minor=dict(showgrid=True, gridcolor="#fce8e8", gridwidth=0.5, dtick=0.04),
        ),
        yaxis=dict(
            title="Amplitude (mV)", range=[y_min, y_max],
            showgrid=True, gridcolor="#f5c6c6", gridwidth=0.8,
            zeroline=True, zerolinecolor="#c0392b", zerolinewidth=0.8,
        ),
        height=400,
        margin=dict(t=8, b=48, l=70, r=8),
        plot_bgcolor="#fff8f8",
        showlegend=False,
    )
    return fig


# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("📂 Datei")
    edf_path = st.text_input("Pfad zur EDF-Datei",
                              value=os.path.expanduser("~/Downloads/CA177317.edf"))
    st.divider()
    st.caption("⚠️ Nur lokal. Keine Datenübertragung.")

# ── Daten laden (gecacht — nur einmal pro Datei-Pfad) ──────────────────────────
if not os.path.exists(edf_path):
    st.info("Bitte gültigen Pfad zur EDF-Datei eingeben.")
    st.stop()

edf = load_and_prepare(edf_path)

if edf["has_patient_id"] or edf["has_rec_id"]:
    st.warning("⚠️ **Patientendaten im Header.** Nur lokal verwenden.", icon="🔒")

# ── Session State für Epoch-Navigation ────────────────────────────────────────
if "ep_eeg" not in st.session_state: st.session_state.ep_eeg = 0
if "ep_ecg" not in st.session_state: st.session_state.ep_ecg = 0

sfreq = edf["sfreq"]
n_epochs = edf["n_epochs"]


def epoch_nav(key, label="EEG"):
    """Rendert Navigationszeile, gibt aktuellen Epochenindex zurück."""
    ep = st.session_state[key]
    t_s = ep * EPOCH_SEC
    t_e = t_s + EPOCH_SEC

    col_p, col_info, col_n = st.columns([1, 5, 1])
    with col_p:
        if st.button("◀", key=f"{key}_prev", disabled=(ep == 0),
                     use_container_width=True):
            st.session_state[key] -= 1
            st.rerun()
    with col_info:
        st.markdown(
            f"<div style='text-align:center;padding:5px 0;font-size:13px'>"
            f"Epoche <b>{ep+1}</b>&nbsp;/&nbsp;{n_epochs}"
            f"&ensp;|&ensp;{t_s:.0f}s – {t_e:.0f}s"
            f"&ensp;|&ensp;Gesamt: {edf['duration_s']/60:.1f} min"
            f"</div>", unsafe_allow_html=True)
    with col_n:
        if st.button("▶", key=f"{key}_next", disabled=(ep >= n_epochs - 1),
                     use_container_width=True):
            st.session_state[key] += 1
            st.rerun()

    new_ep = st.slider(f"Epoche auswählen ({label})", 1, n_epochs, ep + 1,
                       key=f"{key}_slider", label_visibility="collapsed")
    if new_ep - 1 != ep:
        st.session_state[key] = new_ep - 1
        st.rerun()

    return st.session_state[key]


# ── Tabs ───────────────────────────────────────────────────────────────────────
tab_eeg, tab_ecg, tab_report = st.tabs(["🧠 EEG", "❤️ EKG", "📋 Report"])


# ═══════════════ EEG ══════════════════════════════════════════════════════════
with tab_eeg:
    col_m, col_s = st.columns([3, 1])
    montage_name = col_m.selectbox("Montage (DGKN)", list(MONTAGES.keys()), index=0)
    spacing = col_s.number_input("µV / Spur", 20, 600, 150, step=10)

    ep = epoch_nav("ep_eeg", "EEG")
    t_s = ep * EPOCH_SEC
    i_s, i_e = int(t_s * sfreq), int((t_s + EPOCH_SEC) * sfreq)
    t = np.arange(i_s, i_e) / sfreq

    pairs = MONTAGES[montage_name]
    derivs = get_bipolar_epoch(edf["data"], edf["eeg_map"], pairs, i_s, i_e)
    fig = eeg_figure(derivs, t, spacing, edf["annotations"], t_s, t_s + EPOCH_SEC)
    st.plotly_chart(fig, use_container_width=True)

    epoch_anns = [a for a in edf["annotations"] if t_s <= a["onset_s"] <= t_s + EPOCH_SEC]
    if epoch_anns:
        st.caption("Annotations: " + " | ".join(
            f"{a['onset_s']:.1f}s → {a['description']}" for a in epoch_anns))


# ═══════════════ EKG ══════════════════════════════════════════════════════════
with tab_ecg:
    ecg_channels = edf["ecg_channels"]
    if not ecg_channels:
        st.warning("Kein EKG-Kanal gefunden.")
    else:
        ecg_ch = st.selectbox("Kanal", ecg_channels, index=0)
        ep_ecg = epoch_nav("ep_ecg", "EKG")
        t_s_ecg = ep_ecg * EPOCH_SEC
        i_s_ecg = int(t_s_ecg * sfreq)
        i_e_ecg = int((t_s_ecg + EPOCH_SEC) * sfreq)
        t_ecg = np.arange(i_s_ecg, i_e_ecg) / sfreq

        sig = edf["ecg_filtered"][ecg_ch][i_s_ecg:i_e_ecg]
        sig_mv = sig * 1000   # V → mV

        fig_ecg = ecg_figure(t_ecg, sig_mv, t_s_ecg, t_s_ecg + EPOCH_SEC, ecg_ch)
        st.plotly_chart(fig_ecg, use_container_width=True)

        pp = sig_mv.max() - sig_mv.min()
        p5, p95 = np.percentile(sig_mv, 5), np.percentile(sig_mv, 95)
        st.caption(
            f"Kanal: **{ecg_ch}** | peak-peak: **{pp:.2f} mV** | "
            f"5.–95. Perz.: {p5:.2f} – {p95:.2f} mV | "
            f"Filter: Bandpass 0.5–40 Hz (auf Gesamtsignal)"
        )


# ═══════════════ REPORT ═══════════════════════════════════════════════════════
with tab_report:
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
