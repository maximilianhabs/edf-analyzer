"""Abhängigkeits- und Lizenz-Check.

Fängt die Fehler ab, die beim Public-Release-Audit 2026-08-11 real aufgetreten sind:

  1. Ein Paket steht in requirements*.txt, wird aber nirgends importiert (`neurokit2` stand
     dort über die gesamte Projekt-Historie ungenutzt).
  2. Ein Modul wird importiert, ist aber nirgends deklariert — fällt sonst erst in einer
     frischen Installation auf, nicht beim Entwickeln.
  3. Eine Copyleft-Abhängigkeit rutscht in die STANDARD-Requirements (`py-ecg-detectors` ist
     GPL-3.0, das Projekt Apache-2.0). Copyleft ist hier nicht verboten — aber es gehört
     bewusst nach requirements-validated.txt, nicht unbemerkt in die Standardinstallation.
  4. Die NOTICE nennt ein Paket nicht, das in den Requirements steht (dort fehlte
     `matplotlib`), oder nennt eines, das es nicht mehr gibt.

Lizenzangaben kommen IMMER aus den Metadaten der installierten Version, nie aus einer
gepflegten Liste — genau dieses „aus dem Gedächtnis" hatte matplotlib fälschlich als BSD
geführt (es ist eine PSF-artige Eigenlizenz).

Aufruf:  python3 tools/check_licenses.py
Exit-Code 1 bei Befund. Braucht nur die Standardbibliothek; Pakete, die lokal nicht
installiert sind, werden als solche gemeldet statt geraten.
"""

import ast
import importlib.metadata as md
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STD_REQ = ROOT / "requirements.txt"
OPT_REQ = ROOT / "requirements-validated.txt"
DEV_REQ = ROOT / "requirements-dev.txt"   # nur Entwicklung/CI, nicht für den Betrieb
NOTICE = ROOT / "NOTICE"

# Import-Name ≠ PyPI-Name
IMPORT_TO_PYPI = {
    "ecgdetectors": "py-ecg-detectors",
    "extra_streamlit_components": "extra-streamlit-components",
}

# Nur für die NOTICE-Gegenprüfung: dort stehen Anzeigenamen, nicht PyPI-Namen.
PYPI_TO_NOTICE = {
    "py-ecg-detectors": "py-ecg-detectors",
    "extra-streamlit-components": "extra-streamlit-components",
    "mne": "MNE-Python",
    "fooof": "FOOOF",
    "pyedflib": "pyedflib",
    "reportlab": "ReportLab",
    "openpyxl": "openpyxl",
    "streamlit": "Streamlit",
    "plotly": "Plotly",
    "numpy": "NumPy",
    "scipy": "SciPy",
    "pandas": "pandas",
    "matplotlib": "matplotlib",
}

COPYLEFT = ("GPL", "AGPL", "LGPL", "MPL", "EUPL", "CDDL", "OSL", "CECILL")

SKIP_DIRS = {".git", "tools", ".venv", "venv", "static", "build", "dist"}


def read_requirements(path):
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        out[re.split(r"[<>=!\[;]", line)[0].strip()] = line
    return out


def stdlib_names():
    """Namen der Standardbibliothek — auch auf Python 3.9.

    `sys.stdlib_module_names` gibt es erst ab 3.10. Das Projekt läuft aber auf 3.9 (Dockerfile,
    wegen MNE), und genau dort brach dieses Skript in der ersten CI ab. Fallback leitet die
    Namen aus dem stdlib-Verzeichnis ab — ohne die Module zu importieren, also ohne
    Seiteneffekte."""
    names = set(getattr(sys, "stdlib_module_names", ()))
    if names:
        return names
    import sysconfig
    names = set(sys.builtin_module_names)
    # `lib-dynload` MUSS mit: dort liegen die C-Erweiterungsmodule (math, fcntl, select …) als
    # .so/.pyd. Eine erste Fassung sah nur .py-Dateien und Paketordner an und meldete deshalb
    # `math` und `fcntl` als undeklarierte Fremdpakete — aufgefallen erst in der CI, weil meine
    # eigene Stichprobe zufällig nur reine Python-Module enthielt.
    stdlib_dir = Path(sysconfig.get_paths()["stdlib"])
    for d in (stdlib_dir, stdlib_dir / "lib-dynload"):
        if not d.is_dir():
            continue
        for entry in d.iterdir():
            if entry.suffix == ".py":
                names.add(entry.stem)
            elif entry.suffix in (".so", ".pyd", ".dll"):
                names.add(entry.name.split(".")[0])   # math.cpython-39-….so → math
            elif entry.is_dir() and (entry / "__init__.py").exists():
                names.add(entry.name)
    return names


def imported_modules():
    """Top-Level-Module aus dem AST — robuster als grep (erfasst auch Imports in Funktionen,
    davon gibt es hier viele wegen Streamlits Lazy-Loading-Muster)."""
    mods = set()
    for p in sorted(ROOT.rglob("*.py")):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    mods.add(a.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                mods.add(node.module.split(".")[0])
    local = {p.name for p in ROOT.iterdir() if p.is_dir() and (p / "__init__.py").exists()}
    local |= {"tests", "app", "analysis", "core", "views"}
    std = stdlib_names()
    return {IMPORT_TO_PYPI.get(m, m) for m in mods
            if m not in std and m not in local}


def license_of(pkg):
    """(Lizenztext, Quelle) aus den Metadaten. None, wenn nicht installiert."""
    try:
        m = md.metadata(pkg)
    except md.PackageNotFoundError:
        return None, "nicht installiert"
    lic = (m.get("License") or "").strip()
    classifiers = [c.split("::")[-1].strip()
                   for c in (m.get_all("Classifier") or []) if c.startswith("License")]
    if lic and lic.upper() != "UNKNOWN" and len(lic) < 60:
        return lic, "Feld License"
    if classifiers:
        return classifiers[0], "Classifier"
    if lic:
        return "(Lizenz-Volltext im Metadatenfeld)", "Feld License"
    return None, "Metadaten ohne Lizenzangabe"


def is_copyleft(text):
    return bool(text) and any(k in text.upper() for k in COPYLEFT)


def main():
    std, opt = read_requirements(STD_REQ), read_requirements(OPT_REQ)
    dev = read_requirements(DEV_REQ)
    declared = set(std) | set(opt) | set(dev)
    used = imported_modules()
    problems, notes = [], []

    # 1 + 2 — Deklaration und tatsächliche Nutzung
    for pkg in sorted(used - declared):
        problems.append(f"[nicht deklariert] '{pkg}' wird importiert, steht aber in keiner "
                        f"requirements-Datei")
    for pkg in sorted(declared - used):
        problems.append(f"[ungenutzt] '{pkg}' ist deklariert, wird aber nirgends importiert")

    # 3 — Copyleft gehört nicht in die Standard-Requirements
    print(f"{'Paket':30s} {'Lizenz':34s} Quelle")
    print("-" * 78)
    for pkg in sorted(declared):
        lic, src = license_of(pkg)
        # Maßgeblich ist, ob es in den STANDARD-Requirements steht: steht ein Paket in beiden
        # Dateien, zieht `pip install -r requirements.txt` es trotzdem mit. Die frühere
        # Prüfung „ist es in der optionalen Datei?" ließ genau diesen Fall durchrutschen
        # (beim Selbsttest des Prüfers aufgefallen).
        where = "standard" if pkg in std else ("dev" if pkg in dev else "optional")
        print(f"  {pkg:28s} {str(lic or '—'):34s} {src}")
        if lic is None and src == "nicht installiert":
            notes.append(f"'{pkg}' lokal nicht installiert — Lizenz nicht prüfbar")
        elif lic is None:
            notes.append(f"'{pkg}' liefert keine Lizenzangabe in den Metadaten")
        if is_copyleft(lic) and where == "standard":
            problems.append(f"[Copyleft in Standard-Requirements] '{pkg}' ({lic}) gehört nach "
                            f"{OPT_REQ.name}, sonst zieht jede Standardinstallation Copyleft mit")

    # 4 — NOTICE erwähnt jedes deklarierte Paket
    if NOTICE.exists():
        text = NOTICE.read_text(encoding="utf-8")
        for pkg in sorted(declared - set(dev)):   # Dev-Werkzeuge werden nicht ausgeliefert
            needle = PYPI_TO_NOTICE.get(pkg, pkg)
            if needle.lower() not in text.lower():
                problems.append(f"[NOTICE unvollständig] '{pkg}' ist deklariert, kommt in "
                                f"NOTICE aber nicht vor")
    else:
        problems.append("[NOTICE fehlt] Datei NOTICE existiert nicht")

    print()
    for n in notes:
        print("Hinweis: " + n)
    for p in problems:
        print("FEHLER: " + p)
    print(f"\nDeklariert: {len(declared)} ({len(std)} standard, {len(opt)} optional, "
          f"{len(dev)} dev)  |  importiert: {len(used)}")
    if problems:
        print(f"\n{len(problems)} Problem(e) gefunden.")
        return 1
    print("\nAlles konsistent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
