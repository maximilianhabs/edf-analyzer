"""🎨 Glory Report — visueller Abstract (Show-off-PDF).

Kein tabellarischer Report, sondern eine **visuelle Zusammenfassung**: die schönsten und
robustesten Darstellungen des Systems, groß, farbig, druckfertig. A4 quer, 6 Seiten,
heller Poster-Look. EEG und EKG strikt getrennt (eigene Farb-Kopfleisten).

Bewusst NUR verlässliche Marker (Alpha-Peak, rel. Bandpower, DAR, A/P-Gradient; HF, SDNN,
RMSSD, LF/HF, Poincaré). Kein EDR/LZC/DFA — zu erklärungsbedürftig für einen Abstract.

Vektor-PDF via matplotlib PdfPages. Verändert nichts an den bestehenden Analysen/Reports.
"""

from __future__ import annotations

import io
import math

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import FancyBboxPatch, Ellipse, Polygon, Rectangle
from scipy.signal import spectrogram

# ── Design-System ─────────────────────────────────────────────────────────────
C_DELTA, C_THETA, C_ALPHA, C_BETA = "#4a90d9", "#9b59b6", "#27ae60", "#e67e22"
C_ECG = "#c0392b"
C_L, C_R, C_M = "#e67e22", "#3b82f6", "#16a34a"     # links / rechts / Mitte
C_EEG_HDR, C_ECG_HDR = "#1f6f8b", "#b03a2e"
C_INK, C_MUTED, C_GRID = "#1c2733", "#6b7684", "#dfe4ea"
BANDS = [("Delta", 1, 4, C_DELTA), ("Theta", 4, 8, C_THETA),
         ("Alpha", 8, 13, C_ALPHA), ("Beta", 13, 30, C_BETA)]
A4L = (11.69, 8.27)


def _page(title, subtitle, color):
    """Neue A4-quer-Seite mit farbiger Kopfleiste."""
    fig = plt.figure(figsize=A4L, facecolor="white")
    fig.patches.append(Rectangle((0, 0.912), 1, 0.088, transform=fig.transFigure,
                                 facecolor=color, edgecolor="none", zorder=0))
    fig.text(0.035, 0.968, title, color="white", fontsize=18, fontweight="bold", va="center")
    fig.text(0.035, 0.933, subtitle, color="white", fontsize=9.5, va="center", alpha=0.92)
    return fig


def _cap(fig, y, text):
    """Klartext-Zeile unter einer Grafik: was sehe ich / warum wichtig."""
    fig.text(0.035, y, text, fontsize=8.8, color=C_MUTED, va="center")


def _fmt(v, d=1, suf=""):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    return f"{v:.{d}f}{suf}"


# ── Datenbeschaffung ──────────────────────────────────────────────────────────
def _hp(sig, fs, cut=1.0):
    from scipy.signal import butter, filtfilt
    b, a = butter(4, cut / (fs / 2), btype="high")
    return filtfilt(b, a, sig)


def _clean_gaps(dur, segments, win=10.0):
    if not segments:
        return [(0.0, dur)]
    gaps, prev = [], 0.0
    for s in sorted(segments, key=lambda x: x["start_s"]):
        if s["start_s"] - prev > 0:
            gaps.append((prev, s["start_s"]))
        prev = max(prev, s["end_s"])
    if prev < dur:
        gaps.append((prev, dur))
    return [g for g in gaps if g[1] - g[0] >= win] or [(0.0, min(dur, win))]


def _quiet_window(edf, dur, segments, win=10.0):
    """Wählt das **ruhigste** saubere 10-s-Fenster (geringste mediane Amplitude über die
    EEG-Kanäle) — damit der Show-Ausschnitt wirklich schön aussieht, nicht nur artefaktfrei."""
    sf, em = edf["sfreq"], edf.get("eeg_map", {})
    gaps = _clean_gaps(dur, segments, win)
    if not em:
        lo, hi = max(gaps, key=lambda g: g[1] - g[0])
        return max(0.0, (lo + hi) / 2 - win / 2)
    chans = [c for c in ("O1", "O2", "C3", "C4", "P3", "P4", "F3", "F4") if c in em][:6] or list(em)[:6]
    sigs = [_hp(edf["data"][em[c]] * 1e6, sf) for c in chans]
    edge = 15.0                      # Ränder meiden (Kalibrier-/Einschwingphase, Abbruch am Ende)
    cands = []
    for lo, hi in gaps:
        t = max(lo, edge)
        while t + win <= min(hi, dur - edge):
            i0, i1 = int(t * sf), int((t + win) * sf)
            cands.append((t, float(np.median([np.ptp(s[i0:i1]) for s in sigs]))))
            t += 2.0
    if not cands:
        lo, hi = max(gaps, key=lambda g: g[1] - g[0])
        return max(0.0, (lo + hi) / 2 - win / 2)
    scores = np.array([c[1] for c in cands])
    # Plausibilitätsboden: kein flaches/totes Signal (Aufnahme-Ende, Elektroden ab) auswählen
    floor = max(8.0, float(np.percentile(scores, 25)))
    valid = [c for c in cands if c[1] >= floor] or cands
    return min(valid, key=lambda c: c[1])[0]


def _collect(edf, edf_path):
    """Alle Daten für die Panels einmal einsammeln."""
    from views.eeg_spectrum import _compute_psd, _band_power, _peak_freq
    d = {"sf": edf["sfreq"], "dur": edf["duration_s"], "em": edf.get("eeg_map", {})}
    sf, dur, em = d["sf"], d["dur"], d["em"]

    # Artefaktmaske (für sauberes Fenster + Zeitleiste + Qualität)
    try:
        from analysis.artifacts import mask_from_edf
        res = mask_from_edf(edf)
        d["segments"], d["clean_frac"] = res.segments, res.clean_frac
    except Exception:
        d["segments"], d["clean_frac"] = [], 1.0
    d["t_clean"] = _quiet_window(edf, dur, d["segments"])

    # EEG posterior/anterior
    def sig(ch):
        return _hp(edf["data"][em[ch]] * 1e6, sf) if ch in em else None
    o1, o2, f3, f4 = sig("O1"), sig("O2"), sig("F3"), sig("F4")
    d["post"] = (o1 + o2) / 2 if o1 is not None and o2 is not None else (o1 if o1 is not None else o2)
    d["ant"] = (f3 + f4) / 2 if f3 is not None and f4 is not None else (f3 if f3 is not None else f4)
    d["o1"], d["o2"], d["f3"], d["f4"] = o1, o2, f3, f4

    if d["post"] is not None:
        ana = min(dur, 300.0); t0 = max(0.0, (dur - ana) / 2)
        seg = d["post"][int(t0 * sf):int((t0 + ana) * sf)]
        f, p = _compute_psd(seg, sf, amp_thresh_uv=9999.0)
        d["psd_f"], d["psd_p"] = f, p
        if f is not None:
            bp = {n: _band_power(f, p, lo, hi) for n, lo, hi, _ in BANDS}
            tot = sum(bp.values()) or 1
            d["rel"] = {k: v / tot * 100 for k, v in bp.items()}
            d["alpha_peak"] = _peak_freq(f, p, 8, 13)
            d["dar"] = bp["Delta"] / (bp["Alpha"] or 1e-9)
        # A/P-Gradient
        if d["ant"] is not None:
            fa, pa = _compute_psd(d["ant"][int(t0 * sf):int((t0 + ana) * sf)], sf, amp_thresh_uv=9999.0)
            if fa is not None and f is not None:
                d["par"] = _band_power(f, p, 8, 13) / (_band_power(fa, pa, 8, 13) or 1e-9)
                d["rel_ant"] = {n: _band_power(fa, pa, lo, hi) for n, lo, hi, _ in BANDS}
        # Asymmetrie
        d["ai"] = {}
        for lbl, L, R in [("okzipital", o1, o2), ("frontal", f3, f4)]:
            if L is None or R is None:
                continue
            fl, pl = _compute_psd(L[int(t0 * sf):int((t0 + ana) * sf)], sf, amp_thresh_uv=9999.0)
            fr, pr = _compute_psd(R[int(t0 * sf):int((t0 + ana) * sf)], sf, amp_thresh_uv=9999.0)
            if fl is None or fr is None:
                continue
            for n, lo, hi, _ in BANDS:
                a_, b_ = _band_power(fl, pl, lo, hi), _band_power(fr, pr, lo, hi)
                d["ai"][(lbl, n)] = (a_ - b_) / (a_ + b_) * 100 if (a_ + b_) > 1e-9 else np.nan
        # Aperiodik
        try:
            from analysis.aperiodic import welch_psd, fit_aperiodic
            fw, pw = welch_psd(seg, sf, fmax=45.0)
            d["ap"] = fit_aperiodic(fw, pw, 1, 40)
        except Exception:
            d["ap"] = None

    # EKG
    d["ecg"] = None
    if edf.get("ecg_channels"):
        ch = edf["ecg_channels"][0]
        if ch in edf.get("ch_idx", {}):
            from analysis.ecg import detect_r_peaks, build_rr_series, compute_hrv_time_domain
            from analysis.hrv_freq import compute_frequency_domain
            raw = edf["data"][edf["ch_idx"][ch]].astype(float)
            raw = raw - np.median(raw)
            pk = detect_r_peaks(raw, sf)
            rr = build_rr_series(pk, sf)
            if rr is not None:
                clean = rr.rr_ms[~rr.artifact_mask]
                td = compute_hrv_time_domain(clean)
                fd = None
                try:
                    fd = compute_frequency_domain(clean, rr.rr_times_s[~rr.artifact_mask], "welch")
                except Exception:
                    pass
                d["ecg"] = {"name": ch, "sig": raw * 1000.0, "peaks": pk,
                            "rr_all": rr.rr_ms, "t_all": rr.rr_times_s,
                            "mask": rr.artifact_mask, "rr": clean, "td": td, "fd": fd}
    return d


# ── Seite 1: Cover ────────────────────────────────────────────────────────────
def _tile(fig, x, y, w, h, label, value, unit, color):
    fig.patches.append(FancyBboxPatch((x, y), w, h, transform=fig.transFigure,
                                      boxstyle="round,pad=0.006,rounding_size=0.012",
                                      facecolor=color + "1A", edgecolor=color, linewidth=1.4))
    fig.text(x + w / 2, y + h * 0.66, value, fontsize=21, fontweight="bold",
             color=color, ha="center", va="center")
    fig.text(x + w / 2, y + h * 0.30, f"{label}  {unit}", fontsize=8.2,
             color=C_MUTED, ha="center", va="center")


def _page_cover(pdf, d, disp):
    fig = _page("EDF-Analyzer — Visual Report", "EEG & Herzratenvariabilität · visuelle Zusammenfassung", "#0f3d52")
    fig.text(0.035, 0.875, disp, fontsize=13, fontweight="bold", color=C_INK)
    fig.text(0.035, 0.845, f"Dauer {d['dur']/60:.1f} min · {len(d['em'])} EEG-Kanäle · "
             f"{d['sf']:.0f} Hz" + (f" · EKG {d['ecg']['name']}" if d.get("ecg") else ""),
             fontsize=9.5, color=C_MUTED)

    # Qualitäts-Donut
    ax = fig.add_axes([0.79, 0.60, 0.17, 0.26]); ax.set_aspect("equal"); ax.axis("off")
    q = d["clean_frac"] * 100
    ax.pie([q, 100 - q], colors=["#27ae60", "#e9edf2"], startangle=90,
           wedgeprops=dict(width=0.32, edgecolor="white"))
    ax.text(0, 0, f"{q:.0f}%", ha="center", va="center", fontsize=17, fontweight="bold", color="#1e8449")
    ax.text(0, -0.42, "sauberes EEG", ha="center", va="center", fontsize=8, color=C_MUTED)

    # KPI-Kacheln — nur robuste Marker
    fig.text(0.035, 0.79, "EEG", fontsize=11, fontweight="bold", color=C_EEG_HDR)
    tiles = [("Alpha-Peak", _fmt(d.get("alpha_peak"), 1), "Hz", C_ALPHA),
             ("rel. Alpha post.", _fmt((d.get("rel") or {}).get("Alpha"), 0), "%", C_ALPHA),
             ("Delta/Alpha", _fmt(d.get("dar"), 2), "", C_DELTA),
             ("A/P-Gradient", _fmt(d.get("par"), 1), "×", C_M)]
    for i, (l, v, u, c) in enumerate(tiles):
        _tile(fig, 0.035 + i * 0.185, 0.63, 0.165, 0.13, l, v, u, c)

    if d.get("ecg"):
        td, fd = d["ecg"]["td"], (d["ecg"]["fd"] or {})
        fig.text(0.035, 0.555, "EKG / HRV", fontsize=11, fontweight="bold", color=C_ECG_HDR)
        tiles = [("Herzfrequenz", _fmt(td.get("mean_hr_bpm"), 0), "bpm", C_ECG),
                 ("SDNN", _fmt(td.get("sdnn_ms"), 0), "ms", "#8e44ad"),
                 ("RMSSD", _fmt(td.get("rmssd_ms"), 0), "ms", "#2980b9"),
                 ("LF/HF", _fmt(fd.get("lf_hf_ratio"), 2), "", "#d68910")]
        for i, (l, v, u, c) in enumerate(tiles):
            _tile(fig, 0.035 + i * 0.185, 0.395, 0.165, 0.13, l, v, u, c)

    # Zeitleiste mit Artefaktblöcken
    ax = fig.add_axes([0.035, 0.22, 0.93, 0.085])
    ax.set_xlim(0, d["dur"]); ax.set_ylim(0, 1)
    ax.add_patch(Rectangle((0, 0), d["dur"], 1, color="#e8f5ee"))
    for s in d["segments"]:
        ax.add_patch(Rectangle((s["start_s"], 0), s["end_s"] - s["start_s"], 1, color="#e74c3c", alpha=0.75))
    ax.set_yticks([]); ax.set_xlabel("Zeit (s)", fontsize=8.5, color=C_MUTED, labelpad=2)
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.tick_params(labelsize=8, colors=C_MUTED)
    _cap(fig, 0.135, "Aufnahme-Zeitleiste — rot = automatisch erkannte Bewegungs-/Globalartefakte. "
                     "Alle folgenden Beispiel-Ausschnitte stammen aus einem sauberen Abschnitt.")
    fig.text(0.035, 0.06, "Nur robuste, verlässliche Marker · erzeugt vom EDF-Analyzer",
             fontsize=8, color=C_MUTED, style="italic")
    pdf.savefig(fig); plt.close(fig)


# ── Seite 2: EEG-Rohsignal ────────────────────────────────────────────────────
_LONG = [("Fp2", "F8"), ("F8", "T4"), ("T4", "T6"), ("T6", "O2"),
         ("Fp1", "F7"), ("F7", "T3"), ("T3", "T5"), ("T5", "O1"),
         ("Fp2", "F4"), ("F4", "C4"), ("C4", "P4"), ("P4", "O2"),
         ("Fp1", "F3"), ("F3", "C3"), ("C3", "P3"), ("P3", "O1"),
         ("Fz", "Cz"), ("Cz", "Pz")]


def _page_raw_eeg(pdf, edf, d):
    fig = _page("EEG — Das Rohsignal", "Bipolare Längsreihe (DGKN) · 10 s aus einem sauberen Abschnitt", C_EEG_HDR)
    sf, em, t0 = d["sf"], d["em"], d["t_clean"]
    i0, i1 = int(t0 * sf), int((t0 + 10) * sf)
    ax = fig.add_axes([0.06, 0.11, 0.91, 0.75])
    traces = []
    for a, b in _LONG:
        if a in em and b in em:
            s = _hp(edf["data"][em[a]] * 1e6, sf)[i0:i1] - _hp(edf["data"][em[b]] * 1e6, sf)[i0:i1]
            col = C_R if a[-1] in "248" or a in ("Fp2", "F4", "C4", "P4", "O2", "F8", "T4", "T6") else (
                C_M if a in ("Fz", "Cz") else C_L)
            traces.append((f"{a}–{b}", s, col))
    if not traces:
        pdf.savefig(fig); plt.close(fig); return
    g95 = float(np.percentile(np.abs(np.concatenate([t[1] for t in traces])), 95)) or 1.0
    gain = 0.45 / g95
    t = np.arange(i1 - i0) / sf + t0
    for k, (lbl, s, col) in enumerate(traces):
        y = len(traces) - k
        ax.plot(t, y + s * gain, color=col, lw=0.7)
        ax.text(t[0] - 0.25, y, lbl, fontsize=7.5, ha="right", va="center", color=col)
    ax.set_xlim(t[0] - 0.9, t[-1]); ax.set_ylim(0.2, len(traces) + 0.9)
    ax.set_yticks([]); ax.set_xlabel("Zeit (s)", fontsize=9, color=C_MUTED)
    ax.tick_params(labelsize=8, colors=C_MUTED)
    for sp in ("top", "right", "left"):
        ax.spines[sp].set_visible(False)
    ax.spines["bottom"].set_color(C_GRID)
    fig.text(0.80, 0.885, "rechts", color=C_R, fontsize=9, fontweight="bold")
    fig.text(0.855, 0.885, "links", color=C_L, fontsize=9, fontweight="bold")
    fig.text(0.905, 0.885, "Mittellinie", color=C_M, fontsize=9, fontweight="bold")
    _cap(fig, 0.055, "Das unverarbeitete EEG — hierauf beruhen alle folgenden Auswertungen. "
                     "Negativ ist oben (klinische Konvention).")
    pdf.savefig(fig); plt.close(fig)


# ── Seite 3: EEG Frequenz & Rhythmus ──────────────────────────────────────────
def _page_spectrum(pdf, d):
    fig = _page("EEG — Frequenz & Grundrhythmus", "Spektrogramm · Leistungsspektrum · Bandverteilung (posterior O1/O2)", C_EEG_HDR)
    sf, post = d["sf"], d.get("post")
    if post is None:
        pdf.savefig(fig); plt.close(fig); return

    # Spektrogramm
    ax = fig.add_axes([0.055, 0.50, 0.60, 0.36])
    nper = min(int(sf * 2), len(post) // 8, 512)
    f, t, S = spectrogram(post, fs=sf, nperseg=nper, noverlap=nper // 2, scaling="density")
    m = (f >= 1) & (f <= 30)
    S = 10 * np.log10(S[m] + 1e-12)
    im = ax.imshow(S, aspect="auto", origin="lower", cmap="turbo",
                   extent=[t[0], t[-1], 1, 30],
                   vmin=np.median(S) - 12, vmax=np.median(S) + 20)
    for _, lo, hi, c in BANDS:
        ax.axhline(hi, color="white", lw=0.6, ls=":", alpha=0.6)
    ax.set_ylabel("Frequenz (Hz)", fontsize=9, color=C_MUTED)
    ax.set_xlabel("Zeit (s)", fontsize=9, color=C_MUTED)
    ax.tick_params(labelsize=8, colors=C_MUTED)
    cb = fig.colorbar(im, ax=ax, pad=0.012, fraction=0.035)
    cb.set_label("dB", fontsize=8, color=C_MUTED); cb.ax.tick_params(labelsize=7, colors=C_MUTED)
    ax.set_title("Spektrogramm — Frequenzgehalt über die Zeit", fontsize=10.5,
                 fontweight="bold", color=C_INK, loc="left", pad=6)

    # Donut Bandverteilung
    rel = d.get("rel") or {}
    ax = fig.add_axes([0.72, 0.50, 0.24, 0.36]); ax.set_aspect("equal"); ax.axis("off")
    vals = [rel.get(n, 0) for n, _, _, _ in BANDS]
    cols = [c for _, _, _, c in BANDS]
    if sum(vals) > 0:
        ax.pie(vals, colors=cols, startangle=90,
               wedgeprops=dict(width=0.36, edgecolor="white", linewidth=1.5),
               autopct=lambda v: f"{v:.0f}%" if v >= 6 else "",
               pctdistance=0.80, textprops=dict(fontsize=8, color="white", fontweight="bold"))
    ax.set_title("Bandverteilung", fontsize=10.5, fontweight="bold", color=C_INK, pad=8)
    for i, (n, _, _, c) in enumerate(BANDS):
        fig.text(0.72 + (i % 2) * 0.115, 0.475 - (i // 2) * 0.022, f"● {n}", color=c, fontsize=8.5)

    # PSD mit farbigen Bändern
    f, p = d.get("psd_f"), d.get("psd_p")
    ax = fig.add_axes([0.055, 0.11, 0.90, 0.28])
    if f is not None:
        for n, lo, hi, c in BANDS:
            m = (f >= lo) & (f < hi)
            ax.fill_between(f[m], 0, p[m], color=c, alpha=0.45, label=n)
        ax.plot(f, p, color=C_INK, lw=1.3)
        ap = d.get("alpha_peak")
        if ap and ap == ap:
            yv = float(p[np.abs(f - ap).argmin()])
            ax.annotate(f"Alpha-Gipfel {ap:.1f} Hz", xy=(ap, yv), xytext=(ap + 3.5, yv * 1.35),
                        fontsize=9.5, fontweight="bold", color=C_ALPHA,
                        arrowprops=dict(arrowstyle="->", color=C_ALPHA, lw=1.5))
        ax.set_xlim(1, 30)
    ax.set_xlabel("Frequenz (Hz)", fontsize=9, color=C_MUTED)
    ax.set_ylabel("Leistung (µV²/Hz)", fontsize=9, color=C_MUTED)
    ax.tick_params(labelsize=8, colors=C_MUTED)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.set_title("Leistungsspektrum — wo sitzt die Energie?", fontsize=10.5,
                 fontweight="bold", color=C_INK, loc="left", pad=6)
    ax.legend(frameon=False, fontsize=8.5, ncol=4, loc="upper right")
    _cap(fig, 0.055, "Der okzipitale Alpha-Gipfel ist der Grundrhythmus des wachen, entspannten Gehirns. "
                     "Verschiebt er sich nach links (langsamer), spricht das für eine Funktionsstörung.")
    pdf.savefig(fig); plt.close(fig)


# ── Seite 4: EEG Topografie & Symmetrie ───────────────────────────────────────
def _page_topo(pdf, d):
    fig = _page("EEG — Topografie & Symmetrie", "Anterior-posteriorer Gradient · Hemisphären-Asymmetrie · 1/f-Zerlegung", C_EEG_HDR)

    # Schemakopf mit A/P-Verlauf
    ax = fig.add_axes([0.045, 0.14, 0.27, 0.70]); ax.set_aspect("equal"); ax.axis("off")
    ax.set_xlim(-1.35, 1.35); ax.set_ylim(-1.5, 1.5)
    head = Ellipse((0, 0), 2.1, 2.35, facecolor="none", edgecolor="#98a3b0", lw=2, zorder=3)
    ax.add_patch(head)
    grad = np.linspace(0, 1, 256).reshape(-1, 1)
    im = ax.imshow(grad, extent=[-1.05, 1.05, -1.175, 1.175], origin="upper", aspect="auto",
                   cmap=matplotlib.colors.LinearSegmentedColormap.from_list(
                       "ap", ["#e67e22", "#f2f4f7", "#27ae60"]), alpha=0.55, zorder=1)
    im.set_clip_path(head)
    ax.add_patch(Polygon([[-0.17, 1.16], [0, 1.42], [0.17, 1.16]], closed=True,
                         facecolor="#e9edf2", edgecolor="#98a3b0", lw=1.5, zorder=3))
    ax.text(0, 1.30, "vorne", ha="center", fontsize=8.5, color="#c0722a", fontweight="bold")
    ax.text(0, -1.33, "hinten", ha="center", fontsize=8.5, color="#1e8449", fontweight="bold")
    par = d.get("par")
    ax.add_patch(FancyBboxPatch((-0.62, -0.22), 1.24, 0.44, boxstyle="round,pad=0.02,rounding_size=0.08",
                                facecolor="white", edgecolor=C_M, lw=2, zorder=4))
    ax.text(0, 0.08, _fmt(par, 1) + "×", ha="center", fontsize=17, fontweight="bold", color=C_M, zorder=5)
    ax.text(0, -0.12, "Alpha hinten/vorne", ha="center", fontsize=7.5, color=C_MUTED, zorder=5)
    ax.set_title("A/P-Gradient", fontsize=10.5, fontweight="bold", color=C_INK)

    # Asymmetrie
    ax = fig.add_axes([0.38, 0.50, 0.57, 0.34])
    ai = d.get("ai") or {}
    labels, vals, cols = [], [], []
    for reg in ("okzipital", "frontal"):
        for n, _, _, c in BANDS:
            v = ai.get((reg, n))
            if v is None or v != v:
                continue
            labels.append(f"{n}\n{reg[:4]}."); vals.append(v); cols.append(c)
    if vals:
        y = np.arange(len(vals))
        ax.barh(y, vals, color=cols, alpha=0.9, height=0.68)
        ax.axvline(0, color=C_INK, lw=1)
        ax.axvline(20, color="#c0392b", lw=1, ls="--", alpha=0.7)
        ax.axvline(-20, color="#c0392b", lw=1, ls="--", alpha=0.7)
        ax.set_yticks(y); ax.set_yticklabels(labels, fontsize=7.5, color=C_MUTED)
        ax.set_xlim(-40, 40); ax.invert_yaxis()
        ax.set_xlabel("← rechts dominant      Asymmetrie-Index (%)      links dominant →",
                      fontsize=8.5, color=C_MUTED)
    ax.tick_params(labelsize=8, colors=C_MUTED)
    for sp in ("top", "right", "left"):
        ax.spines[sp].set_visible(False)
    ax.set_title("Hemisphären-Symmetrie — |AI| ≤ 20 % ist normal", fontsize=10.5,
                 fontweight="bold", color=C_INK, loc="left", pad=6)

    # Aperiodik
    ax = fig.add_axes([0.38, 0.14, 0.57, 0.26])
    ap = d.get("ap")
    if ap:
        ax.loglog(ap["freqs"], ap["psd"], color=C_INK, lw=1.2, label="gemessenes Spektrum")
        ax.loglog(ap["freqs"], ap["aper_psd"], color="#e74c3c", lw=2, ls="--",
                  label=f"1/f-Untergrund (Exponent {ap['exponent']:.2f})")
        ax.legend(frameon=False, fontsize=8, loc="lower left")
    ax.set_xlabel("Frequenz (Hz)", fontsize=8.5, color=C_MUTED)
    ax.set_ylabel("Leistung", fontsize=8.5, color=C_MUTED)
    ax.tick_params(labelsize=7.5, colors=C_MUTED)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.set_title("1/f-Zerlegung — echter Rhythmus vs. Hintergrund", fontsize=10.5,
                 fontweight="bold", color=C_INK, loc="left", pad=6)
    _cap(fig, 0.075, "Gesundes waches EEG ist hinten Alpha-dominant (A/P > 1) und weitgehend symmetrisch. "
                     "Der 1/f-Untergrund trennt echte Oszillationen von Rauschen.")
    pdf.savefig(fig); plt.close(fig)


# ── Seite 5: EKG Rohsignal & Detektion ────────────────────────────────────────
def _page_ecg(pdf, d):
    e = d["ecg"]
    fig = _page("EKG — Rhythmus & QRS-Erkennung", "Originalsignal mit detektierten R-Zacken · RR-Reihe vor/nach Bereinigung", C_ECG_HDR)
    sf, t0 = d["sf"], d["t_clean"]
    i0, i1 = int(t0 * sf), int((t0 + 10) * sf)
    sig, pk = e["sig"], e["peaks"]

    ax = fig.add_axes([0.055, 0.53, 0.90, 0.33])
    t = np.arange(i0, i1) / sf
    ax.plot(t, sig[i0:i1], color="#37474f", lw=0.9)
    inw = pk[(pk >= i0) & (pk < i1)]
    ax.plot(inw / sf, sig[inw], "o", ms=7, mfc="none", mec=C_ECG, mew=2, label="erkannte R-Zacke")
    ax.set_xlim(t[0], t[-1])
    ax.set_xlabel("Zeit (s)", fontsize=9, color=C_MUTED)
    ax.set_ylabel("mV", fontsize=9, color=C_MUTED)
    ax.tick_params(labelsize=8, colors=C_MUTED)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.legend(frameon=False, fontsize=9, loc="upper right")
    ax.set_title(f"Original-EKG ({e['name']}) — 10 s mit QRS-Detektion", fontsize=10.5,
                 fontweight="bold", color=C_INK, loc="left", pad=6)

    ax = fig.add_axes([0.055, 0.13, 0.90, 0.29])
    ta, ra, msk = e["t_all"], e["rr_all"], e["mask"]
    ax.plot(ta, ra, color="#c7ccd1", lw=0.9, label="Vorselektion (roh)")
    ax.plot(ta[~msk], ra[~msk], color="#2980b9", lw=1.2, label="Nachselektion (bereinigt)")
    if msk.any():
        ax.plot(ta[msk], ra[msk], "x", color=C_ECG, ms=6, mew=1.5,
                label=f"verworfen ({msk.sum()})")
    ax.set_xlabel("Zeit (s)", fontsize=9, color=C_MUTED)
    ax.set_ylabel("RR-Intervall (ms)", fontsize=9, color=C_MUTED)
    ax.tick_params(labelsize=8, colors=C_MUTED)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.legend(frameon=False, fontsize=8.5, ncol=3, loc="upper right")
    ax.set_title("RR-Reihe — vor und nach der Artefaktbereinigung", fontsize=10.5,
                 fontweight="bold", color=C_INK, loc="left", pad=6)
    _cap(fig, 0.065, "Jede R-Zacke ist ein Herzschlag. Aus den Abständen (RR) entsteht die gesamte "
                     "Variabilitätsanalyse — deshalb muss die Detektion exakt sein.")
    pdf.savefig(fig); plt.close(fig)


# ── Seite 6: EKG Autonome Regulation ──────────────────────────────────────────
def _page_hrv(pdf, d):
    e = d["ecg"]
    td, fd = e["td"], (e["fd"] or {})
    fig = _page("EKG — Autonome Regulation", "Poincaré-Streudiagramm · Frequenzspektrum der Herzratenvariabilität", C_ECG_HDR)

    rr = e["rr"]
    ax = fig.add_axes([0.055, 0.14, 0.40, 0.70])
    if len(rr) > 3:
        x, y = rr[:-1], rr[1:]
        ax.scatter(x, y, s=16, c="#2980b9", alpha=0.45, edgecolors="none")
        mx, my = float(np.mean(x)), float(np.mean(y))
        sd1, sd2 = td.get("sd1_ms", 0), td.get("sd2_ms", 0)
        ell = Ellipse((mx, my), 2 * sd2, 2 * sd1, angle=45, facecolor="none",
                      edgecolor="#e67e22", lw=2.4, zorder=5)
        ax.add_patch(ell)
        lim = [min(x.min(), y.min()) - 40, max(x.max(), y.max()) + 40]
        ax.plot(lim, lim, color=C_MUTED, lw=0.8, ls="--", alpha=0.6)
        ax.set_xlim(lim); ax.set_ylim(lim)
        ax.text(0.03, 0.95, f"SD1 {sd1:.0f} ms  ·  SD2 {sd2:.0f} ms", transform=ax.transAxes,
                fontsize=9.5, fontweight="bold", color="#e67e22", va="top")
    ax.set_aspect("equal")
    ax.set_xlabel("RR$_n$ (ms)", fontsize=9, color=C_MUTED)
    ax.set_ylabel("RR$_{n+1}$ (ms)", fontsize=9, color=C_MUTED)
    ax.tick_params(labelsize=8, colors=C_MUTED)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.set_title("Poincaré — Schlag-zu-Schlag-Variabilität", fontsize=10.5,
                 fontweight="bold", color=C_INK, loc="left", pad=6)

    ax = fig.add_axes([0.55, 0.44, 0.40, 0.40])
    if fd and fd.get("freqs") is not None:
        f, p = np.asarray(fd["freqs"]), np.asarray(fd["psd"])
        m = (f >= 0.02) & (f <= 0.45)
        ax.plot(f[m], p[m], color=C_INK, lw=1.2)
        ax.fill_between(f[m], 0, p[m], where=(f[m] >= 0.04) & (f[m] < 0.15),
                        color="#2980b9", alpha=0.55, label="LF (0,04–0,15 Hz)")
        ax.fill_between(f[m], 0, p[m], where=(f[m] >= 0.15) & (f[m] < 0.40),
                        color="#e67e22", alpha=0.55, label="HF (0,15–0,40 Hz)")
        ax.legend(frameon=False, fontsize=8.5)
        ax.set_xlim(0.02, 0.45)
    ax.set_xlabel("Frequenz (Hz)", fontsize=9, color=C_MUTED)
    ax.set_ylabel("PSD (ms²/Hz)", fontsize=9, color=C_MUTED)
    ax.tick_params(labelsize=8, colors=C_MUTED)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.set_title("HRV-Spektrum — Sympathikus vs. Parasympathikus", fontsize=10.5,
                 fontweight="bold", color=C_INK, loc="left", pad=6)

    for i, (l, v, u, c) in enumerate([
            ("Herzfrequenz", _fmt(td.get("mean_hr_bpm"), 0), "bpm", C_ECG),
            ("SDNN", _fmt(td.get("sdnn_ms"), 0), "ms", "#8e44ad"),
            ("RMSSD", _fmt(td.get("rmssd_ms"), 0), "ms", "#2980b9"),
            ("LF/HF", _fmt(fd.get("lf_hf_ratio"), 2), "", "#d68910")]):
        _tile(fig, 0.55 + (i % 2) * 0.205, 0.255 - (i // 2) * 0.115, 0.19, 0.10, l, v, u, c)

    _cap(fig, 0.065, "Die Poincaré-Wolke zeigt die Regulationsbreite des Herzens: breit = flexibles, "
                     "gesundes autonomes Nervensystem. HF steht für Vagus (Erholung), LF für Regulation.")
    pdf.savefig(fig); plt.close(fig)


# ── Öffentliche API ───────────────────────────────────────────────────────────
def build_glory_pdf(edf: dict, edf_path: str, disp_name: str = "EDF") -> bytes:
    """Erzeugt den visuellen Report als Vektor-PDF (A4 quer)."""
    d = _collect(edf, edf_path)
    buf = io.BytesIO()
    with PdfPages(buf) as pdf:
        _page_cover(pdf, d, disp_name)
        if d.get("post") is not None:
            _page_raw_eeg(pdf, edf, d)
            _page_spectrum(pdf, d)
            _page_topo(pdf, d)
        if d.get("ecg"):
            _page_ecg(pdf, d)
            _page_hrv(pdf, d)
    return buf.getvalue()
