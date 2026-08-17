"""Lädt die MIT-BIH Normal Sinus Rhythm Database nach `benchmarks/data_nsrdb/`.

Die NEGATIVKOHORTE. Ohne sie lässt sich die klinisch entscheidende Frage nicht beantworten:
Schlägt das Screening bei jemandem an, der KEIN Vorhofflimmern hat? Die AFib-Datenbank enthält
keine einzige unauffällige Aufnahme — dort ist die Spezifität auf Aufnahmeebene grundsätzlich
nicht messbar.

18 Aufnahmen à rund 25 Stunden, 128 Hz, Probanden ohne nachweisbare relevante Arrhythmien.
Umfang rund 630 MB; Downloadzeit bei uns 20-30 Minuten (siehe fetch_afdb.py zur Einordnung,
warum das länger dauert als die reine Bandbreite vermuten liesse).

    python3 benchmarks/fetch_nsrdb.py 16265        # eine Aufnahme
    python3 benchmarks/fetch_nsrdb.py --all        # alle 18 (rund 630 MB)

WICHTIG — was diese Kohorte NICHT ist: eine neurologische Routineambulanz. Es sind gesunde
Freiwillige ohne Extrasystolen und ohne Medikation. Eine hier gemessene Spezifität ist deshalb
eine OBERGRENZE; echte Patienten mit Ektopie erzeugen mehr Fehlalarme. Diese Frage braucht die
Arrhythmie-Datenbank und eine eigene Betrachtung.

Quelle: PhysioNet, Open Data Commons Attribution License.
Goldberger AL et al. PhysioBank, PhysioToolkit, and PhysioNet. Circulation 101(23):e215 (2000).
"""

import argparse
import sys
import urllib.request
from pathlib import Path

BASE = "https://physionet.org/files/nsrdb/1.0.0"
DATA = Path(__file__).resolve().parent / "data_nsrdb"

ALLE = ["16265", "16272", "16273", "16420", "16483", "16539", "16773", "16786", "16795",
        "17052", "17453", "18177", "18184", "19088", "19090", "19093", "19140", "19830"]

BEWERTET = list(ALLE)

#: `.atr` trägt hier Schlag-Annotationen (überwiegend `N`), keine Rhythmuswechsel — die
#: Wahrheit dieser Kohorte ist die Zugehörigkeit zur Datenbank selbst: kein Vorhofflimmern.
ENDUNGEN = (".dat", ".hea", ".atr")


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
            print(f"  {name:12s} {len(daten):>12,} Byte", flush=True)
        except Exception as exc:
            print(f"  {name:12s} FEHLER: {exc}", flush=True)
            vollstaendig = False
    return vollstaendig


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("records", nargs="*")
    p.add_argument("--all", action="store_true", help="alle 18 Aufnahmen")
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
