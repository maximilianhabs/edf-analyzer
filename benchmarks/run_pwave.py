"""P-Wellen-Kohärenz gegen die Rhythmus-Annotationen der MIT-BIH AFib-Datenbank.

    python3 benchmarks/run_pwave.py 04746                  # Kontrollpunkt, eine Aufnahme
    python3 benchmarks/run_pwave.py --all --csv benchmarks/results/pwave_alle23.csv

Regeln siehe `docs/BENCHMARK_PWAVE.md` — vor der ersten Messung geschrieben.

Gerechnet wird über **dieselben Fenster**, die `sliding_cosen()` liefert, und über denselben
Einstiegspunkt, den die Anwendung benutzt (`p_wave_analysis.analyze_window`, Stufe ②b in
`views/rhythm_screening.py`). Nur so lassen sich CosEn und P-Welle fensterweise gegeneinander
stellen — die Voraussetzung für die Frage nach der Kombination.

`--fenster-csv` schreibt JEDES ausgewertete Fenster einzeln heraus (CosEn, Kohärenz, Wahrheit).
Die Zusammenfassungen weiter unten sind daraus vollständig nachrechenbar; wer eine andere
Schwelle prüfen will, braucht dafür nicht erneut 234 Stunden zu rechnen.
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
import warnings
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore")

from fetch_afdb import BEWERTET, DATA  # noqa: E402
from run_afib import fenster_wahrheit, rhythmus_intervalle  # noqa: E402


def fenster_einer_aufnahme(rec: str) -> list[dict]:
    """Ein Eintrag je auswertbarem 30-s-Fenster, mit beiden Markern und der Wahrheit."""
    import wfdb

    from analysis.ecg import detect_r_peaks_polarity_safe
    from analysis.p_wave_analysis import analyze_window, bandpass_ecg
    from analysis.rhythm_screening import sliding_cosen

    pfad = str(DATA / rec)
    r = wfdb.rdrecord(pfad)
    fs = float(r.fs)
    # Mikrovolt — siehe die ausführliche Begründung in run_afib.py.
    sig = np.asarray(r.p_signal[:, 0], dtype=float) * 1000.0

    _, peaks, _ = detect_r_peaks_polarity_safe(sig, fs)
    peaks = np.asarray(peaks, dtype=np.int64)

    fenster = sliding_cosen(sig, peaks, fs)
    iv = rhythmus_intervalle(pfad, r.sig_len)

    # Einmal über die ganze Aufnahme filtern, nicht je Fenster — so verlangt es der Docstring
    # von `analyze_window`, und so macht es auch die Anwendung.
    sig_filt = bandpass_ecg(sig, fs)

    aus = []
    for f in fenster:
        wahrheit, gemischt = fenster_wahrheit(iv, int(f["t0"] * fs), int(f["t1"] * fs))
        p = analyze_window(sig_filt, peaks, fs, f["t0"], f["t1"])
        aus.append({
            "record": rec, "t0_s": round(f["t0"], 1), "n_beats": f["n_beats"],
            "cosen": round(f["cosen"], 4) if np.isfinite(f["cosen"]) else "",
            "cosen_zone": f["zone"],
            "coherence": round(p["coherence"], 4) if p and np.isfinite(p["coherence"]) else "",
            "p_amplitude_uv": round(p["amplitude_uv"], 2) if p and np.isfinite(p.get("amplitude_uv", float("nan"))) else "",
            "p_verdict": p["verdict"] if p else "nicht_auswertbar",
            "wahrheit": wahrheit, "gemischt": int(gemischt),
        })
    return aus


def verteilung(werte: np.ndarray) -> str:
    if werte.size == 0:
        return "keine"
    return (f"n={werte.size:5d}  Median {np.median(werte):5.2f}  "
            f"Quartile {np.percentile(werte, 25):5.2f}/{np.percentile(werte, 75):5.2f}")


def bericht(zeilen: list) -> None:
    """Verteilungen zuerst, Kennzahlen danach. Die Trennung der Klassen ist die eigentliche
    Frage; eine Kennzahl an einer festen Schwelle sagt nur, wo der Schnitt zufällig liegt."""
    from analysis.p_wave_analysis import COH_UNCERTAIN

    def koh(bedingung) -> np.ndarray:
        return np.array([z["coherence"] for z in zeilen
                         if z["coherence"] != "" and bedingung(z)], dtype=float)

    afib = koh(lambda z: z["wahrheit"] == "afib")
    kein = koh(lambda z: z["wahrheit"] == "kein_afib")
    print("\nP-Wellen-Kohärenz")
    print(f"  AFib-Fenster       {verteilung(afib)}")
    print(f"  Nicht-AFib-Fenster {verteilung(kein)}")
    if afib.size and kein.size:
        print(f"  Abstand der Mediane: {np.median(kein) - np.median(afib):+.2f}")

    ohne = sum(1 for z in zeilen if z["coherence"] == "")
    print(f"  nicht auswertbar: {ohne} von {len(zeilen)} Fenstern")

    # Kennzahlen an der BESTEHENDEN Schwelle (< 0,35 = AFib-Hinweis), unverändert.
    tp = int((afib < COH_UNCERTAIN).sum())
    fn = int((afib >= COH_UNCERTAIN).sum())
    fp = int((kein < COH_UNCERTAIN).sum())
    tn = int((kein >= COH_UNCERTAIN).sum())
    def q(a, b):
        return f"{a / b * 100:6.2f} %" if b else "     — "
    print(f"\nAn der bestehenden Schwelle (Kohärenz < {COH_UNCERTAIN})")
    print(f"  TP {tp:5d}  FP {fp:5d}  TN {tn:6d}  FN {fn:5d}")
    print(f"  Sensitivität {q(tp, tp + fn)}   Spezifität {q(tn, tn + fp)}   "
          f"Vorhersagewert {q(tp, tp + fp)}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("records", nargs="*")
    p.add_argument("--all", action="store_true", help="alle 23 bewerteten Aufnahmen")
    p.add_argument("--fenster-csv", type=Path, default=None,
                   help="jedes einzelne Fenster herausschreiben (Standard bei --all)")
    args = p.parse_args()

    records = BEWERTET if args.all else args.records
    if not records:
        p.print_help()
        return 1

    fehlend = [r for r in records if not (DATA / f"{r}.dat").exists()]
    if fehlend:
        print(f"Nicht geladen: {fehlend}\n  python3 benchmarks/fetch_afdb.py --all")
        return 1

    alle: list[dict] = []
    for rec in records:
        t0 = time.perf_counter()
        zeilen = fenster_einer_aufnahme(rec)
        dauer = time.perf_counter() - t0
        n_afib = sum(1 for z in zeilen if z["wahrheit"] == "afib")
        print(f"{rec}: {len(zeilen):5d} Fenster ({n_afib} AFib), {dauer:6.1f} s", flush=True)
        alle.extend(zeilen)

    bericht(alle)

    ziel = args.fenster_csv
    if ziel is None and args.all:
        ziel = Path("benchmarks/results/pwave_fenster_alle23.csv")
    if ziel:
        ziel.parent.mkdir(parents=True, exist_ok=True)
        with open(ziel, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(alle[0]))
            w.writeheader()
            w.writerows(alle)
        print(f"\nJedes Fenster geschrieben: {ziel}  ({len(alle)} Zeilen)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
