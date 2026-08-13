"""Vergleicht das CosEn-Screening mit den Rhythmus-Annotationen der MIT-BIH AFib-Datenbank.

    python3 benchmarks/run_afib.py 04015
    python3 benchmarks/run_afib.py --all --csv benchmarks/results/afib_alle23.csv
    python3 benchmarks/run_afib.py --all --quelle qrs      # Durchlauf B

Regeln siehe `docs/BENCHMARK_AFIB.md` — vor der ersten Messung geschrieben.

Gerechnet wird über `analysis.rhythm_screening.sliding_cosen()`, denselben Einstiegspunkt wie
in der Anwendung, samt Artefaktausschluss. Ein Benchmark, der die Fenster selbst bildete,
misst etwas, das niemand angezeigt bekommt.
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

from fetch_afdb import BEWERTET, DATA  # noqa: E402

#: Rhythmen, die als „AFib" gelten.
POSITIV = {"(AFIB"}

#: Rhythmen, die WEDER als AFib NOCH als unauffällig gewertet werden (docs/BENCHMARK_AFIB.md):
#: Vorhofflattern als normal zu verbuchen wäre irreführend, als Vorhofflimmern falsch.
AUSGESCHLOSSEN = {"(AFL", "(J"}


def rhythmus_intervalle(pfad: str, sig_len: int) -> list[tuple[int, int, str]]:
    """(start, ende, label) in Samples aus den .atr-Rhythmusmarken."""
    import wfdb

    ann = wfdb.rdann(pfad, "atr")
    marken = [(int(s), (a or "").strip()) for s, a in zip(ann.sample, ann.aux_note) if a]
    if not marken:
        return []
    grenzen = [m[0] for m in marken] + [sig_len]
    return [(grenzen[i], grenzen[i + 1], marken[i][1]) for i in range(len(marken))]


def fenster_wahrheit(iv: list, a0: int, a1: int) -> tuple[str, bool]:
    """Label eines Fensters [a0,a1) und ob es gemischt ist.

    Gibt ("afib" | "kein_afib" | "ausgeschlossen", gemischt) zurück. Ausgeschlossen wird,
    sobald Vorhofflattern oder ein junktionaler Rhythmus auch nur hineinreicht — an einem
    solchen Fenster kann die Auswertung nicht sinnvoll richtig oder falsch sein.
    """
    anteile: dict[str, int] = {}
    for s, e, label in iv:
        ueberlappung = min(a1, e) - max(a0, s)
        if ueberlappung > 0:
            anteile[label] = anteile.get(label, 0) + ueberlappung
    if not anteile:
        return "ausgeschlossen", False
    if any(k in AUSGESCHLOSSEN for k in anteile):
        return "ausgeschlossen", len(anteile) > 1
    gemischt = len(anteile) > 1
    gesamt = sum(anteile.values())
    afib = sum(v for k, v in anteile.items() if k in POSITIV)
    return ("afib" if afib * 2 >= gesamt else "kein_afib"), gemischt


def eine_aufnahme(rec: str, quelle: str) -> dict:
    import wfdb

    from analysis.rhythm_screening import sliding_cosen

    pfad = str(DATA / rec)
    r = wfdb.rdrecord(pfad)
    fs = float(r.fs)
    # ERSTER KANAL, und zwar in MIKROVOLT. wfdb liefert Millivolt; die Anwendung reicht
    # durchgehend µV an `sqi_segments` weiter (views/rhythm_screening.py: `sig_uv`), und
    # dessen Flatline-Regel prüft gegen eine ABSOLUTE Schwelle von 5 µV. Mit mV übergeben
    # gilt jedes Segment als variationslos, `sliding_cosen` liefert null Fenster und der
    # Benchmark meldet stumm „nichts bewertbar" statt eines Fehlers. Beim ersten Lauf genau
    # so passiert. Im QRS-Benchmark fiel es nicht auf, weil die Detektionsschwelle dort
    # relativ (Perzentil) und damit einheitenunabhängig ist.
    sig = np.asarray(r.p_signal[:, 0], dtype=float) * 1000.0

    if quelle == "eigen":
        from analysis.ecg import detect_r_peaks_polarity_safe
        _, peaks, _ = detect_r_peaks_polarity_safe(sig, fs)
        peaks = np.asarray(peaks, dtype=np.int64)
    else:
        peaks = np.asarray(wfdb.rdann(pfad, "qrs").sample, dtype=np.int64)

    fenster = sliding_cosen(sig, peaks, fs)
    iv = rhythmus_intervalle(pfad, r.sig_len)

    z = {"record": rec, "quelle": quelle, "fs": fs,
         "stunden": round(r.sig_len / fs / 3600, 2),
         "schlaege": int(peaks.size),
         "fenster_gesamt": int(r.sig_len / fs // 30),
         "fenster_bewertbar": 0, "ausgeschlossen": 0, "gemischt": 0,
         "tp": 0, "fp": 0, "tn": 0, "fn": 0,
         "tp_rein": 0, "fp_rein": 0, "tn_rein": 0, "fn_rein": 0}

    for f in fenster:
        a0, a1 = int(f["t0"] * fs), int(f["t1"] * fs)
        wahrheit, gemischt = fenster_wahrheit(iv, a0, a1)
        if wahrheit == "ausgeschlossen":
            z["ausgeschlossen"] += 1
            continue
        z["fenster_bewertbar"] += 1
        if gemischt:
            z["gemischt"] += 1
        vorhergesagt = f["zone"] == "afib_verdaechtig"
        ist = wahrheit == "afib"
        schluessel = "tp" if (ist and vorhergesagt) else \
                     "fn" if (ist and not vorhergesagt) else \
                     "fp" if vorhergesagt else "tn"
        z[schluessel] += 1
        if not gemischt:
            z[schluessel + "_rein"] += 1

    # Verworfen durch Artefaktausschluss oder zu wenige Schläge — gehört ausgewiesen.
    z["verworfen"] = z["fenster_gesamt"] - len(fenster)
    z.update(kennzahlen(z))
    return z


def kennzahlen(z: dict, suffix: str = "") -> dict:
    tp, fp = z["tp" + suffix], z["fp" + suffix]
    tn, fn = z["tn" + suffix], z["fn" + suffix]
    def q(a, b):
        return round(a / b * 100, 2) if b else float("nan")
    return {
        "afib_anteil_pct": q(tp + fn, tp + fn + tn + fp),
        "sens_pct": q(tp, tp + fn),
        "spez_pct": q(tn, tn + fp),
        "ppv_pct": q(tp, tp + fp),
        "npv_pct": q(tn, tn + fn),
    }


def gesamt(zeilen: list, name: str, suffix: str = "") -> dict:
    """Über die AUFSUMMIERTEN Fensterzahlen, nicht als Mittel der Einzelwerte."""
    s = {k: sum(z[k + suffix] for z in zeilen) for k in ("tp", "fp", "tn", "fn")}
    aus = {"record": name, "quelle": f"{len(zeilen)} Aufnahmen",
           "stunden": round(sum(z["stunden"] for z in zeilen), 1),
           "fenster_bewertbar": s["tp"] + s["fp"] + s["tn"] + s["fn"],
           "gemischt": sum(z["gemischt"] for z in zeilen),
           "ausgeschlossen": sum(z["ausgeschlossen"] for z in zeilen),
           "verworfen": sum(z["verworfen"] for z in zeilen), **s}
    aus.update(kennzahlen(s))
    return aus


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("records", nargs="*")
    p.add_argument("--all", action="store_true", help="alle 23 bewerteten Aufnahmen")
    p.add_argument("--quelle", default="eigen", choices=("eigen", "qrs"),
                   help="eigen = Detektor der Anwendung (Durchlauf A) | qrs = Referenzschläge (B)")
    p.add_argument("--csv", type=Path)
    args = p.parse_args()

    records = BEWERTET if args.all else args.records
    if not records:
        p.print_help()
        return 1

    fehlend = [r for r in records if not (DATA / f"{r}.dat").exists()]
    if fehlend:
        print(f"Nicht geladen: {fehlend}\n  python3 benchmarks/fetch_afdb.py --all")
        return 1

    kopf = (f"{'Rec':>7} {'h':>5} {'bewertbar':>10} {'AFib%':>6} "
            f"{'TP':>5} {'FP':>5} {'TN':>6} {'FN':>5} "
            f"{'Sens%':>7} {'Spez%':>7} {'+P%':>7}")
    print(f"Durchlauf: {'A (eigener Detektor)' if args.quelle=='eigen' else 'B (.qrs-Referenz)'}")
    print(kopf)
    print("-" * len(kopf))

    zeilen = []
    for rec in records:
        z = eine_aufnahme(rec, args.quelle)
        zeilen.append(z)
        print(f"{z['record']:>7} {z['stunden']:>5.1f} {z['fenster_bewertbar']:>10} "
              f"{z['afib_anteil_pct']:>6.1f} {z['tp']:>5} {z['fp']:>5} {z['tn']:>6} "
              f"{z['fn']:>5} {z['sens_pct']:>7.2f} {z['spez_pct']:>7.2f} {z['ppv_pct']:>7.2f}",
              flush=True)

    if len(zeilen) > 1:
        print("-" * len(kopf))
        g = gesamt(zeilen, "GESAMT")
        gr = gesamt(zeilen, "nur reine Fenster", "_rein")
        for x in (g, gr):
            print(f"{x['record']:>18} {x['fenster_bewertbar']:>8} Fenster  "
                  f"AFib {x['afib_anteil_pct']:>5.1f} %  Sens {x['sens_pct']:>6.2f} %  "
                  f"Spez {x['spez_pct']:>6.2f} %  +P {x['ppv_pct']:>6.2f} %")
        print(f"\nausgeschlossen (AFL/J): {g['ausgeschlossen']}  ·  "
              f"gemischte Fenster: {g['gemischt']}  ·  "
              f"verworfen (Artefakt/zu wenig Schläge): {g['verworfen']}")
        zeilen.extend([g, gr])

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
