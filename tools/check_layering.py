"""Schichtenprüfer — verhindert, dass die Architektur langsam zurückrutscht.

Die Zielarchitektur lautet:

    views/  (Oberfläche)  →  core/  (Infrastruktur)  →  analysis/  (Fachlogik)

Pfeile nur nach rechts. `analysis/` darf nichts aus `views/` importieren und nichts über
Streamlit wissen — sonst lässt sich die Analyse nie ohne Oberfläche betreiben (CLI, Batch,
fremdes Notebook, Reproduktion durch Dritte).

**Warum eine Ratsche und kein Verbot.** Am 2026-08-12 gab es 10 Verstösse: die spektralen
Grundrechnungen lagen in `views/eeg_spectrum.py`, und die Analyseschicht holte sie von dort.
Sechs davon sind sofort behoben worden (Verschiebung nach `analysis/spectral.py`), die
übrigen hängen an Funktionen, die tatsächlich mit Streamlit verwoben sind — Caching,
Session-State — und deren Entflechtung echte Arbeit ist.

Ein Prüfer, der ab sofort null Verstösse fordert, wäre an dem Tag rot und bliebe es. Er würde
abgeschaltet, und dann schützt er gar nichts mehr. Stattdessen friert dieses Skript den
Ist-Stand ein: **die bekannten Verstösse sind namentlich erlaubt, neue nicht.** Wird einer
behoben, meldet der Prüfer das und verlangt, ihn aus der Liste zu streichen — die Liste kann
also nur kürzer werden.

Genau das adressiert die Gefahr, die das Architektur-Review benannt hat: nicht dass die
Struktur falsch wäre, sondern dass sie durch organisches Weiterentwickeln zurückfällt.

Aufruf:  python3 tools/check_layering.py
Exit-Code 1 bei Befund. Braucht nur die Standardbibliothek.
"""

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Was eine Schicht NICHT importieren darf.
VERBOTEN = {
    "analysis": ("views", "streamlit"),
    # `core` darf Streamlit nutzen (Session-State, Caching sind Infrastruktur), aber keine
    # UI-Seiten kennen — sonst zeigt die Infrastruktur auf ihre eigenen Benutzer.
    "core": ("views",),
}

#: Bekannte, geduldete Verstösse — Stand 2026-08-12 nach dem Herausziehen von
#: `analysis/spectral.py`. Format: "datei::importiertes_modul".
#:
#: Jeder Eintrag ist Schuld, die bewusst stehen bleibt, nicht ein Freibrief. Die Funktionen
#: dahinter sind mit Streamlit verwoben (`@st.cache_data`, Session-State) und brauchen eine
#: echte Entflechtung — siehe Phase 3/5 des Backlogs.
ERLAUBT = {
    "analysis/glory_report.py::views.eeg_spectrum",   # _compute_par (@st.cache_data)
    "analysis/glory_report.py::views.ecg_hrv",        # compute_rr   (@st.cache_data)
    "analysis/report_export.py::views.eeg_spectrum",  # _compute_par
    "analysis/report_export.py::views.report",        # _compute_bandpower, _compute_hrv
    "analysis/report_export.py::views.ecg_hrv",       # compute_rr
    "analysis/report_metadata.py::views.eeg_spectrum",  # _alpha_band (altersabhängig)
    "analysis/report_metadata.py::views.aperiodic",   # _age_expected_band
}

SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "build", "dist", "tests"}


def importe(pfad: Path):
    """Alle importierten Top-Level-Module einer Datei, samt Zeilennummer.

    Über den AST, nicht per Textsuche: die meisten Importe hier stehen INNERHALB von
    Funktionen (Streamlits Lazy-Loading-Muster), eine Suche auf Zeilenanfang fände sie nicht.
    """
    try:
        baum = ast.parse(pfad.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.Import):
            for a in knoten.names:
                yield knoten.lineno, a.name
        elif isinstance(knoten, ast.ImportFrom) and knoten.module and knoten.level == 0:
            yield knoten.lineno, knoten.module


def main():
    neu, gesehen = [], set()

    for schicht, tabu in VERBOTEN.items():
        for pfad in sorted((ROOT / schicht).rglob("*.py")):
            if any(teil in SKIP_DIRS for teil in pfad.parts):
                continue
            rel = pfad.relative_to(ROOT).as_posix()
            for zeile, modul in importe(pfad):
                wurzel = modul.split(".")[0]
                if wurzel not in tabu:
                    continue
                schluessel = f"{rel}::{modul}"
                gesehen.add(schluessel)
                if schluessel not in ERLAUBT:
                    neu.append(f"{rel}:{zeile} importiert '{modul}' "
                               f"— {schicht}/ darf das nicht")

    # Behobene Verstösse: stehen noch auf der Liste, kommen aber nicht mehr vor.
    behoben = sorted(ERLAUBT - gesehen)

    print(f"Geduldete Altlasten: {len(ERLAUBT)}  |  davon noch vorhanden: {len(gesehen & ERLAUBT)}")
    print()
    for eintrag in behoben:
        print(f"ERLEDIGT: '{eintrag}' gibt es nicht mehr — bitte aus ERLAUBT streichen, "
              f"damit die Liste kürzer wird und nicht nur älter.")
    for eintrag in neu:
        print("FEHLER: " + eintrag)

    if neu or behoben:
        print(f"\n{len(neu)} neue(r) Verstoss/Verstösse, {len(behoben)} veraltete(r) Eintrag/Einträge.")
        return 1
    print("Keine neuen Schichtverletzungen.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
