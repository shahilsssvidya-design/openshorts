#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
for cmd in python3 node npm ffmpeg ffprobe; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "ERROR: $cmd not found. Install prerequisites in README.md and reopen terminal." >&2
    exit 1
  fi
done
if ! python3 -c 'import sys; assert (3,11) <= sys.version_info[:2] <= (3,12)' 2>/dev/null; then
  echo "WARNING: Python 3.11 or 3.12 is recommended; detected $(python3 --version)." >&2
fi
if [ ! -x backend/.venv/bin/python ]; then
  echo 'Creating Python virtual environment...'
  python3 -m venv backend/.venv
fi
backend/.venv/bin/python -m pip install -r backend/requirements.txt
if [ ! -d frontend/node_modules ]; then
  (cd frontend && npm install)
fi
if [ ! -f frontend/.env.local ]; then
  cp frontend/.env.example frontend/.env.local
fi
mkdir -p data
printf '\nSetup complete. Run: bash scripts/start-linux.sh\n'
