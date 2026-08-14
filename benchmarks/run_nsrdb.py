"""CosEn und P-Wellen-Kohärenz auf der Negativkohorte (MIT-BIH Normal Sinus Rhythm).

    python3 benchmarks/run_nsrdb.py 16265
    python3 benchmarks/run_nsrdb.py --all --fenster-csv benchmarks/results/nsrdb_fenster_alle18.csv

Regeln siehe `docs/BENCHMARK_AFIB.md`, Abschnitt „Protokoll-Erweiterung: die Frage auf
Patientenebene". Alle Fenster gelten als NICHT-AFib (Wahrheit dieser Kohorte: gesund,
siehe fetch_nsrdb.py — kein Extrasystolen-, kein Medikationsscreening).

Schreibt wie `run_pwave.py` jedes Fenster einzeln — Grundlage für die Aggregation zu
20-Minuten-Abschnitten in Schritt 4, ohne dass dafür erneut über die Rohdaten gerechnet
werden muss.
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

from fetch_nsrdb import BEWERTET, DATA  # noqa: E402


def fenster_einer_aufnahme(rec: str) -> list[dict]:
    import wfdb

    from analysis.ecg import detect_r_peaks_polarity_safe
    from analysis.p_wave_analysis import analyze_window, bandpass_ecg
    from analysis.rhythm_screening import sliding_cosen

    pfad = str(DATA / rec)
    r = wfdb.rdrecord(pfad)
    fs = float(r.fs)
    sig = np.asarray(r.p_signal[:, 0], dtype=float) * 1000.0   # mV -> µV, s. run_afib.py

    _, peaks, _ = detect_r_peaks_polarity_safe(sig, fs)
    peaks = np.asarray(peaks, dtype=np.int64)

    fenster = sliding_cosen(sig, peaks, fs)
    sig_filt = bandpass_ecg(sig, fs)

    aus = []
    for f in fenster:
        p = analyze_window(sig_filt, peaks, fs, f["t0"], f["t1"])
        aus.append({
            "record": rec, "t0_s": round(f["t0"], 1), "n_beats": f["n_beats"],
            "cosen": round(f["cosen"], 4) if np.isfinite(f["cosen"]) else "",
            "cosen_zone": f["zone"],
            "coherence": round(p["coherence"], 4) if p and np.isfinite(p["coherence"]) else "",
            "p_verdict": p["verdict"] if p else "nicht_auswertbar",
            "wahrheit": "kein_afib", "gemischt": 0,
        })
    return aus


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("records", nargs="*")
    p.add_argument("--all", action="store_true")
    p.add_argument("--fenster-csv", type=Path, default=None)
    args = p.parse_args()

    records = BEWERTET if args.all else args.records
    if not records:
        p.print_help()
        return 1

    fehlend = [r for r in records if not (DATA / f"{r}.dat").exists()]
    if fehlend:
        print(f"Nicht geladen: {fehlend}\n  python3 benchmarks/fetch_nsrdb.py --all")
        return 1

    alle: list[dict] = []
    for rec in records:
        t0 = time.perf_counter()
        zeilen = fenster_einer_aufnahme(rec)
        dauer = time.perf_counter() - t0
        n_cosen_fp = sum(1 for z in zeilen if z["cosen_zone"] == "afib_verdaechtig")
        n_p_fp = sum(1 for z in zeilen if z["coherence"] != "" and z["coherence"] < 0.35)
        print(f"{rec}: {len(zeilen):5d} Fenster, CosEn-FP {n_cosen_fp:4d}, "
              f"P-Welle-FP {n_p_fp:4d}, {dauer:6.1f} s", flush=True)
        alle.extend(zeilen)

    if alle:
        c_fp = sum(1 for z in alle if z["cosen_zone"] == "afib_verdaechtig")
        p_fp = sum(1 for z in alle if z["coherence"] != "" and z["coherence"] < 0.35)
        n = len(alle)
        print(f"\nGESAMT {n} Fenster (alles gesund)")
        print(f"  CosEn   Spezifität {100*(1-c_fp/n):6.2f} %  ({c_fp} Fehlalarme)")
        print(f"  P-Welle Spezifität {100*(1-p_fp/n):6.2f} %  ({p_fp} Fehlalarme)")

    ziel = args.fenster_csv
    if ziel is None and args.all:
        ziel = Path("benchmarks/results/nsrdb_fenster_alle18.csv")
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
