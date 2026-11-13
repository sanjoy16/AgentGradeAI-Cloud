#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
# Finder and non-login shells may omit Homebrew and Docker Desktop from PATH.
export PATH="/opt/homebrew/bin:/usr/local/bin:/Applications/Docker.app/Contents/Resources/bin:$PATH"
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
.venv/bin/python doctor.py --require-all
# Select a free local port without killing an existing assessment process.
PORT="$(.venv/bin/python - <<'PYPORT'
import os
import socket
requested = os.environ.get('AGENTGRADE_PORT')
ports = [int(requested)] if requested else range(8502, 8523)
for port in ports:
    with socket.socket() as sock:
        try:
            sock.bind(('127.0.0.1', port))
        except OSError:
            continue
        print(port)
        break
else:
    raise SystemExit('No free local port. Stop the previous app or set AGENTGRADE_PORT to a free port.')
PYPORT
)"
echo "Open http://127.0.0.1:$PORT . Stop this app with Control+C in this terminal."
exec .venv/bin/python -m streamlit run app.py --server.address=127.0.0.1 --server.port="$PORT"
