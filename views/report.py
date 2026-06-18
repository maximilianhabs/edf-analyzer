"""Seite: Report — Gesamtübersicht: Aufnahme, HRV, EEG-Spektrum. Selbstständig berechnend."""

import math

import numpy as np
import pandas as pd
import streamlit as st
from scipy.signal import welch

from core.shared import get_edf_or_stop


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
    return float(np.trapz(psd[mask], freqs[mask]))


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
    """Berechnet HRV-Zeitbereich + Frequenzbereich. Gibt Dict zurück."""
    from views.ecg_hrv import compute_rr
    from analysis.hrv_freq import compute_frequency_domain
    ecg_channels = edf.get("ecg_channels", [])
    if not ecg_channels:
        return None
    ecg_ch = ecg_channels[0]
    rr_data = compute_rr(edf_path, ecg_ch)
    rr_ms = rr_data["rr_ms"]
    r_times = rr_data["times"]
    if len(rr_ms) < 10:
        return None

    mean_rr = float(np.mean(rr_ms))
    mean_hr = 60000 / mean_rr
    sdnn    = float(np.std(rr_ms, ddof=1))
    rmssd   = float(np.sqrt(np.mean(np.diff(rr_ms) ** 2)))
    pnn50   = float(np.sum(np.abs(np.diff(rr_ms)) > 50) / max(len(np.diff(rr_ms)), 1) * 100)
    n_total = rr_data["n_peaks_total"]
    n_removed = rr_data["n_removed"]
    pct_removed = n_removed / max(n_total, 1) * 100

    fd_welch = fd_burg = None
    try:
        fd_welch = compute_frequency_domain(rr_ms, r_times, method="welch")
        fd_burg  = compute_frequency_domain(rr_ms, r_times, method="burg", burg_order=16)
    except Exception:
        pass

    return {
        "mean_hr": mean_hr, "sdnn": sdnn, "rmssd": rmssd, "pnn50": pnn50,
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
            hrv = st.session_state.get("hrv_summary")
            if hrv is None:
                with st.spinner("Berechne HRV …"):
                    try:
                        hrv = _compute_hrv(edf_path, edf)
                        if hrv:
                            st.session_state["hrv_summary_report"] = hrv
                    except Exception as e:
                        st.warning(f"HRV-Berechnung fehlgeschlagen: {e}")
                        hrv = None
            # Priorität: frisch berechnete Daten aus Report, dann aus EKG-Seite
            hrv = hrv or st.session_state.get("hrv_summary_report")

            if not hrv:
                st.info("Keine HRV-Daten verfügbar. Bitte die Seite **EKG & HRV** einmal öffnen.")
            else:
                st.markdown("**Zeitbereich**")
                td = pd.DataFrame([
                    {"Parameter": "Herzfrequenz (HR)", "Wert": _nan(hrv["mean_hr"], ".1f"), "Einheit": "bpm",
                     "Referenz": "67  (IQR 61–74)", "": _zone(hrv["mean_hr"], 60, 100)},
                    {"Parameter": "SDNN",   "Wert": _nan(hrv["sdnn"],   ".1f"), "Einheit": "ms",
                     "Referenz": "37  (IQR 27–54)", "": _zone(hrv["sdnn"], 20, 80)},
                    {"Parameter": "RMSSD",  "Wert": _nan(hrv["rmssd"],  ".1f"), "Einheit": "ms",
                     "Referenz": "27  (IQR 17–44)", "": _zone(hrv["rmssd"], 15, 80)},
                    {"Parameter": "pNN50",  "Wert": _nan(hrv["pnn50"],  ".1f"), "Einheit": "%",
                     "Referenz": "~12  (5–28)",     "": "—"},
                    {"Parameter": "Artefaktrate", "Wert": _nan(hrv["pct_removed"], ".1f"), "Einheit": "%",
                     "Referenz": "< 5 % gut",      "": _zone(hrv["pct_removed"], 0, 15)},
                ])
                st.dataframe(td, hide_index=True, use_container_width=True)

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
