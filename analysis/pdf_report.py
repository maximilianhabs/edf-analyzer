"""PDF-Befundbericht für die HRV-Analyse — Layout/Farben analog zur Web-Ansicht."""

import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, HRFlowable,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER

ZONE_COLOR_HEX = {"pathologisch": "#c0392b", "grenzwertig": "#f39c12",
                  "normal": "#27ae60", "info": "#95a5a6"}
MARKER_TEXT_COLOR = {"para": "#3d7ea6", "symp": "#c0695f", "mixed": "#7a6a96",
                     "global": "#7a6a96", "none": "#888888"}


def _styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("H1c", parent=ss["Heading1"], alignment=TA_CENTER, fontSize=18))
    ss.add(ParagraphStyle("H2", parent=ss["Heading2"], fontSize=13, spaceBefore=10, spaceAfter=4))
    ss.add(ParagraphStyle("Small", parent=ss["Normal"], fontSize=8.5, textColor=colors.HexColor("#666666")))
    ss.add(ParagraphStyle("Body", parent=ss["Normal"], fontSize=10))
    return ss


def fig_to_image_flowable(fig, width_mm=160):
    """Plotly-Figure → ReportLab Image-Flowable via PNG-Export (kaleido)."""
    png_bytes = fig.to_image(format="png", scale=2.2)
    buf = io.BytesIO(png_bytes)
    # Seitenverhältnis aus der Originalgröße ableiten
    fig_w = fig.layout.width or 700
    fig_h = fig.layout.height or 400
    ratio = fig_h / fig_w
    w = width_mm * mm
    h = w * ratio
    return Image(buf, width=w, height=h)


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
    balance_index: float,
    lab_rows: list,        # je: dict(label, value, unit, zone, severity, direction, marker_type, p5)
    method_used: str,
    fig_tachogram,
    fig_poincare,
    fig_psd_welch,
    fig_psd_burg,
    fig_balance_gauge,
) -> bytes:
    """Baut den vollständigen PDF-Report und gibt die Bytes zurück."""
    ss = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=16 * mm, bottomMargin=14 * mm, leftMargin=16 * mm, rightMargin=16 * mm,
    )
    el = []

    # ── Kopf ──────────────────────────────────────────────────────────────
    el.append(Paragraph("HRV-Befundbericht", ss["H1c"]))
    el.append(Spacer(1, 4))
    meta_table = Table([
        ["Datei", file_label, "Aufnahmedauer", f"{duration_min:.1f} min"],
        ["Patientenalter", f"{patient_age} Jahre", "Geschlecht", patient_sex],
        ["Erstellt am", datetime.now().strftime("%d.%m.%Y %H:%M"), "Spektralmethode", method_used],
    ], colWidths=[28*mm, 50*mm, 32*mm, 50*mm])
    meta_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#555555")),
        ("TEXTCOLOR", (2, 0), (2, -1), colors.HexColor("#555555")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
    ]))
    el.append(meta_table)
    el.append(Spacer(1, 6))
    el.append(HRFlowable(width="100%", color=colors.HexColor("#dddddd"), thickness=0.75))

    # ── Datenqualität ─────────────────────────────────────────────────────
    el.append(Paragraph("Datenqualität", ss["H2"]))
    qcolor = "#27ae60" if pct_removed < 5 else ("#f39c12" if pct_removed < 15 else "#c0392b")
    el.append(Paragraph(
        f"<font color='{qcolor}'><b>{pct_removed:.1f}% der Schläge entfernt</b></font> — {quality_label}",
        ss["Body"],
    ))
    el.append(Spacer(1, 8))

    # ── Tachogramm + Poincaré ────────────────────────────────────────────
    el.append(Paragraph("RR-Analyse — bereinigte Daten (Ausreißer entfernt)", ss["H2"]))
    img_tacho = fig_to_image_flowable(fig_tachogram, width_mm=170)
    el.append(img_tacho)
    el.append(Spacer(1, 4))
    img_poin = fig_to_image_flowable(fig_poincare, width_mm=120)
    el.append(img_poin)
    el.append(Spacer(1, 8))

    # ── Frequenzdomäne ───────────────────────────────────────────────────
    el.append(Paragraph("Frequenzdomäne — Welch (FFT) und Burg (Maximum Entropy Method)", ss["H2"]))
    img_w = fig_to_image_flowable(fig_psd_welch, width_mm=80)
    img_b = fig_to_image_flowable(fig_psd_burg, width_mm=80)
    psd_table = Table([[img_w, img_b]], colWidths=[85*mm, 85*mm])
    psd_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    el.append(psd_table)
    el.append(Spacer(1, 8))

    # ── HRV-Befund: Balance-Gauge ────────────────────────────────────────
    el.append(Paragraph("HRV-Befund — autonome Tendenz", ss["H2"]))
    img_bal = fig_to_image_flowable(fig_balance_gauge, width_mm=150)
    el.append(img_bal)
    el.append(Paragraph(
        f"<b>Autonome Tendenz: {balance_label}</b> (Index {balance_index:+.0f})",
        ParagraphStyle("BalLabel", parent=ss["Body"], alignment=TA_CENTER, fontSize=11),
    ))
    el.append(Paragraph(
        "Heuristischer Gesamtindex aus RMSSD, HF-Power und LF/HF-Ratio — kein etabliertes "
        "klinisches Maß, sondern orientierende Verdichtung vorhandener (teils umstrittener) Marker.",
        ss["Small"],
    ))
    el.append(Spacer(1, 8))

    # ── Parameter-Zeilen im Laborwert-Stil (Balkengrafik mit Rot/Gelb/Grün-Zonen) ──
    el.append(Paragraph("HRV-Parameter im Normwertvergleich", ss["H2"]))
    cell_style = ParagraphStyle("Cell", fontSize=9, leading=12, fontName="Helvetica")
    label_style = ParagraphStyle("Label", parent=cell_style, fontName="Helvetica-Bold", fontSize=10)

    rows = []
    for r in lab_rows:
        zone_hex = ZONE_COLOR_HEX.get(r["zone"], "#000000")
        marker_hex = MARKER_TEXT_COLOR.get(r["marker_type"], "#888888")
        marker_style = ParagraphStyle("Marker", parent=cell_style, textColor=colors.HexColor(marker_hex),
                                       fontSize=8)
        zone_style = ParagraphStyle("Zone", parent=cell_style, textColor=colors.HexColor(zone_hex),
                                     fontName="Helvetica-Bold", fontSize=9)

        if r["zone"] == "info":
            status_text = "deskriptiv, kein etablierter Cutoff"
            status_para = Paragraph(status_text, cell_style)
        else:
            sev = f" — {r['severity']}" if r["severity"] not in ("—", "") else ""
            p5_text = f" · Normgrenze {r['p5']:.1f} {r['unit']}" if r["p5"] is not None else ""
            status_para = Paragraph(f"<font color='{zone_hex}'><b>{r['zone']}</b></font>{sev}{p5_text}",
                                     cell_style)

        left_cell = [
            Paragraph(r["label"], label_style),
            Paragraph(f"{r['value']:.1f} {r['unit']}", cell_style),
            Paragraph(r["marker_label"], marker_style),
            status_para,
        ]
        bar_img = fig_to_image_flowable(r["fig"], width_mm=105)
        rows.append([left_cell, bar_img])

    param_table = Table(rows, colWidths=[58*mm, 112*mm])
    base_style = [
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dddddd")),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.HexColor("#f7f7f9")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]
    param_table.setStyle(TableStyle(base_style))
    el.append(param_table)
    el.append(Spacer(1, 10))

    # ── Footer / Disclaimer ──────────────────────────────────────────────
    el.append(HRFlowable(width="100%", color=colors.HexColor("#dddddd"), thickness=0.75))
    el.append(Spacer(1, 4))
    el.append(Paragraph(
        "Referenzwerte: Hansen CS et al. (2024) Clin Auton Res 35:101–113; Task Force ESC/NASPE (1996) "
        "Circulation 93:1043–1065; Billman GE (2013) Front Physiol 4:26. Referenzbereiche stammen aus "
        "standardisierten 5-Minuten-Ruhemessungen — eine Routine-EEG-EKG-Ableitung erfüllt diese Bedingungen "
        "nicht. Werte sind als Orientierung zu verstehen, nicht als alleinige Diagnosekriterien. "
        "Nur lokale Verarbeitung — keine Datenübertragung.",
        ss["Small"],
    ))

    doc.build(el)
    return buf.getvalue()
