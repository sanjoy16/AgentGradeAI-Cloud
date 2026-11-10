#!/bin/bash
set -e
cd "$(dirname "$0")"
if ! command -v brew >/dev/null; then
  echo "Install Homebrew from https://brew.sh, follow its PATH instructions, then rerun this launcher."
  exit 1
fi
if ! command -v docker >/dev/null; then
  echo "Install and open Docker Desktop, then rerun this launcher."
  exit 1
fi
docker info >/dev/null
brew install python@3.12 cbmc z3 cppcheck
PYTHON="$(brew --prefix python@3.12)/bin/python3.12"
"$PYTHON" -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
docker pull --platform linux/amd64 klee/klee:3.0
mkdir -p data
export AGENTGRADE_DB="$PWD/data/agentgrade.db"
if [ ! -f "$AGENTGRADE_DB" ]; then
  echo "For your existing Docker database, first follow MIGRATE_MAC.md. New installations can continue."
fi
printf 'Enter faculty password (hidden): '
read -r -s FACULTY_PASSWORD
printf '\n'
export FACULTY_PASSWORD
.venv/bin/python doctor.py
exec .venv/bin/python -m streamlit run app.py --server.address=127.0.0.1 --server.port=8502
