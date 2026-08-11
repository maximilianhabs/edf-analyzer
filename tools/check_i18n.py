"""Vollständigkeits-Check für core/i18n.py.

Prüft dreierlei und meldet jeden Fund mit Datei/Zeile:
  1. Jeder im Code per tr("ns.key") benutzte Schlüssel existiert in ALLEN Sprachen.
  2. Keine Sprache hat Schlüssel, die eine andere nicht hat (Struktur-Gleichheit).
  3. Beide Sprachen nutzen dieselben {platzhalter} je Schlüssel.
  4. Kein definierter Schlüssel ist ungenutzt (Karteileichen nach Refactorings).

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

# tr(f"ns.{variable}") — dynamisch zusammengesetzter Schlüssel. Der konkrete Name steht erst
# zur Laufzeit fest, deshalb kann Prüfung 4 (ungenutzt) für diesen Namensraum nur pauschal
# ausgesetzt werden; die Prüfungen 1–3 greifen unverändert.
# Erfasst auch Schlüssel mit festem Präfix vor der Variablen, z. B. tr(f"ns.window_{v}").
T_CALL_DYNAMIC = re.compile(r"""\btr\(\s*f["']([a-zA-Z0-9_]+)\.[a-zA-Z0-9_]*\{""")


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
    dynamic_ns = set()
    for path in sorted(ROOT.rglob("*.py")):
        if any(part in {".git", "tools", "tests", ".venv", "venv"} for part in path.parts):
            continue
        if path == I18N_FILE:
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for key in T_CALL.findall(line):
                used.setdefault(key, []).append(f"{path.relative_to(ROOT)}:{lineno}")
            dynamic_ns.update(T_CALL_DYNAMIC.findall(line))
    return used, dynamic_ns


def main():
    strings = load_strings()
    langs = sorted(strings)
    per_lang = {lang: flat_keys(strings[lang]) for lang in langs}
    used, dynamic_ns = collect_used_keys()
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

    # 3. Platzhalter-Gleichheit zwischen den Sprachen. tr() ruft .format(**kwargs) auf — hätte
    # eine Sprache einen Platzhalter, den die andere nicht hat, käme der Fehler erst beim
    # Umschalten zur Laufzeit (KeyError bzw. stehengebliebenes "{name}" im Text).
    def placeholders(text):
        return set(re.findall(r"\{([a-zA-Z_][a-zA-Z0-9_]*)", text))

    def value_of(lang, key):
        ns, k = key.split(".", 1)
        return strings[lang][ns][k]

    for key in sorted(all_defined):
        per = {lang: placeholders(value_of(lang, key))
               for lang in langs if key in per_lang[lang]}
        if len(set(map(frozenset, per.values()))) > 1:
            detail = " | ".join(f"{lang}: {sorted(ph) or '—'}" for lang, ph in per.items())
            problems.append(f"[Platzhalter ungleich] '{key}' → {detail}")

    # 4. Definiert, aber ungenutzt (nur Hinweis, kein Fehler). Namensräume mit dynamisch
    # zusammengesetzten Schlüsseln sind ausgenommen — dort liesse sich "ungenutzt" statisch
    # nicht entscheiden, und eine Falschmeldung pro Lauf würde den Check wertlos machen.
    unused = sorted(k for k in all_defined - set(used)
                    if k.split(".", 1)[0] not in dynamic_ns)

    for p in problems:
        print("FEHLER: " + p)
    if dynamic_ns:
        print("Namensräume mit dynamischen Schlüsseln (von Prüfung 4 ausgenommen): "
              + ", ".join(sorted(dynamic_ns)))
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
