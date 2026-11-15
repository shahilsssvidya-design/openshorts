# OpenShorts 2.0

**A real, local-first video-to-shorts web application** built from a blank project, with a cinematic multi-page Next.js frontend and a persistent FastAPI/SQLite backend. Users can register, create projects, upload a video, add an SRT transcript or transcribe speech locally, rank spoken highlights, adjust clip timing/caption styles, render vertical video, and download MP4 files.

> **Honest scope:** This is a self-hosted functional beta, **not yet a commercially hardened production SaaS**. It has a real working video pipeline, not simulated progress. The clip scorer is deterministic speech-density and hook-word analysis, **not an LLM**. Local Whisper transcription is available by optional install. Face detection samples a frame to estimate crop position; it is not continuous subject tracking. YouTube import is best-effort and requires valid permission and compatible access. See [docs/STATUS.md](docs/STATUS.md).

## Run on a MacBook M2 (16 GB)

Install these once:

1. Install [Homebrew](https://brew.sh) if it is not already installed.
2. Open **Terminal**, run `brew install python@3.12 node ffmpeg` (Node.js 20+ is recommended).
3. Extract this ZIP into a folder, then use `cd` to enter `OpenShorts_2.0`.
4. Run `./scripts/start-mac.sh`.
5. Open **http://localhost:3000** in your browser. Sign up and create your first project.

The startup script creates a Python virtual environment, installs dependencies, installs frontend npm dependencies, starts the backend on port `8000`, and starts Next.js on port `3000`. This needs an internet connection to install dependencies initially. You can stop both servers with **Ctrl+C**.

For automatic local speech transcription (instead of providing SRT files), in a second Terminal window run:

```bash
cd OpenShorts_2.0
backend/.venv/bin/python -m pip install faster-whisper
```

Then restart the backend. On first use, `faster-whisper` downloads the configured speech model. Default is `tiny` for a quick M2 start; set `WHISPER_MODEL=base` or `small` for greater accuracy. Faster-whisper is a community package whose current compatibility and model downloads may vary by macOS/Python version.

**No Whisper install?** Upload any MP4/MOV, then upload an `.srt` subtitle file using **Import .SRT**. Click **Discover best moments**. Clip analysis and exports work without external AI services.

## Full workflow

1. Open **Sign up** and create a local account (email + password, min 8 chars).
2. Open **New project** and choose a project name.
3. Upload a video from your machine. Source video metadata is validated with `ffprobe`. Alternatively, paste a YouTube URL **that you have permission to download and process**.
4. Import subtitle `SRT`, or install optional `faster-whisper` for local speech transcription.
5. Click **Discover best moments**. The backend extracts transcription data, evaluates timed candidate windows, and saves scored suggestions.
6. Open any suggested clip. Preview it and change trim points, captions, positions, color, size, title, and generated transcript excerpts.
7. Click **Save changes** or **Export MP4**. FFmpeg makes a 1080×1920 H.264/AAC file. When complete, **Download** appears in the Exports section.
8. Return to **Your projects** to resume work. Use **Delete** to remove a project and its local media/exports.

## Commands

| Task | Command |
|---|---|
| Start website + API | `./scripts/start-mac.sh` |
| Run all automated checks | `./scripts/test.sh` |
| Run backend only | `cd backend && .venv/bin/python -m uvicorn app.main:app --reload --port 8000` |
| Run frontend only | `cd frontend && npm run dev` |
| Frontend production build | `cd frontend && npm run build` |
| Backend API reference | `http://localhost:8000/docs` |

## Architecture

```text
OpenShorts_2.0/
├── frontend/
│   ├── app/                   Next.js App Router, global design system
│   ├── components/Site.tsx    Public pages + auth + dashboard + video editor
│   ├── lib/api.ts             Typed API client with token handling
│   ├── package.json
│   ├── next.config.ts
│   └── .env.example
├── backend/
│   ├── app/main.py            FastAPI, SQLite, authentication, pipeline
│   ├── tests/test_api.py      End-to-end API integration test
│   └── requirements.txt
├── scripts/
│   ├── start-mac.sh
│   └── test.sh
├── docs/
│   ├── ARCHITECTURE.md
│   ├── TROUBLESHOOTING.md
│   └── STATUS.md
└── .env.example
```

See the docs for API architecture and known gaps. Environment variables are described in `.env.example` and `frontend/.env.example`. A backend JWT signing secret is generated locally to `data/.jwt-secret` unless `SECRET_KEY` is provided; it must never be committed. All media and SQLite files are under `data/` and excluded by `.gitignore`.

## Privacy and rights

You control the locally hosted environment and are responsible for media rights. Do not download videos without permission. Public deployment requires a real privacy notice, additional abuse protections, per-user storage and processing quotas, a scalable job queue, and operational security review. The provided legal pages are local-edition informational text, not a substitute for legal review.
