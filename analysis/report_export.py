"""Kompakter Gesamt-Report-Export (PDF + Excel).

Sammelt ALLE berechneten Parameter ultrakompakt und sortiert: Aufnahme, HRV (Zeit/vagal/
nichtlinear/Frequenz), EEG-Bandpower (post/ant), Alpha-Gipfel & A/P-Gradient, klinische Ratios,
spektrale Verlangsamung/Aperiodik/Komplexität, Asymmetrie-Indizes. Je Zeile: Wert · Einheit ·
kurze Norm/Hinweis. Kein Fließtext. Ausgabe als Excel (openpyxl) und PDF (reportlab).
"""

from __future__ import annotations

import io
import math

import numpy as np


def _f(v, fmt=".1f"):
    try:
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return "—"
        return format(float(v), fmt)
    except (TypeError, ValueError):
        return "—"


def _row(p, val, unit="", norm=""):
    return {"Parameter": p, "Wert": val, "Einheit": unit, "Norm / Hinweis": norm}


# ──────────────────────────────────────────────────────────────────────────────
# Parameter sammeln → [(Bereich, [rows])]
# ──────────────────────────────────────────────────────────────────────────────
def collect_sections(edf: dict, edf_path: str):
    sections = []
    sfreq = edf["sfreq"]
    dur_s = edf["duration_s"]
    eeg_map = edf.get("eeg_map", {})

    # ── Aufnahme ──────────────────────────────────────────────────────────────
    phi = "PHI im Header" if (edf.get("has_patient_id") or edf.get("has_rec_id")) else "anonymisiert"
    sections.append(("Aufnahme & Erkennung", [
        _row("Dauer", f"{dur_s/60:.1f}", "min", f"{int(dur_s)} s"),
        _row("Abtastrate", _f(sfreq, ".0f"), "Hz", ""),
        _row("Kanäle gesamt", str(len(edf["ch_names"])), "", ""),
        _row("EEG-Kanäle (10-20)", str(len(eeg_map)), "", ""),
        _row("EKG erkannt", "ja" if edf.get("ecg_channels") else "nein", "",
             (edf["ecg_channels"][0] if edf.get("ecg_channels") else "")),
        _row("Datenschutz", phi, "", ""),
    ]))

    # ── HRV ───────────────────────────────────────────────────────────────────
    if edf.get("ecg_channels"):
        try:
            from views.report import _compute_hrv
            hrv = _compute_hrv(edf_path, edf)
        except Exception:
            hrv = None
        if hrv:
            sections.append(("HRV — Zeitbereich", [
                _row("Herzfrequenz", _f(hrv["mean_hr"]), "bpm", "60–100"),
                _row("Mittleres RR", _f(hrv["mean_rr"], ".0f"), "ms", "600–1000"),
                _row("SDNN", _f(hrv["sdnn"]), "ms", "37 (IQR 27–54)"),
                _row("CV", _f(hrv["cv"]), "%", "HF-unabhängig"),
            ]))
            sections.append(("HRV — vagale Marker", [
                _row("RMSSD", _f(hrv["rmssd"]), "ms", "27 (IQR 17–44)"),
                _row("pNN50", _f(hrv["pnn50"]), "%", "~12 (5–28)"),
                _row("pNN20", _f(hrv["pnn20"]), "%", "sensitiver als pNN50"),
                _row("NN50", _f(hrv["nn50"], ".0f"), "Anzahl", "längenabhängig"),
            ]))
            sections.append(("HRV — nichtlinear & Atmung", [
                _row("SD1", _f(hrv["sd1"]), "ms", "kurzfristig/vagal"),
                _row("SD2", _f(hrv["sd2"]), "ms", "langfristig"),
                _row("SD2/SD1", _f(hrv["sd2_sd1"], ".2f"), "Ratio", "Balance"),
                _row("DFA α₁", _f(hrv["dfa_a1"], ".2f"), "—", "~1,0 gesund (0,75–1,25)"),
                _row("Sample Entropy", _f(hrv["samp_en"], ".2f"), "—", "↓ = regelmäßig"),
                _row("Atemfrequenz (EDR)", _f(hrv["edr_rate"]), "/min", "12–20"),
                _row("Artefaktrate RR", _f(hrv["pct_removed"]), "%", "< 5 % gut"),
            ]))
            fd = hrv.get("fd_welch")
            if fd:
                sections.append(("HRV — Frequenzbereich (Welch)", [
                    _row("Total Power", _f(fd.get("total_power"), ".0f"), "ms²", "235–1033"),
                    _row("LF-Leistung", _f(fd.get("lf_power"), ".0f"), "ms²", "67–368"),
                    _row("HF-Leistung", _f(fd.get("hf_power"), ".0f"), "ms²", "38–263"),
                    _row("LF/HF-Ratio", _f(fd.get("lf_hf_ratio"), ".2f"), "Ratio", "0,5–5,0"),
                    _row("LF normiert", _f(fd.get("lf_norm")), "%", "40–70"),
                    _row("HF normiert", _f(fd.get("hf_norm")), "%", "20–50"),
                    _row("LF-Gipfel", _f(fd.get("lf_peak_freq"), ".3f"), "Hz", "0,04–0,15"),
                    _row("HF-Gipfel", _f(fd.get("hf_peak_freq"), ".3f"), "Hz", "0,15–0,40"),
                ]))

    # ── EEG-Spektrum ──────────────────────────────────────────────────────────
    if eeg_map:
        _collect_eeg(sections, edf, edf_path, sfreq, dur_s, eeg_map)

    return sections


def _collect_eeg(sections, edf, edf_path, sfreq, dur_s, eeg_map):
    from views.report import _compute_bandpower

    def _get(ch):
        return edf["data"][eeg_map[ch]] * 1e6 if ch in eeg_map else None

    o1, o2, f3, f4 = _get("O1"), _get("O2"), _get("F3"), _get("F4")
    sig_post = (o1 + o2) / 2 if o1 is not None and o2 is not None else (o1 if o1 is not None else o2)
    sig_ant = (f3 + f4) / 2 if f3 is not None and f4 is not None else (f3 if f3 is not None else f4)
    if sig_post is None:
        return
    ana = min(dur_s, 300.0)
    t0 = max(0.0, (dur_s - ana) / 2)
    t1 = t0 + ana

    bp_p, freqs_p, psd_p, ap_post = _compute_bandpower(sig_post, sfreq, t0, t1)
    if not bp_p:
        return
    res_a = _compute_bandpower(sig_ant, sfreq, t0, t1) if sig_ant is not None else (None,)
    bp_a = res_a[0] if res_a and res_a[0] else {}
    ap_ant = res_a[3] if res_a and res_a[0] else float("nan")
    tp = sum(bp_p.values()) or 1
    ta = sum(bp_a.values()) or 1
    BK = ["Delta (1–4 Hz)", "Theta (4–8 Hz)", "Alpha (8–13 Hz)", "Beta (13–30 Hz)"]
    BN = ["Delta", "Theta", "Alpha", "Beta"]

    sections.append((f"EEG-Bandpower posterior O1/O2 · {int(t0)}–{int(t1)} s", [
        _row(f"{bn} relativ", _f(bp_p.get(bk, 0) / tp * 100), "%", "rel. Anteil")
        for bk, bn in zip(BK, BN)
    ]))
    if bp_a:
        sections.append(("EEG-Bandpower anterior F3/F4", [
            _row(f"{bn} relativ", _f(bp_a.get(bk, 0) / ta * 100), "%", "rel. Anteil")
            for bk, bn in zip(BK, BN)
        ]))

    ap_ratio = bp_p.get("Alpha (8–13 Hz)", 0) / (bp_a.get("Alpha (8–13 Hz)", 0) or 1e-9) if bp_a else float("nan")
    grad = [
        _row("Alpha-Gipfel posterior", _f(ap_post, ".2f"), "Hz", "8–13 (Norm 9–11)"),
        _row("Alpha-Gipfel anterior", _f(ap_ant, ".2f"), "Hz", "< posterior"),
        _row("Post/Ant Alpha-Ratio", _f(ap_ratio, ".2f"), "Ratio", "> 1 posterior-dominant"),
    ]
    # A/P-Gradient (ganzer Kopf, PAR)
    try:
        from views.eeg_spectrum import _compute_par
        par = _compute_par(edf_path, t0, t1, 8.0, 13.0, False, 9999.0)
        if par["n_post"] >= 2 and par["n_ant"] >= 2:
            grad.append(_row("Alpha-PAR (ganzer Kopf)", _f(par["par"], ".2f"), "—", "> 1 posterior-dominant"))
            grad.append(_row("Exponent-Gradient post−ant", _f(par["exp_grad"], "+.2f"), "—",
                             f"{par['n_post']} post / {par['n_ant']} ant"))
    except Exception:
        pass
    sections.append(("EEG — Alpha-Gipfel & A/P-Gradient", grad))

    # Klinische Ratios
    d = bp_p.get("Delta (1–4 Hz)", 0); t = bp_p.get("Theta (4–8 Hz)", 0)
    a = bp_p.get("Alpha (8–13 Hz)", 0) or 1e-9; b = bp_p.get("Beta (13–30 Hz)", 0) or 1e-9
    sections.append(("EEG — klinische Frequenzratios (posterior)", [
        _row("Delta/Alpha (DAR)", _f(d / a, ".3f"), "Ratio", "0–1,5 · ↑ Verlangsamung"),
        _row("Theta/Alpha (TAR)", _f(t / a, ".3f"), "Ratio", "0,2–0,7 · Frühmarker"),
        _row("Alpha/Theta", _f(a / (t or 1e-9), ".3f"), "Ratio", "1,5–6 · Vigilanz"),
        _row("Theta/Beta (TBR)", _f(t / b, ".3f"), "Ratio", "0,5–2 · Schläfrigkeit"),
        _row("DTAB (D+T)/(A+B)", _f((d + t) / (a + b), ".3f"), "Ratio", "< 0,5 · kort. Funktion"),
    ]))

    # Verlangsamung / Aperiodik / Komplexität
    if freqs_p is not None and len(freqs_p) > 2:
        try:
            from views.eeg_spectrum import _spectral_edge
            from analysis.aperiodic import fit_aperiodic, band_power_defs
            from analysis.complexity import sample_entropy, lziv_complexity
            sef95 = _spectral_edge(freqs_p, psd_p, 0.95)
            medf = _spectral_edge(freqs_p, psd_p, 0.50)
            rap = fit_aperiodic(freqs_p, psd_p, 1, 20)
            exp20 = rap["exponent"] if rap else float("nan")
            r2 = rap["r2"] if rap else float("nan")
            flat_a = band_power_defs(freqs_p, psd_p, 8, 13, res=rap)["flattened"]
            seg = sig_post[int(t0 * sfreq):int(t1 * sfreq)]
            sampen = sample_entropy(seg, max_n=4000) if len(seg) >= 100 else float("nan")
            lzc = lziv_complexity(seg, sfreq) if len(seg) >= int(5 * sfreq) else {"shuffle": float("nan"), "phase": float("nan")}
            sections.append(("EEG — Verlangsamung, Aperiodik (1/f) & Komplexität", [
                _row("SEF95", _f(sef95), "Hz", "↓ = Verlangsamung"),
                _row("Medianfrequenz (SEF50)", _f(medf), "Hz", "↓ = Verlangsamung"),
                _row("Aperiod. Exponent 1–20 Hz", _f(exp20, ".2f"), "—", f"R²={_f(r2, '.2f')} · flach=aktiviert"),
                _row("Alpha flattened", _f(flat_a, ".2f"), "—", "> 0 = echter Gipfel"),
                _row("Sample Entropy", _f(sampen, ".2f"), "—", "↓ = regelmäßig"),
                _row("LZC (shuffle)", _f(lzc.get("shuffle"), ".2f"), "—", "↑ = komplex"),
                _row("LZC (phase)", _f(lzc.get("phase"), ".2f"), "—", "> 1 = spektral-unabh."),
            ]))
        except Exception:
            pass

    # Asymmetrie-Indizes (AI = (L−R)/(L+R)×100)
    def _ai(l, r):
        s = l + r
        return (l - r) / s * 100 if s > 1e-9 else float("nan")

    asym = []
    for pair_label, lch, rch in [("okzipital O1/O2", "O1", "O2"), ("frontal F3/F4", "F3", "F4")]:
        sl, sr = _get(lch), _get(rch)
        if sl is None or sr is None:
            continue
        bl = _compute_bandpower(sl, sfreq, t0, t1)[0]
        br = _compute_bandpower(sr, sfreq, t0, t1)[0]
        if not bl or not br:
            continue
        for bk, bn in zip(BK, BN):
            asym.append(_row(f"AI {bn} ({pair_label})", _f(_ai(bl.get(bk, 0), br.get(bk, 0)), "+.0f"),
                             "%", "|AI| ≤ 20 normal (Nuwer)"))
    if asym:
        sections.append(("EEG — Hemisphärische Asymmetrie", asym))


# ──────────────────────────────────────────────────────────────────────────────
# Excel
# ──────────────────────────────────────────────────────────────────────────────
def build_excel(sections, edf, disp_name: str) -> bytes:
    import pandas as pd
    buf = io.BytesIO()
    flat = []
    for name, rows in sections:
        for r in rows:
            flat.append({"Bereich": name, **r})
    df = pd.DataFrame(flat, columns=["Bereich", "Parameter", "Wert", "Einheit", "Norm / Hinweis"])

    ch_rows = []
    for i, ch in enumerate(edf["ch_names"]):
        sig = edf["data"][i]; sig = sig - sig.mean()
        unit = "µV" if ch.startswith("EEG") else "mV"
        fac = 1e6 if ch.startswith("EEG") else 1e3
        ch_rows.append({"Nr": i, "Kanal": ch, f"Min ({unit})": round(float(sig.min() * fac), 1),
                        f"Max ({unit})": round(float(sig.max() * fac), 1),
                        f"RMS ({unit})": round(float(np.sqrt(np.mean(sig ** 2)) * fac), 1)})
    ann = [{"Zeit (s)": round(a["onset_s"], 1), "Ereignis": a["description"]}
           for a in edf.get("annotations", [])]

    with pd.ExcelWriter(buf, engine="openpyxl") as xl:
        df.to_excel(xl, sheet_name="Parameter", index=False)
        pd.DataFrame(ch_rows).to_excel(xl, sheet_name="Kanäle", index=False)
        if ann:
            pd.DataFrame(ann).to_excel(xl, sheet_name="Ereignisse", index=False)
        for ws in xl.book.worksheets:
            for col in ws.columns:
                width = max((len(str(c.value)) for c in col if c.value is not None), default=8)
                ws.column_dimensions[col[0].column_letter].width = min(max(width + 2, 10), 48)
    return buf.getvalue()


# ──────────────────────────────────────────────────────────────────────────────
# PDF
# ──────────────────────────────────────────────────────────────────────────────
def build_pdf(sections, disp_name: str) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=14 * mm, bottomMargin=12 * mm,
                            leftMargin=14 * mm, rightMargin=14 * mm, title="EDF-Report")
    styles = getSampleStyleSheet()
    h_sec = ParagraphStyle("sec", parent=styles["Heading4"], spaceBefore=8, spaceAfter=3,
                           textColor=colors.HexColor("#2471a3"))
    story = [Paragraph("EDF-Analyzer — Gesamt-Report", styles["Title"]),
             Paragraph(f"Datei: {disp_name}", styles["Normal"]), Spacer(1, 6)]
    header = ["Parameter", "Wert", "Einheit", "Norm / Hinweis"]
    col_w = [58 * mm, 24 * mm, 20 * mm, 78 * mm]
    for name, rows in sections:
        story.append(Paragraph(name, h_sec))
        data = [header] + [[r["Parameter"], r["Wert"], r["Einheit"], r["Norm / Hinweis"]] for r in rows]
        tbl = Table(data, colWidths=col_w, repeatRows=1)
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef3fb")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#333333")),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ALIGN", (1, 0), (2, -1), "RIGHT"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f9fc")]),
            ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.HexColor("#c4ccd6")),
            ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        story.append(tbl)
    doc.build(story)
    return buf.getvalue()
