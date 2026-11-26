#!/usr/bin/env bash
# Lokaler Start des EDF-Analyzers auf dem MacBook (nicht fuer den Server!).
#
# Zweck: EDF_PASSWORD ist Pflicht-Env-Var (core/auth.py, kein Default aus
# Sicherheitsgruenden). Ohne sie bricht die App mit klarer Fehlermeldung ab.
# Dieses Skript laedt sie aus der gitignorierten .env.local und startet
# streamlit aus dem projekteigenen .venv -- nicht aus einem global
# installierten streamlit, das eine andere Version haben kann.
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f .env.local ]; then
  echo "FEHLER: .env.local fehlt. Anlegen mit: echo 'EDF_PASSWORD=...' > .env.local" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
source .env.local
set +a

exec .venv/bin/streamlit run app.py \
  --server.port="${EDF_PORT:-8501}" \
  --server.headless=true \
  --server.maxUploadSize=200
