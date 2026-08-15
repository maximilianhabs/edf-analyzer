#!/usr/bin/env bash
# Bildet exakt den schnellen CI-Job "checks" aus .github/workflows/test.yml nach — vor jedem
# Push von Hand ausführen. Anlass: 2026-08-15 waren vier Pushes in Folge rot, weil `ruff`
# nur in der CI lief, nie lokal — die eigene Prüfroutine deckte das gesamte Repository nicht
# ab. Dieses Skript schliesst genau die Lücke, statt sich darauf zu verlassen, in der
# nächsten Session wieder daran zu denken.
#
#     bash tools/preflight.sh
#
# Bei jeder neuen Prüfzeile in .github/workflows/test.yml (Job "checks") auch hier ergänzen —
# sonst öffnet sich dieselbe Lücke an anderer Stelle wieder.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== i18n =="
python3 tools/check_i18n.py

echo "== Schriften =="
python3 tools/check_fonts.py

echo "== Methoden-Registry =="
python3 tools/check_methods.py

echo "== Schichten =="
python3 tools/check_layering.py

echo "== Session-State =="
python3 tools/check_session_state.py

echo "== Lizenzen =="
python3 tools/check_licenses.py

echo "== Linter (ruff), GESAMTES Repository =="
ruff check .

echo
echo "Alle Preflight-Prüfungen grün."
