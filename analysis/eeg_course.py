"""Repräsentativer Verlauf des posterioren EEG über die ganze Aufnahme.

Die Hauptauswertung der Reports nutzt das saubere 60-s-Fenster mit dem klarsten
Alpha-Grundrhythmus (`glory_report._best_alpha_window`). Das ist gewollt: Es beschreibt den
bestmöglichen Grundrhythmus. Es ist aber nicht repräsentativ für die Aufnahme, Phasen mit
Verlangsamung oder Müdigkeit fallen dabei heraus (Review R7, 02.10.2026).

Dieses Modul ergänzt deshalb ein zweites Auswertungsziel: dieselben Kennwerte für jeden
sauberen, nicht überlappenden 60-s-Abschnitt, zusammengefasst als Median und
Interquartilsabstand. Die Werte des Hauptfensters ändern sich dadurch nicht.

Streamlit-frei, damit Tests und beide Reports es direkt nutzen können.
"""

from __future__ import annotations

import numpy as np

from analysis.spectral import _band_power, _compute_psd, _peak_freq_cog

#: (Name, untere Grenze, obere Grenze) — identisch mit den Report-Bändern.
BAENDER = (("Delta", 1.0, 4.0), ("Theta", 4.0, 8.0), ("Alpha", 8.0, 13.0), ("Beta", 13.0, 30.0))

#: Weniger saubere Abschnitte ergeben keinen sinnvollen Verlauf.
MIN_ABSCHNITTE = 3


def _sauber(t0: float, t1: float, segments) -> bool:
    return not any(s["start_s"] < t1 and s["end_s"] > t0 for s in segments or [])


def representative_course(sig, fs: float, segments=None, win_s: float = 60.0) -> dict:
    """Kennwerte je sauberem 60-s-Abschnitt und ihre Zusammenfassung.

    Rückgabe:
        n_abschnitte   — Zahl der 60-s-Abschnitte der Aufnahme
        n_sauber       — davon ohne Überschneidung mit einem Artefaktsegment und auswertbar
        abschnitte     — je Abschnitt: start_s, rel (Band → %), dar, alpha_cog
        zusammenfassung — je Kennwert: median, q25, q75, min, max
                          (leer, wenn weniger als MIN_ABSCHNITTE saubere Abschnitte)
    """
    if sig is None or fs <= 0:
        return {"n_abschnitte": 0, "n_sauber": 0, "abschnitte": [], "zusammenfassung": {}}
    n_win = int(len(sig) / fs // win_s)
    abschnitte = []
    for k in range(n_win):
        t0, t1 = k * win_s, (k + 1) * win_s
        if not _sauber(t0, t1, segments):
            continue
        f, p = _compute_psd(sig[int(t0 * fs):int(t1 * fs)], fs)
        if f is None:
            continue
        bp = {n: _band_power(f, p, lo, hi) for n, lo, hi in BAENDER}
        tot = sum(bp.values())
        if tot <= 0:
            continue
        abschnitte.append({
            "start_s": t0,
            "rel": {n: v / tot * 100 for n, v in bp.items()},
            "dar": bp["Delta"] / bp["Alpha"] if bp["Alpha"] > 0 else float("nan"),
            "alpha_cog": _peak_freq_cog(f, p, 8.0, 13.0),
        })

    zusammenfassung = {}
    if len(abschnitte) >= MIN_ABSCHNITTE:
        reihen = {f"{n} relativ": [a["rel"][n] for a in abschnitte] for n, _, _ in BAENDER}
        reihen["Delta/Alpha"] = [a["dar"] for a in abschnitte]
        reihen["Alpha-Schwerpunkt"] = [a["alpha_cog"] for a in abschnitte]
        for name, werte in reihen.items():
            w = np.asarray([v for v in werte if v == v], dtype=float)
            if len(w) < MIN_ABSCHNITTE:
                continue
            q25, med, q75 = np.percentile(w, [25, 50, 75])
            zusammenfassung[name] = {"median": float(med), "q25": float(q25), "q75": float(q75),
                                     "min": float(w.min()), "max": float(w.max())}
    return {"n_abschnitte": n_win, "n_sauber": len(abschnitte),
            "abschnitte": abschnitte, "zusammenfassung": zusammenfassung}
