"""Gemeinsame Konstanten, Cache-Funktionen und Plot-Bausteine für alle App-Seiten."""

import os
import numpy as np
import streamlit as st
import plotly.graph_objects as go

# ── Farben: Rechts = Rot, Links = Blau, Mittellinie = Grün (klinische Bedeutung) ─
C_RE   = "#c0392b"
C_LI   = "#1a5276"
C_MID  = "#1e8449"
C_REF  = "#6c3483"

CHAIN_OF = {
    ("Fp2","F8"):("Temporal re", C_RE), ("F8","T4"):("Temporal re", C_RE),
    ("T4","T6"):("Temporal re", C_RE),  ("T6","O2"):("Temporal re", C_RE),
    ("Fp1","F7"):("Temporal li", C_LI), ("F7","T3"):("Temporal li", C_LI),
    ("T3","T5"):("Temporal li", C_LI),  ("T5","O1"):("Temporal li", C_LI),
    ("Fp2","F4"):("Parasagittal re", C_RE), ("F4","C4"):("Parasagittal re", C_RE),
    ("C4","P4"):("Parasagittal re", C_RE),  ("P4","O2"):("Parasagittal re", C_RE),
    ("Fp1","F3"):("Parasagittal li", C_LI), ("F3","C3"):("Parasagittal li", C_LI),
    ("C3","P3"):("Parasagittal li", C_LI),  ("P3","O1"):("Parasagittal li", C_LI),
    ("Fz","Cz"):("Mittellinie", C_MID), ("Cz","Pz"):("Mittellinie", C_MID),
    ("Fp2","Cz"):("Rechts temporal", C_RE), ("F8","Cz"):("Rechts temporal", C_RE),
    ("T4","Cz"):("Rechts temporal", C_RE),  ("T6","Cz"):("Rechts temporal", C_RE),
    ("O2","Cz"):("Rechts temporal", C_RE),
    ("Fp1","Cz"):("Links temporal", C_LI), ("F7","Cz"):("Links temporal", C_LI),
    ("T3","Cz"):("Links temporal", C_LI),  ("T5","Cz"):("Links temporal", C_LI),
    ("O1","Cz"):("Links temporal", C_LI),
    ("F4","Cz"):("Rechts para", C_RE), ("C4","Cz"):("Rechts para", C_RE),
    ("P4","Cz"):("Rechts para", C_RE),
    ("F3","Cz"):("Links para", C_LI),  ("C3","Cz"):("Links para", C_LI),
    ("P3","Cz"):("Links para", C_LI),
    ("Fz","Cz"):("Mittellinie", C_MID),
    ("Pz","Cz"):("Mittellinie", C_MID),
}

MONTAGES = {
    "Doppelte Banane": [
        ("Fp2","F8"),("F8","T4"),("T4","T6"),("T6","O2"),
        ("Fp1","F7"),("F7","T3"),("T3","T5"),("T5","O1"),
        ("Fp2","F4"),("F4","C4"),("C4","P4"),("P4","O2"),
        ("Fp1","F3"),("F3","C3"),("C3","P3"),("P3","O1"),
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
        ("Fp2","Cz"),("F8","Cz"),("T4","Cz"),("T6","Cz"),("O2","Cz"),
        ("Fp1","Cz"),("F7","Cz"),("T3","Cz"),("T5","Cz"),("O1","Cz"),
        ("F4","Cz"),("C4","Cz"),("P4","Cz"),
        ("F3","Cz"),("C3","Cz"),("P3","Cz"),
        ("Fz","Cz"),("Pz","Cz"),
    ],
}

ELECTRODE_POS = {
    "Fp1": (-0.31, 0.95), "Fp2": (0.31, 0.95),
    "F7": (-0.81, 0.58), "F3": (-0.46, 0.64), "Fz": (0.0, 0.7),
    "F4": (0.46, 0.64),  "F8": (0.81, 0.58),
    "T3": (-0.95, 0.0),  "C3": (-0.5, 0.0), "Cz": (0.0, 0.0),
    "C4": (0.5, 0.0),    "T4": (0.95, 0.0),
    "T5": (-0.81, -0.58), "P3": (-0.46, -0.64), "Pz": (0.0, -0.7),
    "P4": (0.46, -0.64),  "T6": (0.81, -0.58),
    "O1": (-0.31, -0.95), "O2": (0.31, -0.95),
}

EPOCH_SEC = 10  # Standard-Epochenlänge (EKG-Tab, Fallback)


def render_sidebar_status():
    """Persistente Patientenkontext-Karte in der Sidebar — sichtbar auf jeder Seite."""
    edf_path  = st.session_state.get("edf_path", "")
    file_name = st.session_state.get("edf_display_name", "")
    validated = st.session_state.get("phi_validated", False)

    with st.sidebar:
        if not edf_path or not file_name:
            st.markdown(
                "<div style='"
                "margin:12px 6px 4px 6px;"
                "padding:10px 12px;"
                "border-radius:10px;"
                "background:#f5f6f8;"
                "border:1px dashed #ced4da;"
                "color:#888;"
                "font-size:12px;"
                "line-height:1.5;"
                "'>"
                "📂 <b>Keine Datei geladen</b><br>"
                "<span style='font-size:11px'>Bitte auf <i>Datei &amp; Patient</i> starten.</span>"
                "</div>",
                unsafe_allow_html=True,
            )
            return

        age   = st.session_state.get("patient_age", "?")
        sex   = st.session_state.get("patient_sex", "X")
        sex_icon = {"M": "♂", "F": "♀", "X": "—"}.get(sex, "—")

        edf = st.session_state.get("_edf_cache_meta")
        dur_str = "—"
        n_ch_str = "—"
        has_ecg = False
        has_hv  = False
        if edf is None:
            try:
                from core.shared import load_and_prepare as _lp
                edf = _lp(edf_path)
                st.session_state["_edf_cache_meta"] = edf
            except Exception:
                edf = {}
        if edf:
            dur_s   = edf.get("duration_s", 0)
            dur_str = f"{int(dur_s)//60}:{int(dur_s)%60:02d} min"
            n_ch_str = str(len(edf.get("eeg_map", {}))) + " EEG"
            has_ecg = bool(edf.get("ecg_channels"))
            anns = edf.get("annotations", [])
            has_hv = any("HVT" in a.get("description","").upper() for a in anns)

        _has_phi = st.session_state.get("phi_has_patient_data", False)
        if not validated:
            phi_badge = "<span style='color:#e67e22;font-size:10px;font-weight:700'>⚠ nicht geprüft</span>"
        elif _has_phi:
            phi_badge = "<span style='color:#e67e22;font-size:10px;font-weight:700'>⚠ PHI — DSGVO beachten</span>"
        else:
            phi_badge = "<span style='color:#27ae60;font-size:10px;font-weight:700'>✓ anonymisiert</span>"

        st.markdown(
            f"<div style='"
            f"margin:10px 6px 4px 6px;"
            f"padding:12px 14px;"
            f"border-radius:12px;"
            f"background:#ffffff;"
            f"border:1px solid #e0e4e8;"
            f"box-shadow:0 1px 4px rgba(0,0,0,0.06);"
            f"'>"
            # Header
            f"<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:8px'>"
            f"<span style='font-size:11px;font-weight:700;color:#555;text-transform:uppercase;"
            f"letter-spacing:0.05em'>Aktive Aufnahme</span>"
            f"{phi_badge}"
            f"</div>"
            # Dateiname
            f"<div style='font-size:12px;font-weight:600;color:#1c2833;"
            f"white-space:nowrap;overflow:hidden;text-overflow:ellipsis;"
            f"margin-bottom:10px;' title='{file_name}'>"
            f"📄 {file_name}"
            f"</div>"
            # Metriken-Grid
            f"<div style='display:grid;grid-template-columns:1fr 1fr;gap:6px'>"
            f"<div style='background:#f8f9fa;border-radius:8px;padding:6px 8px'>"
            f"<div style='font-size:10px;color:#888'>Alter</div>"
            f"<div style='font-size:13px;font-weight:700;color:#1c2833'>{age} J. {sex_icon}</div>"
            f"</div>"
            f"<div style='background:#f8f9fa;border-radius:8px;padding:6px 8px'>"
            f"<div style='font-size:10px;color:#888'>Dauer</div>"
            f"<div style='font-size:13px;font-weight:700;color:#1c2833'>{dur_str}</div>"
            f"</div>"
            f"<div style='background:#f8f9fa;border-radius:8px;padding:6px 8px'>"
            f"<div style='font-size:10px;color:#888'>Kanäle</div>"
            f"<div style='font-size:13px;font-weight:700;color:#1c2833'>{n_ch_str}</div>"
            f"</div>"
            f"<div style='background:#f8f9fa;border-radius:8px;padding:6px 8px'>"
            f"<div style='font-size:10px;color:#888'>Merkmale</div>"
            f"<div style='font-size:12px;font-weight:600;color:#1c2833'>"
            f"{'❤️ ' if has_ecg else ''}{'💨 HV' if has_hv else ''}"
            f"{'—' if not has_ecg and not has_hv else ''}"
            f"</div>"
            f"</div>"
            f"</div>"
            f"</div>",
            unsafe_allow_html=True,
        )


def section_header(title: str, subtitle: str = "", color: str = "#2c3e50") -> None:
    """Visueller Section-Header — ersetzt st.divider() + st.subheader() überall in der App."""
    sub_html = (
        f"<span style='font-size:12px;color:#888;font-weight:400;"
        f"margin-left:10px'>{subtitle}</span>"
        if subtitle else ""
    )
    st.markdown(
        f"<div style='"
        f"margin:22px 0 10px 0;"
        f"padding:10px 16px;"
        f"border-left:4px solid {color};"
        f"background:linear-gradient(90deg,{color}0d 0%,transparent 100%);"
        f"border-radius:0 8px 8px 0;"
        f"'>"
        f"<span style='font-size:15px;font-weight:700;color:{color}'>{title}</span>"
        f"{sub_html}"
        f"</div>",
        unsafe_allow_html=True,
    )


def apply_global_style():
    """Neutrale, hochwertige Basis-Optik. Klinische Farben (Rot/Blau/Grün/Ampel) bleiben
    ausschließlich für ihre fachliche Bedeutung reserviert und werden hier nicht verändert."""
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    h1, h2, h3, h4, h5, h6 {
        font-family: 'Inter', sans-serif;
        font-weight: 600;
        letter-spacing: -0.01em;
        color: #1c2833;
    }
    [data-testid="stMetricValue"] { font-weight: 700; }

    /* Sidebar / Navigation */
    [data-testid="stSidebar"] {
        background: #fafbfc;
        border-right: 1px solid #e8eaed;
    }
    [data-testid="stSidebarNav"] a {
        border-radius: 8px;
        margin: 1px 6px;
        font-weight: 500;
    }
    [data-testid="stSidebarNav"] a:hover {
        background: #eef1f4;
    }

    /* Karten / Container */
    div[data-testid="stExpander"] {
        border-radius: 10px;
        border: 1px solid #e8eaed;
    }
    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 12px !important;
    }
    .stButton button { border-radius: 8px; }
    hr { margin: 0.6rem 0; opacity: 0.5; }

    /* Mobile-Grundbasis: etwas kompaktere Abstände auf schmalen Bildschirmen */
    @media (max-width: 640px) {
        h1 { font-size: 1.4rem !important; }
        h2 { font-size: 1.15rem !important; }
        h3 { font-size: 1.0rem !important; }
        [data-testid="stMetricValue"] { font-size: 1.1rem !important; }
        .block-container { padding-left: 0.8rem !important; padding-right: 0.8rem !important; }
    }
    </style>
    """, unsafe_allow_html=True)


def render_head_diagram(pairs):
    """Schematischer 10-20-Kopf mit der aktuellen Montagenkette farbig eingezeichnet."""
    fig = go.Figure()
    theta = np.linspace(0, 2 * np.pi, 100)
    fig.add_trace(go.Scatter(x=np.cos(theta), y=np.sin(theta), mode="lines",
                              line=dict(color="#aaa", width=1.5), hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(x=[-0.08, 0, 0.08], y=[0.99, 1.13, 0.99], mode="lines",
                              line=dict(color="#aaa", width=1.5), hoverinfo="skip", showlegend=False))
    for sx in (-1, 1):
        fig.add_trace(go.Scatter(x=[sx * 0.99, sx * 1.07, sx * 0.99], y=[0.18, 0, -0.18], mode="lines",
                                  line=dict(color="#aaa", width=1.5), hoverinfo="skip", showlegend=False))
    for anode, cathode in pairs:
        if anode in ELECTRODE_POS and cathode in ELECTRODE_POS:
            _, color = CHAIN_OF.get((anode, cathode), ("andere", "#999"))
            x0, y0 = ELECTRODE_POS[anode]
            x1, y1 = ELECTRODE_POS[cathode]
            fig.add_trace(go.Scatter(x=[x0, x1], y=[y0, y1], mode="lines",
                                      line=dict(color=color, width=3), hoverinfo="skip", showlegend=False))
    xs = [p[0] for p in ELECTRODE_POS.values()]
    ys = [p[1] for p in ELECTRODE_POS.values()]
    labels = list(ELECTRODE_POS.keys())
    used = {e for pair in pairs for e in pair if e in ELECTRODE_POS}
    colors_pt = ["#2c3e50" if lbl in used else "#cccccc" for lbl in labels]
    fig.add_trace(go.Scatter(
        x=xs, y=ys, mode="markers+text", text=labels, textposition="middle center",
        textfont=dict(size=7, color="white"),
        marker=dict(size=17, color=colors_pt, line=dict(width=1, color="white")),
        hoverinfo="skip", showlegend=False,
    ))
    fig.update_layout(
        xaxis=dict(visible=False, range=[-1.3, 1.3], scaleanchor="y"),
        yaxis=dict(visible=False, range=[-1.3, 1.3]),
        height=260, margin=dict(t=5, b=5, l=5, r=5),
        plot_bgcolor="white",
    )
    return fig


@st.cache_data(show_spinner="Lade und verarbeite EDF…")
def load_and_prepare(path: str):
    """Lädt EDF, extrahiert alle Kanäle als numpy-Matrix, filtert ECG vorab."""
    import mne
    from scipy.signal import butter, filtfilt
    from core.channel_classifier import classify_channels, make_short_name, ECG, EEG

    raw = mne.io.read_raw_edf(path, preload=True, verbose=False, encoding="latin1")
    sfreq = raw.info["sfreq"]
    data, _ = raw[:]
    ch_names = raw.ch_names
    n_samples = data.shape[1]
    duration_s = n_samples / sfreq

    ch_idx = {ch: i for i, ch in enumerate(ch_names)}

    # ── Signal-based channel classification (manufacturer-independent) ─────────
    classifications = classify_channels(data, ch_names, sfreq, max_analysis_sec=120.0)

    # EEG map: use signal-detected EEG channels; fall back to name prefix for
    # files where the classifier has low confidence (e.g. very short recordings)
    eeg_map: dict = {}
    for ch, result in classifications.items():
        if result.channel_type == EEG:
            short = make_short_name(ch)
            eeg_map[short] = ch_idx[ch]

    # Fallback for NeuroFax files or recordings where classifier found 0 EEG channels
    if not eeg_map:
        for ch in ch_names:
            if ch.upper().startswith("EEG"):
                short = make_short_name(ch)
                eeg_map[short] = ch_idx[ch]

    # ECG channels sorted by confidence (highest first)
    ecg_channels = [
        ch for ch, r in sorted(
            classifications.items(), key=lambda x: -x[1].confidence
        )
        if r.channel_type == ECG
    ]

    # EOG and EMG channels
    from core.channel_classifier import EOG, EMG, REF
    eog_channels = [ch for ch, r in classifications.items() if r.channel_type == EOG]
    emg_channels = [ch for ch, r in classifications.items() if r.channel_type == EMG]

    # Bandpass-filtered ECG signals for display (0.5–40 Hz)
    ecg_filtered = {}
    nyq = sfreq / 2
    b, a = butter(4, [0.5 / nyq, min(40.0 / nyq, 0.99)], btype="band")
    for ch in ecg_channels:
        idx = ch_idx[ch]
        sig = data[idx].copy().astype(np.float64)
        sig -= sig.mean()
        sig = filtfilt(b, a, sig)
        ecg_filtered[ch] = sig

    with open(path, "rb") as f:
        hdr = f.read(256)
    patient_id = hdr[8:88].decode("latin1").strip()
    rec_id = hdr[88:168].decode("latin1").strip()

    # EDF+ patient_id Feld parsen: "patientcode sex birthdate name" (Felder durch Leerzeichen)
    # Patientenname wird NICHT weitergegeben — nur Geburtsdatum, Geburtsjahr und Geschlecht.
    # Anonymisierte Dateien haben "X X X X" — dann bleiben alle header_* = None.
    header_birth_date = None
    header_birth_year = None
    header_calculated_age = None
    header_sex = None  # "M" | "F" | None

    import re as _re
    _MONTHS = {"JAN":1,"FEB":2,"MAR":3,"APR":4,"MAY":5,"JUN":6,
                "JUL":7,"AUG":8,"SEP":9,"OCT":10,"NOV":11,"DEC":12}

    # EDF+ Standard-Format: Felder durch Leerzeichen getrennt
    _fields = patient_id.split()
    # Geschlecht: zweites Feld wenn M oder F
    if len(_fields) >= 2 and _fields[1].upper() in ("M", "F"):
        header_sex = _fields[1].upper()

    # Geburtsdatum: drittes Feld oder irgendwo im String als DD-MMM-YYYY
    _m = _re.search(r'(\d{2})-([A-Z]{3})-(\d{4})', patient_id)
    if _m:
        try:
            from datetime import date as _date
            day, mon_str, year = int(_m.group(1)), _m.group(2), int(_m.group(3))
            if mon_str in _MONTHS and 1900 < year < 2030:
                birth = _date(year, _MONTHS[mon_str], day)
                header_birth_date = birth.strftime("%d.%m.%Y")
                header_birth_year = year
                today = _date.today()
                header_calculated_age = today.year - year - (
                    (today.month, today.day) < (birth.month, birth.day))
        except Exception:
            pass

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
        "eog_channels": eog_channels,
        "emg_channels": emg_channels,
        "channel_classifications": classifications,
        "sfreq": sfreq,
        "n_samples": n_samples,
        "duration_s": duration_s,
        "n_epochs": int(duration_s // EPOCH_SEC),
        "annotations": annotations,
        "has_patient_id": bool(patient_id and patient_id not in ("X X X X", "X")),
        "has_rec_id": bool(rec_id),
        "header_birth_date": header_birth_date,
        "header_birth_year": header_birth_year,
        "header_calculated_age": header_calculated_age,
        "header_sex": header_sex,
    }


@st.cache_data(show_spinner="Filtere EEG…")
def get_filtered_eeg(_data, eeg_map, sfreq, low_hz, high_hz):
    """Bandpass-Filter auf die EEG-Kanäle der Datenmatrix. _data wird nicht gehasht."""
    from scipy.signal import butter, filtfilt
    filtered = _data.copy()
    idxs = list(eeg_map.values())
    if idxs:
        nyq = sfreq / 2
        b, a = butter(4, [low_hz / nyq, min(high_hz / nyq, 0.99)], btype="band")
        filtered[idxs] = filtfilt(b, a, _data[idxs], axis=1)
    return filtered


def get_bipolar_epoch(d, eeg_map, pairs, i_s, i_e):
    """Berechnet bipolare Ableitungen nur für die Epoche."""
    result = []
    for anode, cathode in pairs:
        ia, ib = eeg_map.get(anode), eeg_map.get(cathode)
        label = f"{anode}–{cathode}"
        chain, color = CHAIN_OF.get((anode, cathode), ("andere", "#555"))
        if ia is not None and ib is not None:
            seg = (d[ia, i_s:i_e] - d[ib, i_s:i_e]) * 1e6
            result.append((label, seg, chain, color))
        else:
            result.append((label, None, chain, color))
    return result


def eeg_figure(derivs, t, spacing, annotations, t_s, t_e):
    """EEG-Plot mit Kettenspacern zwischen Gruppen."""
    GAP = spacing * 1.2

    offsets = []
    y = 0.0
    prev_chain = derivs[-1][2]
    for item in reversed(derivs):
        chain = item[2]
        if chain != prev_chain:
            y += GAP
        offsets.insert(0, y)
        y += spacing
        prev_chain = chain
    total_height = y

    seen = set()
    fig = go.Figure()

    for idx, item in enumerate(derivs):
        label, seg, chain, color = item[:4]
        hover_values = item[4] if len(item) > 4 else seg
        hover_unit = item[5] if len(item) > 5 else "µV"
        offset = offsets[idx]
        show_leg = chain not in seen; seen.add(chain)
        if seg is not None:
            # EEG-Konvention: negativ oben → Signal negieren außer bei EKG-Lane
            plot_seg = seg if chain == "EKG" else -seg
            fig.add_trace(go.Scatter(
                x=t, y=plot_seg + offset, mode="lines",
                name=chain, legendgroup=chain, showlegend=show_leg,
                line=dict(width=0.9, color=color),
                hovertemplate=f"<b>{label}</b>: %{{customdata:.3f}} {hover_unit}<extra></extra>",
                customdata=hover_values,
            ))
        else:
            fig.add_trace(go.Scatter(
                x=[t[0], t[-1]], y=[offset, offset], mode="lines",
                line=dict(width=0.5, color="#ccc", dash="dot"),
                showlegend=False, hoverinfo="skip",
            ))

    prev_chain = derivs[0][2]
    for i, item in enumerate(derivs[1:], 1):
        chain = item[2]
        if chain != prev_chain:
            sep_y = (offsets[i - 1] + offsets[i]) / 2
            fig.add_hline(y=sep_y, line_dash="dot", line_color="#cccccc", line_width=1)
        prev_chain = chain

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
            ticktext=[item[0] for item in derivs],
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

    if lp_hz is not None:
        from scipy.signal import butter, filtfilt
        sfreq = 1.0 / (t[1] - t[0])
        nyq = sfreq / 2
        b, a = butter(4, min(lp_hz / nyq, 0.98), btype="low")
        padlen = 3 * max(len(a), len(b))
        if len(sig_plot) > padlen:
            sig_plot = filtfilt(b, a, sig_plot)

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


def inject_arrow_key_nav():
    """Pfeiltasten ← → navigieren durch Epochen (klickt die sichtbaren ◀/▶-Buttons)."""
    import streamlit.components.v1 as components
    components.html("""
    <script>
    const doc = window.parent.document;
    if (!doc.__arrowNavAttached) {
        doc.__arrowNavAttached = true;
        doc.addEventListener('keydown', function(e) {
            const tag = (e.target.tagName || '').toLowerCase();
            if (tag === 'input' || tag === 'textarea') return;
            if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
            const wantPrev = e.key === 'ArrowLeft';
            const symbol = wantPrev ? '◀' : '▶';
            const buttons = Array.from(doc.querySelectorAll('button'));
            const match = buttons.find(b =>
                b.innerText.trim() === symbol &&
                b.offsetParent !== null &&
                !b.disabled
            );
            if (match) { match.click(); e.preventDefault(); }
        });
    }
    </script>
    """, height=0, width=0)


def epoch_nav(edf, key, label="EEG", epoch_sec=None):
    """Rendert prominente Navigationszeile, gibt aktuellen Epochenindex zurück."""
    e_sec = epoch_sec or EPOCH_SEC
    n_eps = max(1, int(edf["duration_s"] // e_sec))
    if key not in st.session_state:
        st.session_state[key] = 0
    ep = min(st.session_state[key], n_eps - 1)
    st.session_state[key] = ep
    t_s = ep * e_sec
    t_e = t_s + e_sec
    pct = (ep + 1) / n_eps * 100

    st.markdown("""
<style>
div[data-testid="stHorizontalBlock"]:has(> div > div > button[kind="secondary"]) button[kind="secondary"] {
    min-height: 44px !important;
    font-size: 17px !important;
    font-weight: 700 !important;
}
</style>
""", unsafe_allow_html=True)

    c_first, c_prev, c_info, c_next, c_last = st.columns([1, 1, 8, 1, 1])
    with c_first:
        if st.button("⏮", key=f"{key}_first", disabled=(ep == 0),
                     help="Erste Epoche", use_container_width=True):
            st.session_state[key] = 0
            st.rerun()
    with c_prev:
        if st.button("◀", key=f"{key}_prev", disabled=(ep == 0),
                     help="Vorherige Epoche (−10 s)", use_container_width=True):
            st.session_state[key] -= 1
            st.rerun()
    with c_info:
        st.markdown(
            f"<div style='text-align:center;padding:9px 0 6px;"
            f"background:#f4f6f9;border-radius:8px;border:1px solid #d0d6de'>"
            f"<span style='font-size:13px;color:#888'>Epoche</span>&ensp;"
            f"<b style='font-size:18px;color:#2c3e50'>{ep+1}</b>"
            f"<span style='font-size:13px;color:#888'>&nbsp;/&nbsp;{n_eps}</span>"
            f"&ensp;<span style='color:#ccc'>|</span>&ensp;"
            f"<b style='font-size:14px'>{t_s:.0f}s – {t_e:.0f}s</b>"
            f"&ensp;<span style='color:#ccc'>|</span>&ensp;"
            f"<span style='font-size:12px;color:#888'>{pct:.0f}% · {edf['duration_s']/60:.1f} min gesamt</span>"
            f"</div>", unsafe_allow_html=True)
    with c_next:
        if st.button("▶", key=f"{key}_next", disabled=(ep >= n_eps - 1),
                     help="Nächste Epoche (+10 s)", use_container_width=True):
            st.session_state[key] += 1
            st.rerun()
    with c_last:
        if st.button("⏭", key=f"{key}_last", disabled=(ep >= n_eps - 1),
                     help="Letzte Epoche", use_container_width=True):
            st.session_state[key] = n_eps - 1
            st.rerun()

    new_ep = st.slider(f"Epoche auswählen ({label})", 1, n_eps, ep + 1,
                       key=f"{key}_slider_{e_sec}", label_visibility="collapsed")
    if new_ep - 1 != ep:
        st.session_state[key] = new_ep - 1
        st.rerun()

    return st.session_state[key]


def get_edf_path():
    """Liest den aktuell gewählten EDF-Pfad aus dem Session-State (gesetzt auf 'Datei & Patient').
    Liegt unter dem Plain-Key 'edf_path' (nicht 'edf_path_widget') — siehe Kommentar in
    views/file_patient.py zur Widget-State-GC-Problematik bei Multi-Page-Apps."""
    return st.session_state.get("edf_path", "")


def get_edf_or_stop():
    """Lädt die EDF-Datei oder stoppt die Seite mit Hinweis, falls keine gültige Datei gewählt ist."""
    edf_path = get_edf_path()
    if not edf_path or not os.path.exists(edf_path):
        st.info("👈 Bitte zuerst auf der Seite **Datei & Patient** eine gültige EDF-Datei wählen.")
        st.stop()
    if not st.session_state.get("phi_validated"):
        st.error("🚫 Datei wurde nicht durch den Datenschutz-Check validiert. Bitte erneut hochladen.")
        st.stop()
    edf = load_and_prepare(edf_path)
    return edf, edf_path


def get_patient_info():
    """Liest Patientenalter/-geschlecht aus dem Session-State (gesetzt auf 'Datei & Patient')."""
    age = st.session_state.get("patient_age", 50)
    sex = st.session_state.get("patient_sex", "X")
    return age, sex
