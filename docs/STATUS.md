# Functional status and honest limitations

## Implemented (real operations)

- Marketing: landing, features, how-it-works, pricing, contact, informational terms and privacy pages.
- Application: login/signup, protected dashboard, project creation/history/search/delete, settings/account/API configuration, upload/YouTube import, source preview, job progress, moments list, clip editor, caption styling, trim controls, transcript excerpts, MP4 export and authenticated download.
- Backend: SQLite persistence, password hashing, JWTs, API authorization, video probing, SRT ingestion, optional local Whisper, transcript-driven clip ranking, FFmpeg 9:16 crop, optional OpenCV face-biased starting crop, word-timed ASS karaoke subtitles, long-running jobs, error state and analysis retries.
- Integration tests exercise account creation, authentication, CRUD, upload, SRT, analysis, export and download using a generated synthetic video.

## Partial / limitations

- A cloud-hosted generative AI model is **not implemented**. Highlight detection is speech heuristic ranking, not LLM-based reasoning. Suggested hooks/descriptions are excerpts of your real transcript, not generated marketing copy.
- Smart crop is a static face-based estimate at clip start, not continuous tracking.
- Captions use word-aligned timings when Whisper provides them; SRT-only transcripts get approximate evenly spaced word timing. Burned-in ASS uses karaoke transitions, not complex motion graphics.
- YouTube URLs require accessible videos and must comply with platform terms; YouTube restrictions may block certain links.
- Project status polling runs only while viewing the workspace; backend jobs continue if the API process stays alive. FastAPI background tasks are not a durable cloud job queue.
- Contact page deliberately does not invent an operational email address or fake form submission.
- No payments, subscriptions, cloud storage, multi-tenant quotas, or deployment infrastructure are implemented.
- Production-grade account recovery/email verification, abuse moderation, centralized logging, and rate limits are not included.
- Frontend dependency installation and production build require npm registry access. If build cannot run in the evaluation environment due to network restrictions, it remains **unverified**, not "passed".
