"""Konsistenz-Check für die Methoden-Registry.

Der Anlass: Über 15 Verfahren stand jahrelang „✅ validiert", während die Definition im
selben Modul „publizierter Standard-Algorithmus" lautete — literaturbasiert. Niemand hat den
Widerspruch bemerkt, weil nichts ihn prüfen konnte. Genau das holt dieses Skript nach.

Geprüft wird:

  1. Jede Methode oberhalb von `literature-based` hat einen vollständigen `Evidence`-Beleg
     (Datensatz, geprüfte Größe, Sollwert, Toleranz, Test) — und die genannte Testdatei
     existiert tatsächlich. Ein Beleg, der auf nichts zeigt, ist kein Beleg.
  2. Die Zählungen in BEIDEN READMEs stimmen mit der Registry überein. Erweitert jemand die
     Registry und vergisst die Doku, ist die Doku falsch — das fällt sonst erst einem Leser
     auf, und der prüft nicht nach, sondern glaubt.
  3. Kein Anzeigetext behauptet noch das alte, irreführende „validiert" für die unterste
     Stufe.

Aufruf:  python3 tools/check_methods.py
Exit-Code 1 bei Befund. Braucht nur die Standardbibliothek.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from analysis.methods import (  # noqa: E402
    METHODS, LITERATURE, IMPLEMENTATION, CLINICAL, FULL, SIMPLIFIED, PROXY,
    count_by_level, count_by_fidelity)

# README-Zeile → (Zählfunktion, Schlüssel). Die Muster treffen die deutsche UND die englische
# Fassung, damit beide Dateien mit derselben Regel geprüft werden.
ROWS = [
    (r"literaturbasiert|literature-based", count_by_level, LITERATURE),
    (r"implementierungsvalidiert|implementation-validated", count_by_level, IMPLEMENTATION),
    (r"klinisch validiert|clinically validated", count_by_level, CLINICAL),
    (r"^\|\s*(vollständig|full)\s*\|", count_by_fidelity, FULL),
    (r"vereinfacht|simplified", count_by_fidelity, SIMPLIFIED),
    (r"Proxy|proxy", count_by_fidelity, PROXY),
]


def readme_counts(path):
    """Zahlen aus den Tabellenzeilen `| Etikett | 12 | Bedeutung |` ziehen."""
    found = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 2:
            continue
        m = re.fullmatch(r"\d+", cells[1])
        if not m:
            continue
        for pattern, fn, key in ROWS:
            if re.search(pattern, line):
                found[(fn.__name__, key)] = (int(cells[1]), line.strip())
                break
    return found


def main():
    problems = []

    # 1 — Belege sind vollständig und zeigen auf existierende Tests
    for m in METHODS:
        if m.level == LITERATURE:
            continue
        ev = m.evidence            # dass er da ist, erzwingt bereits Method.__post_init__
        for fname in ("dataset", "checked", "expected", "tolerance", "test"):
            if not getattr(ev, fname, "").strip():
                problems.append(f"[Beleg unvollständig] '{m.parameter}': Feld '{fname}' leer")
        test_file = ev.test.split("::")[0]
        if test_file and not (ROOT / test_file).exists():
            problems.append(f"[Beleg zeigt ins Leere] '{m.parameter}': Test '{test_file}' "
                            f"existiert nicht")
        ds = ev.dataset.split()[0] if ev.dataset else ""
        if ds.startswith("tests/") and not (ROOT / ds).exists():
            problems.append(f"[Beleg zeigt ins Leere] '{m.parameter}': Datensatz '{ds}' "
                            f"existiert nicht")

    # 2 — READMEs gegen die Registry
    lvl, fid = count_by_level(), count_by_fidelity()
    actual = {("count_by_level", k): v for k, v in lvl.items()}
    actual.update({("count_by_fidelity", k): v for k, v in fid.items()})

    for readme in ("README.md", "README.de.md"):
        path = ROOT / readme
        if not path.exists():
            problems.append(f"[README fehlt] {readme}")
            continue
        text = path.read_text(encoding="utf-8")
        found = readme_counts(path)
        for key, want in actual.items():
            if key not in found:
                problems.append(f"[{readme}] keine Tabellenzeile für {key[1]} gefunden")
            elif found[key][0] != want:
                problems.append(f"[{readme}] {key[1]}: Doku sagt {found[key][0]}, Registry "
                                f"sagt {want} — Zeile: {found[key][1]}")
        total = re.search(r"\*\*(?:alle |all )(\d+)", text)
        if total and int(total.group(1)) != len(METHODS):
            problems.append(f"[{readme}] Gesamtzahl {total.group(1)}, Registry hat "
                            f"{len(METHODS)}")

    # 3 — das alte, irreführende Etikett darf nicht zurückkehren
    src = (ROOT / "analysis" / "methods.py").read_text(encoding="utf-8")
    for bad in ('"✅ validiert"', '"✅ validated"'):
        if bad in src:
            problems.append(f"[Etikett] {bad} steht wieder in methods.py — genau dieses "
                            f"Etikett behauptete eine Prüfung, die nicht stattgefunden hat")

    print(f"Registry: {len(METHODS)} Verfahren")
    print(f"  Belegstufe:  " + ", ".join(f"{k}={v}" for k, v in lvl.items()))
    print(f"  Umsetzung:   " + ", ".join(f"{k}={v}" for k, v in fid.items()))
    print()
    for p in problems:
        print("FEHLER: " + p)
    if problems:
        print(f"\n{len(problems)} Problem(e) gefunden.")
        return 1
    print("Registry, Belege und beide READMEs sind konsistent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
