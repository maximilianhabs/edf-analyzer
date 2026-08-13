"""Lädt Aufnahmen der MIT-BIH Arrhythmia Database nach `benchmarks/data/`.

Die Daten liegen bewusst NICHT im Repository: 48 Aufnahmen sind rund 500 MB, und sie sind
öffentlich und dauerhaft verfügbar. Im Repository liegen nur die Skripte und die Ergebnisse.

    python3 benchmarks/fetch_mitdb.py 100          # eine Aufnahme
    python3 benchmarks/fetch_mitdb.py --all        # alle 44 der Auswertung

Quelle: PhysioNet, Open Data Commons Attribution License.
Moody GB, Mark RG. The impact of the MIT-BIH Arrhythmia Database.
IEEE Eng in Med and Biol 20(3):45-50 (2001).
"""

import argparse
import sys
import urllib.request
from pathlib import Path

BASE = "https://physionet.org/files/mitdb/1.0.0"
DATA = Path(__file__).resolve().parent / "data"

#: Alle 48 Aufnahmen der Datenbank.
ALLE = [100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 111, 112, 113, 114, 115, 116,
        117, 118, 119, 121, 122, 123, 124, 200, 201, 202, 203, 205, 207, 208, 209, 210,
        212, 213, 214, 215, 217, 219, 220, 221, 222, 223, 228, 230, 231, 232, 233, 234]

#: Aufnahmen mit Herzschrittmacher — nach ANSI/AAMI EC57 aus der QRS-Bewertung ausgeschlossen.
#: Siehe docs/BENCHMARK_QRS.md; der Ausschluss ist Konvention, nicht unsere Wahl.
PACED = [102, 104, 107, 217]

#: Die 44 Aufnahmen, über die ausgewertet wird.
BEWERTET = [r for r in ALLE if r not in PACED]

#: Signal, Kopfdaten, Annotationen — alle drei werden gebraucht.
ENDUNGEN = (".dat", ".hea", ".atr")


def hole(record: int, ziel: Path = DATA) -> bool:
    ziel.mkdir(parents=True, exist_ok=True)
    vollstaendig = True
    for endung in ENDUNGEN:
        name = f"{record}{endung}"
        pfad = ziel / name
        if pfad.exists() and pfad.stat().st_size > 0:
            continue
        url = f"{BASE}/{name}"
        try:
            with urllib.request.urlopen(url, timeout=120) as antwort:
                daten = antwort.read()
            pfad.write_bytes(daten)
            print(f"  {name:12s} {len(daten):>10,} Byte")
        except Exception as exc:
            print(f"  {name:12s} FEHLER: {exc}")
            vollstaendig = False
    return vollstaendig


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("records", nargs="*", type=int, help="Aufnahmenummern, z. B. 100 108")
    p.add_argument("--all", action="store_true", help="alle 44 bewerteten Aufnahmen")
    args = p.parse_args()

    records = BEWERTET if args.all else args.records
    if not records:
        p.print_help()
        return 1

    print(f"Ziel: {DATA}")
    fehler = [r for r in records if not hole(r)]
    print(f"\n{len(records) - len(fehler)} von {len(records)} vollständig.")
    if fehler:
        print(f"Unvollständig: {fehler}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
