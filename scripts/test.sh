#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
(cd backend && if [ -x .venv/bin/python ]; then .venv/bin/python -m pytest tests -q; else python3 -m pytest tests -q; fi)
(cd frontend && npm run lint && npm run build)
