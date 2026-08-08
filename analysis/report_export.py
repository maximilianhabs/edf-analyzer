"""Kompakter Gesamt-Report-Export (PDF + Excel) — vereinheitlicht.

Eine zentrale Stelle, wo ALLES zusammenläuft:
  • bestehende Parameter (HRV Zeit/vagal/nichtlinear/Frequenz Welch, EEG Bandpower abs+rel,
    Alpha-Gipfel/PAR, Ratios, Verlangsamung/Aperiodik/Komplexität, Asymmetrie),
  • je Wert eine **Korrigiert**-Spalte (artefaktkorrigiert, Auto- oder übergebene Maske),
  • eine Sektion **Validierte Zusatzverfahren** (eigen vs. validiert: Hamilton-R-Zacken, FOOOF,
    Lomb-Scargle, relative Asymmetrie, aperiodik-bereinigter Alpha-Peak, Permutationsentropie).

Je Zeile Wert · Einheit · Norm/Richtungsdeutung. Ausgabe Excel (openpyxl) + PDF (reportlab,
Unicode-Font DejaVu → α₁, ≤, ↑↓, − korrekt). Verändert die bestehenden Analyse-Seiten NICHT.
"""

from __future__ import annotations

import io
import math
import os

import numpy as np

_BK = ["Delta (1–4 Hz)", "Theta (4–8 Hz)", "Alpha (8–13 Hz)", "Beta (13–30 Hz)"]
_BN = ["Delta", "Theta", "Alpha", "Beta"]


def _f(v, fmt=".1f"):
    try:
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return "—"
        return format(float(v), fmt)
    except (TypeError, ValueError):
        return "—"


# ──────────────────────────────────────────────────────────────────────────────
# Signal-/Metrik-Helfer
# ──────────────────────────────────────────────────────────────────────────────
def _clean_sig(sig, fs, segments):
    keep = np.ones(len(sig), dtype=bool)
    for s in segments:
        keep[max(0, int(s["start_s"] * fs)):min(len(sig), int(s["end_s"] * fs))] = False
    return sig[keep]


def _ai(l, r):
    s = l + r
    return (l - r) / s * 100 if s > 1e-9 else float("nan")


def _eeg_metrics(edf, edf_path, segments=None):
    """Alle EEG-Spektral-Kennzahlen als flaches Dict — einmal Gesamt (segments=None),
    einmal artefaktkorrigiert (segments=Liste, Signale sample-bereinigt)."""
    from views.report import _compute_bandpower
    from views.eeg_spectrum import _highpass, _spectral_edge, _peak_freq_cog
    corrected = bool(segments)
    sf, dur, em = edf["sfreq"], edf["duration_s"], edf["eeg_map"]

    def raw(ch):
        if ch not in em:
            return None
        s = _highpass(edf["data"][em[ch]] * 1e6, sf, 1.0)
        return _clean_sig(s, sf, segments) if corrected else s

    o1, o2, f3, f4 = raw("O1"), raw("O2"), raw("F3"), raw("F4")
    post = (o1 + o2) / 2 if o1 is not None and o2 is not None else (o1 if o1 is not None else o2)
    ant = (f3 + f4) / 2 if f3 is not None and f4 is not None else (f3 if f3 is not None else f4)
    m = {}
    if post is None:
        return m
    if corrected:
        t0, t1 = 0.0, None
    else:
        ana = min(dur, 300.0); t0 = max(0.0, (dur - ana) / 2); t1 = t0 + ana

    bp_p, fp, pp, ap_p = _compute_bandpower(post, sf, t0, t1)
    if not bp_p:
        return m
    res_a = _compute_bandpower(ant, sf, t0, t1) if ant is not None else (None,)
    bp_a = res_a[0] if res_a and res_a[0] else {}
    ap_a = res_a[3] if res_a and res_a[0] else float("nan")
    tp = sum(bp_p.values()) or 1
    ta = sum(bp_a.values()) or 1

    m["rel_post"] = {bn: bp_p.get(bk, 0) / tp * 100 for bk, bn in zip(_BK, _BN)}
    m["abs_post"] = {bn: bp_p.get(bk, 0) for bk, bn in zip(_BK, _BN)}
    m["rel_ant"] = {bn: bp_a.get(bk, 0) / ta * 100 for bk, bn in zip(_BK, _BN)} if bp_a else {}
    m["abs_ant"] = {bn: bp_a.get(bk, 0) for bk, bn in zip(_BK, _BN)} if bp_a else {}
    m["ap_post"], m["ap_ant"] = ap_p, ap_a
    m["cog_post"] = _peak_freq_cog(fp, pp, 8.0, 13.0)
    a_p = bp_p.get("Alpha (8–13 Hz)", 0)
    a_a = bp_a.get("Alpha (8–13 Hz)", 0) if bp_a else 0
    m["ap_ratio"] = a_p / (a_a or 1e-9) if bp_a else float("nan")
    d = bp_p.get("Delta (1–4 Hz)", 0); t = bp_p.get("Theta (4–8 Hz)", 0)
    a = a_p or 1e-9; b = bp_p.get("Beta (13–30 Hz)", 0) or 1e-9
    m["dar"], m["tar"] = d / a, t / a
    m["atr"], m["tbr"], m["dtab"] = a / (t or 1e-9), t / b, (d + t) / (a + b)

    m["sef95"] = _spectral_edge(fp, pp, 0.95)
    m["medf"] = _spectral_edge(fp, pp, 0.50)
    try:
        from analysis.aperiodic import fit_aperiodic, band_power_defs
        from analysis.complexity import sample_entropy, lziv_complexity, permutation_entropy
        rap = fit_aperiodic(fp, pp, 1, 20)
        m["exp_own"] = rap["exponent"] if rap else float("nan")
        m["r2_own"] = rap["r2"] if rap else float("nan")
        m["flat_alpha"] = band_power_defs(fp, pp, 8, 13, res=rap)["flattened"]
        seg = post if corrected else post[int(t0 * sf):int(t1 * sf)]
        m["sampen"] = sample_entropy(seg, max_n=4000) if len(seg) >= 100 else float("nan")
        m["permen"] = permutation_entropy(seg) if len(seg) >= 100 else float("nan")
        m["lzc"] = lziv_complexity(seg, sf) if len(seg) >= int(5 * sf) else {"shuffle": float("nan"), "phase": float("nan")}
    except Exception:
        m["lzc"] = {"shuffle": float("nan"), "phase": float("nan")}

    m["par"], m["exp_grad"] = float("nan"), float("nan")
    if not corrected:
        try:
            from views.eeg_spectrum import _compute_par
            par = _compute_par(edf_path, t0, t1, 8.0, 13.0, False, 9999.0)
            if par["n_post"] >= 2 and par["n_ant"] >= 2:
                m["par"], m["exp_grad"] = par["par"], par["exp_grad"]
        except Exception:
            pass

    m["ai"] = {}
    for lbl, lch, rch in [("O1/O2", "O1", "O2"), ("F3/F4", "F3", "F4")]:
        sl, sr = raw(lch), raw(rch)
        if sl is None or sr is None:
            continue
        bl = _compute_bandpower(sl, sf, t0, t1)[0]
        br = _compute_bandpower(sr, sf, t0, t1)[0]
        if not bl or not br:
            continue
        tl, tr = (sum(bl.values()) or 1), (sum(br.values()) or 1)
        for bk, bn in zip(_BK, _BN):
            m["ai"][(lbl, bn, "abs")] = _ai(bl.get(bk, 0), br.get(bk, 0))
            m["ai"][(lbl, bn, "rel")] = _ai(bl.get(bk, 0) / tl, br.get(bk, 0) / tr)
    return m


def _compute_hrv_corrected(edf_path, edf, segments):
    from analysis.ecg import detect_r_peaks_polarity_safe, build_rr_series, compute_hrv_time_domain, dfa_alpha1
    from analysis.complexity import sample_entropy
    from analysis.hrv_freq import compute_frequency_domain
    ch = edf["ecg_channels"][0]
    if ch not in edf.get("ch_idx", {}):
        return None
    fs = edf["sfreq"]
    sig = edf["data"][edf["ch_idx"][ch]].astype(float)
    # Polaritäts-sicherer Pfad (User-Audit 2026-08-08) — siehe [[project_edf_rhythm_screening]]
    _, peaks, _ = detect_r_peaks_polarity_safe(sig, fs)
    rr = build_rr_series(peaks, fs)
    if rr is None:
        return None
    rr_ms, times, ect = rr.rr_ms, rr.rr_times_s, rr.artifact_mask
    in_seg = np.zeros(len(rr_ms), dtype=bool)
    for s in segments:
        in_seg |= (times >= s["start_s"]) & (times < s["end_s"])
    keep = (~ect) & (~in_seg)
    rr_c, times_c = rr_ms[keep], times[keep]
    if len(rr_c) < 10:
        return None
    td = compute_hrv_time_domain(rr_c)
    _dfa = dfa_alpha1(rr_c)
    fd = None
    try:
        fd = compute_frequency_domain(rr_c, times_c, method="welch")
    except Exception:
        pass
    return {"mean_hr": td["mean_hr_bpm"], "mean_rr": td["mean_rr_ms"], "sdnn": td["sdnn_ms"],
            "cv": td["cv_pct"], "rmssd": td["rmssd_ms"], "pnn50": td["pnn50_pct"],
            "pnn20": td["pnn20_pct"], "nn50": td["nn50_count"], "sd1": td["sd1_ms"],
            "sd2": td["sd2_ms"], "sd2_sd1": td["sd2_sd1_ratio"],
            "dfa_a1": _dfa["alpha1"] if _dfa else float("nan"),
            "samp_en": sample_entropy(rr_c) if len(rr_c) >= 20 else float("nan"),
            "edr_rate": float("nan"), "pct_removed": float("nan"),
            "fd_welch": fd, "fd_burg": None}


def _hrv_hamilton(edf):
    """HRV-Zeitbereich mit validiertem R-Zacken-Detektor (Hamilton 2002)."""
    from analysis.ecg import detect_r_peaks_validated, detect_polarity_flip, build_rr_series, compute_hrv_time_domain
    ch = edf["ecg_channels"][0]
    if ch not in edf.get("ch_idx", {}):
        return None
    fs = edf["sfreq"]
    sig = edf["data"][edf["ch_idx"][ch]].astype(float)
    # Polaritäts-sicherer Pfad (User-Audit 2026-08-08): erst flippen, DANACH den validierten
    # Detektor laufen lassen — sonst verschiebt dessen interne Verfeinerung den Zeitindex bei
    # invertiertem Kanal, siehe [[project_edf_rhythm_screening]].
    if detect_polarity_flip(sig - sig.mean(), fs):
        sig = -sig
    rr = build_rr_series(detect_r_peaks_validated(sig, fs, "hamilton"), fs)
    if rr is None:
        return None
    return compute_hrv_time_domain(rr.rr_ms[~rr.artifact_mask])


# ──────────────────────────────────────────────────────────────────────────────
# Sektionen zusammenstellen  →  [{name, columns, rows}]
# ──────────────────────────────────────────────────────────────────────────────
def collect_sections(edf: dict, edf_path: str, corr_segments=None):
    sections = []
    sf, dur, em = edf["sfreq"], edf["duration_s"], edf.get("eeg_map", {})
    has_ecg = bool(edf.get("ecg_channels"))

    # Artefakt-Maske für die Korrigiert-Spalte (übergeben oder automatisch)
    if corr_segments is None:
        try:
            from analysis.artifacts import mask_from_edf
            corr_segments = mask_from_edf(edf).segments
        except Exception:
            corr_segments = []
    disc = sum(s["end_s"] - s["start_s"] for s in corr_segments) if corr_segments else 0.0

    # ── Aufnahme ──────────────────────────────────────────────────────────────
    phi = "PHI im Header" if (edf.get("has_patient_id") or edf.get("has_rec_id")) else "anonymisiert"
    sections.append({"name": "Aufnahme & Erkennung",
                     "columns": ["Parameter", "Wert", "Einheit", "Hinweis"], "rows": [
        ["Dauer", f"{dur/60:.1f}", "min", f"{int(dur)} s"],
        ["Abtastrate", _f(sf, ".0f"), "Hz", ""],
        ["Kanäle gesamt", str(len(edf["ch_names"])), "", ""],
        ["EEG-Kanäle (10-20)", str(len(em)), "", ""],
        ["EKG erkannt", "ja" if has_ecg else "nein", "", edf["ecg_channels"][0] if has_ecg else ""],
        ["Datenschutz", phi, "", ""],
        ["Artefakt-Korrektur", f"{len(corr_segments)} Segmente", "",
         f"{disc:.0f}s entfernt · {max(0.0, dur-disc)/dur*100:.0f}% sauber" if dur else ""],
    ]})

    # ── HRV ───────────────────────────────────────────────────────────────────
    if has_ecg:
        try:
            from views.report import _compute_hrv
            hf = _compute_hrv(edf_path, edf)
        except Exception:
            hf = None
        hc = _compute_hrv_corrected(edf_path, edf, corr_segments) if (hf and corr_segments) else None
        if hf:
            def _g(src, k, fmt=".1f"):
                return _f(src.get(k), fmt) if src else "—"
            gc = ["Parameter", "Gesamt", "Korrigiert", "Einheit", "Norm / Deutung"]
            sections.append({"name": "HRV — Zeitbereich", "columns": gc, "rows": [
                ["Herzfrequenz", _g(hf, "mean_hr"), _g(hc, "mean_hr"), "bpm", "60–100 · ↓ athlet. Bradykardie mögl."],
                ["Mittleres RR", _g(hf, "mean_rr", ".0f"), _g(hc, "mean_rr", ".0f"), "ms", "600–1000 · ↑ bei niedriger HF"],
                ["SDNN", _g(hf, "sdnn"), _g(hc, "sdnn"), "ms", "37 (27–54) · ↑ = günstig (Gesamt-Vagotonie)"],
                ["CV", _g(hf, "cv"), _g(hc, "cv"), "%", "SDNN/RR · HF-unabhängig"],
            ]})
            sections.append({"name": "HRV — vagale Marker", "columns": gc, "rows": [
                ["RMSSD", _g(hf, "rmssd"), _g(hc, "rmssd"), "ms", "27 (17–44) · ↑ = günstig (vagal)"],
                ["pNN50", _g(hf, "pnn50"), _g(hc, "pnn50"), "%", "~12 (5–28) · ↑ = günstig"],
                ["pNN20", _g(hf, "pnn20"), _g(hc, "pnn20"), "%", "sensitiver als pNN50 · ↑ günstig"],
                ["NN50", _g(hf, "nn50", ".0f"), _g(hc, "nn50", ".0f"), "Anzahl", "längenabhängig"],
            ]})
            sections.append({"name": "HRV — nichtlinear & Atmung", "columns": gc, "rows": [
                ["SD1", _g(hf, "sd1"), _g(hc, "sd1"), "ms", "kurzfristig/vagal (≈RMSSD/√2)"],
                ["SD2", _g(hf, "sd2"), _g(hc, "sd2"), "ms", "langfristig (≈SDNN)"],
                ["SD2/SD1", _g(hf, "sd2_sd1", ".2f"), _g(hc, "sd2_sd1", ".2f"), "Ratio", "Balance lang/kurz"],
                ["DFA α1", _g(hf, "dfa_a1", ".2f"), _g(hc, "dfa_a1", ".2f"), "—", "~1,0 gesund (0,75–1,25)"],
                ["Sample Entropy", _g(hf, "samp_en", ".2f"), _g(hc, "samp_en", ".2f"), "—", "↓ = regelmäßig"],
                ["Atemfrequenz (EDR)", _g(hf, "edr_rate"), "—", "/min", "12–20 · aus R-Amplitude, unsicher"],
                ["Artefaktrate RR", _g(hf, "pct_removed"), "—", "%", "< 5 % gut"],
            ]})
            fw, fwc = (hf.get("fd_welch") or {}), (hc.get("fd_welch") if hc else {}) or {}
            sections.append({"name": "HRV — Frequenzbereich (Welch, Task Force 1996)", "columns": gc, "rows": [
                ["Total Power", _f(fw.get("total_power"), ".0f"), _f(fwc.get("total_power"), ".0f"), "ms²", "235–1033 · ↑ bei hoher HRV günstig"],
                ["VLF-Leistung", _f(fw.get("vlf_power"), ".0f"), _f(fwc.get("vlf_power"), ".0f"), "ms²", "0,0033–0,04 Hz · bei Kurzzeit unsicher"],
                ["LF-Leistung", _f(fw.get("lf_power"), ".0f"), _f(fwc.get("lf_power"), ".0f"), "ms²", "67–368 · 0,04–0,15 Hz"],
                ["HF-Leistung", _f(fw.get("hf_power"), ".0f"), _f(fwc.get("hf_power"), ".0f"), "ms²", "38–263 · 0,15–0,40 Hz · ↑ = vagal"],
                ["LF/HF-Ratio", _f(fw.get("lf_hf_ratio"), ".2f"), _f(fwc.get("lf_hf_ratio"), ".2f"), "Ratio", "0,5–5,0 · Sympatho-vagale Balance"],
                ["LF normiert", _f(fw.get("lf_norm")), _f(fwc.get("lf_norm")), "%", "40–70 · LF/(LF+HF) = Task Force"],
                ["HF normiert", _f(fw.get("hf_norm")), _f(fwc.get("hf_norm")), "%", "20–50 · HF/(LF+HF) = Task Force"],
                ["LF-Gipfel", _f(fw.get("lf_peak_freq"), ".3f"), _f(fwc.get("lf_peak_freq"), ".3f"), "Hz", "0,04–0,15 (Mayer-Wellen)"],
                ["HF-Gipfel", _f(fw.get("hf_peak_freq"), ".3f"), _f(fwc.get("hf_peak_freq"), ".3f"), "Hz", "0,15–0,40 (Atmung/RSA)"],
                ["Atemfrequenz (HF-Gipfel)", _f(fw.get("hf_resp_rate")), _f(fwc.get("hf_resp_rate")), "/min", "12–20 · Quervergleich zur EDR!"],
            ]})

    # ── EEG ───────────────────────────────────────────────────────────────────
    if em:
        ef = _eeg_metrics(edf, edf_path, None)
        ec = _eeg_metrics(edf, edf_path, corr_segments) if corr_segments else {}
        if ef:
            _add_eeg_sections(sections, ef, ec)

    # ── Validierte Zusatzverfahren (eigen vs. validiert) ──────────────────────
    _add_validated(sections, edf, edf_path, has_ecg, em)
    return sections


def _add_eeg_sections(sections, ef, ec):
    gc = ["Parameter", "Gesamt", "Korrigiert", "Einheit", "Norm / Deutung"]

    def pair(dfull, dcorr, key, sub=None, fmt=".1f"):
        gv = (dfull.get(key, {}).get(sub) if sub else dfull.get(key)) if dfull else None
        cv = (dcorr.get(key, {}).get(sub) if sub else dcorr.get(key)) if dcorr else None
        return _f(gv, fmt), _f(cv, fmt)

    rows = []
    for bn in _BN:
        g, c = pair(ef, ec, "rel_post", bn)
        rows.append([f"{bn} relativ", g, c, "%", "rel. Anteil (posterior O1/O2)"])
    for bn in _BN:
        g, c = pair(ef, ec, "abs_post", bn, ".2f")
        rows.append([f"{bn} absolut", g, c, "µV²", "posterior"])
    sections.append({"name": "EEG-Bandpower posterior O1/O2", "columns": gc, "rows": rows})

    if ef.get("rel_ant"):
        rows = []
        for bn in _BN:
            g, c = pair(ef, ec, "rel_ant", bn)
            note = "↑ Delta anterior oft EOG-Artefakt" if bn == "Delta" else "anterior"
            rows.append([f"{bn} relativ", g, c, "%", note])
        sections.append({"name": "EEG-Bandpower anterior F3/F4", "columns": gc, "rows": rows})

    sections.append({"name": "EEG — Alpha-Gipfel & A/P-Gradient", "columns": gc, "rows": [
        ["Alpha-Gipfel posterior", *pair(ef, ec, "ap_post", fmt=".2f"), "Hz", "8–13 (Norm 9–11)"],
        ["Alpha-Peak CoG posterior", *pair(ef, ec, "cog_post", fmt=".2f"), "Hz", "Schwerpunkt, robuster"],
        ["Alpha-Gipfel anterior", *pair(ef, ec, "ap_ant", fmt=".2f"), "Hz", "< posterior"],
        ["Post/Ant Alpha-Ratio", *pair(ef, ec, "ap_ratio", fmt=".2f"), "Ratio", "> 1 posterior-dominant"],
        ["Alpha-PAR (ganzer Kopf)", _f(ef.get("par"), ".2f"), "—", "—", "> 1 posterior-dominant (nur Gesamt)"],
        ["Exponent-Gradient post−ant", _f(ef.get("exp_grad"), "+.2f"), "—", "—", "+ = posterior steiler (nur Gesamt)"],
    ]})
    sections.append({"name": "EEG — klinische Frequenzratios (posterior)", "columns": gc, "rows": [
        ["Delta/Alpha (DAR)", *pair(ef, ec, "dar", fmt=".3f"), "Ratio", "0–1,5 · ↑ Verlangsamung"],
        ["Theta/Alpha (TAR)", *pair(ef, ec, "tar", fmt=".3f"), "Ratio", "0,2–0,7 · Frühmarker"],
        ["Alpha/Theta", *pair(ef, ec, "atr", fmt=".3f"), "Ratio", "1,5–6 · Vigilanz (↑ = wach)"],
        ["Theta/Beta (TBR)", *pair(ef, ec, "tbr", fmt=".3f"), "Ratio", "0,5–2 · Schläfrigkeit"],
        ["DTAB (D+T)/(A+B)", *pair(ef, ec, "dtab", fmt=".3f"), "Ratio", "< 0,5 · kort. Funktion"],
    ]})
    lzf = ef.get("lzc", {}); lzc = ec.get("lzc", {}) if ec else {}
    sections.append({"name": "EEG — Verlangsamung, Aperiodik (1/f) & Komplexität", "columns": gc, "rows": [
        ["SEF95", *pair(ef, ec, "sef95"), "Hz", "↓ = Verlangsamung"],
        ["Medianfrequenz (SEF50)", *pair(ef, ec, "medf"), "Hz", "↓ = Verlangsamung"],
        ["Aperiod. Exponent 1–20 Hz (eigen)", *pair(ef, ec, "exp_own", fmt=".2f"), "—", f"R²={_f(ef.get('r2_own'), '.2f')} · flach=aktiviert"],
        ["Alpha flattened", *pair(ef, ec, "flat_alpha", fmt=".2f"), "—", "> 0 = echter Gipfel"],
        ["Sample Entropy", *pair(ef, ec, "sampen", fmt=".2f"), "—", "↓ = regelmäßig"],
        ["Permutationsentropie", *pair(ef, ec, "permen", fmt=".2f"), "—", "Bandt-Pompe · ↓ = regelmäßig"],
        ["LZC (shuffle)", _f(lzf.get("shuffle"), ".2f"), _f(lzc.get("shuffle"), ".2f"), "—", "↑ = komplex"],
        ["LZC (phase)", _f(lzf.get("phase"), ".2f"), _f(lzc.get("phase"), ".2f"), "—", "> 1 = spektral-unabh."],
    ]})

    # Asymmetrie: Gesamt(abs) + Korrigiert(abs); relative Variante in Validiert-Sektion
    rows = []
    for lbl in ("O1/O2", "F3/F4"):
        for bn in _BN:
            gv = ef.get("ai", {}).get((lbl, bn, "abs"))
            cv = ec.get("ai", {}).get((lbl, bn, "abs")) if ec else None
            flag = " ⚠" if (gv == gv and abs(gv) > 20) else ""
            rows.append([f"AI {bn} ({lbl})", (f"{_f(gv, '.0f')}{flag}"), _f(cv, ".0f"), "%", "|AI| ≤ 20 normal (Nuwer)"])
    sections.append({"name": "EEG — Hemisphärische Asymmetrie (absolut)", "columns": gc, "rows": rows})


def _add_validated(sections, edf, edf_path, has_ecg, em):
    gc = ["Parameter", "Standard (eigen)", "Validiert", "Einheit", "Referenz / Hinweis"]
    rows = []
    # R-Zacken: eigen vs Hamilton (HRV-Zeit)
    if has_ecg:
        try:
            from views.report import _compute_hrv
            hf = _compute_hrv(edf_path, edf)
        except Exception:
            hf = None
        ham = _hrv_hamilton(edf)
        if hf and ham:
            rows += [
                ["SDNN (R-Zacken-Detektor)", _f(hf.get("sdnn")), _f(ham.get("sdnn_ms")), "ms", "Hamilton 2002 (py-ecg-detectors)"],
                ["RMSSD (R-Zacken-Detektor)", _f(hf.get("rmssd")), _f(ham.get("rmssd_ms")), "ms", "sensibel für Timing-Präzision"],
                ["pNN50 (R-Zacken-Detektor)", _f(hf.get("pnn50")), _f(ham.get("pnn50_pct")), "%", "Hamilton"],
            ]
        # DFA: eigen (nicht überlappend, nur α1) vs Standard-DFA (überlappend, α1+α2)
        try:
            from views.ecg_hrv import compute_rr as _crr
            from analysis.ecg import dfa_alpha12
            _rrm = _crr(edf_path, edf["ecg_channels"][0])["rr_ms"]
            a12 = dfa_alpha12(_rrm)
            if a12 and hf:
                rows += [
                    ["DFA α1", _f(hf.get("dfa_a1"), ".2f"), _f(a12["alpha1"], ".2f"), "—",
                     "eigen (nicht überlappend) vs Standard-DFA (überlappend)"],
                    ["DFA α2 (16–64 Schläge)", "—", _f(a12["alpha2"], ".2f"), "—",
                     "Langzeit-Steigung — nur im Standard-DFA (neu)"],
                ]
        except Exception:
            pass
        # HRV-Spektrum: Welch vs Lomb-Scargle
        try:
            from views.ecg_hrv import compute_rr
            from analysis.hrv_freq import compute_frequency_domain
            from analysis.hrv_lombscargle import lombscargle_hrv
            rr = compute_rr(edf_path, edf["ecg_channels"][0])
            w = compute_frequency_domain(rr["rr_ms"], rr["times"], method="welch")
            ls = lombscargle_hrv(rr["rr_ms"], rr["times"])
            if w and ls:
                rows += [
                    ["LF/HF-Ratio (HRV-Spektrum)", _f(w.get("lf_hf_ratio"), ".2f"), _f(ls.get("lf_hf_ratio"), ".2f"), "Ratio", "Lomb-Scargle: interpolationsfrei"],
                    ["LF normiert (HRV-Spektrum)", _f(w.get("lf_norm")), _f(ls.get("lf_norm")), "%", "Welch vs Lomb-Scargle"],
                    ["HF normiert (HRV-Spektrum)", _f(w.get("hf_norm")), _f(ls.get("hf_norm")), "%", "Welch vs Lomb-Scargle"],
                ]
        except Exception:
            pass
    # Aperiodik: eigen vs FOOOF; Alpha-Peak CoG vs FOOOF
    if em:
        try:
            from views.eeg_spectrum import _highpass, _peak_freq_cog
            from analysis.aperiodic import welch_psd, fit_aperiodic
            from analysis.aperiodic_fooof import fit_fooof
            sf, dur = edf["sfreq"], edf["duration_s"]
            ch = "O2" if "O2" in em else ("O1" if "O1" in em else list(em)[0])
            ana = min(dur, 300.0); t0 = max(0.0, (dur - ana) / 2)
            sig = _highpass(edf["data"][em[ch]] * 1e6, sf, 1.0)
            f, p = welch_psd(sig[int(t0 * sf):int((t0 + ana) * sf)], sf, fmax=45.0)
            own = fit_aperiodic(f, p, 1, 40)
            ff = fit_fooof(f, p, 1, 40, knee=False)
            if own and ff:
                rows += [
                    [f"Aperiod. Exponent 1–40 Hz ({ch})", _f(own["exponent"], ".2f"), _f(ff["exponent"], ".2f"), "—", f"FOOOF R²={_f(ff['r2'], '.2f')} vs eigen R²={_f(own['r2'], '.2f')}"],
                ]
                own_a = _peak_freq_cog(f, p, 8, 13)
                fa = [pk for pk in ff["peaks"] if 8 <= pk[0] <= 13]
                fa_v = max(fa, key=lambda x: x[1])[0] if fa else float("nan")
                rows += [[f"Alpha-Peak ({ch})", _f(own_a, ".2f"), _f(fa_v, ".2f"), "Hz", "eigen CoG (linear) vs FOOOF (aperiodik-bereinigt)"]]
        except Exception:
            pass
        # relative Asymmetrie (validiert gegen absolute)
        try:
            ef = _eeg_metrics(edf, edf_path, None)
            for lbl in ("O1/O2", "F3/F4"):
                for bn in _BN:
                    a_abs = ef.get("ai", {}).get((lbl, bn, "abs"))
                    a_rel = ef.get("ai", {}).get((lbl, bn, "rel"))
                    if a_abs is None or a_rel is None:
                        continue
                    rows.append([f"AI {bn} ({lbl})", _f(a_abs, ".0f"), _f(a_rel, ".0f"), "%", "absolut vs relativ (impedanz-robust)"])
        except Exception:
            pass
    if rows:
        sections.append({"name": "Validierte Zusatzverfahren (eigen vs. validiert)",
                         "columns": gc, "rows": rows})


# ──────────────────────────────────────────────────────────────────────────────
# Excel
# ──────────────────────────────────────────────────────────────────────────────
def build_excel(sections, edf, disp_name: str) -> bytes:
    import pandas as pd
    from openpyxl import Workbook
    from openpyxl.styles import Font
    wb = Workbook()
    ws = wb.active
    ws.title = "Report"
    ws.append([f"EDF-Analyzer — Gesamt-Report · {disp_name}"])
    ws["A1"].font = Font(bold=True, size=13)
    ws.append([])
    for sec in sections:
        r = ws.max_row + 1
        ws.cell(row=r, column=1, value=sec["name"]).font = Font(bold=True, color="1F4E79")
        ws.append(sec["columns"])
        for c in ws[ws.max_row]:
            c.font = Font(bold=True)
        for row in sec["rows"]:
            ws.append(list(row))
        ws.append([])
    for col in ws.columns:
        width = max((len(str(c.value)) for c in col if c.value is not None), default=10)
        ws.column_dimensions[col[0].column_letter].width = min(max(width + 2, 12), 52)

    # Kanäle + Ereignisse
    ch = wb.create_sheet("Kanäle")
    ch.append(["Nr", "Kanal", "Min", "Max", "RMS", "Einheit"])
    for i, name in enumerate(edf["ch_names"]):
        sig = edf["data"][i] - edf["data"][i].mean()
        unit = "µV" if name.startswith("EEG") else "mV"
        fac = 1e6 if name.startswith("EEG") else 1e3
        ch.append([i, name, round(float(sig.min() * fac), 1), round(float(sig.max() * fac), 1),
                   round(float(np.sqrt(np.mean(sig ** 2)) * fac), 1), unit])
    if edf.get("annotations"):
        ev = wb.create_sheet("Ereignisse")
        ev.append(["Zeit (s)", "Ereignis"])
        for a in edf["annotations"]:
            ev.append([round(a["onset_s"], 1), a["description"]])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ──────────────────────────────────────────────────────────────────────────────
# PDF (DejaVu-Font → volle Unicode-Unterstützung)
# ──────────────────────────────────────────────────────────────────────────────
def _register_font():
    try:
        import matplotlib
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        base = os.path.join(matplotlib.get_data_path(), "fonts", "ttf")
        pdfmetrics.registerFont(TTFont("RepSans", os.path.join(base, "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont("RepSans-Bold", os.path.join(base, "DejaVuSans-Bold.ttf")))
        return "RepSans", "RepSans-Bold"
    except Exception:
        return "Helvetica", "Helvetica-Bold"


def build_pdf(sections, disp_name: str) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

    font, font_b = _register_font()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=13 * mm, bottomMargin=12 * mm,
                            leftMargin=12 * mm, rightMargin=12 * mm, title="EDF-Report")
    styles = getSampleStyleSheet()
    title = ParagraphStyle("t", parent=styles["Title"], fontName=font_b)
    normal = ParagraphStyle("n", parent=styles["Normal"], fontName=font)
    h_sec = ParagraphStyle("sec", parent=styles["Heading4"], fontName=font_b, spaceBefore=7,
                           spaceAfter=2, textColor=colors.HexColor("#2471a3"))
    story = [Paragraph("EDF-Analyzer — Gesamt-Report", title),
             Paragraph(f"Datei: {disp_name}", normal), Spacer(1, 5)]
    # Spaltenbreiten je nach Spaltenzahl (4 oder 5)
    widths = {4: [60 * mm, 40 * mm, 22 * mm, 64 * mm],
              5: [56 * mm, 27 * mm, 27 * mm, 18 * mm, 58 * mm]}
    for sec in sections:
        cols = sec["columns"]
        story.append(Paragraph(sec["name"], h_sec))
        data = [cols] + [list(r) for r in sec["rows"]]
        tbl = Table(data, colWidths=widths.get(len(cols)), repeatRows=1)
        style = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef3fb")),
            ("FONTNAME", (0, 0), (-1, -1), font),
            ("FONTNAME", (0, 0), (-1, 0), font_b),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f9fc")]),
            ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.HexColor("#c4ccd6")),
            ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]
        if len(cols) == 5:
            style.append(("ALIGN", (1, 0), (3, -1), "RIGHT"))
        else:
            style.append(("ALIGN", (1, 0), (2, -1), "RIGHT"))
        tbl.setStyle(TableStyle(style))
        story.append(tbl)
    doc.build(story)
    return buf.getvalue()
