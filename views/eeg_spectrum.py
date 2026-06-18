"""EEG-Spektralanalyse — Konsensus A/P-Panel + Einzelkanal-Analyse."""

import numpy as np
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy.signal import spectrogram, welch
from scipy.signal import butter, filtfilt
from scipy.signal.windows import dpss

from core.shared import load_and_prepare, section_header

# ── Frequenzbänder ────────────────────────────────────────────────────────────
BANDS = [
    ("Delta",  (0.5,  4.0),  "#4a90d9"),
    ("Theta",  (4.0,  8.0),  "#9b59b6"),
    ("Alpha",  (8.0, 13.0),  "#27ae60"),
    ("Beta",  (13.0, 30.0),  "#e67e22"),
]
FREQ_MAX = 30.0
BAND_DICT  = {name: rng for name, rng, _ in BANDS}
BAND_COLOR = {name: col for name, _, col in BANDS}

RATIO_INFO = {
    "Delta/Alpha":  {"normal": (0.0, 1.5), "hint": "Erhöht bei diffuser Verlangsamung / Enzephalopathie"},
    "Theta/Alpha":  {"normal": (0.2, 0.7), "hint": "Frühmarker diffuser Enzephalopathie / kognitiven Declines"},
    "Alpha/Theta":  {"normal": (1.5, 6.0), "hint": "Erniedrigt bei Schläfrigkeit / Vigilanzminderung"},
    "Theta/Beta":   {"normal": (0.5, 2.0), "hint": "Erhöht bei Schläfrigkeit, erniedrigt bei Aktivierung"},
    "DTAB":         {"normal": (0.0, 0.5), "hint": "(Delta+Theta)/(Alpha+Beta) — sensitiver Marker diffuser kortikaler Funktionsstörung"},
}


def _highpass(sig: np.ndarray, fs: float, cutoff: float = 1.0) -> np.ndarray:
    """1 Hz Hochpassfilter — entfernt DC-Drift und Bewegungsartefakte."""
    nyq = fs / 2
    b, a = butter(4, cutoff / nyq, btype="high")
    return filtfilt(b, a, sig)


def _band_power(freqs, psd, lo, hi):
    mask = (freqs >= lo) & (freqs < hi)
    return float(np.trapz(psd[mask], freqs[mask])) if mask.sum() > 1 else 0.0


def _peak_freq(freqs, psd, lo, hi):
    mask = (freqs >= lo) & (freqs < hi)
    return float(freqs[mask][np.argmax(psd[mask])]) if mask.sum() > 1 else float("nan")


def _reject_artifacts(sig: np.ndarray, fs: float, nperseg: int,
                       amp_thresh_uv: float = 80.0) -> np.ndarray:
    """
    Liefert eine artifact-bereinigte Version von sig.
    Epochs mit Peak-Amplitude > amp_thresh_uv werden durch lineare Interpolation ersetzt,
    damit die Signallänge für Welch/Multitaper erhalten bleibt.
    Methodengrundlage: Nolan 2010 (FASTER), Jas 2017 (MNE autoreject).
    """
    step = nperseg // 2
    n = len(sig)
    clean = sig.copy()
    i = 0
    while i + nperseg <= n:
        seg = sig[i:i + nperseg]
        if np.ptp(seg) > amp_thresh_uv:
            # Lineare Brücke zwischen Randpunkten
            clean[i:i + nperseg] = np.linspace(sig[i], sig[i + nperseg - 1], nperseg)
        i += step
    return clean


def _compute_psd(sig, fs, nperseg=None, multitaper=False, amp_thresh_uv=80.0):
    nperseg = nperseg or min(int(fs * 4), len(sig) // 2, 1024)
    if nperseg < 64:
        return None, None

    sig_clean = _reject_artifacts(sig, fs, nperseg, amp_thresh_uv)

    if multitaper:
        # Thomson (1982) DPSS — NW=3, K=5 gut für Alpha-Detektion (bandwidth ≈ 1.5 Hz)
        NW, K = 3, 5
        tapers, eigs = dpss(nperseg, NW, K, return_ratios=True)
        step = nperseg // 2
        freqs = np.fft.rfftfreq(nperseg, d=1.0 / fs)

        psds = []
        for i in range(0, len(sig_clean) - nperseg + 1, step):
            epoch = sig_clean[i:i + nperseg]
            ep_psd = np.zeros(len(freqs))
            w_sum = 0.0
            for taper, eig in zip(tapers, eigs):
                if eig < 0.9:
                    continue
                tapered = epoch * taper
                fft_coeffs = np.fft.rfft(tapered)
                ep_psd += eig * (np.abs(fft_coeffs) ** 2) / (fs * np.sum(taper ** 2))
                w_sum += eig
            if w_sum > 0:
                psds.append(ep_psd / w_sum)

        if not psds:
            return None, None
        psd = np.mean(psds, axis=0)
    else:
        freqs, psd = welch(sig_clean, fs=fs, nperseg=nperseg,
                           noverlap=nperseg // 2, scaling="density")

    mask = (freqs >= 1.0) & (freqs <= FREQ_MAX)
    return freqs[mask], psd[mask]


def _compute_spectrogram(sig, fs):
    nperseg = min(int(fs * 2), len(sig) // 8, 512)
    f, t, Sxx = spectrogram(sig, fs=fs, nperseg=nperseg, noverlap=nperseg // 2, scaling="density")
    mask = (f >= 1.0) & (f <= FREQ_MAX)
    Sxx_log = 10 * np.log10(Sxx[mask, :] + 1e-12)
    return f[mask], t, Sxx_log


def _spectrogram_trace(f, t, Sxx_log, dur_s):
    z_med = float(np.median(Sxx_log))
    tick_vals = list(range(0, int(t[-1]) + 1, 60))
    tick_text  = [f"{v//60}:{v%60:02d}" for v in tick_vals]
    trace = go.Heatmap(
        x=t, y=f, z=Sxx_log,
        colorscale="Jet", zmin=z_med - 15, zmax=z_med + 20,
        showscale=True,
        colorbar=dict(title="dB", thickness=10, len=0.8,
                      tickvals=[z_med - 15, z_med, z_med + 20],
                      ticktext=["niedrig", "mittel", "hoch"],
                      tickfont=dict(color="white")),
        hovertemplate="t=%{x:.1f}s  f=%{y:.1f}Hz  %{z:.1f}dB<extra></extra>",
        zsmooth="best",
    )
    return trace, tick_vals, tick_text


def _add_selection_overlay(fig, t_start: int, t_end: int, t_max: float) -> None:
    """Hebt das Analysefenster im Spektrogramm hervor:
    Außenbereiche abdunkeln + helle Randlinien (besser sichtbar als Semi-Transparenz auf Jet-Colormap)."""
    if t_start > 0:
        fig.add_vrect(x0=0, x1=t_start,
                      fillcolor="rgba(0,0,0,0.48)", line_width=0)
    if t_end < t_max:
        fig.add_vrect(x0=t_end, x1=t_max,
                      fillcolor="rgba(0,0,0,0.48)", line_width=0)
    # Helle Randlinien an den Selektionskanten
    fig.add_vline(x=t_start, line_color="white", line_width=3)
    fig.add_vline(x=t_end,   line_color="white", line_width=3)


def _sg_layout_update(fig, tick_vals, tick_text, title, row=1, col=1):
    band_boundaries = sorted({v for _, (lo, hi), _ in BANDS for v in [lo, hi]})
    for bf in band_boundaries:
        if 0.5 < bf < FREQ_MAX:
            fig.add_hline(y=bf, line_color="rgba(255,255,255,0.55)",
                          line_width=1, line_dash="dot", row=row, col=col)
    for name, (lo, hi), color in BANDS:
        fig.add_annotation(
            x=1.01, y=(lo + hi) / 2, xref="paper", yref=f"y{'' if (row==1 and col==1) else row}",
            text=name, showarrow=False, font=dict(size=9, color=color), xanchor="left",
        )


def _fft_figure(signals: dict, t_start, t_end, fs, panel_id,
                multitaper=False, amp_thresh_uv=80.0):
    """FFT-Overlay mehrerer Signale in einem Plot."""
    colors = {"Posterior (O1+O2)": "#27ae60", "Anterior (F3+F4)": "#e67e22",
              "O1": "#27ae60", "O2": "#2ecc71", "F3": "#e67e22", "F4": "#f39c12"}
    fig = go.Figure()
    alpha_peaks = {}
    bp_all = {}

    i0 = int(t_start * fs)
    i1 = int(t_end * fs)

    for label, sig in signals.items():
        seg = sig[i0:i1]
        freqs, psd = _compute_psd(seg, fs, multitaper=multitaper,
                                   amp_thresh_uv=amp_thresh_uv)
        if freqs is None:
            continue

        col = colors.get(label, "#2c3e50")

        # Farbige Band-Flächen (nur beim ersten Signal, sonst zu unübersichtlich)
        if label == list(signals.keys())[0]:
            for bname, (lo, hi), bcol in BANDS:
                bm = (freqs >= lo) & (freqs < hi)
                if bm.sum() > 1:
                    r, g, b = int(bcol[1:3], 16), int(bcol[3:5], 16), int(bcol[5:7], 16)
                    fig.add_trace(go.Scatter(
                        x=freqs[bm], y=psd[bm], fill="tozeroy", mode="none",
                        fillcolor=f"rgba({r},{g},{b},0.18)", name=bname,
                        showlegend=True,
                        hovertemplate=f"{bname}<extra></extra>",
                    ))

        fig.add_trace(go.Scatter(
            x=freqs, y=psd, mode="lines",
            line=dict(color=col, width=2),
            name=label,
            hovertemplate=f"{label}: %{{y:.2f}} µV²/Hz @ %{{x:.1f}} Hz<extra></extra>",
        ))

        ap = _peak_freq(freqs, psd, 8, 13)
        alpha_peaks[label] = ap
        bp_all[label] = {name: _band_power(freqs, psd, lo, hi) for name, (lo, hi), _ in BANDS}

        if ap == ap:
            pv = float(psd[(np.abs(freqs - ap)).argmin()])
            fig.add_vline(x=ap, line_color=col, line_width=1.5, line_dash="dash")
            fig.add_annotation(
                x=ap, y=pv, text=f"α {ap:.1f}",
                showarrow=True, arrowhead=2, arrowcolor=col,
                font=dict(size=10, color=col), yanchor="bottom",
            )

    fig.update_layout(
        xaxis_title="Frequenz (Hz)", yaxis_title="PSD (µV²/Hz)",
        height=260, margin=dict(t=8, b=40, l=65, r=10),
        plot_bgcolor="#fafafa",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, font=dict(size=10)),
    )
    return fig, alpha_peaks, bp_all


def _render_bandpower_and_ratios(bp_all, panel_id):
    for label, bp in bp_all.items():
        total = sum(bp.values()) or 1.0
        bp_pct = {k: v / total * 100 for k, v in bp.items()}

        fig_bp = go.Figure()
        for name, _, col in reversed(BANDS):
            fig_bp.add_trace(go.Bar(
                y=[label], x=[bp_pct[name]], orientation="h",
                marker_color=col, name=name,
                text=f"{bp_pct[name]:.0f}%", textposition="inside",
                hovertemplate=f"{name}: {bp[name]:.1f} µV²  ({bp_pct[name]:.1f}%)<extra></extra>",
            ))
        fig_bp.update_layout(
            xaxis=dict(title="Relativer Anteil (%)", range=[0, 100]),
            height=80, margin=dict(t=2, b=25, l=130, r=10),
            plot_bgcolor="white", showlegend=False, barmode="stack",
        )
        st.plotly_chart(fig_bp, use_container_width=True, key=f"bp_{panel_id}_{label}")

    # Ratios — nur wenn genau 2 Signale (A/P-Vergleich)
    if len(bp_all) == 2:
        labels = list(bp_all.keys())
        post_bp = bp_all[labels[0]]
        ant_bp  = bp_all[labels[1]]
        st.markdown("**Anterior/Posterior-Gradient**")
        g1, g2, g3 = st.columns(3)
        post_alpha = post_bp.get("Alpha", 0)
        ant_alpha  = ant_bp.get("Alpha", 0)
        ap_ratio   = post_alpha / ant_alpha if ant_alpha > 0 else float("nan")
        g1.metric("Alpha posterior/anterior",
                  f"{ap_ratio:.2f}" if ap_ratio == ap_ratio else "—",
                  help="Norm: >1 — Alpha dominiert posterior. <1 = Gradient umgekehrt (pathologisch).")
        post_delta = post_bp.get("Delta", 0)
        ant_delta  = ant_bp.get("Delta", 0)
        g2.metric("Delta anterior", f"{ant_delta/(sum(ant_bp.values()) or 1)*100:.1f}%",
                  help="Frontales Delta erhöht bei Enzephalopathie / tiefer Sedierung.")
        g3.metric("Delta posterior", f"{post_delta/(sum(post_bp.values()) or 1)*100:.1f}%",
                  help="Posteriores Delta pathologisch bei fokaler oder globaler Verlangsamung.")


def _position_bar(ref_start: int, ref_end: int, dur_s: int,
                   color: str, panel_id: str) -> None:
    """Positionsbalken mit Minutenmarken — zeigt wo im Recording die Referenzepoche liegt."""
    fig = go.Figure()
    fig.add_shape(type="rect", xref="x", yref="paper",
                  x0=0, x1=dur_s, y0=0.2, y1=0.8,
                  fillcolor="rgba(200,200,200,0.45)", line_width=0)
    fig.add_shape(type="rect", xref="x", yref="paper",
                  x0=ref_start, x1=ref_end, y0=0, y1=1,
                  fillcolor=color, opacity=0.9, line_width=0)
    # Minutenmarken alle 2 Minuten
    step = 120
    for t_m in range(step, dur_s, step):
        fig.add_vline(x=t_m, line_color="rgba(80,80,80,0.35)",
                      line_width=1, line_dash="dot")
        fig.add_annotation(
            x=t_m, y=1.25, xref="x", yref="paper",
            text=f"{t_m//60} min", showarrow=False,
            font=dict(size=8, color="#777"),
        )
    # Zeitstempel auf dem Fenster
    fig.add_annotation(
        x=(ref_start + ref_end) / 2, y=0.5, xref="x", yref="paper",
        text=f"{ref_start}–{ref_end} s",
        showarrow=False, font=dict(size=10, color="white"),
        bgcolor=color, borderpad=3,
    )
    fig.update_layout(
        xaxis=dict(range=[0, dur_s], showticklabels=False,
                   showgrid=False, zeroline=False),
        yaxis=dict(showticklabels=False, showgrid=False, zeroline=False),
        height=52, margin=dict(t=22, b=2, l=0, r=0),
        plot_bgcolor="white", paper_bgcolor="white",
    )
    st.plotly_chart(fig, use_container_width=True, key=f"pos_{panel_id}")


def _render_single_channel(ch_label, sig_full, fs, dur_s, t_start, t_end, panel_id,
                            multitaper=False, amp_thresh_uv=80.0,
                            all_eeg=None, get_sig_fn=None):
    """Spektrogramm + FFT + Bandpower für einen Kanal."""
    win_label = f"{t_start}–{t_end} s"
    st.markdown(f"#### Kanal: {ch_label}")

    # Spektrogramm
    f_sg, t_sg, Sxx_log = _compute_spectrogram(sig_full, fs)
    trace, tick_vals, tick_text = _spectrogram_trace(f_sg, t_sg, Sxx_log, dur_s)

    fig_sg = go.Figure(trace)
    band_boundaries = sorted({v for _, (lo, hi), _ in BANDS for v in [lo, hi]})
    for bf in band_boundaries:
        if 0.5 < bf < FREQ_MAX:
            fig_sg.add_hline(y=bf, line_color="rgba(255,255,255,0.55)",
                             line_width=1, line_dash="dot")
    for name, (lo, hi), color in BANDS:
        fig_sg.add_annotation(
            x=1.02, y=(lo + hi) / 2, xref="paper", yref="y",
            text=name, showarrow=False, font=dict(size=9, color=color), xanchor="left",
        )
    _add_selection_overlay(fig_sg, t_start, t_end, float(t_sg[-1]) if len(t_sg) else dur_s)
    fig_sg.update_layout(
        xaxis=dict(title="Zeit (min:s)", tickvals=tick_vals, ticktext=tick_text,
                   tickfont=dict(size=10), color="white", gridcolor="rgba(255,255,255,0.1)"),
        yaxis=dict(title="Frequenz (Hz)", range=[1.0, FREQ_MAX],
                   color="white", gridcolor="rgba(255,255,255,0.1)"),
        height=300, margin=dict(t=4, b=45, l=55, r=90),
        plot_bgcolor="black", paper_bgcolor="black", font=dict(color="white"),
    )
    st.plotly_chart(fig_sg, use_container_width=True, key=f"sg_{panel_id}")

    # FFT + Bandpower
    fig_fft, alpha_peaks, bp_all = _fft_figure(
        {ch_label: sig_full}, t_start, t_end, fs, panel_id,
        multitaper=multitaper, amp_thresh_uv=amp_thresh_uv,
    )
    st.markdown(f"**FFT — Fenster {win_label}**")
    st.plotly_chart(fig_fft, use_container_width=True, key=f"fft_{panel_id}")

    st.markdown("**Bandpower**")
    _render_bandpower_and_ratios(bp_all, panel_id)

    ap = alpha_peaks.get(ch_label)
    bp = bp_all.get(ch_label, {})
    total = sum(bp.values()) or 1
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Alpha-Peak", f"{ap:.1f} Hz" if ap == ap else "—",
              help="Norm: 9–11 Hz.")
    k2.metric("Rel. Alpha", f"{bp.get('Alpha',0)/total*100:.1f}%")
    k3.metric("Rel. Delta", f"{bp.get('Delta',0)/total*100:.1f}%")
    k4.metric("Rel. Beta",  f"{bp.get('Beta',0)/total*100:.1f}%")

    # Ratios
    st.markdown("**Klinische Ratios**")
    _d  = bp.get("Delta", 0)
    _t  = bp.get("Theta", 0)
    _a  = bp.get("Alpha", 0) or 1e-9
    _b  = bp.get("Beta",  0) or 1e-9
    _ab = _a + _b
    rv = {
        "Delta/Alpha": _d / _a,
        "Theta/Alpha": _t / _a,
        "Alpha/Theta": _a / (_t or 1e-9),
        "Theta/Beta":  _t / _b,
        "DTAB":        (_d + _t) / _ab,
    }
    r_cols = st.columns(len(RATIO_INFO))
    for cw, (rname, rinfo) in zip(r_cols, RATIO_INFO.items()):
        v = rv[rname]
        lo_n, hi_n = rinfo["normal"]
        badge = "🟢" if (v == v and lo_n <= v <= hi_n) else ("🟡" if v == v else "⚫")
        cw.metric(f"{badge} {rname}", f"{v:.2f}" if v == v else "—",
                  help=f"Norm: {lo_n}–{hi_n} · {rinfo['hint']}")

    # (Referenz-Epoch wird einmalig am Seitenende angeboten — nicht pro Kanal)


def render():
    st.title("📊 EEG-Spektrum")
    st.caption("Spektrogramm, FFT und Bandpower — Konsensus-Panel (O1/O2 + F3/F4) + Einzelkanal.")

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

    import mne
    raw = mne.io.read_raw_edf(edf_path, preload=True, encoding="latin1", verbose=False)
    dur_s = int(edf["duration_s"])

    def _get(ch):
        data, _ = raw[eeg_map[ch], :]
        sig = data[0] * 1e6
        return _highpass(sig, fs, cutoff=1.0)

    # ── Analysefenster-Steuerung ──────────────────────────────────────────────
    st.markdown("---")
    _DUR_OPTIONS = {"30 s": 30, "1 min": 60, "2 min": 120, "5 min": 300,
                    "10 min": 600, "Gesamte Aufnahme": None}
    _dur_keys = list(_DUR_OPTIONS.keys())

    # Sinnvolle Voreinstellung: größte Dauer die ≤ Aufnahmedauer ist (max 5 min)
    _default_dur = "5 min"
    for lbl, sec in _DUR_OPTIONS.items():
        if sec is not None and sec <= dur_s:
            _default_dur = lbl
            break

    wc1, wc2, wc3 = st.columns([5, 2, 3])
    with wc1:
        t_start = st.slider(
            "Fenster-Start (s)", 0, max(0, dur_s - 10), 0, step=5,
            key="spec_t_start",
            format="%d s",
        )
    with wc2:
        dur_label = st.selectbox(
            "Dauer", _dur_keys,
            index=_dur_keys.index(_default_dur),
            key="spec_dur_widget",
            help="Analysefensterlänge ab Start",
        )
    _chosen_sec = _DUR_OPTIONS[dur_label]
    t_end = dur_s if _chosen_sec is None else min(dur_s, t_start + _chosen_sec)
    t_end = max(t_end, t_start + 10)
    with wc3:
        _dur_actual = t_end - t_start
        st.markdown(
            f"<div style='padding:8px 0 4px;font-size:13px;color:#555'>"
            f"⏱ <b>{t_start//60:02d}:{t_start%60:02d}</b> – "
            f"<b>{t_end//60:02d}:{t_end%60:02d}</b> &nbsp;·&nbsp; "
            f"<b>{_dur_actual}s</b> = {_dur_actual/60:.1f} min"
            f"</div>",
            unsafe_allow_html=True,
        )

    with st.expander("⚙️ Analyse-Optionen", expanded=False):
        opt_col1, opt_col2 = st.columns(2)
        with opt_col1:
            use_multitaper = st.toggle(
                "Multitaper-Methode (Thomson 1982)",
                value=False, key="spec_multitaper",
                help=(
                    "Verwendet DPSS-Fenster (NW=3, K=5) statt Welch. "
                    "Schärfere Alpha-Peaks, weniger Spectral Leakage. "
                    "Hilfreich wenn der Alpha-Gipfel in Welch verbreitert erscheint. "
                    "Etwas langsamer bei langen Aufnahmen."
                ),
            )
        with opt_col2:
            use_art_filter = st.toggle(
                "Extremartefakt-Filter (≥150 µV)",
                value=False, key="spec_art_filter",
                help=(
                    "Epochs mit Peak-Amplitude ≥150 µV werden durch lineare Interpolation "
                    "ersetzt — nur für wirklich extreme Artefakte (Elektrode ab, Bewegung). "
                    "Standard: aus — das Gesamtsignal inklusive aller physiologischen Phasen "
                    "(Augen auf/zu, HV) wird vollständig analysiert."
                ),
            )
        amp_thresh = 150.0 if use_art_filter else 9999.0

    all_eeg = sorted(eeg_map.keys())

    # ══════════════════════════════════════════════════════════════════════════
    # KONSENSUS-PANEL — O1+O2 (posterior) vs F3+F4 (anterior)
    # ══════════════════════════════════════════════════════════════════════════
    consensus_channels = {"O1", "O2", "F3", "F4"}
    has_consensus = consensus_channels.issubset(set(all_eeg))

    if has_consensus:
        section_header("🧠 Konsensus-Panel", "Posterior O1+O2 vs. Anterior F3+F4 · ACNS-Empfehlung")
        st.caption(
            "ACNS-Empfehlung für Vigilanz- und Verlangsamungsmonitoring. "
            "Posterior = okzipitaler Alpha-Grundrhythmus · Anterior = frontales Beta/Delta."
        )

        sig_post = (_get("O1") + _get("O2")) / 2
        sig_ant  = (_get("F3") + _get("F4")) / 2

        # Zwei Spektrogramme nebeneinander
        col_p, col_a = st.columns(2)
        for col_w, label, sig, pid in [
            (col_p, "Posterior (O1+O2)", sig_post, "cons_post"),
            (col_a, "Anterior (F3+F4)",  sig_ant,  "cons_ant"),
        ]:
            with col_w:
                st.markdown(f"**{label}**")
                f_sg, t_sg, Sxx_log = _compute_spectrogram(sig, fs)
                trace, tick_vals, tick_text = _spectrogram_trace(f_sg, t_sg, Sxx_log, dur_s)
                fig_sg = go.Figure(trace)
                band_boundaries = sorted({v for _, (lo, hi), _ in BANDS for v in [lo, hi]})
                for bf in band_boundaries:
                    if 0.5 < bf < FREQ_MAX:
                        fig_sg.add_hline(y=bf, line_color="rgba(255,255,255,0.55)",
                                         line_width=1, line_dash="dot")
                for name, (lo, hi), color in BANDS:
                    fig_sg.add_annotation(
                        x=1.03, y=(lo + hi) / 2, xref="paper", yref="y",
                        text=name, showarrow=False,
                        font=dict(size=8, color=color), xanchor="left",
                    )
                _add_selection_overlay(fig_sg, t_start, t_end, float(t_sg[-1]) if len(t_sg) else dur_s)
                fig_sg.update_layout(
                    xaxis=dict(title="Zeit (min:s)", tickvals=tick_vals, ticktext=tick_text,
                               tickfont=dict(size=9), color="white",
                               gridcolor="rgba(255,255,255,0.1)"),
                    yaxis=dict(title="Hz", range=[1.0, FREQ_MAX],
                               color="white", gridcolor="rgba(255,255,255,0.1)"),
                    height=280, margin=dict(t=4, b=40, l=45, r=75),
                    plot_bgcolor="black", paper_bgcolor="black", font=dict(color="white"),
                )
                st.plotly_chart(fig_sg, use_container_width=True, key=f"sg_{pid}")

        # FFT-Overlay: beide Kurven in einem Plot
        mt_label = " · Multitaper" if use_multitaper else " · Welch"
        st.markdown(f"**FFT-Vergleich — Fenster {t_start}–{t_end} s**{mt_label}")
        fig_fft, alpha_peaks, bp_all = _fft_figure(
            {"Posterior (O1+O2)": sig_post, "Anterior (F3+F4)": sig_ant},
            t_start, t_end, fs, "cons",
            multitaper=use_multitaper, amp_thresh_uv=float(amp_thresh),
        )
        st.plotly_chart(fig_fft, use_container_width=True, key="fft_cons")

        # Bandpower + A/P-Gradient
        st.markdown("**Bandpower**")
        _render_bandpower_and_ratios(bp_all, "cons")

        # ── Interne Validierung Konsensus-Panel ────────────────────────────
        section_header("🔍 Referenz-Epoch", "Interne Validierung · 10 s Segment · FFT-Vergleich")

        CONS_VAL_DUR = 10
        cons_ch_opts = [c for c in ["O2", "O1", "F4", "F3"] if c in all_eeg]
        if not cons_ch_opts:
            cons_ch_opts = list(consensus_channels & set(all_eeg))
        cv_col1, cv_col2 = st.columns([3, 5])
        with cv_col1:
            cons_val_ch = st.selectbox(
                "Referenzkanal",
                cons_ch_opts,
                index=0,
                key="cons_val_ch",
                help="Standard: O2 (posterior). Wechsel auf O1 oder frontale Kanäle möglich.",
            )
        cv_col2.caption("Slider anklicken → ← → Pfeiltasten zum Navigieren")
        cons_col = "#27ae60" if cons_val_ch in ("O1", "O2") else "#e67e22"
        cons_val_sig = _get(cons_val_ch)

        # Kanalname-Banner
        st.markdown(
            f"<div style='background:{cons_col}22;border-left:5px solid {cons_col};"
            f"padding:10px 16px;border-radius:6px;margin:6px 0 10px 0'>"
            f"<span style='font-size:26px;font-weight:900;color:{cons_col}'>{cons_val_ch}</span>"
            f"<span style='font-size:13px;color:#555;margin-left:14px'>"
            f"10-Sekunden-Referenzepoche &nbsp;·&nbsp; "
            f"Gesamtaufnahme: {dur_s//60}:{dur_s%60:02d} min</span>"
            f"</div>",
            unsafe_allow_html=True,
        )
        _cdef = max(0, min(dur_s - CONS_VAL_DUR,
                           (t_start + t_end) // 2 - CONS_VAL_DUR // 2))
        cref_start = st.slider(
            "Position im Recording (s)", 0, max(0, dur_s - CONS_VAL_DUR),
            value=_cdef, step=1, key="cons_val_start",
        )
        cref_end = int(cref_start) + CONS_VAL_DUR
        _position_bar(cref_start, cref_end, dur_s, cons_col, "cons")

        cr0, cr1   = int(cref_start * fs), int(cref_end * fs)
        ref_single = cons_val_sig[cr0:cr1]
        # Für FFT-Vergleich: Gesamtfenster des gewählten Kanals
        f_fp, psd_fp = _compute_psd(cons_val_sig[int(t_start*fs):int(t_end*fs)], fs,
                                     multitaper=use_multitaper, amp_thresh_uv=float(amp_thresh))
        f_rp, psd_rp = _compute_psd(ref_single, fs,
                                     multitaper=use_multitaper, amp_thresh_uv=float(amp_thresh))

        # Rohsignal
        st.markdown(
            f"<span style='font-size:15px;font-weight:700;color:{cons_col}'>"
            f"EEG-Rohsignal &mdash; {cons_val_ch}</span>"
            f"<span style='font-size:12px;color:#666;margin-left:8px'>"
            f"{cref_start}&ndash;{cref_end} s &nbsp;&middot;&nbsp; µV (1 Hz HPF)</span>",
            unsafe_allow_html=True,
        )
        t_rp_axis = np.arange(len(ref_single)) / fs + cref_start
        fig_rraw = go.Figure()
        fig_rraw.add_trace(go.Scatter(
            x=t_rp_axis, y=ref_single, mode="lines",
            line=dict(color=cons_col, width=1.3),
            hovertemplate="t=%{x:.2f}s  %{y:.1f} µV<extra></extra>",
        ))
        fig_rraw.add_hline(y=0, line_color="rgba(0,0,0,0.2)", line_width=1)
        for amp_c in [50, -50]:
            fig_rraw.add_hline(y=amp_c, line_color="rgba(100,100,100,0.3)",
                               line_dash="dot", line_width=1,
                               annotation_text=f"{amp_c:+d} µV" if amp_c > 0 else None,
                               annotation_font_size=9)
        sr = max(80.0, float(np.ptp(ref_single)) * 0.6)
        fig_rraw.update_layout(
            xaxis_title="Zeit (s)", yaxis_title="µV",
            height=180, margin=dict(t=4, b=35, l=60, r=10),
            plot_bgcolor="#fafafa", showlegend=False,
        )
        fig_rraw.update_yaxes(range=[-sr, sr])
        st.plotly_chart(fig_rraw, use_container_width=True, key="cons_val_raw")

        if f_fp is not None and f_rp is not None:
            psd_fp_n = psd_fp / (psd_fp.max() or 1)
            psd_rp_n = psd_rp / (psd_rp.max() or 1)
            st.markdown(
                f"<span style='font-size:15px;font-weight:700;color:{cons_col}'>"
                f"FFT-Vergleich &mdash; {cons_val_ch}</span>"
                f"<span style='font-size:12px;color:#666;margin-left:8px'>"
                f"Gesamt {t_start}–{t_end} s (grau) &nbsp;vs.&nbsp; "
                f"Referenz {cref_start}–{cref_end} s (farbig) &nbsp;&middot;&nbsp; normiert</span>",
                unsafe_allow_html=True,
            )
            fig_cv = go.Figure()
            fig_cv.add_trace(go.Scatter(x=f_fp, y=psd_fp_n, mode="lines",
                name=f"Gesamt ({t_start}–{t_end} s)",
                line=dict(color="rgba(150,150,150,0.65)", width=1.5),
                hovertemplate="Gesamt: %{y:.3f} @ %{x:.1f} Hz<extra></extra>"))
            fig_cv.add_trace(go.Scatter(x=f_rp, y=psd_rp_n, mode="lines",
                name=f"{cons_val_ch} Referenz ({cref_start}–{cref_end} s)",
                line=dict(color=cons_col, width=2.8),
                hovertemplate=f"{cons_val_ch}: %{{y:.3f}} @ %{{x:.1f}} Hz<extra></extra>"))
            for bname, (lo, hi), bcol in BANDS:
                r2, g2, b2 = int(bcol[1:3],16), int(bcol[3:5],16), int(bcol[5:7],16)
                fig_cv.add_vrect(x0=lo, x1=hi,
                    fillcolor=f"rgba({r2},{g2},{b2},0.08)", line_width=0,
                    annotation_text=bname, annotation_position="top left",
                    annotation_font_size=9, annotation_font_color=bcol)
            ap_f = _peak_freq(f_fp, psd_fp, 8, 13)
            ap_r = _peak_freq(f_rp, psd_rp, 8, 13)
            for xp, col, lbl in [
                (ap_f, "rgba(120,120,120,0.8)", f"α {ap_f:.1f} Hz (gesamt)"),
                (ap_r, cons_col,               f"α {ap_r:.1f} Hz ({cons_val_ch})"),
            ]:
                if xp == xp:
                    fig_cv.add_vline(x=xp, line_color=col, line_dash="dash",
                                     line_width=1.5, annotation_text=lbl, annotation_font_size=9)
            fig_cv.update_layout(
                xaxis_title="Frequenz (Hz)", yaxis_title="PSD (normiert)",
                height=250, margin=dict(t=8, b=40, l=65, r=10), plot_bgcolor="#fafafa",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, font=dict(size=10)),
            )
            st.plotly_chart(fig_cv, use_container_width=True, key="cons_val_fft")
            if ap_f == ap_f and ap_r == ap_r:
                d = abs(ap_f - ap_r)
                if d <= 0.5:
                    st.success(f"✅ Konsistent: Gesamt {ap_f:.1f} Hz · {cons_val_ch}-Referenz {ap_r:.1f} Hz (Δ {d:.1f} Hz)")
                elif d <= 1.5:
                    st.warning(f"⚠️ Leicht abweichend: {ap_f:.1f} Hz vs. {ap_r:.1f} Hz (Δ {d:.1f} Hz)")
                else:
                    st.error(f"❌ Inkonsistent: {ap_f:.1f} Hz vs. {ap_r:.1f} Hz (Δ {d:.1f} Hz) — Alpha stark zustandsabhängig.")
            else:
                st.info("Kein Alpha-Peak in einem der Segmente detektierbar.")
        else:
            st.warning("Referenz-Segment zu kurz.")

        # Kennzahlen-Kacheln
        bp_p = bp_all.get("Posterior (O1+O2)", {})
        bp_a = bp_all.get("Anterior (F3+F4)", {})
        total_p = sum(bp_p.values()) or 1
        total_a = sum(bp_a.values()) or 1
        ap_post = alpha_peaks.get("Posterior (O1+O2)")
        ap_ant  = alpha_peaks.get("Anterior (F3+F4)")
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Alpha-Peak posterior", f"{ap_post:.1f} Hz" if ap_post == ap_post else "—",
                  help="Norm: 9–11 Hz. Verlangsamung bei Enzephalopathie.")
        k2.metric("Alpha-Peak anterior",  f"{ap_ant:.1f} Hz"  if ap_ant  == ap_ant  else "—",
                  help="Sollte niedriger als posterior sein.")
        k3.metric("Rel. Alpha posterior", f"{bp_p.get('Alpha',0)/total_p*100:.1f}%",
                  help="Dominanter Anteil bei wachem, entspanntem EEG.")
        k4.metric("Rel. Delta anterior",  f"{bp_a.get('Delta',0)/total_a*100:.1f}%",
                  help="Erhöht bei Enzephalopathie / tiefer Sedierung.")


    else:
        missing = consensus_channels - set(all_eeg)
        st.info(f"ℹ️ Konsensus-Panel nicht verfügbar — fehlende Kanäle: {', '.join(sorted(missing))}")

    # ══════════════════════════════════════════════════════════════════════════
    # EINZELKANAL-ANALYSE
    # ══════════════════════════════════════════════════════════════════════════
    section_header("🔬 Einzelkanal-Analyse", "Bandpower · FFT · Klinische Ratios pro Kanal")

    defaults = [c for c in ["O1", "O2"] if c in all_eeg] or all_eeg[:min(2, len(all_eeg))]
    with st.container(border=True):
        selected = st.multiselect(
            "Kanal(e) — max. 2", all_eeg, default=defaults,
            max_selections=2, key="spec_channels",
        )

    if not selected:
        st.info("Bitte mindestens einen Kanal auswählen.")
        return

    for ch_label in selected:
        _render_single_channel(
            ch_label, _get(ch_label), fs, dur_s,
            t_start, t_end, f"ch_{ch_label}",
            multitaper=use_multitaper, amp_thresh_uv=float(amp_thresh),
            all_eeg=all_eeg, get_sig_fn=_get,
        )
        st.markdown("---")

    # ══════════════════════════════════════════════════════════════════════════
    # REFERENZ-EPOCH (einmalig, mit Kanal-Auswahl)
    # ══════════════════════════════════════════════════════════════════════════
    section_header("🔍 Referenz-Epoch", "Interne Validierung · Kanal wählbar · FFT-Overlay")
    st.caption(
        "Wähle einen Kanal und navigiere mit dem Slider (← → Pfeiltasten) zu einem "
        "visuell qualitätsgeprüften 10-Sekunden-Segment. Das Gesamtfenster-Spektrum (grau) "
        "wird mit dem Referenz-Epoch (farbig) verglichen — zeigt ob ein sichtbarer Rhythmus "
        "spektral reproduzierbar ist."
    )

    val_ch_opts = [c for c in ["O2", "O1"] if c in all_eeg] + \
                  [c for c in all_eeg if c not in ("O1", "O2")]
    rv_col1, rv_col2 = st.columns([3, 5])
    with rv_col1:
        val_ch_global = st.selectbox(
            "Kanal für Referenz-Epoch",
            val_ch_opts,
            index=0,
            key="val_ch_global",
            help="Standard: O2 (posteriores Alpha). Wähle jeden verfügbaren EEG-Kanal.",
        )
    rv_col2.caption("Slider anklicken → ← → Pfeiltasten")
    val_sig_global = _get(val_ch_global)
    ch_col_g = "#27ae60" if val_ch_global in ("O1", "O2") else "#e67e22"

    st.markdown(
        f"<div style='background:{ch_col_g}22;border-left:5px solid {ch_col_g};"
        f"padding:10px 16px;border-radius:6px;margin:6px 0 10px 0'>"
        f"<span style='font-size:26px;font-weight:900;color:{ch_col_g}'>{val_ch_global}</span>"
        f"<span style='font-size:13px;color:#555;margin-left:14px'>"
        f"10-Sekunden-Referenzepoche &nbsp;·&nbsp; "
        f"Gesamtaufnahme: {dur_s//60}:{dur_s%60:02d} min</span>"
        f"</div>",
        unsafe_allow_html=True,
    )
    _def_g = max(0, min(dur_s - 10, (t_start + t_end) // 2 - 5))
    ref_start_g = st.slider(
        "Position im Recording (s)", 0, max(0, dur_s - 10),
        value=_def_g, step=1, key="val_start_global",
    )
    ref_end_g = ref_start_g + 10
    _position_bar(ref_start_g, ref_end_g, dur_s, ch_col_g, "global")

    seg_ref_g = val_sig_global[int(ref_start_g * fs):int(ref_end_g * fs)]
    st.markdown(
        f"<span style='font-size:15px;font-weight:700;color:{ch_col_g}'>"
        f"EEG-Rohsignal &mdash; {val_ch_global}</span>"
        f"<span style='font-size:12px;color:#666;margin-left:8px'>"
        f"{ref_start_g}&ndash;{ref_end_g} s &nbsp;&middot;&nbsp; µV (1 Hz HPF)</span>",
        unsafe_allow_html=True,
    )
    t_g = np.arange(len(seg_ref_g)) / fs + ref_start_g
    fig_rg = go.Figure()
    fig_rg.add_trace(go.Scatter(x=t_g, y=seg_ref_g, mode="lines",
        line=dict(color=ch_col_g, width=1.3),
        hovertemplate="t=%{x:.2f}s  %{y:.1f} µV<extra></extra>"))
    fig_rg.add_hline(y=0, line_color="rgba(0,0,0,0.2)", line_width=1)
    for _a in [50, -50]:
        fig_rg.add_hline(y=_a, line_color="rgba(100,100,100,0.3)", line_dash="dot",
                         line_width=1,
                         annotation_text=f"{_a:+d} µV" if _a > 0 else None,
                         annotation_font_size=9)
    _sr_g = max(80.0, float(np.ptp(seg_ref_g)) * 0.6)
    fig_rg.update_layout(xaxis_title="Zeit (s)", yaxis_title="µV",
                         height=180, margin=dict(t=4, b=35, l=60, r=10),
                         plot_bgcolor="#fafafa", showlegend=False)
    fig_rg.update_yaxes(range=[-_sr_g, _sr_g])
    st.plotly_chart(fig_rg, use_container_width=True, key="val_raw_global")

    f_fg, psd_fg = _compute_psd(val_sig_global[int(t_start*fs):int(t_end*fs)], fs,
                                 multitaper=use_multitaper, amp_thresh_uv=float(amp_thresh))
    f_rg2, psd_rg = _compute_psd(seg_ref_g, fs,
                                  multitaper=use_multitaper, amp_thresh_uv=float(amp_thresh))

    if f_fg is not None and f_rg2 is not None:
        psd_fg_n  = psd_fg  / (psd_fg.max()  or 1)
        psd_rg_n  = psd_rg  / (psd_rg.max()  or 1)
        st.markdown(
            f"<span style='font-size:15px;font-weight:700;color:{ch_col_g}'>"
            f"FFT-Vergleich &mdash; {val_ch_global}</span>"
            f"<span style='font-size:12px;color:#666;margin-left:8px'>"
            f"Gesamt {t_start}–{t_end} s (grau) &nbsp;vs.&nbsp; "
            f"Referenz {ref_start_g}–{ref_end_g} s (farbig) &nbsp;&middot;&nbsp; normiert</span>",
            unsafe_allow_html=True,
        )
        fig_vg = go.Figure()
        fig_vg.add_trace(go.Scatter(x=f_fg, y=psd_fg_n, mode="lines",
            name=f"Gesamt ({t_start}–{t_end} s)",
            line=dict(color="rgba(150,150,150,0.65)", width=1.5),
            hovertemplate="Gesamt: %{y:.3f} @ %{x:.1f} Hz<extra></extra>"))
        fig_vg.add_trace(go.Scatter(x=f_rg2, y=psd_rg_n, mode="lines",
            name=f"{val_ch_global} Referenz ({ref_start_g}–{ref_end_g} s)",
            line=dict(color=ch_col_g, width=2.8),
            hovertemplate=f"{val_ch_global}: %{{y:.3f}} @ %{{x:.1f}} Hz<extra></extra>"))
        ap_fg = _peak_freq(f_fg, psd_fg, 8, 13)
        ap_rg = _peak_freq(f_rg2, psd_rg, 8, 13)
        for xp, col, lbl in [
            (ap_fg, "rgba(120,120,120,0.8)", f"α {ap_fg:.1f} Hz (gesamt)"),
            (ap_rg, ch_col_g,               f"α {ap_rg:.1f} Hz ({val_ch_global})"),
        ]:
            if xp == xp:
                fig_vg.add_vline(x=xp, line_color=col, line_dash="dash",
                                 line_width=1.5, annotation_text=lbl, annotation_font_size=9)
        for bname, (lo, hi), bcol in BANDS:
            r2, g2, b2 = int(bcol[1:3],16), int(bcol[3:5],16), int(bcol[5:7],16)
            fig_vg.add_vrect(x0=lo, x1=hi, fillcolor=f"rgba({r2},{g2},{b2},0.08)",
                             line_width=0, annotation_text=bname, annotation_position="top left",
                             annotation_font_size=9, annotation_font_color=bcol)
        fig_vg.update_layout(
            xaxis_title="Frequenz (Hz)", yaxis_title="PSD (normiert)",
            height=250, margin=dict(t=8, b=40, l=65, r=10), plot_bgcolor="#fafafa",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, font=dict(size=10)),
        )
        st.plotly_chart(fig_vg, use_container_width=True, key="val_fft_global")
        if ap_fg == ap_fg and ap_rg == ap_rg:
            d = abs(ap_fg - ap_rg)
            if d <= 0.5:
                st.success(f"✅ Konsistent: Gesamt {ap_fg:.1f} Hz · {val_ch_global}-Referenz {ap_rg:.1f} Hz (Δ {d:.1f} Hz)")
            elif d <= 1.5:
                st.warning(f"⚠️ Leicht abweichend: {ap_fg:.1f} Hz vs. {ap_rg:.1f} Hz (Δ {d:.1f} Hz) — Augen-zu-Segment wählen?")
            else:
                st.error(f"❌ Inkonsistent: {ap_fg:.1f} Hz vs. {ap_rg:.1f} Hz (Δ {d:.1f} Hz) — Alpha zustandsabhängig.")
        else:
            st.info("Kein Alpha-Peak detektierbar.")
    else:
        st.warning("Segment zu kurz für PSD.")

    # ══════════════════════════════════════════════════════════════════════════
    # HEMISPHÄRISCHE ASYMMETRIE
    # ══════════════════════════════════════════════════════════════════════════
    asym_chs = [c for c in ["O1", "O2", "F3", "F4"] if c in all_eeg]
    if len(asym_chs) >= 2 and ("O1" in asym_chs and "O2" in asym_chs
                                or "F3" in asym_chs and "F4" in asym_chs):
        section_header("🔁 Hemisphärische Asymmetrie", "AI = (L−R)/(L+R) × 100% · nach Frequenzband · Nuwer 1997", color="#2980b9")
        st.markdown(
            "<div style='background:#f0f4ff;border-left:4px solid #2980b9;"
            "padding:12px 16px;border-radius:6px;margin-bottom:12px'>"
            "<b>Was wird hier gemessen?</b><br>"
            "Der <b>Asymmetrie-Index (AI)</b> vergleicht die Spektralleistung der linken vs. "
            "rechten Hemisphäre pro Frequenzband:<br>"
            "<code>AI = (P<sub>links</sub> − P<sub>rechts</sub>) / "
            "(P<sub>links</sub> + P<sub>rechts</sub>) × 100 %</code><br><br>"
            "<b>Warum nach Frequenzbändern aufgeteilt?</b> Weil Läsionen frequenzspezifisch "
            "wirken: Eine Ischämie erzeugt typisch <i>Delta-Asymmetrie</i> ipsilateral; "
            "eine Substanzdefekt-Narbe zeigt oft auch <i>Alpha-Reduktion</i> auf der "
            "betroffenen Seite. Verschiedene Bänder können gleichzeitig asymmetrisch sein "
            "oder nicht — das Muster ist klinisch interpretierbar.<br><br>"
            "🟢 |AI| ≤ 20 % — physiologisch normal &nbsp;&nbsp;"
            "🔴 |AI| > 20 % — pathologisch verdächtig (Nuwer 1997, ACNS)</div>",
            unsafe_allow_html=True,
        )
        # PSDs berechnen
        _ch_psds = {}
        for _ch in asym_chs:
            _f_ch, _p_ch = _compute_psd(
                _get(_ch)[int(t_start*fs):int(t_end*fs)], fs,
                multitaper=use_multitaper, amp_thresh_uv=float(amp_thresh),
            )
            if _f_ch is not None:
                _ch_psds[_ch] = {bn: _band_power(_f_ch, _p_ch, lo, hi)
                                  for bn, (lo, hi), _ in BANDS}

        def _ai(l_val, r_val):
            denom = l_val + r_val
            return (l_val - r_val) / denom * 100 if denom > 1e-9 else float("nan")

        for pair_label, l_ch, r_ch in [("Okzipital — O1 (links) vs. O2 (rechts)", "O1", "O2"),
                                         ("Frontal — F3 (links) vs. F4 (rechts)",   "F3", "F4")]:
            if l_ch not in _ch_psds or r_ch not in _ch_psds:
                continue
            lbp = _ch_psds[l_ch]
            rbp = _ch_psds[r_ch]
            st.markdown(f"**{pair_label}**")
            ai_cols = st.columns(4)
            for col_w, bname in zip(ai_cols, ["Delta", "Theta", "Alpha", "Beta"]):
                ai_val = _ai(lbp.get(bname, 0), rbp.get(bname, 0))
                if ai_val != ai_val:
                    col_w.metric(f"AI {bname}", "—")
                    continue
                badge = "🟢" if abs(ai_val) <= 20 else "🔴"
                direction = f"links >{r_ch}" if ai_val > 0 else f"rechts >{l_ch}"
                col_w.metric(
                    f"{badge} AI {bname}",
                    f"{ai_val:+.1f}%",
                    help=(
                        f"{l_ch} = {lbp.get(bname,0):.1f} µV²  "
                        f"{r_ch} = {rbp.get(bname,0):.1f} µV²  "
                        f"({direction}) · |AI|>20% pathologisch verdächtig"
                    ),
                )

    # ══════════════════════════════════════════════════════════════════════════
    # APPENDIX — Methodenerklärungen
    # ══════════════════════════════════════════════════════════════════════════
    st.markdown("---")
    with st.expander("📖 Appendix — Parameter, Methoden und klinische Interpretation", expanded=False):
        st.markdown("""
### Quantitative EEG-Analyse (qEEG) — Methodengrundlagen

---

#### Spektralanalyse — Welch vs. Multitaper

Das EEG-Signal wird mittels **Welch-Methode** (Standard) oder **Multitaper-Methode** (optional) in sein Leistungsspektrum zerlegt.

- **Welch**: Signal wird in überlappende Epochen (4 s, 50 % Überlapp) zerlegt, jede mit Hann-Fenster multipliziert, dann FFT und Mittelung. Schnell, gut für lange Aufnahmen.
- **Multitaper (Thomson 1982)**: Verwendet mehrere orthogonale DPSS-Fenster (NW=3, K=5), deren PSDs gewichtet gemittelt werden. Geringeres Spectral Leakage → schärfere Peaks, besonders hilfreich bei niedrigem SNR im Alpha-Band. Empfohlen wenn Alpha in Welch verbreitert oder schwach erscheint.

Vorverarbeitung: **1 Hz Hochpassfilter** (Butterworth 4. Ordnung) entfernt DC-Drift und Elektroden-Offsetartefakte — physiologisch unbedenklich, da EEG-Nutzspektrum ≥ 1 Hz liegt.

---

#### Frequenzbänder (klinische Definition)

| Band | Bereich | Klinische Bedeutung |
|------|---------|---------------------|
| **Delta** | 1–4 Hz | Tiefschlaf, schwere Enzephalopathie, Läsionskorrelat |
| **Theta** | 4–8 Hz | Leichter Schlaf, Schläfrigkeit, fokale Verlangsamung |
| **Alpha** | 8–13 Hz | Wachheit mit Augen zu, okzipitaler Grundrhythmus, Reaktivität |
| **Beta** | 13–30 Hz | Aktivierung, Medikamenteneffekte (BZD, Barbiturate ↑ Beta) |

---

#### Relative Power (%)

$$\\text{Rel. Power}_{Band} = \\frac{P_{Band}}{P_{Delta} + P_{Theta} + P_{Alpha} + P_{Beta}} \\times 100\\%$$

**Klinischer Goldstandard** für interindividuelle Vergleiche. Eliminiert die stark variable absolute Amplitude (Schädeldicke, Elektrodenimpedanz). Bei gesunden wachen Erwachsenen mit Augen zu dominiert Alpha okzipital (30–50 % der Gesamtpower).

---

#### Alpha Peak Frequency (APF)

Die Frequenz des höchsten Ausschlags im Alpha-Band (8–13 Hz), okzipital gemessen.

- **Normbereich**: 9–11 Hz (Augen zu, entspannt)
- **Klinische Bedeutung**: Die APF ist der stabilste spektrale Parameter des Individuums — vergleichbar einem biologischen Fingerabdruck. Im Längsschnitt signalisiert ein APF-Abfall bereits bei Werten formal im Normbereich einen frühen kognitiven Decline (Petersen 2000, Jelic 2000). Ein APF < 8 Hz ist ein sensitiver Marker für **Alzheimer-Demenz** und metabolische Enzephalopathien.
- **Methodik**: Hier berechnet als Frequenz des PSD-Maximums im Fenster 8–13 Hz.

---

#### Klinische Frequenz-Ratios

**Theta/Alpha-Ratio (TAR)**
$$\\text{TAR} = \\frac{P_{Theta}}{P_{Alpha}}$$
Normbereich: 0.2–0.7. Frühmarker für **diffuse kortikale Funktionsstörung** und kognitiven Decline. Sensitiver als einzelne Bandpower-Werte (Moretti 2009, Rossini 2008).

**Delta/Alpha-Ratio (DAR)**
$$\\text{DAR} = \\frac{P_{Delta}}{P_{Alpha}}$$
Normbereich: 0–1.5. Erhöht bei fokalen Läsionen und globaler Verlangsamung.

**DTAB-Ratio (Slow-to-Fast-Index)**
$$\\text{DTAB} = \\frac{P_{Delta} + P_{Theta}}{P_{Alpha} + P_{Beta}}$$
Normbereich: < 0.5. Der sensitivste Einzelmarker für **diffuse kortikale Funktionsstörung** — vereint alle langsamen Aktivitäten im Zähler gegen alle schnellen im Nenner. Erhöht bei metabolisch-toxischen Enzephalopathien, Demenzen im Frühstadium, vaskulären Läsionen (Brenner 2005, Soininen 1991).

**Alpha/Theta-Ratio**
Normbereich: 1.5–6. Umgekehrtes Maß für Vigilanz. Sinkt bei Schläfrigkeit, Vigilanzminderung, leichter Sedierung.

**Theta/Beta-Ratio (TBR)**
Normbereich: 0.5–2. Historisch in ADHS-Diagnostik bei Kindern diskutiert. Bei Erwachsenen Marker für Schläfrigkeit (erhöht) oder kortikale Aktivierung (erniedrigt). Isoliert bei Erwachsenen wenig spezifisch.

---

#### Hemisphärische Asymmetrie-Index (AI)

$$\\text{AI}_{Band} = \\frac{P_{links} - P_{rechts}}{P_{links} + P_{rechts}} \\times 100\\%$$

- Positiv = links dominant, negativ = rechts dominant
- **Pathologisch**: |AI| > 20 % in einem Band, konsistent über mehrere Bänder
- **Klinische Bedeutung**: Herdförmige Störungen (Substanzdefekte, Ischämien, Tumoren), einseitige Karotisstenose, fokale Epilepsie. Im klinischen Alltag >20 % als grober Schwellenwert, bei konsistenter Asymmetrie über mehrere Bänder hochverdächtig (Nuwer 1997, ACNS-Guideline).
- Physiologische geringe Asymmetrien (< 15 %) sind normal, besonders frontal.

---

#### Anterior-Posterior-Gradient (A/P-Gradient)

Bei gesunden wachen Erwachsenen (Augen zu):
- **Posterior** (O1/O2): Alpha-Dominanz (okzipitaler Grundrhythmus)
- **Anterior** (F3/F4): Beta-Dominanz (kortikale Aktivierung), deutlich weniger Alpha

Alpha posterior/anterior-Ratio > 1.0 gilt als normal. Umkehrung oder Fehlen des Gradienten ist pathologisch (diffuse Verlangsamung, schwere Enzephalopathie).

---

#### Interne Validierung durch Referenz-Epoch

Da Alpha stark zustandsabhängig ist (verschwindet bei Augen auf, Hyperventilation, Aufmerksamkeit), mittelt die Gesamtfenster-Analyse über heterogene Hirnzustände. Die **Referenz-Epoch-Methode** ermöglicht:

1. Auswahl eines visuell qualitätsgeprüften 10-Sekunden-Segments (z.B. sichtbares posteriores Alpha im EEG-Viewer)
2. Vergleich des normierten Spektrums des Referenzsegments mit dem Gesamtfenster
3. Konsistenzcheck: Δ APF ≤ 0.5 Hz → "valide". Δ > 1.5 Hz → Gesamtanalyse durch Nicht-Alpha-Phasen dominiert

Diese interne Kreuzvalidierung ersetzt keine normative Datenbank, erhöht aber die Interpretationssicherheit erheblich — insbesondere bei kurzen Aufnahmen oder unzureichend dokumentiertem Vigilanzstatus.

---

#### Quellen (Auswahl)

- Brenner R. (2005). The interpretation of the EEG in dementia. *Dementia and Geriatric Cognitive Disorders*
- Moretti D. et al. (2009). *Clinical Neurophysiology* — qEEG markers in MCI
- Nuwer M. (1997). Assessment of digital EEG. *Neurology* 49(1):277–292
- Thomson D.J. (1982). Spectrum estimation and harmonic analysis. *Proc. IEEE* 70:1055–1096
- ACNS: American Clinical Neurophysiology Society Guidelines for qEEG
""")
        st.caption("Normwerte gelten für wache Erwachsene, Augen zu, artefaktarme Aufnahme. Zustandsabhängige Variabilität (Augen auf/zu, Schläfrigkeit) ist der häufigste Confounder.")
