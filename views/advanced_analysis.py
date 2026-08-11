"""Erweiterte Analysen & Methodik — ADD-ON (verändert die bestehenden Seiten NICHT).

Feinere/validierte Verfahren (W-Serie) mit **visueller Kontrolle**. Bestehende Analysen bleiben
unverändert als Default; hier werden Verbesserungen parallel angeboten und geprüft.
Aktuell: W0 Methoden-Transparenz · W1 validierte R-Zacken-Detektion mit Roh-EKG-Overlay.
"""

import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

from core.i18n import tr
from core.shared import (apply_global_style, section_header, get_edf_or_stop,
                         load_and_prepare, apply_channel_overrides, safe_slider)


def _default_vs_alt_badge(default_label: str, alt_label: str) -> None:
    """Konsistente, dezent farbige Kennzeichnung: was ist Default auf den bestehenden
    Seiten (blau) vs. was ist die hier geprüfte Alternative (orange) — direkt unter dem
    Sektionstitel, statt nur im Fließtext der Caption vergraben (User-Feedback 2026-08-03)."""
    st.markdown(
        "<div style='display:flex;gap:8px;flex-wrap:wrap;margin:2px 0 12px 0'>"
        "<span style='background:#2980b90d;border:1px solid #2980b955;border-radius:6px;"
        "padding:3px 10px;font-size:12px;color:#2471a3'>"
        f"<span style='display:inline-block;width:9px;height:9px;border-radius:50%;background:#2980b9;margin-right:4px;vertical-align:middle'></span><b>Default</b> (bestehende Seiten): {default_label}</span>"
        "<span style='background:#e67e220d;border:1px solid #e67e2255;border-radius:6px;"
        "padding:3px 10px;font-size:12px;color:#c0722a'>"
        f"<span style='display:inline-block;width:9px;height:9px;border-radius:50%;background:#e67e22;margin-right:4px;vertical-align:middle'></span><b>Alternative</b> (hier geprüft): {alt_label}</span>"
        "</div>", unsafe_allow_html=True)


_DET_STYLE = {
    "eigen (aktueller Default)": ("#2980b9", "circle-open"),
    "Hamilton 2002 (validiert)": ("#e67e22", "x"),
    "Pan-Tompkins (validiert)":  ("#16a34a", "triangle-up-open"),
}


@st.cache_data(show_spinner="Erkenne R-Zacken (mehrere Detektoren) …")
def _detect_all(edf_path: str, ch: str):
    from analysis.ecg import (detect_r_peaks_polarity_safe, detect_r_peaks_validated,
                              build_rr_series, compute_hrv_time_domain)
    e = apply_channel_overrides(load_and_prepare(edf_path))
    sf = e["sfreq"]
    sig = e["data"][e["ch_idx"][ch]].astype(float)
    # Polaritäts-sicherer Pfad (User-Audit 2026-08-08): EINE Flip-Entscheidung für alle
    # Detektoren + die spätere Roh-EKG-Anzeige, damit Overlay und Kurve konsistent bleiben.
    # Siehe [[project_edf_rhythm_screening]].
    sig_corr, eigen_peaks, was_flipped = detect_r_peaks_polarity_safe(sig, sf)
    methods = {
        "eigen (aktueller Default)": eigen_peaks,
        "Hamilton 2002 (validiert)": detect_r_peaks_validated(sig_corr, sf, "hamilton"),
        "Pan-Tompkins (validiert)":  detect_r_peaks_validated(sig_corr, sf, "pan_tompkins"),
    }
    out = {}
    for label, pk in methods.items():
        pk = np.asarray(pk, int)
        rr = build_rr_series(pk, sf)
        td = compute_hrv_time_domain(rr.rr_ms[~rr.artifact_mask]) if rr is not None else {}
        out[label] = {"peaks": pk, "hrv": td}
    return out, sf, sig_corr, was_flipped


def _render_methods_table():
    from analysis.methods import METHODS
    section_header(tr("advanced.methods_validity"), tr("advanced.methods_validity_sub"))
    st.dataframe(pd.DataFrame(
        [{"Bereich": b, "Parameter": p, "Verfahren": v, "Referenz": r, "Reifegrad": m}
         for b, p, v, r, m in METHODS],
        columns=["Bereich", "Parameter", "Verfahren", "Referenz", "Reifegrad"]),
        hide_index=True, use_container_width=True)
    st.caption("✅ validiert · 🟡 akzeptierte Methode, vereinfachte Umsetzung · 🔬 Forschungs-"
               "Proxy/geplant. Diese Seite hebt die Umsetzung schrittweise (W-Serie) an — "
               "**parallel**, ohne die bestehenden Analysen zu ändern.")


def _render_rpeak_visual(edf, edf_path):
    section_header(tr("advanced.detector_comparison"),
                   "Validierte Detektoren neben dem bewährten eigenen — mit Roh-EKG-Overlay")
    _default_vs_alt_badge("eigener Detektor (vereinfachtes Pan-Tompkins)",
                          "Hamilton 2002 / Pan-Tompkins (validiert, py-ecg-detectors)")
    ecg_channels = edf.get("ecg_channels") or []
    if not ecg_channels:
        st.info(tr("advanced.no_ecg"))
        return

    sf = edf["sfreq"]
    dur = edf["duration_s"]
    c1, c2 = st.columns([2, 3])
    ch = c1.selectbox(tr("advanced.ecg_channel"), ecg_channels)
    overlay = c2.multiselect(tr("advanced.overlay_detectors"), list(_DET_STYLE.keys()),
                             default=["eigen (aktueller Default)", "Hamilton 2002 (validiert)"])

    det, _, sig_corr, was_flipped = _detect_all(edf_path, ch)
    sig_mv = sig_corr * 1000.0
    sig_mv = sig_mv - np.median(sig_mv)
    if was_flipped:
        st.caption("ℹ️ Kanal-Polaritätskonvention erkannt und für die Darstellung/Detektoren "
                   "angepasst (R-Zacke zeigt nach oben) — siehe Rhythmus-Screening-Seite für Details.")

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
    win = st.select_slider(tr("advanced.window_width"), options=[5, 10, 20, 30], value=10,
                           format_func=lambda s: f"{s} s")
    t0 = safe_slider(tr("advanced.position_s"), 0.0, float(max(0.0, dur - win)),
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
                      xaxis_title="Zeit (s)", yaxis_title="EKG (mV)", legend=dict(orientation="h", yanchor="bottom", y=1.02, font=dict(size=10)))
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
    section_header(tr("advanced.aperiodic_comparison"),
                   "Validierte Referenz-Implementierung (Donoghue 2020) parallel + visuelle Kontrolle")
    _default_vs_alt_badge("eigener Sigma-Clip-Geradenfit",
                          "FOOOF (Donoghue 2020, validierte Referenz-Implementierung)")
    eeg_map = edf.get("eeg_map", {})
    if not eeg_map:
        st.info(tr("advanced.no_eeg"))
        return
    posterior = [c for c in ("O2", "O1", "Pz", "P4", "P3") if c in eeg_map]
    opts = posterior + [c for c in eeg_map if c not in posterior]
    c1, c2, c3 = st.columns([2, 2, 2])
    ch = c1.selectbox(tr("advanced.channel"), opts, key="fooof_ch")
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
        st.warning(tr("advanced.fooof_unavailable"))
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
                      margin=dict(t=6, b=36, l=58, r=10),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, font=dict(size=10)))
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    # ── G2: Alpha-Peak aperiodik-bereinigt (FOOOF-Gipfel) vs. lineare Baseline ──
    from views.eeg_spectrum import _peak_freq_cog
    own_alpha = _peak_freq_cog(d["f"], d["p"], 8.0, 13.0)
    foof_alpha = None
    if ff:
        band_pk = [pk for pk in ff["peaks"] if 8.0 <= pk[0] <= 13.0]
        if band_pk:
            foof_alpha = max(band_pk, key=lambda x: x[1])[0]
    st.markdown(
        f"**Alpha-Peak (G2):** eigen (CoG, **lineare** 1/f-Baseline) "
        f"**{own_alpha:.2f} Hz**" if own_alpha == own_alpha else "**Alpha-Peak (G2):** eigen —"
    )
    st.caption(
        (f"FOOOF (aperiodik-bereinigt, Gipfel-Mittenfrequenz): **{foof_alpha:.2f} Hz** — "
         if foof_alpha else "FOOOF: kein Alpha-Gipfel im 8–13-Hz-Band erkannt — ")
        + "der FOOOF-Gipfel ist **echt** vom 1/f-Untergrund getrennt (kein linearer "
        "Baseline-Näherungsabzug), daher belastbarer, wenn Theta-Flanke/Untergrund den "
        "Schwerpunkt verzerren.")

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


@st.cache_data(show_spinner="Berechne HRV-Spektrum (Welch + Lomb-Scargle) …")
def _hrv_spectrum_compare(edf_path, ch):
    from views.ecg_hrv import compute_rr
    from analysis.hrv_freq import compute_frequency_domain, resample_rr, psd_welch
    from analysis.hrv_lombscargle import lombscargle_hrv
    rr = compute_rr(edf_path, ch)
    rr_ms, t = rr["rr_ms"], rr["times"]
    if len(rr_ms) < 20:
        return None
    w = compute_frequency_domain(rr_ms, t, method="welch")
    b = compute_frequency_domain(rr_ms, t, method="burg", burg_order=16)
    ls = lombscargle_hrv(rr_ms, t)
    rr_even, _ = resample_rr(rr_ms, t)
    fw, pw = psd_welch(rr_even)
    return {"welch": w, "burg": b, "lomb": ls,
            "welch_curve": (np.asarray(fw), np.asarray(pw))}


def _render_lombscargle(edf, edf_path):
    section_header(tr("advanced.hrv_spectrum_comparison"),
                   "Interpolationsfrei aus den RR-Zeitpunkten — belastbarer bei Lücken/Ektopie")
    _default_vs_alt_badge("Welch/Burg (mit PCHIP-Resampling)",
                          "Lomb-Scargle (interpolationsfrei, validiert)")
    ecg = edf.get("ecg_channels") or []
    if not ecg:
        st.info(tr("advanced.no_ecg"))
        return
    ch = st.selectbox(tr("advanced.ecg_channel"), ecg, key="ls_ch")
    d = _hrv_spectrum_compare(edf_path, ch)
    if not d or not d["lomb"]:
        st.info(tr("advanced.too_few_rr"))
        return
    w, b, ls = d["welch"], d["burg"], d["lomb"]

    def _f(x, fmt=".2f"):
        return format(x, fmt) if (x is not None and x == x) else "—"

    rows = []
    for name, src in [("Welch (Resampling)", w), ("Burg AR (Resampling)", b),
                      ("Lomb-Scargle (interpolationsfrei)", ls)]:
        if not src:
            continue
        rows.append({"Methode": name, "LF/HF": _f(src.get("lf_hf_ratio")),
                     "LFnu (%)": _f(src.get("lf_norm"), ".1f"), "HFnu (%)": _f(src.get("hf_norm"), ".1f"),
                     "LF-Gipfel (Hz)": _f(src.get("lf_peak_freq"), ".3f")})
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    # ── Visuelle Kontrolle: Spektren überlagert, LF/HF-Bänder schattiert ─────
    fw, pw = d["welch_curve"]
    mw = fw <= 0.4

    def _norm(p):
        mx = float(np.max(p)) or 1.0
        return p / mx

    fig = go.Figure()
    fig.add_vrect(x0=0.04, x1=0.15, fillcolor="rgba(41,128,185,0.09)", line_width=0,
                  annotation_text="LF", annotation_position="top left")
    fig.add_vrect(x0=0.15, x1=0.40, fillcolor="rgba(230,126,34,0.09)", line_width=0,
                  annotation_text="HF", annotation_position="top left")
    fig.add_trace(go.Scatter(x=fw[mw], y=_norm(pw[mw]), mode="lines", name="Welch (Resampling)",
                             line=dict(color="#374151", width=1.5)))
    fig.add_trace(go.Scatter(x=ls["freqs"], y=_norm(ls["psd"]), mode="lines",
                             name="Lomb-Scargle", line=dict(color="#e67e22", width=1.8)))
    fig.update_layout(height=320, xaxis_title="Frequenz (Hz)", yaxis_title="PSD (normiert)",
                      xaxis=dict(range=[0, 0.4]), margin=dict(t=6, b=36, l=55, r=10),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, font=dict(size=10)))
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    st.caption("**Lomb-Scargle** rechnet direkt auf den ungleichmäßigen RR-Zeitpunkten (**kein "
               "Resampling**) → bei Lücken/Ektopie belastbarer; Resampling kann LF überschätzen. "
               "Methodenrobust vergleichbar sind v. a. **LF/HF** und **LFnu/HFnu**. Die bestehende "
               "HRV-Frequenzanalyse (Welch/Burg) bleibt **Default**.")


@st.cache_data(show_spinner="Berechne Asymmetrie (absolut + relativ) …")
def _asym_compute(edf_path):
    from views.report import _compute_bandpower
    from views.eeg_spectrum import _highpass
    e = apply_channel_overrides(load_and_prepare(edf_path))
    sf = e["sfreq"]; dur = e["duration_s"]; em = e["eeg_map"]
    ana = min(dur, 300.0); t0 = max(0.0, (dur - ana) / 2); t1 = t0 + ana
    out = {}
    for ch in ("O1", "O2", "F3", "F4"):
        if ch in em:
            sig = _highpass(e["data"][em[ch]] * 1e6, sf, 1.0)
            bp = _compute_bandpower(sig, sf, t0, t1)[0]
            if bp:
                out[ch] = bp
    return out


def _render_asymmetry(edf, edf_path):
    section_header(tr("advanced.asymmetry"),
                   "AI zusätzlich auf relativer Bandpower — robuster gegen Impedanz/Amplitude")
    _default_vs_alt_badge("absolute Bandpower (Nuwer 1997)",
                          "relative Bandpower (impedanz-/amplitudenrobuster)")
    bps = _asym_compute(edf_path)
    BK = ["Delta (1–4 Hz)", "Theta (4–8 Hz)", "Alpha (8–13 Hz)", "Beta (13–30 Hz)"]
    BN = ["Delta", "Theta", "Alpha", "Beta"]

    def _ai(l, r):
        s = l + r
        return (l - r) / s * 100 if s > 1e-9 else float("nan")

    rows = []
    for lbl, lch, rch in [("okzipital O1/O2", "O1", "O2"), ("frontal F3/F4", "F3", "F4")]:
        if lch not in bps or rch not in bps:
            continue
        bl, br = bps[lch], bps[rch]
        # tot_l/tot_r statt tl/tr: `tr` ist appweit die Übersetzungsfunktion (core/i18n.py)
        tot_l, tot_r = (sum(bl.values()) or 1), (sum(br.values()) or 1)
        for bk, bn in zip(BK, BN):
            a_abs = _ai(bl.get(bk, 0), br.get(bk, 0))
            a_rel = _ai(bl.get(bk, 0) / tot_l, br.get(bk, 0) / tot_r)
            flag = " ⚠" if (a_rel == a_rel and abs(a_rel) > 20) else ""
            rows.append({"Region": lbl, "Band": bn,
                         "AI absolut (%)": (round(a_abs) if a_abs == a_abs else "—"),
                         "AI relativ (%)": (f"{round(a_rel)}{flag}" if a_rel == a_rel else "—")})
    if not rows:
        st.info(tr("advanced.no_posterior_anterior"))
        return
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    st.caption("Der **relative** AI (Bandpower als Anteil je Kanal) ist robuster gegen "
               "Impedanz-/Amplituden-Unterschiede zwischen den Elektroden. |AI| ≤ 20 % normal "
               "(Nuwer 1997, ⚠ = darüber). Die bestehende Asymmetrie-Ansicht (EEG-Spektrum) nutzt "
               "weiterhin die **absolute** Variante als Default.")


@st.cache_data(show_spinner="Berechne DFA (α1 + α2) …")
def _dfa_compare(edf_path, ch):
    from views.ecg_hrv import compute_rr
    from analysis.ecg import dfa_alpha1, dfa_alpha12
    rr = compute_rr(edf_path, ch)["rr_ms"]
    return {"n": len(rr), "own": dfa_alpha1(rr), "std": dfa_alpha12(rr)}


def _render_dfa(edf, edf_path):
    section_header(tr("advanced.dfa"),
                   "Standard-DFA (Peng 1995) neben unserer nicht-überlappenden α1-Variante")
    _default_vs_alt_badge("eigene α1-Variante (nicht-überlappende Fenster)",
                          "Standard-DFA α1+α2, überlappende Fenster (Peng 1995)")
    ecg = edf.get("ecg_channels") or []
    if not ecg:
        st.info(tr("advanced.no_ecg"))
        return
    ch = st.selectbox(tr("advanced.ecg_channel"), ecg, key="dfa_ch")
    d = _dfa_compare(edf_path, ch)
    own, std = d["own"], d["std"]
    if not std:
        st.info(tr("advanced.too_few_beats_dfa"))
        return

    def _f(v, fmt=".2f"):
        return format(v, fmt) if (v is not None and v == v) else "—"

    st.dataframe(pd.DataFrame([
        {"Parameter": "α1 (4–16 Schläge)", "eigen (nicht überlappend)": _f(own["alpha1"] if own else float("nan")),
         "Standard-DFA (überlappend)": _f(std["alpha1"]), "Deutung": "~1,0 gesund · ↓0,5 Zufälligkeit"},
        {"Parameter": "α2 (16–64 Schläge)", "eigen (nicht überlappend)": "— (nicht berechnet)",
         "Standard-DFA (überlappend)": _f(std["alpha2"]), "Deutung": "Langzeit-Korrelation (neu)"},
    ]), hide_index=True, use_container_width=True)

    sc = np.asarray(std["scales"], float)
    F = np.asarray(std["F"], float)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=sc, y=F, mode="markers+lines", name="F(n)",
                             line=dict(color="#374151", width=1),
                             marker=dict(size=6, color="#374151")))
    for lo, hi, col, nm, a in [(4, 16, "#2980b9", "α1-Fit", std["alpha1"]),
                               (16, 64, "#e67e22", "α2-Fit", std["alpha2"])]:
        m = (sc >= lo) & (sc <= hi) & (F > 0)
        if m.sum() >= 3 and a == a:
            c = np.polyfit(np.log10(sc[m]), np.log10(F[m]), 1)
            fig.add_trace(go.Scatter(x=sc[m], y=10 ** np.polyval(c, np.log10(sc[m])), mode="lines",
                                     name=f"{nm} (α={a:.2f})", line=dict(color=col, width=2.5, dash="dash")))
    fig.update_layout(height=320, xaxis_type="log", yaxis_type="log",
                      xaxis_title="Fenstergröße n (Schläge)", yaxis_title="F(n)",
                      margin=dict(t=6, b=36, l=55, r=10),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, font=dict(size=10)))
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    st.caption(f"{d['n']} RR-Intervalle · **Standard-DFA** nutzt **überlappende** Fenster (50 %) → "
               "bessere Statistik je Skala, und liefert zusätzlich **α2** (langsame/sympathisch-"
               "humorale Anteile). Validiert: weißes Rauschen α≈0,5 · Random Walk α≈1,5. Die "
               "bestehende HRV-Seite nutzt weiterhin die eigene α1-Variante als Default.")


@st.cache_data(show_spinner="Berechne Spektrum (Welch + Multitaper) …")
def _mt_compare(edf_path, ch):
    from views.eeg_spectrum import (_compute_psd, _highpass, _band_power, _peak_freq,
                                    _spectral_edge, BANDS)
    e = apply_channel_overrides(load_and_prepare(edf_path))
    sf, dur = e["sfreq"], e["duration_s"]
    ana = min(dur, 300.0); t0 = max(0.0, (dur - ana) / 2)
    sig = _highpass(e["data"][e["eeg_map"][ch]] * 1e6, sf, 1.0)
    seg = sig[int(t0 * sf):int((t0 + ana) * sf)]
    out = {}
    for name, mt in [("Welch", False), ("Multitaper", True)]:
        f, p = _compute_psd(seg, sf, multitaper=mt, amp_thresh_uv=9999.0)
        if f is None:
            continue
        bp = {bn: _band_power(f, p, lo, hi) for bn, (lo, hi), _ in BANDS}
        tot = sum(bp.values()) or 1
        out[name] = {"f": np.asarray(f), "p": np.asarray(p),
                     "rel": {k: v / tot * 100 for k, v in bp.items()},
                     "alpha_peak": _peak_freq(f, p, 8.0, 13.0),
                     "sef95": _spectral_edge(f, p, 0.95)}
    return out


def _render_multitaper(edf, edf_path):
    section_header(tr("advanced.multitaper"),
                   "DPSS-Multitaper (Thomson 1982): weniger Leakage, schärfere Gipfel")
    _default_vs_alt_badge("Welch", "Multitaper (DPSS, Thomson 1982, validiert)")
    em = edf.get("eeg_map", {})
    if not em:
        st.info(tr("advanced.no_eeg"))
        return
    posterior = [c for c in ("O2", "O1", "Pz", "P4", "P3") if c in em]
    opts = posterior + [c for c in em if c not in posterior]
    ch = st.selectbox(tr("advanced.channel"), opts, key="mt_ch")
    d = _mt_compare(edf_path, ch)
    if "Welch" not in d or "Multitaper" not in d:
        st.info(tr("advanced.spectrum_uncomputable"))
        return
    w, m = d["Welch"], d["Multitaper"]

    def _f(v, fmt=".1f"):
        return format(v, fmt) if (v is not None and v == v) else "—"

    rows = [{"Parameter": f"{bn} relativ", "Welch": _f(w["rel"].get(bn)),
             "Multitaper": _f(m["rel"].get(bn)), "Einheit": "%"}
            for bn in ("Delta", "Theta", "Alpha", "Beta")]
    rows += [{"Parameter": "Alpha-Peak", "Welch": _f(w["alpha_peak"], ".2f"),
              "Multitaper": _f(m["alpha_peak"], ".2f"), "Einheit": "Hz"},
             {"Parameter": "SEF95", "Welch": _f(w["sef95"]), "Multitaper": _f(m["sef95"]), "Einheit": "Hz"}]
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=w["f"], y=w["p"], mode="lines", name="Welch",
                             line=dict(color="#374151", width=1.4)))
    fig.add_trace(go.Scatter(x=m["f"], y=m["p"], mode="lines", name="Multitaper (DPSS)",
                             line=dict(color="#e67e22", width=1.8)))
    fig.update_layout(height=320, yaxis_type="log", xaxis_title="Frequenz (Hz)",
                      yaxis_title="PSD (µV²/Hz)", margin=dict(t=6, b=36, l=58, r=10),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, font=dict(size=10)))
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    st.caption("**Multitaper** (DPSS, NW=3/K=5) reduziert Spectral Leakage → **schärferer, besser "
               "aufgelöster Alpha-Gipfel** und stabilere Bandwerte, besonders bei kurzen/verrauschten "
               "Abschnitten. Die bestehenden Seiten nutzen **Welch als Default** (Multitaper dort als "
               "Option); hier der direkte Vergleich.")


def render():
    apply_global_style()
    edf, edf_path = get_edf_or_stop()
    st.title(":material/science: " + tr("advanced.title"))
    st.markdown(
        "**Add-on** zu den bestehenden Seiten — diese bleiben **unverändert** und sind weiterhin "
        "der Default. Hier werden feinere/validierte Verfahren **parallel** angeboten und mit "
        "**visueller Kontrolle** geprüft, bevor irgendetwas umgestellt wird."
    )
    _render_methods_table()
    st.divider()
    # EEG-Themen zuerst (analog Navigator-Reihenfolge: EEG vor Herzrhythmus),
    # danach alle EKG/HRV-Themen — bewusst thematisch gruppiert statt alternierend.
    _render_fooof(edf, edf_path)
    st.divider()
    _render_multitaper(edf, edf_path)
    st.divider()
    _render_asymmetry(edf, edf_path)
    st.divider()
    _render_rpeak_visual(edf, edf_path)
    st.divider()
    _render_lombscargle(edf, edf_path)
    st.divider()
    _render_dfa(edf, edf_path)
