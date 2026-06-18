"""Seite: EKG & HRV — RR-Analyse, Frequenzdomäne, Laborwert-Befund, Exporte."""

import io
import os

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from scipy.signal import find_peaks as _fp

from core.shared import EPOCH_SEC, ecg_figure, epoch_nav, get_edf_or_stop, get_patient_info, section_header


def _section(title: str, subtitle: str = "") -> None:
    section_header(title, subtitle)


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

    abs_sig = np.abs(sig_f)
    peak_ref = np.percentile(abs_sig, 98)
    threshold = peak_ref * 0.50
    min_dist = int(fs * 0.35)

    peaks, _ = _fp(abs_sig, height=threshold, distance=min_dist)
    polarities = np.sign(sig_f[peaks])

    rr = np.diff(peaks) / fs * 1000
    mask1 = (rr > 300) & (rr < 2000)

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
        return ~outlier

    def local_pct_filter(rr_arr, half_win=6, max_dev=0.25):
        """Entfernt RR-Intervalle, die >25% vom lokalen gleitenden Median abweichen."""
        n = len(rr_arr)
        mask = np.ones(n, dtype=bool)
        for i in range(n):
            lo = max(0, i - half_win)
            hi = min(n, i + half_win + 1)
            neighbors = np.concatenate([rr_arr[lo:i], rr_arr[i+1:hi]])
            if len(neighbors) < 3:
                continue
            local_med = np.median(neighbors)
            if local_med > 0 and abs(rr_arr[i] - local_med) / local_med > max_dev:
                mask[i] = False
        return mask

    rr_stage1 = rr[mask1]
    mask2_local = hampel(rr_stage1, half_win=5, k=3.0)

    if len(rr_stage1) > 10:
        global_median = np.median(rr_stage1[mask2_local] if mask2_local.any() else rr_stage1)
        mask3 = (rr_stage1 > global_median * 0.5) & (rr_stage1 < global_median * 1.8)
    else:
        mask3 = np.ones(len(rr_stage1), dtype=bool)

    mask4_local = local_pct_filter(rr_stage1, half_win=6, max_dev=0.25)
    final_mask = mask2_local & mask3 & mask4_local

    peaks_s1     = peaks[:-1][mask1]
    rr_clean     = rr_stage1[final_mask]
    peaks_clean  = peaks_s1[final_mask]
    n_removed    = int((~final_mask).sum())

    return {
        "peaks": peaks, "peaks_valid": peaks_clean, "polarities": polarities,
        "rr_ms": rr_clean, "rr_ms_raw": rr_stage1,
        "times": peaks_clean / fs, "times_raw": peaks_s1 / fs,
        "removed_mask": ~final_mask, "fs": fs,
        "threshold_mv": threshold * 1000,
        "n_peaks_total": len(peaks), "n_removed": n_removed,
    }


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def render():
    st.title("❤️ EKG & HRV")

    # ── Imports & Konstanten (für Closures) ───────────────────────────────────
    from analysis.hrv_reference import (
        classify_parameter, classify_parameter_pediatric,
        compute_autonomic_balance, MARKER_TYPE, LF_HF_MEAN, LF_HF_SD,
        BADGE_PARA, BADGE_SYMP, BADGE_NONE, PEDIATRIC_AGE_GROUPS,
        pnn50_expected_from_rmssd,
    )
    from analysis.hrv_freq import compute_frequency_domain as _cfd

    ZONE_COLOR = {"pathologisch": "#c0392b", "grenzwertig": "#f39c12",
                  "normal": "#27ae60", "info": "#7f8c8d"}

    # ── Setup ─────────────────────────────────────────────────────────────────
    edf, edf_path = get_edf_or_stop()
    patient_age, patient_sex = get_patient_info()
    sfreq = edf["sfreq"]
    ecg_channels = edf["ecg_channels"]

    is_pediatric       = st.session_state.get("is_pediatric", False)
    pediatric_age_group = st.session_state.get("pediatric_age_group", "10–14 Jahre")
    if is_pediatric:
        _classify = lambda p, v, a, hr, rmssd=None: classify_parameter_pediatric(p, v, hr, rmssd_ms=rmssd)
    else:
        _classify = lambda p, v, a, hr, rmssd=None: classify_parameter(p, v, a, hr, rmssd_ms=rmssd)

    # ── Innere Hilfsfunktionen ─────────────────────────────────────────────────

    def render_psd_chart(fd_x, title, line_color):
        from analysis.hrv_freq import VLF_BAND, LF_BAND, HF_BAND
        fig = go.Figure()
        for band, color, blabel in [
            (VLF_BAND, "rgba(149,165,166,0.28)", "VLF"),
            (LF_BAND,  "rgba(241,196,15,0.28)",  "LF"),
            (HF_BAND,  "rgba(52,152,219,0.28)",  "HF"),
        ]:
            fig.add_vrect(x0=band[0], x1=band[1], fillcolor=color, line_width=0,
                          annotation_text=blabel, annotation_position="top left",
                          annotation_font_size=10)
        lf_pf = fd_x.get("lf_peak_freq")
        hf_pf = fd_x.get("hf_peak_freq")
        if lf_pf and lf_pf == lf_pf:
            fig.add_vline(x=lf_pf, line_color="#e67e22", line_width=1.5, line_dash="dash")
            fig.add_annotation(x=lf_pf, y=1.0, xref="x", yref="paper", showarrow=False,
                               text=f"LF ▲<br>{lf_pf:.3f} Hz",
                               font=dict(size=9, color="#e67e22"),
                               bgcolor="rgba(255,255,255,0.75)", borderpad=2,
                               xanchor="left", yanchor="top")
        if hf_pf and hf_pf == hf_pf:
            resp = hf_pf * 60
            fig.add_vline(x=hf_pf, line_color="#2980b9", line_width=1.5, line_dash="dash")
            fig.add_annotation(x=hf_pf, y=1.0, xref="x", yref="paper", showarrow=False,
                               text=f"HF ▲<br>{hf_pf:.3f} Hz<br>≈{resp:.0f}/min",
                               font=dict(size=9, color="#2980b9"),
                               bgcolor="rgba(255,255,255,0.75)", borderpad=2,
                               xanchor="left", yanchor="top")
        fig.add_trace(go.Scatter(
            x=fd_x["freqs"], y=fd_x["psd"], mode="lines", fill="tozeroy",
            line=dict(color=line_color, width=1.8),
            fillcolor=_hex_to_rgba(line_color, 0.18),
            hovertemplate="f=%{x:.4f} Hz<br>PSD=%{y:.2f} ms²/Hz<extra></extra>",
        ))
        psd_pos = fd_x["psd"][fd_x["psd"] > 0]
        y_lo = max(np.percentile(psd_pos, 1) * 0.5, 1e-3) if len(psd_pos) else 1e-3
        y_hi = psd_pos.max() * 2.2 if len(psd_pos) else 1.0
        fig.update_layout(
            title=dict(text=title, font=dict(size=13), x=0.02, y=0.97),
            xaxis_title="Frequenz (Hz)", yaxis_title="PSD (ms²/Hz)",
            xaxis=dict(range=[0, 0.42], dtick=0.1, tickformat=".1f"),
            yaxis=dict(type="log", range=[np.log10(y_lo), np.log10(y_hi)]),
            height=260, margin=dict(t=30, b=35, l=50, r=8),
            plot_bgcolor="#f9f9f9", showlegend=False,
        )
        return fig

    def render_marker_badge(marker_type: str, text: str) -> str:
        if marker_type == "para":
            style = f"background:{BADGE_PARA}1f;color:{BADGE_PARA};border:1px solid {BADGE_PARA}55;"
        elif marker_type == "symp":
            style = f"background:{BADGE_SYMP}1f;color:{BADGE_SYMP};border:1px solid {BADGE_SYMP}55;"
        elif marker_type in ("mixed", "global"):
            style = (f"background:linear-gradient(90deg,{BADGE_PARA}1f 0%,{BADGE_PARA}1f 48%,"
                     f"{BADGE_SYMP}1f 52%,{BADGE_SYMP}1f 100%);"
                     f"color:#5a5a7a;border:1px solid #b0b0c055;")
        else:
            style = f"background:{BADGE_NONE}1a;color:{BADGE_NONE};border:1px solid {BADGE_NONE}55;"
        return (f"<span style='display:inline-block;padding:3px 10px;border-radius:12px;"
                f"{style}font-size:12px;font-weight:600;letter-spacing:.2px'>{text}</span>")

    def _render_lab_panel(rr_seg: np.ndarray, r_times_seg: np.ndarray,
                          sdnn_warning: bool = False, freq_warning: bool = False,
                          panel_id: str = "default"):
        """Rendert Balance-Gauge + alle HRV-Parameterbalken für ein RR-Segment."""
        if len(rr_seg) < 5:
            st.warning("Zu wenige Schläge in diesem Segment für HRV-Analyse.")
            return [], {}

        _diff    = np.diff(rr_seg)
        _mean_rr = float(np.mean(rr_seg))
        _mean_hr = 60000 / _mean_rr
        _sdnn    = float(np.std(rr_seg, ddof=1)) if len(rr_seg) > 1 else 0.0
        _rmssd   = float(np.sqrt(np.mean(_diff**2))) if len(_diff) > 0 else 0.0
        _pnn50   = float(np.sum(np.abs(_diff) > 50) / max(len(_diff), 1) * 100)

        _fd = None
        if len(rr_seg) >= 30 and len(r_times_seg) >= 30:
            try:
                _fd = _cfd(rr_seg, r_times_seg, method="welch")
            except Exception:
                _fd = None

        _lf  = _fd["lf_power"]    if _fd else float("nan")
        _hf  = _fd["hf_power"]    if _fd else float("nan")
        _tp  = _fd["total_power"] if _fd else float("nan")
        _lhr = _fd["lf_hf_ratio"] if _fd else float("nan")

        metrics = {"mean_hr": _mean_hr, "sdnn": _sdnn, "rmssd": _rmssd, "pnn50": _pnn50,
                   "lf": _lf, "hf": _hf, "tp": _tp, "lhr": _lhr}

        if _fd and _fd["hf_power"] > 0 and not (float("nan") == _fd["lf_hf_ratio"]):
            try:
                _balance = compute_autonomic_balance(_rmssd, _fd["hf_power"], _fd["lf_hf_ratio"])
                _fig_bal = go.Figure()
                for x0b, x1b, cb in [(-100,-40,"#f1c40f"),(-40,-15,"#f1c40f"),(-15,15,"#27ae60"),
                                      (15,40,"#f1c40f"),(40,100,"#f1c40f")]:
                    _fig_bal.add_vrect(x0=x0b, x1=x1b, fillcolor=cb,
                                       opacity=0.18 if abs(x0b)==100 else 0.10 if abs(x0b)==40 else 0.18,
                                       line_width=0)
                _fig_bal.add_vline(x=0, line_color="#888", line_width=1, line_dash="dot")
                _fig_bal.add_trace(go.Scatter(
                    x=[_balance["index"]], y=[0], mode="markers+text",
                    marker=dict(symbol="diamond", size=20, color="#2c3e50",
                                line=dict(width=2, color="white")),
                    text=[f"{_balance['index']:+.0f}"], textposition="top center",
                    textfont=dict(size=13, color="#2c3e50"),
                ))
                _fig_bal.update_layout(
                    xaxis=dict(range=[-100,100], tickvals=[-100,-40,0,40,100],
                               ticktext=["stark vagal","leicht vagal","ausgeglichen",
                                         "leicht symp.","stark symp."]),
                    yaxis=dict(visible=False, range=[-1,1]),
                    height=140, margin=dict(t=10,b=30,l=20,r=20),
                    plot_bgcolor="white", showlegend=False,
                )
                st.plotly_chart(_fig_bal, use_container_width=True)
                st.markdown(
                    f"<div style='text-align:center;font-size:15px;margin-top:-15px'>"
                    f"Autonome Tendenz: <b>{_balance['label']}</b></div>",
                    unsafe_allow_html=True,
                )
            except Exception:
                pass

        if sdnn_warning:
            st.warning(
                "⚠️ **SDNN kompromittiert** — Atemfrequenz während HV > 0.4 Hz verschiebt die "
                "respiratorische Sinusarrhythmie aus dem HF-Band. SDNN steigt mechanisch. "
                "Wert wird angezeigt, ist aber **nicht mit Ruhewerten vergleichbar**."
            )
        if freq_warning:
            st.info(
                "ℹ️ Frequenzdomäne (LF/HF/Total) in diesem Segment methodisch eingeschränkt: "
                "kurze Segmentdauer und/oder respiratorische Artefakte. Werte orientierend."
            )

        _lf_pf   = _fd["lf_peak_freq"]  if _fd else float("nan")
        _hf_pf   = _fd["hf_peak_freq"]  if _fd else float("nan")
        _resp    = _fd["hf_resp_rate"]   if _fd else float("nan")
        _lf_norm = _fd["lf_norm"]        if _fd else float("nan")
        _hf_norm = _fd["hf_norm"]        if _fd else float("nan")

        _hf_band_invalid = (_hf_pf == _hf_pf) and (_hf_pf > 0.40)
        if _hf_band_invalid:
            st.warning(
                f"⚠️ **HF-Band biologisch ungültig** — Atemfrequenz-Gipfel liegt bei "
                f"**{_hf_pf:.3f} Hz ({_resp:.0f}/min)**, außerhalb des standardisierten "
                f"HF-Bandes (0.15–0.40 Hz). HF Power und HF normiert sind in diesem "
                f"Segment nicht interpretierbar. **Vagusbeurteilung ausschließlich über "
                f"RMSSD (Zeitbereich) vornehmen** — dieser arbeitet bandunabhängig."
            )

        _SYNONYM = {
            "rmssd":        "Zeitbereich-Äquivalent zu HF Power",
            "hf_power":     "Frequenzbereich-Äquivalent zu RMSSD",
            "sdnn":         "Zeitbereich-Näherung für √Total Power",
            "total_power":  "Frequenzbereich-Näherung für SDNN²",
            "hf_norm":      "Komplement zu LF norm (LF norm + HF norm ≈ 100 %)",
            "lf_norm":      "Komplement zu HF norm",
            "hf_resp_rate": "Atemfrequenz aus HF-Gipfel — NeuroFax: NF (Hz) × 60",
            "lf_peak_freq": "NeuroFax: LF (Hz) — Frequenzposition der Mayer-Wellen",
        }

        lab_groups = [
            ("Ebene 1 — Signalvalidität & Physiologie", [
                ("heart_rate",   "Herzfrequenz",              _mean_hr,  "bpm"),
                ("hf_resp_rate", "Atemfrequenz (HF-Gipfel)",  _resp,     "/min"),
                ("pnn50",        "pNN50  (Konkordanz-Check)", _pnn50,    "%"),
            ]),
            ("Ebene 2 — Zeitbereich (robust, bandunabhängig)", [
                ("rmssd", "RMSSD", _rmssd, "ms"),
                ("sdnn",  "SDNN",  _sdnn,  "ms"),
            ]),
            ("Ebene 3 — Frequenzbereich (nur bei valider Signalqualität)", [
                ("lf_power",     "LF Power",          _lf,       "ms²"),
                ("hf_power",     "HF Power",          _hf,       "ms²"),
                ("total_power",  "Total Power",       _tp,       "ms²"),
                ("lf_hf_ratio",  "LF/HF-Ratio",       _lhr,      ""),
                ("lf_norm",      "LF normalisiert",   _lf_norm,  "%"),
                ("hf_norm",      "HF normalisiert",   _hf_norm,  "%"),
                ("lf_peak_freq", "LF-Gipfelfrequenz", _lf_pf,    "Hz"),
            ]),
        ]

        _pdf_rows = []

        def _render_param_row(key, label, value, unit, _pid=panel_id):
            is_nan = (value != value)
            if is_nan and not freq_warning:
                return None
            if is_nan:
                row_l, row_r = st.columns([1, 4])
                with row_l:
                    st.markdown(f"**{label}**")
                with row_r:
                    st.caption("⚫ nicht berechenbar — Segment zu kurz oder Artefakte")
                return None

            cls    = _classify(key, value, patient_age, _mean_hr,
                               rmssd=_rmssd if key == "pnn50" else None)
            marker  = MARKER_TYPE.get(key, {"type": "none", "label": "—"})
            synonym = _SYNONYM.get(key, "")

            row_l, row_r = st.columns([1, 4])
            with row_l:
                st.markdown(f"**{label}**")
                st.markdown(render_marker_badge(marker["type"], marker["label"]),
                            unsafe_allow_html=True)
                if synonym:
                    st.caption(f"↔ {synonym}")
            with row_r:
                fig_row = go.Figure()

                if key == "lf_hf_ratio":
                    if is_pediatric:
                        lo_patho, lo_border, hi_border, hi_patho = 0.0, 0.3, 3.5, 6.0
                    else:
                        lo_patho  = LF_HF_MEAN - 2*LF_HF_SD
                        lo_border = LF_HF_MEAN - LF_HF_SD
                        hi_border = LF_HF_MEAN + LF_HF_SD
                        hi_patho  = LF_HF_MEAN + 2*LF_HF_SD
                    zones = [
                        (0,              max(0, lo_patho),   "pathologisch"),
                        (max(0,lo_patho),max(0,lo_border),  "grenzwertig"),
                        (max(0,lo_border),hi_border,         "normal"),
                        (hi_border,       hi_patho,          "grenzwertig"),
                        (hi_patho,        cls["scale_max"],  "pathologisch"),
                    ]
                elif key == "lf_peak_freq":
                    zones = [(0, cls["scale_max"], "info")]
                elif key == "pnn50":
                    pnn50_exp = cls.get("pnn50_expected")
                    if pnn50_exp is not None and pnn50_exp >= 2.0:
                        lo_warn = pnn50_exp * 0.40
                        lo_ok   = pnn50_exp * 0.65
                        hi_ok   = pnn50_exp * 1.60
                        zones = [
                            (0,       lo_warn,           "pathologisch"),
                            (lo_warn, lo_ok,             "grenzwertig"),
                            (lo_ok,   hi_ok,             "normal"),
                            (hi_ok,   cls["scale_max"],  "grenzwertig"),
                        ]
                    elif pnn50_exp is not None and pnn50_exp > 0.05:
                        zones = [(0, cls["scale_max"], "normal")]
                    else:
                        zones = [(0, cls["scale_max"], "info")]
                elif key in ("lf_norm", "hf_norm"):
                    ref_lo = cls["ref_lo"] or 0
                    ref_hi = cls["ref_hi"] or cls["scale_max"]
                    if key == "heart_rate":
                        zones = [
                            (0,    40,   "pathologisch"),
                            (40,   60,   "grenzwertig"),
                            (60,  100,   "normal"),
                            (100, 140,   "grenzwertig"),
                            (140, cls["scale_max"], "pathologisch"),
                        ]
                    else:
                        zones = [
                            (0,       ref_lo,           "grenzwertig"),
                            (ref_lo,  ref_hi,            "normal"),
                            (ref_hi,  cls["scale_max"],  "grenzwertig"),
                        ]
                elif key == "hf_resp_rate":
                    zones = [
                        (0,   10,  "grenzwertig"),
                        (10,  12,  "grenzwertig"),
                        (12,  20,  "normal"),
                        (20,  25,  "grenzwertig"),
                        (25,  cls["scale_max"], "grenzwertig"),
                    ]
                else:
                    p5 = cls["p5_threshold"] or 0.01
                    zones = [
                        (0,       p5,           "pathologisch"),
                        (p5,      p5 * 1.5,     "grenzwertig"),
                        (p5*1.5,  cls["scale_max"], "normal"),
                    ]

                for x0, x1, zname in zones:
                    if x1 > x0:
                        fig_row.add_vrect(x0=x0, x1=x1, fillcolor=ZONE_COLOR[zname],
                                          opacity=0.22, line_width=0)

                if key == "lf_hf_ratio":
                    fig_row.add_annotation(x=0, y=1.35, xref="x", yref="paper", showarrow=False,
                                           text="◀ parasympathikoton",
                                           font=dict(size=10, color="#1a5276"), xanchor="left")
                    fig_row.add_annotation(x=cls["scale_max"], y=1.35, xref="x", yref="paper",
                                           showarrow=False, text="sympathikoton ▶",
                                           font=dict(size=10, color="#c0392b"), xanchor="right")
                if key in ("lf_norm", "hf_norm"):
                    lbl_lo = "vagal" if key == "lf_norm" else "symp."
                    lbl_hi = "symp." if key == "lf_norm" else "vagal"
                    fig_row.add_annotation(x=0, y=1.35, xref="x", yref="paper", showarrow=False,
                                           text=f"◀ {lbl_lo}",
                                           font=dict(size=10, color="#1a5276"), xanchor="left")
                    fig_row.add_annotation(x=cls["scale_max"], y=1.35, xref="x", yref="paper",
                                           showarrow=False, text=f"{lbl_hi} ▶",
                                           font=dict(size=10, color="#c0392b"), xanchor="right")

                fig_row.add_trace(go.Scatter(
                    x=[value], y=[0], mode="markers",
                    marker=dict(symbol="diamond", size=16, color=ZONE_COLOR[cls["zone"]],
                                line=dict(width=1.5, color="#2c3e50")),
                    hovertemplate=f"{label}: %{{x:.3f}} {unit}<extra></extra>",
                ))

                top_margin = 22 if key in ("lf_hf_ratio", "lf_norm", "hf_norm") else 5
                fig_row.update_layout(
                    xaxis=dict(range=[0, cls["scale_max"]], showgrid=False, title=None,
                               tickfont=dict(size=10)),
                    yaxis=dict(visible=False, range=[-1, 1]),
                    width=900, height=70,
                    margin=dict(t=top_margin, b=20, l=10, r=10),
                    plot_bgcolor="white", showlegend=False,
                )
                st.plotly_chart(fig_row, use_container_width=True, key=f"param_{_pid}_{key}")

                if key == "pnn50":
                    pnn50_exp = cls.get("pnn50_expected")
                    if pnn50_exp is not None and pnn50_exp > 0.5:
                        fig_conc = go.Figure()
                        bar_scale = max(value, pnn50_exp) * 1.5 + 5
                        fig_conc.add_trace(go.Bar(
                            x=[value], y=["pNN50"], orientation="h", name="gemessen",
                            marker_color=ZONE_COLOR[cls["zone"]],
                            hovertemplate=f"Gemessen: {value:.1f}%<extra></extra>",
                        ))
                        fig_conc.add_trace(go.Bar(
                            x=[pnn50_exp], y=["erwartet"], orientation="h", name="erwartet",
                            marker_color="#bdc3c7",
                            hovertemplate=f"Erwartet aus RMSSD={_rmssd:.1f}ms: {pnn50_exp:.1f}%<extra></extra>",
                        ))
                        fig_conc.update_layout(
                            xaxis=dict(range=[0, bar_scale], title="pNN50 (%)",
                                       tickfont=dict(size=10)),
                            yaxis=dict(tickfont=dict(size=10)),
                            height=90, margin=dict(t=4, b=28, l=65, r=10),
                            plot_bgcolor="white", barmode="group",
                            legend=dict(orientation="h", yanchor="bottom", y=1.0,
                                        font=dict(size=10)),
                        )
                        st.plotly_chart(fig_conc, use_container_width=True,
                                        key=f"pnn50_conc_{_pid}")

                ref_src = "Gąsior 2018" if is_pediatric else "Hansen 2024"
                if cls["zone"] == "info":
                    ref_range = ("Mayer-Wellen ~0.07–0.12 Hz"
                                 if key == "lf_peak_freq" else "deskriptiv")
                    st.caption(f"⚪ **{value:.3f} {unit}** · {ref_range}")
                else:
                    badge    = {"pathologisch": "🔴", "grenzwertig": "🟡", "normal": "🟢"}[cls["zone"]]
                    sev_text = f" — {cls['severity']}" if cls["zone"] != "normal" else ""
                    dir_text = f" ({cls['direction']})" if cls["direction"] != "—" else ""
                    if key == "heart_rate":
                        norm_txt = "· Norm: 60–100 bpm · <40 oder >140 = schwere Bradykardie/Tachykardie [klinisch]"
                    elif key == "hf_resp_rate":
                        norm_txt = "· Norm: 12–20 /min [Yasuma 2004]"
                    elif key in ("lf_norm", "hf_norm"):
                        lo, hi = cls["ref_lo"], cls["ref_hi"]
                        norm_txt = f"· Norm: {lo:.0f}–{hi:.0f} % [Task Force 1996]"
                    elif key == "pnn50":
                        pnn50_exp = cls.get("pnn50_expected")
                        norm_txt = (f"· Erwartet aus RMSSD: {pnn50_exp:.1f} % [Mietus 2002]"
                                    if pnn50_exp is not None else "")
                    elif cls["p5_threshold"] is not None:
                        norm_txt = f"· 5. Perz.: {cls['p5_threshold']:.1f} {unit} [{ref_src}]"
                    else:
                        norm_txt = ""
                    st.caption(f"{badge} **{value:.1f} {unit}** · {cls['zone']}{sev_text}{dir_text} {norm_txt}")

            return {"label": label, "value": value, "unit": unit,
                    "marker_label": marker["label"], "marker_type": marker["type"],
                    "zone": cls["zone"], "severity": cls["severity"],
                    "p5": cls["p5_threshold"], "fig": fig_row}

        for group_name, params in lab_groups:
            st.markdown(
                f"<div style='font-size:12px;font-weight:600;color:var(--text-secondary,#888);"
                f"text-transform:uppercase;letter-spacing:.6px;"
                f"border-left:3px solid #bbb;padding-left:8px;margin:14px 0 6px'>"
                f"{group_name}</div>",
                unsafe_allow_html=True,
            )
            for key, label, value, unit in params:
                row_result = _render_param_row(key, label, value, unit)
                if row_result:
                    _pdf_rows.append(row_result)

        return _pdf_rows, metrics

    # ── EKG-Kanal-Auswahl ─────────────────────────────────────────────────────
    all_non_eeg = [ch for ch in edf["ch_names"]
                   if not ch.startswith("EEG") and ch != "EDF Annotations"]

    if not ecg_channels:
        st.warning(
            "⚠️ **Kein EKG-Kanal automatisch erkannt.** "
            "Bitte wähle manuell einen Kanal aus der Liste — das EKG-Signal hat typisch "
            "0.5–5 mV Peak-to-Peak und zeigt eine regelmäßige Pulsfrequenz (40–160/min)."
        )
        with st.expander("🔍 Diagnose — warum wurde kein Kanal erkannt?", expanded=False):
            st.markdown(
                "Die automatische Erkennung prüft jeden Nicht-EEG-Kanal auf:\n"
                "- **Amplitude** 0.1–50 mV Peak-to-Peak (nach DC-Offset-Entfernung)\n"
                "- **Herzfrequenz** 35–160 bpm (über zwei 60-Sekunden-Fenster)\n"
                "- **Kurtosis** 1–100 (scharfe R-Zacken = leptokurtisch)\n\n"
                "Mögliche Ursachen für fehlende Erkennung:\n"
                "- EKG-Kanal heißt anders als X1/X2/EKG/ECG (z. B. `BIP01`, `POL Y1`)\n"
                "- Gain so hoch/niedrig dass Amplitude außerhalb des erwarteten Bereichs liegt\n"
                "- EKG in den ersten 30 Sekunden durch Bewegungsartefakte überlagert\n"
                "- Kanal heißt `EKG` aber startet nicht mit `EEG` → müsste erkannt werden, "
                "bitte Kanal manuell prüfen und Feedback geben"
            )
            st.markdown("**Verfügbare Nicht-EEG-Kanäle:**")
            for ch in all_non_eeg:
                st.code(ch)
        manual_ch = st.selectbox(
            "Kanal manuell auswählen",
            all_non_eeg,
            index=0,
            key="ecg_manual_channel",
        )
        if manual_ch not in edf["ecg_filtered"]:
            from scipy.signal import butter as _b, filtfilt as _f
            _idx = edf["ch_idx"][manual_ch]
            sig_raw = edf["data"][_idx].copy().astype(float)
            sig_raw -= sig_raw.mean()
            nyq = sfreq / 2
            bb, aa = _b(4, [0.5/nyq, min(40/nyq, 0.99)], btype="band")
            edf["ecg_filtered"][manual_ch] = _f(bb, aa, sig_raw)
        ecg_channels = [manual_ch]
        st.info(f"Analysiere Kanal **{manual_ch}** — bitte EKG-Spur visuell prüfen.")

    col_ch, col_sens, col_lp = st.columns([2, 2, 2])
    ecg_ch = col_ch.selectbox(
        "EKG-Kanal",
        ecg_channels + [ch for ch in all_non_eeg if ch not in ecg_channels],
        index=0,
        help=(
            f"Automatisch erkannte Kanäle: {', '.join(ecg_channels) if ecg_channels else '—'}. "
            "Weitere Kanäle sind manuell wählbar falls das EKG auf einem unbekannten Kanal liegt."
        ),
    )
    if ecg_ch not in edf["ecg_filtered"]:
        from scipy.signal import butter as _b2, filtfilt as _f2
        _idx2 = edf["ch_idx"][ecg_ch]
        sig_raw2 = edf["data"][_idx2].copy().astype(float)
        sig_raw2 -= sig_raw2.mean()
        nyq2 = sfreq / 2
        bb2, aa2 = _b2(4, [0.5/nyq2, min(40/nyq2, 0.99)], btype="band")
        edf["ecg_filtered"][ecg_ch] = _f2(bb2, aa2, sig_raw2)

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

    ep_ecg   = epoch_nav(edf, "ep_ecg", "EKG")
    t_s_ecg  = ep_ecg * EPOCH_SEC
    i_s_ecg  = int(t_s_ecg * sfreq)
    i_e_ecg  = int((t_s_ecg + EPOCH_SEC) * sfreq)
    t_ecg    = np.arange(i_s_ecg, i_e_ecg) / sfreq

    sig      = edf["ecg_filtered"][ecg_ch][i_s_ecg:i_e_ecg]
    sig_mv   = sig * 1000

    fig_ecg  = ecg_figure(t_ecg, sig_mv, sensitivity_mv, lp_hz)
    st.plotly_chart(fig_ecg, use_container_width=True)

    sig_centered = sig_mv - np.median(sig_mv)
    pp  = sig_centered.max() - sig_centered.min()
    rms = np.sqrt(np.mean(sig_centered**2))
    st.caption(
        f"Kanal: **{ecg_ch}** | peak-peak: **{pp:.2f} mV** | "
        f"RMS: {rms:.2f} mV | Vorfilter: 0.5–40 Hz | Anzeige: ±{sensitivity_mv} mV"
    )

    # ── Phasen & RR-Berechnung ────────────────────────────────────────────────
    from analysis.hv_segmentation import (detect_hv_phases, hrv_for_segment,
        assess_vagal_rebound, add_phase_bands, PHASE_COLORS)

    phases  = detect_hv_phases(edf["annotations"])
    has_hv  = phases["has_hv"]

    rr_data  = compute_rr(edf_path, ecg_ch)
    rr_ms    = rr_data["rr_ms"]
    r_times  = rr_data["times"]

    if len(rr_ms) < 5:
        st.warning("Zu wenige R-Peaks erkannt. Kanal oder Filter prüfen.")
        return

    n_total     = rr_data["n_peaks_total"]
    n_removed   = rr_data["n_removed"]
    n_kept      = len(rr_ms)
    pct_removed = n_removed / max(n_kept + n_removed, 1) * 100

    if pct_removed < 5:
        qcolor, qicon, qlabel = "#27ae60", "🟢", "Gute Datenqualität"
    elif pct_removed < 15:
        qcolor, qicon, qlabel = "#f39c12", "🟡", "Mäßige Datenqualität — Befund mit Vorsicht interpretieren"
    else:
        qcolor, qicon, qlabel = "#c0392b", "🔴", "Schlechte Datenqualität — HRV-Werte wahrscheinlich nicht valide"

    mean_rr = float(np.mean(rr_ms))
    mean_hr = 60000 / mean_rr
    sdnn    = float(np.std(rr_ms, ddof=1))
    rmssd   = float(np.sqrt(np.mean(np.diff(rr_ms)**2))) if len(rr_ms) > 2 else 0.0
    pnn50   = float(np.sum(np.abs(np.diff(rr_ms)) > 50) / max(len(np.diff(rr_ms)), 1) * 100)

    rr_raw       = rr_data["rr_ms_raw"]
    t_raw        = rr_data["times_raw"]
    removed_mask = rr_data["removed_mask"]

    # ── Segmentierung ─────────────────────────────────────────────────────────
    if has_hv and phases["pre_hv_end"] is not None:
        pre_end           = phases["pre_hv_end"]
        mask_pre          = r_times < pre_end
        rr_ms_analysis   = rr_ms[mask_pre]
        r_times_analysis = r_times[mask_pre]
        seg_label        = f"Prä-HV (0 – {pre_end:.0f} s)"
    else:
        rr_ms_analysis   = rr_ms
        r_times_analysis = r_times
        seg_label        = "Gesamtaufnahme"

    # ── Frequenzdomäne (Berechnung) ───────────────────────────────────────────
    from analysis.hrv_freq import compute_frequency_domain, VLF_BAND, LF_BAND, HF_BAND

    BURG_ORDER_DEFAULT = 16
    fd_welch = compute_frequency_domain(rr_ms_analysis, r_times_analysis, method="welch")
    fd_burg  = compute_frequency_domain(rr_ms_analysis, r_times_analysis,
                                        method="burg", burg_order=BURG_ORDER_DEFAULT)

    # ── Steuerelemente (vor Tabs — beeinflussen Figure-Bau) ───────────────────
    ctrl_c1, ctrl_c2 = st.columns([3, 3])
    with ctrl_c1:
        show_raw = st.toggle("Unbereinigte Rohdaten zusätzlich anzeigen", value=True)
    with ctrl_c2:
        freq_method = st.radio(
            "Spektralmethode für HRV-Befund",
            ["Welch (FFT)", "Burg (Maximum Entropy Method)"],
            horizontal=True,
            help="Welch: klassisch, robust. Burg/MEM: schärfere Peaks, kürzer stabil.",
        )
    method_key = "burg" if "Burg" in freq_method else "welch"
    fd = fd_burg if method_key == "burg" else fd_welch

    # ── Figures vorab bauen ───────────────────────────────────────────────────
    # Tachogram
    fig_rr = go.Figure()
    if show_raw:
        fig_rr.add_trace(go.Scatter(
            x=t_raw[~removed_mask], y=rr_raw[~removed_mask], mode="markers",
            name="behalten", marker=dict(size=3, color="#bbb"),
            hovertemplate="t=%{x:.1f}s  RR=%{y:.0f}ms (behalten)<extra></extra>",
        ))
        fig_rr.add_trace(go.Scatter(
            x=t_raw[removed_mask], y=rr_raw[removed_mask], mode="markers",
            name="entfernt (Ausreißer)", marker=dict(size=7, color="#c0392b", symbol="x"),
            hovertemplate="t=%{x:.1f}s  RR=%{y:.0f}ms (entfernt)<extra></extra>",
        ))
    fig_rr.add_trace(go.Scatter(
        x=r_times, y=rr_ms, mode="lines+markers",
        name="RR (bereinigt)", line=dict(color="#2980b9", width=1),
        marker=dict(size=3, color="#2980b9"),
        hovertemplate="t=%{x:.1f}s  RR=%{y:.0f}ms<extra></extra>",
    ))
    fig_rr.add_hline(y=mean_rr, line_dash="dot", line_color="#27ae60", line_width=1,
                     annotation_text=f"Median {mean_rr:.0f}ms", annotation_font_size=10)
    if has_hv:
        add_phase_bands(fig_rr, phases, edf["duration_s"])
    else:
        for ann in edf["annotations"]:
            fig_rr.add_vline(x=ann["onset_s"], line_dash="dot",
                             line_color="#e67e22", line_width=0.8)
    y_lo = max(0, min(mean_rr*0.5, rr_raw.min()*0.9)) if show_raw else max(0, mean_rr*0.5)
    y_hi = max(mean_rr*1.8, rr_raw.max()*1.05) if show_raw else mean_rr*1.8
    fig_rr.update_layout(
        xaxis_title="Zeit (s)", yaxis_title="RR-Intervall (ms)",
        yaxis=dict(range=[y_lo, y_hi]),
        height=320, margin=dict(t=8, b=40, l=60, r=8),
        plot_bgcolor="#f9f9f9",
        legend=dict(orientation="h", y=1.12, x=0, font=dict(size=10)),
    )

    # Poincaré
    fig_poin = go.Figure()
    if show_raw and len(rr_raw) > 1:
        raw_keep_pair = ~(removed_mask[:-1] | removed_mask[1:])
        raw_drop_pair = ~raw_keep_pair
        fig_poin.add_trace(go.Scatter(
            x=rr_raw[:-1][raw_drop_pair], y=rr_raw[1:][raw_drop_pair], mode="markers",
            name="betrifft Ausreißer",
            marker=dict(color="#c0392b", size=6, symbol="x", opacity=0.7),
            hovertemplate="RR_n=%{x:.0f}ms  RR_n+1=%{y:.0f}ms<extra></extra>",
        ))
    fig_poin.add_trace(go.Scatter(
        x=rr_ms[:-1], y=rr_ms[1:], mode="markers",
        name="bereinigt", marker=dict(color="#8e44ad", size=4, opacity=0.55),
        hovertemplate="RR_n=%{x:.0f}ms  RR_n+1=%{y:.0f}ms<extra></extra>",
    ))
    p_lo = max(300, mean_rr * 0.55)
    p_hi = min(2000, mean_rr * 1.55)
    lim  = [p_lo - 30, p_hi + 30]
    if show_raw and len(rr_raw):
        lim = [min(lim[0], rr_raw.min()-30), max(lim[1], rr_raw.max()+30)]
    fig_poin.update_layout(
        xaxis=dict(title="RR_n (ms)", range=lim),
        yaxis=dict(title="RR_(n+1) (ms)", range=lim),
        height=320, margin=dict(t=8, b=40, l=60, r=8),
        plot_bgcolor="#f9f9f9",
        legend=dict(orientation="h", y=1.12, x=0, font=dict(size=10)),
    )

    # R-Peak-Overlay
    all_peaks  = rr_data["peaks"]
    all_pols   = rr_data["polarities"]
    mask_ep    = (all_peaks >= i_s_ecg) & (all_peaks < i_e_ecg)
    r_in_epoch = all_peaks[mask_ep]
    r_pols     = all_pols[mask_ep]
    fig_ecg_rr = None
    if len(r_in_epoch) > 0:
        r_t  = r_in_epoch / sfreq
        r_v  = edf["ecg_filtered"][ecg_ch][r_in_epoch] * 1000
        r_v_centered = r_v - np.median(sig_mv)
        symbols = ["triangle-up" if p > 0 else "triangle-down" for p in r_pols]
        colors  = ["#27ae60" if p > 0 else "#e67e22" for p in r_pols]
        fig_ecg_rr = go.Figure(fig_ecg)
        fig_ecg_rr.add_trace(go.Scatter(
            x=r_t, y=r_v_centered, mode="markers", name="R-Peaks",
            marker=dict(symbol=symbols, size=11, color=colors,
                        line=dict(width=1, color="#333")),
            hovertemplate="R-Peak t=%{x:.3f}s  %{y:.3f} mV<extra></extra>",
        ))

    # PSD-Figures
    fig_psd_welch_obj = render_psd_chart(fd_welch, "Welch (FFT)", "#2c3e50")
    fig_psd_burg_obj  = render_psd_chart(fd_burg,  "Burg (Maximum Entropy Method)", "#6c3483")

    # Balance-Gauge für PDF
    balance = compute_autonomic_balance(rmssd, fd["hf_power"], fd["lf_hf_ratio"])
    fig_bal = go.Figure()
    for x0b, x1b, cb, op in [(-100,-40,"#f1c40f",0.18), (-40,-15,"#f1c40f",0.10),
                               (-15,15,"#27ae60",0.18), (15,40,"#f1c40f",0.10),
                               (40,100,"#f1c40f",0.18)]:
        fig_bal.add_vrect(x0=x0b, x1=x1b, fillcolor=cb, opacity=op, line_width=0)
    fig_bal.add_vline(x=0, line_color="#888", line_width=1, line_dash="dot")
    fig_bal.add_trace(go.Scatter(
        x=[balance["index"]], y=[0], mode="markers+text",
        marker=dict(symbol="diamond", size=20, color="#2c3e50",
                    line=dict(width=2, color="white")),
        text=[f"{balance['index']:+.0f}"], textposition="top center",
        textfont=dict(size=13, color="#2c3e50"),
    ))
    fig_bal.update_layout(
        xaxis=dict(range=[-100,100], tickvals=[-100,-40,0,40,100],
                   ticktext=["stark vagal","leicht vagal","ausgeglichen",
                             "leicht symp.","stark symp."]),
        yaxis=dict(visible=False, range=[-1,1]),
        height=140, margin=dict(t=10,b=30,l=20,r=20),
        plot_bgcolor="white", showlegend=False,
    )

    # ══════════════════════════════════════════════════════════════════════════
    # 4 TABS
    # ══════════════════════════════════════════════════════════════════════════
    tab_rr, tab_freq, tab_befund, tab_hv = st.tabs([
        "📈 RR & Zeitdomäne",
        "🌊 Frequenzdomäne",
        "📋 HRV-Befund",
        "💨 Hyperventilation",
    ])

    # ── Tab 1: RR & Zeitdomäne ────────────────────────────────────────────────
    with tab_rr:
        _section("📈 RR & Zeitdomäne",
                 "Tachogramm · Poincaré-Plot · SDNN / RMSSD / pNN50")
        if has_hv:
            hv_dur = ((phases["hvt_end"] or 0) - (phases["hvt_start"] or 0))
            st.info(
                f"⚡ **Hyperventilation automatisch erkannt** · "
                f"HVT START {phases['hvt_start']:.0f}s → END {phases['hvt_end']:.0f}s "
                f"({hv_dur:.0f} s ≈ {hv_dur/60:.1f} min) · "
                f"Post-HV-Fenster: +120 s · "
                + (f"Fotostimulation: {len(phases['photo_events'])} Frequenzschritte"
                   if phases["has_photo"] else "")
            )

        with st.container(border=True):
            qc1, qc2 = st.columns([1, 3])
            with qc1:
                st.markdown(
                    f"<div style='text-align:center'><span style='font-size:28px'>{qicon}</span><br>"
                    f"<span style='font-size:22px;font-weight:700;color:{qcolor}'>{pct_removed:.1f}%</span><br>"
                    f"<span style='font-size:11px;color:#888'>Schläge entfernt</span></div>",
                    unsafe_allow_html=True,
                )
            with qc2:
                st.markdown(f"**{qlabel}**")
                st.caption(
                    f"{n_removed} von {n_total} erkannten Schlägen entfernt (verbleibend: {n_kept}). "
                    f"Filter: harte physiologische Grenzen (300–2000 ms) + Hampel-Filter (±5 Nachbarn, 3σ) "
                    f"+ globaler Kontext-Check (±2.5× Median). Ab 15% entfernter Schläge ist die "
                    f"verbleibende Stichprobe i. d. R. zu stark selektiert für eine belastbare HRV-Aussage."
                )

        rr_series = rr_data.get("rr_series")
        if rr_series is not None:
            _art_pct = rr_series.artifact_pct
            _n_clean = rr_series.n_clean
            _art_col = "#27ae60" if _art_pct < 5 else ("#f39c12" if _art_pct < 15 else "#c0392b")
            st.markdown(
                f"<div style='display:inline-flex;align-items:center;gap:8px;"
                f"padding:4px 12px;border-radius:20px;background:#f8f9fa;"
                f"border:1px solid #e0e4e8;margin:4px 0 8px 0;font-size:12px'>"
                f"<span style='color:{_art_col};font-weight:700'>●</span>"
                f"<span><b>{_n_clean}</b> saubere Schläge</span>"
                f"<span style='color:#aaa'>·</span>"
                f"<span style='color:{_art_col}'><b>{_art_pct:.1f}%</b> gefiltert</span>"
                f"<span style='color:#aaa'>·</span>"
                f"<span style='color:#888'>{'✓ analysierbar' if rr_series.is_analyzable else '⚠ zu wenige valide Schläge'}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )

        c1, c2 = st.columns(2)
        c1.metric("Mittlere HR", f"{mean_hr:.1f} bpm")
        c2.metric("Mittleres RR", f"{mean_rr:.0f} ms")

        col_tach, col_poin = st.columns(2)
        with col_tach:
            st.markdown("**Tachogramm**" +
                        ("  — Rohdaten + Ausreißer markiert" if show_raw else " — bereinigt"))
            st.plotly_chart(fig_rr, use_container_width=True)
        with col_poin:
            st.markdown("**Poincaré-Plot**" +
                        ("  — Rohdaten + Ausreißer markiert" if show_raw else " — bereinigt"))
            st.plotly_chart(fig_poin, use_container_width=True)

        st.markdown(
            f"**Epoche mit R-Peak-Markierung** — "
            f"Triggerschwelle: **±{rr_data['threshold_mv']:.2f} mV** "
            f"(50 % des 98. Perzentils des |Signals|)"
        )
        if fig_ecg_rr is not None:
            st.plotly_chart(fig_ecg_rr, use_container_width=True)
        else:
            st.info("Keine R-Peaks in dieser Epoche erkannt.")

    # ── Tab 2: Frequenzdomäne ─────────────────────────────────────────────────
    with tab_freq:
        _section("🌊 Frequenzdomäne (HRV)", seg_label)
        if has_hv:
            st.caption("PSD-Analyse basiert ausschließlich auf dem Prä-HV-Segment (Ruhebedingung).")

        if len(rr_ms_analysis) < 30:
            st.warning(f"Zu wenige Schläge im {seg_label}-Segment (mind. ~30 nötig).")
            if has_hv:
                st.caption("Prä-HV-Phase ggf. zu kurz für Frequenzanalyse.")
        else:
            col_psd_w, col_psd_b = st.columns(2)
            with col_psd_w:
                st.plotly_chart(fig_psd_welch_obj, use_container_width=True)
                _lf_w  = fd_welch.get("lf_peak_freq")
                _hf_w  = fd_welch.get("hf_peak_freq")
                _resp_w = fd_welch.get("hf_resp_rate")
                if _lf_w == _lf_w and _hf_w == _hf_w:
                    st.caption(
                        f"LF-Gipfel: **{_lf_w:.3f} Hz** (Mayer-Wellen, Norm ~0.07–0.12 Hz) · "
                        f"HF-Gipfel: **{_hf_w:.3f} Hz** ≈ **{_resp_w:.0f} /min** Atemfrequenz "
                        f"(Norm 12–20 /min = 0.20–0.33 Hz)"
                    )
            with col_psd_b:
                st.plotly_chart(fig_psd_burg_obj, use_container_width=True)
                _lf_b  = fd_burg.get("lf_peak_freq")
                _hf_b  = fd_burg.get("hf_peak_freq")
                _resp_b = fd_burg.get("hf_resp_rate")
                if _lf_b == _lf_b and _hf_b == _hf_b:
                    st.caption(
                        f"LF-Gipfel: **{_lf_b:.3f} Hz** · "
                        f"HF-Gipfel: **{_hf_b:.3f} Hz** ≈ **{_resp_b:.0f} /min** Atemfrequenz"
                    )
            st.caption(
                "ℹ️ Beide Methoden parallel sichtbar, da sie unterschiedliche Band-Power-Werte liefern können "
                "(unterschiedliche Varianz-/Auflösungseigenschaften). Bei Werten nahe einer Zonengrenze kann "
                "die Klassifikation methodenabhängig kippen. **Welch (FFT) gilt als Standard** für die "
                "klinische Einordnung; Burg dient als ergänzende Detailansicht."
            )

    # ── Tab 3: HRV-Befund ─────────────────────────────────────────────────────
    with tab_befund:
        _section("📋 HRV-Befund — Normwertvergleich", seg_label)

        if is_pediatric:
            st.info(
                f"👶 **Pädiatrische Referenzwerte aktiv — {pediatric_age_group}** · "
                "Gąsior et al. 2018 (Front Physiol), n=312 Kinder 6–13 J., HR-adjustiert."
            )
        elif patient_age < 15:
            st.warning(
                f"⚠️ Patient ist {patient_age} Jahre — bitte **Pädiatrischer Patient** aktivieren."
            )

        pdf_lab_rows, metrics_pre = _render_lab_panel(
            rr_ms_analysis, r_times_analysis, panel_id="pre"
        )

        with st.expander("📖 Parameter-Erklärungen, Synonyme & Quellen"):
            st.markdown("""
#### Zeitbereich

**Herzfrequenz** · kein ANS-Marker
Mittlere Herzrate aus dem RR-Intervall-Mittelwert. Bradykardie <60 bpm, Tachykardie >100 bpm.
Normbereich (Hansen 2024, Ruhe): Median 67 bpm [IQR 61–74].

**SDNN** · globaler Marker (Sympathikus + Parasympathikus)
Standardabweichung aller RR-Intervalle. Spiegelt die gesamte autonome Variabilität wider —
aus beiden Ästen des ANS gespeist. Analog zur Wurzel aus Total Power im Frequenzbereich:
**SDNN ≈ √Total Power** (bei vollständiger Frequenzabdeckung annähernd identisch).
Referenz P5 alters-/HF-adjustiert (Hansen 2024).

**RMSSD** · Parasympathikus-Marker (vagal)
Wurzel der mittleren quadrierten aufeinanderfolgenden RR-Differenzen. Misst die schnelle,
vagal vermittelte Schlag-zu-Schlag-Variabilität (RSA). **Zeitbereich-Synonym für HF Power:**
RMSSD ≈ √HF Power (beide messen denselben physiologischen Prozess, nur in verschiedenen
Domänen). Referenz P5 alters-/HF-adjustiert (Hansen 2024).

**pNN50** · Parasympathikus-Marker (vagal)
Anteil aufeinanderfolgender RR-Differenzen >50 ms. Eng mit RMSSD verwandt (r > 0.92),
stark altersabhängig. Kein altersadjustierter Populationscutoff verfügbar — Bewertung
daher über **RMSSD-Konkordanz** (Mietus et al. 2002):

Aus dem aktuellen RMSSD-Wert wird ein *erwartetes* pNN50 abgeleitet (Näherungsformel
basierend auf Normalverteilungsannahme der RR-Differenzen):
> pNN50_erwartet ≈ 100 × erfc(50 / (√2 × RMSSD))

Mathematischer Hintergrund: erfc() (komplementäre Fehlerfunktion) gibt direkt die
zweiseitige Wahrscheinlichkeit P(|ΔRR| > 50 ms) für normalverteilte RR-Differenzen
mit Standardabweichung RMSSD zurück. Eine Division durch 2 wäre falsch, da sie nur
die einseitige Wahrscheinlichkeit P(ΔRR > 50 ms) ergäbe.

Wenn das gemessene pNN50 deutlich unter dem Erwarteten liegt (**< 65 %** des
Erwarteten), spricht das für gehäufte ektopische Schläge oder Artefakte, die den
50-ms-Schwellenwert häufiger knapp unterschreiten.

Referenz RMSSD→pNN50: RMSSD 20 ms → ~6 %, RMSSD 40 ms → ~21 %, RMSSD 70 ms → ~47 %.

Quelle: **Mietus JE et al.** (2002). *The pNNx files: re-examining a widely used heart
rate variability measure.* Heart 88(4):378–380.

---
#### Frequenzbereich — Bandleistung

**LF Power (0.04–0.15 Hz)** · gemischter Marker (Baroreflex)
Integrierte spektrale Leistung im Low-Frequency-Band. Historisch als "Sympathikus-Marker"
bezeichnet, heute als Maß der Baroreflex-Aktivität verstanden — kein reiner
Sympathikus-Indikator (Billman 2013). Referenz P5 alters-/HF-adjustiert (Hansen 2024).
NeuroFax-Bezeichnung: **LFA** (LF Area).

**HF Power (0.15–0.40 Hz)** · Parasympathikus-Marker (vagal)
Spektrale Leistung im High-Frequency-Band — entspricht der respiratorischen Sinusarrhythmie (RSA).
**Frequenzbereich-Synonym für RMSSD:** beide messen vagale Modulation, HF Power im
Spektralraum. Referenz P5 alters-/HF-adjustiert (Hansen 2024).
NeuroFax-Bezeichnung: **HFPA** (HF Power Area) bzw. **NFA** (in einigen Versionen).

⚠️ **Wichtige Interpretationsregel:** Wenn der HF-Gipfel (Atemfrequenz aus EKG) > 0.40 Hz
liegt (Atemfrequenz > 24/min), wandert der RSA-Peak aus dem standardisierten HF-Band
heraus. HF Power und HF normiert sind dann **biologisch ungültig** — die niedrigen Werte
spiegeln keine autonome Dysfunktion wider, sondern nur die Bandgrenzen-Überschreitung.
In diesen Fällen ausschließlich RMSSD (Zeitbereich) zur Vagusbeurteilung heranziehen.

**Total Power** · globaler Marker
Summe VLF + LF + HF. Analog zur Aussage von SDNN: **Total Power ≈ SDNN²** bei
vollständiger Spektralabdeckung. Referenz P5 alters-/HF-adjustiert (Hansen 2024).
NeuroFax-Bezeichnung: **T.Wert** (Achtung: NeuroFax-T.Wert ist unnormiert, nicht direkt
vergleichbar mit unseren ms²-Werten).

**LF/HF-Ratio** · gemischter Marker (sympathovagale Balance)
Verhältnis LF-Leistung zu HF-Leistung. Klassisch als Maß der sympathovagalen Balance
interpretiert — die physiologische Validität ist in der Literatur umstritten (Billman 2013).
Als Trendmarker verwendbar, nicht als isolierter Diagnosewert.
NeuroFax-Bezeichnung: **LFA/HFA (%)** = LF/HF × 100.

---
#### Frequenzbereich — Normiert & Balance

**LF normalisiert (%)** · gemischter Marker
LF Power als prozentualer Anteil an LF+HF. Reduziert den Einfluss von Gesamtpower-
Schwankungen auf den Balance-Index. Task Force 1996 Normbereich: **40–70 %** (Ruhe, liegend).
Hohe LF norm deutet auf sympathikotone Balance hin.
NeuroFax-Bezeichnung: **LF/NF (%)** (in der FFT-Analyse).

**HF normalisiert (%)** · Parasympathikus-Marker (vagal)
HF Power als prozentualer Anteil an LF+HF. Komplement zu LF norm: LF norm + HF norm ≈ 100 %.
Task Force 1996 Normbereich: **20–50 %** (Ruhe, liegend). Hohe HF norm = vagal dominant.

---
#### Frequenzbereich — Gipfelfrequenzen

**Atemfrequenz aus HF-Gipfel** · kein ANS-Marker (physiologischer Messparameter)
Die Frequenz des dominanten Peaks im HF-Band × 60 ergibt die Atemfrequenz in /min.
Normbereich Ruhe: **12–20 /min** (0.20–0.33 Hz).
Quelle: **Yasuma F & Hayano J** (2004). Chest 125(2):683–690.
NeuroFax-Bezeichnung: **NF (Hz)**.

**LF-Gipfelfrequenz** · kein ANS-Marker (deskriptiv)
Frequenz des dominanten Peaks im LF-Band. Mayer-Wellen, typisch **0.07–0.12 Hz**.
NeuroFax-Bezeichnung: **LF (Hz)**.

---
**Quellen:**
1. **Task Force ESC/NASPE** (1996). Circulation 93(5):1043–1065.
2. **Hansen CS et al.** (2024). Clin Auton Res 35:101–113.
3. **Billman GE** (2013). Front Physiol 4:26.
4. **Yasuma F & Hayano J** (2004). Chest 125(2):683–690.
5. **Eckberg DL** (1997). Circulation 96(9):3224–3232.
6. **Gąsior JS et al.** (2018). Front Physiol 9:1495.
7. **Mietus JE et al.** (2002). Heart 88(4):378–380.

**Zonen-Logik (Erwachsene):**
- 🔴 Pathologisch: unter P5 alters-/HF-adjustiert (Hansen-Formel)
- 🟡 Grenzwertig: P5 bis 1.5×P5
- 🟢 Normal: darüber
- LF/HF-Ratio: Zonen aus Mittelwert ± 1 SD (2.8 ± 2.6)
- LF/HF normiert: Task Force 1996 Richtwerte (40–70% / 20–50%)
- Atemfrequenz: klinische Grenzen (Bradypnoe <10, Norm 12–20, Tachypnoe >20 /min)

**Wichtiger Vorbehalt:** Referenzwerte aus standardisierten 5-Min-Ruhemessungen.
EEG-EKG-Ableitungen (10–20 Min, wechselnde Vigilanz, keine kontrollierte Atmung)
erfüllen diese Bedingungen nicht — alle Werte sind **Orientierung**, keine Diagnosekriterien.
            """)

        with st.expander("RR-Tabelle (alle Schläge)"):
            df_rr = pd.DataFrame({
                "Zeit (s)":           np.round(r_times, 2),
                "RR-Intervall (ms)":  np.round(rr_ms, 1),
                "HR (bpm)":           np.round(60000 / rr_ms, 1),
            })
            st.dataframe(df_rr, hide_index=True, use_container_width=True, height=300)

        # Excel-Export
        summary_rows = [
            {"Parameter": "Herzfrequenz (Mittel)",         "Wert": round(mean_hr, 1),            "Einheit": "bpm"},
            {"Parameter": "Mittleres RR",                   "Wert": round(mean_rr, 1),            "Einheit": "ms"},
            {"Parameter": "SDNN",                           "Wert": round(sdnn, 1),               "Einheit": "ms"},
            {"Parameter": "RMSSD",                          "Wert": round(rmssd, 1),              "Einheit": "ms"},
            {"Parameter": "pNN50",                          "Wert": round(pnn50, 1),              "Einheit": "%"},
            {"Parameter": "Schläge entfernt (Outlier-Filter)", "Wert": round(pct_removed, 1),   "Einheit": "%"},
            {"Parameter": "LF Power",                       "Wert": round(fd["lf_power"], 1),     "Einheit": "ms²"},
            {"Parameter": "HF Power",                       "Wert": round(fd["hf_power"], 1),     "Einheit": "ms²"},
            {"Parameter": "Total Power",                    "Wert": round(fd["total_power"], 1),  "Einheit": "ms²"},
            {"Parameter": "LF/HF-Ratio",                   "Wert": round(fd["lf_hf_ratio"], 2),  "Einheit": "—"},
            {"Parameter": "Spektralmethode",                "Wert": freq_method,                   "Einheit": ""},
        ]
        df_summary = pd.DataFrame(summary_rows)

        xlsx_buf = io.BytesIO()
        with pd.ExcelWriter(xlsx_buf, engine="openpyxl") as writer:
            df_summary.to_excel(writer, sheet_name="HRV_Kennwerte", index=False)
            df_rr.to_excel(writer, sheet_name="RR_Intervalle", index=False)
        xlsx_buf.seek(0)

        col_dl1, col_dl2 = st.columns(2)
        with col_dl1:
            st.download_button(
                "📥 HRV-Ergebnisse als Excel exportieren",
                data=xlsx_buf,
                file_name=f"hrv_export_{os.path.splitext(os.path.basename(edf_path))[0]}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        with col_dl2:
            if st.button("📄 PDF-Report erzeugen"):
                from analysis.pdf_report import build_hrv_pdf
                with st.spinner("Erzeuge PDF…"):
                    pdf_bytes = build_hrv_pdf(
                        patient_age=patient_age, patient_sex=patient_sex,
                        file_label=os.path.basename(edf_path),
                        duration_min=edf["duration_s"] / 60,
                        mean_hr=mean_hr, sdnn=sdnn, rmssd=rmssd, pnn50=pnn50,
                        pct_removed=pct_removed, quality_label=qlabel,
                        balance_label=balance["label"], balance_index=balance["index"],
                        lab_rows=pdf_lab_rows, method_used=freq_method,
                        fig_tachogram=fig_rr, fig_poincare=fig_poin,
                        fig_psd_welch=fig_psd_welch_obj, fig_psd_burg=fig_psd_burg_obj,
                        fig_balance_gauge=fig_bal,
                    )
                st.session_state["pdf_bytes"] = pdf_bytes
            if "pdf_bytes" in st.session_state:
                st.download_button(
                    "💾 PDF herunterladen",
                    data=st.session_state["pdf_bytes"],
                    file_name=f"hrv_report_{os.path.splitext(os.path.basename(edf_path))[0]}.pdf",
                    mime="application/pdf",
                )

    # ── Tab 4: Hyperventilation ───────────────────────────────────────────────
    with tab_hv:
        _section("💨 Hyperventilation & Erholung",
                 "HRV-Analyse pro Phase · Vagaler Rebound")

        dur_s        = int(edf["duration_s"])
        _manual_key  = f"hvt_manual_{st.session_state.get('edf_display_name','')}"
        _manual_active = st.session_state.get(_manual_key, False)

        if not has_hv and not _manual_active:
            col_info_nohv, col_btn_nohv = st.columns([5, 1])
            with col_info_nohv:
                st.info("ℹ️ **Keine Hyperventilation** in dieser Aufnahme erkannt (keine HVT-Annotations).")
            with col_btn_nohv:
                st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
                if st.button("➕ HV manuell", use_container_width=True, key="hvt_manual_add_btn",
                             help="HV-Phasen manuell setzen (z.B. wenn Annotations fehlen)"):
                    st.session_state[_manual_key] = True
                    st.rerun()
        else:
            if has_hv and not _manual_active:
                hv_dur = ((phases["hvt_end"] or 0) - (phases["hvt_start"] or 0))
                if hv_dur < 60:
                    st.warning(
                        f"⚠️ **HVT sehr kurz ({hv_dur:.0f} s < 60 s)** — bitte Annotations prüfen. "
                        f"Dauer zu kurz für valide HRV-Phasenanalyse. Manuelle Anpassung empfohlen."
                    )
                col_info, col_btn = st.columns([5, 1])
                with col_info:
                    st.info(
                        f"⚡ **Automatisch erkannt** · "
                        f"HVT {phases['hvt_start']:.0f}s → {phases['hvt_end']:.0f}s "
                        f"({hv_dur:.0f} s) · Post-HV +120 s · "
                        + (f"Foto: {len(phases['photo_events'])} Schritte"
                           if phases["has_photo"] else "")
                    )
                with col_btn:
                    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
                    if st.button("✏️ Anpassen", use_container_width=True, key="hvt_override_btn"):
                        st.session_state[_manual_key] = True
                        st.rerun()
            else:
                if not has_hv:
                    st.info("ℹ️ Keine HVT-Annotations im EDF — Phasen manuell gesetzt.")
                else:
                    st.warning("✏️ Manuelle Phasengrenzen aktiv — Auto-Erkennung überschrieben.")

                hr_s_all = 60000 / rr_ms
                fig_orient = go.Figure()
                fig_orient.add_trace(go.Scatter(
                    x=r_times, y=hr_s_all, mode="lines",
                    line=dict(color="#2c3e50", width=1.0),
                    hovertemplate="t=%{x:.0f}s  HR=%{y:.1f} bpm<extra></extra>",
                ))
                fig_orient.update_layout(
                    xaxis_title="Zeit (s)", yaxis_title="HR (bpm)",
                    height=180, margin=dict(t=4, b=35, l=55, r=8),
                    plot_bgcolor="#f9f9f9",
                )
                st.plotly_chart(fig_orient, use_container_width=True, key="hvt_orient_plot")
                st.caption("HR-Verlauf zur Orientierung — HVT-Phase zeigt typisch HR-Anstieg.")

                _def_start = int(phases["hvt_start"]) if has_hv and phases["hvt_start"] else max(60, dur_s // 4)
                _def_end   = int(phases["hvt_end"])   if has_hv and phases["hvt_end"]   else min(_def_start + 180, dur_s - 60)
                _def_post  = min(_def_end + 120, dur_s)

                col_s, col_e, col_p = st.columns(3)
                with col_s:
                    hvt_s_man = st.number_input(
                        "HVT Start (s)", min_value=0, max_value=dur_s - 10,
                        value=st.session_state.get(f"{_manual_key}_start", _def_start),
                        step=1, key=f"{_manual_key}_start_widget",
                    )
                    st.session_state[f"{_manual_key}_start"] = hvt_s_man
                with col_e:
                    hvt_e_man = st.number_input(
                        "HVT Ende (s)", min_value=hvt_s_man + 10, max_value=dur_s,
                        value=st.session_state.get(f"{_manual_key}_end",
                              max(_def_end, hvt_s_man + 10)),
                        step=1, key=f"{_manual_key}_end_widget",
                    )
                    st.session_state[f"{_manual_key}_end"] = hvt_e_man
                with col_p:
                    post_e_man = st.number_input(
                        "Post-HV Ende (s)", min_value=hvt_e_man + 10, max_value=dur_s,
                        value=st.session_state.get(f"{_manual_key}_post",
                              min(hvt_e_man + 120, dur_s)),
                        step=1, key=f"{_manual_key}_post_widget",
                    )
                    st.session_state[f"{_manual_key}_post"] = post_e_man

                col_apply, col_reset = st.columns([2, 1])
                with col_reset:
                    if has_hv and st.button("↩ Auto", use_container_width=True,
                                            key="hvt_reset_btn"):
                        st.session_state[_manual_key] = False
                        st.rerun()

                phases = dict(phases)
                phases["has_hv"]      = True
                phases["hvt_start"]   = float(hvt_s_man)
                phases["hvt_end"]     = float(hvt_e_man)
                phases["pre_hv_end"]  = float(hvt_s_man)
                phases["post_hv_end"] = float(post_e_man)

            if not phases["has_hv"]:
                pass
            else:
                hvt_s  = phases["hvt_start"]
                hvt_e  = phases["hvt_end"]
                post_e = phases["post_hv_end"]

                seg_hvt  = hrv_for_segment(rr_ms, r_times, hvt_s, hvt_e)
                seg_post = hrv_for_segment(rr_ms, r_times, hvt_e, post_e) if hvt_e else None
                seg_pre  = hrv_for_segment(rr_ms, r_times, 0, hvt_s)

                st.markdown("**HR-Verlauf mit Phasenbändern**")
                hr_series = 60000 / rr_ms
                fig_hr = go.Figure()
                add_phase_bands(fig_hr, phases, edf["duration_s"])
                fig_hr.add_trace(go.Scatter(
                    x=r_times, y=hr_series, mode="lines",
                    line=dict(color="#2c3e50", width=1.2),
                    hovertemplate="t=%{x:.1f}s  HR=%{y:.1f} bpm<extra></extra>",
                ))
                if seg_pre:
                    fig_hr.add_hline(y=seg_pre["mean_hr"], line_dash="dot",
                                     line_color="#2980b9", line_width=1.2,
                                     annotation_text=f"Baseline {seg_pre['mean_hr']:.1f} bpm",
                                     annotation_font_size=10,
                                     annotation_font_color="#2980b9")
                fig_hr.update_layout(
                    xaxis_title="Zeit (s)", yaxis_title="Herzrate (bpm)",
                    height=260, margin=dict(t=8, b=40, l=55, r=8),
                    plot_bgcolor="#f9f9f9",
                )
                st.plotly_chart(fig_hr, use_container_width=True)

                from analysis.hrv_freq import compute_frequency_domain as _cfd2

                def _seg_fd(seg):
                    if seg is None or len(seg["rr_ms"]) < 30:
                        return None
                    try:
                        return _cfd2(seg["rr_ms"], seg["r_times"], method=method_key)
                    except Exception:
                        return None

                fd_pre  = _seg_fd(seg_pre)
                fd_hvt  = _seg_fd(seg_hvt)
                fd_post = _seg_fd(seg_post)

                def _fmt(val, decimals=1, suffix=""):
                    if val is None or val != val:
                        return "—"
                    return f"{val:.{decimals}f}{suffix}"

                def _seg_row(label, seg, fd_s, sdnn_warn=False):
                    if seg is None:
                        return {"Phase": label, "HR (bpm)": "—", "SDNN (ms)": "—",
                                "RMSSD (ms)": "—", "pNN50 (%)": "—",
                                "LF (ms²)": "—", "HF (ms²)": "—",
                                "LF/HF": "—", "Schläge": "—"}
                    sdnn_val = f"{seg['sdnn']:.1f}" + (" ⚠" if sdnn_warn else "")
                    return {
                        "Phase": label,
                        "HR (bpm)":    f"{seg['mean_hr']:.1f}",
                        "SDNN (ms)":   sdnn_val,
                        "RMSSD (ms)":  f"{seg['rmssd']:.1f}",
                        "pNN50 (%)":   f"{seg['pnn50']:.1f}",
                        "LF (ms²)":    _fmt(fd_s["lf_power"]    if fd_s else None, 0),
                        "HF (ms²)":    _fmt(fd_s["hf_power"]    if fd_s else None, 0),
                        "LF/HF":       _fmt(fd_s["lf_hf_ratio"] if fd_s else None, 2),
                        "Schläge":     seg["n_beats"],
                    }

                cmp_rows = [
                    _seg_row(f"Prä-HV (0–{hvt_s:.0f}s)",         seg_pre,  fd_pre,  sdnn_warn=False),
                    _seg_row(f"HVT aktiv ({hvt_s:.0f}–{hvt_e:.0f}s)", seg_hvt, fd_hvt, sdnn_warn=True),
                ]
                if seg_post and hvt_e and post_e:
                    cmp_rows.append(
                        _seg_row(f"Post-HV ({hvt_e:.0f}–{post_e:.0f}s)", seg_post, fd_post)
                    )
                st.dataframe(pd.DataFrame(cmp_rows), hide_index=True, use_container_width=True)
                st.caption(
                    "⚠ SDNN während HVT kompromittiert (mechanische Atemvariabilität, nicht autonome Modulation). "
                    "LF/HF während HVT ebenfalls eingeschränkt interpretierbar — RSA verschiebt sich aus dem HF-Band."
                )

                if seg_post and seg_pre:
                    rb = assess_vagal_rebound(seg_pre, seg_post)
                    st.markdown(
                        f"<div style='padding:10px 14px;border-radius:8px;"
                        f"border:1px solid {rb['color']}55;background:{rb['color']}11;margin:6px 0'>"
                        f"<span style='font-size:18px'>{rb['icon']}</span> "
                        f"<strong>{rb['text']}</strong><br>"
                        f"<span style='font-size:12px;color:#555'>"
                        f"HR Δ: {rb['delta_hr']:+.1f} bpm ({rb['pct_hr']:+.1f}%) · "
                        f"RMSSD Δ: {rb['delta_rmssd']:+.1f} ms ({rb['pct_rmssd']:+.1f}%)"
                        f"</span></div>",
                        unsafe_allow_html=True,
                    )
                    st.caption(
                        "Vagaler Rebound = parasympathische Überschießreaktion nach HV "
                        "(Brown et al. 1993; Ravenswaaij-Arts et al. 1993 Circulation)."
                    )

                st.divider()

                tab_labels = ["🫁 HVT aktiv"]
                if seg_post:
                    tab_labels.append("🟢 Post-HV Erholung")
                if phases["has_photo"]:
                    tab_labels.append("💡 Fotostimulation")

                tabs      = st.tabs(tab_labels)
                tab_idx   = 0

                with tabs[tab_idx]:
                    tab_idx += 1
                    st.markdown(
                        f"**HVT-Segment** · {hvt_s:.0f}–{hvt_e:.0f} s "
                        f"({(hvt_e - hvt_s):.0f} s) · "
                        f"{seg_hvt['n_beats'] if seg_hvt else '—'} Schläge"
                    )
                    if seg_hvt:
                        _render_lab_panel(seg_hvt["rr_ms"], seg_hvt["r_times"],
                                          sdnn_warning=True, freq_warning=True,
                                          panel_id="hvt")
                    else:
                        st.warning("Zu wenige Schläge im HVT-Segment.")

                if seg_post:
                    with tabs[tab_idx]:
                        tab_idx += 1
                        st.markdown(
                            f"**Post-HV-Segment** · {hvt_e:.0f}–{post_e:.0f} s "
                            f"({(post_e - hvt_e):.0f} s) · {seg_post['n_beats']} Schläge"
                        )
                        _render_lab_panel(seg_post["rr_ms"], seg_post["r_times"],
                                          panel_id="post")

                if phases["has_photo"]:
                    with tabs[tab_idx]:
                        photo_evs = phases["photo_events"]
                        t0_ph     = photo_evs[0]["t"]
                        t1_ph     = photo_evs[-1]["t"] + 13
                        seg_photo = hrv_for_segment(rr_ms, r_times, t0_ph, t1_ph)

                        freqs  = [ev["freq_hz"] for ev in photo_evs]
                        t_phot = [ev["t"]       for ev in photo_evs]

                        st.markdown(
                            f"**Fotostimulations-Segment** · {t0_ph:.0f}–{t1_ph:.0f} s "
                            f"(Beginn bis letzter Reiz +13 s) · "
                            f"{seg_photo['n_beats'] if seg_photo else '—'} Schläge"
                        )
                        st.caption(
                            "Frequenzdomäne ist in diesem Segment methodisch eingeschränkt "
                            "(kurze Segmente, Artefakte durch intermittierende Lichtreize). "
                            "SDNN/RMSSD orientierend."
                        )

                        mask_ph = (r_times >= (t0_ph - 5)) & (r_times < (t1_ph + 5))
                        fig_ph  = go.Figure()
                        fig_ph.add_trace(go.Scatter(
                            x=t_phot, y=freqs, mode="markers+lines",
                            marker=dict(size=9, color="#8e44ad"),
                            line=dict(color="#8e44ad", width=1.5, dash="dot"),
                            name="Reizfrequenz",
                            hovertemplate="t=%{x:.0f}s  %{y} Hz<extra></extra>",
                        ))
                        fig_ph.add_trace(go.Scatter(
                            x=r_times[mask_ph], y=hr_series[mask_ph], mode="lines",
                            yaxis="y2", name="HR",
                            line=dict(color="#2c3e50", width=1),
                            hovertemplate="t=%{x:.1f}s  HR=%{y:.1f} bpm<extra></extra>",
                        ))
                        fig_ph.update_layout(
                            xaxis_title="Zeit (s)",
                            yaxis=dict(title="Reizfrequenz (Hz)", side="left"),
                            yaxis2=dict(title="HR (bpm)", overlaying="y", side="right"),
                            height=220, margin=dict(t=8, b=40, l=55, r=55),
                            plot_bgcolor="#f9f9f9", showlegend=True,
                            legend=dict(orientation="h", yanchor="bottom", y=1.02),
                        )
                        st.plotly_chart(fig_ph, use_container_width=True)

                        if seg_photo:
                            st.markdown("**HRV-Kennwerte Fotostimulationsphase**")
                            _render_lab_panel(seg_photo["rr_ms"], seg_photo["r_times"],
                                              freq_warning=True, panel_id="photo")
                        else:
                            st.info("Zu wenige Schläge im Fotostimulations-Segment.")
