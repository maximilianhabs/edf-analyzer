"""Seite: Report — Gesamtübersicht: Aufnahme, HRV, EEG-Spektrum. Selbstständig berechnend."""

import math

import numpy as np
import pandas as pd
import streamlit as st
from scipy.signal import welch

from core.shared import get_edf_or_stop, load_and_prepare, apply_channel_overrides


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def _nan(val, fmt=".1f", fallback="—"):
    try:
        if val is None or (isinstance(val, float) and math.isnan(val)):
            return fallback
        return format(float(val), fmt)
    except (TypeError, ValueError):
        return fallback


def _zone(val, lo, hi):
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "—"
    v = float(val)
    if lo <= v <= hi:
        return "✅"
    if v < lo * 0.65 or v > hi * 1.5:
        return "🔴"
    return "🟡"


def _psd_bandpower(freqs, psd, lo, hi):
    mask = (freqs >= lo) & (freqs < hi)
    if mask.sum() < 2:
        return 0.0
    return float(np.trapezoid(psd[mask], freqs[mask]))


def _alpha_peak(freqs, psd, lo=8.0, hi=13.0):
    mask = (freqs >= lo) & (freqs < hi)
    if mask.sum() < 2:
        return float("nan")
    return float(freqs[mask][np.argmax(psd[mask])])


def _compute_bandpower(sig, fs, t_start=0, t_end=None):
    """Berechnet Bandpower-Dict für ein EEG-Signal."""
    i0 = int(t_start * fs)
    i1 = int(t_end * fs) if t_end else len(sig)
    seg = sig[i0:i1]
    if len(seg) < 256:
        return None, None, None, float("nan")
    nperseg = min(int(fs * 4), len(seg) // 2, 1024)
    freqs, psd = welch(seg, fs=fs, nperseg=nperseg, noverlap=nperseg // 2, scaling="density")
    mask = (freqs >= 1.0) & (freqs <= 30.0)
    freqs, psd = freqs[mask], psd[mask]
    bp = {
        "Delta (1–4 Hz)":  _psd_bandpower(freqs, psd, 1.0, 4.0),
        "Theta (4–8 Hz)":  _psd_bandpower(freqs, psd, 4.0, 8.0),
        "Alpha (8–13 Hz)": _psd_bandpower(freqs, psd, 8.0, 13.0),
        "Beta (13–30 Hz)": _psd_bandpower(freqs, psd, 13.0, 30.0),
    }
    ap = _alpha_peak(freqs, psd)
    return bp, freqs, psd, ap


def _compute_hrv(edf_path, edf):
    """Berechnet HRV-Zeitbereich + nichtlineare + Frequenzbereich + EDR. Gibt Dict zurück."""
    from views.ecg_hrv import compute_rr
    from analysis.hrv_freq import compute_frequency_domain
    from analysis.ecg import compute_hrv_time_domain, dfa_alpha1, edr_from_ecg
    from analysis.complexity import sample_entropy
    ecg_channels = edf.get("ecg_channels", [])
    if not ecg_channels:
        return None
    ecg_ch = ecg_channels[0]
    rr_data = compute_rr(edf_path, ecg_ch)
    rr_ms = rr_data["rr_ms"]
    r_times = rr_data["times"]
    if len(rr_ms) < 10:
        return None
    fs = rr_data["fs"]

    # Kanonischer Zeitbereich (inkl. CV, NN50, pNN20, SD1/SD2/SD2SD1)
    td = compute_hrv_time_domain(rr_ms)
    n_total = rr_data["n_peaks_total"]
    n_removed = rr_data["n_removed"]
    pct_removed = n_removed / max(n_total, 1) * 100

    # Nichtlinear
    _dfa = dfa_alpha1(rr_ms)
    dfa_a1 = _dfa["alpha1"] if _dfa else float("nan")
    samp_en = sample_entropy(rr_ms) if len(rr_ms) >= 20 else float("nan")

    # EDR (Atmung aus R-Amplitude)
    edr_rate = float("nan")
    try:
        _ecg = edf.get("ecg_filtered", {}).get(ecg_ch)
        if _ecg is not None:
            _edr = edr_from_ecg(_ecg, rr_data["peaks"], fs)
            if _edr:
                edr_rate = _edr["resp_rate_bpm"]
    except Exception:
        pass

    fd_welch = fd_burg = None
    try:
        fd_welch = compute_frequency_domain(rr_ms, r_times, method="welch")
        fd_burg  = compute_frequency_domain(rr_ms, r_times, method="burg", burg_order=16)
    except Exception:
        pass

    return {
        "mean_hr": td["mean_hr_bpm"], "mean_rr": td["mean_rr_ms"],
        "sdnn": td["sdnn_ms"], "cv": td["cv_pct"], "rmssd": td["rmssd_ms"],
        "pnn50": td["pnn50_pct"], "pnn20": td["pnn20_pct"], "nn50": td["nn50_count"],
        "sd1": td["sd1_ms"], "sd2": td["sd2_ms"], "sd2_sd1": td["sd2_sd1_ratio"],
        "dfa_a1": dfa_a1, "samp_en": samp_en, "edr_rate": edr_rate,
        "pct_removed": pct_removed, "fd_welch": fd_welch, "fd_burg": fd_burg,
    }


# ── Hauptseite ────────────────────────────────────────────────────────────────

def render():
    st.title("📋 Report")
    st.caption("Tabellarische Gesamtübersicht — Aufnahme, Herzanalyse, EEG-Spektrum.")

    edf, edf_path = get_edf_or_stop()
    sfreq = edf["sfreq"]
    dur_s = edf["duration_s"]

    # ── 1. Aufnahme ───────────────────────────────────────────────────────────
    with st.expander("📂 Aufnahme & Metadaten", expanded=True):
        meta_df = pd.DataFrame([
            {"Parameter": "Dateiname",      "Wert": st.session_state.get("edf_display_name", "—")},
            {"Parameter": "Dauer",          "Wert": f"{dur_s / 60:.1f} min  ({int(dur_s)} s)"},
            {"Parameter": "Abtastrate",     "Wert": f"{sfreq:.0f} Hz"},
            {"Parameter": "Kanäle gesamt",  "Wert": str(len(edf["ch_names"]))},
            {"Parameter": "EEG-Kanäle",     "Wert": str(len(edf.get("eeg_map", {})))},
            {"Parameter": "EKG erkannt",    "Wert": "ja" if edf.get("ecg_channels") else "nein"},
            {"Parameter": "Epochen (10 s)", "Wert": str(edf["n_epochs"])},
            {"Parameter": "Datenschutz",    "Wert":
                "⚠️ PHI im Header" if (edf.get("has_patient_id") or edf.get("has_rec_id"))
                else "✅ anonymisiert"},
        ])
        st.dataframe(meta_df, hide_index=True, use_container_width=True)

        if edf.get("annotations"):
            st.markdown("**Annotationen / Ereignisse**")
            st.dataframe(pd.DataFrame([
                {"Zeit (s)": f"{a['onset_s']:.1f}", "Ereignis": a["description"]}
                for a in edf["annotations"]
            ]), hide_index=True, use_container_width=True)

        with st.expander("Alle Kanäle — Signal-Statistik"):
            rows = []
            for i, ch in enumerate(edf["ch_names"]):
                sig = edf["data"][i]
                sig_d = sig - sig.mean()
                unit = "µV" if ch.startswith("EEG") else "mV"
                factor = 1e6 if ch.startswith("EEG") else 1e3
                rows.append({
                    "Nr": i, "Kanal": ch,
                    f"Min ({unit})": f"{sig_d.min() * factor:.1f}",
                    f"Max ({unit})": f"{sig_d.max() * factor:.1f}",
                    f"RMS ({unit})": f"{np.sqrt(np.mean(sig_d ** 2)) * factor:.1f}",
                })
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    # ── 2. Herzanalyse / HRV ──────────────────────────────────────────────────
    with st.expander("❤️ Herzanalyse — HRV", expanded=False):
        if not edf.get("ecg_channels"):
            st.info("Kein EKG-Kanal in dieser Aufnahme erkannt.")
        else:
            hrv = st.session_state.get("hrv_summary_report")
            if hrv is None:
                with st.spinner("Berechne HRV …"):
                    try:
                        hrv = _compute_hrv(edf_path, edf)
                        st.session_state["hrv_summary_report"] = hrv
                    except Exception as e:
                        st.warning(f"HRV-Berechnung fehlgeschlagen: {e}")
                        hrv = None

            if not hrv:
                st.info("Keine HRV-Daten verfügbar.")
            else:
                st.markdown("**Zeitbereich — Grundwerte & Variabilität**")
                td = pd.DataFrame([
                    {"Parameter": "Herzfrequenz (HR)", "Wert": _nan(hrv["mean_hr"], ".1f"), "Einheit": "bpm",
                     "Referenz": "67  (IQR 61–74)", "": _zone(hrv["mean_hr"], 60, 100)},
                    {"Parameter": "Mittleres RR",  "Wert": _nan(hrv["mean_rr"], ".0f"), "Einheit": "ms",
                     "Referenz": "600–1000",        "": "—"},
                    {"Parameter": "SDNN",   "Wert": _nan(hrv["sdnn"],   ".1f"), "Einheit": "ms",
                     "Referenz": "37  (IQR 27–54)", "": _zone(hrv["sdnn"], 20, 80)},
                    {"Parameter": "CV (Variationskoeff.)", "Wert": _nan(hrv["cv"], ".1f"), "Einheit": "%",
                     "Referenz": "HF-unabhängig",   "": "—"},
                ])
                st.dataframe(td, hide_index=True, use_container_width=True)

                st.markdown("**Zeitbereich — vagale (parasympathische) Marker**")
                tv = pd.DataFrame([
                    {"Parameter": "RMSSD",  "Wert": _nan(hrv["rmssd"],  ".1f"), "Einheit": "ms",
                     "Referenz": "27  (IQR 17–44)", "": _zone(hrv["rmssd"], 15, 80)},
                    {"Parameter": "pNN50",  "Wert": _nan(hrv["pnn50"],  ".1f"), "Einheit": "%",
                     "Referenz": "~12  (5–28)",     "": "—"},
                    {"Parameter": "pNN20",  "Wert": _nan(hrv["pnn20"],  ".1f"), "Einheit": "%",
                     "Referenz": "sensitiver als pNN50", "": "—"},
                    {"Parameter": "NN50 (Absolutzahl)", "Wert": _nan(hrv["nn50"], ".0f"), "Einheit": "",
                     "Referenz": "längenabhängig",  "": "—"},
                ])
                st.dataframe(tv, hide_index=True, use_container_width=True)

                st.markdown("**Nichtlinear — Poincaré & Komplexität**")
                tn = pd.DataFrame([
                    {"Parameter": "SD1 (kurzfristig/vagal)", "Wert": _nan(hrv["sd1"], ".1f"), "Einheit": "ms",
                     "Referenz": "≈ RMSSD/√2",      "": "—"},
                    {"Parameter": "SD2 (langfristig)", "Wert": _nan(hrv["sd2"], ".1f"), "Einheit": "ms",
                     "Referenz": "≈ SDNN",          "": "—"},
                    {"Parameter": "SD2/SD1",        "Wert": _nan(hrv["sd2_sd1"], ".2f"), "Einheit": "—",
                     "Referenz": "Balance lang/kurz", "": "—"},
                    {"Parameter": "DFA α₁ (fraktal)", "Wert": _nan(hrv["dfa_a1"], ".2f"), "Einheit": "—",
                     "Referenz": "~1,0 gesund",     "": _zone(hrv["dfa_a1"], 0.75, 1.25)},
                    {"Parameter": "Sample Entropy", "Wert": _nan(hrv["samp_en"], ".2f"), "Einheit": "—",
                     "Referenz": "niedrig=regelmäßig", "": "—"},
                    {"Parameter": "Atemfrequenz (EDR)", "Wert": _nan(hrv["edr_rate"], ".1f"), "Einheit": "/min",
                     "Referenz": "12–20",           "": _zone(hrv["edr_rate"], 12, 20)},
                    {"Parameter": "Artefaktrate", "Wert": _nan(hrv["pct_removed"], ".1f"), "Einheit": "%",
                     "Referenz": "< 5 % gut",      "": _zone(hrv["pct_removed"], 0, 15)},
                ])
                st.dataframe(tn, hide_index=True, use_container_width=True)

                for fd_label, fd_key in [("Frequenzbereich — Welch (FFT)", "fd_welch"),
                                          ("Frequenzbereich — Burg (MEM)",  "fd_burg")]:
                    fd = hrv.get(fd_key)
                    if not fd:
                        continue
                    st.markdown(f"**{fd_label}**")
                    lf_hf = fd.get("lf_hf_ratio", float("nan"))
                    lf_n  = fd.get("lf_norm",     float("nan"))
                    hf_n  = fd.get("hf_norm",     float("nan"))
                    resp  = fd.get("hf_resp_rate", float("nan"))
                    fd_df = pd.DataFrame([
                        {"Parameter": "Total Power",       "Wert": _nan(fd.get("total_power"), ".0f"), "Einheit": "ms²",  "Referenz": "235–1033",  "": _zone(fd.get("total_power"), 235, 1033)},
                        {"Parameter": "LF-Leistung",       "Wert": _nan(fd.get("lf_power"),    ".0f"), "Einheit": "ms²",  "Referenz": "67–368",    "": _zone(fd.get("lf_power"),    67,  368)},
                        {"Parameter": "HF-Leistung",       "Wert": _nan(fd.get("hf_power"),    ".0f"), "Einheit": "ms²",  "Referenz": "38–263",    "": _zone(fd.get("hf_power"),    38,  263)},
                        {"Parameter": "LF/HF-Ratio",       "Wert": _nan(lf_hf,  ".2f"),               "Einheit": "—",    "Referenz": "0.5–5.0",   "": _zone(lf_hf,  0.5,  5.0)},
                        {"Parameter": "LF normiert",        "Wert": _nan(lf_n,   ".1f"),               "Einheit": "%",    "Referenz": "40–70 %",   "": _zone(lf_n,   40,   70)},
                        {"Parameter": "HF normiert",        "Wert": _nan(hf_n,   ".1f"),               "Einheit": "%",    "Referenz": "20–50 %",   "": _zone(hf_n,   20,   50)},
                        {"Parameter": "LF-Gipfel",          "Wert": _nan(fd.get("lf_peak_freq"), ".3f"), "Einheit": "Hz", "Referenz": "0.04–0.15 Hz", "": _zone(fd.get("lf_peak_freq"), 0.04, 0.15)},
                        {"Parameter": "HF-Gipfel",          "Wert": _nan(fd.get("hf_peak_freq"), ".3f"), "Einheit": "Hz", "Referenz": "0.15–0.40 Hz", "": _zone(fd.get("hf_peak_freq"), 0.15, 0.40)},
                        {"Parameter": "Atemfrequenz (RSA)", "Wert": _nan(resp,   ".0f"),               "Einheit": "/min", "Referenz": "12–20 /min","": _zone(resp,   12,   20)},
                    ])
                    st.dataframe(fd_df, hide_index=True, use_container_width=True)

    # ── 3. EEG-Spektralanalyse ────────────────────────────────────────────────
    with st.expander("📊 EEG-Spektralanalyse", expanded=False):
        eeg_map = edf.get("eeg_map", {})
        if not eeg_map:
            st.info("Keine EEG-Kanäle gefunden.")
        else:
            # Konsensus-Kanäle: O1/O2 posterior, F3/F4 anterior
            _get = lambda ch: edf["data"][eeg_map[ch]] * 1e6 if ch in eeg_map else None
            sig_o1, sig_o2 = _get("O1"), _get("O2")
            sig_f3, sig_f4 = _get("F3"), _get("F4")

            sig_post = (sig_o1 + sig_o2) / 2 if sig_o1 is not None and sig_o2 is not None else (sig_o1 or sig_o2)
            sig_ant  = (sig_f3 + sig_f4) / 2 if sig_f3 is not None and sig_f4 is not None else (sig_f3 or sig_f4)

            if sig_post is None:
                st.info("Keine posterioren Kanäle (O1/O2) verfügbar.")
            else:
                # Analysefenster: max 5 Minuten aus der Mitte der Aufnahme
                ana_dur = min(dur_s, 300.0)
                t_start = max(0.0, (dur_s - ana_dur) / 2)
                t_end   = t_start + ana_dur
                st.caption(
                    f"Analysefenster: {int(t_start)}–{int(t_end)} s "
                    f"({ana_dur/60:.0f} min) · Methode: Welch"
                )

                BAND_KEYS = ["Delta (1–4 Hz)", "Theta (4–8 Hz)", "Alpha (8–13 Hz)", "Beta (13–30 Hz)"]
                BAND_NAMES = ["Delta", "Theta", "Alpha", "Beta"]

                # Bandpower berechnen
                _res_p = _compute_bandpower(sig_post, sfreq, t_start, t_end)
                bp_p, ap_post = _res_p[0], _res_p[3] if _res_p[0] else (None, float("nan"))
                _res_a = _compute_bandpower(sig_ant, sfreq, t_start, t_end) if sig_ant is not None else None
                bp_a = _res_a[0] if _res_a and _res_a[0] else {}
                ap_ant_val = _res_a[3] if _res_a and _res_a[0] else float("nan")

                if bp_p:
                    tp = sum(bp_p.values()) or 1
                    ta = sum(bp_a.values()) or 1

                    st.markdown("**Bandpower — absolut (µV²) und relativ**")
                    bp_rows = []
                    for bk, bn in zip(BAND_KEYS, BAND_NAMES):
                        vp = bp_p.get(bk, 0)
                        va = bp_a.get(bk, 0) if bp_a else float("nan")
                        bp_rows.append({
                            "Band":                    bn,
                            "Post absolut (µV²)":      f"{vp:.3f}",
                            "Post relativ":            f"{vp / tp * 100:.1f} %",
                            "Ant absolut (µV²)":       f"{va:.3f}" if not math.isnan(va) else "—",
                            "Ant relativ":             f"{va / ta * 100:.1f} %" if not math.isnan(va) else "—",
                        })
                    st.dataframe(pd.DataFrame(bp_rows), hide_index=True, use_container_width=True)

                    # Alpha-Peak + Gradient
                    st.markdown("**Alpha-Gipfelfrequenz & Posterior/Anterior-Gradient**")
                    ap_ant = ap_ant_val
                    ap_ratio = bp_p.get("Alpha (8–13 Hz)", 0) / (bp_a.get("Alpha (8–13 Hz)", 0) or 1e-9) if bp_a else float("nan")
                    st.dataframe(pd.DataFrame([
                        {"Parameter": "Alpha-Gipfel posterior (O1/O2)",
                         "Wert": _nan(ap_post, ".2f") + " Hz",
                         "Referenz": "8–13 Hz", "": _zone(ap_post, 8, 13)},
                        {"Parameter": "Alpha-Gipfel anterior (F3/F4)",
                         "Wert": _nan(ap_ant, ".2f") + " Hz" if not math.isnan(ap_ant) else "—",
                         "Referenz": "8–13 Hz", "": _zone(ap_ant, 8, 13)},
                        {"Parameter": "Post/Ant Alpha-Ratio",
                         "Wert": _nan(ap_ratio, ".2f"),
                         "Referenz": "> 1.0  (posterior dominant)",
                         "": "✅" if (not math.isnan(ap_ratio) and ap_ratio > 1.0) else "🟡"},
                    ]), hide_index=True, use_container_width=True)

                    # Klinische Ratios
                    st.markdown("**Klinische Frequenzratios**")
                    d = bp_p.get("Delta (1–4 Hz)", 0)
                    t = bp_p.get("Theta (4–8 Hz)", 0)
                    a = bp_p.get("Alpha (8–13 Hz)", 0) or 1e-9
                    b = bp_p.get("Beta (13–30 Hz)", 0) or 1e-9
                    RATIO_REF = {
                        "Delta/Alpha": (d / a, 0.0,  1.5, "Diffuse Verlangsamung / Enzephalopathie"),
                        "Theta/Alpha": (t / a, 0.2,  0.7, "Frühmarker kognitiver Dysfunktion"),
                        "Alpha/Theta": (a / (t or 1e-9), 1.5, 6.0, "Vigilanz / Wachheit"),
                        "Theta/Beta":  (t / b, 0.5,  2.0, "Schläfrigkeit / Aktivierung"),
                        "DTAB":        ((d + t) / (a + b), 0.0, 0.5, "(D+T)/(A+B) — kortikale Funktionsstörung"),
                    }
                    ratio_rows = []
                    for rname, (rval, lo, hi, hint) in RATIO_REF.items():
                        ratio_rows.append({
                            "Ratio":       rname,
                            "Wert":        _nan(rval, ".3f"),
                            "Normbereich": f"{lo}–{hi}",
                            "":            _zone(rval, lo, hi),
                            "Klinischer Hinweis": hint,
                        })
                    st.dataframe(pd.DataFrame(ratio_rows), hide_index=True, use_container_width=True)

                    # ── Spektrale Kennzahlen, Aperiodik & Komplexität (posterior) ──
                    freqs_p, psd_p = _res_p[1], _res_p[2]
                    if freqs_p is not None and len(freqs_p) > 2:
                        from views.eeg_spectrum import _spectral_edge, _compute_par
                        from analysis.aperiodic import fit_aperiodic, band_power_defs
                        from analysis.complexity import sample_entropy, lziv_complexity
                        with st.spinner("Berechne spektrale Kennzahlen & Komplexität …"):
                            _sef95 = _spectral_edge(freqs_p, psd_p, 0.95)
                            _medf  = _spectral_edge(freqs_p, psd_p, 0.50)
                            _rap20 = fit_aperiodic(freqs_p, psd_p, 1, 20)
                            _exp20 = _rap20["exponent"] if _rap20 else float("nan")
                            _r2_20 = _rap20["r2"] if _rap20 else float("nan")
                            _flat_a = band_power_defs(freqs_p, psd_p, 8, 13, res=_rap20)["flattened"]
                            _seg = sig_post[int(t_start * sfreq):int(t_end * sfreq)]
                            _sampen = sample_entropy(_seg, max_n=4000) if len(_seg) >= 100 else float("nan")
                            _lzc = lziv_complexity(_seg, sfreq) if len(_seg) >= int(5 * sfreq) else {"shuffle": float("nan"), "phase": float("nan")}
                        st.markdown("**Spektrale Kennzahlen, Aperiodik & Komplexität (posterior O1/O2)**")
                        st.dataframe(pd.DataFrame([
                            {"Parameter": "SEF95 (spektrale Randfrequenz)", "Wert": _nan(_sef95, ".1f"), "Einheit": "Hz", "Referenz": "sinkt bei Verlangsamung"},
                            {"Parameter": "Medianfrequenz (SEF50)", "Wert": _nan(_medf, ".1f"), "Einheit": "Hz", "Referenz": "sinkt bei Verlangsamung"},
                            {"Parameter": "Aperiod. Exponent (1–20 Hz)", "Wert": _nan(_exp20, ".2f"), "Einheit": "—", "Referenz": f"R²={_nan(_r2_20, '.2f')} · flach=aktiviert"},
                            {"Parameter": "Alpha flattened (aperiodik-bereinigt)", "Wert": _nan(_flat_a, ".2f"), "Einheit": "—", "Referenz": ">0 = echter Alpha-Gipfel"},
                            {"Parameter": "Sample Entropy", "Wert": _nan(_sampen, ".2f"), "Einheit": "—", "Referenz": "niedrig=regelmäßig (↓ Bewusstsein)"},
                            {"Parameter": "LZC (shuffle)", "Wert": _nan(_lzc.get("shuffle"), ".2f"), "Einheit": "—", "Referenz": "hoch=komplex"},
                            {"Parameter": "LZC (phase)", "Wert": _nan(_lzc.get("phase"), ".2f"), "Einheit": "—", "Referenz": ">1=spektral-unabh. komplex"},
                        ]), hide_index=True, use_container_width=True)

                        # ── Anterior-Posterior-Gradient (ganzer Kopf, PAR) ──────
                        try:
                            _par = _compute_par(edf_path, t_start, t_end, 8.0, 13.0, False, 9999.0)
                            if _par["n_post"] >= 2 and _par["n_ant"] >= 2:
                                st.markdown("**Anterior-Posterior-Gradient (ganzer Kopf)**")
                                st.dataframe(pd.DataFrame([
                                    {"Parameter": "Alpha-PAR (post/ant, geom. Mittel)",
                                     "Wert": _nan(_par["par"], ".2f"), "Einheit": "—",
                                     "Referenz": ">1 posterior-dominant", "": _zone(_par["par"], 1.0, 99)},
                                    {"Parameter": "Exponent-Gradient (post−ant)",
                                     "Wert": _nan(_par["exp_grad"], "+.2f"), "Einheit": "—",
                                     "Referenz": f"{_par['n_post']} post · {_par['n_ant']} ant", "": "—"},
                                ]), hide_index=True, use_container_width=True)
                        except Exception:
                            pass

    # ── 4. Export: kompletter Report als PDF / Excel ──────────────────────────
    st.divider()
    st.subheader("⬇️ Gesamt-Report exportieren")
    st.caption("Alle Werte kompakt und sortiert (Aufnahme · HRV · EEG-Spektrum · Aperiodik · "
               "Asymmetrie) — je Zeile Wert, Einheit und kurze Norm. Ohne Kommentar.")

    @st.cache_data(show_spinner="Erstelle Report-Dateien …")
    def _export_bytes(_path, _disp):
        from analysis.report_export import collect_sections, build_excel, build_pdf
        e = apply_channel_overrides(load_and_prepare(_path))
        secs = collect_sections(e, _path)
        return build_pdf(secs, _disp), build_excel(secs, e, _disp)

    _disp = st.session_state.get("edf_display_name", "report")
    _base = _disp.rsplit(".", 1)[0] if _disp else "report"
    @st.cache_data(show_spinner="Erstelle Visual Report …")
    def _glory_bytes(_path, _disp):
        from analysis.glory_report import build_glory_pdf
        e = apply_channel_overrides(load_and_prepare(_path))
        return build_glory_pdf(e, _path, _disp)

    try:
        pdf_bytes, xlsx_bytes = _export_bytes(edf_path, _disp)
        ec1, ec2, ec3 = st.columns(3)
        ec1.download_button("📄 PDF herunterladen", pdf_bytes, file_name=f"{_base}_report.pdf",
                            mime="application/pdf", use_container_width=True)
        ec2.download_button(
            "📊 Excel herunterladen", xlsx_bytes, file_name=f"{_base}_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True)
        with ec3:
            try:
                ec3.download_button("🎨 Visual Report (PDF)", _glory_bytes(edf_path, _disp),
                                    file_name=f"{_base}_visual.pdf", mime="application/pdf",
                                    type="primary", use_container_width=True)
            except Exception as ex:
                st.caption(f"Visual Report nicht verfügbar: {ex}")
        st.caption("**🎨 Visual Report** = grafischer Abstract (A4 quer, 6 Seiten): Roh-EEG, "
                   "Spektrogramm, Bandverteilung, A/P-Gradient, Asymmetrie, EKG mit QRS-Erkennung, "
                   "RR vor/nach Bereinigung, Poincaré & HRV-Spektrum — nur robuste Marker, "
                   "zum Zeigen und Präsentieren.")
    except Exception as e:
        st.error(f"Report-Export fehlgeschlagen: {e}")
