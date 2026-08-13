"""Gemeinsame Konstanten, Cache-Funktionen und Plot-Bausteine für alle App-Seiten."""

import html
import os
import numpy as np
import streamlit as st
import plotly.graph_objects as go

from core.i18n import tr

# ── Farben: Rechts = Rot, Links = Blau, Mittellinie = Grün (klinische Bedeutung) ─
C_RE   = "#c0392b"
C_LI   = "#1a5276"
C_MID  = "#1e8449"
C_REF  = "#6c3483"

CHAIN_OF = {
    ("Fp2","F8"):("Temporal re", C_RE), ("F8","T4"):("Temporal re", C_RE),
    ("T4","T6"):("Temporal re", C_RE),  ("T6","O2"):("Temporal re", C_RE),
    ("Fp1","F7"):("Temporal li", C_LI), ("F7","T3"):("Temporal li", C_LI),
    ("T3","T5"):("Temporal li", C_LI),  ("T5","O1"):("Temporal li", C_LI),
    ("Fp2","F4"):("Parasagittal re", C_RE), ("F4","C4"):("Parasagittal re", C_RE),
    ("C4","P4"):("Parasagittal re", C_RE),  ("P4","O2"):("Parasagittal re", C_RE),
    ("Fp1","F3"):("Parasagittal li", C_LI), ("F3","C3"):("Parasagittal li", C_LI),
    ("C3","P3"):("Parasagittal li", C_LI),  ("P3","O1"):("Parasagittal li", C_LI),
    ("Fz","Cz"):("Mittellinie", C_MID), ("Cz","Pz"):("Mittellinie", C_MID),
    ("Fp2","Cz"):("Rechts temporal", C_RE), ("F8","Cz"):("Rechts temporal", C_RE),
    ("T4","Cz"):("Rechts temporal", C_RE),  ("T6","Cz"):("Rechts temporal", C_RE),
    ("O2","Cz"):("Rechts temporal", C_RE),
    ("Fp1","Cz"):("Links temporal", C_LI), ("F7","Cz"):("Links temporal", C_LI),
    ("T3","Cz"):("Links temporal", C_LI),  ("T5","Cz"):("Links temporal", C_LI),
    ("O1","Cz"):("Links temporal", C_LI),
    ("F4","Cz"):("Rechts para", C_RE), ("C4","Cz"):("Rechts para", C_RE),
    ("P4","Cz"):("Rechts para", C_RE),
    ("F3","Cz"):("Links para", C_LI),  ("C3","Cz"):("Links para", C_LI),
    ("P3","Cz"):("Links para", C_LI),
    # ("Pz","Cz") separat nötig: MONTAGES["Referenziell Cz"] listet das Paar in dieser
    # Richtung (nicht ("Cz","Pz") wie oben) — CHAIN_OF-Lookup ist reihenfolgeabhängig.
    ("Pz","Cz"):("Mittellinie", C_MID),
}

MONTAGES = {
    "Doppelte Banane": [
        ("Fp2","F8"),("F8","T4"),("T4","T6"),("T6","O2"),
        ("Fp1","F7"),("F7","T3"),("T3","T5"),("T5","O1"),
        ("Fp2","F4"),("F4","C4"),("C4","P4"),("P4","O2"),
        ("Fp1","F3"),("F3","C3"),("C3","P3"),("P3","O1"),
        ("Fz","Cz"),("Cz","Pz"),
    ],
    "Temporal": [
        ("Fp2","F8"),("F8","T4"),("T4","T6"),("T6","O2"),
        ("Fp1","F7"),("F7","T3"),("T3","T5"),("T5","O1"),
    ],
    "Parasagittal": [
        ("Fp2","F4"),("F4","C4"),("C4","P4"),("P4","O2"),
        ("Fp1","F3"),("F3","C3"),("C3","P3"),("P3","O1"),
    ],
    "Referenziell Cz": [
        ("Fp2","Cz"),("F8","Cz"),("T4","Cz"),("T6","Cz"),("O2","Cz"),
        ("Fp1","Cz"),("F7","Cz"),("T3","Cz"),("T5","Cz"),("O1","Cz"),
        ("F4","Cz"),("C4","Cz"),("P4","Cz"),
        ("F3","Cz"),("C3","Cz"),("P3","Cz"),
        ("Fz","Cz"),("Pz","Cz"),
    ],
}

ELECTRODE_POS = {
    "Fp1": (-0.31, 0.95), "Fp2": (0.31, 0.95),
    "F7": (-0.81, 0.58), "F3": (-0.46, 0.64), "Fz": (0.0, 0.7),
    "F4": (0.46, 0.64),  "F8": (0.81, 0.58),
    "T3": (-0.95, 0.0),  "C3": (-0.5, 0.0), "Cz": (0.0, 0.0),
    "C4": (0.5, 0.0),    "T4": (0.95, 0.0),
    "T5": (-0.81, -0.58), "P3": (-0.46, -0.64), "Pz": (0.0, -0.7),
    "P4": (0.46, -0.64),  "T6": (0.81, -0.58),
    "O1": (-0.31, -0.95), "O2": (0.31, -0.95),
}

EPOCH_SEC = 10  # Standard-Epochenlänge (EKG-Tab, Fallback)

#: Vorbelegung des Patientenalters — an EINER Stelle, siehe get_patient_info().
STANDARD_ALTER = 52


def render_sidebar_status():
    """Persistente Patientenkontext-Karte in der Sidebar — sichtbar auf jeder Seite."""
    # Über get_edf_path(), nicht direkt aus dem Session-State: die Sidebar rendert VOR dem
    # Seiteninhalt und zeigte sonst nach einem Dateiwechsel für einen Durchlauf noch Dauer
    # und Kanalzahl der alten Aufnahme (aus `_edf_cache_meta`).
    edf_path  = get_edf_path()
    # html.escape: file_name stammt vom hochgeladenen Dateinamen (uploaded.name) und
    # landet unten via unsafe_allow_html direkt im DOM — ohne Escaping wäre ein
    # präparierter Dateiname ein Stored-XSS-Vektor gegen den eigenen Browser.
    file_name = html.escape(st.session_state.get("edf_display_name", ""))
    validated = st.session_state.get("phi_validated", False)

    with st.sidebar:
        # Haftungshinweis auf JEDER Seite, nicht nur beim Login. Der Login geschieht einmal
        # und der Cookie hält 30 Tage — wer täglich damit arbeitet, sieht die Login-Seite
        # praktisch nie wieder. Deshalb dauerhaft hier, dezent, aber nicht ausblendbar.
        st.caption("⚠️ " + tr("auth.disclaimer_short"))

        if not edf_path or not file_name:
            st.markdown(
                "<div style='"
                "margin:12px 6px 4px 6px;"
                "padding:10px 12px;"
                "border-radius:10px;"
                "background:#f5f6f8;"
                "border:1px dashed #ced4da;"
                "color:#888;"
                "font-size:12px;"
                "line-height:1.5;"
                "'>"
                f"<span class='material-symbol' style='font-size:0.95em;vertical-align:-2px'>folder_open</span> <b>{tr('sidebar.no_file_title')}</b><br>"
                f"<span style='font-size:11px'>{tr('sidebar.no_file_hint')}<i>{tr('sidebar.no_file_hint_page')}</i>{tr('sidebar.no_file_hint_suffix')}</span>"
                "</div>",
                unsafe_allow_html=True,
            )
            return

        age   = st.session_state.get("patient_age", "?")
        sex   = st.session_state.get("patient_sex", "X")
        sex_icon = {"M": "♂", "F": "♀", "X": "—"}.get(sex, "—")

        edf = st.session_state.get("_edf_cache_meta")
        dur_str = "—"
        n_ch_str = "—"
        has_ecg = False
        has_hv  = False
        if edf is None:
            try:
                from core.shared import load_and_prepare as _lp
                edf = _lp(edf_path)
                st.session_state["_edf_cache_meta"] = edf
            except Exception:
                edf = {}
        if edf:
            dur_s   = edf.get("duration_s", 0)
            dur_str = f"{int(dur_s)//60}:{int(dur_s)%60:02d} min"
            n_ch_str = str(len(edf.get("eeg_map", {}))) + " EEG"
            has_ecg = bool(edf.get("ecg_channels"))
            anns = edf.get("annotations", [])
            has_hv = any("HVT" in a.get("description","").upper() for a in anns)

        _ecg_icon_span = ("<span class='material-symbol' "
                         "style='font-size:0.95em;vertical-align:-2px'>ecg_heart</span> ")

        _has_phi = st.session_state.get("phi_has_patient_data", False)
        if not validated:
            phi_badge = (f"{status_dot('warning')}<span style='color:#e67e22;font-size:10px;"
                        f"font-weight:700'>{tr('sidebar.not_checked')}</span>")
        elif _has_phi:
            phi_badge = (f"{status_dot('warning')}<span style='color:#e67e22;font-size:10px;"
                        f"font-weight:700'>{tr('sidebar.phi_warning')}</span>")
        else:
            phi_badge = (f"{status_dot('success')}<span style='color:#27ae60;font-size:10px;"
                        f"font-weight:700'>{tr('sidebar.anonymized')}</span>")

        st.markdown(
            f"<div style='"
            f"margin:10px 6px 4px 6px;"
            f"padding:12px 14px;"
            f"border-radius:12px;"
            f"background:#ffffff;"
            f"border:1px solid #e0e4e8;"
            f"box-shadow:0 1px 4px rgba(0,0,0,0.06);"
            f"'>"
            # Header
            f"<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:8px'>"
            f"<span style='font-size:11px;font-weight:700;color:#555;text-transform:uppercase;"
            f"letter-spacing:0.05em'>{tr('sidebar.active_recording')}</span>"
            f"{phi_badge}"
            f"</div>"
            # Dateiname
            f"<div style='font-size:12px;font-weight:600;color:#1c2833;"
            f"white-space:nowrap;overflow:hidden;text-overflow:ellipsis;"
            f"margin-bottom:10px;' title='{file_name}'>"
            f"<span class='material-symbol' style='font-size:0.95em;vertical-align:-2px'>description</span> {file_name}"
            f"</div>"
            # Metriken-Grid
            f"<div style='display:grid;grid-template-columns:1fr 1fr;gap:6px'>"
            f"<div style='background:#f8f9fa;border-radius:8px;padding:6px 8px'>"
            f"<div style='font-size:10px;color:#888'>{tr('sidebar.age_label')}</div>"
            f"<div style='font-size:13px;font-weight:700;color:#1c2833'>{age} {tr('sidebar.years_suffix')} {sex_icon}</div>"
            f"</div>"
            f"<div style='background:#f8f9fa;border-radius:8px;padding:6px 8px'>"
            f"<div style='font-size:10px;color:#888'>{tr('sidebar.duration_label')}</div>"
            f"<div style='font-size:13px;font-weight:700;color:#1c2833'>{dur_str}</div>"
            f"</div>"
            f"<div style='background:#f8f9fa;border-radius:8px;padding:6px 8px'>"
            f"<div style='font-size:10px;color:#888'>{tr('sidebar.channels_label')}</div>"
            f"<div style='font-size:13px;font-weight:700;color:#1c2833'>{n_ch_str}</div>"
            f"</div>"
            f"<div style='background:#f8f9fa;border-radius:8px;padding:6px 8px'>"
            f"<div style='font-size:10px;color:#888'>{tr('sidebar.features_label')}</div>"
            f"<div style='font-size:12px;font-weight:600;color:#1c2833'>"
            f"{_ecg_icon_span if has_ecg else ''}"
            f"{'HV' if has_hv else ''}"
            f"{'—' if not has_ecg and not has_hv else ''}"
            f"</div>"
            f"</div>"
            f"</div>"
            f"</div>",
            unsafe_allow_html=True,
        )


def section_header(title: str, subtitle: str = "", color: str = "#2c3e50") -> None:
    """Visueller Section-Header — ersetzt st.divider() + st.subheader() überall in der App."""
    sub_html = (
        f"<span style='font-size:12px;color:#888;font-weight:400;"
        f"margin-left:10px'>{subtitle}</span>"
        if subtitle else ""
    )
    st.markdown(
        f"<div style='"
        f"margin:22px 0 10px 0;"
        f"padding:10px 16px;"
        f"border-left:4px solid {color};"
        f"background:linear-gradient(90deg,{color}0d 0%,transparent 100%);"
        f"border-radius:0 8px 8px 0;"
        f"'>"
        f"<span style='font-size:15px;font-weight:700;color:{color}'>{title}</span>"
        f"{sub_html}"
        f"</div>",
        unsafe_allow_html=True,
    )


def render_banner(kind: str, title: str, body: str, icon: str = None) -> None:
    """Einheitlicher Status-Banner (Phase 2 des GUI-Redesigns, siehe [[project_edf_ui_redesign]]).

    Ersetzt die zuvor über ~8 Stellen (rhythm_screening.py, ecg_hrv.py, eeg_spectrum.py,
    aperiodic.py) verstreuten Ad-hoc-st.markdown-Banner mit je eigenen Hex-Werten durch eine
    Quelle, die die konsolidierten Farben aus core/design_tokens.py nutzt.

    kind: "info" | "success" | "warning" | "danger" — mappt auf INFO/SUCCESS/WARNING/DANGER.
    body: darf HTML enthalten (z.B. <br> oder <b>), wird nicht escaped.
    """
    from core.design_tokens import DANGER, WARNING, SUCCESS, INFO
    color = {"info": INFO, "success": SUCCESS, "warning": WARNING, "danger": DANGER}.get(kind, INFO)
    if icon is None:
        icon = {"info": "ℹ️", "success": "✅", "warning": "⚠️", "danger": "⚠️"}.get(kind, "ℹ️")
    st.markdown(
        f"<div style='background:{color}14;border:1.5px solid {color}66;"
        f"border-radius:10px;padding:10px 14px;margin-bottom:10px;font-size:13px;"
        f"color:#1d1d1f;line-height:1.5'>"
        f"{icon} <b style='color:{color}'>{title}:</b> {body}"
        f"</div>",
        unsafe_allow_html=True,
    )


def status_dot(zone: str, size: int = 9) -> str:
    """HTML-Farbpunkt (ersetzt 🔴🟡🟢⚪-Ampel-Emoji, Phase 2 GUI-Redesign, siehe
    [[project_edf_ui_redesign]]). NUR innerhalb von st.markdown(unsafe_allow_html=True)
    nutzbar — in st.tabs()/st.expander()-Titeln etc. stattdessen `status_bullet()` verwenden.

    zone: "danger" | "warning" | "success" | "neutral" — mappt auf DANGER/WARNING/SUCCESS
    aus core/design_tokens.py bzw. neutralgrau.
    """
    from core.design_tokens import DANGER, WARNING, SUCCESS
    color = {"danger": DANGER, "warning": WARNING, "success": SUCCESS}.get(zone, "#86868b")
    return (f"<span style='display:inline-block;width:{size}px;height:{size}px;"
            f"border-radius:50%;background:{color};margin-right:5px;vertical-align:middle'>"
            f"</span>")


def status_bullet(zone: str = "neutral") -> str:
    """Reiner Unicode-Punkt (kein HTML) für Kontexte ohne unsafe_allow_html (Tab-Titel,
    Expander-Header, st.caption ohne HTML) — ersetzt bunte Ampel-Emoji durch einen
    neutralen, ruhigeren Marker, ohne Farbe (dort nicht renderbar)."""
    return "●"


_KPI_ZONE_COLOR = {"success": "#27ae60", "warning": "#e67e22", "danger": "#c0392b",
                   "info": "#2471a3", "neutral": "#86868b"}


def kpi_tile(label: str, value: str, sub_text: str = "", zone: str = "info",
            border_color: str = None, dot_color: str = None, muted: bool = False) -> str:
    """Einheitliche KPI-Kachel (Phase 3 GUI-Redesign, siehe [[project_edf_ui_redesign]]) —
    ersetzt die zuvor unabhängig in `views/eeg_spectrum.py` (`_kpi_card`) und
    `views/ecg_hrv.py` (`_metric_card`) definierten, visuell leicht unterschiedlichen
    Kachel-Varianten durch EINE gemeinsame Quelle. Continuous-Corner-/Border-Top-Akzent-Stil
    (Apple-artig, wie im Referenz-Prompt), nutzt `core/design_tokens.py`-Farben als Default.

    zone: "success"|"warning"|"danger"|"info"|"neutral" — bestimmt Rand-/Punktfarbe, sofern
    `border_color`/`dot_color` nicht explizit übergeben werden (z. B. für bandspezifische
    Farben wie `BAND_COLOR` in eeg_spectrum.py, die keiner der 5 Zonen entsprechen).
    `muted=True` dämpft die Kachel optisch (z. B. wenn der Wert kaum Aussagekraft hat).
    """
    col = border_color or _KPI_ZONE_COLOR.get(zone, _KPI_ZONE_COLOR["info"])
    _dot = (f"<span style='color:{dot_color};font-size:15px;margin-left:6px'>●</span>"
            if dot_color else "")
    op = "0.55" if muted else "1"
    return (
        f"<div style='background:var(--surface-1,#f8f9fa);border:0.5px solid var(--border);"
        f"border-top:3px solid {col};border-radius:0 10px 10px 0;"
        f"padding:10px 12px;opacity:{op};min-height:74px'>"
        f"<div style='font-size:11px;color:var(--text-secondary,#6b7684)'>{label}</div>"
        f"<div style='font-size:20px;font-weight:800;color:var(--text-primary,#1c2833)'>"
        f"{value}{_dot}</div>"
        f"<div style='font-size:10px;color:var(--text-muted,#98a3b0);margin-top:3px'>"
        f"{sub_text}</div></div>")


def register_plotly_theme():
    """Registriert ein gemeinsames Plotly-Template (Phase 4 GUI-Redesign, siehe
    [[project_edf_ui_redesign]]) und setzt es als App-weiten Default — Foundation-Schritt wie
    Phase 0: neue/nicht explizit gestylte Diagramm-Elemente (Achsen, Grid, Schrift, Legende,
    Standard-Farbfolge) folgen ab jetzt EINER Quelle statt der bisher pro Seite verstreuten
    Hex-Werte. Diagramme, die Farben/Hintergrund EXPLIZIT selbst setzen (z. B. `plot_bgcolor=
    "#fafafa"`, klinische Ampelfarben für Befunde), überschreiben das Template lokal — das ist
    gewollt (fachliche Farben bleiben reserviert) und wird seitenweise erst in Phase 5 bereinigt,
    nicht rückwirkend hier. Mehrfacher Aufruf ist billig (Plotly dedupliziert das Template)."""
    import plotly.io as pio
    import plotly.graph_objects as _go
    from core.design_tokens import (BG_SUBTLE, BORDER, TEXT_PRIMARY, TEXT_SECONDARY, ACCENT,
                                     DANGER, WARNING, SUCCESS, INFO)
    if "edf_analyzer" not in pio.templates:
        _font = dict(family="-apple-system, BlinkMacSystemFont, 'SF Pro Text', "
                            "Helvetica, Arial, sans-serif", color=TEXT_PRIMARY, size=12)
        _axis = dict(gridcolor="rgba(0,0,0,0.06)", zerolinecolor="rgba(0,0,0,0.10)",
                    linecolor=BORDER, tickfont=dict(color=TEXT_SECONDARY, size=10),
                    title_font=dict(color=TEXT_SECONDARY, size=11))
        pio.templates["edf_analyzer"] = _go.layout.Template(layout=_go.Layout(
            font=_font,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor=BG_SUBTLE,
            colorway=[ACCENT, SUCCESS, WARNING, DANGER, INFO, "#9b59b6", "#e67e22"],
            xaxis=_axis, yaxis=_axis,
            legend=dict(font=dict(size=11, color=TEXT_SECONDARY)),
            margin=dict(t=30, b=35, l=45, r=10),
        ))
    pio.templates.default = "edf_analyzer"


def apply_global_style():
    """Neutrale, hochwertige Basis-Optik. Klinische Farben (Rot/Blau/Grün/Ampel) bleiben
    ausschließlich für ihre fachliche Bedeutung reserviert und werden hier nicht verändert.

    Phase 0 des GUI-Redesigns (User-Vorgabe 2026-08-08, siehe [[project_edf_ui_redesign]]):
    CSS-Variablen aus core/design_tokens.py + ein paar Utility-Klassen (.eyebrow/.hero-title/
    .subtitle/.dw-card) als FUNDAMENT für die kommenden Phasen (Navigation, Status-Banner,
    Karten, Plotly-Theme). Migriert NICHT rückwirkend bestehende Seiten — die nutzen bis zur
    jeweiligen Phase weiterhin ihre bisherigen Ad-hoc-Styles, nichts bricht."""
    register_plotly_theme()
    from core.design_tokens import (BG_SUBTLE, SURFACE, BORDER, TEXT_PRIMARY, TEXT_SECONDARY,
                                    ACCENT, ACCENT_HOVER, DANGER, WARNING, SUCCESS, INFO,
                                    RADIUS_SM, RADIUS_MD, RADIUS_LG, RADIUS_XL,
                                    FONT_EYEBROW_PX, FONT_HERO_PX, FONT_SUBTITLE_PX,
                                    ICON_FONT_CSS)
    st.markdown(f"""
    <style>
    /* Schriften werden NICHT von einem CDN geladen (gemessen 2026-08-11: der frühere
    @import auf fonts.googleapis.com erzeugte pro Seitenaufruf echte Requests, also eine
    Übermittlung der Nutzer-IP an Google). Inter liegt jetzt lokal unter static/fonts/,
    ausgeliefert über Streamlits statischen Ordner (server.enableStaticServing). */
    /* latin */
    @font-face {{
        font-family: 'Inter';
        src: url('app/static/fonts/Inter-latin.woff2') format('woff2');
        font-weight: 100 900;
        font-style: normal;
        font-display: swap;
        unicode-range: U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+0304, U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD;
    }}
    /* latin-ext */
    @font-face {{
        font-family: 'Inter';
        src: url('app/static/fonts/Inter-latin-ext.woff2') format('woff2');
        font-weight: 100 900;
        font-style: normal;
        font-display: swap;
        unicode-range: U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+0304, U+0308, U+0329, U+1D00-1DBF, U+1E00-1E9F, U+1EF2-1EFF, U+2020, U+20A0-20AB, U+20AD-20C0, U+2113, U+2C60-2C7F, U+A720-A7FF;
    }}
    /* greek */
    @font-face {{
        font-family: 'Inter';
        src: url('app/static/fonts/Inter-greek.woff2') format('woff2');
        font-weight: 100 900;
        font-style: normal;
        font-display: swap;
        unicode-range: U+0370-0377, U+037A-037F, U+0384-038A, U+038C, U+038E-03A1, U+03A3-03FF;
    }}

    /* Phase 6 GUI-Redesign (siehe [[project_edf_ui_redesign]]): Material-Symbols-Glyphen für
    eigenen HTML-Content (z. B. Kanal-Typ-Icons) — ersetzt Emoji außerhalb der von Streamlit
    selbst gerenderten `:material/...:`-Shortcodes (Seitentitel/Nav, die brauchen das nicht).

    Nutzt bewusst 'Material Symbols Rounded': diese Variante bringt STREAMLIT bereits lokal
    mit, es muss also keine zweite Schriftdatei ins Repo und es geht kein Request nach außen.
    Nebeneffekt: die eigenen HTML-Icons sehen damit genauso aus wie Streamlits native
    `:material/...:`-Icons. Die Ligaturnamen (z. B. `ecg_heart`) sind bei beiden Varianten
    identisch, der Wechsel ändert nur die Strichführung. */
    .material-symbol {{
        font-family: {ICON_FONT_CSS};
        font-weight: normal;
        font-style: normal;
        line-height: 1;
        vertical-align: middle;
        -webkit-font-smoothing: antialiased;
    }}

    :root {{
        --dw-bg-subtle: {BG_SUBTLE};
        --dw-surface: {SURFACE};
        --dw-border: {BORDER};
        --dw-text-primary: {TEXT_PRIMARY};
        --dw-text-secondary: {TEXT_SECONDARY};
        --dw-accent: {ACCENT};
        --dw-accent-hover: {ACCENT_HOVER};
        --dw-danger: {DANGER};
        --dw-warning: {WARNING};
        --dw-success: {SUCCESS};
        --dw-info: {INFO};
        --dw-radius-sm: {RADIUS_SM}px;
        --dw-radius-md: {RADIUS_MD}px;
        --dw-radius-lg: {RADIUS_LG}px;
        --dw-radius-xl: {RADIUS_XL}px;
    }}

    html, body, [class*="css"] {{
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'SF Pro Text', sans-serif;
    }}
    h1, h2, h3, h4, h5, h6 {{
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'SF Pro Display', sans-serif;
        font-weight: 600;
        letter-spacing: -0.01em;
        color: var(--dw-text-primary);
    }}
    /* Seitentitel (st.title -> h1): Phase 1, engere Laufweite passend zur Design-Token-Skala.
    Größe bewusst NICHT auf FONT_HERO_PX erzwungen (Streamlits Default liegt schon nah dran,
    !important-Kämpfe mit internen Responsive-Regeln würden nur Risiko ohne echten Zugewinn
    bringen). Icon-Glyphen (:material/...:) etwas transparenter, wirken so wie sekundäre
    Symbole statt bunte Sticker. */
    h1 {{ letter-spacing: -0.02em; }}
    h1 [data-testid="stIconMaterial"] {{ opacity: 0.7; vertical-align: -2px; }}
    [data-testid="stMetricValue"] {{ font-weight: 700; }}

    /* Sidebar / Navigation — Phase 1 (2026-08-08): etwas mehr Luft zwischen den Einträgen,
    aktive Seite in der Akzentfarbe statt Streamlits Standard-Rot, dezenterer Hover. Reines
    CSS, keine zusätzlichen Komponenten/Rechenlast. */
    [data-testid="stSidebar"] {{
        background: var(--dw-bg-subtle);
        border-right: 1px solid var(--dw-border);
    }}
    [data-testid="stSidebarNav"] a {{
        border-radius: var(--dw-radius-sm);
        margin: 2px 8px;
        padding-top: 8px;
        padding-bottom: 8px;
        font-weight: 500;
        color: var(--dw-text-primary);
        transition: background 0.12s ease;
    }}
    [data-testid="stSidebarNav"] a:hover {{
        background: rgba(0,0,0,0.04);
    }}
    [data-testid="stSidebarNav"] a[aria-current="page"] {{
        background: color-mix(in srgb, var(--dw-accent) 10%, transparent);
        color: var(--dw-accent);
        font-weight: 600;
    }}
    [data-testid="stSidebarNav"] a[aria-current="page"] span {{
        color: var(--dw-accent) !important;
    }}

    /* Karten / Container */
    div[data-testid="stExpander"] {{
        border-radius: var(--dw-radius-md);
        border: 1px solid #e8eaed;
    }}
    div[data-testid="stVerticalBlockBorderWrapper"] {{
        border-radius: var(--dw-radius-md) !important;
    }}
    .stButton button {{ border-radius: var(--dw-radius-sm); }}
    hr {{ margin: 0.6rem 0; opacity: 0.5; }}

    /* ── Phase-0-Utility-Klassen (Typografie-Skala aus dem Referenz-Prompt, auf
    App-Seitentitel statt Marketing-Hero herunterskaliert) — ab jetzt für neue/migrierte
    Seiten nutzbar, siehe [[project_edf_ui_redesign]] Phase 1 ────────────────────────────── */
    .dw-eyebrow {{
        font-size: {FONT_EYEBROW_PX}px;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        font-weight: 600;
        color: var(--dw-text-secondary);
        margin-bottom: 4px;
    }}
    .dw-hero-title {{
        font-size: {FONT_HERO_PX}px;
        font-weight: 600;
        letter-spacing: -0.02em;
        line-height: 1.1;
        color: var(--dw-text-primary);
        margin: 0 0 6px 0;
    }}
    .dw-subtitle {{
        font-size: {FONT_SUBTITLE_PX}px;
        font-weight: 400;
        color: var(--dw-text-secondary);
        line-height: 1.4;
        margin: 0 0 20px 0;
    }}
    .dw-card {{
        background: var(--dw-surface);
        border: 1px solid var(--dw-border);
        border-radius: var(--dw-radius-lg);
        padding: 20px 24px;
    }}
    .dw-card-subtle {{
        background: var(--dw-bg-subtle);
        border: 1px solid var(--dw-border);
        border-radius: var(--dw-radius-lg);
        padding: 20px 24px;
    }}

    /* Mobile-Grundbasis: etwas kompaktere Abstände auf schmalen Bildschirmen */
    @media (max-width: 640px) {{
        h1 {{ font-size: 1.4rem !important; }}
        h2 {{ font-size: 1.15rem !important; }}
        h3 {{ font-size: 1.0rem !important; }}
        [data-testid="stMetricValue"] {{ font-size: 1.1rem !important; }}
        .block-container {{ padding-left: 0.8rem !important; padding-right: 0.8rem !important; }}
        .dw-hero-title {{ font-size: 26px; }}
    }}
    </style>
    """, unsafe_allow_html=True)


def render_head_diagram(pairs):
    """Schematischer 10-20-Kopf mit der aktuellen Montagenkette farbig eingezeichnet."""
    fig = go.Figure()
    theta = np.linspace(0, 2 * np.pi, 100)
    fig.add_trace(go.Scatter(x=np.cos(theta), y=np.sin(theta), mode="lines",
                              line=dict(color="#aaa", width=1.5), hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(x=[-0.08, 0, 0.08], y=[0.99, 1.13, 0.99], mode="lines",
                              line=dict(color="#aaa", width=1.5), hoverinfo="skip", showlegend=False))
    for sx in (-1, 1):
        fig.add_trace(go.Scatter(x=[sx * 0.99, sx * 1.07, sx * 0.99], y=[0.18, 0, -0.18], mode="lines",
                                  line=dict(color="#aaa", width=1.5), hoverinfo="skip", showlegend=False))
    for anode, cathode in pairs:
        if anode in ELECTRODE_POS and cathode in ELECTRODE_POS:
            _, color = CHAIN_OF.get((anode, cathode), ("andere", "#999"))
            x0, y0 = ELECTRODE_POS[anode]
            x1, y1 = ELECTRODE_POS[cathode]
            fig.add_trace(go.Scatter(x=[x0, x1], y=[y0, y1], mode="lines",
                                      line=dict(color=color, width=3), hoverinfo="skip", showlegend=False))
    xs = [p[0] for p in ELECTRODE_POS.values()]
    ys = [p[1] for p in ELECTRODE_POS.values()]
    labels = list(ELECTRODE_POS.keys())
    used = {e for pair in pairs for e in pair if e in ELECTRODE_POS}
    colors_pt = ["#2c3e50" if lbl in used else "#cccccc" for lbl in labels]
    fig.add_trace(go.Scatter(
        x=xs, y=ys, mode="markers+text", text=labels, textposition="middle center",
        textfont=dict(size=7, color="white"),
        marker=dict(size=17, color=colors_pt, line=dict(width=1, color="white")),
        hoverinfo="skip", showlegend=False,
    ))
    fig.update_layout(
        xaxis=dict(visible=False, range=[-1.3, 1.3], scaleanchor="y"),
        yaxis=dict(visible=False, range=[-1.3, 1.3]),
        height=260, margin=dict(t=5, b=5, l=5, r=5),
        plot_bgcolor="white",
    )
    return fig


# show_spinner=False + expliziter st.spinner an der Aufrufstelle (get_edf_or_stop): ein
# Dekorator-Argument wird beim IMPORT ausgewertet, ein t()-Aufruf dort würde die Sprache
# dauerhaft auf den beim Prozessstart geltenden Wert einfrieren.
@st.cache_data(show_spinner=False)
def load_and_prepare(path: str):
    """Lädt EDF, extrahiert alle Kanäle als numpy-Matrix, filtert ECG vorab.

    RAM-Faustregel (empirisch, Audit 2026-07-04): ~180 MB pro Session für eine typische
    mehrkanalige 10-Minuten-Aufnahme — deutlich mehr als die Upload-Dateigröße, da die
    Rohdaten als float64-Arrays gehalten und beim Laden/Filtern mehrfach kopiert werden.
    Kein hartes RAM-Limit hinterlegt; siehe .streamlit/config.toml für den Kontext zu
    `maxUploadSize` (begrenzt nur die Dateigröße, nicht den RAM-Bedarf).
    """
    import mne
    from scipy.signal import butter, filtfilt
    from core.channel_classifier import classify_channels, make_short_name, ECG, EEG

    raw = mne.io.read_raw_edf(path, preload=True, verbose=False, encoding="latin1")
    sfreq = raw.info["sfreq"]
    data, _ = raw[:]
    ch_names = raw.ch_names

    # ── Unit-Skalierungs-Korrektur ────────────────────────────────────────────
    # Manche EDF-Dateien lassen das Physical-Dimension-Feld leer oder auf 'n/a'.
    # MNE hat dann keine Unit-Information und behandelt die physikalischen Werte
    # als Volt, obwohl sie in µV gespeichert sind → Amplitude 10⁶ zu groß.
    # Heuristik: wenn _orig_units nur 'n/a' enthält UND der Median-Std aller
    # Kanäle > 1 mV ist, liegt µV-als-V-Skalierung vor → durch 1e6 dividieren.
    _orig_units = getattr(raw, "_orig_units", {})
    if _orig_units and all(u.strip().lower() in ("n/a", "", "na") for u in _orig_units.values()):
        _med_std = float(np.median(np.std(data, axis=1)))
        if _med_std > 1e-3:  # > 1 mV median std → µV ohne Unit-Label
            data = data / 1e6
    n_samples = data.shape[1]
    duration_s = n_samples / sfreq

    ch_idx = {ch: i for i, ch in enumerate(ch_names)}

    # ── Signal-based channel classification (manufacturer-independent) ─────────
    classifications = classify_channels(
        data, ch_names, sfreq,
        max_analysis_sec=120.0,
        filename=os.path.basename(path),
    )

    # EEG map: use signal-detected EEG channels; fall back to name prefix for
    # files where the classifier has low confidence (e.g. very short recordings)
    eeg_map: dict = {}
    for ch, result in classifications.items():
        if result.channel_type == EEG:
            short = make_short_name(ch)
            eeg_map[short] = ch_idx[ch]

    # Fallback for NeuroFax files or recordings where classifier found 0 EEG channels
    if not eeg_map:
        for ch in ch_names:
            if ch.upper().startswith("EEG"):
                short = make_short_name(ch)
                eeg_map[short] = ch_idx[ch]

    # ECG channels: require minimum confidence of 60% to avoid wearable-EEG artifacts.
    # Sortierung: Konfidenz zuerst, bei GLEICHSTAND (z. B. mehrere Kandidaten mit 97%,
    # wie häufig bei diesem Aufnahmesystem) QRS-Formkonsistenz als Tie-Breaker — sonst
    # entschied bisher die zufällige Dict-Reihenfolge (=Kanalreihenfolge in der EDF-Datei),
    # wodurch ecg_channels[0] (der überall als "der" EKG-Kanal verwendet wird, z. B.
    # Report-Export/Glory-Report) nicht zuverlässig der qualitativ beste Kandidat war
    # (User-Fund 2026-08-08, siehe [[project_edf_ekg_polaritaet_stellen]]).
    _ECG_MIN_CONF = 60.0

    def _ecg_tiebreak(r):
        # Dieselbe Amplituden-abgeschmolzene Formkonsistenz wie core/channel_classifier.py
        # ::_ecg_quality() — bewusst dupliziert statt importiert (core/ bleibt entkoppelt
        # von der Klassifizierer-internen Post-Processing-Logik), siehe
        # [[project_edf_ekg_polaritaet_stellen]].
        p2p = r.features.get("p2p_mv", 0.0)
        tmpl = r.features.get("qrs_template_corr", 0.0)
        return tmpl * min(1.0, p2p / 0.3)

    ecg_channels = [
        ch for ch, r in sorted(
            classifications.items(),
            key=lambda x: (-x[1].confidence, -_ecg_tiebreak(x[1]))
        )
        if r.channel_type == ECG and r.confidence >= _ECG_MIN_CONF
    ]

    # EOG and EMG channels
    from core.channel_classifier import EOG, EMG
    eog_channels = [ch for ch, r in classifications.items() if r.channel_type == EOG]
    emg_channels = [ch for ch, r in classifications.items() if r.channel_type == EMG]

    # Bandpass-filtered ECG signals for display (0.5–40 Hz). Polaritäts-korrigiert an der
    # QUELLE (User-Audit 2026-08-08): dieses Dict wird app-weit für die EKG-Darstellung
    # wiederverwendet (EEG-Viewer, EKG&HRV-Hauptkurve, Report) — ohne Korrektur hier würde
    # die Kurve bei jedem invertierten Kanal (z. B. POL X1, systematische Gerätekonvention
    # dieses Aufnahmesystems, siehe [[project_edf_rhythm_screening]]) trotz korrekter RR-
    # Zeiten optisch mit der R-Zacke nach unten erscheinen. Flip-Entscheidung auf dem
    # UNGEFILTERTEN Signal (robuster, wie überall sonst in der App).
    from analysis.ecg import detect_polarity_flip
    ecg_filtered = {}
    nyq = sfreq / 2
    b, a = butter(4, [0.5 / nyq, min(40.0 / nyq, 0.99)], btype="band")
    for ch in ecg_channels:
        idx = ch_idx[ch]
        sig = data[idx].copy().astype(np.float64)
        sig -= sig.mean()
        if detect_polarity_flip(sig, sfreq):
            sig = -sig
        sig = filtfilt(b, a, sig)
        ecg_filtered[ch] = sig

    with open(path, "rb") as f:
        hdr = f.read(256)
    patient_id = hdr[8:88].decode("latin1").strip()
    rec_id = hdr[88:168].decode("latin1").strip()

    # EDF+ patient_id Feld parsen: "patientcode sex birthdate name" (Felder durch Leerzeichen)
    # Patientenname wird NICHT weitergegeben — nur Geburtsdatum, Geburtsjahr und Geschlecht.
    # Anonymisierte Dateien haben "X X X X" — dann bleiben alle header_* = None.
    header_birth_date = None
    header_birth_year = None
    header_calculated_age = None
    header_sex = None  # "M" | "F" | None

    import re as _re
    _MONTHS = {"JAN":1,"FEB":2,"MAR":3,"APR":4,"MAY":5,"JUN":6,
                "JUL":7,"AUG":8,"SEP":9,"OCT":10,"NOV":11,"DEC":12}

    # EDF+ Standard-Format: Felder durch Leerzeichen getrennt
    _fields = patient_id.split()
    # Geschlecht: zweites Feld wenn M oder F
    if len(_fields) >= 2 and _fields[1].upper() in ("M", "F"):
        header_sex = _fields[1].upper()

    # Geburtsdatum: drittes Feld oder irgendwo im String als DD-MMM-YYYY
    _m = _re.search(r'(\d{2})-([A-Z]{3})-(\d{4})', patient_id)
    if _m:
        try:
            from datetime import date as _date
            day, mon_str, year = int(_m.group(1)), _m.group(2), int(_m.group(3))
            if mon_str in _MONTHS and 1900 < year < 2030:
                birth = _date(year, _MONTHS[mon_str], day)
                header_birth_date = birth.strftime("%d.%m.%Y")
                header_birth_year = year
                today = _date.today()
                header_calculated_age = today.year - year - (
                    (today.month, today.day) < (birth.month, birth.day))
        except Exception:
            pass

    annotations = []
    for ann in raw.annotations:
        desc = ann["description"]
        if "np.str_" in desc:
            desc = desc.replace("np.str_('", "").rstrip("')")
        if desc.startswith("+") and desc[1:].replace(".", "").isdigit():
            continue
        annotations.append({"onset_s": round(float(ann["onset"]), 2), "description": desc})

    return {
        "data": data,
        "ch_names": ch_names,
        "ch_idx": ch_idx,
        "eeg_map": eeg_map,
        "ecg_filtered": ecg_filtered,
        "ecg_channels": ecg_channels,
        "eog_channels": eog_channels,
        "emg_channels": emg_channels,
        "channel_classifications": classifications,
        "sfreq": sfreq,
        "n_samples": n_samples,
        "duration_s": duration_s,
        "n_epochs": int(duration_s // EPOCH_SEC),
        "annotations": annotations,
        "has_patient_id": bool(patient_id and patient_id not in ("X X X X", "X")),
        "has_rec_id": bool(rec_id),
        "header_birth_date": header_birth_date,
        "header_birth_year": header_birth_year,
        "header_calculated_age": header_calculated_age,
        "header_sex": header_sex,
    }


@st.cache_data(show_spinner=False)  # s. load_and_prepare: Spinner-Text an der Aufrufstelle
def get_filtered_eeg(_data, eeg_map, sfreq, low_hz, high_hz):
    """Bandpass-Filter auf die EEG-Kanäle der Datenmatrix. _data wird nicht gehasht."""
    from scipy.signal import butter, filtfilt
    filtered = _data.copy()
    idxs = list(eeg_map.values())
    if idxs:
        nyq = sfreq / 2
        b, a = butter(4, [low_hz / nyq, min(high_hz / nyq, 0.99)], btype="band")
        filtered[idxs] = filtfilt(b, a, _data[idxs], axis=1)
    return filtered


def get_bipolar_epoch(d, eeg_map, pairs, i_s, i_e):
    """Berechnet bipolare Ableitungen nur für die Epoche."""
    result = []
    for anode, cathode in pairs:
        ia, ib = eeg_map.get(anode), eeg_map.get(cathode)
        label = f"{anode}–{cathode}"
        chain, color = CHAIN_OF.get((anode, cathode), ("andere", "#555"))
        if ia is not None and ib is not None:
            seg = (d[ia, i_s:i_e] - d[ib, i_s:i_e]) * 1e6
            result.append((label, seg, chain, color))
        else:
            result.append((label, None, chain, color))
    return result


def eeg_figure(derivs, t, spacing, annotations, t_s, t_e):
    """EEG-Plot mit Kettenspacern zwischen Gruppen."""
    GAP = spacing * 1.2

    offsets = []
    y = 0.0
    prev_chain = derivs[-1][2]
    for item in reversed(derivs):
        chain = item[2]
        if chain != prev_chain:
            y += GAP
        offsets.insert(0, y)
        y += spacing
        prev_chain = chain
    total_height = y

    seen = set()
    fig = go.Figure()

    for idx, item in enumerate(derivs):
        label, seg, chain, color = item[:4]
        hover_values = item[4] if len(item) > 4 else seg
        hover_unit = item[5] if len(item) > 5 else "µV"
        offset = offsets[idx]
        show_leg = chain not in seen; seen.add(chain)
        if seg is not None:
            # EEG-Konvention: negativ oben → Signal negieren außer bei EKG-Lane
            plot_seg = seg if chain == "EKG" else -seg
            fig.add_trace(go.Scatter(
                x=t, y=plot_seg + offset, mode="lines",
                name=chain, legendgroup=chain, showlegend=show_leg,
                line=dict(width=1.6, color=color),
                hovertemplate=f"<b>{label}</b>: %{{customdata:.3f}} {hover_unit}<extra></extra>",
                customdata=hover_values,
            ))
        else:
            fig.add_trace(go.Scatter(
                x=[t[0], t[-1]], y=[offset, offset], mode="lines",
                line=dict(width=0.5, color="#ccc", dash="dot"),
                showlegend=False, hoverinfo="skip",
            ))

    prev_chain = derivs[0][2]
    for i, item in enumerate(derivs[1:], 1):
        chain = item[2]
        if chain != prev_chain:
            sep_y = (offsets[i - 1] + offsets[i]) / 2
            fig.add_hline(y=sep_y, line_dash="dot", line_color="#cccccc", line_width=1)
        prev_chain = chain

    for ann in annotations:
        o = ann["onset_s"]
        if t_s <= o <= t_e:
            fig.add_vline(x=o, line_dash="dot", line_color="#e67e22", line_width=1.2,
                          annotation_text=ann["description"][:22],
                          annotation_font_size=9, annotation_position="top left")

    fig.update_layout(
        xaxis=dict(title="Zeit (s)", range=[t[0], t[-1]], showgrid=True, dtick=1),
        yaxis=dict(
            range=[-spacing * 0.8, total_height + spacing * 0.3],
            tickvals=offsets,
            ticktext=[item[0] for item in derivs],
            showgrid=False, tickfont=dict(size=13),
        ),
        height=max(500, int(total_height / spacing) * 42 + 80),
        margin=dict(t=8, b=48, l=132, r=8),
        legend=dict(orientation="h", y=-0.06, x=0, font=dict(size=11)),
        )
    return fig


def ecg_figure(t, sig_mv, sensitivity_mv, lp_hz=None):
    """EKG-Plot. sensitivity_mv = sichtbarer ±-Bereich der y-Achse in mV."""
    sig_plot = sig_mv.copy()

    if lp_hz is not None:
        from scipy.signal import butter, filtfilt
        sfreq = 1.0 / (t[1] - t[0])
        nyq = sfreq / 2
        b, a = butter(4, min(lp_hz / nyq, 0.98), btype="low")
        padlen = 3 * max(len(a), len(b))
        if len(sig_plot) > padlen:
            sig_plot = filtfilt(b, a, sig_plot)

    baseline = np.median(sig_plot)
    sig_centered = sig_plot - baseline

    y_min, y_max = -sensitivity_mv, sensitivity_mv

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=t, y=sig_centered, mode="lines",
        line=dict(color="#c0392b", width=1.8),
        hovertemplate="%{y:.3f} mV<extra></extra>",
    ))
    fig.update_layout(
        xaxis=dict(
            title="Zeit (s)", range=[t[0], t[-1]],
            showgrid=True, gridcolor="#f5c6c6", gridwidth=0.8, dtick=0.2,
            minor=dict(showgrid=True, gridcolor="#fce8e8", gridwidth=0.5, dtick=0.04),
        ),
        yaxis=dict(
            title="Amplitude (mV)", range=[y_min, y_max],
            showgrid=True, gridcolor="#f5c6c6", gridwidth=0.8, dtick=sensitivity_mv / 4,
            zeroline=True, zerolinecolor="#999999", zerolinewidth=0.8,
        ),
        height=420,
        margin=dict(t=8, b=48, l=70, r=8),
        plot_bgcolor="#fff8f8",
        showlegend=False,
    )
    return fig


def inject_arrow_key_nav():
    """Pfeiltasten ← → navigieren durch Epochen (klickt die sichtbaren ◀/▶-Buttons)."""
    import streamlit.components.v1 as components
    components.html("""
    <script>
    const doc = window.parent.document;
    if (!doc.__arrowNavAttached) {
        doc.__arrowNavAttached = true;
        doc.addEventListener('keydown', function(e) {
            const tag = (e.target.tagName || '').toLowerCase();
            if (tag === 'input' || tag === 'textarea') return;
            if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
            const wantPrev = e.key === 'ArrowLeft';
            const symbol = wantPrev ? '◀' : '▶';
            const buttons = Array.from(doc.querySelectorAll('button'));
            const match = buttons.find(b =>
                b.innerText.trim() === symbol &&
                b.offsetParent !== null &&
                !b.disabled
            );
            if (match) { match.click(); e.preventDefault(); }
        });
    }
    </script>
    """, height=0, width=0)


def safe_slider(label, lo, hi, value=None, **kwargs):
    """st.slider, das bei **entartetem Bereich** (lo >= hi) nicht abstürzt.

    Streamlit verlangt zwingend min_value < max_value. Bei sehr kurzen Aufnahmen
    (z. B. eine 10-s-EDF → genau EINE Epoche; oder Fenster-Start-Slider mit
    max = dauer − 10 = 0) fallen Minimum und Maximum zusammen und Streamlit wirft
    `StreamlitAPIException: Slider min_value must be less than the max_value`.
    In dem Fall gibt es schlicht nichts zu navigieren → wir rendern keinen Slider
    und liefern den einzigen möglichen Wert zurück.
    """
    if hi <= lo:
        return lo
    if value is None:
        value = lo
    value = min(max(value, lo), hi)
    return st.slider(label, lo, hi, value, **kwargs)


def epoch_nav(edf, key, label="EEG", epoch_sec=None):
    """Rendert prominente Navigationszeile, gibt aktuellen Epochenindex zurück."""
    e_sec = epoch_sec or EPOCH_SEC
    n_eps = max(1, int(edf["duration_s"] // e_sec))
    if key not in st.session_state:
        st.session_state[key] = 0
    ep = min(st.session_state[key], n_eps - 1)
    st.session_state[key] = ep
    t_s = ep * e_sec
    t_e = t_s + e_sec
    pct = (ep + 1) / n_eps * 100

    st.markdown("""
<style>
div[data-testid="stHorizontalBlock"]:has(> div > div > button[kind="secondary"]) button[kind="secondary"] {
    min-height: 44px !important;
    font-size: 17px !important;
    font-weight: 700 !important;
}
</style>
""", unsafe_allow_html=True)

    c_first, c_prev, c_info, c_next, c_last = st.columns([1, 1, 8, 1, 1])
    with c_first:
        if st.button("⏮", key=f"{key}_first", disabled=(ep == 0),
                     help=tr("shared.first_epoch_tooltip"), use_container_width=True):
            st.session_state[key] = 0
            st.rerun()
    with c_prev:
        if st.button("◀", key=f"{key}_prev", disabled=(ep == 0),
                     help=tr("shared.prev_epoch_tooltip"), use_container_width=True):
            st.session_state[key] -= 1
            st.rerun()
    with c_info:
        st.markdown(
            f"<div style='text-align:center;padding:9px 0 6px;"
            f"background:#f4f6f9;border-radius:8px;border:1px solid #d0d6de'>"
            f"<span style='font-size:13px;color:#888'>{tr('shared.epoch_label')}</span>&ensp;"
            f"<b style='font-size:18px;color:#2c3e50'>{ep+1}</b>"
            f"<span style='font-size:13px;color:#888'>&nbsp;/&nbsp;{n_eps}</span>"
            f"&ensp;<span style='color:#ccc'>|</span>&ensp;"
            f"<b style='font-size:14px'>{t_s:.0f}s – {t_e:.0f}s</b>"
            f"&ensp;<span style='color:#ccc'>|</span>&ensp;"
            f"<span style='font-size:12px;color:#888'>{pct:.0f}% · {edf['duration_s']/60:.1f} {tr('shared.total_duration_suffix')}</span>"
            f"</div>", unsafe_allow_html=True)
    with c_next:
        if st.button("▶", key=f"{key}_next", disabled=(ep >= n_eps - 1),
                     help=tr("shared.next_epoch_tooltip"), use_container_width=True):
            st.session_state[key] += 1
            st.rerun()
    with c_last:
        if st.button("⏭", key=f"{key}_last", disabled=(ep >= n_eps - 1),
                     help=tr("shared.last_epoch_tooltip"), use_container_width=True):
            st.session_state[key] = n_eps - 1
            st.rerun()

    new_ep = safe_slider(tr("shared.epoch_select_label", label=label), 1, n_eps, ep + 1,
                         key=f"{key}_slider_{e_sec}", label_visibility="collapsed")
    if new_ep - 1 != ep:
        st.session_state[key] = new_ep - 1
        st.rerun()

    return st.session_state[key]


#: Session-State-Schlüssel, die aus dem INHALT der geladenen Datei abgeleitet sind und beim
#: Dateiwechsel deshalb ungültig werden. Ohne diese Liste überlebten Ergebnisse der vorherigen
#: Datei den Wechsel — der Report zeigte dann Werte der alten Aufnahme unter dem Namen der
#: neuen (User-Fund 2026-08-13). Das ist die gefährliche Fehlerklasse dieses Projekts:
#: nichts stürzt ab, die Zahlen sehen plausibel aus, und nur der Zufall deckt es auf.
#:
#: NICHT enthalten sind bewusst:
#:   * **Einstellungen** — Artefakt-Parameter (`art_*`), Fensterwahl, Rechenintensiv-Schalter.
#:     Sie beschreiben, WIE gerechnet wird, nicht WAS gemessen wurde, und gelten weiter.
#:     Sie hängen ausserdem an Widgets; sie zu löschen, während das Widget gerendert wird,
#:     quittiert Streamlit mit einem Fehler.
#:   * **Sitzungsebene** — Anmeldung, Sprache, Upload-Token, der Pfad selbst.
#:   * `phi_validated` / `phi_has_patient_data` — werden an JEDEM Einstiegspunkt in
#:     views/file_patient.py ausdrücklich gesetzt (geprüft 2026-08-13); ein Löschen hier
#:     würde die Freigabe nur verzögert wiederherstellen, nicht sicherer machen.
#:
#: Neue Schlüssel gehören geprüft: `tools/check_session_state.py` erzwingt eine Entscheidung.
ABGELEITETE_KEYS = (
    # Rechenergebnisse
    "_edf_cache_meta", "hrv_summary", "hrv_summary_report", "eeg_summary",
    # fertig gebaute Report-Dateien — gehören zur Datei, aus der sie entstanden sind
    "hrv_export", "report_export", "visual_export", "art_export",
    # manuelle Korrekturen — beziehen sich auf die Kanäle GENAU DIESER Aufnahme
    "channel_overrides", "artifact_overrides",
    # Positionen in der Aufnahme (eine Epoche aus Datei A bedeutet in Datei B nichts)
    "ecg_sens_idx", "ep_ecg", "rhythm_win_idx", "artifact_screen_idx", "_art_last_evt",
    # Patientendaten — gehören zur Aufnahme, nicht zur Sitzung. Sie fliessen in die
    # Normwert-Einordnung ein (Hansen-Perzentile, pädiatrische Grenzen); das Alter des
    # vorherigen Patienten still weiterzuverwenden wäre der schlimmste Fall dieses Bugs.
    "patient_age", "patient_age_label", "patient_sex", "patient_data_from_header",
    "pediatric_age_group", "is_pediatric",
)

#: Merker, für welchen Pfad der abgeleitete Zustand gilt.
_ZUSTAND_FUER = "_state_for_path"


def invalidate_file_state(pfad: str) -> int:
    """Verwirft abgeleiteten Zustand, sobald eine ANDERE Datei aktiv ist.

    Bewusst als Wächter am gemeinsamen Zugriffspunkt statt als Aufräumen an jeder Ladestelle:
    Ladestellen kommen dazu (Upload, PHI-Freigabe, Demodatei), und die eine, die man vergisst,
    fällt nicht auf. Gibt die Zahl der verworfenen Schlüssel zurück (für Tests).
    """
    if st.session_state.get(_ZUSTAND_FUER) == pfad:
        return 0
    n = sum(st.session_state.pop(k, _ZUSTAND_FUER) is not _ZUSTAND_FUER
            for k in ABGELEITETE_KEYS)
    st.session_state[_ZUSTAND_FUER] = pfad
    return n


def get_edf_path():
    """Liest den aktuell gewählten EDF-Pfad aus dem Session-State (gesetzt auf 'Datei & Patient').
    Liegt unter dem Plain-Key 'edf_path' (nicht 'edf_path_widget') — siehe Kommentar in
    views/file_patient.py zur Widget-State-GC-Problematik bei Multi-Page-Apps.

    Verwirft nebenbei den abgeleiteten Zustand der vorherigen Datei; siehe
    `invalidate_file_state`."""
    pfad = st.session_state.get("edf_path", "")
    invalidate_file_state(pfad)
    return pfad


def apply_channel_overrides(edf: dict) -> dict:
    """Wendet manuelle Kanal-Typ-Korrekturen aus dem Session-State an.

    Overrides werden in st.session_state["channel_overrides"] gespeichert als
    dict[channel_name → new_type_string].  Die Funktion gibt eine modifizierte
    Kopie des edf-Dicts zurück (shallow copy, nur betroffene Listen neu gebaut).
    """
    overrides: dict = st.session_state.get("channel_overrides", {})
    if not overrides:
        return edf

    from core.channel_classifier import (ChannelResult, ECG, EEG, EOG, EMG,
                                          make_short_name)

    edf = dict(edf)
    classifications = dict(edf.get("channel_classifications", {}))

    for ch, new_type in overrides.items():
        if ch in classifications:
            old = classifications[ch]
            classifications[ch] = ChannelResult(
                channel_type=new_type,
                confidence=100.0,
                reasons=[tr("shared.channel_override_reason",
                           old=old.channel_type, new=new_type)],
                features=old.features,
            )

    edf["channel_classifications"] = classifications

    # Derived channel lists
    edf["ecg_channels"] = [ch for ch, r in classifications.items() if r.channel_type == ECG]
    edf["eog_channels"] = [ch for ch, r in classifications.items() if r.channel_type == EOG]
    edf["emg_channels"] = [ch for ch, r in classifications.items() if r.channel_type == EMG]

    # Rebuild eeg_map from overridden classifications
    ch_idx = edf["ch_idx"]
    eeg_map: dict = {}
    for ch, r in classifications.items():
        if r.channel_type == EEG:
            short = make_short_name(ch)
            eeg_map[short] = ch_idx[ch]
    if eeg_map:
        edf["eeg_map"] = eeg_map

    # Add bandpass-filtered ECG for newly added ECG channels — mit derselben Polaritäts-
    # korrektur wie im Erstlade-Pfad (load_and_prepare), sonst würde ein manuell nachträglich
    # als EKG markierter Kanal die Kurve invertiert zeigen.
    from analysis.ecg import detect_polarity_flip
    ecg_filtered = dict(edf.get("ecg_filtered", {}))
    new_ecg = set(edf["ecg_channels"]) - set(ecg_filtered.keys())
    if new_ecg:
        from scipy.signal import butter, filtfilt as _filtfilt
        data = edf["data"]
        sfreq = edf["sfreq"]
        nyq = sfreq / 2
        b, a = butter(4, [0.5 / nyq, min(40.0 / nyq, 0.99)], btype="band")
        for ch in new_ecg:
            idx = ch_idx.get(ch)
            if idx is not None:
                sig = data[idx].copy().astype(float)
                sig -= sig.mean()
                if detect_polarity_flip(sig, sfreq):
                    sig = -sig
                ecg_filtered[ch] = _filtfilt(b, a, sig)
    edf["ecg_filtered"] = ecg_filtered

    return edf


def get_edf_or_stop():
    """Lädt die EDF-Datei oder stoppt die Seite mit Hinweis, falls keine gültige Datei gewählt ist."""
    edf_path = get_edf_path()
    if not edf_path or not os.path.exists(edf_path):
        st.info(tr("shared.please_select_file"), icon=":material/folder_open:")
        st.stop()
    if not st.session_state.get("phi_validated"):
        st.error(tr("shared.phi_not_validated"), icon=":material/block:")
        st.stop()
    with st.spinner(tr("shared.loading_edf")):
        edf = load_and_prepare(edf_path)
    edf = apply_channel_overrides(edf)
    return edf, edf_path


def get_patient_info():
    """Liest Patientenalter/-geschlecht aus dem Session-State (gesetzt auf 'Datei & Patient')."""
    # STANDARD_ALTER statt einer hier eingesetzten Zahl: bis 2026-08-13 stand hier 50,
    # während views/file_patient.py mit 52 vorbelegte — je nachdem, ob die Seite „Datei &
    # Patient" schon besucht war, ging dieselbe Aufnahme mit unterschiedlichem Alter in die
    # Normwert-Einordnung.
    age = st.session_state.get("patient_age", STANDARD_ALTER)
    sex = st.session_state.get("patient_sex", "X")
    return age, sex
