"""PDF-Befundbericht für die HRV-Analyse — klinisch-tabellarisches Layout, keine Grafiken."""

import io
from datetime import datetime
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, KeepTogether,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

# ── Farben (dezent, klinisch) ─────────────────────────────────────────────────
_C_HEADER   = colors.HexColor("#1c2833")
_C_SUBHEAD  = colors.HexColor("#2c3e50")
_C_LABEL    = colors.HexColor("#444444")
_C_VALUE    = colors.HexColor("#111111")
_C_MUTED    = colors.HexColor("#888888")
_C_RULE     = colors.HexColor("#cccccc")
_C_ROW_ALT  = colors.HexColor("#f7f8f9")
_C_NORMAL   = colors.HexColor("#1e7e34")
_C_BORDER   = colors.HexColor("#aab6be")
_C_WARN     = colors.HexColor("#856404")
_C_PATHO    = colors.HexColor("#842029")

_ZONE_COLOR = {
    "normal":        _C_NORMAL,
    "grenzwertig":   _C_WARN,
    "pathologisch":  _C_PATHO,
    "info":          _C_MUTED,
}


def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("ReportTitle",
        parent=ss["Heading1"], alignment=TA_CENTER,
        fontSize=15, textColor=_C_HEADER, spaceAfter=2))
    ss.add(ParagraphStyle("SectionHead",
        parent=ss["Heading2"],
        fontSize=10, textColor=_C_SUBHEAD,
        fontName="Helvetica-Bold",
        spaceBefore=10, spaceAfter=3))
    ss.add(ParagraphStyle("Body10",
        parent=ss["Normal"], fontSize=10, textColor=_C_VALUE, leading=14))
    ss.add(ParagraphStyle("Small8",
        parent=ss["Normal"], fontSize=8, textColor=_C_MUTED, leading=11))
    ss.add(ParagraphStyle("Cell9",
        parent=ss["Normal"], fontSize=9, textColor=_C_VALUE, leading=12))
    ss.add(ParagraphStyle("CellBold",
        parent=ss["Normal"], fontSize=9, fontName="Helvetica-Bold",
        textColor=_C_LABEL, leading=12))
    ss.add(ParagraphStyle("CellRight",
        parent=ss["Normal"], fontSize=9, textColor=_C_VALUE, leading=12,
        alignment=TA_RIGHT))
    return ss


def _rule():
    return HRFlowable(width="100%", color=_C_RULE, thickness=0.6)


def _section_table_style():
    return TableStyle([
        ("FONTNAME",    (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME",    (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0), (-1, -1), 9),
        ("TEXTCOLOR",   (0, 0), (-1, 0), _C_SUBHEAD),
        ("BACKGROUND",  (0, 0), (-1, 0), colors.HexColor("#eaecee")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _C_ROW_ALT]),
        ("GRID",        (0, 0), (-1, -1), 0.4, _C_RULE),
        ("LEFTPADDING",  (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING",   (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
    ])


def _nan_str(val, fmt=".1f", fallback="—"):
    try:
        if val != val:
            return fallback
        return format(float(val), fmt)
    except (TypeError, ValueError):
        return fallback


def build_hrv_pdf(
    *,
    patient_age: int,
    patient_sex: str,
    file_label: str,
    duration_min: float,
    mean_hr: float,
    sdnn: float,
    rmssd: float,
    pnn50: float,
    pct_removed: float,
    quality_label: str,
    balance_label: str,
    lab_rows: list,
    method_used: str,
    fd_welch: Optional[dict] = None,
    fd_burg: Optional[dict] = None,
) -> bytes:
    """Baut den klinischen Tabellen-Report (kein Grafik-Export, nur Werte)."""
    ss = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=14 * mm, bottomMargin=14 * mm,
        leftMargin=16 * mm, rightMargin=16 * mm,
    )
    el = []

    # ── Kopfzeile ─────────────────────────────────────────────────────────────
    el.append(Paragraph("Herzratenvariabilität — Befundbericht", ss["ReportTitle"]))
    el.append(Spacer(1, 3))
    el.append(_rule())
    el.append(Spacer(1, 4))

    sex_label = {"M": "männlich", "F": "weiblich", "X": "—"}.get(patient_sex, "—")
    meta = Table([
        [Paragraph("Datei", ss["CellBold"]),
         Paragraph(file_label, ss["Cell9"]),
         Paragraph("Aufnahmedauer", ss["CellBold"]),
         Paragraph(f"{duration_min:.1f} min", ss["Cell9"])],
        [Paragraph("Patientenalter", ss["CellBold"]),
         Paragraph(f"{patient_age} Jahre", ss["Cell9"]),
         Paragraph("Geschlecht", ss["CellBold"]),
         Paragraph(sex_label, ss["Cell9"])],
        [Paragraph("Erstellt", ss["CellBold"]),
         Paragraph(datetime.now().strftime("%d.%m.%Y  %H:%M"), ss["Cell9"]),
         Paragraph("Spektralmethode", ss["CellBold"]),
         Paragraph(method_used, ss["Cell9"])],
    ], colWidths=[30*mm, 60*mm, 35*mm, 45*mm])
    meta.setStyle(TableStyle([
        ("FONTSIZE",     (0, 0), (-1, -1), 9),
        ("GRID",         (0, 0), (-1, -1), 0.3, _C_RULE),
        ("TOPPADDING",   (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 3),
        ("LEFTPADDING",  (0, 0), (-1, -1), 5),
    ]))
    el.append(meta)
    el.append(Spacer(1, 6))

    # ── Datenqualität ─────────────────────────────────────────────────────────
    el.append(_rule())
    el.append(Spacer(1, 3))
    qc = _C_NORMAL if pct_removed < 5 else (_C_WARN if pct_removed < 15 else _C_PATHO)
    qline = Table([[
        Paragraph("Datenqualität", ss["CellBold"]),
        Paragraph(f"{pct_removed:.1f}% Artefakte entfernt", ss["Cell9"]),
        Paragraph(quality_label, ParagraphStyle("Q", parent=ss["Cell9"], textColor=qc)),
    ]], colWidths=[32*mm, 44*mm, 94*mm])
    qline.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.3, _C_RULE),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
    ]))
    el.append(qline)
    el.append(Spacer(1, 8))

    # ── Zeitbereich ───────────────────────────────────────────────────────────
    el.append(Paragraph("1  Zeitbereich (Time Domain)", ss["SectionHead"]))
    td_rows = [
        [Paragraph("Parameter", ss["CellBold"]),
         Paragraph("Wert", ss["CellBold"]),
         Paragraph("Einheit", ss["CellBold"]),
         Paragraph("Populationsmedian (IQR)", ss["CellBold"]),
         Paragraph("Bedeutung", ss["CellBold"])],
        [Paragraph("Herzfrequenz (HR)", ss["Cell9"]),
         Paragraph(f"{mean_hr:.1f}", ss["Cell9"]),
         Paragraph("bpm", ss["Cell9"]),
         Paragraph("67  (61–74)", ss["Cell9"]),
         Paragraph("Mittlere Herzrate", ss["Cell9"])],
        [Paragraph("SDNN", ss["Cell9"]),
         Paragraph(f"{sdnn:.1f}", ss["Cell9"]),
         Paragraph("ms", ss["Cell9"]),
         Paragraph("37  (27–54)", ss["Cell9"]),
         Paragraph("Globale ANS-Variabilität", ss["Cell9"])],
        [Paragraph("RMSSD", ss["Cell9"]),
         Paragraph(f"{rmssd:.1f}", ss["Cell9"]),
         Paragraph("ms", ss["Cell9"]),
         Paragraph("27  (17–44)", ss["Cell9"]),
         Paragraph("Vagaler / parasympathischer Marker", ss["Cell9"])],
        [Paragraph("pNN50", ss["Cell9"]),
         Paragraph(f"{pnn50:.1f}", ss["Cell9"]),
         Paragraph("%", ss["Cell9"]),
         Paragraph("—", ss["Cell9"]),
         Paragraph("Vagaler Marker (korreliert mit RMSSD)", ss["Cell9"])],
    ]
    td_table = Table(td_rows, colWidths=[38*mm, 18*mm, 16*mm, 38*mm, 60*mm])
    td_table.setStyle(_section_table_style())
    el.append(td_table)
    el.append(Spacer(1, 8))

    # ── Frequenzbereich ───────────────────────────────────────────────────────
    for fd_label, fd in [("Welch (FFT)", fd_welch), ("Burg (MEM)", fd_burg)]:
        if not fd:
            continue
        el.append(Paragraph(
            f"2  Frequenzbereich (Frequency Domain) — {fd_label}", ss["SectionHead"]))

        def _fv(key, fmt=".1f"):
            return _nan_str(fd.get(key), fmt)

        lf_hf = fd.get("lf_hf_ratio", float("nan"))
        lf_norm = fd.get("lf_norm", float("nan"))
        hf_norm = fd.get("hf_norm", float("nan"))
        resp = fd.get("hf_resp_rate", float("nan"))

        fd_rows = [
            [Paragraph("Parameter", ss["CellBold"]),
             Paragraph("Wert", ss["CellBold"]),
             Paragraph("Einheit", ss["CellBold"]),
             Paragraph("Referenzbereich", ss["CellBold"]),
             Paragraph("Bedeutung", ss["CellBold"])],
            [Paragraph("Total Power", ss["Cell9"]),
             Paragraph(_fv("total_power", ".0f"), ss["Cell9"]),
             Paragraph("ms²", ss["Cell9"]),
             Paragraph("≥ 235  (Median 486)", ss["Cell9"]),
             Paragraph("Gesamtvariabilität", ss["Cell9"])],
            [Paragraph("LF-Leistung", ss["Cell9"]),
             Paragraph(_fv("lf_power", ".0f"), ss["Cell9"]),
             Paragraph("ms²", ss["Cell9"]),
             Paragraph("67–368  (Median 152)", ss["Cell9"]),
             Paragraph("Baroreflex / gemischt", ss["Cell9"])],
            [Paragraph("HF-Leistung", ss["Cell9"]),
             Paragraph(_fv("hf_power", ".0f"), ss["Cell9"]),
             Paragraph("ms²", ss["Cell9"]),
             Paragraph("38–263  (Median 100)", ss["Cell9"]),
             Paragraph("Vagal / respiratorisch", ss["Cell9"])],
            [Paragraph("LF/HF-Ratio", ss["Cell9"]),
             Paragraph(_nan_str(lf_hf, ".2f"), ss["Cell9"]),
             Paragraph("—", ss["Cell9"]),
             Paragraph("0.5–5.0  (Median 2.8)", ss["Cell9"]),
             Paragraph("Sympathovagale Balance", ss["Cell9"])],
            [Paragraph("LF normiert", ss["Cell9"]),
             Paragraph(_nan_str(lf_norm, ".1f"), ss["Cell9"]),
             Paragraph("%", ss["Cell9"]),
             Paragraph("40–70 %", ss["Cell9"]),
             Paragraph("LF-Anteil (ohne VLF)", ss["Cell9"])],
            [Paragraph("HF normiert", ss["Cell9"]),
             Paragraph(_nan_str(hf_norm, ".1f"), ss["Cell9"]),
             Paragraph("%", ss["Cell9"]),
             Paragraph("20–50 %", ss["Cell9"]),
             Paragraph("HF-Anteil (ohne VLF) — vagal", ss["Cell9"])],
            [Paragraph("LF-Gipfelfrequenz", ss["Cell9"]),
             Paragraph(_fv("lf_peak_freq", ".3f"), ss["Cell9"]),
             Paragraph("Hz", ss["Cell9"]),
             Paragraph("0.04–0.15 Hz", ss["Cell9"]),
             Paragraph("Mayer-Wellen / Baroreflex", ss["Cell9"])],
            [Paragraph("HF-Gipfelfrequenz", ss["Cell9"]),
             Paragraph(_fv("hf_peak_freq", ".3f"), ss["Cell9"]),
             Paragraph("Hz", ss["Cell9"]),
             Paragraph("0.15–0.40 Hz", ss["Cell9"]),
             Paragraph("Respiratorische SA", ss["Cell9"])],
            [Paragraph("Atemfrequenz (RSA)", ss["Cell9"]),
             Paragraph(_nan_str(resp, ".0f"), ss["Cell9"]),
             Paragraph("/min", ss["Cell9"]),
             Paragraph("12–20 /min", ss["Cell9"]),
             Paragraph("Aus HF-Gipfelfrequenz × 60", ss["Cell9"])],
        ]
        fd_table = Table(fd_rows, colWidths=[34*mm, 18*mm, 14*mm, 44*mm, 60*mm])
        fd_table.setStyle(_section_table_style())
        el.append(KeepTogether(fd_table))
        el.append(Spacer(1, 8))

    # ── ANS-Übersicht ─────────────────────────────────────────────────────────
    el.append(Paragraph("3  Autonomes Nervensystem — Gesamttendenz", ss["SectionHead"]))
    ans_table = Table([[
        Paragraph("ANS-Tendenz", ss["CellBold"]),
        Paragraph(balance_label, ss["Cell9"]),
        Paragraph("Aus RMSSD, pNN50, HF-Power, LF/HF, HR", ss["Small8"]),
    ]], colWidths=[32*mm, 50*mm, 88*mm])
    ans_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.3, _C_RULE),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    el.append(ans_table)
    el.append(Spacer(1, 8))

    # ── Normwertvergleich (aus lab_rows) ──────────────────────────────────────
    if lab_rows:
        el.append(Paragraph("4  Normwertvergleich — Einzelparameter", ss["SectionHead"]))
        nv_header = [
            Paragraph("Parameter", ss["CellBold"]),
            Paragraph("Messwert", ss["CellBold"]),
            Paragraph("Einheit", ss["CellBold"]),
            Paragraph("Normgrenze (P5)", ss["CellBold"]),
            Paragraph("Zone", ss["CellBold"]),
            Paragraph("Befund", ss["CellBold"]),
        ]
        nv_data = [nv_header]
        for r in lab_rows:
            zone_col = _ZONE_COLOR.get(r.get("zone", "info"), _C_MUTED)
            zone_style = ParagraphStyle("ZS", parent=ss["Cell9"], textColor=zone_col,
                                        fontName="Helvetica-Bold")
            p5_str = f"{r['p5']:.1f}" if r.get("p5") is not None else "—"
            nv_data.append([
                Paragraph(r.get("label", ""), ss["Cell9"]),
                Paragraph(f"{r['value']:.1f}", ss["Cell9"]),
                Paragraph(r.get("unit", ""), ss["Cell9"]),
                Paragraph(p5_str, ss["Cell9"]),
                Paragraph(r.get("zone", "—"), zone_style),
                Paragraph(r.get("severity", "—"), ss["Cell9"]),
            ])
        nv_table = Table(nv_data, colWidths=[38*mm, 18*mm, 14*mm, 28*mm, 24*mm, 48*mm])
        nv_table.setStyle(_section_table_style())
        el.append(KeepTogether(nv_table))
        el.append(Spacer(1, 8))

    # ── Methodische Hinweise ──────────────────────────────────────────────────
    el.append(_rule())
    el.append(Spacer(1, 3))
    el.append(Paragraph(
        "Normwerte und Referenzbereiche: Hansen CS et al. (2024) Clin Auton Res 35:101–113 "
        "(alters- und herzraten-adjustiertes log-lineares Modell); Task Force ESC/NASPE (1996) "
        "Circulation 93:1043–1065 (Frequenzbereich); Billman GE (2013) Front Physiol 4:26 "
        "(LF/HF-Ratio); Gąsior JS et al. (2018) Front Physiol (Pädiatrie). "
        "Referenzbereiche beziehen sich auf standardisierte 5-Minuten-Ruhemessungen — "
        "Routine-EEG-Ableitungen sind nicht äquivalent. Werte sind als Orientierung zu verstehen. "
        "Alle Berechnungen lokal — keine Datenübertragung.",
        ss["Small8"],
    ))

    doc.build(el)
    return buf.getvalue()
