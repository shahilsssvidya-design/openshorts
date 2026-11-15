# Troubleshooting

**`brew: command not found`** — install Homebrew from brew.sh, restart Terminal, and follow the displayed `eval` command to add it to PATH.

**`ffmpeg` / `ffprobe` not found** — run `brew install ffmpeg` and check `ffmpeg -version`.

**`npm` not found** — run `brew install node` and verify `node -v` is 20 or newer.

**The browser says "Cannot connect to API"** — keep `scripts/start-mac.sh` running; check `http://localhost:8000/api/health`, or start the API manually. Your frontend `.env.local` should say `NEXT_PUBLIC_API_URL=http://localhost:8000`.

**Port already in use** — stop the other processes running on ports 3000 or 8000 before restarting. On Mac: `lsof -i :3000` or `lsof -i :8000`.

**"No transcript available"** — import an `.srt` file via the workspace, or run `backend/.venv/bin/python -m pip install faster-whisper` and restart. A first transcription can require downloading model weights. For limited memory start with `WHISPER_MODEL=tiny`.

**YouTube import fails** — only use videos you have rights to process; try a direct file upload instead. Some videos are DRM-protected, private or otherwise restricted. Check that `yt-dlp` was installed with Python dependencies. The importer intentionally does not accept arbitrary websites.

**Export fails with `No such filter: ass`** — your FFmpeg build lacks libass. Install with `brew install ffmpeg`. You can temporarily turn captions OFF in the editor.

**Export is slow** — 1080×1920 H.264 CPU encoding costs resources. Keep clips short; lower simultaneous workloads. The first frame analysis can be slower if OpenCV initializes its classifier.

**Cannot preview video** — supported playback formats differ among browsers. MOV with unusual codecs may not play in browser even when FFmpeg can render it. Try MP4 H.264/AAC.

**Frontend build fails during installation** — ensure network access to npmjs.org and run `cd frontend && npm install && npm run build`. Do not copy a `node_modules` folder from another platform.

**Reset local installation** — Stop both servers, then delete `data/` to remove ALL accounts, projects, source videos and exports. This is destructive and cannot be undone without a backup.
