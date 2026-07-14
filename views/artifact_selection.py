"""Artefaktkorrektur & EEG/EKG-Selektion — NEUE Seite (Gleis 2).

A5: die Artefakt-Maske erstmals SICHTBAR machen — read-only. Ändert nichts an den
bestehenden Analysen (EEG-Spektrum, EKG & HRV laufen weiter über die Gesamtaufnahme).
Nachgeschaltet nach der Kanal-Identifikation (nutzt deren Typ-Overrides).
"""

import json
import os
from dataclasses import replace

import numpy as np
import streamlit as st
import streamlit.components.v1 as components
import plotly.graph_objects as go

# Bidirektionales Custom-Component: Canvas-Review mit Klick-Interaktion (A9b)
_ART_CANVAS = components.declare_component(
    "artifact_canvas", path=os.path.join(os.path.dirname(__file__), "artifact_canvas"))

from core.shared import (
    apply_global_style, section_header, get_edf_or_stop,
    load_and_prepare, apply_channel_overrides, get_patient_info, ELECTRODE_POS,
)
from analysis.artifacts import ArtifactParams, mask_from_edf
# Reuse der bestehenden Spektrum-Logik OHNE eeg_spectrum.py zu verändern (nur Import).
from views.eeg_spectrum import (
    _compute_psd, _band_power, _peak_freq, _spectral_edge, _highpass,
    _alpha_band, BANDS, BAND_COLOR,
)
from analysis.ecg import detect_r_peaks, build_rr_series, compute_hrv_time_domain


def _mmss(s: float) -> str:
    s = int(round(s))
    return f"{s // 60}:{s % 60:02d}"


# A10: Regions-Toleranz-Presets (Faktoren + räumlicher Schutz min_nonfrontal)
_REGION_PRESETS = {
    "aus":     ({"FP1": 1.0, "FP2": 1.0, "F7": 1.0, "F8": 1.0, "T3": 1.0, "T4": 1.0}, 0),
    "moderat": (None, 1),  # None → Modul-Default (Fp 2,0 / F7F8 1,4 / T3T4 1,2)
    "kräftig": ({"FP1": 2.5, "FP2": 2.5, "F7": 1.8, "F8": 1.8, "T3": 1.4, "T4": 1.4}, 2),
}


@st.cache_data(show_spinner="Berechne Artefakt-Maske …")
def _cached_mask(edf_path: str, overrides_key: str, flag_sus: float, consensus_n: int,
                 min_island: float, region: str):
    """Gecachte Masken-Berechnung. Cache-Key umfasst Kanal-Overrides UND die justierten
    Detektor-Schwellen (A10)."""
    edf = apply_channel_overrides(load_and_prepare(edf_path))
    rf, mnf = _REGION_PRESETS.get(region, (None, 1))
    p = ArtifactParams(flag_sus=flag_sus, consensus_n=int(consensus_n),
                       min_clean_island_s=float(min_island),
                       region_factors=rf, min_nonfrontal=mnf)
    return mask_from_edf(edf, p)


@st.cache_data(show_spinner="Erkenne R-Zacken …")
def _cached_rr(edf_path: str, ecg_name: str, overrides_key: str):
    """Gecachte R-Zacken-/RR-Erkennung für den HRV-Vergleich."""
    edf = apply_channel_overrides(load_and_prepare(edf_path))
    sig = edf["data"][edf["ch_idx"][ecg_name]].astype(float)
    rp = detect_r_peaks(sig, edf["sfreq"])
    rr = build_rr_series(rp, edf["sfreq"])
    if rr is None:
        return None
    return {"rr_ms": rr.rr_ms, "times": rr.rr_times_s, "mask": rr.artifact_mask}


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
    st.caption(f"🔄 Der Korrigiert-Wert nutzt die **aktuelle** Maske ({_mmss(res.clean_s)} min:s "
               f"sauber, {len(res.segments)} Segmente) — aktualisiert sich sofort bei jeder "
               "Bearbeitung oben.")

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


def _render_hrv_compare(edf, edf_path, res, overrides_key):
    """A7: HRV Gesamt vs. artefaktkorrigiert (Schläge in Artefakt-Segmenten ausgeschlossen)."""
    ecg_channels = edf.get("ecg_channels") or []
    section_header("HRV — Gesamt vs. artefaktkorrigiert",
                   "RR-basierte Herzratenvariabilität, einmal komplett, einmal ohne Bewegungsfenster")
    st.caption(f"🔄 Der Korrigiert-Wert schließt die Schläge in der **aktuellen** Maske "
               f"({len(res.segments)} Segmente) aus — aktualisiert sich sofort bei jeder Bearbeitung.")
    if not ecg_channels:
        st.info("Kein EKG-Kanal identifiziert → HRV-Vergleich nicht möglich. Ggf. in der "
                "Kanal-Identifikation einen EKG-Kanal festlegen.")
        return

    ecg_name = ecg_channels[0]
    rr = _cached_rr(edf_path, ecg_name, overrides_key)
    if rr is None or len(rr["rr_ms"]) < 10:
        st.warning(f"Zu wenige R-Zacken auf **{ecg_name}** für eine HRV-Auswertung.")
        return

    rr_ms, times, ectopic = rr["rr_ms"], rr["times"], rr["mask"]
    base_ok = ~ectopic                                   # ektopische/implausible RR raus (Standard)
    in_seg = np.zeros(len(rr_ms), dtype=bool)            # Schläge in Artefakt-Segmenten
    for s in res.segments:
        in_seg |= (times >= s["start_s"]) & (times < s["end_s"])

    full_rr = rr_ms[base_ok]
    corr_rr = rr_ms[base_ok & ~in_seg]
    n_removed = int((base_ok & in_seg).sum())

    hrv_full = compute_hrv_time_domain(full_rr)
    hrv_corr = compute_hrv_time_domain(corr_rr)
    if not hrv_full or not hrv_corr:
        st.warning("Zu wenige saubere RR-Intervalle für die HRV-Berechnung.")
        return

    labels = [("mean_hr_bpm", "Mittlere HF", "bpm"), ("sdnn_ms", "SDNN", "ms"),
              ("rmssd_ms", "RMSSD", "ms"), ("pnn50_pct", "pNN50", "%"),
              ("cv_pct", "CV", "%")]
    rows, rel_change = [], 0.0
    for key, name, unit in labels:
        vf, vc = hrv_full.get(key), hrv_corr.get(key)
        d = (vc - vf) if (vf is not None and vc is not None) else None
        if key in ("sdnn_ms", "rmssd_ms") and vf:
            rel_change = max(rel_change, abs(d) / vf * 100)
        rows.append({"Parameter": name, "Gesamt": f"{vf} {unit}",
                     "Korrigiert": f"{vc} {unit}", "Δ": ("—" if d is None else f"{d:+.1f}")})
    st.dataframe(rows, use_container_width=True, hide_index=True)

    st.caption(f"EKG-Kanal **{ecg_name}** · {n_removed} von {len(full_rr)} sauberen RR-Intervallen "
               f"lagen in Artefakt-Segmenten und wurden für die korrigierte Auswertung entfernt. "
               "Beide Werte zusätzlich um ektopische/implausible Schläge bereinigt (Standard).")
    if rel_change < 5:
        st.success(f"✅ **Geringer Artefakt-Impact auf die HRV** — SDNN/RMSSD ändern sich um "
                   f"< {max(rel_change,0.1):.0f} %. Die Gesamt-HRV ist hier belastbar.")
    elif rel_change < 15:
        st.info(f"ℹ️ **Moderater Impact** — SDNN/RMSSD ändern sich um bis zu {rel_change:.0f} %.")
    else:
        st.warning(f"⚠️ **Deutlicher Impact** — SDNN/RMSSD ändern sich um bis zu {rel_change:.0f} % "
                   "→ korrigierte HRV bevorzugen (Bewegung verzerrt die RR-Reihe).")


# ── DGKN-Montagen für die Review-Ansicht ─────────────────────────────────────
# Hemisphären-Farben: rechts bläulich · links orange · Mittellinie grün · EKG rot.
_COL_R, _COL_L, _COL_M, _COL_ECG = "#3b82f6", "#e67e22", "#16a34a", "#c0392b"

# Bipolare Längsreihe (DGKN „Doppelte Banane") — nach Ketten gruppiert (Spacer dazwischen).
_LONG_GROUPS = [
    ("re. temporal",      [("Fp2", "F8"), ("F8", "T4"), ("T4", "T6"), ("T6", "O2")], _COL_R),
    ("li. temporal",      [("Fp1", "F7"), ("F7", "T3"), ("T3", "T5"), ("T5", "O1")], _COL_L),
    ("re. parasagittal",  [("Fp2", "F4"), ("F4", "C4"), ("C4", "P4"), ("P4", "O2")], _COL_R),
    ("li. parasagittal",  [("Fp1", "F3"), ("F3", "C3"), ("C3", "P3"), ("P3", "O1")], _COL_L),
    ("Mittellinie",       [("Fz", "Cz"), ("Cz", "Pz")], _COL_M),
]
# Referenzielle Ketten (für Cz-Ref & Average) — nach Hemisphäre geordnet.
_REF_GROUPS = [
    ("rechts",      ["Fp2", "F8", "F4", "T4", "C4", "T6", "P4", "O2"], _COL_R),
    ("links",       ["Fp1", "F7", "F3", "T3", "C3", "T5", "P3", "O1"], _COL_L),
    ("Mittellinie", ["Fz", "Cz", "Pz"], _COL_M),
]

_MONTAGES = ["Bipolare Längsreihe", "Cz-Referenz", "Average-Referenz"]


def _build_traces(edf, montage, i0, i1):
    """Baut die Ableitungen der gewählten Montage → geordnete Trace-Liste mit Gruppen (Spacer)."""
    eeg_map = edf["eeg_map"]
    sf = edf["sfreq"]
    present = {e: edf["data"][eeg_map[e], i0:i1] * 1e6 for e in ELECTRODE_POS if e in eeg_map}
    present = {e: _highpass(v, sf, 1.0) if len(v) > 20 else v for e, v in present.items()}
    avg = np.mean(list(present.values()), axis=0) if present else None

    groups = []  # [(group_label, [ {label,sig,color} ... ])]
    if montage == "Bipolare Längsreihe":
        for gname, pairs, col in _LONG_GROUPS:
            traces = [{"label": f"{a}–{b}", "sig": present[a] - present[b], "color": col}
                      for a, b in pairs if a in present and b in present]
            if traces:
                groups.append((gname, traces))
    else:
        ref_ok = montage == "Average-Referenz" or "Cz" in present
        for gname, elecs, col in _REF_GROUPS:
            traces = []
            for e in elecs:
                if e not in present:
                    continue
                if montage == "Cz-Referenz":
                    if e == "Cz" or "Cz" not in present:
                        continue
                    sig, lab = present[e] - present["Cz"], f"{e}–Cz"
                else:  # Average
                    sig, lab = present[e] - avg, f"{e}–avg"
                traces.append({"label": lab, "sig": sig, "color": col})
            if traces:
                groups.append((gname, traces))
    return groups



def _minmax_decimate(sig: np.ndarray, n_buckets: int):
    """Min/Max-Dezimierung: erhält Spitzen (Artefakte) auch bei starker Verkleinerung."""
    n = len(sig)
    if n <= n_buckets:
        return sig.tolist(), sig.tolist()
    edges = np.linspace(0, n, n_buckets + 1).astype(int)
    mins = np.array([sig[edges[i]:edges[i + 1]].min() for i in range(n_buckets)])
    maxs = np.array([sig[edges[i]:edges[i + 1]].max() for i in range(n_buckets)])
    return mins.tolist(), maxs.tolist()


def _render_review_viewer(edf, res, res_auto):
    """A8/A9b: All-Kanal-Review-Canvas (DGKN-Montage, Hemisphärenfarben, EKG, Spacer) mit
    Klick-Interaktion — Block anklicken = raus/rein, ins EEG klicken = Artefakt hinzufügen."""
    section_header("Review-Ansicht — alle Kanäle",
                   "DGKN-Montage · 60–100 s/Screen · Artefakt-Segmente markiert")

    sfreq = edf["sfreq"]
    dur = res.duration_s

    c1, c2, c3, c4 = st.columns([2.2, 1.4, 3, 2.4])
    with c1:
        montage = st.selectbox("Montage", _MONTAGES, index=0)
    with c2:
        screen_s = st.selectbox("Screen", [10, 30, 60, 100], index=2,
                                format_func=lambda s: f"{s} s", key="artifact_screen_len")
    with c4:
        st.markdown("<div style='font-size:13px;color:#555'>Empfindlichkeit</div>",
                    unsafe_allow_html=True)
        _SENS_OPTS = [0.25, 0.5, 1.0, 2.0, 4.0, 8.0]
        sk = "artifact_sens"
        cur = st.session_state.get(sk, 1.0)
        si = _SENS_OPTS.index(cur) if cur in _SENS_OPTS else 2
        sc1, sc2, sc3 = st.columns([1, 1.3, 1])
        if sc1.button("−", key="sens_dn", use_container_width=True, disabled=(si == 0)):
            si -= 1
        if sc3.button("＋", key="sens_up", use_container_width=True,
                      disabled=(si == len(_SENS_OPTS) - 1)):
            si += 1
        st.session_state[sk] = _SENS_OPTS[si]
        sens = _SENS_OPTS[si]
        sc2.markdown(f"<div style='text-align:center;padding-top:6px;font-weight:800;"
                     f"font-size:15px'>{sens:g}×</div>", unsafe_allow_html=True)

    n_screens = max(1, int(np.ceil(dur / screen_s)))
    key = "artifact_screen_idx"
    idx = max(0, min(st.session_state.get(key, 0), n_screens - 1))
    with c3:
        nav_prev, nav_lbl, nav_next = st.columns([1, 2, 1])
        if nav_prev.button("◀", use_container_width=True, disabled=(idx == 0)):
            idx -= 1
        if nav_next.button("▶", use_container_width=True, disabled=(idx >= n_screens - 1)):
            idx += 1
        nav_lbl.markdown(f"<div style='text-align:center;padding-top:6px;font-size:13px'>Screen "
                         f"<b>{idx+1}</b>/{n_screens}</div>", unsafe_allow_html=True)
    st.session_state[key] = idx

    t0 = idx * screen_s
    t1 = min(dur, t0 + screen_s)
    i0, i1 = int(t0 * sfreq), int(t1 * sfreq)
    n_buckets = 1100
    lane_h, spacer_h, header_h = 26, 12, 18

    groups = _build_traces(edf, montage, i0, i1)
    # Uniforme EEG-Verstärkung (klinisch: gleiche µV/mm über alle Kanäle) aus 95. Perzentil.
    all_abs = np.concatenate([np.abs(tr["sig"]) for _, trs in groups for tr in trs]) \
        if groups else np.array([1.0])
    g95 = float(np.percentile(all_abs, 95)) or 1.0
    g_eeg = (lane_h * 0.5) / g95 * sens

    traces, spacers, y = [], [], float(header_h)   # Header-Platz oben für den Klick-Hinweis
    for gi, (gname, trs) in enumerate(groups):
        for tr in trs:
            y += lane_h
            mins, maxs = _minmax_decimate(tr["sig"].astype(float), n_buckets)
            traces.append({"label": tr["label"], "color": tr["color"], "pol": 1, "yc": y - lane_h / 2,
                           "gain": round(g_eeg, 4),
                           "mins": [round(v, 1) for v in mins], "maxs": [round(v, 1) for v in maxs]})
        y += spacer_h
        spacers.append(y - spacer_h / 2)

    # EKG-Spur (rot, R-Zacke oben, eigene Verstärkung)
    ecg_channels = edf.get("ecg_channels") or []
    if ecg_channels and ecg_channels[0] in edf.get("ch_idx", {}):
        esig = edf["data"][edf["ch_idx"][ecg_channels[0]], i0:i1] * 1000.0  # mV
        if len(esig) > 20:
            esig = _highpass(esig, sfreq, 0.5)
        e95 = float(np.percentile(np.abs(esig), 95)) or 1.0
        y += lane_h
        mins, maxs = _minmax_decimate(esig.astype(float), n_buckets)
        traces.append({"label": f"EKG ({ecg_channels[0]})", "color": _COL_ECG, "pol": -1,
                       "yc": y - lane_h / 2, "gain": round((lane_h * 0.55) / e95, 4),
                       "mins": [round(v, 2) for v in mins], "maxs": [round(v, 2) for v in maxs]})

    # ── Segment-Zustände (aktiv / entfernt / manuell) für das klickbare Canvas ──
    ov = st.session_state.setdefault("artifact_overrides", {"removed": [], "added": []})
    span = (t1 - t0) or 1.0
    _vis = lambda a, b: b > t0 and a < t1
    seg_state = []
    for s in res_auto.segments:
        if not _vis(s["start_s"], s["end_s"]):
            continue
        k = _seg_key(s)
        seg_state.append({"x0": max(0.0, s["start_s"] - t0) / span,
                          "x1": (min(t1, s["end_s"]) - t0) / span, "key": k,
                          "state": "removed" if k in ov["removed"] else "active"})
    for a in ov["added"]:
        if not _vis(a["start_s"], a["end_s"]):
            continue
        seg_state.append({"x0": max(0.0, a["start_s"] - t0) / span,
                          "x1": (min(t1, a["end_s"]) - t0) / span,
                          "key": f"{a['start_s']:.1f}-{a['end_s']:.1f}", "state": "manual"})

    plot_h = int(y + 8)
    evt = _ART_CANVAS(traces=traces, spacers=spacers, segments=seg_state, t0=t0, t1=t1,
                      n_buckets=n_buckets, plotH=plot_h, height=plot_h + 26,
                      key="artcanvas", default=None)
    # Klick-Event verarbeiten (nur neue Klicks → n-Guard gegen Doppelverarbeitung)
    if evt and evt.get("n") != st.session_state.get("_art_last_evt"):
        st.session_state["_art_last_evt"] = evt["n"]
        act = evt.get("action")
        if act == "toggle":
            k = evt["key"]
            ov["removed"].remove(k) if k in ov["removed"] else ov["removed"].append(k)
        elif act == "add":
            tt = float(evt["t"])
            ov["added"].append({"start_s": round(max(0.0, tt - 2.5), 2),
                                "end_s": round(min(dur, tt + 2.5), 2)})
            # Benachbarte/überlappende manuelle Blöcke zu EINEM großen Block verschmelzen:
            # so verlängert man durch Klicken links/rechts einen Artefaktblock.
            ov["added"] = _merge_added(ov["added"])
        elif act == "del_manual":
            k = evt["key"]
            ov["added"] = [a for a in ov["added"]
                           if f"{a['start_s']:.1f}-{a['end_s']:.1f}" != k]
        st.rerun()

    st.caption(f"⏱ {_mmss(t0)}–{_mmss(t1)} · Montage **{montage}** · rechts blau · links orange · "
               "Mitte grün · EKG rot. **Klick ins EEG** = 5-s-Artefakt hinzufügen "
               "(direkt daneben klicken verlängert den Block) · **Klick auf einen Block** = "
               "entfernen bzw. wieder aktivieren. Verworfen = negativ-invertiert, inaktiv = gestrichelt.")


# ── A9a: manuelle Bearbeitung der Maske (Override-Ebene, getrennt von der Auto-Maske) ──
def _seg_key(s) -> str:
    return f"{s['start_s']:.1f}-{s['end_s']:.1f}"


def _merge_added(added, tol=2.5):
    """Verschmilzt manuelle Blöcke, die sich überlappen oder ≤ tol s auseinanderliegen,
    zu einem großen Block (Klicken links/rechts verlängert)."""
    ivs = sorted([[a["start_s"], a["end_s"]] for a in added])
    out = []
    for lo, hi in ivs:
        if out and lo <= out[-1][1] + tol:
            out[-1][1] = max(out[-1][1], hi)
        else:
            out.append([lo, hi])
    return [{"start_s": round(lo, 2), "end_s": round(hi, 2)} for lo, hi in out]


def _union_len(segs) -> float:
    """Gesamtdauer der (ggf. überlappenden) Segmente per Intervall-Vereinigung."""
    ivs = sorted((s["start_s"], s["end_s"]) for s in segs)
    tot, lo, hi = 0.0, None, None
    for a, b in ivs:
        if hi is None:
            lo, hi = a, b
        elif a <= hi:
            hi = max(hi, b)
        else:
            tot += hi - lo; lo, hi = a, b
    if hi is not None:
        tot += hi - lo
    return tot


def _effective_res(res_auto, dur):
    """Effektive Maske = Auto-Segmente (minus vom User entfernte) + manuell hinzugefügte."""
    ov = st.session_state.setdefault("artifact_overrides", {"removed": [], "added": []})
    removed = set(ov["removed"])
    eff = [dict(s, manual=False) for s in res_auto.segments if _seg_key(s) not in removed]
    for a in ov["added"]:
        eff.append({"start_s": a["start_s"], "end_s": a["end_s"],
                    "dur_s": round(a["end_s"] - a["start_s"], 2),
                    "max_ratio": None, "ecg_disturbed": None, "manual": True})
    eff.sort(key=lambda s: s["start_s"])
    clean_s = max(0.0, dur - _union_len(eff)) if eff else dur
    return replace(res_auto, segments=eff, clean_s=clean_s,
                   clean_frac=clean_s / dur if dur else 1.0)


def _render_segment_editor(res_auto, dur):
    """A9a: Auto-Segmente entfernen (kein Artefakt) / manuell Bereiche hinzufügen (übersehen)."""
    ov = st.session_state.setdefault("artifact_overrides", {"removed": [], "added": []})
    n_add, n_rem = len(ov["added"]), len(ov["removed"])
    section_header("Artefakt-Segmente — bearbeiten",
                   "Auto-Vorschlag anpassen · fließt sofort in Vorher/Nachher-Auswertung")
    if n_add or n_rem:
        cc1, cc2 = st.columns([4, 1])
        cc1.info(f"✏️ Manuell: **{n_add}** hinzugefügt · **{n_rem}** als kein Artefakt entfernt.")
        if cc2.button("Zurücksetzen", use_container_width=True):
            st.session_state["artifact_overrides"] = {"removed": [], "added": []}
            st.rerun()

    hdr = st.columns([3, 1.4, 2, 2, 2.2])
    for c, t in zip(hdr, ["Bereich", "Dauer", "max. Amplitude", "EKG", ""]):
        c.markdown(f"<span style='font-size:11px;color:#888;font-weight:700'>{t}</span>",
                   unsafe_allow_html=True)

    # Auto-Segmente
    for s in res_auto.segments:
        k = _seg_key(s)
        removed = k in ov["removed"]
        col = st.columns([3, 1.4, 2, 2, 2.2])
        strike = "text-decoration:line-through;opacity:0.5;" if removed else ""
        col[0].markdown(f"<span style='{strike}'>🔴 {_mmss(s['start_s'])}–{_mmss(s['end_s'])}</span>",
                        unsafe_allow_html=True)
        col[1].markdown(f"<span style='{strike}'>{s['dur_s']}s</span>", unsafe_allow_html=True)
        col[2].markdown(f"<span style='{strike}'>{s['max_ratio']}×</span>"
                        if s["max_ratio"] else "—", unsafe_allow_html=True)
        col[3].markdown("✓" if s["ecg_disturbed"] else ("–" if s["ecg_disturbed"] is not None else ""))
        if removed:
            if col[4].button("↩︎ doch Artefakt", key=f"reart_{k}", use_container_width=True):
                ov["removed"].remove(k); st.rerun()
        else:
            if col[4].button("✗ kein Artefakt", key=f"keep_{k}", use_container_width=True):
                ov["removed"].append(k); st.rerun()

    # Manuell hinzugefügte
    for i, a in enumerate(ov["added"]):
        col = st.columns([3, 1.4, 2, 2, 2.2])
        col[0].markdown(f"🖐 **{_mmss(a['start_s'])}–{_mmss(a['end_s'])}** "
                        "<span style='font-size:10px;color:#e67e22'>manuell</span>",
                        unsafe_allow_html=True)
        col[1].markdown(f"{round(a['end_s']-a['start_s'],1)}s")
        col[2].markdown("—"); col[3].markdown("")
        if col[4].button("🗑 löschen", key=f"del_{i}", use_container_width=True):
            ov["added"].pop(i); st.rerun()

    if not res_auto.segments and not ov["added"]:
        st.success("✅ Keine Artefakt-Segmente — die Aufnahme läuft ruhig durch.")

    # Bereich hinzufügen
    with st.expander("➕ Artefakt-Bereich hinzufügen (übersehenen Bereich ausklammern)"):
        idx = st.session_state.get("artifact_screen_idx", 0)
        slen = st.session_state.get("artifact_screen_len", 60)
        def_start = float(min(idx * slen, max(0.0, dur - 10)))
        ca, cb, cd = st.columns([2, 2, 1.4])
        s0 = ca.number_input("Start (s)", 0.0, float(dur), def_start, step=1.0, key="add_start")
        s1 = cb.number_input("Ende (s)", 0.0, float(dur), min(def_start + 10, float(dur)),
                             step=1.0, key="add_end")
        if cd.button("Hinzufügen", type="primary", use_container_width=True):
            if s1 > s0:
                ov["added"].append({"start_s": round(s0, 2), "end_s": round(s1, 2)})
                st.rerun()
            else:
                st.error("Ende muss nach Start liegen.")


def render():
    apply_global_style()
    edf, edf_path = get_edf_or_stop()

    st.title("🧹 Artefaktkorrektur & EEG/EKG-Selektion")
    st.markdown(
        "Markiert **grobe Bewegungs-/Globalartefakte** — bewusst **konservativ** (nur klar "
        "Artefaktbelastetes, kein Blinzeln/Slow-Wave-Sleep). Diese Seite ist ein **zweites Gleis**: "
        "die bestehenden Analysen (EEG-Spektrum, EKG & HRV) laufen unverändert über die "
        "**Gesamtaufnahme** weiter. Hier siehst du den **Auto-Vorschlag**, kannst ihn **manuell "
        "anpassen** (Segmente entfernen/hinzufügen) und die Auswertung **mit vs. ohne** Artefakte "
        "vergleichen. Die Originalanalysen bleiben unberührt."
    )

    if not edf.get("eeg_map"):
        st.warning(
            "⚠️ Keine EEG-Kanäle erkannt. Bitte zuerst auf **🔍 Kanal-Identifikation** die "
            "Kanäle festlegen (EEG / EKG / unbekannt) — die Artefakterkennung baut darauf auf."
        )
        return

    overrides_key = str(sorted(st.session_state.get("channel_overrides", {}).items()))

    # ── A10: Detektor-Schwellen justierbar ───────────────────────────────────
    with st.expander("⚙️ Detektor-Einstellungen — Feinjustierung der Artefakt-Erkennung", expanded=False):
        if st.button("Auf Standard zurücksetzen", key="art_reset_params"):
            for k in ("art_flag_sus", "art_consensus", "art_island", "art_region"):
                st.session_state.pop(k, None)
            st.rerun()
        sc = st.columns(4)
        flag_sus = sc[0].slider("Amplitude ≥ (× Baseline)", 3.0, 8.0,
                                st.session_state.get("art_flag_sus", 4.0), 0.5, key="art_flag_sus",
                                help="Höher = strenger (nur größere Ausschläge zählen).")
        consensus_n = sc[1].slider("Konsens: ≥ Kanäle heiß", 2, 8,
                                   st.session_state.get("art_consensus", 3), key="art_consensus",
                                   help="Höher = strenger (mehr Kanäle müssen gleichzeitig ausschlagen).")
        min_island = sc[2].slider("Min. saubere Insel (s)", 0.0, 15.0,
                                  st.session_state.get("art_island", 5.0), 1.0, key="art_island",
                                  help="Kürzere saubere Lücken zwischen Artefakten werden zu einem Block verschmolzen.")
        region = sc[3].select_slider("Regions-Toleranz (Fp/F7/F8/T)", ["aus", "moderat", "kräftig"],
                                     st.session_state.get("art_region", "moderat"), key="art_region",
                                     help="Schützt augen-/muskelnahe Elektroden vor Fehlflags (Blinzeln/EMG).")
        st.caption("Strenger (↑ Amplitude / ↑ Konsens) = weniger verworfen. Änderungen wirken "
                   "**sofort** auf Maske, Canvas und Vorher/Nachher-Auswertung.")

    res_auto = _cached_mask(edf_path, overrides_key, float(flag_sus), int(consensus_n),
                            float(min_island), region)
    dur = res_auto.duration_s
    res = _effective_res(res_auto, dur)   # Auto-Maske + manuelle Overrides (A9a)

    # ── Zusammenfassung ──────────────────────────────────────────────────────
    ov = st.session_state.get("artifact_overrides", {"removed": [], "added": []})
    n_add, n_rem = len(ov["added"]), len(ov["removed"])
    edited = bool(n_add or n_rem)
    section_header("Übersicht", "Effektive Maske = Auto + deine Änderungen · live berechnet")
    disc = dur - res.clean_s
    _dpp = (res.clean_frac - res_auto.clean_frac) * 100   # Prozentpunkte vs. Auto
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Sauberes EEG", f"{res.clean_frac*100:.0f}%",
              delta=(f"{_dpp:+.0f} pp vs. Auto" if abs(_dpp) >= 0.5 else None),
              help="Anteil ohne markiertes Artefakt (nach deinen Änderungen).")
    m2.metric("Verworfen", f"{disc:.0f}s", help=f"{_mmss(disc)} min:s von {_mmss(dur)}.")
    m3.metric("Segmente", f"{len(res.segments)}",
              delta=(f"+{n_add}/−{n_rem} manuell" if edited else None), delta_color="off")
    m4.metric("Bad-Channel-Vorschläge", f"{len(res.bad_channels)}")

    # Live-Status: WANN/WORAUF die Auswertung basiert
    if edited:
        st.success(
            f"🔄 **Live aktualisiert.** Spektrum & HRV unten rechnen mit deiner **bearbeiteten** "
            f"Maske: Auto {len(res_auto.segments)} Segmente, manuell **+{n_add} / −{n_rem}** → "
            f"effektiv **{len(res.segments)} Segmente**, **{res.clean_frac*100:.0f}%** sauber "
            f"(Auto: {res_auto.clean_frac*100:.0f}%). Jede Klick-Änderung wird **sofort** neu berechnet.")
    else:
        st.info("🔄 Noch keine manuellen Änderungen — es gilt die **Auto-Maske**. Sobald du oben im "
                "Canvas Segmente hinzufügst/entfernst, werden **Spektrum & HRV sofort** neu berechnet.")

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

    # ── A9a: Segment-Editor (entfernen / hinzufügen) ─────────────────────────
    _render_segment_editor(res_auto, dur)

    # ── Bad-Channel-Vorschläge ───────────────────────────────────────────────
    if res.bad_channels:
        section_header("Bad-Channel-Vorschläge", "Elektrode dauerhaft auffällig")
        for b in res.bad_channels:
            st.warning(
                f"🔌 **{b['name']}** ab **{_mmss(b['since_s'])}** dauerhaft isoliert auffällig "
                f"({b['frac']*100:.0f}% der Fenster) — möglicherweise gelöste/defekte Elektrode. "
                "**Vorschlag:** diese Ableitung aus den Analysen ausblenden. (Noch nur Vorschlag.)"
            )

    # ── A8/A9b: Review-Ansicht (alle Kanäle, klickbar) ───────────────────────
    _render_review_viewer(edf, res, res_auto)

    # ── A6: Spektralanalyse Gesamt vs. korrigiert ────────────────────────────
    _render_spectral_compare(edf, res)

    # ── A7: HRV Gesamt vs. korrigiert ────────────────────────────────────────
    _render_hrv_compare(edf, edf_path, res, overrides_key)

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

    # ── Export: artefaktkorrigierter Report als PDF / Excel ──────────────────
    st.divider()
    st.subheader("⬇️ Artefaktkorrigierten Report exportieren")
    st.caption("Alle Parameter (HRV · EEG-Spektrum · Aperiodik · Asymmetrie) berechnet auf den "
               "**sauberen** Segmenten deiner aktuellen Maske — kompakt, mit Einheit und kurzer Norm. "
               "PDF und Excel, analog zum Report, aber artefaktkorrigiert.")

    @st.cache_data(show_spinner="Erstelle artefaktkorrigierten Report …")
    def _export_corrected(_path, _seg_tuple, _disp):
        from analysis.report_export import collect_sections, build_pdf, build_excel
        e = apply_channel_overrides(load_and_prepare(_path))
        segs = [{"start_s": a, "end_s": b} for a, b in _seg_tuple]
        secs = collect_sections(e, _path, corr_segments=segs)
        return build_pdf(secs, _disp + " (mit deiner Maske)"), build_excel(secs, e, _disp)

    _disp = st.session_state.get("edf_display_name", "report")
    _base = (_disp.rsplit(".", 1)[0] if _disp else "report") + "_artefaktkorrigiert"
    _seg_tuple = tuple((s["start_s"], s["end_s"]) for s in res.segments)
    if not res.segments:
        st.info("Noch keine Artefakt-Segmente markiert → der korrigierte Report entspräche der "
                "Gesamtauswertung. Markiere/erzeuge oben Segmente oder nutze den Export auf der "
                "**Report**-Seite.")
    else:
        try:
            pdf_bytes, xlsx_bytes = _export_corrected(edf_path, _seg_tuple, _disp)
            ec1, ec2 = st.columns(2)
            ec1.download_button("📄 PDF (korrigiert)", pdf_bytes, file_name=f"{_base}.pdf",
                                mime="application/pdf", use_container_width=True)
            ec2.download_button(
                "📊 Excel (korrigiert)", xlsx_bytes, file_name=f"{_base}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True)
        except Exception as e:
            st.error(f"Export fehlgeschlagen: {e}")
