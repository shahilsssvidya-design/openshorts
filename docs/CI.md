# Continuous Integration (CI) for OpenShorts

When code is pushed to `main` or a pull request is opened, **GitHub Actions** runs two checks on a fresh Linux runner:

1. **Backend:** installs Python 3.12 and FFmpeg, installs `backend/requirements.txt`, validates dependency compatibility, checks Python syntax, and runs all existing backend tests. These use synthetic/local test data, not your own accounts or video uploads.
2. **Frontend:** installs Node.js 22, installs npm dependencies, runs TypeScript checks, and builds Next.js for production.

### How to view results

Open your GitHub repository → **Actions** → **OpenShorts CI** → the most recent run. Green means both jobs passed. Red means at least one check failed; open that job and expand the failed step to read the actual error.

### How to re-run tests on your Mac

From the project root (with Python packages, npm dependencies and FFmpeg installed):

```bash
bash scripts/test.sh
```

Or separately:

```bash
cd backend && .venv/bin/python -m pytest -q tests
cd ../frontend && npm run lint && npm run build
```

On Windows, activate your virtual environment or run `backend\.venv\Scripts\python.exe -m pytest -q backend\tests` from the project root (if the package import path is configured, otherwise run it from `backend`).

### What CI **does not** verify

- Live YouTube downloads or uploads, Google OAuth consent, and YouTube API quotas
- Local Ollama/Qwen output or model downloads
- Hardware-specific Windows/macOS video rendering and subtitles
- Visual appearance or real-world video quality

These still need manual testing on each operating system. **A green CI run does not guarantee all features work on every platform.**

### Privacy and safety

The workflow only needs `contents: read` permissions. It does not use or upload your Google credentials, personal SQLite database, videos, or local `.env` files. Do not store real API keys in test code or commit them to GitHub. Test data is created within the temporary GitHub runner and discarded afterwards.

### One improvement to make later

Commit a reviewed `frontend/package-lock.json` so CI can use `npm ci` for reproducible npm installs. Until then, the workflow uses `npm install`.
