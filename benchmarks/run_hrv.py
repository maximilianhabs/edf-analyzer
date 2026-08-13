"""Vergleicht HRV aus DETEKTIERTEN mit HRV aus ANNOTIERTEN Schlägen.

    python3 benchmarks/run_hrv.py 100 108
    python3 benchmarks/run_hrv.py --all --csv benchmarks/results/hrv_alle44.csv

Regeln siehe `docs/BENCHMARK_HRV.md` — vor der ersten Messung geschrieben. Dieses Skript
setzt sie nur um.

Kern des Ganzen: auf beide Schlagreihen läuft **dieselbe** Kette wie in der Anwendung
(`build_rr_series` → `clean_rr` → `compute_hrv_time_domain`). Der einzige Unterschied
zwischen den zwei Durchläufen ist, woher die Schläge kommen. Alles andere gleich zu halten
ist die ganze Aussagekraft dieser Messung — jede Abweichung an anderer Stelle würde als
Detektionsfehler erscheinen.
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

from fetch_mitdb import BEWERTET  # noqa: E402
from mitdb import BEAT_SYMBOLS, DATA, SKIP_START_S  # noqa: E402

#: Grenze der Schichtung, vor der Messung festgelegt (docs/BENCHMARK_HRV.md).
SINUSNAH_MAX_PCT = 5.0

#: Berichtete Kennwerte — die, die in Oberfläche und Report stehen.
#: Schlüssel exakt so, wie `compute_hrv_time_domain()` sie liefert — nicht neu benannt,
#: damit kein Übertragungsfehler zwischen Anwendung und Benchmark entstehen kann.
KENNWERTE = ("mean_hr_bpm", "sdnn_ms", "rmssd_ms", "pnn50_pct")


def _hrv(peaks: np.ndarray, fs: float) -> dict:
    """Die Kette der Anwendung, unverändert."""
    from analysis.ecg import build_rr_series, compute_hrv_time_domain

    serie = build_rr_series(np.asarray(peaks, dtype=int), fs)
    if serie is None:
        return {}
    sauber = serie.clean_rr
    if len(sauber) < 5:
        return {}
    return compute_hrv_time_domain(sauber)


def eine_aufnahme(nr: int) -> dict:
    import wfdb

    from analysis.ecg import detect_r_peaks_polarity_safe

    pfad = str(DATA / str(nr))
    rec = wfdb.rdrecord(pfad)
    ann = wfdb.rdann(pfad, "atr")
    fs = float(rec.fs)

    # MLII, wo vorhanden — „der EKG-Kanal ist korrekt gewählt" (docs/BENCHMARK_HRV.md).
    idx = list(rec.sig_name).index("MLII") if "MLII" in rec.sig_name else 0
    signal = np.asarray(rec.p_signal[:, idx], dtype=float)

    ist_schlag = np.array([s in BEAT_SYMBOLS for s in ann.symbol], dtype=bool)
    symbole = np.asarray(ann.symbol)[ist_schlag]
    beats = np.asarray(ann.sample, dtype=np.int64)[ist_schlag]

    ab = int(SKIP_START_S * fs)
    behalten = beats >= ab
    beats, symbole = beats[behalten], symbole[behalten]

    _, det, _ = detect_r_peaks_polarity_safe(signal, fs)
    det = np.asarray(det, dtype=np.int64)
    det = det[det >= ab]

    wahr, gemessen = _hrv(beats, fs), _hrv(det, fs)

    # Anteil nicht-normaler Schläge — die Schichtungsgrösse.
    anteil_abnorm = float((symbole != "N").mean() * 100) if symbole.size else float("nan")

    zeile = {
        "record": nr, "channel": rec.sig_name[idx],
        "beats_ann": int(beats.size), "beats_det": int(det.size),
        "abnorm_pct": round(anteil_abnorm, 2),
        "gruppe": "sinusnah" if anteil_abnorm <= SINUSNAH_MAX_PCT else "arrhythmisch",
    }
    for k in KENNWERTE:
        w, g = wahr.get(k, float("nan")), gemessen.get(k, float("nan"))
        zeile[f"{k}_ann"] = round(w, 2)
        zeile[f"{k}_det"] = round(g, 2)
        zeile[f"{k}_diff"] = round(g - w, 2)
        # Relativer Fehler nur, wo der Bezugswert nicht praktisch null ist: bei pNN50 = 0
        # (völlig regelmässiger Rhythmus) wäre jede Abweichung „unendlich Prozent" und
        # würde jede Zusammenfassung unbrauchbar machen.
        zeile[f"{k}_diff_pct"] = round((g - w) / w * 100, 2) if w and abs(w) > 1e-9 else ""
    return zeile


def zusammenfassung(zeilen: list, name: str) -> dict:
    """Median und Spannweite der Abweichungen. Median, weil einzelne Aufnahmen mit schwerer
    Arrhythmie einen Mittelwert dominieren würden, ohne den typischen Fall zu beschreiben."""
    aus = {"record": name, "channel": f"{len(zeilen)} Aufnahmen"}
    for k in KENNWERTE:
        d = np.array([z[f"{k}_diff"] for z in zeilen
                      if isinstance(z[f"{k}_diff"], float) and np.isfinite(z[f"{k}_diff"])])
        p = np.array([z[f"{k}_diff_pct"] for z in zeilen
                      if isinstance(z[f"{k}_diff_pct"], float)])
        aus[f"{k}_diff"] = round(float(np.median(d)), 2) if d.size else ""
        aus[f"{k}_diff_pct"] = round(float(np.median(p)), 2) if p.size else ""
        aus[f"{k}_ann"] = round(float(np.median(np.abs(d))), 2) if d.size else ""   # |Median|
        aus[f"{k}_det"] = round(float(np.max(np.abs(d))), 2) if d.size else ""      # Maximum
    return aus


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("records", nargs="*", type=int)
    p.add_argument("--all", action="store_true", help="alle 44 bewerteten Aufnahmen")
    p.add_argument("--csv", type=Path)
    args = p.parse_args()

    records = BEWERTET if args.all else args.records
    if not records:
        p.print_help()
        return 1

    fehlend = [r for r in records if not (DATA / f"{r}.dat").exists()]
    if fehlend:
        print(f"Nicht geladen: {fehlend}\n  python3 benchmarks/fetch_mitdb.py --all")
        return 1

    kopf = (f"{'Rec':>5} {'abn%':>5} {'Gruppe':<12} "
            f"{'HF ann':>7} {'HF det':>7} {'ΔHF':>6} "
            f"{'SDNN a':>7} {'SDNN d':>7} {'ΔSDNN':>7} "
            f"{'RMSSDa':>7} {'RMSSDd':>7} {'ΔRMSSD':>7} {'ΔpNN50':>7}")
    print(kopf)
    print("-" * len(kopf))

    zeilen = []
    for nr in records:
        z = eine_aufnahme(nr)
        zeilen.append(z)
        print(f"{z['record']:>5} {z['abnorm_pct']:>5.1f} {z['gruppe']:<12} "
              f"{z['mean_hr_bpm_ann']:>7.1f} {z['mean_hr_bpm_det']:>7.1f} {z['mean_hr_bpm_diff']:>6.1f} "
              f"{z['sdnn_ms_ann']:>7.1f} {z['sdnn_ms_det']:>7.1f} {z['sdnn_ms_diff']:>7.1f} "
              f"{z['rmssd_ms_ann']:>7.1f} {z['rmssd_ms_det']:>7.1f} {z['rmssd_ms_diff']:>7.1f} "
              f"{z['pnn50_pct_diff']:>7.1f}")

    if len(zeilen) > 1:
        print("-" * len(kopf))
        gruppen = [("sinusnah", [z for z in zeilen if z["gruppe"] == "sinusnah"]),
                   ("arrhythmisch", [z for z in zeilen if z["gruppe"] == "arrhythmisch"])]
        zusammen = []
        for name, teil in gruppen:
            if not teil:
                continue
            zusammen.append(zusammenfassung(teil, f"Median {name}"))
        zusammen.append(zusammenfassung(zeilen, "Median GESAMT"))
        for g in zusammen:
            print(f"{g['record']:>20} ({g['channel']:>13})  "
                  f"ΔHF {g['mean_hr_bpm_diff']:>6}  ΔSDNN {g['sdnn_ms_diff']:>7}  "
                  f"ΔRMSSD {g['rmssd_ms_diff']:>7}  ΔpNN50 {g['pnn50_pct_diff']:>6}")
        zeilen.extend(zusammen)

    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        felder = list(zeilen[0])
        with open(args.csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=felder, extrasaction="ignore")
            w.writeheader()
            w.writerows(zeilen)
        print(f"\nGeschrieben: {args.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
