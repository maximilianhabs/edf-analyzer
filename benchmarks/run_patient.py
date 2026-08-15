"""Aggregiert die bereits gerechneten Fenster zu Abschnitten und wertet auf Patientenebene aus.

    python3 benchmarks/run_patient.py --csv benchmarks/results/patient_ebene.csv

Regeln siehe `docs/BENCHMARK_AFIB.md`, Abschnitt „Protokoll-Erweiterung: die Frage auf
Patientenebene". Rechnet NICHTS aus den Rohdaten neu — liest die beiden bereits geschriebenen
Fenster-CSVs (`pwave_fenster_alle23.csv`, `nsrdb_fenster_alle18.csv`) und fasst sie zu
nicht überlappenden Abschnitten von 10/20/30 Minuten zusammen.

Verdikt je Abschnitt wie in der Anwendung (`classify_afib_risk`): Verdacht, sobald MINDESTENS
EIN auswertbares Fenster im AFib-Bereich liegt.

Drei Gruppen, gebildet über die WAHRHEIT der Fenster (nicht über die Datenbankzugehörigkeit):
    A — gesund (nsrdb, jedes Fenster "kein_afib")
    B — AFib-Patient (afdb), aber im Abschnitt kein einziges AFib-Fenster
    C — AFib-Patient (afdb), im Abschnitt mindestens ein AFib-Fenster
Ein Abschnitt aus B ohne Verdacht ist richtig negativ, keine verpasste Diagnose — deshalb die
Trennung von A und B, obwohl beide "kein Verdacht" erwarten.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

FENSTER_S = 30.0

#: Abschnittslängen in Fenstern (je 30 s). 20 min = Dauer der Anwendung; 10/30 min zusätzlich,
#: damit die Dauerabhängigkeit sichtbar wird statt behauptet.
LAENGEN = {"10min": 20, "20min": 40, "30min": 60}


def lies_fenster(pfad: Path) -> list[dict]:
    with open(pfad, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def cosen_verdacht(f: dict) -> bool:
    return f.get("cosen_zone") == "afib_verdaechtig"


def coherence_verdacht(f: dict) -> bool:
    c = f.get("coherence", "")
    return c != "" and float(c) < 0.35


def kombi_verdacht(f: dict) -> bool:
    return cosen_verdacht(f) or coherence_verdacht(f)


#: Je Verfahren: True, sobald IRGENDEIN Fenster des Abschnitts anschlägt — dieselbe Regel wie
#: `classify_afib_risk` in der Anwendung.
VERFAHREN = {"cosen": cosen_verdacht, "coherence": coherence_verdacht, "kombi": kombi_verdacht}


def block_verdacht(block: list[dict], einzelfenster_fn) -> bool:
    return any(einzelfenster_fn(f) for f in block)


def abschnitte_bilden(fenster: list[dict], n_fenster: int) -> list[list[dict]]:
    """Nicht überlappende Blöcke von `n_fenster` Fenstern, je Aufnahme neu begonnen —
    ein Abschnitt darf keine Aufnahmegrenze überschreiten."""
    aus = []
    nach_aufnahme: dict[str, list[dict]] = {}
    for f in fenster:
        nach_aufnahme.setdefault(f["record"], []).append(f)
    for _rec, fl in nach_aufnahme.items():
        fl = sorted(fl, key=lambda z: float(z["t0_s"]))
        for i in range(0, len(fl) - n_fenster + 1, n_fenster):
            aus.append(fl[i:i + n_fenster])
    return aus


def gruppe_des_abschnitts(block: list[dict], herkunft: str) -> str:
    if herkunft == "nsrdb":
        return "A"
    hat_afib = any(f["wahrheit"] == "afib" for f in block)
    return "C" if hat_afib else "B"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--afdb-csv", type=Path,
                   default=Path("benchmarks/results/pwave_fenster_alle23.csv"))
    p.add_argument("--nsrdb-csv", type=Path,
                   default=Path("benchmarks/results/nsrdb_fenster_alle18.csv"))
    p.add_argument("--csv", type=Path, help="Abschnittsebene als CSV schreiben")
    args = p.parse_args()

    for pfad in (args.afdb_csv, args.nsrdb_csv):
        if not pfad.exists():
            print(f"Fehlt: {pfad}\n  python3 benchmarks/run_pwave.py --all\n"
                  f"  python3 benchmarks/run_nsrdb.py --all")
            return 1

    afdb = lies_fenster(args.afdb_csv)
    nsrdb = lies_fenster(args.nsrdb_csv)
    # nsrdb hat keine "gemischt"-Spalte mit Bedeutung, afdb schon — gemischte Fenster bleiben
    # in der Aggregation ENTHALTEN (anders als auf Fensterebene): ein Abschnitt ist real und
    # enthält reale Übergänge; sie herauszuschneiden würde einen Abschnitt vortäuschen, der so
    # nie vorkam. Auf Fensterebene war das anders, weil dort das EINZELNE Fenster bewertet wird.

    alle_zeilen = []
    for laenge_name, n_fenster in LAENGEN.items():
        blocks = (
            [(b, "afdb") for b in abschnitte_bilden(afdb, n_fenster)] +
            [(b, "nsrdb") for b in abschnitte_bilden(nsrdb, n_fenster)]
        )
        zaehler = {g: {v: {"tp": 0, "fp": 0, "tn": 0, "fn": 0} for v in VERFAHREN}
                   for g in "ABC"}
        for block, herkunft in blocks:
            gruppe = gruppe_des_abschnitts(block, herkunft)
            rec = block[0]["record"]
            t0 = block[0]["t0_s"]
            zeile = {"laenge": laenge_name, "record": rec, "t0_s": t0, "gruppe": gruppe}
            for name, fn in VERFAHREN.items():
                positiv = block_verdacht(block, fn)
                zeile[f"{name}_verdacht"] = int(positiv)
                if gruppe == "C":
                    zaehler[gruppe][name]["tp" if positiv else "fn"] += 1
                else:
                    zaehler[gruppe][name]["fp" if positiv else "tn"] += 1
            alle_zeilen.append(zeile)

        print(f"\n=== Abschnittslänge {laenge_name} ({n_fenster} Fenster) ===")
        n_a = sum(1 for b, h in blocks if gruppe_des_abschnitts(b, h) == "A")
        n_b = sum(1 for b, h in blocks if gruppe_des_abschnitts(b, h) == "B")
        n_c = sum(1 for b, h in blocks if gruppe_des_abschnitts(b, h) == "C")
        print(f"Abschnitte: A(gesund)={n_a}  B(AFib-Pat., kein AFib im Abschnitt)={n_b}  "
              f"C(AFib im Abschnitt)={n_c}")
        for verfahren in VERFAHREN:
            tp = zaehler["C"][verfahren]["tp"]; fn = zaehler["C"][verfahren]["fn"]
            tn_a = zaehler["A"][verfahren]["tn"]; fp_a = zaehler["A"][verfahren]["fp"]
            tn_b = zaehler["B"][verfahren]["tn"]; fp_b = zaehler["B"][verfahren]["fp"]
            sens = tp / (tp + fn) * 100 if (tp + fn) else float("nan")
            spez_a = tn_a / (tn_a + fp_a) * 100 if (tn_a + fp_a) else float("nan")
            spez_b = tn_b / (tn_b + fp_b) * 100 if (tn_b + fp_b) else float("nan")
            print(f"  {verfahren:10s}  Sens(C) {sens:6.2f} %  ({tp}/{tp+fn})   "
                  f"Spez(A,gesund) {spez_a:6.2f} % ({fp_a} FA/{n_a})   "
                  f"Spez(B,Pat.o.Episode) {spez_b:6.2f} % ({fp_b} FA/{n_b})")

    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with open(args.csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(alle_zeilen[0]))
            w.writeheader()
            w.writerows(alle_zeilen)
        print(f"\nJeder Abschnitt geschrieben: {args.csv}  ({len(alle_zeilen)} Zeilen)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
