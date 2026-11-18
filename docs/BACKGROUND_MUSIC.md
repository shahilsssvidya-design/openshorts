# OpenShorts 2.0 — Background Music Upgrade

Add background music to **every existing OpenShorts clip layout**: Smart Crop, Fit / No Crop, and Gameplay Split Screen.

## What is included

- A new **Music** tab inside the Clip Editor.
- Three original, included instrumental demo WAV tracks. No external streaming service, paid API, or download required:
  - **Night Drive:** cinematic synth (108 BPM)
  - **Bright Bounce:** upbeat, playful (120 BPM)
  - **Soft Focus:** calm ambient (90 BPM)
- Upload your own MP3, WAV, M4A, AAC, FLAC, OGG, OPUS, or WMA file (up to 60 MB, subject to decoding support in FFmpeg).
- Separate music volume (default **20%**) and main-video voice volume (default **100%**).
- Play/pause the selected track and hear it with the video preview while the Music tab is open.
- Music loops to fill the Short, with a short fade-out. Existing exports are not overwritten, and the original video is never changed.
- The **Export all clips** action respects each clip's individually saved music settings.
- Download Full Project Folder includes your uploaded audio in `music/` (demo tracks are shipped with the app rather than copied into each project archive).
- Local-only and authenticated file endpoints: each user's uploaded music is scoped to their own project.

## Install (macOS)

1. Download `OpenShorts_Background_Music_Upgrade.zip` from the ChatGPT message.
2. In Finder, extract the ZIP. Move **the full extracted folder** (not just `install.py`) into `~/kali/`, alongside `~/kali/OpenShorts_2.0/`.
3. Stop the OpenShorts server using `Control + C`. **Do not stop Ollama** if you use AI titles or moment discovery.
4. In Terminal, run:

```bash
cd ~/kali/OpenShorts_2.0
python3 ../OpenShorts_Background_Music_Upgrade/install.py
export PATH="$PWD/backend/.venv/bin:$PATH"
./scripts/start-mac.sh
```

Open `http://localhost:3000`, sign in, open a project with clips, select a clip, then go to **Music**.

1. Choose **No music**, one of three demos, or **Upload your own music**.
2. Adjust the two volume sliders. For speech-heavy videos, try 15–25% music and 100% original audio.
3. Click **Save changes**, then **Export MP4**. When the export finishes, download it from the Exports section.
4. Listen to the exported MP4 to verify the final audio mix. Changing the settings does not retroactively change previously exported videos; re-export as needed.

**Note:** The Music tab can audition and synchronize audio with the in-browser video preview. Browser decoding differs by format; if an uploaded audio file doesn't play in the browser, check whether FFmpeg accepts it, or use MP3/WAV. Mixing takes place on the backend during MP4 export.

## Using your fresh GitHub test copy

If you want to test it without changing your working project, run the installer against that copy instead:

```bash
python3 ~/kali/OpenShorts_Background_Music_Upgrade/install.py --root ~/test/OpenShorts_Fresh_Test
```

Only run one OpenShorts instance at once (ports 3000 and 8000).

## Publish the new feature to GitHub

After verifying the feature, run in your original `~/kali/OpenShorts_2.0` project:

```bash
cd ~/kali/OpenShorts_2.0

git add backend/app/music.py backend/app/demo_music/ \
  backend/app/main.py backend/app/media_extras.py backend/tests/test_background_music.py \
  frontend/components/BackgroundMusic.tsx frontend/components/Site.tsx \
  frontend/lib/api.ts frontend/app/globals.css docs/BACKGROUND_MUSIC.md README.md

git diff --cached --stat
git commit -m "Add background music library and MP4 audio mixing"
git push origin main
```

Any Windows or Linux user who clones your updated repo gets the same demo audio files and features. FFmpeg must be on their PATH. This upgrade does not require numpy on end users' machines (the included WAVs are pre-generated).

## Troubleshooting

- **Music tab missing:** Restart the Next.js server. If needed, stop all server processes, remove `frontend/.next-dev`, and restart.
- **Demo track missing:** Make sure the extracted ZIP contained `demo_music/*.wav` and rerun the installer if it was incomplete.
- **Custom music unavailable:** Upload the audio in the same project, then select **My uploaded track** and save the clip.
- **Music drowned out the voice:** Lower Music Volume. The original audio remains at its configured level.
- **No sound on the original video:** OpenShorts still exports the chosen background track, even if the original source has no audio.
- **Project ZIP too large:** It now contains your uploaded audio, along with the existing video files and exports.
- **MP4 video takes longer to export:** Adding music requires a second FFmpeg pass for audio, while the video stream is copied without re-encoding.

## Files added/changed

Added: `backend/app/music.py`, `backend/app/demo_music/{night-drive,bright-bounce,soft-focus}.wav`, `frontend/components/BackgroundMusic.tsx`, `backend/tests/test_background_music.py`, `docs/BACKGROUND_MUSIC.md`.

Updated: `README.md` (new feature section), `backend/app/main.py` (clip schema, validation, export hook and routes), `backend/app/media_extras.py` (project ZIP), `frontend/components/Site.tsx` (Music tab and preview sync), `frontend/lib/api.ts` (music fields), `frontend/app/globals.css` (dark styling).

## Privacy and rights

No commercial music is bundled; the three instrumentals were created specifically as original demo tracks for this upgrade. You are responsible for ensuring that uploaded third-party music can legally be included in your YouTube or other published videos. **YouTube may still apply Content ID policies to material it detects.**

Installation creates backups outside your repository in `~/test/OpenShorts_Upgrade_Backups/`. Your projects, SQLite database, uploads, existing exports, account tokens, and OAuth/API credentials are untouched. The installer is repeat-safe and does not delete any of them.
