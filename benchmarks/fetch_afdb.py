"""Lädt Aufnahmen der MIT-BIH Atrial Fibrillation Database nach `benchmarks/data_afdb/`.

Wie bei der Arrhythmie-Datenbank liegen die Daten bewusst NICHT im Repository: 23 Aufnahmen
à 10 Stunden sind rund 640 MB, und sie sind öffentlich und dauerhaft verfügbar. Im Repository
liegen nur die Skripte und die Ergebnisse.

Downloadzeit: bei 20-50 MBit/s theoretisch 2-5 Minuten — in unserer eigenen Erfahrung eher
eine gute halbe Stunde, weil PhysioNets Server oft der Flaschenhals sind, nicht die eigene
Leitung. Einplanen, nicht nebenbei laufen lassen und vergessen.

    python3 benchmarks/fetch_afdb.py 04015        # eine Aufnahme (~28 MB)
    python3 benchmarks/fetch_afdb.py --all        # alle 23

Quelle: PhysioNet, Open Data Commons Attribution License.
Moody GB, Mark RG. A new method for detecting atrial fibrillation using R-R intervals.
Computers in Cardiology 10:227-230 (1983).
"""

import argparse
import sys
import urllib.request
from pathlib import Path

BASE = "https://physionet.org/files/afdb/1.0.0"
DATA = Path(__file__).resolve().parent / "data_afdb"

#: Alle 25 Kennungen der Datenbank.
ALLE = ["00735", "03665", "04015", "04043", "04048", "04126", "04746", "04908", "04936",
        "05091", "05121", "05261", "06426", "06453", "06995", "07162", "07859", "07879",
        "07910", "08215", "08219", "08378", "08405", "08434", "08455"]

#: Zu diesen beiden Aufnahmen gibt es KEIN Signal — nur Annotationen (auf PhysioNet fehlt die
#: .dat-Datei, geprüft 2026-08-13). Ein Detektor kann darauf nichts finden; sie fallen deshalb
#: aus der Bewertung. Der Ausschluss ist Datenlage, nicht unsere Wahl.
OHNE_SIGNAL = ["00735", "03665"]

#: Die 23 Aufnahmen, über die ausgewertet wird.
BEWERTET = [r for r in ALLE if r not in OHNE_SIGNAL]

#: Signal, Kopfdaten, Rhythmus-Annotationen, Referenz-Schläge.
#: `.atr` trägt die RHYTHMUS-Annotationen ((AFIB, (N, …) — die Wahrheit dieses Benchmarks.
#: `.qrs` trägt maschinell erzeugte, NICHT von Hand geprüfte Schlagpositionen; sie dienen
#: nur der Trennung „CosEn allein" von „Detektor + CosEn", siehe docs/BENCHMARK_AFIB.md.
ENDUNGEN = (".dat", ".hea", ".atr", ".qrs")


def hole(record: str, ziel: Path = DATA) -> bool:
    ziel.mkdir(parents=True, exist_ok=True)
    vollstaendig = True
    for endung in ENDUNGEN:
        name = f"{record}{endung}"
        pfad = ziel / name
        if pfad.exists() and pfad.stat().st_size > 0:
            continue
        try:
            with urllib.request.urlopen(f"{BASE}/{name}", timeout=300) as antwort:
                daten = antwort.read()
            pfad.write_bytes(daten)
            print(f"  {name:12s} {len(daten):>12,} Byte")
        except Exception as exc:
            print(f"  {name:12s} FEHLER: {exc}")
            vollstaendig = False
    return vollstaendig


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("records", nargs="*", help="Kennungen, z. B. 04015")
    p.add_argument("--all", action="store_true", help="alle 23 bewerteten Aufnahmen")
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
