#!/usr/bin/env python3
"""Jeder Session-State-Schlüssel muss eingeordnet sein: Ergebnis, Einstellung oder Sitzung.

Warum es diesen Prüfer gibt (User-Fund 2026-08-13): Ein Report zeigte Werte einer früher
geladenen Aufnahme unter dem Namen der aktuellen. Ursache war Session-State als Cache ohne
Bezug zur Datei, an keiner Ladestelle verworfen. Der Fehler war nicht zu sehen — nichts stürzte
ab, die Zahlen blieben plausibel, der Dateiname stimmte sogar.

Die Reparatur (`core.shared.invalidate_file_state`) hilft nur, solange neue Schlüssel dort
landen. Ein Schlüssel, den jemand nächstes Jahr hinzufügt und nicht einträgt, bringt genau
denselben Fehler zurück. Deshalb hier die Ratsche: unbekannte Schlüssel sind ein Fehler, bis
jemand sie einordnet.

Dependency-frei, wie die anderen Prüfer.

    python3 tools/check_session_state.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent

#: Schlüssel, die WEITERGELTEN dürfen, weil sie nicht vom Dateiinhalt abhängen.
#:
#: Einstellungen — beschreiben, WIE gerechnet wird, nicht WAS gemessen wurde. Sie hängen an
#: Widgets; sie beim Dateiwechsel zu löschen wäre nicht nur unnötig, sondern quittiert
#: Streamlit mit einem Fehler, wenn das Widget gerade gerendert wird.
EINSTELLUNGEN = {
    "art_consensus", "art_flag_sus", "art_island", "art_region", "artifact_screen_len",
    "hrv_window_choice", "rhythm_canvas", "spec_heavy",
}

#: Sitzungsebene — Anmeldung, Sprache, Dateiauswahl selbst. Überlebt jeden Dateiwechsel.
SITZUNG = {
    "_edf_auth", "_cookie_mgr", "lang", "_lang_switch", "_lang_user_choice",
    "session_upload_token", "edf_path", "edf_display_name", "_state_for_path",
    "phi_pending_path", "phi_pending_name",
    # An JEDEM Einstiegspunkt in views/file_patient.py ausdrücklich gesetzt (geprüft
    # 2026-08-13) — ein Verwerfen hier würde die Freigabe verzögert wiederherstellen,
    # nicht sicherer machen.
    "phi_validated", "phi_has_patient_data",
}

MUSTER = re.compile(r'session_state(?:\.get\(\s*|\.pop\(\s*|\.setdefault\(\s*|\[)\s*["\']([A-Za-z0-9_]+)["\']')
MUSTER_ATTR = re.compile(r'session_state\.([A-Za-z_][A-Za-z0-9_]*)')
NICHT_KEYS = {"get", "pop", "setdefault", "clear", "keys", "items", "values", "update", "to_dict"}


def gefundene_keys() -> dict[str, set[str]]:
    treffer: dict[str, set[str]] = {}
    for pfad in sorted([*WURZEL.glob("views/*.py"), *WURZEL.glob("core/*.py"),
                        *WURZEL.glob("analysis/*.py"), WURZEL / "app.py"]):
        if not pfad.exists():
            continue
        # Kommentarzeilen weg, bevor gesucht wird: ein Verweis auf diese Datei
        # („tools/check_session_state.py") sähe sonst wie der Schlüssel `py` aus — der
        # Prüfer meldete sich beim ersten Lauf über seinen eigenen Kommentar.
        text = "\n".join(z.split("#")[0] if z.lstrip().startswith("#") else z
                         for z in pfad.read_text(encoding="utf-8").splitlines())
        for m in list(MUSTER.finditer(text)) + list(MUSTER_ATTR.finditer(text)):
            k = m.group(1)
            if k in NICHT_KEYS:
                continue
            treffer.setdefault(k, set()).add(str(pfad.relative_to(WURZEL)))
    return treffer


def main() -> int:
    sys.path.insert(0, str(WURZEL))
    # Nur die Konstante lesen — ohne Streamlit-Import, der einen Server erwartet.
    quelle = (WURZEL / "core" / "shared.py").read_text(encoding="utf-8")
    block = re.search(r"ABGELEITETE_KEYS = \((.*?)\n\)", quelle, re.S)
    if not block:
        print("FEHLER: ABGELEITETE_KEYS nicht in core/shared.py gefunden")
        return 1
    abgeleitet = set(re.findall(r'"([A-Za-z0-9_]+)"', block.group(1)))

    bekannt = abgeleitet | EINSTELLUNGEN | SITZUNG
    gefunden = gefundene_keys()

    unbekannt = {k: v for k, v in gefunden.items() if k not in bekannt}
    verwaist = sorted(bekannt - set(gefunden))

    if unbekannt:
        print(f"{len(unbekannt)} nicht eingeordnete Session-State-Schlüssel:\n")
        for k in sorted(unbekannt):
            print(f"  {k:28s} {', '.join(sorted(unbekannt[k]))}")
        print("\nJeder Schlüssel braucht eine Entscheidung:")
        print("  * aus dem DATEIINHALT abgeleitet -> core/shared.py::ABGELEITETE_KEYS")
        print("    (sonst überlebt er den Dateiwechsel und der Report zeigt Werte der")
        print("     vorherigen Aufnahme unter dem Namen der aktuellen)")
        print("  * Einstellung oder Sitzungsebene  -> hier in EINSTELLUNGEN / SITZUNG")
        return 1

    print(f"Alle {len(gefunden)} Session-State-Schlüssel eingeordnet "
          f"({len(abgeleitet & set(gefunden))} abgeleitet, "
          f"{len(EINSTELLUNGEN & set(gefunden))} Einstellungen, "
          f"{len(SITZUNG & set(gefunden))} Sitzung).")
    if verwaist:
        # Kein Fehler: die Ratsche darf enger werden, nur nicht lockerer.
        print(f"Hinweis — gelistet, aber nirgends mehr benutzt: {', '.join(verwaist)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
