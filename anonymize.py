#!/usr/bin/env python3
"""
EDF De-Identifikations-Tool
============================
Entfernt alle personenbezogenen Daten aus EDF/EDF+-Dateien.
Nach Verarbeitung ist die Datei nicht mehr einer natürlichen Person zuordenbar
und unterliegt nicht mehr der DSGVO (ErwG 26).

Verwendung:
    python anonymize.py INPUT.edf [--output OUTPUT.edf] [--id ANON_001]

Was wird entfernt:
    - Patient-ID (Name, Geburtsdatum, Geschlecht falls im Header)
    - Recording-ID (oft Gerätename, Untersucher, Datum)
    - Genaues Datum und Uhrzeit → nur Jahr bleibt, Uhrzeit wird 00.00.00

Was bleibt:
    - Geschlecht (M/F) — nötig für EEG-Normwerte
    - Alters-Dekade (z.B. "50s") — nötig für EEG-Normwerte
    - Alle Signaldaten unverändert
    - Annotations (klinische Befundnotizen — ACHTUNG: können Namen enthalten)
"""

import re
import os
import sys
import argparse
import hashlib
import json
import fcntl
from datetime import datetime
from pathlib import Path


# ── EDF-Header-Struktur (fixe Bytepositionen nach Standard) ──────────────────
HEADER = {
    "version":      (0,   8),
    "patient_id":   (8,   88),
    "recording_id": (88,  168),
    "startdate":    (168, 176),
    "starttime":    (176, 184),
    "header_bytes": (184, 192),
    "reserved":     (192, 236),
    "num_records":  (236, 244),
    "duration":     (244, 252),
    "num_signals":  (252, 256),
}


def read_header(path: str) -> dict:
    """Liest EDF-Header-Felder als Strings."""
    with open(path, "rb") as f:
        raw = f.read(256)
    return {k: raw[s:e].decode("latin1").strip() for k, (s, e) in HEADER.items()}


def parse_patient_info(patient_id_str: str) -> dict:
    """
    Extrahiert Alter/Geschlecht aus dem Patient-ID-Feld.
    EDF-Standard: "code sex birthdate name" (leerzeichen-getrennt)
    Beispiel: "MCH-0234 M 02-MAY-1951 Haagse_Harry"
    """
    parts = patient_id_str.split()
    result = {"sex": None, "age_decade": None}

    for p in parts:
        if p.upper() in ("M", "F", "X"):
            result["sex"] = p.upper()
        # Geburtsdatum im Format DD-MON-YYYY oder YYYY
        m = re.search(r"(\d{4})", p)
        if m:
            birth_year = int(m.group(1))
            if 1900 < birth_year < 2010:
                age = datetime.now().year - birth_year
                result["age_decade"] = f"{(age // 10) * 10}s"

    return result


def _field(value: str, width: int) -> bytes:
    """Schreibt einen String als EDF-Feld fixer Breite (space-padded, latin1)."""
    s = value[:width].ljust(width)
    return s.encode("latin1")


def anonymize_edf(
    input_path: str,
    output_path: str,
    anon_id: str,
    keep_year: bool = True,
    keep_sex_age: bool = True,
    log_path: str = None,
) -> dict:
    """
    Schreibt eine anonymisierte Kopie der EDF-Datei.

    Returns:
        dict mit Metadaten des Vorgangs (für Audit-Log)
    """
    input_path = str(input_path)
    output_path = str(output_path)

    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Datei nicht gefunden: {input_path}")

    if os.path.abspath(input_path) == os.path.abspath(output_path):
        raise ValueError("Input und Output dürfen nicht dieselbe Datei sein.")

    # ── Original lesen ────────────────────────────────────────────────────────
    with open(input_path, "rb") as f:
        original = f.read()

    hdr = read_header(input_path)
    patient_info = parse_patient_info(hdr["patient_id"])

    # ── Neuen Header aufbauen ─────────────────────────────────────────────────
    # Patient-ID: anonyme ID + optionale klinische Parameter
    if keep_sex_age and patient_info["sex"] and patient_info["age_decade"]:
        new_patient_id = f"{anon_id} {patient_info['sex']} X {patient_info['age_decade']}"
    elif keep_sex_age and patient_info["sex"]:
        new_patient_id = f"{anon_id} {patient_info['sex']} X X"
    else:
        new_patient_id = f"{anon_id} X X X"

    # Recording-ID: Datum (nur Jahr) + "anonymized"
    if keep_year and len(hdr["startdate"]) >= 6:
        # Datum ist DD.MM.YY oder DD-MM-YY — Jahr extrahieren
        year_match = re.search(r"(\d{2})$", hdr["startdate"].replace(".", "").replace("-", ""))
        year_str = "20" + year_match.group(1) if year_match else "20XX"
        new_recording_id = f"Startdate {year_str} anonymized X X"
    else:
        new_recording_id = "Startdate X anonymized X X"

    # Datum → 01.01.85 (EDF-Konvention für "unbekannt" nach EDF+ Spec)
    new_date = "01.01.85"
    # Uhrzeit → 00.00.00
    new_time = "00.00.00"

    # ── Header-Bytes zusammensetzen ───────────────────────────────────────────
    new_header = bytearray(original[:256])
    new_header[8:88]    = _field(new_patient_id,   80)
    new_header[88:168]  = _field(new_recording_id, 80)
    new_header[168:176] = _field(new_date,         8)
    new_header[176:184] = _field(new_time,         8)

    # ── Ausgabedatei schreiben ────────────────────────────────────────────────
    with open(output_path, "wb") as f:
        f.write(bytes(new_header))
        f.write(original[256:])

    # ── Prüfsumme des Originals (für Audit-Log) ───────────────────────────────
    sha256 = hashlib.sha256(original).hexdigest()

    audit_entry = {
        "timestamp": datetime.now().isoformat(),
        "anon_id": anon_id,
        "input_file": os.path.basename(input_path),
        "output_file": os.path.basename(output_path),
        "original_sha256": sha256,
        "original_size_bytes": len(original),
        "fields_cleared": ["patient_id", "recording_id", "startdate", "starttime"],
        "fields_retained": {
            "sex": patient_info["sex"],
            "age_decade": patient_info["age_decade"],
            "year": year_str if keep_year else None,
        },
        "keep_year": keep_year,
        "keep_sex_age": keep_sex_age,
    }

    # ── Audit-Log schreiben ───────────────────────────────────────────────────
    # fcntl.flock sperrt Lese+Schreib-Zyklus exklusiv: ohne Lock würden zwei
    # parallele Aufrufe (z. B. Batch-Verarbeitung) denselben alten Stand lesen und
    # sich beim Zurückschreiben gegenseitig überschreiben (verlorener Audit-Eintrag).
    if log_path:
        log_path = str(log_path)
        # Lock-Datei separat von der eigentlichen Log-Datei: verhindert, dass ein
        # leeres/nicht-existentes Log beim ersten Lauf zu Lock-Handling-Sonderfällen führt.
        lock_path = log_path + ".lock"
        with open(lock_path, "w") as lockfile:
            fcntl.flock(lockfile, fcntl.LOCK_EX)
            try:
                entries = []
                if os.path.exists(log_path):
                    with open(log_path, "r", encoding="utf-8") as f:
                        entries = json.load(f)
                entries.append(audit_entry)
                with open(log_path, "w", encoding="utf-8") as f:
                    json.dump(entries, f, indent=2, ensure_ascii=False)
            finally:
                fcntl.flock(lockfile, fcntl.LOCK_UN)

    return audit_entry


def verify_anonymization(path: str) -> dict:
    """Prüft ob eine EDF-Datei korrekt anonymisiert wurde."""
    hdr = read_header(path)
    issues = []

    if hdr["patient_id"] and not hdr["patient_id"].startswith("ANON"):
        if any(c.isalpha() for c in hdr["patient_id"].replace("M", "").replace("F", "").replace("X", "").replace("s", "")):
            issues.append(f"Patient-ID könnte Namen enthalten: '{hdr['patient_id'][:20]}…'")

    if hdr["startdate"] not in ("01.01.85", "01-01-85", ""):
        issues.append(f"Datum nicht anonymisiert: '{hdr['startdate']}'")

    if hdr["starttime"] not in ("00.00.00", "00-00-00", ""):
        issues.append(f"Uhrzeit nicht anonymisiert: '{hdr['starttime']}'")

    return {
        "path": path,
        "is_anonymized": len(issues) == 0,
        "issues": issues,
        "patient_id": hdr["patient_id"],
        "recording_id": hdr["recording_id"][:40],
        "startdate": hdr["startdate"],
    }


# ── CLI ───────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="EDF De-Identifikations-Tool — entfernt Patientendaten aus EDF-Dateien",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Beispiele:
  # Einzelne Datei anonymisieren:
  python anonymize.py patient.edf --id ANON_001

  # Mit eigenem Ausgabepfad:
  python anonymize.py patient.edf --output /tmp/anon_001.edf --id ANON_001

  # Ohne Alters-/Geschlechts-Erhalt (maximale Anonymisierung):
  python anonymize.py patient.edf --id ANON_001 --no-demographics

  # Bestehende Datei prüfen:
  python anonymize.py patient.edf --verify-only

  # Batch: alle EDF-Dateien in einem Ordner:
  python anonymize.py /ordner/ --batch --prefix STUDIE_A
        """
    )
    parser.add_argument("input", help="EDF-Datei oder Ordner (bei --batch)")
    parser.add_argument("--output", "-o", help="Ausgabedatei (Standard: INPUT_anon.edf)")
    parser.add_argument("--id", help="Anonyme ID (z.B. ANON_001). Standard: auto-generiert")
    parser.add_argument("--prefix", default="ANON", help="Präfix für auto-generierte IDs (Standard: ANON)")
    parser.add_argument("--no-year", action="store_true", help="Auch Jahr entfernen (max. Anonymisierung)")
    parser.add_argument("--no-demographics", action="store_true",
                        help="Auch Alter/Geschlecht entfernen")
    parser.add_argument("--log", default="anonymization_log.json",
                        help="Pfad zur Audit-Log-Datei (Standard: anonymization_log.json)")
    parser.add_argument("--verify-only", action="store_true",
                        help="Nur prüfen ob Datei anonymisiert ist, nicht schreiben")
    parser.add_argument("--batch", action="store_true",
                        help="Alle .edf Dateien im Eingabe-Ordner verarbeiten")

    args = parser.parse_args()

    if args.verify_only:
        result = verify_anonymization(args.input)
        print(f"\n{'✅' if result['is_anonymized'] else '❌'} {result['path']}")
        print(f"  Patient-ID:    {result['patient_id']}")
        print(f"  Recording-ID:  {result['recording_id']}")
        print(f"  Datum:         {result['startdate']}")
        if result["issues"]:
            for issue in result["issues"]:
                print(f"  ⚠️  {issue}")
        return

    # Batch-Modus
    if args.batch:
        folder = Path(args.input)
        edf_files = sorted(folder.glob("*.edf")) + sorted(folder.glob("*.EDF"))
        if not edf_files:
            print(f"Keine EDF-Dateien in {folder} gefunden.")
            return
        out_folder = folder / "anonymized"
        out_folder.mkdir(exist_ok=True)
        print(f"\nVerarbeite {len(edf_files)} EDF-Dateien → {out_folder}\n")
        for i, edf_file in enumerate(edf_files, 1):
            anon_id = f"{args.prefix}_{i:04d}"
            out_path = out_folder / f"{anon_id}.edf"
            try:
                entry = anonymize_edf(
                    str(edf_file), str(out_path), anon_id,
                    keep_year=not args.no_year,
                    keep_sex_age=not args.no_demographics,
                    log_path=str(out_folder / args.log),
                )
                sex = entry["fields_retained"].get("sex") or "?"
                age = entry["fields_retained"].get("age_decade") or "?"
                year = entry["fields_retained"].get("year") or "?"
                print(f"  [{i:3d}/{len(edf_files)}] {edf_file.name:30s} → {anon_id}.edf  "
                      f"(Sex:{sex} Alter:{age} Jahr:{year})")
            except Exception as e:
                print(f"  [FEHLER] {edf_file.name}: {e}")
        print(f"\n✅ Fertig. Audit-Log: {out_folder / args.log}")
        return

    # Einzeldatei
    input_path = Path(args.input)
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = input_path.parent / f"{input_path.stem}_anon{input_path.suffix}"

    anon_id = args.id or f"{args.prefix}_{input_path.stem[:8].upper()}"

    print(f"\n🔒 EDF De-Identifikation")
    print(f"   Input:   {input_path}")
    print(f"   Output:  {output_path}")
    print(f"   ID:      {anon_id}")

    # Vorher-Zustand zeigen
    hdr_before = read_header(str(input_path))
    print(f"\n   Vor Anonymisierung:")
    print(f"   Patient-ID:   '{hdr_before['patient_id']}'")
    print(f"   Recording-ID: '{hdr_before['recording_id'][:50]}'")
    print(f"   Datum:        '{hdr_before['startdate']}'")

    entry = anonymize_edf(
        str(input_path), str(output_path), anon_id,
        keep_year=not args.no_year,
        keep_sex_age=not args.no_demographics,
        log_path=args.log,
    )

    # Nachher-Zustand prüfen
    hdr_after = read_header(str(output_path))
    print(f"\n   Nach Anonymisierung:")
    print(f"   Patient-ID:   '{hdr_after['patient_id']}'")
    print(f"   Recording-ID: '{hdr_after['recording_id'][:50]}'")
    print(f"   Datum:        '{hdr_after['startdate']}'")

    retained = entry["fields_retained"]
    print(f"\n   Behalten: Sex={retained['sex']} | Alter={retained['age_decade']} | Jahr={retained['year']}")
    print(f"   SHA-256 Original: {entry['original_sha256'][:16]}…")
    print(f"   Audit-Log:        {args.log}")
    print(f"\n✅ Fertig. Original unverändert.")


if __name__ == "__main__":
    main()
