"""Kanal-Identifikations-Report: zeigt Classifier-Ergebnisse für alle Kanäle."""

import streamlit as st
import numpy as np

from core.shared import get_edf_or_stop, section_header, apply_global_style
from core.channel_classifier import ECG, EEG, EOG, EMG, REF, VITAL, UNKN


_TYPE_META = {
    ECG:   {"icon": "❤️",  "color": "#c0392b", "label": "EKG"},
    EEG:   {"icon": "🧠",  "color": "#2471a3", "label": "EEG"},
    EOG:   {"icon": "👁",  "color": "#8e44ad", "label": "EOG"},
    EMG:   {"icon": "💪",  "color": "#e67e22", "label": "EMG"},
    REF:   {"icon": "⏚",   "color": "#7f8c8d", "label": "Referenz"},
    VITAL: {"icon": "📊",  "color": "#27ae60", "label": "Vital"},
    UNKN:  {"icon": "❓",  "color": "#95a5a6", "label": "Unbekannt"},
}

_CONFIDENCE_COLOR = {
    "high":   "#27ae60",
    "medium": "#e67e22",
    "low":    "#c0392b",
}


def _conf_tier(conf: float) -> str:
    if conf >= 70:
        return "high"
    if conf >= 40:
        return "medium"
    return "low"


def render():
    apply_global_style()
    edf, _ = get_edf_or_stop()

    st.title("🔍 Kanal-Identifikation")
    st.markdown(
        "Automatische, signalbasierte Kanalerkennung — "
        "herstellerunabhängig, ohne Annahmen über Kanalpositionen oder Bezeichnungen."
    )

    classifications = edf.get("channel_classifications", {})
    ch_names  = edf["ch_names"]
    sfreq     = edf["sfreq"]

    if not classifications:
        st.warning("Keine Klassifikationsdaten verfügbar. Bitte Datei neu laden.")
        return

    # ── Zusammenfassung ──────────────────────────────────────────────────────
    section_header("Zusammenfassung", f"{len(ch_names)} Kanäle analysiert")

    counts: dict = {}
    for r in classifications.values():
        counts[r.channel_type] = counts.get(r.channel_type, 0) + 1

    cols = st.columns(len(counts) if len(counts) <= 6 else 6)
    for i, (t, n) in enumerate(sorted(counts.items())):
        meta = _TYPE_META.get(t, _TYPE_META[UNKN])
        with cols[i % 6]:
            st.markdown(
                f"<div style='text-align:center;padding:12px 6px;"
                f"border-radius:10px;border:1px solid {meta['color']}20;"
                f"background:{meta['color']}08'>"
                f"<div style='font-size:1.6rem'>{meta['icon']}</div>"
                f"<div style='font-size:1.4rem;font-weight:700;color:{meta['color']}'>{n}</div>"
                f"<div style='font-size:0.75rem;color:#555'>{meta['label']}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

    # ── Filter ───────────────────────────────────────────────────────────────
    section_header("Kanäle im Detail")

    all_types = sorted(set(r.channel_type for r in classifications.values()))
    filter_col, sort_col = st.columns([3, 1])
    with filter_col:
        sel_types = st.multiselect(
            "Typ-Filter",
            options=all_types,
            default=all_types,
            format_func=lambda t: f"{_TYPE_META.get(t, {}).get('icon','?')} {_TYPE_META.get(t, {}).get('label', t)}",
            label_visibility="collapsed",
        )
    with sort_col:
        sort_by = st.selectbox("Sortieren", ["Kanalreihenfolge", "Confidence ↓", "Typ"],
                                label_visibility="collapsed")

    items = [(ch, classifications[ch]) for ch in ch_names if ch in classifications
             and classifications[ch].channel_type in sel_types]

    if sort_by == "Confidence ↓":
        items.sort(key=lambda x: -x[1].confidence)
    elif sort_by == "Typ":
        items.sort(key=lambda x: x[1].channel_type)

    # ── Tabelle ──────────────────────────────────────────────────────────────
    for ch, result in items:
        meta   = _TYPE_META.get(result.channel_type, _TYPE_META[UNKN])
        tier   = _conf_tier(result.confidence)
        c_conf = _CONFIDENCE_COLOR[tier]
        f      = result.features

        with st.expander(
            f"{meta['icon']} **{ch}** — "
            f"{meta['label']} · {result.confidence:.0f}% Confidence",
            expanded=False,
        ):
            r1, r2 = st.columns([1, 2])

            with r1:
                st.markdown(
                    f"<div style='padding:10px 12px;border-radius:10px;"
                    f"border:2px solid {meta['color']};background:{meta['color']}0d'>"
                    f"<div style='font-size:2rem;text-align:center'>{meta['icon']}</div>"
                    f"<div style='text-align:center;font-weight:700;font-size:1.1rem;"
                    f"color:{meta['color']}'>{meta['label']}</div>"
                    f"<div style='text-align:center;margin-top:6px'>"
                    f"<span style='font-size:1.3rem;font-weight:700;color:{c_conf}'>"
                    f"{result.confidence:.0f}%</span>"
                    f"<span style='font-size:0.75rem;color:#888;margin-left:4px'>Confidence</span>"
                    f"</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
                st.markdown("**Begründung:**")
                for reason in result.reasons:
                    st.markdown(f"- {reason}")

            with r2:
                if f and not f.get("is_flat"):
                    st.markdown("**Signal-Features:**")
                    fa, fb, fc = st.columns(3)
                    fa.metric("Std",        f"{f.get('std_mv', 0)*1000:.1f} µV")
                    fb.metric("Peak-Peak",  f"{f.get('p2p_mv', 0):.3f} mV")
                    fc.metric("Kurtosis",   f"{f.get('kurtosis', 0):.1f}")

                    fd, fe, ff = st.columns(3)
                    fd.metric("Dom. Freq.", f"{f.get('dom_freq', 0):.1f} Hz")
                    fe.metric("QRS-Rate",   f"{f.get('qrs_rate', 0):.0f} bpm" if f.get('qrs_rate', 0) > 0 else "—")
                    ff.metric("Rhythmizität", f"{f.get('rhythmicity', 0):.2f}")

                    # Mini spectrum bar
                    bands = [
                        ("δ",     f.get("delta_rel", 0)),
                        ("θ",     f.get("theta_rel", 0)),
                        ("α",     f.get("alpha_rel", 0)),
                        ("β",     f.get("beta_rel",  0)),
                        ("γ",     f.get("gamma_rel", 0)),
                    ]
                    st.markdown("**Spektrale Verteilung:**")
                    bar_html = "<div style='display:flex;gap:4px;align-items:flex-end;height:50px'>"
                    colors = ["#3498db","#9b59b6","#e74c3c","#2ecc71","#e67e22"]
                    for (lbl, val), col in zip(bands, colors):
                        h = max(4, int(val * 48))
                        bar_html += (
                            f"<div style='display:flex;flex-direction:column;"
                            f"align-items:center;flex:1'>"
                            f"<div style='width:100%;height:{h}px;background:{col};"
                            f"border-radius:3px 3px 0 0' title='{val:.1%}'></div>"
                            f"<div style='font-size:10px;color:#555'>{lbl}</div>"
                            f"<div style='font-size:9px;color:#888'>{val:.0%}</div>"
                            f"</div>"
                        )
                    bar_html += "</div>"
                    st.markdown(bar_html, unsafe_allow_html=True)

                elif f.get("is_flat"):
                    st.warning("Flacher/toter Kanal — kein Signal.")

    # ── EEG Map Übersicht ────────────────────────────────────────────────────
    eeg_map = edf.get("eeg_map", {})
    if eeg_map:
        section_header("Erkannte EEG-Kanäle", f"{len(eeg_map)} Elektroden für EEG-Analyse")
        cols = st.columns(min(6, len(eeg_map)))
        for i, (short, idx) in enumerate(eeg_map.items()):
            with cols[i % len(cols)]:
                st.markdown(
                    f"<div style='text-align:center;padding:6px;border-radius:8px;"
                    f"background:#2471a308;border:1px solid #2471a330;font-size:12px'>"
                    f"<b>{short}</b><br><span style='color:#888;font-size:10px'>Ch {idx}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

    # ── EKG / EOG / EMG Übersicht ────────────────────────────────────────────
    ecg = edf.get("ecg_channels", [])
    eog = edf.get("eog_channels", [])
    emg = edf.get("emg_channels", [])

    if ecg or eog or emg:
        section_header("Hilfskanäle")
        hc = st.columns(3)
        for col, label, icon, channels, color in (
            (hc[0], "EKG", "❤️",  ecg, "#c0392b"),
            (hc[1], "EOG", "👁",  eog, "#8e44ad"),
            (hc[2], "EMG", "💪",  emg, "#e67e22"),
        ):
            with col:
                st.markdown(
                    f"<div style='padding:10px;border-radius:10px;"
                    f"border:1px solid {color}30;background:{color}08'>"
                    f"<b style='color:{color}'>{icon} {label}</b><br>"
                    + ("".join(
                        f"<div style='font-size:12px;padding:2px 0'>{ch}</div>"
                        for ch in channels
                    ) if channels else "<div style='color:#aaa;font-size:12px'>—</div>")
                    + "</div>",
                    unsafe_allow_html=True,
                )
