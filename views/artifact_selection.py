"""Artefaktkorrektur & EEG/EKG-Selektion — NEUE Seite (Gleis 2).

A5: die Artefakt-Maske erstmals SICHTBAR machen — read-only. Ändert nichts an den
bestehenden Analysen (EEG-Spektrum, EKG & HRV laufen weiter über die Gesamtaufnahme).
Nachgeschaltet nach der Kanal-Identifikation (nutzt deren Typ-Overrides).
"""

import numpy as np
import streamlit as st
import plotly.graph_objects as go

from core.shared import (
    apply_global_style, section_header, get_edf_or_stop,
    load_and_prepare, apply_channel_overrides, get_patient_info,
)
from analysis.artifacts import ArtifactParams, mask_from_edf
# Reuse der bestehenden Spektrum-Logik OHNE eeg_spectrum.py zu verändern (nur Import).
from views.eeg_spectrum import (
    _compute_psd, _band_power, _peak_freq, _spectral_edge, _highpass,
    _alpha_band, BANDS, BAND_COLOR,
)


def _mmss(s: float) -> str:
    s = int(round(s))
    return f"{s // 60}:{s % 60:02d}"


@st.cache_data(show_spinner="Berechne Artefakt-Maske …")
def _cached_mask(edf_path: str, overrides_key: str):
    """Gecachte Masken-Berechnung. overrides_key hält den Cache konsistent mit den
    manuellen Kanal-Korrekturen (Kanal-Identifikation)."""
    edf = apply_channel_overrides(load_and_prepare(edf_path))
    return mask_from_edf(edf, ArtifactParams())


def _timeline_figure(res, dur_s: float) -> go.Figure:
    t = res.window_t
    fig = go.Figure()
    # Artefakt-Segmente als schattierte Bereiche
    for sg in res.segments:
        fig.add_vrect(x0=sg["start_s"], x1=sg["end_s"],
                      fillcolor="rgba(192,57,43,0.16)", line_width=0, layer="below")
    # #heiße Kanäle je Fenster (Fläche)
    fig.add_trace(go.Scatter(
        x=t, y=res.n_hot, mode="lines", line=dict(color="#c0392b", width=1),
        fill="tozeroy", fillcolor="rgba(192,57,43,0.45)",
        hovertemplate="t=%{x:.0f}s · %{y} Kanäle heiß<extra></extra>", name="heiße Kanäle",
    ))
    # Konsens-Schwelle
    consensus = res.params.get("consensus_n", 3)
    fig.add_hline(y=consensus, line_color="#c0392b", line_width=1, line_dash="dash",
                  annotation_text=f"Konsens N≥{consensus}", annotation_font_size=9)
    # min:sec-Ticks alle 60 s
    ticks = list(range(0, int(dur_s) + 1, 60))
    fig.update_layout(
        height=200, margin=dict(t=8, b=34, l=48, r=10),
        xaxis=dict(title="Zeit (min:s)", tickvals=ticks,
                   ticktext=[_mmss(v) for v in ticks], gridcolor="rgba(200,200,200,0.25)"),
        yaxis=dict(title="Kanäle > Schwelle", rangemode="tozero",
                   gridcolor="rgba(200,200,200,0.25)"),
        plot_bgcolor="#fafafa", showlegend=False,
    )
    return fig


def _clean_signal(sig: np.ndarray, sfreq: float, segments: list) -> np.ndarray:
    """Entfernt die Artefakt-Segmente aus dem Signal (behält nur saubere Samples)."""
    keep = np.ones(len(sig), dtype=bool)
    for s in segments:
        i0, i1 = int(s["start_s"] * sfreq), int(s["end_s"] * sfreq)
        keep[max(0, i0):min(len(sig), i1)] = False
    return sig[keep]


def _spectral_metrics(sig: np.ndarray, sfreq: float, alpha_band) -> dict:
    """Relative Bandpower + Alpha-Peak + SEF95 für ein Signal (kein Extra-Artefaktfilter)."""
    f, p = _compute_psd(sig, sfreq, amp_thresh_uv=9999.0)
    if f is None:
        return {}
    bp = {name: _band_power(f, p, lo, hi) for name, (lo, hi), _ in BANDS}
    tot = sum(bp.values()) or 1.0
    out = {name: bp[name] / tot * 100 for name in bp}
    out["Alpha-Peak"] = _peak_freq(f, p, alpha_band[0], alpha_band[1])
    out["SEF95"] = _spectral_edge(f, p, 0.95)
    return out


def _render_spectral_compare(edf, res):
    """A6: Spektralanalyse Gesamt vs. artefaktkorrigiert (nebeneinander)."""
    eeg_map = edf["eeg_map"]
    section_header("Spektralanalyse — Gesamt vs. artefaktkorrigiert",
                   "Gleiche Analyse einmal über die ganze Aufnahme, einmal nur auf sauberen Segmenten")

    if not res.segments:
        st.info("Keine Artefakt-Segmente markiert → korrigiert = Gesamt (nichts zu entfernen).")
        return
    if res.clean_s < 30:
        st.warning(f"Nur {res.clean_s:.0f}s sauberes EEG — Korrektur-Spektrum wenig belastbar.")

    posterior = [c for c in ("O2", "O1", "Pz", "P4", "P3") if c in eeg_map]
    options = posterior + [c for c in eeg_map if c not in posterior]
    ch = st.selectbox("Kanal für den Vergleich", options, index=0,
                      help="Posteriore Kanäle (O1/O2) zeigen den Alpha-Grundrhythmus am klarsten.")

    age, _ = get_patient_info()
    ab = _alpha_band(age)
    sfreq = edf["sfreq"]
    sig = _highpass(edf["data"][eeg_map[ch], :] * 1e6, sfreq, 1.0)
    sig_clean = _clean_signal(sig, sfreq, res.segments)

    full = _spectral_metrics(sig, sfreq, ab)
    corr = _spectral_metrics(sig_clean, sfreq, ab)
    if not full or not corr:
        st.warning("Segment zu kurz für eine stabile Spektralschätzung.")
        return

    # Vergleichstabelle
    def _fmt(k, v):
        if v != v:
            return "—"
        return f"{v:.1f} Hz" if k in ("Alpha-Peak", "SEF95") else f"{v:.1f} %"

    rows, max_delta = [], 0.0
    for k in ["Delta", "Theta", "Alpha", "Beta", "Alpha-Peak", "SEF95"]:
        vf, vc = full.get(k, float("nan")), corr.get(k, float("nan"))
        d = (vc - vf) if (vf == vf and vc == vc) else float("nan")
        if k in ("Delta", "Theta", "Alpha", "Beta") and d == d:
            max_delta = max(max_delta, abs(d))
        rows.append({"Parameter": k, "Gesamt": _fmt(k, vf), "Korrigiert": _fmt(k, vc),
                     "Δ": ("—" if d != d else f"{d:+.1f}")})
    st.dataframe(rows, use_container_width=True, hide_index=True)

    # Gruppierter Balken: relative Bandpower Gesamt vs. korrigiert
    fig = go.Figure()
    bands = ["Delta", "Theta", "Alpha", "Beta"]
    fig.add_trace(go.Bar(x=bands, y=[full[b] for b in bands], name="Gesamt",
                         marker_color="#95a5a6"))
    fig.add_trace(go.Bar(x=bands, y=[corr[b] for b in bands], name="Artefaktkorrigiert",
                         marker_color=[BAND_COLOR[b] for b in bands]))
    fig.update_layout(height=230, margin=dict(t=8, b=30, l=45, r=10), barmode="group",
                      yaxis_title="Rel. Power (%)", plot_bgcolor="#fafafa",
                      legend=dict(orientation="h", yanchor="bottom", y=1.02))
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    # Impact-Einordnung
    if max_delta < 1.0:
        st.success(f"✅ **Geringer Artefakt-Impact** — größte Änderung der relativen Bandpower "
                   f"nur **{max_delta:.1f} Prozentpunkte**. Über die lange Aufnahme mitteln sich die "
                   "kurzen Artefakte weitgehend heraus; die Gesamt-Auswertung ist hier belastbar.")
    elif max_delta < 3.0:
        st.info(f"ℹ️ **Moderater Artefakt-Impact** — bis **{max_delta:.1f} Prozentpunkte** Unterschied. "
                "Die korrigierte Auswertung lohnt den Blick.")
    else:
        st.warning(f"⚠️ **Deutlicher Artefakt-Impact** — bis **{max_delta:.1f} Prozentpunkte** "
                   "Unterschied. Hier verändern die Artefakte das Spektrum spürbar → korrigierte "
                   "Auswertung bevorzugen.")
    st.caption(f"Gesamt: ganze Aufnahme ({_mmss(res.duration_s)} min:s) · "
               f"Korrigiert: {_mmss(res.clean_s)} min:s saubere Segmente · Kanal {ch} · "
               "identische PSD-Methode (Welch), nur der Zeitausschnitt unterscheidet sich.")


def render():
    apply_global_style()
    edf, edf_path = get_edf_or_stop()

    st.title("🧹 Artefaktkorrektur & EEG/EKG-Selektion")
    st.markdown(
        "Markiert **grobe Bewegungs-/Globalartefakte** — bewusst **konservativ** (nur klar "
        "Artefaktbelastetes, kein Blinzeln/Slow-Wave-Sleep). Diese Seite ist ein **zweites Gleis**: "
        "die bestehenden Analysen (EEG-Spektrum, EKG & HRV) laufen unverändert über die "
        "**Gesamtaufnahme** weiter. Hier siehst du **nur die Maske** — noch wird nichts verworfen."
    )

    if not edf.get("eeg_map"):
        st.warning(
            "⚠️ Keine EEG-Kanäle erkannt. Bitte zuerst auf **🔍 Kanal-Identifikation** die "
            "Kanäle festlegen (EEG / EKG / unbekannt) — die Artefakterkennung baut darauf auf."
        )
        return

    overrides_key = str(sorted(st.session_state.get("channel_overrides", {}).items()))
    res = _cached_mask(edf_path, overrides_key)
    dur = res.duration_s

    # ── Zusammenfassung ──────────────────────────────────────────────────────
    section_header("Übersicht", "Auto-Vorschlag — read-only")
    disc = dur - res.clean_s
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Sauberes EEG", f"{res.clean_frac*100:.0f}%", help="Anteil ohne markiertes Artefakt.")
    m2.metric("Verworfen (Vorschlag)", f"{disc:.0f}s",
              help=f"{_mmss(disc)} min:s von {_mmss(dur)}.")
    m3.metric("Artefakt-Segmente", f"{len(res.segments)}")
    m4.metric("Bad-Channel-Vorschläge", f"{len(res.bad_channels)}")

    # Genügend saubere Zeit? (Literatur: ~1–2 min reichen spektral)
    if res.clean_s < 60:
        st.warning(f"⚠️ Nur **{res.clean_s:.0f}s** sauberes EEG — für stabile Spektralwerte grenzwertig "
                   "(Richtwert ≥ 1–2 min).")
    else:
        st.caption(f"✅ **{_mmss(res.clean_s)} min:s** sauberes EEG verfügbar "
                   "(Richtwert für stabile Spektralwerte: ≥ 1–2 min).")

    # ── Zeitleiste ───────────────────────────────────────────────────────────
    section_header("Zeitleiste", "Rote Flächen = Multikanal-Ausschläge · schattiert = Artefakt-Segment")
    st.plotly_chart(_timeline_figure(res, dur), use_container_width=True,
                    config={"displayModeBar": False})

    # ── Segmentliste ─────────────────────────────────────────────────────────
    if res.segments:
        section_header("Artefakt-Segmente", f"{len(res.segments)} markiert")
        rows = [{
            "Start": _mmss(s["start_s"]), "Ende": _mmss(s["end_s"]),
            "Dauer (s)": s["dur_s"], "max. Amplitude (× Baseline)": s["max_ratio"],
            "EKG mitgestört": ("—" if s["ecg_disturbed"] is None
                               else ("ja ✓" if s["ecg_disturbed"] else "nein")),
        } for s in res.segments]
        st.dataframe(rows, use_container_width=True, hide_index=True)
        st.caption("EKG mitgestört = ja stützt eine echte Körperbewegung; nein heißt nicht "
                   "sauber, sondern nur: die Bewegung hat die EKG-Elektrode nicht mit erfasst.")
    else:
        st.success("✅ Keine groben Artefakt-Segmente erkannt — die Aufnahme läuft ruhig durch.")

    # ── Bad-Channel-Vorschläge ───────────────────────────────────────────────
    if res.bad_channels:
        section_header("Bad-Channel-Vorschläge", "Elektrode dauerhaft auffällig")
        for b in res.bad_channels:
            st.warning(
                f"🔌 **{b['name']}** ab **{_mmss(b['since_s'])}** dauerhaft isoliert auffällig "
                f"({b['frac']*100:.0f}% der Fenster) — möglicherweise gelöste/defekte Elektrode. "
                "**Vorschlag:** diese Ableitung aus den Analysen ausblenden. (Noch nur Vorschlag.)"
            )

    # ── A6: Spektralanalyse Gesamt vs. korrigiert ────────────────────────────
    _render_spectral_compare(edf, res)

    # ── Transparenz ──────────────────────────────────────────────────────────
    with st.expander("ℹ️ Wie funktioniert die Erkennung?", expanded=False):
        p = res.params
        st.markdown(
            "**Konservatives, regelbasiertes Verfahren** (zwei Achsen):\n\n"
            "**Zeit-Achse (Bewegung/global):** je Kanal wird die Amplitude (Peak-to-Peak) pro "
            f"{p['win_s']:.0f}-s-Fenster mit der **eigenen Baseline** (Median über die Aufnahme) "
            f"verglichen. Ein Kanal ist auffällig ab **{p['flag_sus']:.0f}×** Baseline. Ein Fenster gilt "
            f"als Artefakt, wenn **≥ {p['consensus_n']} Kanäle** gleichzeitig heiß sind — so werden "
            "Einzelkanal-Ausschläge (lokal) und rhythmisches, echtes EEG (Slow-Wave-Sleep, Blinzeln) "
            "nicht verworfen.\n\n"
            "**Regionsabhängige Toleranz:** augen-/muskelnahe Elektroden dürfen mehr — "
            "**Fp1/Fp2 ×2,0**, **F7/F8 ×1,4**, **T3/T4 ×1,2** (Blinzeln/EOG/Kau-EMG). Zusätzlich muss "
            "mindestens ein **nicht-frontaler** Kanal beteiligt sein (rein frontales Blinzeln zählt "
            "nicht als Bewegung).\n\n"
            "**EKG:** bestätigt eine Körperbewegung, wenn es mitgestört ist — ist aber **kein "
            "Ausschlusskriterium** (manche Bewegungen erreichen die EKG-Elektrode nicht).\n\n"
            "**Kanal-Achse (Bad-Channel):** ein Kanal, der über einen längeren Abschnitt "
            "**isoliert** (bei ruhigem Rest) stark schwankt, wird als möglicherweise gelöste "
            "Elektrode zum Ausblenden **vorgeschlagen**.\n\n"
            "*Im Zweifel wird behalten — lieber ein Artefakt durchlassen als echtes EEG verwerfen.*"
        )
