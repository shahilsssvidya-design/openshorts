# OpenShorts 2.0

**Local-first AI video clipping and repurposing.** Turn videos you own or are authorized to use into vertical Shorts, edit clips and captions, and export MP4 files from a web dashboard running on **your computer**.

- **Frontend:** Next.js 15 / React / TypeScript (port `3000`)
- **Backend:** Python / FastAPI / SQLite (port `8000`)
- **Video processing:** FFmpeg + FFprobe
- **Optional local AI:** faster-whisper for transcription; Ollama with `qwen3:4b` for creative titles, descriptions, hooks, hashtags, and supported caption features
- **Optional integrations:** YouTube uploads via each user's own Google OAuth credentials; authorized YouTube imports/live-source tools where available

> **Project status:** Local-development beta, **not** a production-ready hosted SaaS. macOS is the primary development environment. Windows and Linux instructions below are based on the code and tools, but **have not been tested end-to-end on those operating systems**. Some video filters, model dependencies, and integrations may need platform-specific adjustments. Please report reproducible issues.
>
> **No paid AI API is required for basic use.** Optional models require their own downloads and hardware resources. A fresh clone does **not** contain the original developer's videos, accounts, projects, tokens, API keys, or AI model files.

## 1. Requirements

| Component | macOS | Windows 10/11 (64-bit) | Linux (Ubuntu/Debian example) |
| --- | --- | --- | --- |
| Git | Homebrew or Git installer | Git for Windows | `apt install git` |
| Python | **3.12 recommended**, with `venv` | **3.12 recommended**, Python launcher (`py`) | **3.11–3.12 recommended**, with `venv` |
| Node.js | **20.9+** (22 LTS is a good choice) and npm | Same | Same |
| FFmpeg **and FFprobe** | `brew install ffmpeg` | FFmpeg build added to `PATH` | `apt install ffmpeg` |
| Disk / memory | Several GB free; 16 GB RAM recommended for local AI | Same | Same |
| Internet | Needed for initial package and optional model downloads | Same | Same |

Official downloads: [Git](https://git-scm.com/downloads) · [Python](https://www.python.org/downloads/) · [Node.js](https://nodejs.org/en/download) · [FFmpeg](https://ffmpeg.org/download.html) · [Ollama](https://ollama.com/download)

Check tools are available **in a new terminal** after installing them:

```text
python --version  (or python3 --version / py -3.12 --version)
node --version
npm --version
ffmpeg -version
ffprobe -version
```

**Important:** FFmpeg needs an H.264 encoder (normally `libx264`) and subtitle rendering support for some exports; not every minimal FFmpeg build has them. Check `ffmpeg -encoders` and `ffmpeg -filters` if exports fail.

## 2. Get the code

```bash
git clone https://github.com/shahilsssvidya-design/openshorts.git
cd openshorts
```

If the repository is **private**, GitHub will require an account with access; the owner must grant access before others can clone. You can also use GitHub's **Code → Download ZIP**, extract it, and open a terminal inside the extracted folder.

> Run commands from the **repository root**, the directory containing `frontend/`, `backend/`, and `scripts/`. Your folder name does not need to be `OpenShorts_2.0`.

## 3. Installation by operating system

### macOS (Apple Silicon M1/M2/M3/M4 or Intel)

Install prerequisites using [Homebrew](https://brew.sh):

```bash
brew install git python@3.12 node ffmpeg
```

In the cloned repository folder, make a Python 3.12 environment **before** the first start (avoids using an incompatible system Python):

```bash
python3.12 -m venv backend/.venv
./scripts/start-mac.sh
```

The existing Mac startup script installs backend/frontend dependencies as needed and launches both servers. To stop, press **Control+C** in the running terminal. If necessary, run `chmod +x scripts/start-mac.sh` first.

If you have already configured a working environment, just run `./scripts/start-mac.sh`.

### Windows 10/11 — PowerShell

Install Git, Python 3.12, Node.js, and FFmpeg. With `winget` available, these commands are an option (installers might prompt you):

```powershell
winget install --id Git.Git --exact
winget install --id Python.Python.3.12 --exact
winget install --id OpenJS.NodeJS.LTS --exact
winget install --id Gyan.FFmpeg --exact
```

**Close and reopen PowerShell** so the new tools appear on `PATH`. Verify `py -3.12 --version`, `node --version`, `npm --version`, `ffmpeg -version`, and `ffprobe -version`.

Clone the repository (or open your extracted ZIP folder):

```powershell
git clone https://github.com/shahilsssvidya-design/openshorts.git
cd openshorts
```

Install dependencies, then launch the API and web app in two PowerShell windows:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup-windows.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-windows.ps1
```

The start script opens **two separate PowerShell windows**, one for FastAPI and one for Next.js. Leave both open while using OpenShorts; close them or press **Control+C** in each to stop. `-ExecutionPolicy Bypass` applies only to the launched PowerShell process, not as a permanent machine setting.

**Manual Windows alternative:** In the repository root, use `py -3.12 -m venv backend\.venv`, then `backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt`. Run `npm install` inside `frontend`. Set `$env:PATH="$(Resolve-Path backend\.venv\Scripts);$env:PATH"`; in one terminal run `cd backend; .venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`, and in a second run `cd frontend; npm run dev`. Copy `frontend\.env.example` to `frontend\.env.local` first.

### Linux — Ubuntu / Debian example

```bash
sudo apt update
sudo apt install -y git ffmpeg python3 python3-venv python3-pip
```

Install Node.js **20.9+** (Node.js 22 LTS recommended) using the [official Node.js installation instructions](https://nodejs.org/en/download). The distro's default `nodejs` package may be too old. Prefer Python 3.11 or 3.12; on distributions whose `python3` is newer or older, install a supported Python and use it to create the venv instead.

```bash
git clone https://github.com/shahilsssvidya-design/openshorts.git
cd openshorts
bash scripts/setup-linux.sh
bash scripts/start-linux.sh
```

`setup-linux.sh` installs backend and frontend packages into the local project; `start-linux.sh` launches the local API and website. Press **Control+C** to stop. If `python3` is not a supported version, run the venv setup manually with a compatible interpreter, then rerun setup.

## 4. Open OpenShorts

When both servers are running:

| Service | Local URL |
| --- | --- |
| Web dashboard | **http://localhost:3000** |
| API documentation | **http://127.0.0.1:8000/docs** |
| Backend health check | **http://127.0.0.1:8000/api/health** |

Open the dashboard, **Sign up** for a new account on your **own local instance**, create a project, upload a video you have rights to use, and import `.srt` captions or configure local transcription. Discover moments, review/edit the proposed clips, and export vertical videos.

**AI metadata:** The initial highlight suggestion titles may be simple transcript-derived placeholders. For creative packaging, start Ollama, then use **AI Enhance All Clips** on an analyzed project or **Content → Generate with AI** on an individual clip, if those features are present in your checked-out version. Apply/save the generated copy before publishing. AI suggestions are not guaranteed to become viral and should be reviewed for accuracy.

## 5. Optional: speech transcription and AI titles

### Local speech transcription

Use the **virtual environment's Python**, not a global `pip`:

**macOS / Linux**

```bash
backend/.venv/bin/python -m pip install faster-whisper
```

**Windows (PowerShell)**

```powershell
backend\.venv\Scripts\python.exe -m pip install faster-whisper
```

The first transcription downloads a model; by default this project uses `WHISPER_MODEL=tiny`. Set `WHISPER_MODEL=base` or `small` for potentially better accuracy at additional resource cost. Model/wheel support differs by OS and Python version. **Without faster-whisper, upload an SRT transcript.**

### Creative title / description / hashtags (Ollama)

1. Install and start [Ollama](https://ollama.com/download) for your OS.
2. In a terminal run:

```bash
ollama pull qwen3:4b
ollama list
```

3. Keep Ollama running on `http://127.0.0.1:11434` (its usual local address).
4. Use the AI generation buttons in OpenShorts. The default model name is `qwen3:4b` if your installed version includes AI Content Studio / AI Metadata enhancements.

You can choose another compatible local model by setting the backend environment variable `OPENSHORTS_CONTENT_MODEL` to its installed name. Ollama-generated content should be reviewed; it may be inaccurate or unoriginal.

## 6. Optional: YouTube and livestream settings

You **do not need YouTube credentials** to process your own uploaded files. Optional features use credentials belonging to **each user of the clone**:

- **Channel live-status monitoring:** Google YouTube Data API v3 key, exposed only to the local backend as `OPENSHORTS_YOUTUBE_API_KEY`.
- **Publish to your YouTube channel:** Your own Google OAuth web-app client (`OPENSHORTS_YOUTUBE_CLIENT_ID`, `OPENSHORTS_YOUTUBE_CLIENT_SECRET`), with a redirect URI such as `http://localhost:8000/api/youtube/oauth/callback`. Configure the same redirect URI in Google Cloud and the application.
- **Authorized livestream recording:** Disabled by default; `OPENSHORTS_LIVE_RECORDING_ENABLED=1` is needed along with compatible authorized capture access. Creator-provided licensed feeds can be used where supported.
- **YouTube URL import:** Best effort. `yt-dlp` can be blocked by YouTube sign-in or automated-access checks. An upload OAuth token **does not** unlock video downloads.

Never commit credentials. The Mac/Linux launch scripts optionally load private `backend/.youtube.env` and `backend/.channel-monitor.env` files with `KEY=value` lines. The Windows launcher loads the same **simple** environment-file format (no multiline values or shell commands). Alternatively, provide these environment variables to the backend process yourself.

Example private configuration (use **your own** values; do not copy the literal placeholders into a real configuration):

```ini
OPENSHORTS_YOUTUBE_CLIENT_ID=YOUR_CLIENT_ID
OPENSHORTS_YOUTUBE_CLIENT_SECRET=YOUR_SECRET
OPENSHORTS_YOUTUBE_CALLBACK=http://localhost:8000/api/youtube/oauth/callback
```

Each clone gets its own SQLite data, encryption keys, and Google OAuth credentials. Never share your `data/` directory, account secrets, browser cookies, or uploaded media publicly.

## 7. Useful developer commands

| Task | macOS / Linux | Windows PowerShell |
| --- | --- | --- |
| Backend tests | `cd backend && .venv/bin/python -m pytest tests` | `cd backend; .venv\Scripts\python.exe -m pytest tests` |
| Frontend production build | `cd frontend && npm run build` | `cd frontend; npm run build` |
| Run frontend alone | `cd frontend && npm run dev` | `cd frontend; npm run dev` |
| Run API alone | `cd backend && .venv/bin/python -m uvicorn app.main:app --reload --port 8000` | `cd backend; .venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000` |

**Do not run `npm run build` while `npm run dev` is using the same `.next` directory.** Stop the dev server first, or configure separate `distDir` folders in `frontend/next.config.ts`.

## 8. Troubleshooting

- **`python: command not found` / no `py -3.12`:** Install Python 3.12 and reopen the terminal. Create the virtual environment with the installed interpreter.
- **`npm`, `ffmpeg`, or `ffprobe` not found:** Install prerequisites and reopen your terminal so the PATH updates. `ffprobe` must be installed alongside `ffmpeg`.
- **`yt-dlp not installed` even though pip installed it:** Ensure the backend virtual environment's `bin` (Unix) or `Scripts` (Windows) directory is on the backend process's `PATH`. The included launch scripts do this.
- **Port `3000` or `8000` in use:** Stop old Next.js/Uvicorn instances before launching another. Don't run multiple copies of OpenShorts against one project database.
- **`Cannot find module './vendor-chunks/lucide-react.js'`:** Stop the dev server, clear generated `frontend/.next` (and `.next-dev` if applicable), then restart. Never delete `data/`.
- **Webpack CSS warning about `start` vs `flex-start`:** A warning may be nonfatal if `next build` succeeds. The underlying CSS declaration can be adjusted separately.
- **AI repeats transcript titles:** Install/start Ollama, verify `ollama list` includes the configured model, and run **AI Enhance All Clips** or **Generate with AI**. The initial analyzer's baseline titles are not AI-generated.
- **Export has no captions:** Make sure FFmpeg supports the `subtitles` filter / libass. Re-export after updating caption settings.
- **Windows subtitle path/render failure:** FFmpeg filter paths on Windows can require extra escaping. This is a known area needing Windows testing; report the clip settings and FFmpeg stderr.
- **YouTube sign-in/bot detection:** The app cannot guarantee downloading YouTube content even if it is publicly viewable. Use your own source file or properly authorized downloadable feed.

## 9. Repository structure

```text
openshorts/
├── backend/
│   ├── app/                FastAPI routes, media processing, AI helpers
│   ├── tests/              Python API tests
│   └── requirements.txt
├── frontend/
│   ├── app/                Next.js routes and CSS
│   ├── components/         Editor UI
│   ├── lib/                Frontend API client
│   └── package.json
├── scripts/
│   ├── start-mac.sh        Existing Mac launcher
│   ├── setup-linux.sh      Linux install
│   ├── start-linux.sh      Linux launcher
│   ├── setup-windows.ps1   Windows install
│   └── start-windows.ps1   Windows launcher
├── docs/
└── README.md
```

The actual features present depend on which upgrades are committed to the branch you clone. This README does **not** substitute for merging uncommitted files from the developer's Mac.

## 10. Security, rights, contributions, and license

- Use media you own or have explicit permission to process and publish. Respect creator rights, privacy, platform restrictions, and local laws.
- `.env*` secrets, `backend/.youtube.env`, `backend/.channel-monitor.env`, SQLite databases, `.venv/`, `node_modules/`, models, and exported media **must never be committed**. Always review `git status` and staged files before pushing.
- Local development binds the API to `127.0.0.1`; the Next.js dev process may bind to all interfaces (`0.0.0.0`). **Do not expose this development application to the internet** or treat it as a secure hosted service.
- Check the repository's Issues tab for bugs; include OS/version, Python/Node/FFmpeg versions, error logs **with secrets redacted**, and reproduction steps.
- **License:** Unless a `LICENSE` file is added explicitly, public source visibility is **not** the same as a grant of open-source redistribution rights. The repository owner should choose a license before inviting public reuse.

Built as a local-first project, with community testing especially welcome on Windows and Linux.
