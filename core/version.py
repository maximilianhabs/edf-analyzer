"""Herkunft eines Analyseergebnisses — Version, Commit, Umgebung, Fingerabdruck.

Das Problem, das diese Datei löst: Ein exportierter Report zeigte bisher Werte, aber nichts
darüber, WOMIT sie entstanden sind. Es gab überhaupt keine Versionsnummer im Code — nur
`CITATION.cff` nannte eine. Wer zwei Reports derselben Aufnahme aus verschiedenen Wochen
nebeneinander legte, konnte nicht entscheiden, ob ein Unterschied aus der Aufnahme oder aus
einer Codeänderung stammt. Für ein Werkzeug, dessen Anspruch Nachvollziehbarkeit ist, ist
das die empfindlichste Lücke.

Eine Quelle, kein zweiter Ort
-----------------------------
Die Versionsnummer steht **ausschließlich** in `CITATION.cff` und wird hier ausgelesen. Eine
zweite Konstante im Code wäre ein zweiter Ort zum Vergessen — genau so entstehen Doku und
Code, die auseinanderlaufen.

Der Commit im Container
-----------------------
`.dockerignore` schließt `.git/` aus, im Image gibt es also kein Repository. Der Commit muss
deshalb beim Bauen hineingereicht werden (`--build-arg EDF_BUILD_COMMIT=$(git rev-parse
--short HEAD)`); fehlt er, steht das ausdrücklich im Report statt einer erfundenen Angabe.
Lokal wird ersatzweise `git` befragt.
"""

from __future__ import annotations

import hashlib
import os
import platform
import re
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

#: Pakete, deren Version ein Ergebnis verändern kann. Bewusst kurz gehalten: eine
#: vollständige `pip freeze`-Liste liest niemand, und die relevanten Rechenwege hängen an
#: diesen hier.
_RELEVANT_PACKAGES = ("numpy", "scipy", "pandas", "mne", "pyedflib", "fooof", "streamlit",
                      "py-ecg-detectors")

UNKNOWN = "unbekannt"


@lru_cache(maxsize=1)
def version() -> str:
    """Versionsnummer aus `CITATION.cff` — der einzigen Stelle, an der sie gepflegt wird."""
    cff = _ROOT / "CITATION.cff"
    try:
        m = re.search(r"^version:\s*['\"]?([^'\"\s]+)", cff.read_text(encoding="utf-8"),
                      re.MULTILINE)
        return m.group(1) if m else UNKNOWN
    except OSError:
        return UNKNOWN


@lru_cache(maxsize=1)
def commit() -> str:
    """Kurzer Git-Commit. Beim Bauen über `EDF_BUILD_COMMIT` hereingereicht, lokal aus dem
    Repository gelesen. Ein angehängtes `+dirty` heißt: es lagen uncommittete Änderungen vor —
    das Ergebnis ist dann **nicht** allein über den Commit reproduzierbar, und genau das soll
    man sehen."""
    env = os.environ.get("EDF_BUILD_COMMIT", "").strip()
    if env:
        return env
    try:
        sha = subprocess.run(["git", "-C", str(_ROOT), "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, timeout=3)
        if sha.returncode != 0:
            return UNKNOWN
        out = sha.stdout.strip()
        dirty = subprocess.run(["git", "-C", str(_ROOT), "status", "--porcelain"],
                               capture_output=True, text=True, timeout=5)
        if dirty.returncode == 0 and dirty.stdout.strip():
            out += "+dirty"
        return out
    except (OSError, subprocess.SubprocessError):
        return UNKNOWN


@lru_cache(maxsize=1)
def environment() -> dict:
    """Python- und Paketversionen der LAUFENDEN Umgebung — aus `importlib.metadata`, nicht
    aus `requirements.txt`. Was installiert ist, entscheidet über das Ergebnis; was
    deklariert ist, nur über das, was installiert werden sollte."""
    import importlib.metadata as md
    pkgs = {}
    for name in _RELEVANT_PACKAGES:
        try:
            pkgs[name] = md.version(name)
        except md.PackageNotFoundError:
            pkgs[name] = "nicht installiert"
    return {
        "python": platform.python_version(),
        "platform": f"{platform.system()} {platform.machine()}",
        "packages": pkgs,
    }


def file_hash(path: str, chunk: int = 1 << 20) -> str:
    """SHA-256 der EDF-Datei, blockweise gelesen (die Dateien werden bis 200 MB groß).

    Der Hash identifiziert die Aufnahme, ohne irgendetwas über sie preiszugeben — er kann in
    einem Report stehen, auch wenn der Dateiname es nicht dürfte."""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            for block in iter(lambda: fh.read(chunk), b""):
                h.update(block)
    except OSError:
        return UNKNOWN
    return h.hexdigest()


def fingerprint(edf_path: str, params: dict | None = None) -> str:
    """Kurzer Fingerabdruck aus Datei, Version, Commit und Analyseparametern.

    Zweck: zwei Reports auf einen Blick vergleichbar machen. Gleicher Fingerabdruck heißt
    gleiche Datei, gleicher Code, gleiche Einstellungen — ein Unterschied in den Werten wäre
    dann erklärungsbedürftig. Unterschiedlicher Fingerabdruck sagt, dass ein Vergleich von
    vornherein nicht zulässig ist.

    Bewusst KEIN Ersatz für die Einzelangaben: 12 Hexzeichen sagen niemandem, WAS sich
    geändert hat. Sie stehen deshalb neben Version, Commit und Parametern, nicht statt ihnen.
    """
    parts = [file_hash(edf_path), version(), commit()]
    for key in sorted((params or {})):
        parts.append(f"{key}={(params or {})[key]}")
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:12]


def provenance(edf_path: str | None = None, params: dict | None = None) -> dict:
    """Alle Herkunftsangaben in einem Rutsch — die Form, die die Report-Bauer erwarten."""
    env = environment()
    out = {
        "version": version(),
        "commit": commit(),
        "python": env["python"],
        "platform": env["platform"],
        "packages": env["packages"],
        "params": dict(params or {}),
    }
    if edf_path:
        out["file_sha256"] = file_hash(edf_path)
        out["fingerprint"] = fingerprint(edf_path, params)
    return out


def provenance_lines(prov: dict, lang: str = "de") -> list:
    """Herkunft als flache (Bezeichnung, Wert)-Liste für Tabellen in Excel und PDF."""
    de = lang != "en"
    pkgs = ", ".join(f"{k} {v}" for k, v in prov["packages"].items()
                     if v != "nicht installiert")
    rows = [
        ("Version" if de else "Version", prov["version"]),
        ("Git-Commit" if de else "Git commit", prov["commit"]),
        ("Python", f"{prov['python']} ({prov['platform']})"),
        ("Pakete" if de else "Packages", pkgs),
    ]
    if prov.get("file_sha256"):
        rows.append(("SHA-256 der Datei" if de else "File SHA-256",
                     prov["file_sha256"][:32] + "…"))
        rows.append(("Analyse-Fingerabdruck" if de else "Analysis fingerprint",
                     prov["fingerprint"]))
    for key, val in prov.get("params", {}).items():
        rows.append((f"Parameter: {key}", str(val)))
    return rows


def short_line(prov: dict, lang: str = "de") -> str:
    """Einzeiler für die Fußzeile einer Grafikseite, wo kein Platz für eine Tabelle ist."""
    if lang == "en":
        return (f"EDF-Analyzer {prov['version']} · commit {prov['commit']} · "
                f"Python {prov['python']} · fingerprint {prov.get('fingerprint', '—')}")
    return (f"EDF-Analyzer {prov['version']} · Commit {prov['commit']} · "
            f"Python {prov['python']} · Fingerabdruck {prov.get('fingerprint', '—')}")


if __name__ == "__main__":   # kleine Selbstauskunft: `python3 core/version.py`
    p = provenance(sys.argv[1] if len(sys.argv) > 1 else None)
    for k, v in provenance_lines(p):
        print(f"{k:24s} {v}")
