# Architecture and engineering decisions

## Components

- **Browser:** Next.js 15 / React 19 / TypeScript, CSS design system (no external UI kit). Responsive marketing and application pages via App Router. Accessible form labels and buttons, loading/empty/error states, client-side video preview.
- **API:** FastAPI. All project and media routes require a signed JWT. Accounts use PBKDF2-HMAC-SHA256 with per-password random salt; secrets remain server-side. Sign-in tokens are kept in browser localStorage in this local beta. For production, migrate to secure HttpOnly same-site cookies and CSRF defenses.
- **Database:** SQLite WAL with users, projects and exports tables. Primary keys are UUID-like random IDs, and all project queries are user-scoped. `OPENSHORTS_DATA` configures durable storage. WAL + sqlite connections per request.
- **Video:** FFprobe validates source duration and resolution; FFmpeg handles trimming, 9:16 cropped frames, 1080×1920 H.264/AAC encoding, ASS subtitles using karaoke (`\\kf`) word-duration effects; MP4 returned as authenticated file download.
- **Transcription:** Optional `faster-whisper` local model. First attempts manual SRT on the project, then Whisper if installed, then embedded subtitles from FFmpeg. On failure it reports exactly which configuration is needed, with no fabricated transcript.
- **Highlighting:** sliding duration windows (24s/38s/52s), scored using speech density, hook vocabulary, punctuation, and sample length. Overlapping candidates are de-duplicated. Titles, descriptions and hooks are extracted from the real transcript. This is heuristic AI-assisted analysis, **not generative LLM output**.
- **Smart crop:** optional OpenCV face detection of one frame at each clip start. Computes centered horizontal crop around the largest detected face when possible; falls back to centered cropping. Not object tracking or dynamic multi-subject framing.
- **YouTube:** `yt-dlp` is a backend optional ingestion method for URLs of permitted videos. It may fail due to platform changes or regional/credential restrictions. Upload remains the reliable route.
- **Background processing:** FastAPI background tasks run in the API process, update SQLite status, and are polled every ~1.7 seconds from the project workspace. For a public deployment use a durable, isolated worker service instead. On server crash tasks do not automatically resume.

## Main API surface

| Method | Route | Purpose |
|---|---|---|
| GET | `/api/health` | Dependency readiness |
| POST | `/api/auth/signup` | Register |
| POST | `/api/auth/login` | Authenticate |
| GET | `/api/auth/me` | Current account |
| GET/POST | `/api/projects` | List/create projects |
| GET/PATCH/DELETE | `/api/projects/{id}` | Read/rename/delete |
| POST | `/api/projects/{id}/upload` | Stream upload with size limit |
| POST | `/api/projects/{id}/youtube` | Schedule permitted URL import |
| POST | `/api/projects/{id}/transcript` | Import SRT |
| POST | `/api/projects/{id}/analyze` | Schedule transcription + scoring |
| PATCH | `/api/projects/{id}/clips/{clip_id}` | Edit clip |
| POST | `/api/projects/{id}/clips/{clip_id}/export` | Schedule MP4 render |
| GET | `/api/projects/{id}/source` | Authenticated source media |
| GET | `/api/projects/{id}/exports` | Export list |
| GET | `/api/exports/{export_id}/download` | Authenticated MP4 download |

## Production evolution

Use Postgres for project data, object storage for media, a Redis-backed durable job queue with isolated rendering workers, short-lived presigned media URLs, cookies instead of localStorage JWT, OAuth/email confirmation and password recovery, stronger ingestion MIME/magic checks, explicit processing limits, observability, and AI model-serving architecture. Add continuous subject tracking, scene segmentation, diarization and a real LLM suggestion service behind backend-only credentials. Run FFmpeg workloads inside a restricted sandbox with CPU/memory limits. Never expose backend filesystem paths or user data in the client.
