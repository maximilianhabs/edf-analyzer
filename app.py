"""EDF Analyzer — lokale Streamlit-App. Epoch-Viewer mit DGKN-Montagen."""

import streamlit as st
import numpy as np
import plotly.graph_objects as go
import pandas as pd
import sys, os, warnings

sys.path.insert(0, os.path.dirname(__file__))
warnings.filterwarnings("ignore")

st.set_page_config(page_title="EDF Analyzer", layout="wide", page_icon="🧠")

# ── Farben: Rechts = Rot, Links = Blau, Mittellinie = Grün ────────────────────
C_RE   = "#c0392b"   # rechts — rot
C_LI   = "#1a5276"   # links  — blau
C_MID  = "#1e8449"   # Mitte  — grün
C_REF  = "#6c3483"   # referenziell — lila

# Kette: (Name, Farbe) pro Elektrodenpaar
CHAIN_OF = {
    # Temporal rechts
    ("Fp2","F8"):("Temporal re", C_RE), ("F8","T4"):("Temporal re", C_RE),
    ("T4","T6"):("Temporal re", C_RE),  ("T6","O2"):("Temporal re", C_RE),
    # Temporal links
    ("Fp1","F7"):("Temporal li", C_LI), ("F7","T3"):("Temporal li", C_LI),
    ("T3","T5"):("Temporal li", C_LI),  ("T5","O1"):("Temporal li", C_LI),
    # Parasagittal rechts
    ("Fp2","F4"):("Parasagittal re", C_RE), ("F4","C4"):("Parasagittal re", C_RE),
    ("C4","P4"):("Parasagittal re", C_RE),  ("P4","O2"):("Parasagittal re", C_RE),
    # Parasagittal links
    ("Fp1","F3"):("Parasagittal li", C_LI), ("F3","C3"):("Parasagittal li", C_LI),
    ("C3","P3"):("Parasagittal li", C_LI),  ("P3","O1"):("Parasagittal li", C_LI),
    # Mittellinie
    ("Fz","Cz"):("Mittellinie", C_MID), ("Cz","Pz"):("Mittellinie", C_MID),
    # Referenziell Cz (links=blau, rechts=rot)
    ("Fp1","Cz"):("Links temporal", C_LI), ("F7","Cz"):("Links temporal", C_LI),
    ("T3","Cz"):("Links temporal", C_LI),  ("T5","Cz"):("Links temporal", C_LI),
    ("O1","Cz"):("Links temporal", C_LI),
    ("F3","Cz"):("Links para", C_LI),  ("C3","Cz"):("Links para", C_LI),
    ("P3","Cz"):("Links para", C_LI),
    ("Fz","Cz"):("Mittellinie", C_MID),
    ("F4","Cz"):("Rechts para", C_RE), ("C4","Cz"):("Rechts para", C_RE),
    ("P4","Cz"):("Rechts para", C_RE),
    ("Fp2","Cz"):("Rechts temporal", C_RE), ("F8","Cz"):("Rechts temporal", C_RE),
    ("T4","Cz"):("Rechts temporal", C_RE),  ("T6","Cz"):("Rechts temporal", C_RE),
    ("O2","Cz"):("Rechts temporal", C_RE),
}

# ── DGKN-Montagen — Reihenfolge: re oben, li unten, Mitte zentral ─────────────
MONTAGES = {
    "Doppelte Banane": [
        # Temporal rechts (oben)
        ("Fp2","F8"),("F8","T4"),("T4","T6"),("T6","O2"),
        # Temporal links
        ("Fp1","F7"),("F7","T3"),("T3","T5"),("T5","O1"),
        # Parasagittal rechts
        ("Fp2","F4"),("F4","C4"),("C4","P4"),("P4","O2"),
        # Parasagittal links
        ("Fp1","F3"),("F3","C3"),("C3","P3"),("P3","O1"),
        # Mittellinie (unten)
        ("Fz","Cz"),("Cz","Pz"),
    ],
    "Temporal": [
        ("Fp2","F8"),("F8","T4"),("T4","T6"),("T6","O2"),
        ("Fp1","F7"),("F7","T3"),("T3","T5"),("T5","O1"),
    ],
    "Parasagittal": [
        ("Fp2","F4"),("F4","C4"),("C4","P4"),("P4","O2"),
        ("Fp1","F3"),("F3","C3"),("C3","P3"),("P3","O1"),
    ],
    "Referenziell Cz": [
        ("Fp1","Cz"),("F7","Cz"),("T3","Cz"),("T5","Cz"),("O1","Cz"),
        ("F3","Cz"),("C3","Cz"),("P3","Cz"),
        ("Fz","Cz"),
        ("F4","Cz"),("C4","Cz"),("P4","Cz"),
        ("Fp2","Cz"),("F8","Cz"),("T4","Cz"),("T6","Cz"),("O2","Cz"),
    ],
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

    # ECG-Kanal-Erkennung: dynamisch via Signal-Qualitätsprüfung
    # $A1/$A2 sind in NeuroFax gesättigte Kalibrierkanäle (nur 2 Digitalwerte) — kein EKG
    # Echtes EKG typisch in POL X1-X7: analog, pp > 0.3 mV, rate 40-150 bpm
    def _is_ecg_candidate(sig_raw, fs):
        """Prüft ob ein Kanal EKG-typische Eigenschaften hat."""
        seg = sig_raw[int(60*fs):int(120*fs)].copy().astype(np.float64)
        seg -= seg.mean()
        n_unique = len(np.unique(np.round(seg * 1e5)))
        if n_unique < 20:
            return False  # gesättigt/digital
        pp = (seg.max() - seg.min()) * 1000  # mV
        if pp < 0.3 or pp > 50:
            return False
        from scipy.signal import find_peaks
        from scipy.signal import butter as _b, filtfilt as _f
        nyq = fs / 2
        bb, aa = _b(4, [0.5/nyq, min(40/nyq, 0.99)], btype='band')
        seg_f = _f(bb, aa, seg)
        thresh = np.percentile(np.abs(seg_f), 85)
        peaks, _ = find_peaks(seg_f, height=thresh, distance=int(fs*0.4))
        rate = len(peaks) / 60.0 * 60
        return 35 < rate < 160

    ecg_channels = []
    for ch in ch_names:
        if ch.startswith("EEG") or ch == "EDF Annotations":
            continue
        if _is_ecg_candidate(data[ch_idx[ch]], sfreq):
            ecg_channels.append(ch)

    # Bandpass-Filter für alle ECG-Kandidaten
    ecg_filtered = {}
    nyq = sfreq / 2
    b, a = butter(4, [0.5 / nyq, min(40.0 / nyq, 0.99)], btype="band")
    for ch in ecg_channels:
        idx = ch_idx[ch]
        sig = data[idx].copy().astype(np.float64)
        sig -= sig.mean()
        sig = filtfilt(b, a, sig)
        ecg_filtered[ch] = sig

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
    """EEG-Plot mit Kettenspacern zwischen Gruppen."""
    # Kettenstruktur analysieren: Gruppenübergänge bestimmen
    GAP = spacing * 1.2   # Leerraum zwischen Ketten (größer als normaler Spurabstand)

    # Offsets vorberechnen: von unten nach oben, Spacer an Kettengrenzen
    offsets = []
    y = 0.0
    prev_chain = derivs[-1][2]
    for label, seg, chain, color in reversed(derivs):
        if chain != prev_chain:
            y += GAP           # Kettenspacer
        offsets.insert(0, y)
        y += spacing
        prev_chain = chain
    total_height = y

    seen = set()
    fig = go.Figure()

    for idx, (label, seg, chain, color) in enumerate(derivs):
        offset = offsets[idx]
        show_leg = chain not in seen; seen.add(chain)
        if seg is not None:
            fig.add_trace(go.Scatter(
                x=t, y=seg + offset, mode="lines",
                name=chain, legendgroup=chain, showlegend=show_leg,
                line=dict(width=0.9, color=color),
                hovertemplate=f"<b>{label}</b>: %{{customdata:.1f}} µV<extra></extra>",
                customdata=seg,
            ))
        else:
            fig.add_trace(go.Scatter(
                x=[t[0], t[-1]], y=[offset, offset], mode="lines",
                line=dict(width=0.5, color="#ccc", dash="dot"),
                showlegend=False, hoverinfo="skip",
            ))

    # Trennlinie zwischen Ketten (mittig im Spacer)
    prev_chain = derivs[0][2]
    for i, (_, _, chain, _) in enumerate(derivs[1:], 1):
        if chain != prev_chain:
            sep_y = (offsets[i - 1] + offsets[i]) / 2
            fig.add_hline(y=sep_y, line_dash="dot", line_color="#cccccc", line_width=1)
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
            range=[-spacing * 0.8, total_height + spacing * 0.3],
            tickvals=offsets,
            ticktext=[lbl for lbl, _, _, _ in derivs],
            showgrid=False, tickfont=dict(size=10),
        ),
        height=max(500, int(total_height / spacing) * 42 + 80),
        margin=dict(t=8, b=48, l=120, r=8),
        legend=dict(orientation="h", y=-0.06, x=0, font=dict(size=11)),
        plot_bgcolor="#f9f9f9",
    )
    return fig


def ecg_figure(t, sig_mv, sensitivity_mv, lp_hz=None):
    """EKG-Plot. sensitivity_mv = sichtbarer ±-Bereich der y-Achse in mV."""
    sig_plot = sig_mv.copy()

    # Optionaler Tiefpass für glattere Darstellung
    if lp_hz is not None:
        from scipy.signal import butter, filtfilt
        sfreq = 1.0 / (t[1] - t[0])
        nyq = sfreq / 2
        b, a = butter(4, min(lp_hz / nyq, 0.98), btype="low")
        sig_plot = filtfilt(b, a, sig_plot)

    # Baseline: Median des Segments als Nulllinie
    baseline = np.median(sig_plot)
    sig_centered = sig_plot - baseline

    y_min, y_max = -sensitivity_mv, sensitivity_mv

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=t, y=sig_centered, mode="lines",
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
            showgrid=True, gridcolor="#f5c6c6", gridwidth=0.8, dtick=sensitivity_mv / 4,
            zeroline=True, zerolinecolor="#999999", zerolinewidth=0.8,
        ),
        height=420,
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
        # Steuerelemente
        col_ch, col_sens, col_lp = st.columns([2, 2, 2])
        ecg_ch = col_ch.selectbox("Kanal", ecg_channels, index=0)
        sensitivity_mv = col_sens.select_slider(
            "Sensitivität (±mV Anzeigebereich)",
            options=[0.3, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0, 10.0],
            value=1.0,
            help="±1 mV = Standard-EKG (10 mm/mV). Anpassen falls Signal abgeschnitten."
        )
        lp_options = {"Kein Tiefpass (Rohdaten)": None, "25 Hz": 25, "15 Hz": 15, "10 Hz": 10}
        lp_label = col_lp.selectbox("Tiefpass-Filter", list(lp_options.keys()), index=1,
                                     help="Glättet die Kurve — kein Einfluss auf Herzrhythmus")
        lp_hz = lp_options[lp_label]

        ep_ecg = epoch_nav("ep_ecg", "EKG")
        t_s_ecg = ep_ecg * EPOCH_SEC
        i_s_ecg = int(t_s_ecg * sfreq)
        i_e_ecg = int((t_s_ecg + EPOCH_SEC) * sfreq)
        t_ecg = np.arange(i_s_ecg, i_e_ecg) / sfreq

        sig = edf["ecg_filtered"][ecg_ch][i_s_ecg:i_e_ecg]
        sig_mv = sig * 1000   # V → mV

        fig_ecg = ecg_figure(t_ecg, sig_mv, sensitivity_mv, lp_hz)
        st.plotly_chart(fig_ecg, use_container_width=True)

        # Signal-Info
        sig_centered = sig_mv - np.median(sig_mv)
        pp = sig_centered.max() - sig_centered.min()
        rms = np.sqrt(np.mean(sig_centered**2))
        st.caption(
            f"Kanal: **{ecg_ch}** | peak-peak: **{pp:.2f} mV** | "
            f"RMS: {rms:.2f} mV | Vorfilter: 0.5–40 Hz | Anzeige: ±{sensitivity_mv} mV"
        )

        # ── RR-Analyse ────────────────────────────────────────────────────────
        st.divider()
        st.subheader("RR-Analyse (Gesamtaufnahme)")

        from scipy.signal import find_peaks as _fp

        @st.cache_data(show_spinner="Berechne R-Peaks…")
        def compute_rr(path, channel):
            """R-Peak-Erkennung auf gefiltertem Gesamtsignal."""
            from core.loader import load_edf
            import warnings; warnings.filterwarnings("ignore")
            _raw = load_edf(path, preload=True)
            _data, _ = _raw[:]
            _idx = _raw.ch_names.index(channel)
            sig = _data[_idx].copy().astype(np.float64)
            sig -= sig.mean()
            from scipy.signal import butter, filtfilt
            nyq = _raw.info["sfreq"] / 2
            b, a = butter(4, [0.5/nyq, min(40/nyq, 0.99)], btype="band")
            sig_f = filtfilt(b, a, sig)
            fs = _raw.info["sfreq"]

            # ── Robuste R-Peak-Erkennung auf Absolutbetrag ──────────────────
            # Strategie: |Signal| → nur die dominanten Spitzen zählen,
            # egal ob die Ableitung positiv oder negativ gepoolt ist.
            # Schwelle = 50 % des 98. Perzentils des |Signals|
            # → kleine Bumps (<50 % des typischen R-Peaks) werden ignoriert.
            abs_sig = np.abs(sig_f)
            peak_ref = np.percentile(abs_sig, 98)    # typische R-Peak-Höhe
            threshold = peak_ref * 0.50              # 50 % davon als Trigger
            min_dist = int(fs * 0.35)                # Refraktärzeit 350 ms → max ~170 bpm

            peaks, _ = _fp(abs_sig, height=threshold, distance=min_dist)

            # Polarität: war der ursprüngliche Peak positiv oder negativ?
            polarities = np.sign(sig_f[peaks])

            # ── Stufe 1: Harte physiologische Grenzen ───────────────────────
            rr = np.diff(peaks) / fs * 1000
            mask1 = (rr > 300) & (rr < 2000)

            # ── Stufe 2: Hampel-Filter — lokale Ausreißer ───────────────────
            # Für jedes RR: Median + MAD der ±5 Nachbarn berechnen.
            # Abweichung > 3 × MAD → Artefakt / Ausreißer.
            # MAD-Schätzung des lokalen Sigma: sigma ≈ 1.4826 × MAD
            def hampel(rr_arr, half_win=5, k=3.0):
                n = len(rr_arr)
                outlier = np.zeros(n, dtype=bool)
                for i in range(n):
                    lo = max(0, i - half_win)
                    hi = min(n, i + half_win + 1)
                    window = rr_arr[lo:hi]
                    med = np.median(window)
                    mad = np.median(np.abs(window - med))
                    sigma = 1.4826 * mad
                    if sigma > 0 and abs(rr_arr[i] - med) > k * sigma:
                        outlier[i] = True
                return ~outlier   # True = behalten

            rr_stage1 = rr[mask1]
            mask2_local = hampel(rr_stage1, half_win=5, k=3.0)

            # ── Stufe 3: Globaler Kontext-Check ─────────────────────────────
            # Median-HR der gesamten Aufnahme als Referenz.
            # RR > 2.5× oder < 0.4× des globalen Medians → Artefakt.
            if len(rr_stage1) > 10:
                global_median = np.median(rr_stage1[mask2_local] if mask2_local.any() else rr_stage1)
                mask3 = (rr_stage1 > global_median * 0.4) & (rr_stage1 < global_median * 2.5)
            else:
                mask3 = np.ones(len(rr_stage1), dtype=bool)

            final_mask = mask2_local & mask3

            # Ergebnis zusammenstellen
            peaks_s1     = peaks[:-1][mask1]
            rr_clean     = rr_stage1[final_mask]
            peaks_clean  = peaks_s1[final_mask]
            n_removed    = int((~final_mask).sum())

            return {
                "peaks": peaks,                        # alle erkannten Peaks (für Overlay)
                "peaks_valid": peaks_clean,
                "polarities": polarities,
                "rr_ms": rr_clean,
                "rr_ms_raw": rr_stage1,                # vor Outlier-Filter (für Debug)
                "times": peaks_clean / fs,
                "fs": fs,
                "threshold_mv": threshold * 1000,
                "n_peaks_total": len(peaks),
                "n_removed": n_removed,
            }

        rr_data = compute_rr(edf_path, ecg_ch)
        rr_ms = rr_data["rr_ms"]
        r_times = rr_data["times"]

        if len(rr_ms) < 5:
            st.warning("Zu wenige R-Peaks erkannt. Kanal oder Filter prüfen.")
        else:
            # Outlier-Info
            n_total   = rr_data["n_peaks_total"]
            n_removed = rr_data["n_removed"]
            n_kept    = len(rr_ms)
            if n_removed > 0:
                st.info(
                    f"🔎 Outlier-Filter: **{n_removed} Schläge** entfernt "
                    f"({n_removed/(n_kept+n_removed)*100:.1f} %) — "
                    f"Hampel-Filter (±5 Nachbarn, 3σ) + globaler Kontext-Check (±2.5× Median). "
                    f"Verbleibend: **{n_kept} Schläge**.",
                    icon="ℹ️",
                )

            # HRV-Metriken (nur auf bereinigten RR)
            mean_rr = float(np.mean(rr_ms))
            mean_hr = 60000 / mean_rr
            sdnn    = float(np.std(rr_ms, ddof=1))
            rmssd   = float(np.sqrt(np.mean(np.diff(rr_ms)**2))) if len(rr_ms) > 2 else 0.0
            pnn50   = float(np.sum(np.abs(np.diff(rr_ms)) > 50) / max(len(np.diff(rr_ms)),1) * 100)

            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Mittlere HR", f"{mean_hr:.1f} bpm")
            c2.metric("Mittleres RR", f"{mean_rr:.0f} ms")
            c3.metric("SDNN", f"{sdnn:.1f} ms", help="Gesamtvariabilität — Norm: 20–100 ms")
            c4.metric("RMSSD", f"{rmssd:.1f} ms", help="Kurzzeit-HRV, parasympathisch — Norm: 15–40 ms")
            c5.metric("pNN50", f"{pnn50:.1f} %", help="Anteil aufeinanderfolgender RR-Differenzen >50 ms")

            col_tach, col_poin = st.columns(2)

            with col_tach:
                st.markdown("**Tachogramm — bereinigte RR-Intervalle**")
                fig_rr = go.Figure()
                # Bereinigte Werte
                fig_rr.add_trace(go.Scatter(
                    x=r_times, y=rr_ms, mode="lines+markers",
                    name="RR (bereinigt)",
                    line=dict(color="#2980b9", width=1),
                    marker=dict(size=3, color="#2980b9"),
                    hovertemplate="t=%{x:.1f}s  RR=%{y:.0f}ms<extra></extra>",
                ))
                # Median-Linie
                fig_rr.add_hline(y=mean_rr, line_dash="dot",
                                 line_color="#27ae60", line_width=1,
                                 annotation_text=f"Median {mean_rr:.0f}ms",
                                 annotation_font_size=10)
                # Annotations
                for ann in edf["annotations"]:
                    fig_rr.add_vline(x=ann["onset_s"], line_dash="dot",
                                     line_color="#e67e22", line_width=0.8)
                fig_rr.update_layout(
                    xaxis_title="Zeit (s)", yaxis_title="RR-Intervall (ms)",
                    yaxis=dict(range=[max(0, mean_rr*0.5), mean_rr*1.8]),
                    height=300, margin=dict(t=8, b=40, l=60, r=8),
                    plot_bgcolor="#f9f9f9", showlegend=False,
                )
                st.plotly_chart(fig_rr, use_container_width=True)

            with col_poin:
                st.markdown("**Poincaré-Plot — RR_n vs. RR_(n+1)**")
                fig_poin = go.Figure(go.Scatter(
                    x=rr_ms[:-1], y=rr_ms[1:], mode="markers",
                    marker=dict(color="#8e44ad", size=4, opacity=0.55),
                    hovertemplate="RR_n=%{x:.0f}ms  RR_n+1=%{y:.0f}ms<extra></extra>",
                ))
                # Achsen auf ±30% um Median — Ausreißer werden abgeschnitten, nicht angezeigt
                p_lo = max(300, mean_rr * 0.55)
                p_hi = min(2000, mean_rr * 1.55)
                lim = [p_lo - 30, p_hi + 30]
                fig_poin.update_layout(
                    xaxis=dict(title="RR_n (ms)", range=lim),
                    yaxis=dict(title="RR_(n+1) (ms)", range=lim),
                    height=300, margin=dict(t=8, b=40, l=60, r=8),
                    plot_bgcolor="#f9f9f9",
                )
                st.plotly_chart(fig_poin, use_container_width=True)

            # R-Peak-Overlay in der aktuellen Epoche
            all_peaks = rr_data["peaks"]
            all_pols  = rr_data["polarities"]
            mask = (all_peaks >= i_s_ecg) & (all_peaks < i_e_ecg)
            r_in_epoch = all_peaks[mask]
            r_pols     = all_pols[mask]

            st.markdown(
                f"**Epoche mit R-Peak-Markierung** — "
                f"Triggerschwelle: **±{rr_data['threshold_mv']:.2f} mV** "
                f"(50 % des 98. Perzentils des |Signals|)"
            )
            if len(r_in_epoch) > 0:
                r_t = r_in_epoch / sfreq
                r_v = edf["ecg_filtered"][ecg_ch][r_in_epoch] * 1000
                r_v_centered = r_v - np.median(sig_mv)
                # Dreieck oben bei positiven Peaks, unten bei negativen
                symbols = ["triangle-up" if p > 0 else "triangle-down" for p in r_pols]
                colors  = ["#27ae60" if p > 0 else "#e67e22" for p in r_pols]
                fig_ecg_rr = go.Figure(fig_ecg)
                fig_ecg_rr.add_trace(go.Scatter(
                    x=r_t, y=r_v_centered, mode="markers", name="R-Peaks",
                    marker=dict(symbol=symbols, size=11, color=colors,
                                line=dict(width=1, color="#333")),
                    hovertemplate="R-Peak t=%{x:.3f}s  %{y:.3f} mV<extra></extra>",
                ))
                st.plotly_chart(fig_ecg_rr, use_container_width=True)
            else:
                st.info("Keine R-Peaks in dieser Epoche erkannt.")

            with st.expander("RR-Tabelle (alle Schläge)"):
                df_rr = pd.DataFrame({
                    "Zeit (s)": np.round(r_times, 2),
                    "RR-Intervall (ms)": np.round(rr_ms, 1),
                    "HR (bpm)": np.round(60000 / rr_ms, 1),
                })
                st.dataframe(df_rr, hide_index=True, use_container_width=True, height=300)


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
