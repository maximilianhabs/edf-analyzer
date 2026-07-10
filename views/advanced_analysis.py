"""Erweiterte Analysen & Methodik — ADD-ON (verändert die bestehenden Seiten NICHT).

Feinere/validierte Verfahren (W-Serie) mit **visueller Kontrolle**. Bestehende Analysen bleiben
unverändert als Default; hier werden Verbesserungen parallel angeboten und geprüft.
Aktuell: W0 Methoden-Transparenz · W1 validierte R-Zacken-Detektion mit Roh-EKG-Overlay.
"""

import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

from core.shared import (apply_global_style, section_header, get_edf_or_stop,
                         load_and_prepare, apply_channel_overrides)


_DET_STYLE = {
    "eigen (aktueller Default)": ("#2980b9", "circle-open"),
    "Hamilton 2002 (validiert)": ("#e67e22", "x"),
    "Pan-Tompkins (validiert)":  ("#16a34a", "triangle-up-open"),
}


@st.cache_data(show_spinner="Erkenne R-Zacken (mehrere Detektoren) …")
def _detect_all(edf_path: str, ch: str):
    from analysis.ecg import (detect_r_peaks, detect_r_peaks_validated,
                              build_rr_series, compute_hrv_time_domain)
    e = apply_channel_overrides(load_and_prepare(edf_path))
    sf = e["sfreq"]
    sig = e["data"][e["ch_idx"][ch]].astype(float)
    methods = {
        "eigen (aktueller Default)": detect_r_peaks(sig, sf),
        "Hamilton 2002 (validiert)": detect_r_peaks_validated(sig, sf, "hamilton"),
        "Pan-Tompkins (validiert)":  detect_r_peaks_validated(sig, sf, "pan_tompkins"),
    }
    out = {}
    for label, pk in methods.items():
        pk = np.asarray(pk, int)
        rr = build_rr_series(pk, sf)
        td = compute_hrv_time_domain(rr.rr_ms[~rr.artifact_mask]) if rr is not None else {}
        out[label] = {"peaks": pk, "hrv": td}
    return out, sf


def _render_methods_table():
    from analysis.methods import METHODS
    section_header("Methoden & Validität", "Welche Verfahren, welche Referenz, welcher Reifegrad")
    st.dataframe(pd.DataFrame(
        [{"Bereich": b, "Parameter": p, "Verfahren": v, "Referenz": r, "Reifegrad": m}
         for b, p, v, r, m in METHODS],
        columns=["Bereich", "Parameter", "Verfahren", "Referenz", "Reifegrad"]),
        hide_index=True, use_container_width=True)
    st.caption("✅ validiert · 🟡 akzeptierte Methode, vereinfachte Umsetzung · 🔬 Forschungs-"
               "Proxy/geplant. Diese Seite hebt die Umsetzung schrittweise (W-Serie) an — "
               "**parallel**, ohne die bestehenden Analysen zu ändern.")


def _render_rpeak_visual(edf, edf_path):
    section_header("R-Zacken-Detektor — Vergleich & visuelle Kontrolle",
                   "Validierte Detektoren neben dem bewährten eigenen — mit Roh-EKG-Overlay")
    ecg_channels = edf.get("ecg_channels") or []
    if not ecg_channels:
        st.info("Kein EKG-Kanal identifiziert.")
        return

    sf = edf["sfreq"]
    dur = edf["duration_s"]
    c1, c2 = st.columns([2, 3])
    ch = c1.selectbox("EKG-Kanal", ecg_channels)
    overlay = c2.multiselect("Overlay-Detektoren", list(_DET_STYLE.keys()),
                             default=["eigen (aktueller Default)", "Hamilton 2002 (validiert)"])

    det, _ = _detect_all(edf_path, ch)
    sig_mv = edf["data"][edf["ch_idx"][ch]].astype(float) * 1000.0
    sig_mv = sig_mv - np.median(sig_mv)

    # ── Kennzahlen-Vergleich ─────────────────────────────────────────────────
    rows = []
    for label, d in det.items():
        td = d["hrv"]
        rows.append({"Detektor": label, "#R-Zacken": len(d["peaks"]),
                     "HR (bpm)": td.get("mean_hr_bpm", float("nan")),
                     "SDNN (ms)": td.get("sdnn_ms", float("nan")),
                     "RMSSD (ms)": td.get("rmssd_ms", float("nan")),
                     "pNN50 (%)": td.get("pnn50_pct", float("nan"))})
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    st.caption("Der Detektor beeinflusst v. a. **RMSSD/pNN50** (Timing-Präzision). Der eigene "
               "Detektor **bleibt Default** (bewährt, visuell sauber); die validierten laufen hier "
               "nur **parallel zur Prüfung** — kein Ersatz ohne sorgfältige Validierung.")

    # ── Visuelle Kontrolle: Roh-EKG + überlagerte R-Zacken ───────────────────
    st.markdown("**Visuelle Kontrolle — passt die R-Zacken-Erkennung?**")
    win = st.select_slider("Fensterbreite", options=[5, 10, 20, 30], value=10,
                           format_func=lambda s: f"{s} s")
    t0 = st.slider("Position (s)", 0.0, float(max(0.0, dur - win)),
                   min(30.0, float(max(0.0, dur - win))), step=1.0)
    i0, i1 = int(t0 * sf), int((t0 + win) * sf)
    tvec = np.arange(i0, i1) / sf

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=tvec, y=sig_mv[i0:i1], mode="lines",
                             line=dict(color="#374151", width=1), name=ch,
                             hovertemplate="%{x:.2f}s · %{y:.2f} mV<extra></extra>"))
    for label in overlay:
        color, symbol = _DET_STYLE[label]
        pk = det[label]["peaks"]
        pk = pk[(pk >= i0) & (pk < i1)]
        if len(pk):
            fig.add_trace(go.Scatter(x=pk / sf, y=sig_mv[pk], mode="markers",
                                     marker=dict(color=color, symbol=symbol, size=11,
                                                 line=dict(width=1.5, color=color)),
                                     name=label, hovertemplate=label + "<extra></extra>"))
    fig.update_layout(height=300, margin=dict(t=6, b=34, l=50, r=10),
                      xaxis_title="Zeit (s)", yaxis_title="EKG (mV)", plot_bgcolor="#fafafa",
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, font=dict(size=10)))
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    st.caption("Marker sollten **genau auf den R-Zacken** sitzen. So lässt sich prüfen, ob ein "
               "Detektor Schläge verpasst, doppelt zählt oder T-Wellen fehlerkennt — bevor man ihm "
               "vertraut.")


@st.cache_data(show_spinner="Berechne Aperiodik (eigen + FOOOF) …")
def _fooof_compare(edf_path, ch, hi, knee):
    from analysis.aperiodic import welch_psd, fit_aperiodic
    from analysis.aperiodic_fooof import fit_fooof
    from views.eeg_spectrum import _highpass
    e = apply_channel_overrides(load_and_prepare(edf_path))
    sf = e["sfreq"]; dur = e["duration_s"]
    ana = min(dur, 300.0); t0 = max(0.0, (dur - ana) / 2)
    sig = _highpass(e["data"][e["eeg_map"][ch]] * 1e6, sf, 1.0)
    f, p = welch_psd(sig[int(t0 * sf):int((t0 + ana) * sf)], sf, fmax=45.0)
    own = fit_aperiodic(f, p, 1, hi)
    ff = fit_fooof(f, p, 1, hi, knee=knee)
    return {"f": np.asarray(f), "p": np.asarray(p),
            "own": {"freqs": np.asarray(own["freqs"]), "aper": np.asarray(own["aper_psd"]),
                    "exponent": own["exponent"], "offset": own["offset"], "r2": own["r2"]},
            "ff": ff, "win": (t0, t0 + ana)}


def _render_fooof(edf, edf_path):
    section_header("Aperiodik 1/f — FOOOF vs. eigener Fit (W2)",
                   "Validierte Referenz-Implementierung (Donoghue 2020) parallel + visuelle Kontrolle")
    eeg_map = edf.get("eeg_map", {})
    if not eeg_map:
        st.info("Keine EEG-Kanäle.")
        return
    posterior = [c for c in ("O2", "O1", "Pz", "P4", "P3") if c in eeg_map]
    opts = posterior + [c for c in eeg_map if c not in posterior]
    c1, c2, c3 = st.columns([2, 2, 2])
    ch = c1.selectbox("Kanal", opts, key="fooof_ch")
    hi = c2.select_slider("Fit-Obergrenze (Hz)", options=[20, 30, 40], value=40, key="fooof_hi")
    knee = c3.toggle("Knee-Modell", value=False, key="fooof_knee",
                     help="FOOOF mit Knick (aperiodic_mode='knee') — sinnvoll über breite Bereiche.")

    d = _fooof_compare(edf_path, ch, int(hi), bool(knee))
    own, ff = d["own"], d["ff"]

    rows = [{"Methode": "eigen (Sigma-Clip-Geradenfit)", "Exponent": f"{own['exponent']:.2f}",
             "Offset": f"{own['offset']:.2f}", "R²": f"{own['r2']:.3f}", "Knee": "—", "Gipfel": "—"}]
    if ff:
        rows.append({"Methode": f"FOOOF ({ff['mode']})", "Exponent": f"{ff['exponent']:.2f}",
                     "Offset": f"{ff['offset']:.2f}", "R²": f"{ff['r2']:.3f}",
                     "Knee": (f"{ff['knee']:.1f}" if ff['knee'] is not None else "—"),
                     "Gipfel": str(len(ff["peaks"]))})
    else:
        st.warning("FOOOF nicht verfügbar (Lib fehlt) — nur eigener Fit angezeigt.")
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    # ── Visuelle Kontrolle: Log-Log-PSD mit beiden 1/f-Fits ──────────────────
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=d["f"], y=d["p"], mode="lines", name="PSD",
                             line=dict(color="#374151", width=1)))
    fig.add_trace(go.Scatter(x=own["freqs"], y=own["aper"], mode="lines", name="eigen 1/f",
                             line=dict(color="#2980b9", width=2, dash="dash")))
    if ff:
        fig.add_trace(go.Scatter(x=ff["fit_freqs"], y=ff["ap_fit_lin"], mode="lines",
                                 name="FOOOF 1/f", line=dict(color="#e67e22", width=2)))
        for pk in ff["peaks"]:
            fig.add_vline(x=pk[0], line=dict(color="#16a34a", width=1, dash="dot"))
    fig.update_layout(height=340, xaxis_type="log", yaxis_type="log",
                      xaxis_title="Frequenz (Hz)", yaxis_title="PSD (µV²/Hz)",
                      plot_bgcolor="#fafafa", margin=dict(t=6, b=36, l=58, r=10),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, font=dict(size=10)))
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    if ff and ff["peaks"]:
        st.markdown("**FOOOF-Gipfel (parametrisiert, aperiodik-bereinigt):**")
        st.dataframe(pd.DataFrame(
            [{"Mittenfrequenz (Hz)": round(cf, 1), "Power (log)": round(pw, 2),
              "Bandbreite (Hz)": round(bw, 1)} for cf, pw, bw in ff["peaks"]]),
            hide_index=True, use_container_width=True)
    st.caption("**FOOOF** (Donoghue 2020) trennt Oszillationsgipfel vom 1/f-Untergrund und liefert "
               "meist einen **höheren R²** (unser Fit wird durch Restgipfel leicht verzerrt). Grün "
               "gepunktet = erkannte Gipfel. Fenster: mittlere ≤5 min, Welch. Der eigene Fit bleibt "
               "**Default** in den bestehenden Seiten — hier nur der validierte Vergleich.")


def render():
    apply_global_style()
    edf, edf_path = get_edf_or_stop()
    st.title("🔬 Erweiterte Analysen & Methodik")
    st.markdown(
        "**Add-on** zu den bestehenden Seiten — diese bleiben **unverändert** und sind weiterhin "
        "der Default. Hier werden feinere/validierte Verfahren **parallel** angeboten und mit "
        "**visueller Kontrolle** geprüft, bevor irgendetwas umgestellt wird."
    )
    _render_methods_table()
    st.divider()
    _render_rpeak_visual(edf, edf_path)
    st.divider()
    _render_fooof(edf, edf_path)
