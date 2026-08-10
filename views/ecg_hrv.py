"""Seite: EKG & HRV — RR-Analyse, Frequenzdomäne, Laborwert-Befund, Exporte."""

import io
import os
from typing import Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from scipy.signal import find_peaks as _fp

from core.shared import ecg_figure, window_nav_controls, get_edf_or_stop, get_patient_info, section_header, render_banner, status_dot, kpi_tile


def _section(title: str, subtitle: str = "") -> None:
    section_header(title, subtitle)


def _select_stablest_window(r_times: np.ndarray, rr_ms: np.ndarray,
                            win_s: float = 180.0) -> float:
    """Finde den Startzeitpunkt des stationärsten win_s-Fensters.

    Stationarität = geringster linearer Trend der RR-Intervalle innerhalb des
    Fensters (kleinste |Steigung|). Bestraft driftende Herzfrequenz (Bewegung,
    Weckreaktion), nicht die kurzfristige Variabilität selbst — daher besser als
    ein reiner Varianz-Vergleich, der echte HRV fälschlich abwerten würde.
    Kandidaten-Starts werden in 15-s-Schritten geprüft.
    """
    t0, t_end = float(r_times[0]), float(r_times[-1])
    if t_end - t0 <= win_s:
        return t0
    best_start, best_slope = t0, np.inf
    for start in np.arange(t0, t_end - win_s + 1e-6, 15.0):
        m = (r_times >= start) & (r_times <= start + win_s)
        if int(np.sum(m)) < 10:
            continue
        tt = r_times[m] - r_times[m][0]
        rr = rr_ms[m]
        # Lineare Regressionssteigung (ms pro s), normiert auf mittleres RR
        slope = abs(np.polyfit(tt, rr, 1)[0]) / (np.mean(rr) + 1e-9)
        if slope < best_slope:
            best_slope, best_start = slope, float(start)
    return best_start


@st.cache_data(show_spinner="Berechne R-Peaks…")
def compute_rr(path, channel):
    """R-Peak-Erkennung via QRS-Band-Detektor (Pan-Tompkins, 5–15 Hz) mit
    Fiducial-Refinement auf den echten R-Zacken-Scheitel. Präzisere R-Timing-
    Bestimmung als eine Betragssignal-Schwelle → korrektes RMSSD/pNN50.
    Danach 4-stufige robuste Artefakt-Bereinigung der RR-Reihe."""
    from core.loader import load_edf
    from analysis.ecg import detect_r_peaks_polarity_safe
    import warnings; warnings.filterwarnings("ignore")
    _raw = load_edf(path, preload=True)
    _data, _ = _raw[:]
    _idx = _raw.ch_names.index(channel)
    fs = _raw.info["sfreq"]
    sig = _data[_idx].copy().astype(np.float64)
    sig -= sig.mean()

    # Polaritäts-Flip + Nachverfeinerung über den gemeinsamen, getesteten Helfer (analysis/ecg.py
    # — auch von views/rhythm_screening.py genutzt, damit beide Pfade konsistent bleiben).
    # Hintergrund (User-Fund 2026-08-08, siehe [[project_edf_rhythm_screening]]): die interne
    # argmax-Verfeinerung von detect_r_peaks() springt bei invertiertem Kanal (z. B. POL X1 in
    # diesem Aufnahmesystem — systematische Konvention, kein Einzelfall) NICHT zufällig, sondern
    # STRUKTURIERT neben die echte R-Zacke (auf Nebenpunkte wie T-Wellen-Anflanken) — sichtbar
    # als mehrere parallele Bänder im Tachogramm/Poincaré statt einer glatten Verteilung.
    sig, peaks, was_flipped = detect_r_peaks_polarity_safe(sig, fs)

    # Anzeigesignal (0.5–40 Hz) — nur für Amplitude & Polarität der Peaks. Auf dem bereits
    # korrekt orientierten `sig` berechnet, damit ▲/▼-Marker konsistent zur Polarität sind.
    from scipy.signal import butter, filtfilt
    nyq = fs / 2
    b, a = butter(4, [0.5/nyq, min(40/nyq, 0.99)], btype="band")
    sig_f = filtfilt(b, a, sig)

    # Polarität & Amplitude der Peaks aus dem Anzeigesignal (für ▲/▼ und Referenz)
    if len(peaks):
        polarities  = np.sign(sig_f[peaks])
        peak_amps   = np.abs(sig_f[peaks])
        peak_ref    = float(np.median(peak_amps))
    else:
        polarities  = np.array([], dtype=float)
        peak_ref    = 0.0
    threshold = peak_ref  # informativer Referenzwert (median R-Amplitude) für UI

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
        "threshold_mv": threshold * 1000, "peak_ref_mv": peak_ref * 1000,
        "n_peaks_total": len(peaks), "n_removed": n_removed, "was_flipped": was_flipped,
    }


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def render():
    st.title(":material/favorite: EKG & HRV")

    # ── Imports & Konstanten (für Closures) ───────────────────────────────────
    from analysis.hrv_reference import (
        classify_parameter, classify_parameter_pediatric,
        compute_autonomic_balance, MARKER_TYPE, LF_HF_MEAN, LF_HF_SD,
        BADGE_PARA, BADGE_SYMP, BADGE_NONE, PEDIATRIC_AGE_GROUPS,
        pnn50_expected_from_rmssd, POOLED_REFERENCE, _iqr_sigma,
    )
    import math as _math
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

    def _build_ans_state_fig(hr: float, rmssd_val: float, fd_dict: Optional[dict],
                             sdnn_val: Optional[float] = None,
                             pnn50_val: Optional[float] = None,
                             height: int = 500,
                             duration_s: Optional[float] = None) -> tuple:
        """
        2D ANS-Statusdiagramm mit SDNN-Leiste.
        X = sympathische Aktivierung, Y = vagale Aktivierung (je σ relativ Norm).
        Rautengröße = globale ANS-Aktivität (SDNN). Gibt (fig, label) zurück.
        """
        from plotly.subplots import make_subplots

        def _z(val: float, median: float, iqr_tuple: tuple) -> float:
            sigma = _iqr_sigma(iqr_tuple)
            return (val - median) / sigma if sigma > 0 else 0.0

        def _z_log(val: float, median: float, iqr_tuple: tuple) -> float:
            """Z-Score für log-normalverteilte Parameter (HF/LF Power)."""
            if val <= 0:
                return -3.0
            sigma_log = (_math.log(iqr_tuple[1]) - _math.log(iqr_tuple[0])) / 1.349
            return (_math.log(val) - _math.log(median)) / sigma_log if sigma_log > 0 else 0.0

        # -- Z-Scores --------------------------------------------------------------
        z_rmssd = _z(rmssd_val, POOLED_REFERENCE["rmssd"]["median"],
                     POOLED_REFERENCE["rmssd"]["iqr"])
        z_hr    = _z(hr, POOLED_REFERENCE["heart_rate"]["median"],
                     POOLED_REFERENCE["heart_rate"]["iqr"])
        z_sdnn  = _z(sdnn_val, POOLED_REFERENCE["sdnn"]["median"],
                     POOLED_REFERENCE["sdnn"]["iqr"]) if sdnn_val is not None else 0.0

        # pNN50: grobe Populationsschätzung (Median ~12%, SD ~12% für Kurzzeit-HRV)
        z_pnn50 = (pnn50_val - 12.0) / 12.0 if pnn50_val is not None else None

        # HF Power: log-normiert (POOLED_REFERENCE["hf_power"] = median 100, IQR (38,263) ms²)
        hf_power = fd_dict.get("hf_power") if fd_dict else None
        z_hf = _z_log(hf_power, POOLED_REFERENCE["hf_power"]["median"],
                      POOLED_REFERENCE["hf_power"]["iqr"]) if hf_power and hf_power > 0 else None

        lf_hf = fd_dict["lf_hf_ratio"] if fd_dict and not _math.isnan(
            fd_dict.get("lf_hf_ratio", float("nan"))) else None
        z_lfhf = (lf_hf - LF_HF_MEAN) / LF_HF_SD if lf_hf is not None else None

        # -- Projektion in 2D-Ereignisraum ----------------------------------------
        # Vagale Marker → Richtung oben-links  (x = -z*0.3, y = +z)
        # Balance/Symp.  → Richtung unten-rechts (x = +z,    y = -z*0.25)
        # HR als Surrogat → kleinere Gewichtung (marker size 10 statt 14)
        pts: list = []  # (x, y, name, hover_val, color, size, weight)

        pts.append((-z_rmssd * 0.30,  z_rmssd,        "RMSSD",  f"{rmssd_val:.1f} ms", "#1a5276", 14, 1.0))

        if z_pnn50 is not None:
            pts.append((-z_pnn50 * 0.25, z_pnn50,      "pNN50",  f"{pnn50_val:.1f} %",  "#2e86c1", 14, 1.0))

        if z_hf is not None:
            pts.append((-z_hf * 0.28,    z_hf * 0.85,  "HF-Power", f"{hf_power:.0f} ms²", "#1abc9c", 13, 0.85))

        if z_lfhf is not None:
            pts.append((z_lfhf,          -z_lfhf * 0.25, "LF/HF",  f"{lf_hf:.2f}",        "#7d3c98", 14, 1.0))

        # HR: Surrogat mit halber Gewichtung und kleinerem Marker
        pts.append((z_hr * 0.45,      -z_hr * 0.38,   "HR*",    f"{hr:.0f} bpm",        "#b03a2e", 10, 0.5))

        # -- Schwerpunkt (gewichtet) -----------------------------------------------
        total_w = sum(p[6] for p in pts)
        cx = sum(p[0] * p[6] for p in pts) / total_w
        cy = sum(p[1] * p[6] for p in pts) / total_w
        dist = _math.sqrt(cx**2 + cy**2)

        if dist < 0.6:
            label, c_color = "ausgeglichen", "#1e8449"
        elif cx < 0 and cy > 0:
            s = "leicht " if dist < 1.4 else ("mäßig " if dist < 2.0 else "stark ")
            label, c_color = s + "parasympathikoton", "#1a5276"
        elif cx > 0 and cy < 0:
            s = "leicht " if dist < 1.4 else ("mäßig " if dist < 2.0 else "stark ")
            label, c_color = s + "sympathikoton", "#922b21"
        elif cx < 0 and cy < 0:
            label, c_color = "ANS-Dämpfung", "#555"
        else:
            label, c_color = "gemischt erhöht", "#27ae60"

        # Rautengröße aus SDNN: z=0 → size 20, z=-2 → 12, z=+2 → 28
        diamond_size = max(10, min(32, int(20 + z_sdnn * 4)))

        # -- Figur aufbauen (Subplots: Scatter oben, SDNN-Leiste unten) -----------
        LMAX = 3.2
        fig = make_subplots(
            rows=2, cols=1,
            row_heights=[0.84, 0.16],
            vertical_spacing=0.06,
        )

        # Quadranten-Hintergrund (row 1)
        for x0, x1, y0, y1, col in [
            (-LMAX, 0, 0, LMAX, "rgba(41,128,185,0.07)"),
            (0, LMAX, -LMAX, 0, "rgba(192,57,43,0.07)"),
            (-LMAX, 0, -LMAX, 0, "rgba(100,100,100,0.04)"),
            (0, LMAX, 0, LMAX, "rgba(39,174,96,0.04)"),
        ]:
            fig.add_shape(type="rect", x0=x0, x1=x1, y0=y0, y1=y1,
                          fillcolor=col, line_width=0, row=1, col=1)

        # Referenzkreise ±1σ / ±2σ
        _th = [i * 2 * _math.pi / 64 for i in range(65)]
        for r, col, dash in [(1.0, "#27ae60", "dot"), (2.0, "#f39c12", "dot")]:
            fig.add_trace(go.Scatter(
                x=[_math.cos(t) * r for t in _th], y=[_math.sin(t) * r for t in _th],
                mode="lines", line=dict(color=col, width=1.2, dash=dash),
                showlegend=False, hoverinfo="skip",
            ), row=1, col=1)

        # Achsenlinien
        for shape_args in [
            dict(type="line", x0=-LMAX, x1=LMAX, y0=0, y1=0),
            dict(type="line", x0=0, x1=0, y0=-LMAX, y1=LMAX),
        ]:
            fig.add_shape(**shape_args, line=dict(color="#ddd", width=1), row=1, col=1)

        # Parameter-Punkte
        for px, py, pn, pv, pc, ps, _ in pts:
            fig.add_trace(go.Scatter(
                x=[px], y=[py], mode="markers+text",
                text=[pn], textposition="top center",
                textfont=dict(size=9, color=pc),
                marker=dict(size=ps, color=pc, symbol="circle",
                            line=dict(width=1.5, color="white")),
                hovertemplate=f"<b>{pn}</b>: {pv}<extra></extra>",
                showlegend=False,
            ), row=1, col=1)

        # Schwerpunkt-Raute (Größe = SDNN)
        fig.add_trace(go.Scatter(
            x=[cx], y=[cy], mode="markers+text",
            text=[label], textposition="bottom center",
            textfont=dict(size=11, color=c_color),
            marker=dict(size=diamond_size, color=c_color, symbol="diamond",
                        line=dict(width=2, color="white")),
            hovertemplate=(f"<b>ANS-Tendenz: {label}</b>"
                           f"<br>Rautengröße ~ SDNN: {sdnn_val:.0f} ms (z={z_sdnn:+.1f})"
                           f"<extra></extra>"),
            showlegend=False,
        ), row=1, col=1)

        # Quadranten-Labels
        for ax, ay, atext, acol, axanchor, ayanchor in [
            (-LMAX + 0.1, LMAX - 0.15, "Parasympathikoton", "#1a5276", "left", "top"),
            (0.1, -LMAX + 0.15, "Sympathikoton", "#922b21", "left", "bottom"),
            (-LMAX + 0.1, -LMAX + 0.15, "ANS-Dämpfung", "#666", "left", "bottom"),
        ]:
            fig.add_annotation(x=ax, y=ay, text=atext, showarrow=False,
                               font=dict(size=9, color=acol), opacity=0.55,
                               xanchor=axanchor, yanchor=ayanchor, row=1, col=1)

        # σ-Kreisbeschriftungen
        for r, col_c in [(1.0, "#27ae60"), (2.0, "#f39c12")]:
            fig.add_annotation(
                x=_math.cos(_math.pi / 4) * r + 0.08,
                y=_math.sin(_math.pi / 4) * r,
                text=f"±{r:.0f}σ", showarrow=False,
                font=dict(size=8, color=col_c), opacity=0.7,
                row=1, col=1,
            )

        # -- SDNN-Leiste (row 2) --------------------------------------------------
        # Asymmetrisch: links rot (niedrig = schlecht), rechts blau (hoch = günstig)
        BMAX = 3.0
        for bx0, bx1, bc in [
            (-BMAX, -2.0, "rgba(192,57,43,0.25)"),   # zu niedrig → rot
            (-2.0,  -1.0, "rgba(241,196,15,0.25)"),   # grenzwertig niedrig → gelb
            (-1.0,   1.0, "rgba(39,174,96,0.20)"),    # normal → grün
            (1.0,    2.0, "rgba(52,152,219,0.15)"),   # erhöht → hellblau (günstig)
            (2.0,   BMAX, "rgba(52,152,219,0.28)"),   # stark erhöht → blau (günstig, aber Hinweis)
        ]:
            fig.add_shape(type="rect", x0=bx0, x1=bx1, y0=-1, y1=1,
                          fillcolor=bc, line_width=0, row=2, col=1)

        sdnn_z_clamped = max(-BMAX + 0.1, min(BMAX - 0.1, z_sdnn))
        # Farbe: links = Warnung, rechts = Info (nicht Alarm)
        if sdnn_z_clamped >= 2.0:
            sdnn_color = "#2471a3"   # blau: erhöht, aber günstig
        elif sdnn_z_clamped >= 1.0:
            sdnn_color = "#5dade2"   # hellblau
        elif sdnn_z_clamped >= -1.0:
            sdnn_color = "#27ae60"   # grün: normal
        elif sdnn_z_clamped >= -2.0:
            sdnn_color = "#f39c12"   # gelb: grenzwertig niedrig
        else:
            sdnn_color = "#c0392b"   # rot: zu niedrig
        sdnn_label = f"SDNN {sdnn_val:.0f} ms" if sdnn_val else "SDNN n/v"
        # Hinweis bei langer Aufnahme (>10 min → Normwerte nur bedingt vergleichbar)
        long_rec = duration_s is not None and duration_s > 600
        hover_suffix = " · Norm für 5-min-EEG — bei Langzeitableitung erwartet erhöht" if long_rec and z_sdnn > 1.0 else ""
        display_label = f"{sdnn_label}{'*' if long_rec and z_sdnn > 1.0 else ''}"
        fig.add_trace(go.Scatter(
            x=[sdnn_z_clamped], y=[0], mode="markers+text",
            text=[display_label], textposition="top center",
            textfont=dict(size=9, color=sdnn_color),
            marker=dict(size=12, color=sdnn_color, symbol="diamond",
                        line=dict(width=1.5, color="white")),
            hovertemplate=f"SDNN: {sdnn_label} · z={z_sdnn:+.2f}{hover_suffix}<extra></extra>",
            showlegend=False,
        ), row=2, col=1)
        fig.add_shape(type="line", x0=0, x1=0, y0=-1, y1=1,
                      line=dict(color="#ddd", width=1), row=2, col=1)

        # -- Layout ---------------------------------------------------------------
        fig.update_layout(
            height=height,
            margin=dict(t=16, b=10, l=60, r=16),
            plot_bgcolor="white",
            showlegend=False,
        )
        fig.update_xaxes(
            range=[-LMAX, LMAX], zeroline=False, showgrid=False,
            tickvals=[-2, -1, 0, 1, 2], ticktext=["−2σ", "−1σ", "0", "+1σ", "+2σ"],
            title=dict(text="Sympathische Aktivierung →", font=dict(size=10), standoff=4),
            row=1, col=1,
        )
        fig.update_yaxes(
            range=[-LMAX, LMAX], zeroline=False, showgrid=False,
            tickvals=[-2, -1, 0, 1, 2], ticktext=["−2σ", "−1σ", "0", "+1σ", "+2σ"],
            title=dict(text="Vagale Aktivierung →", font=dict(size=10), standoff=4),
            row=1, col=1,
        )
        fig.update_xaxes(
            range=[-BMAX, BMAX], zeroline=False, showgrid=False,
            tickvals=[-2, -1, 0, 1, 2], ticktext=["−2σ", "−1σ", "0", "+1σ", "+2σ"],
            title=dict(text="Globale ANS-Aktivität (SDNN) →", font=dict(size=9), standoff=3),
            row=2, col=1,
        )
        fig.update_yaxes(visible=False, row=2, col=1)
        return fig, label, z_sdnn

    _ANS_LEGEND = (
        "**Wie lesen Sie das Diagramm?**  \n"
        "**Punkte** (●) = einzelne HRV-Parameter, normiert auf Bevölkerungsmedian "
        "(0 = Norm, ±1σ/±2σ = übliche Streuung). "
        "Vagale Marker (RMSSD, pNN50, HF-Power) zeigen nach **oben-links** = parasympathikoton; "
        "Balance-Marker (LF/HF, HR\\*) nach **unten-rechts** = sympathikoton.  \n"
        "**◆ Raute** = gewichteter Schwerpunkt aller Punkte — zeigt die **autonome Gesamttendenz**. "
        "Die **Größe** der Raute spiegelt die **globale ANS-Aktivität (SDNN)** wider: "
        "große Raute = kräftiges, aktives ANS; kleine Raute = gedämpfte Gesamtaktivität.  \n"
        "**Grüner Kreis** = ±1σ Normbereich · **Gelber Kreis** = ±2σ Grenzbereich.  \n"
        "**SDNN-Leiste** (unten): Gesamtstärke des ANS unabhängig von der Sympathikus/Parasympathikus-Balance — "
        "ein separat bewertetes Maß für die kardiovaskuläre Regelkapazität.  \n"
        "\\* HR ist ein indirekter Surrogat-Marker mit halber Gewichtung."
    )

    def render_psd_chart(fd_x, title, line_color):
        # Bei zu kurzer Aufnahme liefert compute_frequency_domain None (< 20 RR-Intervalle)
        # → kein Spektrum zeichenbar. Aufrufer zeigt stattdessen einen Hinweis.
        if not fd_x:
            return None
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
            showlegend=False,
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
        _nn50    = int(np.sum(np.abs(_diff) > 50))
        _pnn50   = float(_nn50 / max(len(_diff), 1) * 100)
        # CV% = SDNN/mean_RR × 100 — direkt aus der RR-Reihe (keine Rundungskaskade)
        _cv      = (_sdnn / _mean_rr * 100.0) if _mean_rr > 0 else 0.0
        # DFA α₁ (nichtlinear) — nur bei ausreichender Schlagzahl
        from analysis.ecg import dfa_alpha1 as _dfa_fn_panel
        _dfa_p   = _dfa_fn_panel(rr_seg)
        _dfa_a1  = _dfa_p["alpha1"] if _dfa_p else float("nan")

        # Task Force 1996: Frequenzdomäne valide ab ≥300 Schlägen (~5 min Ruhe-EKG)
        _FREQ_MIN_BEATS = 300
        _freq_too_short = len(rr_seg) < _FREQ_MIN_BEATS
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

        metrics = {"mean_hr": _mean_hr, "sdnn": _sdnn, "cv": _cv, "rmssd": _rmssd,
                   "pnn50": _pnn50, "nn50": _nn50,
                   "lf": _lf, "hf": _hf, "tp": _tp, "lhr": _lhr}

        try:
            _fig_ans, _ans_lbl, _z_sdnn = _build_ans_state_fig(
                _mean_hr, _rmssd, _fd, sdnn_val=_sdnn, pnn50_val=_pnn50,
                duration_s=edf["duration_s"])
            # "Starre Herzfrequenz"-Warnung (User-Konzept 2026-08-08): die Balance-Achse
            # (vagal↔sympathisch) allein kann einen GLOBALEN Ausfall beider Äste nicht zeigen
            # (LF/HF kann unauffällig aussehen, obwohl beide Pole kollabiert sind — Fall
            # GA2410DH: LF/HF=1,14, sogar unter dem Populationsmittel, trotz RMSSD/SDNN/pNN50
            # praktisch am Boden). WICHTIG: der ursprünglich vorgesehene Trigger SDNN-z<-2
            # (POOLED_REFERENCE-Sigma, nicht altersadjustiert) löst bei GA2410DH selbst NICHT
            # aus (z=-1,22 — das grobe Populations-Sigma ist zu breit) — durch Testlauf entdeckt
            # und korrigiert. Stattdessen direkter, populationsmodell-unabhängiger Trigger:
            # pNN50 nahe 0% UND CV% sehr niedrig — beide beschreiben "praktisch keine Schlag-zu-
            # Schlag-Variabilität" ohne Umweg über ein Referenzmodell. Kalibriert an allen 5
            # Referenzfällen: trennt GA2410DH (pNN50=0,00%/CV=1,9%) sauber von allen anderen,
            # AUCH vom AFib-Fall (hohe statt niedrige Variabilität, löst korrekt nicht aus).
            _rigid_hr = (_pnn50 < 0.5) and (_cv < 3.0)
            if _rigid_hr:
                st.markdown(
                    "<div style='background:#c0392b14;border:2px solid #c0392b;border-radius:10px;"
                    "padding:12px 16px;margin-bottom:10px'>"
                    "<div style='font-size:15px;font-weight:800;color:#c0392b'>"
                    f"{status_dot('danger')} Auffällig starre Herzfrequenz</div>"
                    "<div style='font-size:13px;color:#555;margin-top:4px'>"
                    f"Praktisch keine Schlag-zu-Schlag-Variabilität: pNN50={_pnn50:.2f}% "
                    f"(nahe 0), CV={_cv:.1f}% (sehr niedrig), SDNN={_sdnn:.1f}ms "
                    f"(z={_z_sdnn:+.1f} σ ggü. Population). Das kann auf eine autonome "
                    "Funktionsstörung hindeuten (z. B. Dysautonomie/autonome Neuropathie) — "
                    "<b>unabhängig davon, ob die Balance-Achse unten unauffällig aussieht.</b> "
                    "Bei stark reduzierter Gesamtaktivität sind vagale UND sympathische Marker "
                    "oft gemeinsam betroffen, wodurch die reine Richtungsaussage (vagal/"
                    "sympathisch) wenig über das eigentliche Ausmaß aussagt. Bitte die "
                    "Einzelwerte unten (RMSSD, SDNN, pNN50, LF/HF) gezielt gegenprüfen und "
                    "klinisch korrelieren.</div></div>", unsafe_allow_html=True)
            st.plotly_chart(_fig_ans, use_container_width=True)
            st.markdown(
                f"<div style='text-align:center;font-size:15px;margin-top:-10px'>"
                f"ANS-Tendenz: <b>{_ans_lbl}</b></div>",
                unsafe_allow_html=True,
            )
            with st.expander("Diagramm-Erklärung", icon=":material/info:"):
                st.markdown(_ANS_LEGEND)
        except Exception:
            pass

        if sdnn_warning:
            st.warning(
                "**SDNN kompromittiert** — Atemfrequenz während HV > 0.4 Hz verschiebt die "
                "respiratorische Sinusarrhythmie aus dem HF-Band. SDNN steigt mechanisch. "
                "Wert wird angezeigt, ist aber **nicht mit Ruhewerten vergleichbar**."
            )
        if _freq_too_short:
            st.warning(
                f"**Frequenzdomäne eingeschränkt** — nur {len(rr_seg)} Schläge analysiert. "
                f"Task Force 1996 fordert ≥ 300 Schläge (~5 min) für valide LF/HF-Werte. "
                f"LF, HF und LF/HF sind orientierend — **nicht für klinische Entscheidungen geeignet**."
            )
        elif freq_warning:
            st.info(
                "Frequenzdomäne (LF/HF/Total) in diesem Segment methodisch eingeschränkt: "
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
                f"**HF-Band biologisch ungültig** — Atemfrequenz-Gipfel liegt bei "
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
            "cv":           "HF-normierte Gesamtvariabilität (SDNN/RR) — entkoppelt SDNN von der Herzfrequenz",
            "nn50":         "Absolutzahl zu pNN50 — NeuroFax gibt beide aus",
            "dfa_a1":       "Nichtlinear: fraktale Struktur statt Größe der RR-Schwankungen",
        }

        lab_groups = [
            ("Ebene 1 — Signalvalidität & Physiologie", [
                ("heart_rate",   "Herzfrequenz",              _mean_hr,  "bpm"),
                ("hf_resp_rate", "Atemfrequenz (HF-Gipfel)",  _resp,     "/min"),
                ("pnn50",        "pNN50  (Konkordanz-Check)", _pnn50,    "%"),
                ("nn50",         "NN50  (Absolutzahl)",       _nn50,     ""),
            ]),
            ("Ebene 2 — Zeitbereich (robust, bandunabhängig)", [
                ("rmssd", "RMSSD", _rmssd, "ms"),
                ("sdnn",  "SDNN",  _sdnn,  "ms"),
                ("cv",    "CV (Variationskoeffizient)", _cv, "%"),
                ("dfa_a1", "DFA α₁ (nichtlinear/fraktal)", _dfa_a1, ""),
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
                    st.caption("nicht berechenbar — Segment zu kurz oder Artefakte")
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
                    elif pnn50_exp is not None:
                        # RMSSD selbst sehr niedrig (pnn50_exp<2%) — Zone kommt jetzt aus
                        # RMSSDs EIGENER Klassifikation (User-Fund 2026-08-08, siehe
                        # analysis/hrv_reference.py), kein neutraler Flach-Balken mehr.
                        zones = [(0, cls["scale_max"], cls["zone"])]
                    else:
                        zones = [(0, cls["scale_max"], "info")]
                elif key == "heart_rate":
                    zones = [
                        (0,    40,   "pathologisch"),
                        (40,   60,   "grenzwertig"),
                        (60,  100,   "normal"),
                        (100, 140,   "grenzwertig"),
                        (140, cls["scale_max"], "pathologisch"),
                    ]
                elif key in ("lf_norm", "hf_norm"):
                    ref_lo = cls["ref_lo"] or 0
                    ref_hi = cls["ref_hi"] or cls["scale_max"]
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
                elif key == "nn50":
                    # Absolutzahl ist längenabhängig → neutraler Info-Balken;
                    # die klinische Wertung (Marker-Farbe) kommt aus der pNN50-Zone.
                    zones = [(0, cls["scale_max"], "info")]
                elif key == "dfa_a1":
                    # Zweiseitig: gesund ~1,0, auffällig sowohl <0,75 als auch >1,25
                    zones = [
                        (0.0,  0.5,  "pathologisch"),
                        (0.5,  0.75, "grenzwertig"),
                        (0.75, 1.25, "normal"),
                        (1.25, 1.5,  "grenzwertig"),
                        (1.5,  cls["scale_max"], "pathologisch"),
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

                # NN50: Marker-Farbe aus der pNN50-Zone (gleicher vagaler Prozess),
                # da die Absolutzahl selbst keine feste Populationsgrenze hat.
                _marker_zone = cls["zone"]
                if key == "nn50":
                    _pn_cls = _classify("pnn50", _pnn50, patient_age, _mean_hr, rmssd=_rmssd)
                    _marker_zone = _pn_cls["zone"]

                fig_row.add_trace(go.Scatter(
                    x=[value], y=[0], mode="markers",
                    marker=dict(symbol="diamond", size=16, color=ZONE_COLOR[_marker_zone],
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
                    if key == "nn50":
                        _pn_badge = {"pathologisch": status_dot("danger"), "grenzwertig": status_dot("warning"),
                                     "normal": status_dot("success"), "info": status_dot("neutral")}[_marker_zone]
                        st.caption(
                            f"{_pn_badge} **{int(round(value))}** Intervalle > 50 ms · "
                            f"Absolutzahl (längenabhängig) — klinische Wertung folgt pNN50 "
                            f"(Marker in pNN50-Farbe)", unsafe_allow_html=True
                        )
                    else:
                        ref_range = ("Mayer-Wellen ~0.07–0.12 Hz"
                                     if key == "lf_peak_freq" else "deskriptiv")
                        st.caption(f"{status_dot('neutral')} **{value:.3f} {unit}** · {ref_range}", unsafe_allow_html=True)
                else:
                    badge    = {"pathologisch": status_dot("danger"), "grenzwertig": status_dot("warning"),
                                "normal": status_dot("success")}[cls["zone"]]
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
                    elif key == "dfa_a1":
                        norm_txt = "· gesund ~1,0 (0,75–1,25) · <0,5 od. >1,5 auffällig [Peng 1995]"
                    elif cls["p5_threshold"] is not None:
                        norm_txt = f"· 5. Perz.: {cls['p5_threshold']:.1f} {unit} [{ref_src}]"
                    else:
                        norm_txt = ""
                    st.caption(f"{badge} **{value:.1f} {unit}** · {cls['zone']}{sev_text}{dir_text} {norm_txt}",
                               unsafe_allow_html=True)

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
            "**Kein EKG-Kanal automatisch erkannt.** "
            "Bitte wähle manuell einen Kanal aus der Liste — das EKG-Signal hat typisch "
            "0.5–5 mV Peak-to-Peak und zeigt eine regelmäßige Pulsfrequenz (40–160/min)."
        )
        with st.expander("Diagnose — warum wurde kein Kanal erkannt?", icon=":material/search:", expanded=False):
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
            from analysis.ecg import detect_polarity_flip
            _idx = edf["ch_idx"][manual_ch]
            sig_raw = edf["data"][_idx].copy().astype(float)
            sig_raw -= sig_raw.mean()
            # Polaritäts-sicherer Pfad (User-Audit 2026-08-08) — dieselbe Logik wie
            # core/shared.py, hier dupliziert für manuell gewählte Kanäle. Siehe
            # [[project_edf_rhythm_screening]].
            if detect_polarity_flip(sig_raw, sfreq):
                sig_raw = -sig_raw
            nyq = sfreq / 2
            bb, aa = _b(4, [0.5/nyq, min(40/nyq, 0.99)], btype="band")
            edf["ecg_filtered"][manual_ch] = _f(bb, aa, sig_raw)
        ecg_channels = [manual_ch]
        st.info(f"Analysiere Kanal **{manual_ch}** — bitte EKG-Spur visuell prüfen.")

    _SENS_OPTIONS = [0.3, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0, 10.0]
    if "ecg_sens_idx" not in st.session_state:
        st.session_state.ecg_sens_idx = 6  # default: 3.0 mV

    col_ch, col_lp = st.columns([3, 2])
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
        from analysis.ecg import detect_polarity_flip as _dpf2
        _idx2 = edf["ch_idx"][ecg_ch]
        sig_raw2 = edf["data"][_idx2].copy().astype(float)
        sig_raw2 -= sig_raw2.mean()
        # Polaritäts-sicherer Pfad (User-Audit 2026-08-08), siehe [[project_edf_rhythm_screening]]
        if _dpf2(sig_raw2, sfreq):
            sig_raw2 = -sig_raw2
        nyq2 = sfreq / 2
        bb2, aa2 = _b2(4, [0.5/nyq2, min(40/nyq2, 0.99)], btype="band")
        edf["ecg_filtered"][ecg_ch] = _f2(bb2, aa2, sig_raw2)

    lp_options = {"Kein Tiefpass": None, "25 Hz": 25, "15 Hz": 15, "10 Hz": 10}
    lp_label = col_lp.selectbox("Tiefpass-Filter", list(lp_options.keys()), index=1,
                                 help="Glättet die Kurve — kein Einfluss auf Herzrhythmus")
    lp_hz = lp_options[lp_label]

    # ── Nav-CSS (einmalig pro Render) ─────────────────────────────────────────
    st.markdown("""
<style>
/* EKG-Navigationsleiste */
[data-testid="baseButton-secondary"] {
    min-height: 46px !important;
    font-weight: 700 !important;
    background-color: #eef2ff !important;
    color: #1a3a6b !important;
    border: 1px solid #c3d0f0 !important;
    border-radius: 8px !important;
}
[data-testid="baseButton-secondary"] p {
    font-size: 18px !important;
    font-weight: 700 !important;
    margin: 0 !important;
    text-align: center !important;
    width: 100% !important;
}
[data-testid="baseButton-secondary"]:hover:not(:disabled) {
    background-color: #dce8ff !important;
    border-color: #8aa4e0 !important;
    color: #0d2a5a !important;
}
[data-testid="baseButton-secondary"]:disabled {
    background-color: #f5f7ff !important;
    border-color: #e0e6f8 !important;
}
[data-testid="baseButton-secondary"]:disabled p {
    color: #b0bedd !important;
}
</style>
""", unsafe_allow_html=True)

    # ── Sensitivitäts-Kontrolle (Ausschlag-Skalierung, unabhängig von der Nav) ─────
    def _ecg_sens_bar(loc: str):
        """Sensitivitäts-Kontrolle (±mV-Skalierung). loc='top'|'bottom' für eindeutige Keys."""
        _si = st.session_state.ecg_sens_idx
        csm, csv, csp = st.columns([1.6, 3.2, 1.6])
        with csm:
            _prev_s = f"→ ±{_SENS_OPTIONS[max(0, _si-1)]:.3g} mV" if _si > 0 else ""
            if st.button("−", key=f"en_sm_{loc}", disabled=(_si == 0),
                         help=f"Ausschlag vergrößern {_prev_s}",
                         use_container_width=True):
                st.session_state.ecg_sens_idx -= 1; st.rerun()
        with csv:
            st.markdown(
                f"<div style='text-align:center;padding:7px 4px 6px;"
                f"background:#f0faf0;border-radius:8px;border:1px solid #a8d5a8;line-height:1.4'>"
                f"<span style='font-size:10px;color:#4a7a4a;letter-spacing:.5px'>SENS.</span><br>"
                f"<b style='font-size:15px;color:#1a5c1a'>±{_SENS_OPTIONS[_si]:.3g}&thinsp;mV</b>"
                f"</div>", unsafe_allow_html=True,
            )
        with csp:
            _next_s = f"→ ±{_SENS_OPTIONS[min(len(_SENS_OPTIONS)-1, _si+1)]:.3g} mV" if _si < len(_SENS_OPTIONS)-1 else ""
            if st.button("＋", key=f"en_sp_{loc}", disabled=(_si >= len(_SENS_OPTIONS) - 1),
                         help=f"Ausschlag verkleinern {_next_s}",
                         use_container_width=True):
                st.session_state.ecg_sens_idx += 1; st.rerun()

    # Ganze Aufnahme geplottet (kein Ausschneiden mehr nötig) — zwei einfache Regler
    # (Fensterbreite + Position) steuern die Ansicht zuverlässig; der native Plotly-
    # Rangeslider unter dem Chart bleibt als zusätzliche Scroll-Möglichkeit erhalten.
    t_s_ecg, ecg_window_sec = window_nav_controls(edf, "ep_ecg")
    _ecg_sens_bar("top")
    sensitivity_mv = _SENS_OPTIONS[st.session_state.ecg_sens_idx]
    t_ecg    = np.arange(edf["n_samples"]) / sfreq

    sig      = edf["ecg_filtered"][ecg_ch]
    sig_mv   = sig * 1000

    # Auto-Flip: R-Zacke soll positiv oben sein (über die gesamte Aufnahme entschieden)
    sig_centered_check = sig_mv - np.median(sig_mv)
    if abs(sig_centered_check.min()) > abs(sig_centered_check.max()):
        sig_mv = -sig_mv

    _ecg_view = [t_s_ecg, t_s_ecg + ecg_window_sec]
    fig_ecg  = ecg_figure(t_ecg, sig_mv, sensitivity_mv, lp_hz, view_range=_ecg_view)
    st.plotly_chart(fig_ecg, use_container_width=True)
    st.caption(
        f"Fensterbreite/Position oben einstellen, oder direkt im Regler unter dem Plot "
        f"scrollen ({t_s_ecg:.0f}s–{t_s_ecg + ecg_window_sec:.0f}s)."
    )

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

    # ── Rhythmus-Screening-Verweis (Add-on, ändert die bestehende HRV-Pipeline NICHT) ──
    # Der ausführliche, gestufte AFib-/Ektopie-Disclaimer lebt jetzt AUSSCHLIESSLICH auf der
    # eigenen Rhythmus-Screening-Seite (views/rhythm_screening.py, davor im Seitenmenü) — dort
    # inkl. Sicherheitsstufe (CosEn) UND P-Wellen-Nachweis (Stufe②b). User-Entscheidung
    # 2026-08-08: kein doppelter großer Banner mehr hier, da beide sonst potenziell aus dem
    # Takt geraten (z. B. leicht unterschiedliche Peak-Erkennung) und Redundanz Wartungsrisiko
    # ist. Nur ein leichtgewichtiger Verweis bleibt hier als Sicherheitsnetz für den Fall, dass
    # jemand direkt auf diese Seite navigiert, ohne vorher das Screening zu öffnen. Siehe
    # [[project_edf_rhythm_screening]].
    st.caption(
        "ℹ️ Diese HRV-Analyse setzt einen stabilen Sinusrhythmus voraus. Bei Verdacht auf "
        "Vorhofflimmern oder andere Rhythmusstörungen bitte zuerst die **Rhythmus-Screening**-"
        "Seite (Seitenmenü) prüfen — dort inkl. Sicherheitsstufe und P-Wellen-Nachweis."
    )

    # ── Polaritäts-Hinweis (User-Anfrage 2026-08-08, PRÄZISIERT 2026-08-08 — gleiche Logik/UI
    # wie views/rhythm_screening.py, dort ausführlich hergeleitet + gegengeprüft mit
    # SYNTH_groundtruth.edf, siehe [[project_edf_rhythm_screening]]) ─────────────────────────
    if rr_data.get("was_flipped"):
        render_banner(
            "info", "Kanal-Polaritätskonvention erkannt und für die Darstellung angepasst",
            "Die QRS-Auslenkung ist im Rohsignal dieses Kanals negativ dominant. Das ist bei "
            "diesem Kanal (POL X1) die durchgehende, verlässliche Konvention dieses "
            "Aufnahmesystems — kein Hinweis auf ein Problem bei dieser Ableitung. Für die "
            "Darstellung und Analyse wird die Polarität automatisch so ausgerichtet, dass die "
            "R-Zacke wie klinisch gewohnt nach oben zeigt; alle Zahlen bleiben unverändert gültig.")
        with st.expander("Polaritäts-Check: Analyse mit vs. ohne Korrektur anzeigen", icon=":material/search:"):
            from analysis.ecg import flip_diagnostic
            _sig0 = edf["data"][edf["ch_idx"][ecg_ch]].astype(np.float64)
            _sig0 = _sig0 - _sig0.mean()
            _diag = flip_diagnostic(_sig0, sfreq)
            st.markdown(
                "**Warum das wichtig ist:** Die Peak-Verfeinerung sucht per `argmax()` den "
                "höchsten Punkt in einem ±40ms-Fenster um jeden Kandidaten — das setzt voraus, "
                "dass die R-Zacke positiv ist. Bei einem invertierten Kanal (wie hier) springt "
                "sie stattdessen auf einen zufälligen Nebenpunkt (Überschwinger, T-Wellen-"
                "Anflanke) statt auf die echte R-Zacke. Da dieser Nebenpunkt je nach lokaler "
                "Kurvenform leicht unterschiedlich weit von der echten R-Zacke entfernt liegt, "
                "entstehen keine zufälligen, sondern **strukturierte Zeitfehler** — sichtbar als "
                "mehrere getrennte Bänder/Cluster im Tachogramm, obwohl der echte Rhythmus "
                "glatt und regelmäßig ist."
            )
            _dfig = go.Figure()
            _dfig.add_trace(go.Scatter(x=_diag["t_ohne_s"], y=_diag["rr_ohne_ms"], mode="markers",
                                       marker=dict(size=3, color="#c0392b"),
                                       name=f"ohne Flip (std={_diag['std_ohne']:.0f}ms)"))
            _dfig.add_trace(go.Scatter(x=_diag["t_mit_s"], y=_diag["rr_mit_ms"], mode="markers",
                                       marker=dict(size=3, color="#27ae60"),
                                       name=f"mit Flip-Korrektur (std={_diag['std_mit']:.0f}ms)"))
            _dfig.update_layout(
                title="Tachogramm — RR-Intervalle über die Zeit",
                xaxis_title="Zeit (s)", yaxis_title="RR (ms)", height=340,
                margin=dict(t=40, b=40, l=55, r=10), legend=dict(orientation="h", y=1.12),
            )
            st.plotly_chart(_dfig, use_container_width=True, key="hrv_flip_diag_tacho")
            st.caption(
                "Ohne Korrektur: mehrere parallele Bänder (Peak-Verfeinerung springt auf "
                "Nebenpunkte). Mit Korrektur: eine kompakte, glatte Verteilung — das ist "
                "der Pfad, den diese Seite jetzt tatsächlich verwendet."
            )

    n_total     = rr_data["n_peaks_total"]
    n_removed   = rr_data["n_removed"]
    n_kept      = len(rr_ms)
    pct_removed = n_removed / max(n_kept + n_removed, 1) * 100

    if pct_removed < 5:
        qcolor, qicon, qlabel = "#27ae60", status_dot("success", size=28), "Gute Datenqualität"
    elif pct_removed < 15:
        qcolor, qicon, qlabel = "#f39c12", status_dot("warning", size=28), "Mäßige Datenqualität — Befund mit Vorsicht interpretieren"
    else:
        qcolor, qicon, qlabel = "#c0392b", status_dot("danger", size=28), "Schlechte Datenqualität — HRV-Werte wahrscheinlich nicht valide"

    # ── Analysefenster-Auswahl (nur ohne HV-Protokoll) ────────────────────────
    # Zeitbereichsparameter (v.a. SDNN) und Spektralwerte skalieren mit der
    # Fensterlänge. Für Vergleiche mit NeuroFax-Kurzzeit-HRV (typ. 3 min) kann der
    # User auf ein 3-min-Subfenster einschränken. Das Widget selbst wird weiter unten
    # (bei den Parametern) gerendert; hier wird nur der gespeicherte Wert gelesen,
    # damit die Metriken bereits gefenstert berechnet werden.
    _total_dur_min = float(np.sum(rr_ms) / 60000.0)
    _window_choice = st.session_state.get("hrv_window_choice", "Gesamtaufnahme")
    _window_active = None  # (start_s, end_s) oder None
    if (not has_hv) and _total_dur_min >= 4.5 and _window_choice != "Gesamtaufnahme":
        _t0 = float(r_times[0])
        if _window_choice == "Erste 3 min":
            _w_start = _t0
        else:  # "Stabilste 3 min" — Fenster mit geringstem RR-Trend (Stationarität)
            _w_start = _select_stablest_window(r_times, rr_ms, win_s=180.0)
        _w_end = _w_start + 180.0
        _mask_win = (r_times >= _w_start) & (r_times <= _w_end)
        if int(np.sum(_mask_win)) >= 10:
            rr_ms   = rr_ms[_mask_win]
            r_times = r_times[_mask_win]
            _window_active = (_w_start, _w_end)

    mean_rr = float(np.mean(rr_ms))
    mean_hr = 60000 / mean_rr
    sdnn    = float(np.std(rr_ms, ddof=1))
    _dd     = np.diff(rr_ms)
    rmssd   = float(np.sqrt(np.mean(_dd**2))) if len(_dd) > 0 else 0.0
    _n_diff = max(len(_dd), 1)
    _nn50   = int(np.sum(np.abs(_dd) > 50))
    pnn50   = float(_nn50 / _n_diff * 100)
    # pNN20: sensitiver als pNN50 bei geringer Variabilität (Schwelle 20 ms)
    _nn20   = int(np.sum(np.abs(_dd) > 20))
    pnn20   = float(_nn20 / _n_diff * 100)
    # CV% direkt aus der RR-Zeitreihe (SDNN/mean_RR × 100) — entkoppelt SDNN von der
    # absoluten Herzfrequenz und vermeidet Rundungsfehler aus den Anzeigewerten.
    cv_pct  = (sdnn / mean_rr * 100.0) if mean_rr > 0 else 0.0
    nn50    = _nn50
    # Poincaré-Deskriptoren: SD1 = kurzfristige (vagale) Streuung quer zur Identität,
    # SD2 = langfristige Streuung entlang. SDSD = Std der Sukzessivdifferenzen.
    _sdsd   = float(np.std(_dd, ddof=1)) if len(_dd) > 1 else 0.0
    sd1     = float(np.sqrt(0.5) * _sdsd)
    sd2     = float(np.sqrt(max(2.0 * sdnn**2 - 0.5 * _sdsd**2, 0.0)))
    sd_ratio = (sd2 / sd1) if sd1 > 0 else float("nan")
    # DFA α₁ — fraktaler Kurzzeit-Skalenexponent (nichtlinear)
    from analysis.ecg import dfa_alpha1 as _dfa_fn
    _dfa = _dfa_fn(rr_ms)
    dfa_a1 = _dfa["alpha1"] if _dfa else float("nan")
    # Sample Entropy der RR-Reihe — Komplexität/Regelmäßigkeit (nichtlinear)
    from analysis.complexity import sample_entropy as _sampen_fn
    samp_en = _sampen_fn(rr_ms) if len(rr_ms) >= 20 else float("nan")

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
        seg_label        = (f"Subfenster {_window_active[0]:.0f}–{_window_active[1]:.0f} s"
                            if _window_active is not None else "Gesamtaufnahme")

    # ── Frequenzdomäne (Berechnung) ───────────────────────────────────────────
    from analysis.hrv_freq import compute_frequency_domain, VLF_BAND, LF_BAND, HF_BAND

    BURG_ORDER_DEFAULT = 16
    fd_welch = compute_frequency_domain(rr_ms_analysis, r_times_analysis, method="welch")
    fd_burg  = compute_frequency_domain(rr_ms_analysis, r_times_analysis,
                                        method="burg", burg_order=BURG_ORDER_DEFAULT)
    # Zu kurze Aufnahme (< 20 RR-Intervalle) → compute_frequency_domain gibt None zurück.
    # Das ist korrekt (HRV-Frequenzanalyse braucht Minuten, nicht Sekunden), muss aber
    # überall abgefangen werden, sonst crasht die Seite mit AttributeError auf None.
    _fd_ok = bool(fd_welch or fd_burg)

    def _fdget(fd, key, default=float("nan")):
        """None-sicherer Zugriff auf ein Frequenzdomänen-Dict."""
        return fd.get(key, default) if fd else default

    # ── Steuerelemente (vor Tabs — beeinflussen Figure-Bau) ───────────────────
    freq_method = st.radio(
        "Spektralmethode für HRV-Befund",
        ["Welch (FFT)", "Burg (Maximum Entropy Method)"],
        horizontal=True,
        help="Welch: klassisch, robust. Burg/MEM: schärfere Peaks, kürzer stabil.",
    )
    method_key = "burg" if "Burg" in freq_method else "welch"
    fd = fd_burg if method_key == "burg" else fd_welch

    # ── Figures vorab bauen ───────────────────────────────────────────────────
    # Tachogramm roh
    fig_rr_raw = go.Figure()
    fig_rr_raw.add_trace(go.Scatter(
        x=t_raw[~removed_mask], y=rr_raw[~removed_mask], mode="markers",
        name="behalten", marker=dict(size=3, color="#95a5a6"),
        hovertemplate="t=%{x:.1f}s  RR=%{y:.0f}ms<extra></extra>",
    ))
    fig_rr_raw.add_trace(go.Scatter(
        x=t_raw[removed_mask], y=rr_raw[removed_mask], mode="markers",
        name="Ausreißer", marker=dict(size=7, color="#c0392b", symbol="x"),
        hovertemplate="t=%{x:.1f}s  RR=%{y:.0f}ms (entfernt)<extra></extra>",
    ))
    fig_rr_raw.add_hline(y=mean_rr, line_dash="dot", line_color="#27ae60", line_width=1,
                         annotation_text=f"∅ {mean_rr:.0f}ms", annotation_font_size=10)
    if has_hv:
        add_phase_bands(fig_rr_raw, phases, edf["duration_s"])
    else:
        for ann in edf["annotations"]:
            fig_rr_raw.add_vline(x=ann["onset_s"], line_dash="dot", line_color="#e67e22", line_width=0.8)
    y_lo_raw = max(0, min(mean_rr*0.5, rr_raw.min()*0.9))
    y_hi_raw = max(mean_rr*1.8, rr_raw.max()*1.05)
    fig_rr_raw.update_layout(
        xaxis_title="Zeit (s)", yaxis_title="RR (ms)",
        title=dict(text="Tachogramm — Rohdaten", font=dict(size=12), x=0.02),
        yaxis=dict(range=[y_lo_raw, y_hi_raw]),
        height=300, margin=dict(t=28, b=36, l=54, r=8),
        legend=dict(orientation="h", y=1.18, x=0, font=dict(size=9)),
    )

    # Tachogramm bereinigt
    fig_rr_clean = go.Figure()
    fig_rr_clean.add_trace(go.Scatter(
        x=r_times, y=rr_ms, mode="lines+markers",
        name="bereinigt", line=dict(color="#2980b9", width=1.2),
        marker=dict(size=3, color="#2980b9"),
        hovertemplate="t=%{x:.1f}s  RR=%{y:.0f}ms<extra></extra>",
    ))
    fig_rr_clean.add_hline(y=mean_rr, line_dash="dot", line_color="#27ae60", line_width=1,
                           annotation_text=f"∅ {mean_rr:.0f}ms", annotation_font_size=10)
    if has_hv:
        add_phase_bands(fig_rr_clean, phases, edf["duration_s"])
    fig_rr_clean.update_layout(
        xaxis_title="Zeit (s)", yaxis_title="RR (ms)",
        title=dict(text="Tachogramm — bereinigt", font=dict(size=12), x=0.02),
        yaxis=dict(range=[max(0, mean_rr*0.5), mean_rr*1.8]),
        height=300, margin=dict(t=28, b=36, l=54, r=8),
        legend=dict(orientation="h", y=1.18, x=0, font=dict(size=9)),
    )

    # Poincaré roh
    fig_poin_raw = go.Figure()
    if len(rr_raw) > 1:
        raw_keep_pair = ~(removed_mask[:-1] | removed_mask[1:])
        raw_drop_pair = ~raw_keep_pair
        fig_poin_raw.add_trace(go.Scatter(
            x=rr_raw[:-1][raw_keep_pair], y=rr_raw[1:][raw_keep_pair], mode="markers",
            name="behalten", marker=dict(color="#95a5a6", size=4, opacity=0.55),
            hovertemplate="RRn=%{x:.0f}  RRn+1=%{y:.0f}ms<extra></extra>",
        ))
        fig_poin_raw.add_trace(go.Scatter(
            x=rr_raw[:-1][raw_drop_pair], y=rr_raw[1:][raw_drop_pair], mode="markers",
            name="Ausreißer", marker=dict(color="#c0392b", size=6, symbol="x", opacity=0.7),
            hovertemplate="RRn=%{x:.0f}  RRn+1=%{y:.0f}ms (entfernt)<extra></extra>",
        ))
    lim_raw = [max(0, rr_raw.min()-30), rr_raw.max()+30] if len(rr_raw) else [300, 1200]
    fig_poin_raw.update_layout(
        xaxis=dict(title="RRn (ms)", range=lim_raw),
        yaxis=dict(title="RRn+1 (ms)", range=lim_raw),
        title=dict(text="Poincaré — Rohdaten", font=dict(size=12), x=0.02),
        height=300, margin=dict(t=28, b=36, l=54, r=8),
        legend=dict(orientation="h", y=1.18, x=0, font=dict(size=9)),
    )

    # Poincaré bereinigt
    fig_poin_clean = go.Figure()
    fig_poin_clean.add_trace(go.Scatter(
        x=rr_ms[:-1], y=rr_ms[1:], mode="markers",
        name="bereinigt", marker=dict(color="#8e44ad", size=4, opacity=0.6),
        hovertemplate="RRn=%{x:.0f}  RRn+1=%{y:.0f}ms<extra></extra>",
    ))
    # SD1/SD2-Ellipse (um den Schwerpunkt, 45° zur Identität): halbe Achsen = SD2 (lang) / SD1 (quer)
    if sd1 > 0 and sd2 > 0:
        _t = np.linspace(0, 2 * np.pi, 100)
        _cos, _sin = np.cos(np.pi / 4), np.sin(np.pi / 4)
        _ex, _ey = sd2 * np.cos(_t), sd1 * np.sin(_t)
        _x = mean_rr + _ex * _cos - _ey * _sin
        _y = mean_rr + _ex * _sin + _ey * _cos
        fig_poin_clean.add_trace(go.Scatter(
            x=_x, y=_y, mode="lines", name="SD1/SD2-Ellipse",
            line=dict(color="#e67e22", width=2), hoverinfo="skip",
        ))
        fig_poin_clean.add_annotation(
            x=0.02, y=0.98, xref="paper", yref="paper", showarrow=False,
            align="left", xanchor="left", yanchor="top",
            text=f"SD1 {sd1:.1f} ms · SD2 {sd2:.1f} ms · SD2/SD1 {sd_ratio:.2f}",
            font=dict(size=10, color="#8e44ad"),
            bgcolor="rgba(255,255,255,0.75)", borderpad=3,
        )
    p_lo = max(300, mean_rr * 0.55)
    p_hi = min(2000, mean_rr * 1.55)
    lim_clean = [p_lo - 30, p_hi + 30]
    fig_poin_clean.update_layout(
        xaxis=dict(title="RRn (ms)", range=lim_clean),
        yaxis=dict(title="RRn+1 (ms)", range=lim_clean),
        title=dict(text="Poincaré — bereinigt", font=dict(size=12), x=0.02),
        height=300, margin=dict(t=28, b=36, l=54, r=8),
        legend=dict(orientation="h", y=1.18, x=0, font=dict(size=9)),
    )

    # R-Peak-Overlay — über die GESAMTE Aufnahme (kein Fenster-Ausschnitt mehr nötig,
    # da `fig_ecg` jetzt selbst die ganze Aufzeichnung mit Rangeslider zeigt).
    all_peaks  = rr_data["peaks"]
    all_pols   = rr_data["polarities"]
    fig_ecg_rr = None
    if len(all_peaks) > 0:
        r_t  = all_peaks / sfreq
        r_v  = sig_mv[all_peaks]  # bereits ggf. auto-geflippt, gleiche Skala wie fig_ecg
        symbols = ["triangle-up" if p > 0 else "triangle-down" for p in all_pols]
        colors  = ["#27ae60" if p > 0 else "#e67e22" for p in all_pols]
        fig_ecg_rr = ecg_figure(
            t_ecg, sig_mv, sensitivity_mv, lp_hz, view_range=_ecg_view,
            r_peaks=(r_t, r_v, symbols, colors),
        )

    # PSD-Figures
    fig_psd_welch_obj = render_psd_chart(fd_welch, "Welch (FFT)", "#2c3e50")
    fig_psd_burg_obj  = render_psd_chart(fd_burg,  "Burg (Maximum Entropy Method)", "#6c3483")

    # ANS-Statusdiagramm für PDF und Tab 3
    fig_bal, _ans_label, _z_sdnn_summary = _build_ans_state_fig(
        mean_hr, rmssd, fd, sdnn_val=sdnn, pnn50_val=pnn50,
        duration_s=edf["duration_s"])
    balance = {"label": _ans_label, "index": 0.0}  # index nur noch für PDF-Kompatibilität

    # Ergebnisse für Report-Seite persistieren — inkl. z_sdnn für "starre Herzfrequenz"-Hinweis
    # (User-Konzept 2026-08-08), damit Report-Seite/PDF denselben Befund zeigen können.
    st.session_state["hrv_summary"] = {
        "mean_hr": mean_hr, "sdnn": sdnn, "cv_pct": cv_pct,
        "rmssd": rmssd, "pnn50": pnn50, "nn50": nn50,
        "pct_removed": pct_removed, "quality_label": qlabel,
        "ans_label": _ans_label, "z_sdnn": _z_sdnn_summary, "seg_label": seg_label,
        "fd_welch": fd_welch, "fd_burg": fd_burg,
        "edf_name": os.path.basename(edf_path),
    }

    # ══════════════════════════════════════════════════════════════════════════
    # 4 TABS
    # ══════════════════════════════════════════════════════════════════════════
    st.markdown("""
<style>
/* Prominentere EKG-Tab-Leiste */
div[data-testid="stTabs"] > div:first-child {
    gap: 6px;
    border-bottom: 2px solid #e0e4e8;
    margin-bottom: 4px;
}
div[data-testid="stTabs"] button[role="tab"] {
    font-size: 15px !important;
    font-weight: 600 !important;
    padding: 10px 22px !important;
    border-radius: 10px 10px 0 0 !important;
    border: 1px solid #d0d6de !important;
    border-bottom: none !important;
    background: #f4f6f9 !important;
    color: #555 !important;
    transition: background 0.15s, color 0.15s;
}
div[data-testid="stTabs"] button[role="tab"]:hover {
    background: #e8edf5 !important;
    color: #2c3e50 !important;
}
div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
    background: white !important;
    color: #2980b9 !important;
    border-color: #2980b9 !important;
    border-bottom: 2px solid white !important;
    margin-bottom: -2px;
}
</style>
""", unsafe_allow_html=True)

    tab_rr, tab_freq, tab_befund, tab_hv = st.tabs([
        ":material/show_chart: RR & Zeitdomäne",
        ":material/waves: Frequenzdomäne",
        ":material/assignment: HRV-Befund",
        ":material/air: Hyperventilation",
    ])

    # ── Tab 1: RR & Zeitdomäne ────────────────────────────────────────────────
    with tab_rr:
        _section("RR & Zeitdomäne",
                 "QRS-Erkennung · Zeitdomäne-Parameter · Tachogramm · Poincaré-Plot")
        if has_hv:
            hv_dur = ((phases["hvt_end"] or 0) - (phases["hvt_start"] or 0))
            st.info(
                f"**Hyperventilation automatisch erkannt** · "
                f"HVT START {phases['hvt_start']:.0f}s → END {phases['hvt_end']:.0f}s "
                f"({hv_dur:.0f} s ≈ {hv_dur/60:.1f} min) · "
                f"Post-HV-Fenster: +120 s · "
                + (f"Fotostimulation: {len(phases['photo_events'])} Frequenzschritte"
                   if phases["has_photo"] else "")
            )

        # ── QRS-Erkennung (R-Peak-Overlay) ──────────────────────────────────
        st.markdown("**QRS-Erkennung — aktuelle Epoche mit erkannten R-Peaks**")
        if fig_ecg_rr is not None:
            st.plotly_chart(fig_ecg_rr, use_container_width=True)
            ref_mv = rr_data.get("peak_ref_mv", 0)
            st.caption(
                f"▲ grün = R-Peak aufwärts · ▼ orange = R-Peak abwärts — "
                f"QRS-Band-Detektor (Pan-Tompkins 5–15 Hz, ±40 ms Scheitel-Refinement) · "
                f"mittlere R-Amplitude {ref_mv:.2f} mV"
            )
        else:
            st.info("Keine R-Peaks erkannt — anderen Kanal prüfen.")
        _ecg_sens_bar("bottom")

        st.divider()

        # ── Analysefenster-Auswahl (nur relevant ohne HV & bei langer Aufnahme) ──
        if (not has_hv) and _total_dur_min >= 4.5:
            _wc1, _wc2 = st.columns([2, 3])
            with _wc1:
                st.selectbox(
                    "Analysefenster für Zeitbereichsparameter",
                    options=["Gesamtaufnahme", "Erste 3 min", "Stabilste 3 min"],
                    key="hrv_window_choice",
                    help="SDNN & Spektralwerte skalieren mit der Fensterlänge. "
                         "Für Vergleiche mit NeuroFax-Kurzzeit-HRV (3 min) auf ein "
                         "3-min-Subfenster einschränken.",
                )
            with _wc2:
                if _window_active is not None:
                    st.caption(
                        f"Aktives Fenster: **{_window_active[0]:.0f} – {_window_active[1]:.0f} s** "
                        f"({(_window_active[1]-_window_active[0])/60:.1f} min, {len(rr_ms)+1} Schläge)"
                    )

        # ── Wesentliche Zeitdomäne-Parameter mit Farbkodierung ─────────────
        _win_hdr = (f"Fenster {_window_active[0]:.0f}–{_window_active[1]:.0f} s"
                    if _window_active is not None else "Gesamtaufnahme")
        st.markdown(f"**Wesentliche Zeitdomäne-Parameter ({_win_hdr})**")
        # Zonen-Namen dieser Seite (normal/grenzwertig/pathologisch/info) auf die 5 Standard-
        # Zonen der gemeinsamen Kachel-Komponente gemappt (Phase 3 GUI-Redesign, siehe
        # [[project_edf_ui_redesign]] — ersetzt die vorher hier lokal definierte Variante).
        _zone_map = {"normal": "success", "grenzwertig": "warning",
                    "pathologisch": "danger", "info": "info"}

        def _metric_card(col, label, value_str, zone: str, ref_str: str):
            col.markdown(kpi_tile(label, value_str, ref_str, zone=_zone_map.get(zone, "info")),
                        unsafe_allow_html=True)

        _hr_cls    = _classify("heart_rate", mean_hr,  patient_age, mean_hr)
        _sdnn_cls  = _classify("sdnn",       sdnn,     patient_age, mean_hr)
        _rmssd_cls = _classify("rmssd",      rmssd,    patient_age, mean_hr)
        _pnn50_cls = _classify("pnn50",      pnn50,    patient_age, mean_hr, rmssd=rmssd)

        def _grp(title, sub):
            st.markdown(
                f"<div style='margin:12px 0 3px 0'>"
                f"<span style='font-size:13px;font-weight:700;color:#2c3e50'>{title}</span>"
                f"<span style='font-size:11px;color:#8a94a0;margin-left:8px'>{sub}</span></div>",
                unsafe_allow_html=True)

        def _graded_ref(cls, unit, fallback_p5):
            # Ampel-Grenzen exakt wie in classify_parameter: pathologisch <P5,
            # grenzwertig P5…max(1.5·P5, P5+5), normal (grün) darüber. Text an die
            # angezeigte Farbe koppeln, damit „grün ≥…" nicht der Gelb-Färbung widerspricht.
            p5 = cls.get("p5_threshold") or fallback_p5
            norm = max(p5 * 1.5, p5 + 5.0)
            return f"grün ≥{norm:.0f} · gelb {p5:.0f}–{norm:.0f} {unit}"

        _sdnn_ref  = _graded_ref(_sdnn_cls,  "ms", 40)
        _rmssd_ref = _graded_ref(_rmssd_cls, "ms", 20)
        _pnn50_ref = f"Erw. {_pnn50_cls.get('pnn50_expected', 0):.1f}%" if _pnn50_cls.get('pnn50_expected') else ">3%"

        # Gruppe 1 — Grundwerte
        _grp("Grundwerte", "Herzrate & mittlerer Schlagabstand")
        g1 = st.columns(4)
        _metric_card(g1[0], "HERZFREQUENZ", f"{mean_hr:.1f} bpm", _hr_cls["zone"], "Norm 60–100 bpm")
        _metric_card(g1[1], "MITTL. RR",    f"{mean_rr:.0f} ms",  "info",          "600–1000 ms")

        # Gruppe 2 — Gesamtvariabilität
        _grp("Gesamtvariabilität", "gesamte autonome Streuung (Sympathikus + Parasympathikus)")
        g2 = st.columns(4)
        _metric_card(g2[0], "SDNN", f"{sdnn:.1f} ms",   _sdnn_cls["zone"], _sdnn_ref)
        _metric_card(g2[1], "CV",   f"{cv_pct:.1f} %",  "info",            "= SDNN/RR · HF-unabhängig")

        # Gruppe 3 — Vagale Marker
        _grp("Vagale Marker", "Parasympathikus — schnelle Schlag-zu-Schlag-Variabilität")
        g3 = st.columns(4)
        _metric_card(g3[0], "RMSSD", f"{rmssd:.1f} ms", _rmssd_cls["zone"], _rmssd_ref)
        _metric_card(g3[1], "pNN50", f"{pnn50:.1f} %",  _pnn50_cls["zone"], _pnn50_ref)
        _metric_card(g3[2], "pNN20", f"{pnn20:.1f} %",  "info",            "sensitiver als pNN50")
        _metric_card(g3[3], "NN50",  f"{nn50}",         "info",            "Anzahl > 50 ms")

        # Gruppe 4 — Poincaré-Geometrie
        _grp("Poincaré-Geometrie", "Form der RR-Punktwolke: kurz- vs. langfristige Streuung")
        g4 = st.columns(4)
        _metric_card(g4[0], "SD1",     f"{sd1:.1f} ms", "info", "quer · kurzfristig (vagal)")
        _metric_card(g4[1], "SD2",     f"{sd2:.1f} ms", "info", "entlang · langfristig")
        _metric_card(g4[2], "SD2/SD1", f"{sd_ratio:.2f}" if sd_ratio == sd_ratio else "—",
                     "info", "Balance lang/kurz")

        # Gruppe 5 — Nichtlineare Komplexität
        _grp("Nichtlineare Komplexität", "Struktur & Vorhersagbarkeit statt Größe der Schwankung")
        g5 = st.columns(4)
        if dfa_a1 == dfa_a1:
            _dfa_cls = _classify("dfa_a1", dfa_a1, patient_age, mean_hr)
            _metric_card(g5[0], "DFA α₁", f"{dfa_a1:.2f}", _dfa_cls["zone"], "fraktal · ~1,0 gesund")
        else:
            _metric_card(g5[0], "DFA α₁", "—", "info", "zu wenige Schläge")
        _metric_card(g5[1], "SampEn", f"{samp_en:.2f}" if samp_en == samp_en else "—",
                     "info", "niedrig = regelmäßig")

        # ── Dauer-Confounder-Hinweis ──────────────────────────────────────────
        # SDNN und die Spektralwerte (Total Power, LF) steigen systematisch mit der
        # Aufnahmedauer, weil längere Fenster mehr niederfrequente Schwankungen einfangen.
        # Bei Vergleich mit NeuroFax-Reflextests (typisch 3 min) ist das ein bekannter
        # Confounder — hier explizit vermerkt.
        _dur_min = float(np.sum(rr_ms) / 60000.0)
        if _window_active is not None:
            st.caption(
                f"⏱️ Analyse auf **{_dur_min:.1f}-min-Subfenster** eingeschränkt — "
                f"für Vergleiche mit NeuroFax-Kurzzeit-HRV (3 min) methodisch angeglichen. "
                f"RMSSD/pNN50/CV sind ohnehin kaum dauerabhängig."
            )
        elif _total_dur_min >= 4.5:
            st.caption(
                f"⏱️ **Gesamtaufnahme: {_dur_min:.1f} min.** **Confounder:** SDNN und die "
                f"Spektralwerte (Total/LF Power) steigen systematisch mit der Fensterlänge — "
                f"ein Vergleich mit NeuroFax-Kurzzeit-HRV (typ. 3 min) überschätzt daher SDNN/Power. "
                f"Oben auf ein 3-min-Subfenster einschränken oder die Diskrepanz als bekannten "
                f"Effekt vermerken. RMSSD/pNN50/CV sind weit weniger dauerabhängig."
            )

        st.divider()

        # ── Datenqualität ────────────────────────────────────────────────────
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

        st.divider()

        # ── Tachogramm + Poincaré (je Rohdaten + bereinigt) ────────────────
        col_a, col_b = st.columns(2)
        with col_a:
            st.plotly_chart(fig_rr_raw, use_container_width=True)
        with col_b:
            st.plotly_chart(fig_poin_raw, use_container_width=True)
        col_c, col_d = st.columns(2)
        with col_c:
            st.plotly_chart(fig_rr_clean, use_container_width=True)
        with col_d:
            st.plotly_chart(fig_poin_clean, use_container_width=True)

        # ── Histogramme (User-Idee 2026-08-08): "geometrische" HRV-Methode nach Task Force
        # 1996 — RR-Intervall-Histogramm (→ HRV-Triangulärindex) + ΔRR-Histogramm (macht
        # pNN50/NN50 visuell greifbar, mit den ±50ms-Schwellen eingezeichnet). Rein auf
        # bereits vorhandenen Daten (rr_ms), kein neuer Berechnungspfad — Kosten: 2× np.histogram
        # + 2 Plotly-Bar-Traces, keine spürbare Mehrlast. ─────────────────────────────────────
        if len(rr_ms) >= 10:
            _section("Histogramme", "Geometrische HRV-Darstellung (Task Force 1996)")
            col_h1, col_h2 = st.columns(2)

            with col_h1:
                # Bin-Breite 1000/128 ms ≈ 7,8125ms — Task-Force-Konvention für den
                # HRV-Triangulärindex (Gesamtzahl NN / Höhe des höchsten Balkens).
                _bin_w = 1000.0 / 128.0
                _edges = np.arange(rr_ms.min() - _bin_w, rr_ms.max() + 2 * _bin_w, _bin_w)
                _counts, _edges = np.histogram(rr_ms, bins=_edges)
                _tri_index = len(rr_ms) / _counts.max() if _counts.max() > 0 else float("nan")
                fig_rr_hist = go.Figure()
                fig_rr_hist.add_trace(go.Bar(
                    x=_edges[:-1] + _bin_w / 2, y=_counts, width=_bin_w * 0.9,
                    marker_color="#2471a3", opacity=0.85,
                    hovertemplate="RR≈%{x:.0f}ms · %{y} Schläge<extra></extra>",
                ))
                fig_rr_hist.add_vline(x=mean_rr, line_dash="dot", line_color="#27ae60",
                                      line_width=1.5, annotation_text=f"∅ {mean_rr:.0f}ms",
                                      annotation_font_size=10)
                fig_rr_hist.update_layout(
                    xaxis_title="RR-Intervall (ms)", yaxis_title="Anzahl Schläge",
                    title=dict(text="RR-Intervall-Histogramm", font=dict(size=12), x=0.02),
                    height=280, margin=dict(t=28, b=36, l=54, r=8), showlegend=False,
                )
                st.plotly_chart(fig_rr_hist, use_container_width=True)
                st.caption(f"**HRV-Triangulärindex** ≈ {_tri_index:.1f} (Gesamtzahl NN-Intervalle "
                          "÷ Höhe des höchsten Balkens, Bin-Breite 7,8ms nach Task-Force-1996-"
                          "Konvention) — je höher, desto größer die Gesamtvariabilität, "
                          "unabhängig von der genauen Kurvenform.")

            with col_h2:
                _drr = np.diff(rr_ms)
                if len(_drr) >= 5:
                    _dedges = np.arange(-200, 205, 10.0)
                    _dcounts, _dedges = np.histogram(_drr, bins=_dedges)
                    fig_drr_hist = go.Figure()
                    fig_drr_hist.add_trace(go.Bar(
                        x=_dedges[:-1] + 5.0, y=_dcounts, width=9.0,
                        marker_color="#8e44ad", opacity=0.85,
                        hovertemplate="ΔRR≈%{x:.0f}ms · %{y}×<extra></extra>",
                    ))
                    for _xv in (-50, 50):
                        fig_drr_hist.add_vline(x=_xv, line_dash="dash", line_color="#c0392b",
                                               line_width=1.2)
                    fig_drr_hist.add_annotation(
                        x=0.02, y=0.98, xref="paper", yref="paper", showarrow=False,
                        align="left", xanchor="left", yanchor="top",
                        text=f"pNN50 = {pnn50:.1f}% außerhalb ±50ms (rote Linien)",
                        font=dict(size=10, color="#c0392b"),
                        bgcolor="rgba(255,255,255,0.75)", borderpad=3,
                    )
                    fig_drr_hist.update_layout(
                        xaxis_title="ΔRR — Differenz aufeinanderfolgender Schläge (ms)",
                        yaxis_title="Anzahl",
                        title=dict(text="ΔRR-Histogramm (Sukzessivdifferenzen)",
                                  font=dict(size=12), x=0.02),
                        height=280, margin=dict(t=28, b=36, l=54, r=8), showlegend=False,
                    )
                    st.plotly_chart(fig_drr_hist, use_container_width=True)
                    st.caption("Verteilung der Schlag-zu-Schlag-Differenzen — ein schmaler, hoher "
                              "Peak um 0 zeigt eine sehr geringe Beat-to-Beat-Variabilität "
                              "(\"starre Herzfrequenz\"), eine breite Streuung eine hohe "
                              "vagale Modulation. Macht pNN50/NN50 direkt sichtbar statt nur "
                              "als abstrakte Zahl.")

        # ── DFA α₁ — fraktale Korrelationsstruktur ─────────────────────────────
        _section("DFA α₁ — fraktale Dynamik", "Detrended Fluctuation Analysis (Peng 1995)")
        st.markdown(
            "<div style='background:linear-gradient(90deg,#27ae6014,transparent);"
            "border-left:5px solid #27ae60;border-radius:8px;padding:14px 18px;margin:2px 0 8px 0'>"
            "<div style='font-size:15px;font-weight:800;color:#1e8449'>DFA α₁ ≈ die „Gesundheit\" "
            "der autonomen Regulation — fraktale Ordnung des Herzschlags</div>"
            "<div style='font-size:13px;color:#333;margin-top:5px'>"
            "<b>Warum bestimmen wir das?</b> SDNN/RMSSD messen die <i>Größe</i> der "
            "Herzraten-Schwankung — DFA α₁ misst ihre <b>innere Struktur</b>: Folgen die "
            "Schlagabstände einem komplexen, gesunden Muster oder werden sie zufällig? Eine "
            "gesunde Regulation erzeugt ein <b>1/f-Muster</b> (α₁ ≈ 1,0) — die Balance zwischen "
            "zu starr und rein zufällig. <b>Sinn:</b> einer der <b>robustesten Marker</b> für "
            "körperliche Belastung, Erschöpfung und autonome Integrität — oft aussagekräftiger "
            "als die reine Variabilität.<br>"
            "<b>α₁ → 0,5</b> = Richtung Zufall (Fatigue, autonome Dysregulation, hohe Last) · "
            "<b>α₁ → 1,5</b> = zu starr (Brown'sches Rauschen).<br>"
            "<b>Anwendungen:</b> Fatigue-/Belastungssteuerung · Stress · autonome Dysfunktion · "
            "Prognose bei Herz-/Hirnschädigung.</div></div>",
            unsafe_allow_html=True,
        )
        if _dfa is not None:
            _sc = _dfa["scales"]; _Fv = _dfa["F"]
            _logn = np.log10(_sc); _logF = np.log10(_Fv)
            _b, _a0 = np.polyfit(_logn, _logF, 1)
            _fit = 10 ** (_a0 + _b * _logn)
            _dfa_cls2 = _classify("dfa_a1", dfa_a1, patient_age, mean_hr)
            _dcol = {"normal": "#27ae60", "grenzwertig": "#e67e22",
                     "pathologisch": "#c0392b", "info": "#7f8c8d"}[_dfa_cls2["zone"]]
            dcol1, dcol2 = st.columns([3, 2])
            with dcol1:
                fig_dfa = go.Figure()
                fig_dfa.add_trace(go.Scatter(
                    x=_sc, y=_Fv, mode="markers", name="F(n)",
                    marker=dict(color="#8e44ad", size=8),
                    hovertemplate="n=%{x} Schläge · F(n)=%{y:.1f}<extra></extra>"))
                fig_dfa.add_trace(go.Scatter(
                    x=_sc, y=_fit, mode="lines", name=f"Fit α₁={dfa_a1:.2f}",
                    line=dict(color=_dcol, width=2.4, dash="dash"), hoverinfo="skip"))
                fig_dfa.update_layout(
                    xaxis=dict(title="Fenstergröße n (Schläge)", type="log",
                               tickvals=[4, 6, 8, 11, 16], ticktext=["4", "6", "8", "11", "16"]),
                    yaxis=dict(title="Fluktuation F(n)", type="log"),
                    height=260, margin=dict(t=10, b=40, l=60, r=10),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, font=dict(size=10)),
                )
                st.plotly_chart(fig_dfa, use_container_width=True)
            with dcol2:
                st.markdown(
                    f"<div style='padding:14px 16px;border-radius:10px;border:2px solid {_dcol};"
                    f"background:{_dcol}0d;text-align:center'>"
                    f"<div style='font-size:12px;color:#888'>DFA α₁</div>"
                    f"<div style='font-size:2.2rem;font-weight:800;color:{_dcol}'>{dfa_a1:.2f}</div>"
                    f"<div style='font-size:12px;color:#555'>{_dfa_cls2['direction']}</div></div>",
                    unsafe_allow_html=True,
                )
                st.caption(
                    "**≈1,0** gesunde 1/f-Dynamik · **→0,5** Zufälligkeit "
                    "(Fatigue/autonome Dysregulation) · **→1,5** Brown'sches Rauschen. "
                    "Skalen 4–16 Schläge. *Orientierend.*"
                )
        else:
            st.info("ℹ️ DFA α₁ nicht berechenbar — zu wenige Schläge (mind. ~32 nötig).")

        # ── Atmung: EDR (ECG-Derived Respiration) ──────────────────────────────
        _section("Atmung — EDR", "Aus der R-Zacken-Amplitude rekonstruiert (Moody 1985)")
        from analysis.ecg import edr_from_ecg as _edr_fn
        _edr = None
        if ecg_ch and ecg_ch in edf.get("ecg_filtered", {}):
            _edr = _edr_fn(edf["ecg_filtered"][ecg_ch], rr_data["peaks"], sfreq)
        _rsa_rate = fd_welch.get("hf_resp_rate") if fd_welch else float("nan")

        if _edr is None:
            st.info("ℹ️ EDR nicht berechenbar — zu wenige/instabile R-Zacken oder Segment zu kurz.")
        else:
            _edr_rate = _edr["resp_rate_bpm"]
            ec1, ec2 = st.columns([3, 2])
            with ec1:
                fig_edr = go.Figure()
                fig_edr.add_trace(go.Scatter(
                    x=_edr["t"], y=_edr["edr"], mode="lines",
                    line=dict(color="#2980b9", width=1.6),
                    hovertemplate="t=%{x:.1f}s<extra></extra>"))
                fig_edr.update_layout(
                    xaxis=dict(title="Zeit (s)"),
                    yaxis=dict(title="EDR (rel.)", showticklabels=False, zeroline=True),
                    height=200, margin=dict(t=8, b=38, l=40, r=10),
                    showlegend=False,
                )
                st.plotly_chart(fig_edr, use_container_width=True, key="edr_wave")
            with ec2:
                # Bewertung Atemfrequenz (Ruhe 12–20/min)
                _zone = "normal" if 12 <= _edr_rate <= 20 else (
                    "grenzwertig" if 8 <= _edr_rate <= 25 else "pathologisch")
                _zc = {"normal": "#27ae60", "grenzwertig": "#e67e22",
                       "pathologisch": "#c0392b"}[_zone]
                st.markdown(
                    f"<div style='padding:12px 14px;border-radius:10px;border:2px solid {_zc};"
                    f"background:{_zc}0d;text-align:center'>"
                    f"<div style='font-size:12px;color:#888'>Atemfrequenz (EDR)</div>"
                    f"<div style='font-size:2rem;font-weight:800;color:{_zc}'>{_edr_rate:.1f}"
                    f"<span style='font-size:1rem'> /min</span></div>"
                    f"<div style='font-size:11px;color:#555'>Norm 12–20/min · Qualität "
                    f"{_edr['quality']:.1f}</div></div>",
                    unsafe_allow_html=True,
                )
                # Kreuzvergleich mit RSA
                if _rsa_rate == _rsa_rate:
                    _diff = abs(_edr_rate - _rsa_rate)
                    if _diff <= 3:
                        st.success(f"Konsistent mit RSA-Schätzung ({_rsa_rate:.1f}/min, "
                                   f"Δ {_diff:.1f}) — Atemfrequenz belastbar.")
                    elif _diff <= 6 or abs(_edr_rate*2 - _rsa_rate) <= 3:
                        st.warning(f"Weicht von RSA ab ({_rsa_rate:.1f}/min). Mögliche "
                                   f"Harmonische/Subharmonische — mit Vorsicht interpretieren.")
                    else:
                        st.warning(f"Deutliche Abweichung zur RSA ({_rsa_rate:.1f}/min) — "
                                   f"Atemfrequenz unsicher (unkontrollierte Atmung/Artefakte).")
            st.caption(
                "**EDR** rekonstruiert die Atmung aus der atembedingten Schwankung der "
                "**R-Zacken-Amplitude** (mechanische Herzachsen-Verschiebung) — funktioniert "
                "auch, wenn die RSA (HF-Peak) schwach ist. Ergänzt die frequenzbasierte "
                "RSA-Schätzung im Frequenz-Tab. *Einkanal-Verfahren, orientierend.*"
            )

    # ── Tab 2: Frequenzdomäne ─────────────────────────────────────────────────
    with tab_freq:
        _section("Frequenzdomäne (HRV)", seg_label)
        if has_hv:
            st.caption("PSD-Analyse basiert ausschließlich auf dem Prä-HV-Segment (Ruhebedingung).")

        if len(rr_ms_analysis) < 30 or not _fd_ok:
            _dur_min = edf["duration_s"] / 60
            st.warning(
                f"**HRV-Frequenzanalyse hier nicht möglich** — nur "
                f"**{len(rr_ms_analysis)} RR-Intervalle** im {seg_label}-Segment "
                f"(Aufnahme {_dur_min:.1f} min). Nötig sind mindestens ~30, für belastbare "
                f"Werte deutlich mehr."
            )
            st.info(
                "**Warum?** Die Frequenzanalyse zerlegt die Herzschlag-Schwankungen in "
                "**langsame Rhythmen**: LF 0,04–0,15 Hz (eine Welle alle 7–25 s) und "
                "HF 0,15–0,40 Hz (Atmung). Um solche Rhythmen überhaupt messen zu können, "
                "braucht man **Minuten, nicht Sekunden** — die **Task Force 1996** empfiehlt "
                "**5 Minuten** für die Kurzzeit-HRV.\n\n"
                "**Die Zeitbereichs-Werte** (SDNN, RMSSD, pNN50 …) im Tab **RR & Zeitdomäne** "
                "**bleiben nutzbar** — sie brauchen keine Minuten-Rhythmen."
            )
            if has_hv:
                st.caption("Prä-HV-Phase ggf. zu kurz für Frequenzanalyse.")
        else:
            _n_beats = len(rr_ms_analysis)
            _dur_min = edf["duration_s"] / 60
            if _n_beats < 300:
                st.warning(
                    f"**LF/HF orientierend** — {_n_beats} Schläge analysiert "
                    f"({_dur_min:.1f} min). Task Force 1996 fordert ≥ 300 Schläge (~5 min) "
                    f"für statistisch valide Frequenzdomäne-Werte."
                )
            if _dur_min < 5:
                st.info(
                    f"**VLF-Band nicht interpretierbar** — Aufnahmedauer {_dur_min:.1f} min. "
                    f"VLF (0.003–0.04 Hz, Periode 25–300 s) benötigt mindestens 5 min für "
                    f"≥ 1 vollständigen Zyklus. VLF-Zone im Diagramm ist rein orientierend."
                )
            # Lücken-Confounder: große zusammenhängende Zeitlücken (entfernte
            # Schläge / Dropout) werden PCHIP-interpoliert (kein Overshoot), aber
            # das interpolierte Segment trägt keine echte Information → melden.
            _mgap = fd.get("max_gap_s", 0.0)
            _ngap = fd.get("n_gaps", 0)
            if _ngap > 0:
                _gfrac = fd.get("gap_fraction", 0.0)
                st.warning(
                    f"**{_ngap} große Zeitlücke(n)** in der RR-Reihe "
                    f"(längste {_mgap:.1f} s, zusammen {_gfrac*100:.0f}% der Zeitachse). "
                    f"Diese Bereiche werden formerhaltend interpoliert (PCHIP, kein "
                    f"Overshoot), tragen aber keine echte HRV-Information — LF/HF/Total "
                    f"in diesem Ausmaß mit Vorsicht interpretieren."
                )
            col_psd_w, col_psd_b = st.columns(2)
            with col_psd_w:
                if fig_psd_welch_obj is None:
                    st.info("Kein Welch-Spektrum berechenbar (zu wenige RR-Intervalle).")
                else:
                    st.plotly_chart(fig_psd_welch_obj, use_container_width=True)
                _lf_w  = _fdget(fd_welch, "lf_peak_freq")
                _hf_w  = _fdget(fd_welch, "hf_peak_freq")
                _resp_w = _fdget(fd_welch, "hf_resp_rate")
                if _lf_w == _lf_w and _hf_w == _hf_w:
                    st.caption(
                        f"LF-Gipfel: **{_lf_w:.3f} Hz** (Mayer-Wellen, Norm ~0.07–0.12 Hz) · "
                        f"HF-Gipfel: **{_hf_w:.3f} Hz** ≈ **{_resp_w:.0f} /min** Atemfrequenz "
                        f"(Norm 12–20 /min = 0.20–0.33 Hz)"
                    )
            with col_psd_b:
                if fig_psd_burg_obj is None:
                    st.info("Kein Burg-Spektrum berechenbar (zu wenige RR-Intervalle).")
                else:
                    st.plotly_chart(fig_psd_burg_obj, use_container_width=True)
                _lf_b  = _fdget(fd_burg, "lf_peak_freq")
                _hf_b  = _fdget(fd_burg, "hf_peak_freq")
                _resp_b = _fdget(fd_burg, "hf_resp_rate")
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

            # ── Kennzahlen-Übersicht (Welch-Standard) ──────────────────────────
            _section("Frequenzband-Kennzahlen", "Welch (Standard) · Task Force 1996")
            st.markdown(
                "<div style='font-size:12px;color:#666;margin-bottom:4px'>"
                "<b>VLF</b> 0,003–0,04 Hz (langsame Regulation) · "
                "<b>LF</b> 0,04–0,15 Hz (Baroreflex, gemischt) · "
                "<b>HF</b> 0,15–0,40 Hz (vagal, atemgekoppelt = RSA). Power in ms² = "
                "Stärke der Schwankung im jeweiligen Rhythmusband.</div>",
                unsafe_allow_html=True)
            _lf = _fdget(fd_welch, "lf_power")
            _hf = _fdget(fd_welch, "hf_power")
            _tp = _fdget(fd_welch, "total_power")
            _lhr = _fdget(fd_welch, "lf_hf_ratio")
            _hfn = _fdget(fd_welch, "hf_norm")
            fq = st.columns(5)
            def _fq(col, label, val, unit, sub):
                col.markdown(
                    f"<div style='background:#f4f6f9;border:1px solid #e0e4e8;border-radius:9px;"
                    f"padding:9px 10px;text-align:center;min-height:74px'>"
                    f"<div style='font-size:10px;color:#888;font-weight:600'>{label}</div>"
                    f"<div style='font-size:17px;font-weight:800;color:#2c3e50;margin:3px 0'>"
                    f"{val}{unit}</div><div style='font-size:9px;color:#999'>{sub}</div></div>",
                    unsafe_allow_html=True)
            _fq(fq[0], "LF Power",  f"{_lf:.0f}" if _lf==_lf else "—", " ms²", "Baroreflex")
            _fq(fq[1], "HF Power",  f"{_hf:.0f}" if _hf==_hf else "—", " ms²", "vagal (RSA)")
            _fq(fq[2], "Total Power", f"{_tp:.0f}" if _tp==_tp else "—", " ms²", "≈ SDNN²")
            _fq(fq[3], "LF/HF",     f"{_lhr:.2f}" if _lhr==_lhr else "—", "", "Balance (umstritten)")
            _fq(fq[4], "HF normiert", f"{_hfn:.0f}" if _hfn==_hfn else "—", " %", "vagaler Anteil")
            st.caption(
                "Volle Normwerte, Farbkodierung und Interpretation der Frequenzparameter findest du "
                "im Reiter **HRV-Befund**. **LF/HF** ist als Sympathovagal-Balance umstritten "
                "(Billman 2013) — nur als Trend/unter Provokation verwenden.")

    # ── Tab 3: HRV-Befund ─────────────────────────────────────────────────────
    with tab_befund:
        _section("HRV-Befund — Normwertvergleich", seg_label)

        if is_pediatric:
            st.info(
                f"**Pädiatrische Referenzwerte aktiv — {pediatric_age_group}** · "
                "Gąsior et al. 2018 (Front Physiol), n=312 Kinder 6–13 J., HR-adjustiert."
            )
        elif patient_age < 15:
            st.warning(
                f"Patient ist {patient_age} Jahre — bitte **Pädiatrischer Patient** aktivieren."
            )

        pdf_lab_rows, metrics_pre = _render_lab_panel(
            rr_ms_analysis, r_times_analysis, panel_id="pre"
        )

        with st.expander("Parameter-Erklärungen, Synonyme & Quellen", icon=":material/menu_book:"):
            st.markdown("""
#### Zeitbereich

**Herzfrequenz** · kein ANS-Marker
Mittlere Herzrate aus dem RR-Intervall-Mittelwert. Bradykardie <60 bpm, Tachykardie >100 bpm.
Normbereich (Hansen 2024, Ruhe): Median 67 bpm [IQR 61–74].

---

**RMSSD** · Parasympathikus-Marker (vagal)
🏆 **Evidenz: ★★★★★** — Robustester Einzelparameter der HRV-Messung
Wurzel der mittleren quadrierten aufeinanderfolgenden RR-Differenzen. Misst die schnelle,
vagal vermittelte Schlag-zu-Schlag-Variabilität (RSA). **Zeitbereich-Synonym für HF Power:**
RMSSD ≈ √HF Power (beide messen denselben physiologischen Prozess, nur in verschiedenen
Domänen). Hervorragende Reproduzierbarkeit, stabil bei Kurz- und Langzeitmessungen,
gut validiert bei kardiovaskulären und psychiatrischen Erkrankungen. Referenz P5 alters-/HF-adjustiert (Hansen 2024).

**SDNN** · globaler Marker (Sympathikus + Parasympathikus)
🏆 **Evidenz: ★★★★★** — Stärkster prognostischer Langzeitmarker
Standardabweichung aller RR-Intervalle. Spiegelt die gesamte autonome Variabilität wider —
aus beiden Ästen des ANS gespeist. **Beste klinische Evidenz** bei post-Myokardinfarkt und
Herzinsuffizienz (ATRAMI, Kleiger 1987). Analog zur Wurzel aus Total Power im Frequenzbereich:
**SDNN ≈ √Total Power** (bei vollständiger Frequenzabdeckung annähernd identisch).
Referenz P5 alters-/HF-adjustiert (Hansen 2024).

**pNN50** · Parasympathikus-Marker (vagal)
⚠️ **Evidenz: ★★★☆☆** — Weitgehend redundant mit RMSSD
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

**pNN20** · Parasympathikus-Marker (vagal)
⚠️ **Evidenz: ★★★☆☆** — pNNx-Familie; sensitiver als pNN50, aber RMSSD-redundant
Anteil aufeinanderfolgender RR-Differenzen **>20 ms** (statt 50 ms). Durch die
niedrigere Schwelle **sensitiver bei geringer Variabilität** (ältere Patienten,
reduzierte HRV), wo pNN50 oft nahe 0 liegt und kaum noch differenziert. Ergänzt
pNN50 nach unten hin.

**CV (Variationskoeffizient, %)** · globaler Marker
⚠️ **Evidenz: ★★★☆☆** — robuste Berechnung, HF-normiert; im Kern normiertes SDNN, moderate eigenständige klinische Evidenz
CV = SDNN / mittleres RR × 100. **HF-normierte Streuung:** SDNN fällt bei höherer
Herzfrequenz automatisch kleiner aus (kürzere RR-Intervalle), auch wenn die *relative*
Variabilität gleich bleibt. CV entkoppelt die Streuung von der absoluten Herzfrequenz
und macht Personen/Zustände mit unterschiedlicher HF besser vergleichbar. Normgrenze
hier aus der SDNN-P5 umgerechnet (`CV_p5 = SDNN_p5 × HR/600`, Hansen 2024).

**NN50 (Absolutzahl)** · Parasympathikus-Marker (vagal, längenabhängig)
⚠️ **Evidenz: ★★☆☆☆** — längenabhängig, keine feste Norm; nur als Ergänzung zu pNN50
Absolute Anzahl aufeinanderfolgender RR-Differenzen >50 ms (NeuroFax gibt Zahl *und*
Prozent aus). **Achtung:** die Zahl steigt mit Aufnahmelänge/Schlagzahl → keine feste
Normgrenze; die klinische Wertung erfolgt über pNN50 (deshalb wird der NN50-Marker in
der pNN50-Farbe dargestellt).

---
#### Nichtlinear & Poincaré

**SD1 / SD2 (Poincaré-Plot, ms)** · SD1 vagal · SD2 global
✅ **Evidenz: ★★★★☆** (SD1) / ⚠️ ★★★☆☆ (SD2) — SD1 ≈ RMSSD/√2 (sehr robust, aber redundant), SD2 korreliert mit SDNN
Der Poincaré-Plot trägt jedes RR-Intervall gegen das nächste auf (RRₙ vs. RRₙ₊₁). Die
Punktwolke bildet eine Ellipse:
- **SD1** = Streuung **quer** zur Identitätslinie = kurzfristige Schlag-zu-Schlag-
  Variabilität, **vagal** (SD1 = √0,5 × SDSD, eng verwandt mit RMSSD).
- **SD2** = Streuung **entlang** der Linie = langfristige Variabilität, global.
- **SD2/SD1** = Verhältnis lang-/kurzfristig (autonome Balance). Es gilt
  SD1² + SD2² = 2 × SDNN².
Quelle: **Brennan M et al.** (2001). IEEE Trans Biomed Eng 48(11):1342–1347.

**DFA α₁ (Detrended Fluctuation Analysis)** · nichtlinear, fraktal
✅ **Evidenz: ★★★★☆** — gute Prognosedaten (Mäkikallio 1999: Mortalität post-MI, unabhängig von SDNN/RMSSD); robust, aber zustandsabhängig (Ruhe ≠ Belastung) und braucht ausreichend Schläge
Misst **nicht die Größe**, sondern die **fraktale Korrelationsstruktur** der RR-Reihe:
Sind die Intervalle rein zufällig oder komplex-biologisch organisiert? Das integrierte
RR-Profil wird in Fenster (4–16 Schläge) zerlegt, je Fenster der lineare Trend abgezogen
und die Fluktuation F(n) bestimmt; α₁ ist die Steigung von log F(n) über log n.
- **α₁ ≈ 1,0** → gesunde 1/f-Dynamik („pink noise"), langreichweitig korreliert.
- **α₁ → 0,5** → unkorreliertes weißes Rauschen: **Verlust der Korrelation** (Fatigue,
  autonome Dysregulation, hohe Belastung, ungünstige Prognose).
- **α₁ → 1,5** → Brown'sches Rauschen (integriertes weißes Rauschen).
Orientierende Grenzen (Ruhe): gesund 0,75–1,25 · auffällig <0,5 oder >1,5. Robuster
Belastungs-/Fatigue-Marker, aber zustandsabhängig (Ruhe ≠ Belastung).
Quelle: **Peng CK et al.** (1995). Chaos 5(1):82–87.

**Sample Entropy (SampEn)** · nichtlinear, Komplexität
⚠️ **Evidenz: ★★★☆☆** — etabliertes Komplexitätsmaß, aber parameter- (m, r) und
längenabhängig; Normwerte kontextspezifisch
Misst die **Regelmäßigkeit/Vorhersagbarkeit** der RR-Reihe: Wie wahrscheinlich bleiben
zwei ähnliche Muster der Länge m (=2) auch bei Länge m+1 ähnlich (Toleranz r = 0,2·SD)?
SampEn = −ln(A/B). **Niedrig** = regelmäßig/vorhersagbar (reduzierte Komplexität —
Alterung, Krankheit, autonome Verarmung), **hoch** = komplex. Ergänzt DFA α₁ um die
Musterebene. Orientierend, v. a. im Verlauf/Vergleich.
Quelle: **Richman JS & Moorman JR** (2000). Am J Physiol Heart Circ Physiol 278:H2039–H2049.

---
#### Frequenzbereich — Bandleistung

**HF Power (0.15–0.40 Hz)** · Parasympathikus-Marker (vagal)
✅ **Evidenz: ★★★★☆** — Gut validiert, atemfrequenzabhängig
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
✅ **Evidenz: ★★★★☆** — Solider Breitband-Marker, methodenanfällig
Summe VLF + LF + HF. Analog zur Aussage von SDNN: **Total Power ≈ SDNN²** bei
vollständiger Spektralabdeckung. Achtung: Wert variiert je nach Schätzverfahren (Welch vs. Burg)
stärker als der zeitdomänenäquivalente SDNN. Referenz P5 alters-/HF-adjustiert (Hansen 2024).
NeuroFax-Bezeichnung: **T.Wert** (Achtung: NeuroFax-T.Wert ist unnormiert, nicht direkt
vergleichbar mit unseren ms²-Werten).

**LF Power (0.04–0.15 Hz)** · gemischter Marker (Baroreflex)
⚠️ **Evidenz: ★★★★☆** — Gut reproduzierbar, aber physiologisch fehlinterpretiert
Integrierte spektrale Leistung im Low-Frequency-Band. Historisch als "Sympathikus-Marker"
bezeichnet — diese Interpretation ist **durch die Literatur widerlegt** (Billman 2013):
LF Power wird hauptsächlich durch Baroreflex-Aktivität (sowohl sympathisch als auch vagal)
bestimmt, nicht durch den Sympathikus allein. Als Amplitudenmaß der LF-Oszillation ist er
reproduzierbar und klinisch nutzbar, solange er nicht als reiner Sympathikus-Indikator
missverstanden wird. Referenz P5 alters-/HF-adjustiert (Hansen 2024).
NeuroFax-Bezeichnung: **LFA** (LF Area).

**LF/HF-Ratio** · umstrittener Balance-Marker
🚫 **Evidenz: ★☆☆☆☆** — Physiologisch weitgehend diskreditiert
Verhältnis LF-Leistung zu HF-Leistung. Klassisch als Maß der "sympathovagalen Balance"
bezeichnet — dies ist aus mehreren Gründen problematisch: (1) LF ist kein reiner
Sympathikus-Marker (s.o.), daher ist LF/HF kein Sympatho-Vagal-Index. (2) Die Ratio
ist mathematisch instabil bei kleinen HF-Werten (Hyperventilation, Tachypnoe).
(3) Aktuelle Metaanalysen zeigen schlechte klinische Vorhersagekraft. Als Trendmarker
im Verlauf oder unter Provokation (Kipptisch) noch vertretbar, als Absolutwert nicht.
NeuroFax-Bezeichnung: **LFA/HFA (%)** = LF/HF × 100.

---
#### Frequenzbereich — Normiert & Balance

**LF normalisiert (%)** · gemischter Marker
⚠️ **Evidenz: ★★☆☆☆** — Methodisch problematisch, für Verlauf bedingt nutzbar
LF Power als prozentualer Anteil an LF+HF. Reduziert den Einfluss von Gesamtpower-
Schwankungen auf den Balance-Index. Das Problem: LF ist kein reiner Sympathikus-Marker —
daher misst LF norm keine verlässliche sympathikotone Dominanz. Bei kontrollierter Atmung
und Verlaufsuntersuchungen bedingt verwertbar. Task Force 1996 Normbereich: **40–70 %** (Ruhe, liegend).
NeuroFax-Bezeichnung: **LF/NF (%)** (in der FFT-Analyse).

**HF normalisiert (%)** · Parasympathikus-Marker (vagal)
⚠️ **Evidenz: ★★☆☆☆** — Atemabhängig, nur bei kontrollierter Atmung sinnvoll
HF Power als prozentualer Anteil an LF+HF. Komplement zu LF norm: LF norm + HF norm ≈ 100 %.
Bei unkontrollierter Atmung (wie in EEG-EKG-Ableitungen) stark durch Atemfrequenz beeinflusst.
Task Force 1996 Normbereich: **20–50 %** (Ruhe, liegend). Hohe HF norm = vagal dominant.

---
#### Frequenzbereich — Gipfelfrequenzen

**Atemfrequenz aus HF-Gipfel (RSA)** · kein ANS-Marker (physiologischer Messparameter)
✅ **Evidenz: ★★★★☆** — etabliert, aber nur gültig solange die RSA im HF-Band liegt
Die Frequenz des dominanten Peaks im HF-Band × 60 ergibt die Atemfrequenz in /min.
Normbereich Ruhe: **12–20 /min** (0.20–0.33 Hz). Versagt bei schwacher RSA oder
Atemfrequenz > 24/min (Peak wandert aus dem HF-Band).
Quelle: **Yasuma F & Hayano J** (2004). Chest 125(2):683–690.
NeuroFax-Bezeichnung: **NF (Hz)**.

**Atemfrequenz aus EDR (R-Amplitude)** · kein ANS-Marker (physiologischer Messparameter)
✅ **Evidenz: ★★★★☆** — robustes Einkanal-Standardverfahren, unabhängig von der RSA
**ECG-Derived Respiration:** Die Atmung verschiebt die elektrische Herzachse
(Zwerchfell-/Thoraxbewegung) → die **R-Zacken-Amplitude** schwankt im Atemtakt. Aus
dieser Amplituden-Modulation wird ein Atemsignal rekonstruiert (R-Amplituden je Schlag
→ Interpolation → Bandpass 0.1–0.5 Hz → dominante Frequenz). **Vorteil gegenüber RSA:**
funktioniert auch bei schwacher respiratorischer Sinusarrhythmie. Wir zeigen beide
Schätzer als **Kreuzvergleich** — stimmen sie überein, ist die Atemfrequenz belastbar;
weichen sie ab (oft Faktor 2 = Harmonische), ist sie unsicher (unkontrollierte Atmung).
Quelle: **Moody GB et al.** (1985). *Derivation of respiratory signals from multi-lead
ECGs.* Computers in Cardiology 12:113–116.

**LF-Gipfelfrequenz** · kein ANS-Marker (deskriptiv)
Frequenz des dominanten Peaks im LF-Band. Mayer-Wellen, typisch **0.07–0.12 Hz**.
NeuroFax-Bezeichnung: **LF (Hz)**.

---

#### Evidenz-Ranking im Überblick

| Parameter | Evidenz | Stärke |
|-----------|---------|--------|
| RMSSD | ★★★★★ | Robustester Einzelparameter; kurz- wie langzeitstabil |
| SDNN | ★★★★★ | Beste Prognosedaten (post-MI, HI); Breitband-Marker |
| HF Power | ★★★★☆ | Gut validiert, aber atemfrequenzabhängig |
| Total Power | ★★★★☆ | SDNN-Analog im Frequenzraum; Methodenanfälligkeit beachten |
| LF Power | ★★★★☆ | Reproduzierbar, aber ≠ Sympathikus-Marker |
| **DFA α₁** | ★★★★☆ | Unabhängige Prognosedaten (Mäkikallio 1999); robust, zustandsabhängig |
| **SD1** | ★★★★☆ | ≈ RMSSD/√2; sehr robust, aber redundant zu RMSSD |
| **CV** | ★★★☆☆ | Robust, HF-normiert; im Kern normiertes SDNN |
| **SD2** | ★★★☆☆ | Langzeit-Streuung; korreliert mit SDNN |
| **SD2/SD1** | ★★★☆☆ | Beschreibt Zufälligkeit/Balance; moderate Evidenz |
| **SampEn** | ★★★☆☆ | Komplexität/Regelmäßigkeit; parameter-/längenabhängig |
| **pNN20** | ★★★☆☆ | Sensitiver als pNN50 bei niedriger HRV; RMSSD-redundant |
| pNN50 | ★★★☆☆ | RMSSD-Redundanz (r>0.92); kein altersadjustierter Cutoff |
| **NN50** | ★★☆☆☆ | Längenabhängig, keine feste Norm; Wertung via pNN50 |
| HF normiert | ★★☆☆☆ | Nur bei kontrollierter Atmung sinnvoll |
| LF normiert | ★★☆☆☆ | Methodisch schwach; basiert auf fehlerhafter LF-Interpretation |
| LF/HF-Ratio | ★☆☆☆☆ | Physiologisch diskreditiert; kein verlässlicher Sympatho-Vagal-Index |

*Ranking nach: Reproduzierbarkeit · physiologischer Validität · klinischer Evidenz (Billman 2013, Shaffer & Ginsberg 2017). Fett = neu ergänzte Parameter.*

---
**Quellen:**
1. **Task Force ESC/NASPE** (1996). Circulation 93(5):1043–1065.
2. **Hansen CS et al.** (2024). Clin Auton Res 35:101–113.
3. **Billman GE** (2013). Front Physiol 4:26.
4. **Yasuma F & Hayano J** (2004). Chest 125(2):683–690.
5. **Eckberg DL** (1997). Circulation 96(9):3224–3232.
6. **Gąsior JS et al.** (2018). Front Physiol 9:1495.
7. **Mietus JE et al.** (2002). Heart 88(4):378–380.
8. **Shaffer F & Ginsberg JP** (2017). Front Public Health 5:258.
9. **Brennan M et al.** (2001). *Do existing measures of Poincaré plot geometry reflect nonlinear features of HRV?* IEEE Trans Biomed Eng 48(11):1342–1347.
10. **Peng CK et al.** (1995). *Quantification of scaling exponents … DFA.* Chaos 5(1):82–87.
11. **Mäkikallio TH et al.** (1999). *Prediction of sudden cardiac death by fractal analysis (DFA α₁).* J Am Coll Cardiol 34(4):1395–1401.

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
            {"Parameter": "CV (Variationskoeffizient)",     "Wert": round(cv_pct, 2),             "Einheit": "%"},
            {"Parameter": "RMSSD",                          "Wert": round(rmssd, 1),              "Einheit": "ms"},
            {"Parameter": "pNN50",                          "Wert": round(pnn50, 1),              "Einheit": "%"},
            {"Parameter": "NN50 (Absolutzahl)",             "Wert": nn50,                          "Einheit": "Anzahl"},
            {"Parameter": "pNN20",                          "Wert": round(pnn20, 1),              "Einheit": "%"},
            {"Parameter": "SD1 (Poincaré)",                 "Wert": round(sd1, 1),                "Einheit": "ms"},
            {"Parameter": "SD2 (Poincaré)",                 "Wert": round(sd2, 1),                "Einheit": "ms"},
            {"Parameter": "SD2/SD1",                        "Wert": round(sd_ratio, 2) if sd_ratio == sd_ratio else None, "Einheit": "—"},
            {"Parameter": "DFA α₁ (nichtlinear)",           "Wert": round(dfa_a1, 2) if dfa_a1 == dfa_a1 else None, "Einheit": "—"},
            {"Parameter": "Sample Entropy (nichtlinear)",   "Wert": round(samp_en, 2) if samp_en == samp_en else None, "Einheit": "—"},
            {"Parameter": "Aufnahmedauer (Analyse)",        "Wert": round(len(rr_ms_analysis) and float(np.sum(rr_ms_analysis)/1000) or 0.0, 1), "Einheit": "s"},
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
                "HRV-Ergebnisse als Excel exportieren", icon=":material/download:",
                data=xlsx_buf,
                file_name=f"hrv_export_{os.path.splitext(os.path.basename(edf_path))[0]}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        with col_dl2:
            if st.button("PDF-Report erzeugen", icon=":material/description:"):
                from analysis.pdf_report import build_hrv_pdf
                with st.spinner("Erzeuge PDF…"):
                    pdf_bytes = build_hrv_pdf(
                        patient_age=patient_age, patient_sex=patient_sex,
                        file_label=os.path.basename(edf_path),
                        duration_min=edf["duration_s"] / 60,
                        mean_hr=mean_hr, sdnn=sdnn, rmssd=rmssd, pnn50=pnn50,
                        pct_removed=pct_removed, quality_label=qlabel,
                        balance_label=balance["label"],
                        lab_rows=pdf_lab_rows, method_used=freq_method,
                        fd_welch=fd_welch, fd_burg=fd_burg, is_pediatric=is_pediatric,
                    )
                st.session_state["pdf_bytes"] = pdf_bytes
            if "pdf_bytes" in st.session_state:
                st.download_button(
                    "PDF herunterladen", icon=":material/download:",
                    data=st.session_state["pdf_bytes"],
                    file_name=f"hrv_report_{os.path.splitext(os.path.basename(edf_path))[0]}.pdf",
                    mime="application/pdf",
                )

    # ── Tab 4: Hyperventilation ───────────────────────────────────────────────
    with tab_hv:
        _section("Hyperventilation & Erholung",
                 "HRV-Analyse pro Phase · Vagaler Rebound")

        dur_s        = int(edf["duration_s"])
        _manual_key  = f"hvt_manual_{st.session_state.get('edf_display_name','')}"
        _manual_active = st.session_state.get(_manual_key, False)

        if not has_hv and not _manual_active:
            col_info_nohv, col_btn_nohv = st.columns([5, 1])
            with col_info_nohv:
                st.info("**Keine Hyperventilation** in dieser Aufnahme erkannt (keine HVT-Annotations).")
            with col_btn_nohv:
                st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
                if st.button("HV manuell", icon=":material/add:", use_container_width=True, key="hvt_manual_add_btn",
                             help="HV-Phasen manuell setzen (z.B. wenn Annotations fehlen)"):
                    st.session_state[_manual_key] = True
                    st.rerun()
        else:
            if has_hv and not _manual_active:
                hv_dur = ((phases["hvt_end"] or 0) - (phases["hvt_start"] or 0))
                if hv_dur < 60:
                    st.warning(
                        f"**HVT sehr kurz ({hv_dur:.0f} s < 60 s)** — bitte Annotations prüfen. "
                        f"Dauer zu kurz für valide HRV-Phasenanalyse. Manuelle Anpassung empfohlen."
                    )
                col_info, col_btn = st.columns([5, 1])
                with col_info:
                    st.info(
                        f"**Automatisch erkannt** · "
                        f"HVT {phases['hvt_start']:.0f}s → {phases['hvt_end']:.0f}s "
                        f"({hv_dur:.0f} s) · Post-HV +120 s · "
                        + (f"Foto: {len(phases['photo_events'])} Schritte"
                           if phases["has_photo"] else "")
                    )
                with col_btn:
                    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
                    if st.button("Anpassen", icon=":material/edit:", use_container_width=True, key="hvt_override_btn"):
                        st.session_state[_manual_key] = True
                        st.rerun()
            else:
                if not has_hv:
                    st.info("Keine HVT-Annotations im EDF — Phasen manuell gesetzt.")
                else:
                    st.warning("Manuelle Phasengrenzen aktiv — Auto-Erkennung überschrieben.", icon=":material/edit:")

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
                    "SDNN während HVT kompromittiert (mechanische Atemvariabilität, nicht autonome Modulation). "
                    "LF/HF während HVT ebenfalls eingeschränkt interpretierbar — RSA verschiebt sich aus dem HF-Band."
                )

                if seg_post and seg_pre:
                    rb = assess_vagal_rebound(seg_pre, seg_post)
                    _rb_zone = {"🟢": "success", "🟡": "warning", "🔴": "danger"}.get(rb["icon"], "neutral")
                    st.markdown(
                        f"<div style='padding:10px 14px;border-radius:8px;"
                        f"border:1px solid {rb['color']}55;background:{rb['color']}11;margin:6px 0'>"
                        f"{status_dot(_rb_zone, size=13)} "
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

                tab_labels = [":material/air: HVT aktiv"]
                if seg_post:
                    tab_labels.append(":material/monitor_heart: Post-HV Erholung")
                if phases["has_photo"]:
                    tab_labels.append(":material/lightbulb: Fotostimulation")

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
                            showlegend=True,
                            legend=dict(orientation="h", yanchor="bottom", y=1.02),
                        )
                        st.plotly_chart(fig_ph, use_container_width=True)

                        if seg_photo:
                            st.markdown("**HRV-Kennwerte Fotostimulationsphase**")
                            _render_lab_panel(seg_photo["rr_ms"], seg_photo["r_times"],
                                              freq_warning=True, panel_id="photo")
                        else:
                            st.info("Zu wenige Schläge im Fotostimulations-Segment.")
