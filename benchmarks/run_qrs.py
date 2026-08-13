"""Führt den QRS-Benchmark aus: Detektor auf MIT-BIH, Abgleich, Kennzahlen.

    python3 benchmarks/run_qrs.py 100                  # eine Aufnahme
    python3 benchmarks/run_qrs.py 100 108 203 207 222  # mehrere
    python3 benchmarks/run_qrs.py --all                # alle 44
    python3 benchmarks/run_qrs.py --all --csv benchmarks/results/eigen.csv

Regeln siehe `docs/BENCHMARK_QRS.md`. Dieses Skript setzt sie nur um; die Entscheidungen
darüber, was gezählt wird, stehen dort und in `mitdb.py`/`matching.py`.
"""

from __future__ import annotations

import argparse
import csv
import sys
import warnings
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore")

from fetch_mitdb import BEWERTET, SELEKTIERT, ZUFALLSAUSWAHL  # noqa: E402
from matching import match  # noqa: E402
from mitdb import DATA, SKIP_START_S, lade  # noqa: E402


def detektiere(signal: np.ndarray, fs: float, verfahren: str) -> np.ndarray:
    """Ruft einen Detektor auf. `eigen` ist der Standardweg der Anwendung.

    Bewusst derselbe Einstiegspunkt, den auch die App benutzt
    (`detect_r_peaks_polarity_safe`) — inklusive Polaritätskorrektur. Ein Benchmark, der einen
    anderen Weg nähme als die Anwendung, misst etwas, das niemand benutzt.
    """
    from analysis.ecg import detect_r_peaks_polarity_safe, detect_r_peaks_validated_ex

    if verfahren == "eigen":
        _, peaks, _ = detect_r_peaks_polarity_safe(signal, fs)
        return np.asarray(peaks, dtype=np.int64)

    # Für die validierten Detektoren gilt dieselbe Reihenfolge wie in der App: erst die
    # Polarität korrigieren, dann detektieren (Engzee scheitert sonst, siehe
    # tests/test_ecg_pipeline.py).
    korrigiert, _, _ = detect_r_peaks_polarity_safe(signal, fs)
    res = detect_r_peaks_validated_ex(korrigiert, fs, method=verfahren)
    if res.fell_back:
        raise RuntimeError(f"{verfahren} lief nicht: {res.reason}")
    return np.asarray(res.peaks, dtype=np.int64)


def eine_aufnahme(nr: int, verfahren: str) -> dict:
    r = lade(nr)
    det = detektiere(r.signal, r.fs, verfahren)

    # Dieselbe Anfangsregel wie für die Annotationen — sonst zählte man Schläge als verpasst,
    # die man gar nicht suchen durfte, oder Detektionen als falsch, die vor dem Fenster liegen.
    det = det[det >= int(SKIP_START_S * r.fs)]

    m = match(r.beats, det, r.fs)
    return {
        "record": nr, "channel": r.channel, "beats": int(r.beats.size),
        "detected": int(det.size), "tp": m.tp, "fp": m.fp, "fn": m.fn,
        "se_pct": round(m.sensitivity * 100, 3), "ppv_pct": round(m.ppv * 100, 3),
        "f1_pct": round(m.f1 * 100, 3), "der_pct": round(m.der * 100, 3),
        "offset_mean_ms": round(m.offset_mean_ms, 2),
        "offset_sd_ms": round(m.offset_sd_ms, 2),
        "offset_abs_mean_ms": round(m.offset_abs_mean_ms, 2),
    }


def gesamt(zeilen: list) -> dict:
    """Gesamtwert über die AUFSUMMIERTEN TP/FP/FN, nicht als Mittel der Einzelwerte — sonst
    zählte eine Aufnahme mit 1500 Schlägen so viel wie eine mit 2500."""
    tp = sum(z["tp"] for z in zeilen)
    fp = sum(z["fp"] for z in zeilen)
    fn = sum(z["fn"] for z in zeilen)
    se = tp / (tp + fn) if (tp + fn) else float("nan")
    pp = tp / (tp + fp) if (tp + fp) else float("nan")
    return {"record": "GESAMT", "channel": f"{len(zeilen)} Aufnahmen",
            "beats": tp + fn, "detected": tp + fp, "tp": tp, "fp": fp, "fn": fn,
            "se_pct": round(se * 100, 3), "ppv_pct": round(pp * 100, 3),
            "f1_pct": round(2 * se * pp / (se + pp) * 100, 3) if (se + pp) else float("nan"),
            "der_pct": round((fp + fn) / (tp + fn) * 100, 3) if (tp + fn) else float("nan"),
            "offset_mean_ms": "", "offset_sd_ms": "", "offset_abs_mean_ms": ""}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("records", nargs="*", type=int)
    p.add_argument("--all", action="store_true", help="alle 44 bewerteten Aufnahmen")
    p.add_argument("--detector", default="eigen",
                   help="eigen (Standard) | hamilton | pan_tompkins | christov | engzee | two_average")
    p.add_argument("--csv", type=Path, help="Ergebnis zusätzlich als CSV schreiben")
    args = p.parse_args()

    records = BEWERTET if args.all else args.records
    if not records:
        p.print_help()
        return 1

    fehlend = [r for r in records if not (DATA / f"{r}.dat").exists()]
    if fehlend:
        print(f"Nicht geladen: {fehlend}\n  python3 benchmarks/fetch_mitdb.py "
              f"{' '.join(map(str, fehlend))}")
        return 1

    kopf = f"{'Rec':>5s} {'Kanal':<6s} {'Schläge':>8s} {'TP':>6s} {'FP':>5s} {'FN':>5s} " \
           f"{'Se %':>7s} {'+P %':>7s} {'F1 %':>7s} {'Δt ms':>7s} {'|Δt| ms':>8s}"
    print(f"Detektor: {args.detector}")
    print(kopf)
    print("-" * len(kopf))

    zeilen = []
    for nr in records:
        z = eine_aufnahme(nr, args.detector)
        zeilen.append(z)
        print(f"{z['record']:>5} {z['channel']:<6s} {z['beats']:>8d} {z['tp']:>6d} "
              f"{z['fp']:>5d} {z['fn']:>5d} {z['se_pct']:>7.2f} {z['ppv_pct']:>7.2f} "
              f"{z['f1_pct']:>7.2f} {z['offset_mean_ms']:>7.1f} {z['offset_abs_mean_ms']:>8.1f}")

    if len(zeilen) > 1:
        print("-" * len(kopf))
        # Geschichtet berichten: die Datenbank ist nicht repräsentativ zusammengestellt
        # (siehe fetch_mitdb.ZUFALLSAUSWAHL). Ein Gesamtwert allein wäre irreführend.
        gruppen = [
            ("Zufallsauswahl", [z for z in zeilen if z["record"] in ZUFALLSAUSWAHL]),
            ("selektiert", [z for z in zeilen if z["record"] in SELEKTIERT]),
        ]
        zusammen = []
        for name, teil in gruppen:
            if not teil:
                continue
            g = gesamt(teil)
            g["record"] = name
            zusammen.append(g)
            print(f"{name:>14s} {g['beats']:>8d} {g['tp']:>6d} {g['fp']:>5d} {g['fn']:>5d} "
                  f"{g['se_pct']:>7.2f} {g['ppv_pct']:>7.2f} {g['f1_pct']:>7.2f}")
        g = gesamt([z for z in zeilen])
        zusammen.append(g)
        print(f"{'GESAMT':>14s} {g['beats']:>8d} {g['tp']:>6d} {g['fp']:>5d} {g['fn']:>5d} "
              f"{g['se_pct']:>7.2f} {g['ppv_pct']:>7.2f} {g['f1_pct']:>7.2f}")
        zeilen.extend(zusammen)

    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with open(args.csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(zeilen[0]))
            w.writeheader()
            w.writerows(zeilen)
        print(f"\nGeschrieben: {args.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
