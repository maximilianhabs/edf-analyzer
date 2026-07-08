"""EEG — Aperiodische 1/f-Komponente (schlanke specparam-Analyse)."""

import numpy as np
import streamlit as st
import plotly.graph_objects as go

from core.shared import load_and_prepare, section_header, get_patient_info
from analysis.aperiodic import welch_psd, fit_aperiodic, corrected_peak
from views.eeg_spectrum import _highpass, _alpha_band, BANDS

FIT_LO, FIT_HI = 1.0, 40.0


@st.cache_data(show_spinner="Berechne Exponenten je Kanal…")
def _all_channel_exponents(edf_path, fmin, fmax):
    """Aperiodischer Exponent + R² für jeden EEG-Kanal (für die Übersicht)."""
    import mne
    edf = load_and_prepare(edf_path)
    fs = edf["sfreq"]
    eeg_map = edf["eeg_map"]
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
    st.title("🌀 Aperiodische Komponente (1/f)")
    st.caption(
        "Trennt das Spektrum in den aperiodischen 1/f-Untergrund (Offset + Exponent) "
        "und die echten oszillatorischen Gipfel. Fit-Bereich 1–40 Hz, ohne Knee-Term."
    )

    edf_path = st.session_state.get("edf_path", "")
    if not edf_path:
        st.info("👆 Bitte zuerst auf **Datei & Patient** eine EDF-Datei laden.")
        return
    if not st.session_state.get("phi_validated"):
        st.error("🚫 Datei wurde nicht durch den Datenschutz-Check validiert. Bitte erneut hochladen.")
        return

    edf = load_and_prepare(edf_path)
    fs = edf["sfreq"]
    eeg_map = edf["eeg_map"]
    if not eeg_map:
        st.warning("Keine EEG-Kanäle (10-20) erkannt.")
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
        ch = st.selectbox("Kanal", all_eeg, index=all_eeg.index(default_ch),
                          key="aper_channel", format_func=_ch_fmt)
    with c2:
        st.markdown(
            f"<div style='padding:8px 0 4px;font-size:13px;color:#555'>"
            f"Analyse über die <b>Gesamtaufnahme</b> · Alpha-Suchband "
            f"<b>{a_lo:.0f}–{a_hi:.0f} Hz</b> (altersadaptiv)</div>",
            unsafe_allow_html=True,
        )

    with st.expander("ℹ️ Welchen Kanal wählen?"):
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
        st.warning("Signal zu kurz für die Spektralschätzung.")
        return
    res = fit_aperiodic(freqs, psd, fmin=FIT_LO, fmax=FIT_HI)
    if res is None:
        st.warning("Aperiodischer Fit nicht möglich (zu wenige Frequenzpunkte).")
        return

    exp = res["exponent"]
    off = res["offset"]
    r2 = res["r2"]
    apf_corr = corrected_peak(res, a_lo, a_hi)

    # ── Kennzahlen ────────────────────────────────────────────────────────────
    section_header("Kennzahlen", f"Kanal {ch} · Fit {FIT_LO:.0f}–{FIT_HI:.0f} Hz")
    _r2_zone = "normal" if r2 >= 0.95 else ("grenzwertig" if r2 >= 0.90 else "pathologisch")
    _r2_col = {"normal": "#27ae60", "grenzwertig": "#e67e22", "pathologisch": "#c0392b"}[_r2_zone]
    _r2_txt = {"normal": "guter Fit", "grenzwertig": "mäßiger Fit", "pathologisch": "schwacher Fit"}[_r2_zone]

    def _tile(col, label, value, sub, color="#2471a3"):
        col.markdown(
            f"<div style='text-align:center;padding:12px 8px;border-radius:10px;"
            f"border:1.5px solid {color}40;background:{color}0d'>"
            f"<div style='font-size:10px;color:#888;font-weight:600;letter-spacing:.5px'>{label}</div>"
            f"<div style='font-size:22px;font-weight:800;color:{color};margin:3px 0'>{value}</div>"
            f"<div style='font-size:10px;color:#999'>{sub}</div></div>",
            unsafe_allow_html=True,
        )

    k1, k2, k3, k4 = st.columns(4)
    _tile(k1, "EXPONENT (Steilheit)", f"{exp:.2f}", "1/f-Abfall", "#8e44ad")
    _tile(k2, "OFFSET", f"{off:.2f}", "log₁₀ Power @ 1 Hz", "#2471a3")
    _tile(k3, "FIT-GÜTE R²", f"{r2:.3f}", _r2_txt, _r2_col)
    _tile(k4, "ALPHA-PEAK (korrigiert)",
          f"{apf_corr:.1f} Hz" if apf_corr == apf_corr else "—",
          "Gipfel über Untergrund", "#27ae60")

    st.caption(f"🌀 **Exponent {exp:.2f}** — {_exponent_hint(exp, age)}. "
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
            f"⚠️ Fit-Güte R² = {r2:.3f} — der 1/f-Untergrund ist in diesem Kanal nur "
            f"{_r2_txt.lower()} beschreibbar (Artefakte, Krümmung/Knee, breite Gipfel). "
            f"Exponent/Offset mit Vorsicht interpretieren."
        )

    # ── Plot 1: Zerlegung im log-log-Raum ─────────────────────────────────────
    section_header("Spektrale Zerlegung", "log-log: Original vs. aperiodischer Fit")
    f = res["freqs"]
    fig1 = go.Figure()
    # Band-Hintergründe
    for bname, (lo, hi), bcol in BANDS:
        fig1.add_vrect(x0=lo, x1=hi, fillcolor=bcol, opacity=0.06, line_width=0,
                       annotation_text=bname, annotation_position="top",
                       annotation_font_size=9, annotation_font_color=bcol)
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
        plot_bgcolor="#fafafa",
        legend=dict(orientation="h", yanchor="bottom", y=1.03, x=0, font=dict(size=11)),
    )
    st.plotly_chart(fig1, use_container_width=True, key="aper_decomp")
    st.caption(
        "Die **rote Gerade** ist der aperiodische Untergrund. Wo das graue "
        "Originalspektrum darüber liegt, sitzt ein **echter Rhythmus** (z. B. Alpha)."
    )

    # ── Plot 2: Untergrund-bereinigtes Spektrum (Verhältnis) ──────────────────
    section_header("Untergrund-bereinigtes Spektrum", "Vielfaches über dem 1/f-Untergrund")
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
        plot_bgcolor="#fafafa", showlegend=False,
    )
    st.plotly_chart(fig2, use_container_width=True, key="aper_flat")
    st.caption(
        "Baseline **1,0** = reiner Untergrund. Werte **> 1** sind oszillatorische "
        "Gipfel. Der Alpha-Gipfel ist hier unabhängig vom 1/f-Abfall ablesbar."
    )

    # ── Kanal-Übersicht ───────────────────────────────────────────────────────
    section_header("Exponent je Kanal", "Konsistenz-Check & Kanalwahl")
    _exps = _all_channel_exponents(edf_path, FIT_LO, FIT_HI)
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
            plot_bgcolor="#fafafa", showlegend=False,
        )
        st.plotly_chart(fig3, use_container_width=True, key="aper_perchannel")
        st.caption(
            f"Aktiver Kanal **{ch}** (lila) im Vergleich zum Median aller Kanäle "
            f"(**{_median:.2f}**, orange). Stark abweichende, **blasse** Balken haben "
            f"schwache Fit-Güte (R² < 0,90) — meist artefaktbedingt. Ein Kanal nahe "
            f"dem Median ist für die E/I-Einordnung am repräsentativsten."
        )

    # ── Appendix ──────────────────────────────────────────────────────────────
    st.markdown("---")
    with st.expander("📖 Was ist die aperiodische Komponente? — Methodik & Literatur", expanded=False):
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

PSD (Welch, 1–40 Hz) → log-log → **robuster iterativer Geradenfit**: Punkte, die
deutlich über der Geraden liegen (= Gipfel), werden verworfen und neu gefittet
(„sigma-clipping"), damit die Gipfel den Untergrund nicht nach oben ziehen.
Ausgabe: Offset, Exponent, Fit-Güte R² und das untergrund-bereinigte Spektrum.

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
