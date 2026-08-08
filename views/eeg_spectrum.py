"""EEG-Spektralanalyse — Konsensus A/P-Panel + Einzelkanal-Analyse."""

import numpy as np
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy.signal import spectrogram
from scipy.signal import butter, filtfilt
from scipy.signal.windows import dpss

from core.shared import load_and_prepare, section_header, get_patient_info, safe_slider

# ── Frequenzbänder ────────────────────────────────────────────────────────────
# Delta-Untergrenze 1.0 Hz — konsistent mit dem 1-Hz-Hochpass und der 1-Hz-PSD-Maske
BANDS = [
    ("Delta",  (1.0,  4.0),  "#4a90d9"),
    ("Theta",  (4.0,  8.0),  "#9b59b6"),
    ("Alpha",  (8.0, 13.0),  "#27ae60"),
    ("Beta",  (13.0, 30.0),  "#e67e22"),
]
FREQ_MAX = 30.0
BAND_DICT  = {name: rng for name, rng, _ in BANDS}
BAND_COLOR = {name: col for name, _, col in BANDS}

# dir = Richtung, in der der Wert pathologisch wird (nicht symmetrisch!):
#   "high" → nur erhöhte Werte auffällig (grün ≤ normal-hi, gelb ≤ amber, rot darüber)
#   "low"  → nur erniedrigte Werte auffällig (grün ≥ normal-lo, gelb ≥ amber, rot darunter)
# amber = Grenze zwischen gelb (grenzwertig) und rot (deutlich pathologisch).
RATIO_INFO = {
    "Delta/Alpha":  {"normal": (0.0, 1.5), "dir": "high", "amber": 3.0,
                     "hint": "DAR — erhöht bei diffuser/fokaler Verlangsamung & Enzephalopathie"},
    "Theta/Alpha":  {"normal": (0.2, 0.7), "dir": "high", "amber": 1.4,
                     "hint": "TAR — Frühmarker diffuser Enzephalopathie / kognitiven Declines"},
    "Alpha/Theta":  {"normal": (1.5, 6.0), "dir": "low",  "amber": 0.8,
                     "hint": "Vigilanzmaß — erniedrigt bei Schläfrigkeit / Vigilanzminderung"},
    "Theta/Beta":   {"normal": (0.5, 2.0), "dir": "high", "amber": 4.0,
                     "hint": "TBR — erhöht bei Schläfrigkeit; isoliert wenig spezifisch"},
    "DTAB":         {"normal": (0.0, 0.5), "dir": "high", "amber": 1.0,
                     "hint": "(Delta+Theta)/(Alpha+Beta) — sensitivster Einzelmarker diffuser Funktionsstörung"},
}


def _ratio_zone(rinfo: dict, v: float):
    """Richtungsabhängige Ampel für eine klinische Ratio → (farbe, emoji, label)."""
    if v != v:
        return "#7f8c8d", "⚫", "—"
    lo_n, hi_n = rinfo["normal"]
    if rinfo["dir"] == "high":
        if v <= hi_n:
            return "#27ae60", "🟢", "normal"
        if v <= rinfo["amber"]:
            return "#e6a817", "🟡", "leicht erhöht"
        return "#c0392b", "🔴", "deutlich erhöht"
    # dir == "low": nur niedrige Werte auffällig
    if v >= lo_n:
        return "#27ae60", "🟢", "normal"
    if v >= rinfo["amber"]:
        return "#e6a817", "🟡", "leicht erniedrigt"
    return "#c0392b", "🔴", "deutlich erniedrigt"


def _alpha_band(age) -> tuple:
    """Altersadaptives Alpha-Suchfenster für die Peak-Bestimmung.

    Der posteriore Grundrhythmus reift altersabhängig: bei kleinen Kindern liegt er
    tiefer (~6–9 Hz) und steigt bis ~10 Hz im Jugendalter. Im höheren Alter kann er
    leicht verlangsamen. Konservativ gehalten — für Erwachsene identisch zum
    klinischen Standard 8–13 Hz, damit sich etablierte Befunde nicht verschieben.

    Rückgabe: (lo, hi) Suchgrenzen in Hz.
    """
    try:
        a = float(age)
    except (TypeError, ValueError):
        return (8.0, 13.0)
    if a < 6:
        return (6.0, 11.0)
    if a < 10:
        return (7.0, 12.0)
    return (8.0, 13.0)


def _highpass(sig: np.ndarray, fs: float, cutoff: float = 1.0) -> np.ndarray:
    """1 Hz Hochpassfilter — entfernt DC-Drift und Bewegungsartefakte."""
    nyq = fs / 2
    b, a = butter(4, cutoff / nyq, btype="high")
    return filtfilt(b, a, sig)


def _band_power(freqs, psd, lo, hi):
    mask = (freqs >= lo) & (freqs < hi)
    return float(np.trapezoid(psd[mask], freqs[mask])) if mask.sum() > 1 else 0.0


def _peak_freq(freqs, psd, lo, hi):
    mask = (freqs >= lo) & (freqs < hi)
    return float(freqs[mask][np.argmax(psd[mask])]) if mask.sum() > 1 else float("nan")


@st.cache_data(show_spinner="Berechne LZC-Komplexität…")
def _lzc_cached(seg_bytes: bytes, n: int, fs: float) -> dict:
    """Gecachte LZC-Berechnung (langsam, O(N²)) — Key = Segment-Bytes."""
    from analysis.complexity import lziv_complexity
    x = np.frombuffer(seg_bytes, dtype=np.float64)[:n]
    return lziv_complexity(x, fs)


def _group_header(number: str, title: str, subtitle: str) -> None:
    """Kräftigere Gruppen-Ebene NUR für diese Seite (nummeriert + Farbband) — bewusst
    getrennt von core.shared.section_header (app-weit an 28 Stellen in 7 Dateien genutzt,
    daher nicht global verändert). Schafft eine sichtbare zweite Hierarchie-Ebene über den
    bestehenden Sektionen (User-Feedback 2026-08-03: Seite wirkte als „Einheitsbrei")."""
    st.markdown(
        "<div style='margin:34px 0 6px 0;padding:14px 18px;border-radius:10px;"
        "background:linear-gradient(90deg,#1c283a 0%,#2c3e50 100%);'>"
        f"<span style='display:inline-block;background:#ffffff22;border-radius:6px;"
        f"padding:2px 10px;font-size:13px;font-weight:800;color:#fff;margin-right:10px'>{number}</span>"
        f"<span style='font-size:17px;font-weight:800;color:#fff'>{title}</span>"
        f"<span style='font-size:12px;color:#ffffffaa;margin-left:12px'>{subtitle}</span>"
        "</div>", unsafe_allow_html=True)


def _active_settings_note(use_multitaper: bool, use_art_filter: bool) -> None:
    """Zeigt sichtbar, welche globalen ⚙️-Einstellungen diese Sektion gerade beeinflussen —
    Multitaper/Artefaktfilter wirken seitenweit, nicht lokal; ohne diesen Hinweis muss man
    zum Nachschauen nach oben scrollen (User-Feedback 2026-08-03)."""
    _mt = "Multitaper" if use_multitaper else "Welch"
    _af = f"an (≥150 µV)" if use_art_filter else "aus"
    st.caption(f"⚙️ Aktive Einstellungen dieser Sektion: Methode **{_mt}** · "
               f"Extremartefakt-Filter **{_af}** — änderbar oben in den Analyse-Optionen.")


@st.cache_data(show_spinner="Berechne A/P-Gradient (PAR)…")
def _compute_par(edf_path, t_start, t_end, a_lo, a_hi, multitaper, amp_thresh):
    """Anterior-Posterior-Ratio der absoluten Alpha-Power über den ganzen Kopf.

    PAR = geom. Mittel(posteriore absolute Alpha-Fläche) / geom. Mittel(anteriore)
    (Colombo 2023 / Maschke 2025). Split an der Cz-Linie (|y|≤0,2 ausgeschlossen).
    PAR > 1 = posterior-dominantes Alpha (wach/normal), < 1 = anteriorisiert
    (Bewusstseinsminderung/Anästhesie). Zusätzlich Exponent-Gradient (post−ant, 1–20 Hz).
    """
    import mne
    from core.shared import ELECTRODE_POS
    from analysis.aperiodic import fit_aperiodic
    edf = load_and_prepare(edf_path)
    fs = edf["sfreq"]
    eeg_map = edf["eeg_map"]
    raw = mne.io.read_raw_edf(edf_path, preload=True, encoding="latin1", verbose=False)
    i0, i1 = int(t_start * fs), int(t_end * fs)
    post_a, ant_a, post_e, ant_e = [], [], [], []
    for short, idx in eeg_map.items():
        pos = ELECTRODE_POS.get(short)
        if pos is None or abs(pos[1]) <= 0.2:      # unbekannt oder Cz-Linie → ausschließen
            continue
        sig = _highpass(raw[idx, :][0][0] * 1e6, fs, 1.0)
        f, p = _compute_psd(sig[i0:i1], fs, multitaper=multitaper, amp_thresh_uv=amp_thresh)
        if f is None:
            continue
        m = (f >= a_lo) & (f < a_hi)
        area = float(np.trapezoid(p[m], f[m])) if m.sum() > 1 else float("nan")
        r = fit_aperiodic(f, p, 1, 20)
        exp = r["exponent"] if r else float("nan")
        if pos[1] > 0.2:                            # anterior
            if area == area and area > 0: ant_a.append(area)
            if exp == exp: ant_e.append(exp)
        else:                                       # posterior
            if area == area and area > 0: post_a.append(area)
            if exp == exp: post_e.append(exp)

    def _geo(xs):
        return float(np.exp(np.mean(np.log(xs)))) if xs else float("nan")

    par = (_geo(post_a) / _geo(ant_a)) if (post_a and ant_a) else float("nan")
    exp_grad = (float(np.mean(post_e)) - float(np.mean(ant_e))) if (post_e and ant_e) else float("nan")
    return {"par": par, "exp_grad": exp_grad, "n_post": len(post_a), "n_ant": len(ant_a)}


def _spectral_edge(freqs, psd, pct):
    """Spektrale Edge-Frequenz: Frequenz, unter der pct der Gesamtleistung liegt.

    pct=0.95 → SEF95 (Vigilanz-/Sedierungs-/Enzephalopathie-Marker), pct=0.50 →
    Medianfrequenz. Sinkt bei Verlangsamung. Berechnet über das Analyseband (1–30 Hz)
    per kumulierter Leistung mit linearer Interpolation zwischen den Bins.
    """
    if len(freqs) < 2:
        return float("nan")
    cum = np.cumsum(psd)
    tot = cum[-1]
    if tot <= 0:
        return float("nan")
    cum = cum / tot
    idx = int(np.searchsorted(cum, pct))
    if idx == 0:
        return float(freqs[0])
    if idx >= len(freqs):
        return float(freqs[-1])
    # lineare Interpolation zwischen idx-1 und idx für Sub-Bin-Genauigkeit
    c0, c1 = cum[idx - 1], cum[idx]
    f0, f1 = freqs[idx - 1], freqs[idx]
    if c1 == c0:
        return float(f1)
    return float(f0 + (pct - c0) / (c1 - c0) * (f1 - f0))


def _peak_freq_cog(freqs, psd, lo, hi):
    """Alpha-Peak per Schwerpunkt (Center of Gravity / Individual Alpha Frequency).

    Robuster als roher argmax: bei bimodalem Alpha (z.B. Gipfel bei 9 und 11 Hz)
    springt argmax instabil, der Schwerpunkt liefert einen stabilen Mittelwert.

    Vor der Schwerpunktbildung wird eine **lineare Baseline** zwischen den
    Bandrändern abgezogen (Näherung des 1/f-Untergrunds + Theta-Ausläufer),
    damit die absteigende Flanke des Theta-Bandes den Schwerpunkt nicht
    künstlich nach unten zieht (Klimesch, Individual Alpha Frequency).

    CoG = Σ(fᵢ·Pᵢ) / Σ(Pᵢ)  über das (baseline-korrigierte) Alpha-Band.
    """
    mask = (freqs >= lo) & (freqs < hi)
    if mask.sum() < 3:
        return float("nan")
    f = freqs[mask]
    p = psd[mask].astype(float).copy()
    # 1/f-/Theta-Untergrund als Gerade zwischen den Bandrändern approximieren
    baseline = np.linspace(p[0], p[-1], len(p))
    p = p - baseline
    p[p < 0] = 0.0
    if p.sum() <= 0:
        return float("nan")
    return float(np.sum(f * p) / np.sum(p))


def _epoch_starts(n: int, nperseg: int):
    """Startindizes überlappender Epochen (50 % Überlapp)."""
    step = nperseg // 2
    return list(range(0, n - nperseg + 1, step))


def _compute_psd(sig, fs, nperseg=None, multitaper=False, amp_thresh_uv=9999.0):
    """Leistungsspektraldichte (Welch oder Multitaper), epochenweise gemittelt.

    Artefaktbehandlung: Epochen, deren Peak-to-Peak-Amplitude > amp_thresh_uv liegt,
    werden **komplett aus dem Mittel weggelassen** (statt per linearer Brücke
    interpoliert — das erzeugte Steigungssprünge und spektrales Splatter). Bleiben
    zu wenige saubere Epochen übrig (< 1), wird ausnahmsweise die gesamte (auch
    artefaktbehaftete) Epochenmenge verwendet, damit weiterhin ein Spektrum entsteht.
    """
    nperseg = nperseg or min(int(fs * 4), len(sig) // 2, 1024)
    if nperseg < 64:
        return None, None

    starts = _epoch_starts(len(sig), nperseg)
    if not starts:
        return None, None

    # Saubere Epochen selektieren (ptp <= Schwelle); Fallback auf alle Epochen
    clean_starts = [i for i in starts if np.ptp(sig[i:i + nperseg]) <= amp_thresh_uv]
    if not clean_starts:
        clean_starts = starts

    freqs = np.fft.rfftfreq(nperseg, d=1.0 / fs)

    if multitaper:
        # Thomson (1982) DPSS — NW=3, K=5 gut für Alpha-Detektion (bandwidth ≈ 1.5 Hz)
        NW, K = 3, 5
        tapers, eigs = dpss(nperseg, NW, K, return_ratios=True)
        psds = []
        for i in clean_starts:
            epoch = sig[i:i + nperseg]
            epoch = epoch - epoch.mean()
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
    else:
        # Welch, epochenweise (Hann-Fenster, Density-Skalierung wie scipy.welch)
        win = np.hanning(nperseg)
        U = np.sum(win ** 2)                       # Fensterleistung
        scale_2s = np.full(len(freqs), 2.0)        # einseitiges Spektrum: ×2 …
        scale_2s[0] = 1.0                          # … außer DC
        if nperseg % 2 == 0:
            scale_2s[-1] = 1.0                     # … und Nyquist (bei gerader Länge)
        psds = []
        for i in clean_starts:
            epoch = sig[i:i + nperseg]
            epoch = epoch - epoch.mean()           # detrend='constant'
            X = np.fft.rfft(epoch * win)
            psds.append(scale_2s * (np.abs(X) ** 2) / (fs * U))

    if not psds:
        return None, None
    psd = np.mean(psds, axis=0)

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


def _bandpower_trend(f_sg, t_sg, Sxx_log, dur_s):
    """Liniendiagramm: relative Bandpower über die Zeit (aus Spektrogramm-Daten)."""
    Sxx_lin = 10 ** (Sxx_log / 10)
    trend = {}
    for name, (lo, hi), color in BANDS:
        mask = (f_sg >= lo) & (f_sg < hi)
        trend[name] = (Sxx_lin[mask, :].sum(axis=0), color)

    total = sum(v for v, _ in trend.values()) + 1e-30
    tick_vals = list(range(0, int(t_sg[-1]) + 1, 60))
    tick_text  = [f"{v//60}:{v%60:02d}" for v in tick_vals]

    fig = go.Figure()
    for name, (power, color) in trend.items():
        rel = power / total * 100
        # gleitender Mittelwert über ~4 s für ruhigere Kurve
        k = max(1, len(rel) // (int(t_sg[-1]) // 4 + 1))
        smooth = np.convolve(rel, np.ones(k)/k, mode="same")
        fig.add_trace(go.Scatter(
            x=t_sg, y=smooth, mode="lines", name=name,
            line=dict(color=color, width=1.8),
            hovertemplate=f"{name}: %{{y:.1f}}%  t=%{{x:.0f}}s<extra></extra>",
        ))

    fig.update_layout(
        xaxis=dict(title="Zeit (min:s)", tickvals=tick_vals, ticktext=tick_text,
                   tickfont=dict(size=10), gridcolor="rgba(200,200,200,0.2)"),
        yaxis=dict(title="Rel. Power (%)", range=[0, 100],
                   gridcolor="rgba(200,200,200,0.2)"),
        height=200, margin=dict(t=4, b=40, l=55, r=10),
        plot_bgcolor="#111", paper_bgcolor="#111",
        font=dict(color="white"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    font=dict(size=10, color="white")),
    )
    return fig


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
                multitaper=False, amp_thresh_uv=9999.0, alpha_band=(8.0, 13.0)):
    """FFT-Overlay mehrerer Signale in einem Plot."""
    a_lo, a_hi = alpha_band
    colors = {"Posterior (O1+O2)": "#27ae60", "Anterior (F3+F4)": "#e67e22",
              "O1": "#27ae60", "O2": "#2ecc71", "F3": "#e67e22", "F4": "#f39c12"}
    fig = go.Figure()
    alpha_peaks = {}
    alpha_cog = {}
    bp_all = {}

    i0 = int(t_start * fs)
    i1 = int(t_end * fs)

    for label, sig in signals.items():
        # sig kann ein einzelnes Signal ODER eine Liste von Kanalsignalen sein.
        # Bei mehreren Kanälen werden die PSDs gemittelt (nicht die Zeitsignale) —
        # verhindert Phasenauslöschung, wenn z.B. O1/O2 gegenphasige Anteile haben.
        if isinstance(sig, (list, tuple)):
            _psds = []
            freqs = None
            for _s in sig:
                _fr, _pp = _compute_psd(_s[i0:i1], fs, multitaper=multitaper,
                                        amp_thresh_uv=amp_thresh_uv)
                if _fr is not None:
                    freqs = _fr
                    _psds.append(_pp)
            if not _psds:
                continue
            psd = np.mean(_psds, axis=0)
        else:
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

        ap = _peak_freq(freqs, psd, a_lo, a_hi)
        alpha_peaks[label] = ap
        alpha_cog[label] = _peak_freq_cog(freqs, psd, a_lo, a_hi)
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
    return fig, alpha_peaks, alpha_cog, bp_all


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
        st.markdown("**Anterior/Posterior-Gradient** "
                    "<span style='font-size:11px;color:#888'>— gesundes waches EEG ist "
                    "posterior-dominant (okzipitaler Alpha-Grundrhythmus)</span>",
                    unsafe_allow_html=True)
        g1, g2, g3 = st.columns(3)
        post_alpha = post_bp.get("Alpha", 0)
        ant_alpha  = ant_bp.get("Alpha", 0)
        ap_ratio   = post_alpha / ant_alpha if ant_alpha > 0 else float("nan")
        # Farbcodierung: >1 posterior-dominant (grün), 0,6–1 abgeschwächt (gelb), <0,6 umgekehrt (rot)
        if ap_ratio == ap_ratio:
            _apz = "#27ae60" if ap_ratio >= 1 else ("#e67e22" if ap_ratio >= 0.6 else "#c0392b")
            _apl = "🟢 posterior-dominant" if ap_ratio >= 1 else (
                   "🟡 abgeschwächt" if ap_ratio >= 0.6 else "🔴 umgekehrt/verloren")
        else:
            _apz, _apl = "#7f8c8d", "—"
        with g1:
            st.markdown(
                f"<div style='background:{_apz}0d;border:1.5px solid {_apz};border-radius:10px;"
                f"padding:8px 10px;text-align:center'>"
                f"<div style='font-size:10px;color:#888'>Alpha posterior/anterior</div>"
                f"<div style='font-size:20px;font-weight:800;color:{_apz}'>"
                f"{ap_ratio:.2f}" + ("</div>" if ap_ratio == ap_ratio else "—</div>") +
                f"<div style='font-size:10px;color:#555'>{_apl}</div></div>",
                unsafe_allow_html=True)
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
                            multitaper=False, amp_thresh_uv=9999.0,
                            all_eeg=None, get_sig_fn=None, alpha_band=(8.0, 13.0),
                            compute_lzc=False):
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

    # Bandpower-Trend
    st.markdown(
        "<span style='font-size:13px;font-weight:700;color:#ccc'>Bandpower-Trend</span>"
        "<span style='font-size:11px;color:#888;margin-left:8px'>Relative Power je Frequenzband über die Zeit</span>",
        unsafe_allow_html=True,
    )
    fig_trend = _bandpower_trend(f_sg, t_sg, Sxx_log, dur_s)
    st.plotly_chart(fig_trend, use_container_width=True, key=f"trend_{panel_id}")

    # FFT + Bandpower
    fig_fft, alpha_peaks, alpha_cog, bp_all = _fft_figure(
        {ch_label: sig_full}, t_start, t_end, fs, panel_id,
        multitaper=multitaper, amp_thresh_uv=amp_thresh_uv, alpha_band=alpha_band,
    )
    st.markdown(f"**FFT — Fenster {win_label}**")
    st.plotly_chart(fig_fft, use_container_width=True, key=f"fft_{panel_id}")

    st.markdown("**Bandpower**")
    _render_bandpower_and_ratios(bp_all, panel_id)

    ap = alpha_peaks.get(ch_label)
    acog = alpha_cog.get(ch_label)
    bp = bp_all.get(ch_label, {})
    total = sum(bp.values()) or 1

    # PSD des Fensters (Basis für Alpha-Power/SEF/Komplexität)
    i0, i1 = int(t_start * fs), int(t_end * fs)
    f_psd, p_psd = _compute_psd(sig_full[i0:i1], fs,
                                multitaper=multitaper, amp_thresh_uv=amp_thresh_uv)
    _apow = {"absolute": float("nan"), "relative": float("nan"), "flattened": float("nan")}
    _sef95 = _medf = _sampen_val = float("nan")
    _lzc = {"shuffle": float("nan"), "phase": float("nan")}
    if f_psd is not None:
        from analysis.aperiodic import fit_aperiodic as _fit_ap, band_power_defs as _bpd
        from analysis.complexity import sample_entropy as _sampen
        _res_ap = _fit_ap(f_psd, p_psd, fmin=1.0, fmax=min(20.0, float(f_psd[-1])))
        _apow = _bpd(f_psd, p_psd, alpha_band[0], alpha_band[1], res=_res_ap)
        _sef95 = _spectral_edge(f_psd, p_psd, 0.95)
        _medf  = _spectral_edge(f_psd, p_psd, 0.50)
        _seg = sig_full[i0:i1]
        _sampen_val = _sampen(_seg, max_n=4000) if len(_seg) >= 100 else float("nan")
        if compute_lzc and len(_seg) >= int(5 * fs):
            _lzc = _lzc_cached(_seg.astype(np.float64).tobytes(), len(_seg), fs)

    # ── Band-Karten (je Rhythmus eine Karte, feste Bandfarben) ────────────────
    def _fx(v, u="", d=1):
        return f"{v:.{d}f}{u}" if v == v else "—"

    def _apk_dot(v):
        if v != v:
            return "transparent"
        if 9 <= v <= 11:
            return "#27ae60"
        if 8 <= v < 9 or 11 < v <= 13:
            return "#e6a817"
        return "#c0392b"

    st.markdown("**Frequenzbänder** <span style='font-size:11px;color:#8a94a0'>— je Rhythmus "
                "eine Karte · feste Bandfarben · Ampel nur beim Alpha-Peak (belastbare Norm)</span>",
                unsafe_allow_html=True)

    _band_meta = [
        ("Alpha", "#27ae60", "Grundrhythmus, wach — hinten am stärksten · Norm-Peak 9–11 Hz"),
        ("Delta", "#4a90d9", "↑ erhöht = Verlangsamung / Enzephalopathie"),
        ("Theta", "#9b59b6", "↑ bei Schläfrigkeit / Verlangsamung"),
        ("Beta",  "#e67e22", "Aktivierung · Benzodiazepine/Barbiturate ↑"),
    ]
    _cards = []
    for name, col, meaning in _band_meta:
        rel = bp.get(name, 0) / total * 100
        extra = ""
        if name == "Alpha":
            extra = (
                "<div style='border-top:0.5px solid var(--border);margin-top:9px;padding-top:7px'>"
                "<div style='display:flex;justify-content:space-between;font-size:12px;color:var(--text-secondary)'>"
                f"<span>Peak (Max/CoG)</span><span style='color:var(--text-primary)'>"
                f"{_fx(ap,' Hz')} <span style='color:{_apk_dot(ap)};font-size:14px'>●</span> / {_fx(acog,' Hz')}</span></div>"
                "<div style='display:flex;justify-content:space-between;font-size:12px;color:var(--text-secondary);margin-top:3px'>"
                f"<span>abs / relativ / flattened</span><span style='color:var(--text-primary)'>"
                f"{_fx(_apow['absolute'],'',2)} / {_fx(_apow['relative'],' %')} / {_fx(_apow['flattened'],'',2)}</span></div></div>")
        _cards.append(
            f"<div style='background:{col}12;border:0.5px solid var(--border);"
            f"border-left:4px solid {col};border-radius:0 10px 10px 0;padding:11px 13px'>"
            "<div style='display:flex;justify-content:space-between;align-items:baseline'>"
            f"<span style='font-weight:700;color:{col}'>{name}</span>"
            f"<span style='font-size:21px;font-weight:800;color:var(--text-primary)'>{rel:.0f} %</span></div>"
            "<div style='height:5px;border-radius:3px;background:var(--surface-1);margin-top:6px'>"
            f"<div style='height:100%;width:{min(rel,100):.0f}%;background:{col};border-radius:3px'></div></div>"
            f"<div style='font-size:11px;color:var(--text-muted);margin-top:7px'>{meaning}</div>{extra}</div>")

    st.markdown(
        "<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:10px'>"
        + "".join(_cards) + "</div>", unsafe_allow_html=True)

    # ── Übergreifende Karte: Verlangsamung & Komplexität (zustandsabhängig) ────
    _lzc_str = (f"{_fx(_lzc['shuffle'],'',2)} / {_fx(_lzc['phase'],'',2)}"
                if _lzc['shuffle'] == _lzc['shuffle'] else "— (in ⚙️ aktivieren)")

    def _cxcell(label, val, hint):
        return (f"<div><div style='font-size:11px;color:var(--text-secondary)'>{label}</div>"
                f"<div style='font-size:19px;font-weight:500;color:var(--text-primary)'>{val}</div>"
                f"<div style='font-size:10px;color:var(--text-muted)'>{hint}</div></div>")

    st.markdown(
        "<div style='background:rgba(100,116,139,0.12);border:0.5px solid var(--border);"
        "border-left:4px solid #64748b;border-radius:0 10px 10px 0;padding:11px 13px;margin-top:10px'>"
        "<div style='font-weight:700;color:var(--text-secondary)'>"
        "Übergreifend — spektrale Verlangsamung &amp; Komplexität</div>"
        "<div style='font-size:11px;color:var(--text-muted);margin:2px 0 9px'>"
        "Zwei Fragen über das ganze Spektrum: <b>Wie langsam</b> ist das EEG (Verlangsamung = "
        "Funktionsstörung) und <b>wie komplex/unvorhersagbar</b> (Komplexität sinkt bei "
        "reduziertem Bewusstsein).</div>"
        "<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:12px'>"
        + _cxcell("SEF95", _fx(_sef95, " Hz"), "95 %-Grenzfrequenz · ↓ = Verlangsamung")
        + _cxcell("Medianfrequenz", _fx(_medf, " Hz"), "50 %-Grenzfrequenz · ↓ = Verlangsamung")
        + _cxcell("Sample Entropy", _fx(_sampen_val, "", 2), "Vorhersagbarkeit · ↓ = weniger wach")
        + _cxcell("LZC (shuffle/phase)", _lzc_str, "Signal-Komplexität · ↑ = komplexer")
        + "</div><div style='font-size:11px;color:var(--text-muted);margin-top:8px'>"
        "Zustandsabhängig — als Trend/Deutung, keine feste Ampel.</div></div>",
        unsafe_allow_html=True)

    # Ratios — richtungsabhängige Ampel (nur die pathologische Richtung wird rot)
    st.markdown("**Klinische Ratios** <span style='font-size:11px;color:#8a94a0'>— "
                "Verhältnis langsamer zu schneller Aktivität · Ampel <b>richtungsabhängig</b>: "
                "nur die klinisch auffällige Richtung (↑ Verlangsamung bzw. ↓ Vigilanz) wird "
                "gelb/rot</span>", unsafe_allow_html=True)
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
    _rcards = []
    for rname, rinfo in RATIO_INFO.items():
        v = rv[rname]
        zc, zemoji, zlabel = _ratio_zone(rinfo, v)
        lo_n, hi_n = rinfo["normal"]
        _vstr = f"{v:.2f}" if v == v else "—"
        _arrow = "↑ hoch = auffällig" if rinfo["dir"] == "high" else "↓ niedrig = auffällig"
        _rcards.append(
            f"<div style='background:{zc}12;border:0.5px solid {zc}55;"
            f"border-top:3px solid {zc};border-radius:8px;padding:9px 11px'>"
            f"<div style='font-size:12px;font-weight:700;color:var(--text-secondary)'>{rname}</div>"
            f"<div style='font-size:22px;font-weight:800;color:{zc};margin:1px 0'>{_vstr}</div>"
            f"<div style='font-size:11px;color:{zc};font-weight:600'>{zemoji} {zlabel}</div>"
            f"<div style='font-size:10px;color:var(--text-muted);margin-top:4px'>"
            f"Norm {lo_n:g}–{hi_n:g} · {_arrow}</div>"
            f"<div style='font-size:10px;color:var(--text-muted);margin-top:3px'>{rinfo['hint']}</div>"
            f"</div>")
    st.markdown(
        "<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px'>"
        + "".join(_rcards) + "</div>", unsafe_allow_html=True)

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

    # Altersadaptives Alpha-Suchfenster (für Erwachsene = Standard 8–13 Hz)
    _age, _sex = get_patient_info()
    alpha_band = _alpha_band(_age)

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
        t_start = safe_slider(
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

    with st.expander("⚙️ Analyse-Optionen", expanded=True):
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

    _group_header("①", "Vier-Elektroden-Achsen", "O1/O2 + F3/F4 — vorne↔hinten und links↔rechts")

    # ══════════════════════════════════════════════════════════════════════════
    # KONSENSUS-PANEL — O1+O2 (posterior) vs F3+F4 (anterior)
    # ══════════════════════════════════════════════════════════════════════════
    consensus_channels = {"O1", "O2", "F3", "F4"}
    has_consensus = consensus_channels.issubset(set(all_eeg))

    if has_consensus:
        section_header("🧠 Konsensus-Panel", "Posterior O1+O2 vs. Anterior F3+F4 · ACNS-Empfehlung")
        _active_settings_note(use_multitaper, use_art_filter)
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

        # FFT-Overlay: beide Kurven in einem Plot.
        # Quantitativ (FFT/Bandpower/Peaks) werden die PSDs der Einzelkanäle
        # gemittelt — deshalb hier Kanallisten statt der zeitgemittelten Signale.
        mt_label = " · Multitaper" if use_multitaper else " · Welch"
        st.markdown(f"**FFT-Vergleich — Fenster {t_start}–{t_end} s**{mt_label}")
        fig_fft, alpha_peaks, alpha_cog, bp_all = _fft_figure(
            {"Posterior (O1+O2)": [_get("O1"), _get("O2")],
             "Anterior (F3+F4)":  [_get("F3"), _get("F4")]},
            t_start, t_end, fs, "cons",
            multitaper=use_multitaper, amp_thresh_uv=float(amp_thresh),
            alpha_band=alpha_band,
        )
        st.plotly_chart(fig_fft, use_container_width=True, key="fft_cons")
        _band_note = ("" if alpha_band == (8.0, 13.0)
                      else f" · Alpha-Suchfenster altersadaptiv **{alpha_band[0]:.0f}–{alpha_band[1]:.0f} Hz**")
        st.caption(
            "FFT, Bandpower und Peaks aus **gemittelten Spektren** der Einzelkanäle "
            "(O1&O2 bzw. F3&F4) — vermeidet Phasenauslöschung. Die Spektrogramm-Heatmaps "
            "oben sind zur Darstellung zeitgemittelt." + _band_note
        )

        # Bandpower + A/P-Gradient
        st.markdown("**Bandpower**")
        _render_bandpower_and_ratios(bp_all, "cons")

        # Ergebnisse für Report-Seite persistieren
        _bp_post = bp_all.get("Posterior (O1+O2)", {})
        _bp_ant  = bp_all.get("Anterior (F3+F4)", {})
        _total_post = sum(_bp_post.values()) or 1
        _total_ant  = sum(_bp_ant.values()) or 1
        _d = _bp_post.get("Delta", 0); _t = _bp_post.get("Theta", 0)
        _a = _bp_post.get("Alpha", 0) or 1e-9; _b = _bp_post.get("Beta", 0) or 1e-9
        _ap_post = alpha_peaks.get("Posterior (O1+O2)")
        _ap_ant  = alpha_peaks.get("Anterior (F3+F4)")
        _cog_post = alpha_cog.get("Posterior (O1+O2)")
        _cog_ant  = alpha_cog.get("Anterior (F3+F4)")
        st.session_state["eeg_summary"] = {
            "t_start": t_start, "t_end": t_end,
            "bp_post": _bp_post, "bp_ant": _bp_ant,
            "total_post": _total_post, "total_ant": _total_ant,
            "ratios": {
                "Delta/Alpha": _d / _a,
                "Theta/Alpha": _t / _a,
                "Alpha/Theta": _a / (_t or 1e-9),
                "Theta/Beta":  _t / (_b or 1e-9),
                "DTAB":        (_d + _t) / ((_a + _b) or 1e-9),
            },
            "alpha_peak_post_hz": _ap_post,
            "alpha_peak_ant_hz":  _ap_ant,
            "alpha_cog_post_hz":  _cog_post,
            "alpha_cog_ant_hz":   _cog_ant,
            "ap_ratio": _bp_post.get("Alpha", 0) / (_bp_ant.get("Alpha", 0) or 1e-9),
        }

        # Kennzahlen-Kacheln
        bp_p = bp_all.get("Posterior (O1+O2)", {})
        bp_a = bp_all.get("Anterior (F3+F4)", {})
        total_p = sum(bp_p.values()) or 1
        total_a = sum(bp_a.values()) or 1
        ap_post = alpha_peaks.get("Posterior (O1+O2)")
        ap_ant  = alpha_peaks.get("Anterior (F3+F4)")
        # Karten im Stil der Einzelkanal-Analyse (Frequenzbänder/Klinische Ratios):
        # Normbereich sichtbar in der Karte statt nur im Hover-Tooltip. Nur Alpha-Peak
        # posterior hat einen belastbaren festen Normwert (9–11 Hz, Ampel-Punkt) — bei
        # den anderen drei ehrlich "kein fester Normbereich" statt erfundener Zahlen.
        def _apk_dot_cons(v):
            if v != v:
                return "transparent"
            if 9 <= v <= 11:
                return "#27ae60"
            if 8 <= v < 9 or 11 < v <= 13:
                return "#e6a817"
            return "#c0392b"

        def _kpi_card(label, value, norm_text, dot_color=None):
            _dot = (f"<span style='color:{dot_color};font-size:15px;margin-left:6px'>●</span>"
                    if dot_color else "")
            return (
                "<div style='background:var(--surface-1,#f8f9fa);border:0.5px solid var(--border);"
                "border-top:3px solid #2471a3;border-radius:0 10px 10px 0;padding:10px 12px'>"
                f"<div style='font-size:11px;color:var(--text-secondary,#6b7684)'>{label}</div>"
                f"<div style='font-size:20px;font-weight:800;color:var(--text-primary,#1c2833)'>"
                f"{value}{_dot}</div>"
                f"<div style='font-size:10px;color:var(--text-muted,#98a3b0);margin-top:3px'>"
                f"{norm_text}</div></div>")

        _apk_p_str = f"{ap_post:.1f} Hz" if ap_post == ap_post else "—"
        _apk_a_str = f"{ap_ant:.1f} Hz"  if ap_ant  == ap_ant  else "—"
        k1, k2, k3, k4 = st.columns(4)
        k1.markdown(_kpi_card("Alpha-Peak posterior", _apk_p_str, "Norm 9–11 Hz",
                              _apk_dot_cons(ap_post)), unsafe_allow_html=True)
        k2.markdown(_kpi_card("Alpha-Peak anterior", _apk_a_str,
                              "kein fester Normbereich · sollte < posterior sein"),
                    unsafe_allow_html=True)
        k3.markdown(_kpi_card("Rel. Alpha posterior", f"{bp_p.get('Alpha',0)/total_p*100:.1f}%",
                              "kein fester %-Normbereich (montage-/referenzabhängig) · "
                              "siehe Alpha/Theta-Ratio (Norm 1,5–6,0) unten"),
                    unsafe_allow_html=True)
        k4.markdown(_kpi_card("Rel. Delta anterior", f"{bp_a.get('Delta',0)/total_a*100:.1f}%",
                              "kein fester %-Normbereich (montage-/referenzabhängig) · "
                              "siehe DAR Delta/Alpha-Ratio (Norm 0,0–1,5) unten"),
                    unsafe_allow_html=True)

        # Vergleich Schwerpunkt (CoG) vs. Maximum — robusteres Maß bei bimodalem Alpha
        _cog_p_str = f"{_cog_post:.1f} Hz" if _cog_post == _cog_post else "—"
        _cog_a_str = f"{_cog_ant:.1f} Hz"  if _cog_ant  == _cog_ant  else "—"
        st.caption(
            f"🎯 **Alpha-Schwerpunkt (CoG, 1/f-korrigiert):** posterior **{_cog_p_str}** · "
            f"anterior **{_cog_a_str}** — stabiler bei bimodalem Alpha als das reine Maximum. "
            f"Größere Abweichung Max↔CoG deutet auf einen breiten oder doppelgipfligen Alpha-Peak."
        )


    else:
        missing = consensus_channels - set(all_eeg)
        st.info(f"ℹ️ Konsensus-Panel nicht verfügbar — fehlende Kanäle: {', '.join(sorted(missing))}")

    # ══════════════════════════════════════════════════════════════════════════
    # HEMISPHÄRISCHE ASYMMETRIE
    # (direkt nach dem Konsensus-Panel — beide nutzen O1/O2+F3/F4, nur andere Achse:
    #  Konsensus-Panel = vorne↔hinten, Asymmetrie = links↔rechts)
    # ══════════════════════════════════════════════════════════════════════════
    asym_chs = [c for c in ["O1", "O2", "F3", "F4"] if c in all_eeg]
    if len(asym_chs) >= 2 and ("O1" in asym_chs and "O2" in asym_chs
                                or "F3" in asym_chs and "F4" in asym_chs):
        section_header("🔁 Hemisphärische Asymmetrie", "AI = (L−R)/(L+R) × 100% · nach Frequenzband · Nuwer 1997", color="#2980b9")
        _active_settings_note(use_multitaper, use_art_filter)
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
            st.markdown(f"**{pair_label}** "
                        "<span style='font-size:11px;color:#888'>🔵 links dominant · "
                        "🟠 rechts dominant · roter Rahmen = |AI| > 20 % (auffällig)</span>",
                        unsafe_allow_html=True)
            _L, _R = "#2980b9", "#e67e22"          # links blau · rechts orange
            ai_cols = st.columns(4)
            for col_w, bname in zip(ai_cols, ["Delta", "Theta", "Alpha", "Beta"]):
                ai_val = _ai(lbp.get(bname, 0), rbp.get(bname, 0))
                if ai_val != ai_val:
                    col_w.markdown(
                        f"<div style='text-align:center;color:var(--text-muted);font-size:12px;"
                        f"padding:10px 0'>AI {bname}<br>—</div>", unsafe_allow_html=True)
                    continue
                _patho = abs(ai_val) > 20
                _side_col = _L if ai_val > 0 else _R
                _w = min(abs(ai_val), 50.0)         # |AI|% der vollen Breite ab Mitte
                if ai_val >= 0:                     # links dominant → Balken nach links
                    _seg = (f"<div style='position:absolute;right:50%;top:2px;bottom:2px;"
                            f"width:{_w:.0f}%;background:{_L};border-radius:4px 0 0 4px'></div>")
                else:                               # rechts dominant → nach rechts
                    _seg = (f"<div style='position:absolute;left:50%;top:2px;bottom:2px;"
                            f"width:{_w:.0f}%;background:{_R};border-radius:0 4px 4px 0'></div>")
                _bandcol = BAND_COLOR.get(bname, "#64748b")
                _outline = "border:1.5px solid #c0392b;" if _patho else f"border:0.5px solid {_bandcol}55;"
                col_w.markdown(
                    f"<div style='{_outline}background:{_bandcol}12;border-top:3px solid {_bandcol};"
                    f"border-radius:8px;padding:7px 8px'>"
                    f"<div style='font-size:11px;color:{_bandcol};font-weight:700;text-align:center'>"
                    f"AI {bname}{' ⚠' if _patho else ''}</div>"
                    f"<div style='position:relative;height:20px;background:var(--surface-1);"
                    f"border-radius:5px;margin:5px 0'>"
                    f"<div style='position:absolute;left:50%;top:0;bottom:0;width:1px;"
                    f"background:var(--border-strong)'></div>{_seg}</div>"
                    f"<div style='font-size:13px;font-weight:500;text-align:center;color:{_side_col}'>"
                    f"{ai_val:+.0f} %</div>"
                    f"<div style='display:flex;justify-content:space-between;font-size:9px;"
                    f"color:var(--text-muted)'><span>{l_ch}</span><span>{r_ch}</span></div></div>",
                    unsafe_allow_html=True)

    _group_header("②", "Ganzer Kopf", "Kopfweiter A/P-Gradient — kein Elektrodenpaar, sondern Gesamtbild")

    # ══════════════════════════════════════════════════════════════════════════
    # ANTERIOR-POSTERIOR-GRADIENT (PAR) — ganzer Kopf
    # ══════════════════════════════════════════════════════════════════════════
    section_header("🧭 Anterior-Posterior-Gradient (PAR)", "Ganzer Kopf · ganzes Gehirn")
    _active_settings_note(use_multitaper, use_art_filter)
    st.markdown(
        "<div style='background:#eef3fb;border-left:4px solid #2471a3;border-radius:8px;"
        "padding:10px 14px;margin:2px 0 8px 0;font-size:13px'>"
        "<b>Was misst dieser Gradient — und warum ist er interessant?</b><br>"
        "Beim <b>gesunden wachen Gehirn</b> sitzt der Alpha-Grundrhythmus <b>hinten</b> "
        "(okzipital), vorne dominiert schnellere Aktivität. Dieses <b>Hinten-stärker-als-vorne</b> "
        "ist ein Grundmerkmal des intakten, wachen Kortex. Der PAR fasst das in einer Zahl: "
        "<b>&gt;1 = posterior-dominant (normal)</b>. Sinkt oder kehrt sich der Gradient um "
        "(&lt;1), spricht das für eine <b>diffuse Hirnfunktionsstörung</b> (Enzephalopathie, "
        "Bewusstseinsminderung) — der Rhythmus wandert nach vorne oder verschwindet.</div>",
        unsafe_allow_html=True,
    )
    heavy_calc = st.toggle(
        "Rechenintensive Maße berechnen (A/P-Gradient hier + LZC-Komplexität weiter "
        "unten in der Einzelkanal-Analyse)",
        value=False, key="spec_heavy",
        help="Beide Maße sind O(N²)/kopfweit und brauchen mehr Rechenzeit. Standard aus, "
             "damit die Ansicht schnell bleibt — bei Bedarf hier aktivieren; gilt für "
             "die ganze Seite, nicht nur für den A/P-Gradienten.")
    if not heavy_calc:
        st.info("ℹ️ Rechenintensiv — obigen Schalter aktivieren, um den A/P-Gradienten "
                "(ganzer Kopf) zu berechnen.")
        _par = {"n_post": 0, "n_ant": 0, "par": float("nan")}
    else:
        _par = _compute_par(edf_path, t_start, t_end, alpha_band[0], alpha_band[1],
                            use_multitaper, float(amp_thresh))
    if _par["n_post"] >= 2 and _par["n_ant"] >= 2 and _par["par"] == _par["par"]:
        _pv = _par["par"]
        _pzone = "normal" if _pv >= 1.0 else ("grenzwertig" if _pv >= 0.6 else "pathologisch")
        _pcol = {"normal": "#27ae60", "grenzwertig": "#e67e22", "pathologisch": "#c0392b"}[_pzone]
        # Alpha-PAR ist der Leitwert dieser Sektion — visuell zentral/groß, die Nebenwerte
        # (Exponent-Gradient, Elektrodenzahl) bewusst kleiner (User-Feedback 2026-08-03).
        pc1, pc2, pc3 = st.columns([2, 1, 2])
        with pc1:
            _lbl = {"normal": "🟢 posterior-dominant", "grenzwertig": "🟡 abgeschwächt",
                    "pathologisch": "🔴 anteriorisiert"}[_pzone]
            st.markdown(
                f"<div style='padding:12px 16px;border-radius:12px;border:2px solid {_pcol};"
                f"background:{_pcol}0d'>"
                f"<div style='font-size:12px;color:var(--text-secondary,#6b7684);"
                f"font-weight:700'>Alpha-PAR (Leitwert)</div>"
                f"<div style='font-size:34px;font-weight:800;color:{_pcol};line-height:1.15'>"
                f"{_pv:.2f}</div>"
                f"<div style='font-size:12px;color:{_pcol};font-weight:600'>{_lbl}</div></div>",
                unsafe_allow_html=True)
            st.caption("Posterior/anterior geom. Mittel der absoluten Alpha-Power. >1 = "
                       "posterior-dominant (wach/normal), <1 = anteriorisiert "
                       "(Bewusstseinsminderung/Anästhesie).")
        with pc2:
            _exp_grad_str = (f"{_par['exp_grad']:+.2f}" if _par['exp_grad'] == _par['exp_grad'] else "—")
            st.markdown(
                "<div style='font-size:10px;color:var(--text-muted,#98a3b0);margin-top:6px'>"
                "Exponent-Gradient<br>(post−ant)</div>"
                f"<div style='font-size:15px;font-weight:600;color:var(--text-primary,#1c2833)'>"
                f"{_exp_grad_str}</div>",
                unsafe_allow_html=True,
                help="Differenz des spektralen Exponenten posterior − anterior (1–20 Hz). "
                     "Positiv = posterior steiler; anterior-posteriore Verflachung "
                     "korreliert mit Bewusstseinsniveau (Maschke 2025).")
        with pc3:
            st.markdown(
                "<div style='font-size:10px;color:var(--text-muted,#98a3b0);margin-top:6px'>"
                "Elektroden</div>"
                f"<div style='font-size:13px;color:var(--text-secondary,#6b7684)'>"
                f"{_par['n_post']} posterior · {_par['n_ant']} anterior "
                f"<span style='font-size:10px'>(Cz-Linie ausgeschlossen)</span></div>",
                unsafe_allow_html=True)
        # ── Schemakopf: anteriore Werte oben, posteriore unten, Kopf vorne→hinten graduiert
        _es = st.session_state.get("eeg_summary") or {}

        def _rp(side, band):
            bp = _es.get(f"bp_{side}") or {}
            tot = _es.get(f"total_{side}") or (sum(bp.values()) or 1)
            return (bp.get(band, 0) / tot * 100) if bp else float("nan")

        def _fh(v, u="", d=1):
            return f"{v:.{d}f}{u}" if (v is not None and v == v) else "—"

        _apk_ant  = _es.get("alpha_peak_ant_hz")
        _apk_post = _es.get("alpha_peak_post_hz")
        _relA_ant,  _relD_ant  = _rp("ant", "Alpha"),  _rp("ant", "Delta")
        _relA_post, _relD_post = _rp("post", "Alpha"), _rp("post", "Delta")

        def _chip(x, y, label, value, sub, color):
            return (
                f"<rect x='{x}' y='{y}' width='190' height='58' rx='9' "
                f"fill='var(--surface-1,#fff)' stroke='{color}' stroke-width='1.2' stroke-opacity='0.55'/>"
                f"<text x='{x+12}' y='{y+19}' font-size='11' fill='var(--text-secondary,#6b7684)'>{label}</text>"
                f"<text x='{x+12}' y='{y+41}' font-size='18' font-weight='700' fill='{color}'>{value}</text>"
                f"<text x='{x+12}' y='{y+53}' font-size='9.5' fill='var(--text-muted,#98a3b0)'>{sub}</text>"
            )

        _GRN, _BLU, _AMB = "#27ae60", "#4a90d9", "#e67e22"
        _svg = (
            "<svg viewBox='0 0 660 500' xmlns='http://www.w3.org/2000/svg' role='img' "
            "font-family='system-ui,-apple-system,sans-serif' style='max-width:560px;width:100%'>"
            "<title>A/P-Gradient als Schemakopf</title>"
            "<defs><linearGradient id='apheadgrad' x1='0' y1='0' x2='0' y2='1'>"
            "<stop offset='0%' stop-color='#e67e22' stop-opacity='0.26'/>"
            "<stop offset='45%' stop-color='#9b59b6' stop-opacity='0.13'/>"
            "<stop offset='100%' stop-color='#27ae60' stop-opacity='0.32'/>"
            "</linearGradient></defs>"
            "<text x='330' y='18' text-anchor='middle' font-size='12' font-weight='700' "
            "fill='#c0722a' letter-spacing='1'>ANTERIOR · vorne</text>"
            # anteriore Chips (oben)
            + _chip(20, 28, "Alpha-Peak ant.", _fh(_apk_ant, " Hz"), "frontaler Gipfel", _AMB)
            + _chip(235, 28, "rel. Alpha ant.", _fh(_relA_ant, " %", 0), "vorne meist gering", _GRN)
            + _chip(450, 28, "rel. Delta ant.", _fh(_relD_ant, " %", 0), "↑ = frontale Verlangsamung", _BLU)
            # Nase + Ohren + Kopf
            + "<path d='M330 104 L316 128 L344 128 Z' fill='var(--surface-2,#e9edf2)' "
              "stroke='var(--border,#c4ccd6)' stroke-width='1.5'/>"
            + "<ellipse cx='188' cy='262' rx='15' ry='28' fill='var(--surface-2,#e9edf2)' "
              "stroke='var(--border,#c4ccd6)' stroke-width='1.5'/>"
            + "<ellipse cx='472' cy='262' rx='15' ry='28' fill='var(--surface-2,#e9edf2)' "
              "stroke='var(--border,#c4ccd6)' stroke-width='1.5'/>"
            + "<ellipse cx='330' cy='262' rx='122' ry='148' fill='url(#apheadgrad)' "
              "stroke='var(--border-strong,#98a3b0)' stroke-width='2'/>"
            # PAR-Badge (Mitte)
            + f"<rect x='245' y='232' width='170' height='60' rx='12' fill='var(--surface-1,#fff)' "
              f"stroke='{_pcol}' stroke-width='2'/>"
            + "<text x='330' y='253' text-anchor='middle' font-size='11.5' "
              "fill='var(--text-secondary,#6b7684)'>Alpha-PAR (post/ant)</text>"
            + f"<text x='330' y='279' text-anchor='middle' font-size='23' font-weight='800' "
              f"fill='{_pcol}'>{_pv:.2f}</text>"
            # posteriore Chips (unten)
            + _chip(20, 412, "Alpha-Peak post.", _fh(_apk_post, " Hz"), "okz. Grundrhythmus", _GRN)
            + _chip(235, 412, "rel. Alpha post.", _fh(_relA_post, " %", 0), "dominant = wach/normal", _GRN)
            + _chip(450, 412, "rel. Delta post.", _fh(_relD_post, " %", 0), "↑ = post. Verlangsamung", _BLU)
            + "<text x='330' y='488' text-anchor='middle' font-size='12' font-weight='700' "
              "fill='#1e8449' letter-spacing='1'>POSTERIOR · hinten</text>"
            "</svg>"
        )
        st.markdown(f"<div style='text-align:center;margin:6px 0'>{_svg}</div>",
                    unsafe_allow_html=True)
        if not _es:
            st.caption("ℹ️ Die anterioren/posterioren Bandwerte am Kopf stammen aus dem "
                       "Konsensus-Panel (O1+O2 vs. F3+F4) — sichtbar sobald diese Kanäle vorliegen.")
        st.caption(
            "Der **A/P-Gradient** ist bei gesundem wachem EEG posterior-dominant (okzipitaler "
            "Alpha-Grundrhythmus). Umkehr/Verlust = diffuse Störung. Colombo 2023: PAR "
            "diagnostisch v. a. bei nicht-anoxischen DoC-Patienten; Maschke 2025: als "
            "Ganzgruppen-Marker durch Ätiologie konfundiert — ätiologiespezifisch interpretieren.")
    else:
        st.info("ℹ️ PAR nicht berechenbar — zu wenige posteriore/anteriore 10-20-Elektroden "
                "(je ≥ 2 nötig, Cz-Linie ausgeschlossen).")

    _group_header("③", "Einzelkanal-Detail", "Ein Kanal im Fokus — Bandpower, FFT, interne Validierung")

    # ══════════════════════════════════════════════════════════════════════════
    # EINZELKANAL-ANALYSE
    # ══════════════════════════════════════════════════════════════════════════
    section_header("🔬 Einzelkanal-Analyse", "Bandpower · FFT · Klinische Ratios pro Kanal")
    _active_settings_note(use_multitaper, use_art_filter)

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
            all_eeg=all_eeg, get_sig_fn=_get, alpha_band=alpha_band, compute_lzc=heavy_calc,
        )
        st.markdown("---")

    # ══════════════════════════════════════════════════════════════════════════
    # REFERENZ-EPOCH (einmalig, mit Kanal-Auswahl)
    # ══════════════════════════════════════════════════════════════════════════
    section_header("🔍 Referenz-Epoch", "Interne Validierung · Kanal wählbar · FFT-Overlay")
    _active_settings_note(use_multitaper, use_art_filter)
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
    ref_start_g = safe_slider(
        "Position im Recording (s)", 0, max(0, dur_s - 10),
        _def_g, step=1, key="val_start_global",
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
        ap_fg = _peak_freq(f_fg, psd_fg, alpha_band[0], alpha_band[1])
        ap_rg = _peak_freq(f_rg2, psd_rg, alpha_band[0], alpha_band[1])
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

#### Alpha-Power — drei Definitionen (Maschke et al. 2025)

Für Bewusstseinsmarker (DoC) sind **drei** Alpha-Power-Definitionen relevant, die
unterschiedlich robust und **ätiologie-abhängig** aussagekräftig sind:

- **Absolut** = log₁₀(Fläche unter der PSD im Alpha-Band). Wird stark von der
  **Untergrund-Suppression** beeinflusst (bei Anoxie ist der Untergrund oft supprimiert).
  → diagnostisch v. a. bei **anoxischen** Patienten.
- **Relativ** = Alpha-Fläche / Gesamt-Fläche (1–40 Hz) × 100. Korrigiert für die Gesamtpower.
  → diagnostisch v. a. bei **nicht-anoxischen** Patienten (Wert läuft dort weitgehend über
  den spektralen Exponenten).
- **Flattened** = Fläche unter dem **aperiodik-bereinigten** Spektrum im Alpha-Band
  (FOOOF `_spectrum_flat`): nur der echte Oszillationsgipfel, **ohne 1/f-Untergrund**. Trennt
  „echtes Alpha" von broadband-Untergrund. → diagnostisch v. a. bei **anoxischen** Patienten.

**Kernbotschaft von Maschke 2025:** *Der gleiche Marker bedeutet je nach Ätiologie
Verschiedenes* — anoxisch vs. nicht-anoxisch nie zusammenwerfen. Grundlage des geplanten
DoC-Gradings.
Quelle: **Maschke C. et al.** (2025). *Cerebral Cortex* 35:bhaf254; **Donoghue et al.** (2020).

---

#### Alpha Peak Frequency (APF)

Die Frequenz des höchsten Ausschlags im Alpha-Band (8–13 Hz), okzipital gemessen.

- **Normbereich**: 9–11 Hz (Augen zu, entspannt)
- **Klinische Bedeutung**: Die APF ist der stabilste spektrale Parameter des Individuums — vergleichbar einem biologischen Fingerabdruck. Im Längsschnitt signalisiert ein APF-Abfall bereits bei Werten formal im Normbereich einen frühen kognitiven Decline (Petersen 2000, Jelic 2000). Ein APF < 8 Hz ist ein sensitiver Marker für **Alzheimer-Demenz** und metabolische Enzephalopathien.
- **Methodik**: Wir zeigen **zwei** Schätzer nebeneinander:
  - **Alpha-Peak (Max)** = Frequenz des PSD-Maximums (argmax) im 8–13-Hz-Band. Einfach,
    aber bei zwei nahen Gipfeln (z. B. 9 und 11 Hz) instabil — springt zum minimal höheren.
  - **Alpha-Peak (CoG)** = Schwerpunkt (Center of Gravity, „Individual Alpha Frequency"):
    CoG = Σ(fᵢ·Pᵢ) / Σ(Pᵢ) über das Alpha-Band, nach Abzug einer linearen 1/f-Baseline
    (damit die Theta-Flanke den Schwerpunkt nicht nach unten zieht). **Robuster** bei
    breitem oder bimodalem Alpha. Eine große Abweichung Max↔CoG deutet auf einen breiten
    oder doppelgipfligen Alpha-Peak. Das **altersadaptive Suchband** (Kinder tiefer, s. o.)
    gilt für beide Schätzer. Quelle: Klimesch (1999), Brain Res Rev 29:169–195.

---

#### Spektrale Summenkennzahlen — SEF95 & Medianfrequenz

Zwei Einzelzahlen, die die **Form des gesamten Spektrums** zusammenfassen (aus der
kumulierten Leistung im Analyseband 1–30 Hz):

- **SEF95 (Spectral Edge Frequency 95 %)**: Frequenz, unter der **95 %** der Leistung
  liegen. Sinkt bei spektraler Verlangsamung. Standard-Trendmarker in Sedierungs-/
  Narkose-Monitoring und bei Enzephalopathie; höhere Werte = wacher/aktivierter.
- **Medianfrequenz (SEF50)**: Frequenz, unter der **50 %** der Leistung liegen —
  robustes Maß der Verlangsamung, weniger empfindlich gegen hochfrequente Artefakte
  als SEF95.

Beide sind rein deskriptiv (kein fester Cutoff hier) und v. a. im **Verlauf** bzw. im
**Seitenvergleich** aussagekräftig. Berechnet mit linearer Interpolation zwischen den
Frequenz-Bins für Sub-Bin-Genauigkeit.
Quelle: **Drummond GB et al.** (1991), Br J Anaesth; **Tonner & Bein** (2006), Best Pract Res Clin Anaesthesiol.

---

#### Sample Entropy (Komplexität)

Nichtlineares Maß der **Vorhersagbarkeit** des EEG-Signals (m=2, r=0,2·SD): Wie
wahrscheinlich bleiben ähnliche Muster über eine Zeitschritt-Verlängerung ähnlich?
- **niedrig** → regelmäßig/vorhersagbar: Müdigkeit, Sedierung, Delir, Demenz,
  Bewusstseinsstörungen
- **hoch** → komplex/wach

Berechnet auf einem zentralen Segment des Analysefensters (max. 4000 Punkte, O(N²)).
Bereits ein Kanal genügt. Orientierend, parameter-/längenabhängig — v. a. im Verlauf/
Seitenvergleich aussagekräftig.
Quelle: **Richman JS & Moorman JR** (2000). Am J Physiol Heart Circ Physiol 278:H2039–H2049.

**Lempel-Ziv-Komplexität (LZC)** — zweite, kompressionsbasierte Komplexitäts-Sicht:
Das Signal wird je 5-s-Segment am Mittelwert **binarisiert** und die LZ76-Komplexität
bestimmt, auf zwei Arten normalisiert:
- **shuffle** (0..1): gegen zufällig gemischte Binärsequenzen — hoch = komplex/inkompressibel.
- **phase** (~1): gegen phasen-randomisierte Surrogate mit gleichem Spektrum — >1 = komplexer
  als das Spektrum allein erklärt (spektral-unabhängige, „echte" Komplexität), <1 = weniger.

Reduzierte LZC bei sinkendem Bewusstsein. **Maschke et al. 2025** (Cerebral Cortex 35:bhaf254):
LZC (shuffle) diagnostisch v. a. bei **nicht-anoxischen** DoC-Patienten; kongruent mit dem
spektralen Exponenten. Grundlage für das geplante DoC-Grading.
Quelle: **Lempel & Ziv** (1976) IEEE Trans Inf Theory; **Schartner et al.** (2015) PLoS ONE.

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
