"""Vollständigkeits-Check für core/i18n.py.

Prüft dreierlei und meldet jeden Fund mit Datei/Zeile:
  1. Jeder im Code per tr("ns.key") benutzte Schlüssel existiert in ALLEN Sprachen.
  2. Keine Sprache hat Schlüssel, die eine andere nicht hat (Struktur-Gleichheit).
  3. Kein definierter Schlüssel ist ungenutzt (Karteileichen nach Refactorings).

Absichtlich ohne Abhängigkeiten (nur ast/re/pathlib), damit es auch in einer CI ohne
installierte App-Umgebung läuft:  python3 tools/check_i18n.py
"""

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
I18N_FILE = ROOT / "core" / "i18n.py"

# tr("ns.key") / tr('ns.key') — auch mit führendem Modulpräfix (i18n.tr(...)) und Argumenten.
T_CALL = re.compile(r"""\btr\(\s*["']([a-zA-Z0-9_]+\.[a-zA-Z0-9_]+)["']""")


def load_strings():
    """Liest STRINGS aus core/i18n.py per AST — kein Import, damit kein Streamlit nötig ist."""
    tree = ast.parse(I18N_FILE.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "STRINGS":
                    return ast.literal_eval(node.value)
    raise SystemExit("FEHLER: STRINGS nicht in core/i18n.py gefunden")


def flat_keys(lang_dict):
    return {f"{ns}.{k}" for ns, entries in lang_dict.items() for k in entries}


def collect_used_keys():
    used = {}
    for path in sorted(ROOT.rglob("*.py")):
        if any(part in {".git", "tools", "tests", ".venv", "venv"} for part in path.parts):
            continue
        if path == I18N_FILE:
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for key in T_CALL.findall(line):
                used.setdefault(key, []).append(f"{path.relative_to(ROOT)}:{lineno}")
    return used


def main():
    strings = load_strings()
    langs = sorted(strings)
    per_lang = {lang: flat_keys(strings[lang]) for lang in langs}
    used = collect_used_keys()
    problems = []

    # 1. Struktur-Gleichheit zwischen den Sprachen
    all_defined = set().union(*per_lang.values())
    for lang in langs:
        for missing in sorted(all_defined - per_lang[lang]):
            problems.append(f"[fehlende Übersetzung] '{missing}' fehlt in Sprache '{lang}'")

    # 2. Benutzte, aber nirgends definierte Schlüssel (führt zur Laufzeit zum KeyError)
    for key in sorted(used):
        for lang in langs:
            if key not in per_lang[lang]:
                where = ", ".join(used[key][:3])
                problems.append(f"[undefiniert] tr(\"{key}\") in {where} fehlt in Sprache '{lang}'")

    # 3. Definiert, aber ungenutzt (nur Hinweis, kein Fehler)
    unused = sorted(all_defined - set(used))

    for p in problems:
        print("FEHLER: " + p)
    if unused:
        print(f"\nHinweis: {len(unused)} definierte Schlüssel werden nirgends per tr() benutzt:")
        for key in unused:
            print(f"  - {key}")

    print(f"\nSprachen: {', '.join(langs)}  |  Schlüssel je Sprache: "
          + ", ".join(f"{lang}={len(per_lang[lang])}" for lang in langs)
          + f"  |  im Code benutzt: {len(used)}")

    if problems:
        print(f"\n{len(problems)} Problem(e) gefunden.")
        return 1
    print("\nAlles konsistent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
