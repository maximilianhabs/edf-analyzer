"""Seite: Report — Gesamtübersicht: Aufnahme, HRV, EEG-Spektrum. Selbstständig berechnend."""

import math

import numpy as np
import pandas as pd
import streamlit as st
from scipy.signal import welch

from core.i18n import tr
from core.shared import get_edf_or_stop, load_and_prepare, apply_channel_overrides, get_patient_info


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
    st.title(":material/description: " + tr("report.title"))
    st.caption(tr("report.subtitle"))

    edf, edf_path = get_edf_or_stop()
    sfreq = edf["sfreq"]
    dur_s = edf["duration_s"]

    # Spaltenüberschriften der Tabellen: EINMAL hier, nicht in den einzelnen Zweigen — sie
    # werden auch in der EEG-Sektion gebraucht, die ohne EKG-Kanal erreicht wird, während der
    # HRV-Zweig dann übersprungen wird.
    _P, _V = tr("report.col_parameter"), tr("report.col_value")
    _U, _R = tr("report.col_unit"), tr("report.col_reference")

    # ── 1. Aufnahme ───────────────────────────────────────────────────────────
    with st.expander(tr("report.section_recording"), icon=":material/folder_open:", expanded=True):
        meta_df = pd.DataFrame([
            {_P: tr("report.meta_filename"),       _V: st.session_state.get("edf_display_name", "—")},
            {_P: tr("report.meta_duration"),       _V: f"{dur_s / 60:.1f} min  ({int(dur_s)} s)"},
            {_P: tr("report.meta_samplerate"),     _V: f"{sfreq:.0f} Hz"},
            {_P: tr("report.meta_channels_total"), _V: str(len(edf["ch_names"]))},
            {_P: tr("report.meta_eeg_channels"),   _V: str(len(edf.get("eeg_map", {})))},
            {_P: tr("report.meta_ecg_detected"),   _V: tr("report.meta_yes") if edf.get("ecg_channels") else tr("report.meta_no")},
            {_P: tr("report.meta_epochs"),         _V: str(edf["n_epochs"])},
            {_P: tr("report.meta_privacy"),        _V:
                tr("report.meta_phi_present") if (edf.get("has_patient_id") or edf.get("has_rec_id"))
                else tr("report.meta_anonymized")},
        ])
        st.dataframe(meta_df, hide_index=True, use_container_width=True)

        if edf.get("annotations"):
            st.markdown(tr("report.annotations_header"))
            _T, _E = tr("report.col_time_s"), tr("report.col_event")
            st.dataframe(pd.DataFrame([
                {_T: f"{a['onset_s']:.1f}", _E: a["description"]}
                for a in edf["annotations"]
            ]), hide_index=True, use_container_width=True)

        with st.expander(tr("report.all_channels_stats")):
            rows = []
            for i, ch in enumerate(edf["ch_names"]):
                sig = edf["data"][i]
                sig_d = sig - sig.mean()
                unit = "µV" if ch.startswith("EEG") else "mV"
                factor = 1e6 if ch.startswith("EEG") else 1e3
                rows.append({
                    tr("report.col_nr"): i, tr("report.col_channel"): ch,
                    f"Min ({unit})": f"{sig_d.min() * factor:.1f}",
                    f"Max ({unit})": f"{sig_d.max() * factor:.1f}",
                    f"RMS ({unit})": f"{np.sqrt(np.mean(sig_d ** 2)) * factor:.1f}",
                })
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    # ── 2. Herzanalyse / HRV ──────────────────────────────────────────────────
    with st.expander(tr("report.section_hrv"), icon=":material/ecg_heart:", expanded=False):
        if not edf.get("ecg_channels"):
            st.info(tr("report.no_ecg"))
        else:
            hrv = st.session_state.get("hrv_summary_report")
            if hrv is None:
                with st.spinner(tr("report.computing_hrv")):
                    try:
                        hrv = _compute_hrv(edf_path, edf)
                        st.session_state["hrv_summary_report"] = hrv
                    except Exception as e:
                        st.warning(tr("report.hrv_failed", err=e))
                        hrv = None

            if not hrv:
                st.info(tr("report.no_hrv_data"))
            else:
                st.markdown(tr("report.hrv_time_basic"))
                td = pd.DataFrame([
                    {_P: tr("report.p_hr"), _V: _nan(hrv["mean_hr"], ".1f"), _U: "bpm",
                     _R: "67  (IQR 61–74)", "": _zone(hrv["mean_hr"], 60, 100)},
                    {_P: tr("report.p_mean_rr"),  _V: _nan(hrv["mean_rr"], ".0f"), _U: "ms",
                     _R: "600–1000",        "": "—"},
                    {_P: "SDNN",   _V: _nan(hrv["sdnn"],   ".1f"), _U: "ms",
                     _R: "37  (IQR 27–54)", "": _zone(hrv["sdnn"], 20, 80)},
                    {_P: tr("report.p_cv"), _V: _nan(hrv["cv"], ".1f"), _U: "%",
                     _R: tr("report.ref_hr_independent"),   "": "—"},
                ])
                st.dataframe(td, hide_index=True, use_container_width=True)

                st.markdown(tr("report.hrv_time_vagal"))
                tv = pd.DataFrame([
                    {_P: "RMSSD",  _V: _nan(hrv["rmssd"],  ".1f"), _U: "ms",
                     _R: "27  (IQR 17–44)", "": _zone(hrv["rmssd"], 15, 80)},
                    {_P: "pNN50",  _V: _nan(hrv["pnn50"],  ".1f"), _U: "%",
                     _R: "~12  (5–28)",     "": "—"},
                    {_P: "pNN20",  _V: _nan(hrv["pnn20"],  ".1f"), _U: "%",
                     _R: tr("report.ref_more_sensitive"), "": "—"},
                    {_P: tr("report.p_nn50"), _V: _nan(hrv["nn50"], ".0f"), _U: "",
                     _R: tr("report.ref_length_dependent"),  "": "—"},
                ])
                st.dataframe(tv, hide_index=True, use_container_width=True)

                st.markdown(tr("report.hrv_nonlinear"))
                tn = pd.DataFrame([
                    {_P: tr("report.p_sd1"), _V: _nan(hrv["sd1"], ".1f"), _U: "ms",
                     _R: "≈ RMSSD/√2",      "": "—"},
                    {_P: tr("report.p_sd2"), _V: _nan(hrv["sd2"], ".1f"), _U: "ms",
                     _R: "≈ SDNN",          "": "—"},
                    {_P: "SD2/SD1",        _V: _nan(hrv["sd2_sd1"], ".2f"), _U: "—",
                     _R: tr("report.ref_balance"), "": "—"},
                    {_P: tr("report.p_dfa"), _V: _nan(hrv["dfa_a1"], ".2f"), _U: "—",
                     _R: tr("report.ref_healthy_1"),     "": _zone(hrv["dfa_a1"], 0.75, 1.25)},
                    {_P: tr("report.p_sampen"), _V: _nan(hrv["samp_en"], ".2f"), _U: "—",
                     _R: tr("report.ref_low_regular"), "": "—"},
                    {_P: tr("report.p_resp_edr"), _V: _nan(hrv["edr_rate"], ".1f"), _U: "/min",
                     _R: "12–20",           "": _zone(hrv["edr_rate"], 12, 20)},
                    {_P: tr("report.p_artifact_rate"), _V: _nan(hrv["pct_removed"], ".1f"), _U: "%",
                     _R: tr("report.ref_below_5_good"),      "": _zone(hrv["pct_removed"], 0, 15)},
                ])
                st.dataframe(tn, hide_index=True, use_container_width=True)

                for fd_label, fd_key in [(tr("report.fd_welch"), "fd_welch"),
                                          (tr("report.fd_burg"),  "fd_burg")]:
                    fd = hrv.get(fd_key)
                    if not fd:
                        continue
                    st.markdown(f"**{fd_label}**")
                    lf_hf = fd.get("lf_hf_ratio", float("nan"))
                    lf_n  = fd.get("lf_norm",     float("nan"))
                    hf_n  = fd.get("hf_norm",     float("nan"))
                    resp  = fd.get("hf_resp_rate", float("nan"))
                    fd_df = pd.DataFrame([
                        {_P: tr("report.p_total_power"),       _V: _nan(fd.get("total_power"), ".0f"), _U: "ms²",  _R: "235–1033",  "": _zone(fd.get("total_power"), 235, 1033)},
                        {_P: tr("report.p_lf_power"),       _V: _nan(fd.get("lf_power"),    ".0f"), _U: "ms²",  _R: "67–368",    "": _zone(fd.get("lf_power"),    67,  368)},
                        {_P: tr("report.p_hf_power"),       _V: _nan(fd.get("hf_power"),    ".0f"), _U: "ms²",  _R: "38–263",    "": _zone(fd.get("hf_power"),    38,  263)},
                        {_P: tr("report.p_lf_hf"),       _V: _nan(lf_hf,  ".2f"),               _U: "—",    _R: "0.5–5.0",   "": _zone(lf_hf,  0.5,  5.0)},
                        {_P: tr("report.p_lf_norm"),        _V: _nan(lf_n,   ".1f"),               _U: "%",    _R: "40–70 %",   "": _zone(lf_n,   40,   70)},
                        {_P: tr("report.p_hf_norm"),        _V: _nan(hf_n,   ".1f"),               _U: "%",    _R: "20–50 %",   "": _zone(hf_n,   20,   50)},
                        {_P: tr("report.p_lf_peak"),          _V: _nan(fd.get("lf_peak_freq"), ".3f"), _U: "Hz", _R: "0.04–0.15 Hz", "": _zone(fd.get("lf_peak_freq"), 0.04, 0.15)},
                        {_P: tr("report.p_hf_peak"),          _V: _nan(fd.get("hf_peak_freq"), ".3f"), _U: "Hz", _R: "0.15–0.40 Hz", "": _zone(fd.get("hf_peak_freq"), 0.15, 0.40)},
                        {_P: tr("report.p_resp_rsa"), _V: _nan(resp,   ".0f"),               _U: "/min", _R: "12–20 /min","": _zone(resp,   12,   20)},
                    ])
                    st.dataframe(fd_df, hide_index=True, use_container_width=True)

    # ── 3. EEG-Spektralanalyse ────────────────────────────────────────────────
    with st.expander(tr("report.section_eeg"), icon=":material/bar_chart:", expanded=False):
        eeg_map = edf.get("eeg_map", {})
        if not eeg_map:
            st.info(tr("report.no_eeg"))
        else:
            # Konsensus-Kanäle: O1/O2 posterior, F3/F4 anterior
            _get = lambda ch: edf["data"][eeg_map[ch]] * 1e6 if ch in eeg_map else None
            sig_o1, sig_o2 = _get("O1"), _get("O2")
            sig_f3, sig_f4 = _get("F3"), _get("F4")

            sig_post = (sig_o1 + sig_o2) / 2 if sig_o1 is not None and sig_o2 is not None else (sig_o1 or sig_o2)
            sig_ant  = (sig_f3 + sig_f4) / 2 if sig_f3 is not None and sig_f4 is not None else (sig_f3 or sig_f4)

            if sig_post is None:
                st.info(tr("report.no_posterior"))
            else:
                # Analysefenster: max 5 Minuten aus der Mitte der Aufnahme
                ana_dur = min(dur_s, 300.0)
                t_start = max(0.0, (dur_s - ana_dur) / 2)
                t_end   = t_start + ana_dur
                st.caption(tr("report.analysis_window", t0=int(t_start), t1=int(t_end),
                              min=ana_dur / 60))

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

                    st.markdown(tr("report.bandpower_header"))
                    bp_rows = []
                    for bk, bn in zip(BAND_KEYS, BAND_NAMES):
                        vp = bp_p.get(bk, 0)
                        va = bp_a.get(bk, 0) if bp_a else float("nan")
                        bp_rows.append({
                            tr("report.col_band"):     bn,
                            tr("report.col_post_abs"): f"{vp:.3f}",
                            tr("report.col_post_rel"): f"{vp / tp * 100:.1f} %",
                            tr("report.col_ant_abs"):  f"{va:.3f}" if not math.isnan(va) else "—",
                            tr("report.col_ant_rel"):  f"{va / ta * 100:.1f} %" if not math.isnan(va) else "—",
                        })
                    st.dataframe(pd.DataFrame(bp_rows), hide_index=True, use_container_width=True)

                    # Alpha-Peak + Gradient
                    st.markdown(tr("report.alpha_peak_header"))
                    ap_ant = ap_ant_val
                    ap_ratio = bp_p.get("Alpha (8–13 Hz)", 0) / (bp_a.get("Alpha (8–13 Hz)", 0) or 1e-9) if bp_a else float("nan")
                    st.dataframe(pd.DataFrame([
                        {_P: tr("report.p_alpha_post"),
                         _V: _nan(ap_post, ".2f") + " Hz",
                         _R: "8–13 Hz", "": _zone(ap_post, 8, 13)},
                        {_P: tr("report.p_alpha_ant"),
                         _V: _nan(ap_ant, ".2f") + " Hz" if not math.isnan(ap_ant) else "—",
                         _R: "8–13 Hz", "": _zone(ap_ant, 8, 13)},
                        {_P: tr("report.p_alpha_ratio"),
                         _V: _nan(ap_ratio, ".2f"),
                         _R: tr("report.ref_posterior_dominant"),
                         "": "✅" if (not math.isnan(ap_ratio) and ap_ratio > 1.0) else "🟡"},
                    ]), hide_index=True, use_container_width=True)

                    # Klinische Ratios
                    st.markdown(tr("report.clinical_ratios"))
                    d = bp_p.get("Delta (1–4 Hz)", 0)
                    t = bp_p.get("Theta (4–8 Hz)", 0)
                    a = bp_p.get("Alpha (8–13 Hz)", 0) or 1e-9
                    b = bp_p.get("Beta (13–30 Hz)", 0) or 1e-9
                    RATIO_REF = {
                        "Delta/Alpha": (d / a, 0.0,  1.5, tr("report.hint_slowing")),
                        "Theta/Alpha": (t / a, 0.2,  0.7, tr("report.hint_cognitive")),
                        "Alpha/Theta": (a / (t or 1e-9), 1.5, 6.0, tr("report.hint_vigilance")),
                        "Theta/Beta":  (t / b, 0.5,  2.0, tr("report.hint_drowsiness")),
                        "DTAB":        ((d + t) / (a + b), 0.0, 0.5, tr("report.hint_dtab")),
                    }
                    ratio_rows = []
                    for rname, (rval, lo, hi, hint) in RATIO_REF.items():
                        ratio_rows.append({
                            tr("report.col_ratio"):         rname,
                            _V:                             _nan(rval, ".3f"),
                            tr("report.col_normal_range"):  f"{lo}–{hi}",
                            "":                             _zone(rval, lo, hi),
                            tr("report.col_clinical_hint"): hint,
                        })
                    st.dataframe(pd.DataFrame(ratio_rows), hide_index=True, use_container_width=True)

                    # ── Spektrale Kennzahlen, Aperiodik & Komplexität (posterior) ──
                    freqs_p, psd_p = _res_p[1], _res_p[2]
                    if freqs_p is not None and len(freqs_p) > 2:
                        from views.eeg_spectrum import _spectral_edge, _compute_par
                        from analysis.aperiodic import fit_aperiodic, band_power_defs
                        from analysis.complexity import sample_entropy, lziv_complexity
                        with st.spinner(tr("report.computing_spectral")):
                            _sef95 = _spectral_edge(freqs_p, psd_p, 0.95)
                            _medf  = _spectral_edge(freqs_p, psd_p, 0.50)
                            _rap20 = fit_aperiodic(freqs_p, psd_p, 1, 20)
                            _exp20 = _rap20["exponent"] if _rap20 else float("nan")
                            _r2_20 = _rap20["r2"] if _rap20 else float("nan")
                            _flat_a = band_power_defs(freqs_p, psd_p, 8, 13, res=_rap20)["flattened"]
                            _seg = sig_post[int(t_start * sfreq):int(t_end * sfreq)]
                            _sampen = sample_entropy(_seg, max_n=4000) if len(_seg) >= 100 else float("nan")
                            _lzc = lziv_complexity(_seg, sfreq) if len(_seg) >= int(5 * sfreq) else {"shuffle": float("nan"), "phase": float("nan")}
                        st.markdown(tr("report.spectral_header"))
                        st.dataframe(pd.DataFrame([
                            {_P: tr("report.p_sef95"), _V: _nan(_sef95, ".1f"), _U: "Hz", _R: tr("report.ref_drops_slowing")},
                            {_P: tr("report.p_medfreq"), _V: _nan(_medf, ".1f"), _U: "Hz", _R: tr("report.ref_drops_slowing")},
                            {_P: tr("report.p_aperiodic_exp"), _V: _nan(_exp20, ".2f"), _U: "—", _R: tr("report.ref_flat_activated", r2=_nan(_r2_20, ".2f"))},
                            {_P: tr("report.p_alpha_flattened"), _V: _nan(_flat_a, ".2f"), _U: "—", _R: tr("report.ref_true_alpha")},
                            {_P: tr("report.p_sampen"), _V: _nan(_sampen, ".2f"), _U: "—", _R: tr("report.ref_low_regular_consciousness")},
                            {_P: tr("report.p_lzc_shuffle"), _V: _nan(_lzc.get("shuffle"), ".2f"), _U: "—", _R: tr("report.ref_high_complex")},
                            {_P: tr("report.p_lzc_phase"), _V: _nan(_lzc.get("phase"), ".2f"), _U: "—", _R: tr("report.ref_spectral_independent")},
                        ]), hide_index=True, use_container_width=True)

                        # ── Anterior-Posterior-Gradient (ganzer Kopf, PAR) ──────
                        try:
                            _par = _compute_par(edf_path, t_start, t_end, 8.0, 13.0, False, 9999.0)
                            if _par["n_post"] >= 2 and _par["n_ant"] >= 2:
                                st.markdown(tr("report.ap_gradient_header"))
                                st.dataframe(pd.DataFrame([
                                    {_P: tr("report.p_alpha_par"),
                                     _V: _nan(_par["par"], ".2f"), _U: "—",
                                     _R: tr("report.ref_par_posterior"), "": _zone(_par["par"], 1.0, 99)},
                                    {_P: tr("report.p_exp_gradient"),
                                     _V: _nan(_par["exp_grad"], "+.2f"), _U: "—",
                                     _R: tr("report.ref_post_ant_count", n_post=_par["n_post"], n_ant=_par["n_ant"]), "": "—"},
                                ]), hide_index=True, use_container_width=True)
                        except Exception:
                            pass

    # ── 4. Export: kompletter Report als PDF / Excel ──────────────────────────
    st.divider()
    st.subheader("⬇️ " + tr("report.export_header"))
    st.caption(tr("report.export_caption"))

    @st.cache_data(show_spinner=False)  # Spinner an der Aufrufstelle, s. core/shared.py
    def _export_bytes(_path, _disp, _age, _sex, _pediatric):
        from analysis.report_export import (collect_sections, build_excel, build_pdf,
                                            build_manifest)
        e = apply_channel_overrides(load_and_prepare(_path))
        secs = collect_sections(e, _path, age=_age, sex=_sex, is_pediatric=_pediatric)
        return (build_pdf(secs, _disp), build_excel(secs, e, _disp),
                build_manifest(secs, e, _path, _disp, age=_age, sex=_sex,
                               is_pediatric=_pediatric))

    _disp = st.session_state.get("edf_display_name", "report")
    _base = _disp.rsplit(".", 1)[0] if _disp else "report"
    _rep_age, _rep_sex = get_patient_info()
    _rep_pediatric = st.session_state.get("is_pediatric", False)
    @st.cache_data(show_spinner=False)
    def _glory_bytes(_path, _disp, _age, _pediatric):
        from analysis.glory_report import build_glory_pdf
        e = apply_channel_overrides(load_and_prepare(_path))
        return build_glory_pdf(e, _path, _disp, age=_age, is_pediatric=_pediatric)

    # Erzeugen NUR auf Knopfdruck (User-Entscheidung 2026-08-13). Vorher genügte das Öffnen
    # dieser Seite, um PDF, Excel, Manifest UND den visuellen Report zu bauen — auf einer
    # 10-Minuten-Aufnahme rund 7 Sekunden, davon 5,7 in collect_sections. Die Arbeit steckt
    # also nicht im Schreiben der Dateien, sondern im Rechnen davor; ein Knopf spart sie fast
    # vollständig. Und häufig will man den Report gar nicht, sondern nur die Tabellen oben.
    st.caption(tr("report.build_caption"))
    if st.button(tr("report.build_button"), icon=":material/description:",
                 key="report_build", type="primary"):
        try:
            with st.spinner(tr("report.creating_reports")):
                st.session_state["report_export"] = _export_bytes(
                    edf_path, _disp, _rep_age, _rep_sex, _rep_pediatric)
        except Exception as e:
            st.session_state.pop("report_export", None)
            st.error(tr("report.export_failed", err=e))

    _fertig = st.session_state.get("report_export")
    if not _fertig:
        st.info(tr("report.build_hint"), icon=":material/hourglass_empty:")
    else:
        pdf_bytes, xlsx_bytes, manifest_bytes = _fertig
        ec1, ec2, ec3 = st.columns(3)
        ec1.download_button(tr("report.download_pdf"), pdf_bytes, icon=":material/description:", file_name=f"{_base}_report.pdf",
                            mime="application/pdf", use_container_width=True)
        ec2.download_button(
            tr("report.download_excel"), xlsx_bytes, icon=":material/bar_chart:", file_name=f"{_base}_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True)
        # Eigener Knopf: der visuelle Report kostet noch einmal gut eine Sekunde und wird
        # seltener gebraucht als PDF und Excel.
        with ec3:
            if st.session_state.get("visual_export") is None:
                if st.button(tr("report.build_visual_button"), icon=":material/palette:",
                             key="visual_build", use_container_width=True):
                    try:
                        with st.spinner(tr("report.creating_visual")):
                            st.session_state["visual_export"] = _glory_bytes(
                                edf_path, _disp, _rep_age, _rep_pediatric)
                    except Exception as ex:
                        st.caption(tr("report.visual_unavailable", err=ex))
            if st.session_state.get("visual_export") is not None:
                ec3.download_button(tr("report.download_visual"),
                                    st.session_state["visual_export"],
                                    icon=":material/palette:", file_name=f"{_base}_visual.pdf", mime="application/pdf",
                                    type="primary", use_container_width=True)
        st.caption(tr("report.build_visual_caption"))
        st.caption(tr("report.visual_caption"))

        # Maschinenlesbar, bewusst als vierter Knopf unter den drei Report-Formaten: PDF,
        # Excel und Visual sind für Menschen. Wer eine Serie auswertet oder ein Ergebnis
        # anderswo nachrechnet, braucht dieselben Werte in einlesbarer Form — samt Herkunft
        # und Datei-Prüfsumme. Enthält KEINE Kopfdaten der Aufnahme (siehe build_manifest).
        st.download_button(
            tr("report.download_manifest"), manifest_bytes,
            icon=":material/data_object:", file_name=f"{_base}_manifest.json",
            mime="application/json", use_container_width=True)
        st.caption(tr("report.manifest_caption"))
