"""EEG — Aperiodische 1/f-Komponente (schlanke specparam-Analyse)."""

import numpy as np
import streamlit as st
import plotly.graph_objects as go

from core.i18n import tr
from core.shared import load_and_prepare, apply_channel_overrides, section_header, get_patient_info, kpi_tile
from analysis.aperiodic import welch_psd, fit_aperiodic, corrected_peak
from views.eeg_spectrum import _highpass, _alpha_band, BANDS

FIT_LO, FIT_HI = 1.0, 40.0


@st.cache_data(show_spinner="Berechne Exponenten je Kanal…")
def _all_channel_exponents(edf_path, fmin, fmax, channels=None, overrides_key=""):
    """Aperiodischer Exponent + R² für die angegebenen (oder alle) EEG-Kanäle.

    `channels`: optionale Teilmenge (z. B. nur empfohlene Kanäle) — vermeidet
    unnötige Fits für Kanäle, die in der Übersicht ohnehin nicht gezeigt werden.
    `overrides_key`: nur für den Cache-Key (Bugfix 2026-08-09, siehe eeg_spectrum.py::
    _compute_par für die volle Begründung — manuelle Kanal-Typ-Korrekturen wurden hier
    vorher ignoriert)."""
    import mne
    edf = apply_channel_overrides(load_and_prepare(edf_path))
    fs = edf["sfreq"]
    eeg_map = edf["eeg_map"]
    if channels is not None:
        eeg_map = {c: idx for c, idx in eeg_map.items() if c in channels}
    raw = mne.io.read_raw_edf(edf_path, preload=True, encoding="latin1", verbose=False)
    out = {}
    for c, idx in eeg_map.items():
        sig = _highpass(raw[idx, :][0][0] * 1e6, fs, 1.0)
        fr, ps = welch_psd(sig, fs, fmax + 5)
        if fr is None:
            continue
        r = fit_aperiodic(fr, ps, fmin, fmax)
        if r is not None:
            out[c] = (r["exponent"], r["r2"])
    return out


def _age_expected_band(age):
    """Orientierender Erwartungsbereich des Exponenten nach Alterstrend.

    Der aperiodische Exponent flacht mit dem Alter ab (Voytek et al. 2015).
    Die Bänder sind BEWUSST breit und rein orientierend — es gibt (noch) keine
    für diese Methode/Montage validierte Normdatenbank. Sie zeigen die Richtung
    des Alterstrends, keinen diagnostischen Cutoff.
    """
    try:
        a = float(age)
    except (TypeError, ValueError):
        return (1.5, 3.0, "Erwachsene (orientierend)")
    if a < 30:
        return (1.8, 3.2, f"~{int(a)} J. — jünger: tendenziell steiler")
    if a < 60:
        return (1.6, 3.0, f"~{int(a)} J. — mittleres Alter")
    return (1.4, 2.8, f"~{int(a)} J. — älter: tendenziell flacher")


def _ei_gauge_fig(exp: float, age):
    """Horizontale E/I-Achse: Exponent als Proxy für Exzitation↔Inhibition.

    Gao, Peterson & Voytek (2017): flacher Exponent (niedrig) = relativ mehr
    Exzitation, steiler (hoch) = relativ mehr Inhibition. Also E/I ∝ 1/Exponent.
    """
    x0, x1 = 0.5, 3.5
    lo, hi, band_lbl = _age_expected_band(age)
    fig = go.Figure()
    # Farbverlauf-Zonen: links (Exzitation) rötlich, rechts (Inhibition) bläulich
    fig.add_vrect(x0=x0, x1=(x0 + x1) / 2, fillcolor="#c0392b", opacity=0.06, line_width=0)
    fig.add_vrect(x0=(x0 + x1) / 2, x1=x1, fillcolor="#2471a3", opacity=0.06, line_width=0)
    # Altersorientierter Erwartungsbereich
    fig.add_vrect(x0=lo, x1=hi, fillcolor="#27ae60", opacity=0.16, line_width=0,
                  annotation_text="altersorientierter Bereich", annotation_position="top",
                  annotation_font_size=9, annotation_font_color="#1e8449")
    # Messwert
    fig.add_trace(go.Scatter(
        x=[exp], y=[0], mode="markers+text",
        marker=dict(symbol="diamond", size=22, color="#8e44ad",
                    line=dict(width=2, color="white")),
        text=[f"{exp:.2f}"], textposition="top center",
        textfont=dict(size=13, color="#8e44ad"),
        hovertemplate=f"Exponent {exp:.2f}<extra></extra>",
    ))
    fig.add_annotation(x=x0, y=-0.55, xref="x", yref="y", showarrow=False, xanchor="left",
                       text="◀ mehr Exzitation (flach)", font=dict(size=11, color="#c0392b"))
    fig.add_annotation(x=x1, y=-0.55, xref="x", yref="y", showarrow=False, xanchor="right",
                       text="mehr Inhibition (steil) ▶", font=dict(size=11, color="#2471a3"))
    fig.update_layout(
        xaxis=dict(range=[x0, x1], title=None, tickfont=dict(size=10),
                   showgrid=False, zeroline=False),
        yaxis=dict(range=[-0.9, 0.9], visible=False),
        height=120, margin=dict(t=22, b=6, l=10, r=10),
        plot_bgcolor="white", showlegend=False,
    )
    return fig, band_lbl


def _exponent_hint(exp: float, age) -> str:
    """Orientierende Einordnung des Exponenten (keine etablierte klinische Norm)."""
    try:
        a = float(age)
    except (TypeError, ValueError):
        a = None
    base = ""
    if exp < 0.8:
        base = "flach — relativ mehr Exzitation / höhere Vigilanz"
    elif exp > 2.2:
        base = "steil — relativ mehr Inhibition (Schläfrigkeit, Sedierung, Schlaf)"
    else:
        base = "im typischen Ruhebereich (wach, Augen zu)"
    if a is not None and a >= 60:
        base += " · im Alter physiologisch tendenziell flacher (Voytek 2015)"
    return base


def render():
    st.title(":material/waves: " + tr("aperiodic.title"))

    # ── Biomarker-Headline (Biologie zuerst) ──────────────────────────────────
    st.markdown(
        "<div style='background:linear-gradient(90deg,#8e44ad14,transparent);"
        "border-left:5px solid #8e44ad;border-radius:8px;padding:14px 18px;margin:4px 0 4px 0'>"
        "<div style='font-size:16px;font-weight:800;color:#6c3483'>Der aperiodische Exponent ≈ "
        "Erregungs-/Hemmungs-Balance (E/I) des Kortex</div>"
        "<div style='font-size:13px;color:#333;margin-top:5px'>"
        "Er ist ein <b>eigenständiger Biomarker für Arousal, Vigilanz und kortikale Aktivierung</b> "
        "— unabhängig von jedem einzelnen Rhythmus. <b>Flacher</b> = relativ mehr <b>Exzitation</b> "
        "(wacher/aktivierter), <b>steiler</b> = relativ mehr <b>Inhibition</b> (schläfrig, sediert, "
        "tiefe Bewusstseinsstörung).<br>"
        "<b>Anwendungen:</b> Anästhesietiefe · Bewusstseinsstörungen (DoC) · Schlaf/Vigilanz · "
        "Alter (flacht mit dem Alter ab) · Kognition.</div></div>",
        unsafe_allow_html=True,
    )

    # ── Wie funktioniert die Trennung? (Kurzfassung) ──────────────────────────
    with st.expander(tr("aperiodic.how_measured")):
        st.markdown(
            "Ein EEG-Spektrum ist die **Summe** aus (1) dem **1/f-Hintergrund** (aperiodisch, eine "
            "schräg abfallende Kurve *ohne* echten Rhythmus — ihre **Steilheit** ist der Exponent) "
            "und (2) den **echten Rhythmen** (Alpha, Beta … = Gipfel, die *über* dem Hintergrund "
            "herausragen). Diese Seite **trennt beides**: 1/f-Gerade + Exponent als Marker, und das "
            "**untergrund-bereinigte** Spektrum, in dem der echte Alpha-Gipfel unabhängig vom "
            "Hintergrund ablesbar ist.\n\n"
            "**Warum wichtig?** Scheinbare *Alpha-sinkt / Beta-steigt*-Befunde sind oft nur eine "
            "Verschiebung des Hintergrunds — erst die Trennung zeigt, was *wirklich* ein Rhythmus "
            "ist. Methodik: robuster 1/f-Geradenfit im log-log-Raum (1–40 & 1–20 Hz), ohne Knee. "
            "*Forschungsmarker — orientierend, nicht für Einzelfall-Entscheidungen.*")

    edf_path = st.session_state.get("edf_path", "")
    if not edf_path:
        st.info(tr("aperiodic.load_file_first"), icon=":material/folder_open:")
        return
    if not st.session_state.get("phi_validated"):
        st.error(tr("shared.phi_not_validated"), icon=":material/block:")
        return

    edf = apply_channel_overrides(load_and_prepare(edf_path))
    fs = edf["sfreq"]
    eeg_map = edf["eeg_map"]
    if not eeg_map:
        st.warning(tr("aperiodic.no_eeg"))
        return

    age, _sex = get_patient_info()
    a_lo, a_hi = _alpha_band(age)

    import mne
    raw = mne.io.read_raw_edf(edf_path, preload=True, encoding="latin1", verbose=False)

    def _get(ch):
        data, _ = raw[eeg_map[ch], :]
        return _highpass(data[0] * 1e6, fs, cutoff=1.0)

    all_eeg = sorted(eeg_map.keys())
    _RECOMMENDED = ["O1", "O2", "Pz", "P3", "P4"]     # klarster Alpha, wenig Artefakt
    _ARTIFACT_PRONE = ["Fp1", "Fp2", "F7", "F8"]      # EOG/EMG → Exponent verfälscht
    default_ch = next((c for c in ["O1", "O2", "Pz", "Cz"] if c in all_eeg), all_eeg[0])

    def _ch_fmt(c):
        if c in _RECOMMENDED:
            return f"⭐ {c}  (empfohlen)"
        if c in _ARTIFACT_PRONE:
            return f"⚠ {c}  (artefaktanfällig)"
        return c

    st.markdown("---")
    c1, c2 = st.columns([2, 3])
    with c1:
        ch = st.selectbox(tr("aperiodic.channel"), all_eeg, index=all_eeg.index(default_ch),
                          key="aper_channel", format_func=_ch_fmt)
    with c2:
        st.markdown(
            f"<div style='padding:8px 0 4px;font-size:13px;color:#555'>"
            f"Analyse über die <b>Gesamtaufnahme</b> · Alpha-Suchband "
            f"<b>{a_lo:.0f}–{a_hi:.0f} Hz</b> (altersadaptiv)</div>",
            unsafe_allow_html=True,
        )

    with st.expander(tr("aperiodic.which_channel"), icon=":material/info:"):
        st.markdown(
            "- **⭐ Posterior (O1, O2, Pz, P3, P4)** — beste Wahl: klarster "
            "Alpha-Gipfel und sauberes Signal → der 1/f-Fit ist am zuverlässigsten.\n"
            "- **Zentral/Mittellinie (Cz, C3, C4)** — robuste Alternative, wenig Artefakt.\n"
            "- **⚠ Frontopolar/temporal anterior (Fp1, Fp2, F7, F8)** — meiden: "
            "Augenbewegungen (EOG) und Muskelaktivität (EMG) heben die hohen Frequenzen "
            "an und machen den Exponenten künstlich **flacher** (falsch niedrig).\n"
            "- **Faustregel:** einen Kanal wählen, dessen Exponent nahe am Median der "
            "Kanal-Übersicht (unten) liegt — Ausreißer sind meist artefaktbedingt."
        )

    sig = _get(ch)
    freqs, psd = welch_psd(sig, fs, fmax=FIT_HI + 5)
    if freqs is None:
        st.warning(tr("aperiodic.signal_too_short"))
        return
    res = fit_aperiodic(freqs, psd, fmin=FIT_LO, fmax=FIT_HI)
    if res is None:
        st.warning(tr("aperiodic.fit_impossible"))
        return
    # Zusätzlicher Fit im 1–20-Hz-Fenster (Maschke 2025: diagnostisch/prognostisch stärker)
    res20 = fit_aperiodic(freqs, psd, fmin=FIT_LO, fmax=20.0)
    exp20 = res20["exponent"] if res20 else float("nan")

    exp = res["exponent"]
    off = res["offset"]
    r2 = res["r2"]
    apf_corr = corrected_peak(res, a_lo, a_hi)

    # ── Kennzahlen ────────────────────────────────────────────────────────────
    section_header(tr("aperiodic.metrics"), f"Kanal {ch} · Fit 1–40 & 1–20 Hz")
    _r2_zone = "normal" if r2 >= 0.95 else ("grenzwertig" if r2 >= 0.90 else "pathologisch")
    _r2_col = {"normal": "#27ae60", "grenzwertig": "#e67e22", "pathologisch": "#c0392b"}[_r2_zone]
    _r2_txt = {"normal": "guter Fit", "grenzwertig": "mäßiger Fit", "pathologisch": "schwacher Fit"}[_r2_zone]

    # Phase 5 GUI-Redesign (siehe [[project_edf_ui_redesign]]): vorher eigenständige, dritte
    # Kachel-Variante neben eeg_spectrum.py/ecg_hrv.py — delegiert jetzt an die gemeinsame
    # kpi_tile()-Komponente (core/shared.py), Aufrufstellen unverändert.
    def _tile(col, label, value, sub, color="#2471a3"):
        col.markdown(kpi_tile(label, value, sub, border_color=color), unsafe_allow_html=True)

    k1, k2, k3, k4, k5 = st.columns(5)
    _tile(k1, "EXPONENT (1–40 Hz)", f"{exp:.2f}", "1/f-Abfall", "#8e44ad")
    _tile(k2, "EXPONENT (1–20 Hz)", f"{exp20:.2f}" if exp20 == exp20 else "—",
          "diagnostisch stärker", "#7d3c98")
    _tile(k3, "OFFSET", f"{off:.2f}", "log₁₀ Power @ 1 Hz", "#2471a3")
    _tile(k4, "FIT-GÜTE R²", f"{r2:.3f}", _r2_txt, _r2_col)
    _tile(k5, "ALPHA-PEAK (korrigiert)",
          f"{apf_corr:.1f} Hz" if apf_corr == apf_corr else "—",
          "Gipfel über Untergrund", "#27ae60")

    st.caption(f"**Exponent {exp:.2f}** (1–40 Hz) · **{exp20:.2f}** (1–20 Hz) — "
               f"{_exponent_hint(exp, age)}. Das **1–20-Hz-Fenster** ist bei DoC-Patienten "
               f"diagnostisch/prognostisch stärker (Maschke 2025). "
               f"*Orientierend — Forschungsmarker, keine breit etablierte klinische Norm.*")

    # ── E/I-Achse (altersbezogen) ─────────────────────────────────────────────
    _ei_fig, _band_lbl = _ei_gauge_fig(exp, age)
    st.markdown("**Exzitation / Inhibition (E/I-Index)**")
    st.plotly_chart(_ei_fig, use_container_width=True, key="aper_ei")
    st.caption(
        f"Der Exponent ist ein Proxy für die **E/I-Balance** (Gao/Peterson/Voytek 2017): "
        f"flacher = mehr Exzitation, steiler = mehr Inhibition. Grüner Bereich = "
        f"**{_band_lbl}**. Der Exponent flacht mit dem Alter ab (Voytek 2015) — der "
        f"Erwartungsbereich verschiebt sich entsprechend nach links. "
        f"*Bänder breit & orientierend, keine validierte Norm für diese Methode.*"
    )
    if _r2_zone != "normal":
        st.warning(
            f"Fit-Güte R² = {r2:.3f} — der 1/f-Untergrund ist in diesem Kanal nur "
            f"{_r2_txt.lower()} beschreibbar (Artefakte, Krümmung/Knee, breite Gipfel). "
            f"Exponent/Offset mit Vorsicht interpretieren."
        )

    # ── Plot 1: Zerlegung im log-log-Raum ─────────────────────────────────────
    section_header(tr("aperiodic.spectral_decomposition"), tr("aperiodic.spectral_decomposition_sub"))
    f = res["freqs"]
    fig1 = go.Figure()
    # Band-Hintergründe. WICHTIG: Plotly transformiert bei Annotations (anders als bei
    # Kurven-Datenpunkten) den x-Wert auf log-Achsen NICHT automatisch — weder add_vrect()s
    # annotation_position-Kurzform noch add_annotation(xref="x", x=<roher Hz-Wert>)
    # funktionieren hier (empirisch verifiziert 2026-08-04: beide platzieren alle vier
    # Bandnamen falsch/außerhalb des sichtbaren Bereichs). Fix: eigene Log-Bruchteils-
    # berechnung + xref="paper" — umgeht die fehlerhafte interne Log-Transformation komplett.
    _log_lo, _log_hi = np.log10(FIT_LO), np.log10(FIT_HI)
    for bname, (lo, hi), bcol in BANDS:
        fig1.add_vrect(x0=lo, x1=hi, fillcolor=bcol, opacity=0.06, line_width=0)
        _frac = (np.log10(lo) - _log_lo) / (_log_hi - _log_lo)
        fig1.add_annotation(x=float(_frac), y=1.0, xref="paper", yref="paper",
                            text=bname, showarrow=False,
                            xanchor="left", yanchor="top",
                            font=dict(size=9, color=bcol))
    fig1.add_trace(go.Scatter(
        x=f, y=res["psd"], mode="lines", name="Originalspektrum",
        line=dict(color="#7f8c8d", width=2),
        hovertemplate="%{y:.3f} µV²/Hz @ %{x:.1f} Hz<extra></extra>"))
    fig1.add_trace(go.Scatter(
        x=f, y=res["aper_psd"], mode="lines", name="Aperiodischer Fit (1/f)",
        line=dict(color="#c0392b", width=2.4, dash="dash"),
        hovertemplate="1/f-Untergrund: %{y:.3f} @ %{x:.1f} Hz<extra></extra>"))
    fig1.update_layout(
        # Explizite Range in log10-Einheiten — sonst zieht Plotly die Log-Achse
        # über 40 Hz hinaus auf und die Daten (1–40 Hz) kleben gestaucht am Rand.
        xaxis=dict(title="Frequenz (Hz)", type="log",
                   range=[float(np.log10(FIT_LO)), float(np.log10(FIT_HI))],
                   tickmode="array",
                   tickvals=[1, 2, 3, 5, 8, 13, 20, 30, 40],
                   ticktext=["1", "2", "3", "5", "8", "13", "20", "30", "40"]),
        yaxis=dict(title="PSD (µV²/Hz)", type="log"),
        height=360, margin=dict(t=26, b=44, l=65, r=12),
        legend=dict(orientation="h", yanchor="bottom", y=1.03, x=0, font=dict(size=11)),
    )
    st.plotly_chart(fig1, use_container_width=True, key="aper_decomp")
    st.caption(
        "Die **rote Gerade** ist der aperiodische Untergrund. Wo das graue "
        "Originalspektrum darüber liegt, sitzt ein **echter Rhythmus** (z. B. Alpha)."
    )

    # ── Plot 2: Untergrund-bereinigtes Spektrum (Verhältnis) ──────────────────
    section_header(tr("aperiodic.corrected_spectrum"), tr("aperiodic.corrected_spectrum_sub"))
    ratio = res["ratio"]
    fig2 = go.Figure()
    for bname, (lo, hi), bcol in BANDS:
        fig2.add_vrect(x0=lo, x1=hi, fillcolor=bcol, opacity=0.08, line_width=0,
                       annotation_text=bname, annotation_position="top left",
                       annotation_font_size=9, annotation_font_color=bcol)
    fig2.add_hline(y=1.0, line_color="#c0392b", line_dash="dash", line_width=1.2)
    fig2.add_trace(go.Scatter(
        x=f, y=ratio, mode="lines", line=dict(color="#8e44ad", width=2),
        fill="tozeroy", fillcolor="rgba(142,68,173,0.10)",
        hovertemplate="%{y:.2f}× Untergrund @ %{x:.1f} Hz<extra></extra>"))
    if apf_corr == apf_corr:
        _pv = float(ratio[(np.abs(f - apf_corr)).argmin()])
        fig2.add_vline(x=apf_corr, line_color="#27ae60", line_width=1.6, line_dash="dot")
        fig2.add_annotation(x=apf_corr, y=_pv, text=f"α {apf_corr:.1f} Hz",
                            showarrow=True, arrowhead=2, arrowcolor="#27ae60",
                            font=dict(size=11, color="#27ae60"), yanchor="bottom")
    fig2.update_layout(
        xaxis=dict(title="Frequenz (Hz)", range=[FIT_LO, FIT_HI]),
        yaxis=dict(title="PSD / Untergrund (×)", rangemode="tozero"),
        height=280, margin=dict(t=24, b=44, l=65, r=12),
        showlegend=False,
    )
    st.plotly_chart(fig2, use_container_width=True, key="aper_flat")
    st.caption(
        "Baseline **1,0** = reiner Untergrund. Werte **> 1** sind oszillatorische "
        "Gipfel. Der Alpha-Gipfel ist hier unabhängig vom 1/f-Abfall ablesbar."
    )

    # ── Kanal-Übersicht ───────────────────────────────────────────────────────
    section_header(tr("aperiodic.exponent_per_channel"), tr("aperiodic.exponent_per_channel_sub"))
    _overview_chs = list(dict.fromkeys(_RECOMMENDED + [ch]))  # empfohlene + aktiver Kanal, keine Dubletten
    _exps = _all_channel_exponents(edf_path, FIT_LO, FIT_HI, channels=_overview_chs,
                                   overrides_key=str(sorted(st.session_state.get("channel_overrides", {}).items())))
    if len(_exps) >= 2:
        _chs = sorted(_exps.keys())
        _vals = [_exps[c][0] for c in _chs]
        _r2s = [_exps[c][1] for c in _chs]
        _median = float(np.median(_vals))
        _bar_cols = []
        for c, rr in zip(_chs, _r2s):
            if c == ch:
                _bar_cols.append("#8e44ad")                    # aktiver Kanal
            elif rr < 0.90:
                _bar_cols.append("#d5b8e0")                    # schwacher Fit → blass
            else:
                _bar_cols.append("#95a5a6")
        fig3 = go.Figure()
        fig3.add_trace(go.Bar(
            x=_chs, y=_vals, marker_color=_bar_cols,
            customdata=np.array(_r2s),
            hovertemplate="%{x}: Exponent %{y:.2f} · R²=%{customdata:.2f}<extra></extra>",
        ))
        fig3.add_hline(y=_median, line_color="#e67e22", line_dash="dash", line_width=1.5,
                       annotation_text=f"Median {_median:.2f}", annotation_position="right",
                       annotation_font_size=10, annotation_font_color="#e67e22")
        fig3.update_layout(
            xaxis=dict(title=None, tickfont=dict(size=10)),
            yaxis=dict(title="Exponent", rangemode="tozero"),
            height=240, margin=dict(t=8, b=40, l=55, r=60),
            showlegend=False,
        )
        st.plotly_chart(fig3, use_container_width=True, key="aper_perchannel")
        st.caption(
            f"Aktiver Kanal **{ch}** (lila) im Vergleich zum Median der empfohlenen Kanäle "
            f"(**{_median:.2f}**, orange). Beschränkt auf ⭐ empfohlene Kanäle + aktiven Kanal — "
            f"nicht alle EEG-Kanäle. Stark abweichende, **blasse** Balken haben "
            f"schwache Fit-Güte (R² < 0,90) — meist artefaktbedingt. Ein Kanal nahe "
            f"dem Median ist für die E/I-Einordnung am repräsentativsten."
        )

    # ── Appendix ──────────────────────────────────────────────────────────────
    st.markdown("---")
    with st.expander(tr("aperiodic.methodology"), icon=":material/menu_book:", expanded=False):
        st.markdown(
            """
### Die zwei Anteile des EEG-Spektrums

Jedes EEG-Leistungsspektrum ist die **Summe** aus:

1. **Aperiodischer Anteil** — der „Hintergrund" ohne echte Rhythmen. Im
   log-log-Diagramm eine **fallende Gerade**, beschrieben durch:
   - **Offset** — Gesamthöhe der Kurve (Gesamtleistung).
   - **Exponent** — Steilheit des 1/f-Abfalls.
2. **Periodischer Anteil** — die echten Oszillationen (Alpha, Beta …), die als
   **Gipfel über** dem Hintergrund herausragen.

> Was wir „Alpha-Power" nennen, ist immer **Gipfel + Hintergrund**. Erst nach
> Abzug des Hintergrunds sieht man den echten Rhythmus — und der Hintergrund
> selbst ist ein eigener, klinisch bedeutsamer Marker.

### Evidenz-Einordnung

⚠️ **Evidenz: ★★★☆☆** — mechanistisch gut begründet (E/I-Balance) und mit rasch
wachsender Forschungsdatenlage; **robuster** Messwert aus der PSD. Aber: **noch keine
breit validierte klinische Normdatenbank** für diese Methode/Montage, stark
zustandsabhängig (Vigilanz, Augen auf/zu). Daher Forschungs-/Zusatzmarker, keine
alleinige Entscheidungsgrundlage.

### Klinische Bedeutung des Exponenten

- **Exzitation/Inhibition:** flacher = relativ mehr Exzitation, steiler = mehr
  Inhibition (Gao, Peterson & Voytek 2017).
- **Alter:** der Exponent **flacht mit dem Alter ab** (Voytek et al. 2015).
- **Vigilanz/Sedierung:** der Exponent **steilt** in Schlaf und unter Anästhesie
  (Lendner et al. 2020; Colombo et al. 2019).
- **Methodische Warnung:** scheinbare Bandpower-Unterschiede sind oft nur
  Verschiebungen der aperiodischen Kurve — nicht echte Rhythmusänderungen
  (Donoghue et al. 2020).

### Unsere Methode (schlank, ohne Knee)

PSD (Welch) → log-log → **robuster iterativer Geradenfit**: Punkte, die
deutlich über der Geraden liegen (= Gipfel), werden verworfen und neu gefittet
(„sigma-clipping"), damit die Gipfel den Untergrund nicht nach oben ziehen.
Ausgabe: Offset, Exponent, Fit-Güte R² und das untergrund-bereinigte Spektrum.

**Zwei Fit-Fenster:** **1–40 Hz** (breite Sicht) und **1–20 Hz**. Letzteres ist bei
Bewusstseinsstörungen (DoC) diagnostisch/prognostisch aussagekräftiger (Maschke et al.
2025) — u. a. weil hochfrequente Muskelartefakte den Exponenten im breiten Fenster
verfälschen können.

**Methoden-Hinweis:** Wir nutzen einen **robusten Sigma-Clip-Geradenfit**, nicht die
volle FOOOF/specparam-Gipfel-Parametrisierung. Der aperiodische Exponent ist derselbe
Kennwert; FOOOF-Hyperparameter (min_peak_height etc.) haben hier daher **kein** direktes
Pendant. Volle FOOOF-Gipfelanalyse ist eine mögliche Ausbaustufe.

**Grenzen:** Forschungsmarker mit wachsender, aber noch nicht flächig
etablierter klinischer Normdatenbank. Zustandsabhängig (Augen auf/zu, Vigilanz).
Kein Knee-Term — bei stark gekrümmten Spektren sinkt die Fit-Güte (R² beachten).

### Quellen
- Donoghue T. et al. (2020). Parameterizing neural power spectra into periodic
  and aperiodic components. *Nature Neuroscience* 23:1655–1665.
- Gao R., Peterson E.J., Voytek B. (2017). Inferring synaptic excitation/inhibition
  balance from field potentials. *NeuroImage* 158:70–78.
- Voytek B. et al. (2015). Age-related changes in 1/f neural electrophysiological
  noise. *Journal of Neuroscience* 35:13257–13265.
- He B.J. (2014). Scale-free brain activity. *Trends in Cognitive Sciences* 18:480–487.
"""
        )
    st.caption(
        "Aperiodische Parameter sind ein Forschungsmarker — orientierend, nicht als "
        "alleinige klinische Entscheidungsgrundlage. Zustandsabhängigkeit beachten."
    )
