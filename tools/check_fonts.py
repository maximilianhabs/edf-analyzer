"""Prüft, dass jede im CSS angeforderte Schrift auch tatsächlich verfügbar ist.

Hintergrund (realer Fehler, 2026-08-11): Beim Wechsel der Icon-Schrift von „Material Symbols
Outlined" auf „Material Symbols Rounded" wurde eine Stelle übersehen — sie schreibt den
Schriftnamen anders als die CSS-Klasse (Leerzeichen statt Bindestriche) und entging deshalb
dem Suchen-und-Ersetzen. Das erzeugte KEINEN Fehler: der Browser fand die Schrift nicht, fiel
auf die Standardschrift zurück und stellte den Ligaturnamen als Klartext dar — im Kopf jeder
Kanalzeile stand „neurology" statt des Gehirn-Symbols. So etwas fällt keinem Test auf und
keinem Log; nur dem Auge, und auch dem erst beim genauen Hinsehen.

Geprüft wird gegen drei zulässige Quellen:
  1. selbst gehostet — es gibt ein @font-face für die Familie im Projektcode
  2. von Streamlit mitgeliefert  (siehe STREAMLIT_BUNDLED)
  3. generische/System-Schlüsselwörter (sans-serif, inherit, -apple-system …)

Alles andere ist entweder ein Tippfehler oder ein stiller CDN-Zugriff — beides soll auffallen.

Aufruf:  python3 tools/check_fonts.py      Exit-Code 1 bei Befund. Nur Standardbibliothek.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", "tools", ".venv", "venv", "build", "dist", "static"}

# Von Streamlit selbst lokal ausgeliefert (verifiziert 2026-08-11 über die geladenen
# FontFaces im Browser: /static/media/SourceSansVF…, MaterialSymbols-Rounded…).
STREAMLIT_BUNDLED = {
    "material symbols rounded",
    "source sans", "source sans pro", "source code pro", "source serif",
}

# Keine echten Schriften, sondern Schlüsselwörter/System-Stacks
GENERIC = {
    "inherit", "initial", "unset", "revert", "sans-serif", "serif", "monospace",
    "cursive", "fantasy", "system-ui", "ui-sans-serif", "ui-monospace",
    "-apple-system", "blinkmacsystemfont", "segoe ui", "roboto", "helvetica",
    "helvetica neue", "arial", "sf pro text", "sf pro display", "noto sans",
}

FONT_FAMILY_RE = re.compile(r"font-family\s*:\s*([^;{}\n]+)", re.I)
# Icon-Schriftname als Literal — GENAU so entstand der Fehler von 2026-08-11:
# `_icon_font = "'Material Symbols Outlined'"`, weiter unten `font-family:{_icon_font}`.
# Über `font-family:` allein nicht auffindbar, dort steht nur der Platzhalter.
#
# Bewusst eng gefasst auf Icon-Schriftfamilien statt „irgendeine Variable mit 'font' im Namen":
# Letzteres wurde ausprobiert und lieferte 94 Fehlalarme (`fontweight="bold"`,
# `font=dict(color="white")` aus matplotlib/plotly). Ein Prüfer, den man wegen Rauschen
# ignoriert, ist schlechter als keiner.
ICON_FONT_LITERAL_RE = re.compile(r"""['"]((?:Material\s+(?:Symbols|Icons))[^'"]*)['"]""", re.I)
FONT_FACE_RE = re.compile(r"@font-face\s*\{{?[^}]*?font-family\s*:\s*([^;}\n]+)", re.I | re.S)
# Verweise auf ein Schriften-CDN — sollen gar nicht mehr vorkommen (siehe NOTICE/CHANGELOG)
CDN_RE = re.compile(r"fonts\.(googleapis|gstatic)\.com", re.I)


def clean(name: str) -> str:
    """'Material Symbols Rounded' / {ICON_FONT_CSS} → normalisierter Vergleichsname."""
    return name.strip().strip("'\"").strip().lower()


def strip_comments(text: str) -> str:
    """Entfernt CSS-Blockkommentare und Python-Zeilenkommentare, BEHÄLT aber die Zeilenanzahl
    (Inhalt wird durch Leerzeichen ersetzt) — sonst stimmen die gemeldeten Zeilennummern nicht.

    Nötig, weil die Erklärtexte in diesem Projekt selbst über CDNs und Schriftnamen sprechen.
    Eine Prüfung „beginnt die Zeile mit einem Kommentarzeichen" reicht dafür nicht: bei
    mehrzeiligen /* */-Blöcken sieht die zweite Zeile aus wie echtes CSS."""
    def blank(m):
        return re.sub(r"[^\n]", " ", m.group(0))
    text = re.sub(r"/\*.*?\*/", blank, text, flags=re.S)      # CSS-Blockkommentare
    text = re.sub(r"(?m)^\s*#.*$", blank, text)               # Python-Zeilenkommentare
    return text


def python_files():
    for p in sorted(ROOT.rglob("*.py")):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        yield p


def main():
    # 1. Selbst gehostete Familien einsammeln (@font-face irgendwo im Code)
    self_hosted = set()
    for p in python_files():
        for m in FONT_FACE_RE.finditer(strip_comments(p.read_text(encoding="utf-8"))):
            self_hosted.add(clean(m.group(1)))

    problems = []
    for p in python_files():
        text = strip_comments(p.read_text(encoding="utf-8"))

        # 2. Kein CDN mehr (Kommentare sind oben entfernt, Treffer sind also echt)
        for i, line in enumerate(text.splitlines(), 1):
            if CDN_RE.search(line):
                problems.append(f"[CDN-Verweis] {p.relative_to(ROOT)}:{i} — "
                                f"Schrift von extern laden ist ausgeschlossen: {line.strip()[:80]}")

        # 3. Jede angeforderte Familie muss auflösbar sein
        for m in FONT_FAMILY_RE.finditer(text):
            raw = m.group(1)
            line_no = text[:m.start()].count("\n") + 1
            for part in raw.split(","):
                name = clean(part)
                if not name:
                    continue
                # Aus Variablen/Platzhaltern zusammengesetzt → zur Laufzeit aufgelöst,
                # statisch nicht entscheidbar (z. B. {ICON_FONT_CSS}, var(--…)).
                if name.startswith(("{", "var(", "$")) or "{" in name:
                    continue
                if name in GENERIC or name in STREAMLIT_BUNDLED or name in self_hosted:
                    continue
                problems.append(
                    f"[Schrift nicht verfügbar] {p.relative_to(ROOT)}:{line_no} — "
                    f"'{part.strip()}' hat weder ein @font-face im Projekt noch ist sie von "
                    f"Streamlit mitgeliefert. Der Browser fällt still zurück (bei Icon-Fonts "
                    f"erscheint dann der Ligaturname als Text).")

        # 4. Icon-Schriftnamen als Literal — auch wenn sie über eine Variable ins CSS
        # gelangen und Prüfung 3 dort nur den Platzhalter sieht.
        for m in ICON_FONT_LITERAL_RE.finditer(text):
            name = clean(m.group(1))
            if name in STREAMLIT_BUNDLED or name in self_hosted:
                continue
            line_no = text[:m.start()].count("\n") + 1
            problems.append(
                f"[Icon-Schrift nicht verfügbar] {p.relative_to(ROOT)}:{line_no} — "
                f"'{m.group(1)}' ist weder selbst gehostet noch von Streamlit mitgeliefert. "
                f"Der Browser fällt still auf die Standardschrift zurück und zeigt dann den "
                f"Ligaturnamen als Text (z. B. 'neurology' statt des Symbols). Schriftnamen "
                f"gehören nach core/design_tokens.py (ICON_FONT_CSS).")

    print("Selbst gehostete Familien:", ", ".join(sorted(self_hosted)) or "—")
    print("Von Streamlit mitgeliefert:", ", ".join(sorted(STREAMLIT_BUNDLED)))
    print()
    for pr in problems:
        print("FEHLER: " + pr)
    if problems:
        print(f"\n{len(problems)} Problem(e) gefunden.")
        return 1
    print("Alle angeforderten Schriften sind auflösbar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
