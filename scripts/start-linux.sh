#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [ ! -x backend/.venv/bin/python ] || [ ! -d frontend/node_modules ]; then
  echo 'Run bash scripts/setup-linux.sh first.' >&2
  exit 1
fi
for cmd in ffmpeg ffprobe npm; do
  if ! command -v "$cmd" >/dev/null 2>&1; then echo "Missing dependency: $cmd" >&2; exit 1; fi
done
export PATH="$ROOT/backend/.venv/bin:$PATH"
# Load owner's private backend-only credentials, never from the frontend.
for env_file in backend/.channel-monitor.env backend/.youtube.env; do
  if [ -f "$env_file" ]; then set -a; . "$env_file"; set +a; fi
done
if [ ! -f frontend/.env.local ]; then cp frontend/.env.example frontend/.env.local; fi
cleanup() {
  trap - INT TERM EXIT
  kill "${BACK_PID:-}" "${FRONT_PID:-}" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT
(cd backend && .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload) & BACK_PID=$!
(cd frontend && npm run dev) & FRONT_PID=$!
printf '\nOpenShorts: http://localhost:3000 | API: http://127.0.0.1:8000/docs\n'
wait "$BACK_PID" "$FRONT_PID"
