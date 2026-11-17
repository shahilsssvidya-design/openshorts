# 🎬 OpenShorts 2.0

**Turn long videos into YouTube Shorts, Instagram Reels, and other vertical clips — on your own computer.**

OpenShorts is a local video editor with a website-style dashboard. It helps you find interesting moments, add subtitles, make vertical videos, create titles and thumbnails with AI, and upload finished clips to your **own YouTube channel**.

**Runs locally • No paid AI API needed for basic use • Your projects stay on your computer**

> **Project status:** OpenShorts is a work-in-progress, self-hosted beta. It was developed mainly on macOS. Windows and Linux launch scripts are included, but those operating systems have **not yet been tested end to end**. Some AI or video-processing features may need additional troubleshooting there. This is not a hosted website or a finished commercial service.
>
> **Important:** Everyone who downloads the project gets the **source code and features**, not the original developer's accounts, videos, Google credentials, or AI model downloads. You create your own local account and connect your own YouTube channel.

## ✨ What can OpenShorts do?

| Feature | What it means |
| --- | --- |
| 📹 Import a video | Upload an MP4/MOV video, or try an accessible YouTube link you have permission to use. |
| ✂️ Find clips | Suggest interesting moments from the spoken transcript. You choose which ones are good. |
| 💬 Automatic subtitles | Turn speech into captions using the optional local Whisper model, or import an `.srt` file. |
| 🌍 Caption languages | Original language, Hindi written as **Hinglish**, or English translation. You can also turn captions off. |
| 🎨 Edit captions | Change caption style, size, color, and position. |
| 📱 Vertical Shorts | Export **1080 × 1920 (9:16)** MP4 videos. |
| 🎯 Smart framing | Choose face-focused or manual framing. You can also use Fit/No Crop layouts. |
| 🎮 Gameplay split-screen | Put your main clip on top and your own Minecraft/Subway Surfers gameplay on the bottom. |
| 🧠 AI titles & descriptions | Use local **Qwen through Ollama** to suggest better titles, hooks, descriptions, and hashtags. |
| 🖼️ Thumbnail designs | Generate three thumbnail ideas from real frames of the selected clip, then download the JPEG. |
| 📦 Export and save | Export one clip, export all suggested clips, or download the complete project as a ZIP. |
| ▶️ Publish to YouTube | Connect a YouTube channel using Google login and upload completed clips with titles and descriptions. |
| 🔴 Live highlights | Optional tools for **authorized** livestreams and channel monitoring, with extra setup. |

**Good to know:** Suggested clips are ranked mostly from transcript information, not by an all-knowing AI. AI titles and thumbnails are separate actions. No tool can promise that a video will go viral.

---

## 🚀 Quick start: Install OpenShorts

### Before you start

Install these free tools:

1. **Git** — [git-scm.com](https://git-scm.com/downloads) (downloads the project).
2. **Python 3.12** — [python.org](https://www.python.org/downloads/) (runs the backend). Python 3.11 should also work for many setups.
3. **Node.js 20.9 or newer** — [nodejs.org](https://nodejs.org/en/download) (runs the website). Node.js 22 LTS is a good choice.
4. **FFmpeg + FFprobe** — [ffmpeg.org](https://ffmpeg.org/download.html) (edits and exports the videos).
5. **Several GB of free space.** 16 GB RAM is recommended if you want to use local AI.

A fresh installation needs an internet connection to download software packages. You **do not** need a Google account or Ollama just to edit and export your own uploaded videos with an existing subtitle file.

### 🍎 macOS (MacBook / Mac mini / iMac)

**1.** Open **Terminal**. Install [Homebrew](https://brew.sh) if needed, then run:

```bash
brew install git python@3.12 node ffmpeg
```

**2.** Download the project:

```bash
git clone https://github.com/shahilsssvidya-design/openshorts.git
cd openshorts
```

**3.** Prepare Python and start everything:

```bash
python3.12 -m venv backend/.venv
bash scripts/start-mac.sh
```

Leave Terminal open while OpenShorts is running.

### 🪟 Windows 10 / 11

**1.** Install Git, Python 3.12, Node.js, and FFmpeg. You can use the download links above, or try these commands in PowerShell if `winget` is installed:

```powershell
winget install --id Git.Git --exact
winget install --id Python.Python.3.12 --exact
winget install --id OpenJS.NodeJS.LTS --exact
winget install --id Gyan.FFmpeg --exact
```

Close and reopen PowerShell after installing the tools.

**2.** Download OpenShorts:

```powershell
git clone https://github.com/shahilsssvidya-design/openshorts.git
cd openshorts
```

**3.** Set up and start:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup-windows.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-windows.ps1
```

The launcher opens separate windows for the website and backend. **Keep both open.** If PowerShell says a script is missing, check that your copy of the repository includes `scripts/setup-windows.ps1` and `scripts/start-windows.ps1`.

> Windows support is experimental. An FFmpeg build with `libx264` and subtitle-rendering support is needed for the full export experience.

### 🐧 Linux (Ubuntu / Debian example)

**1.** Open a terminal and install the system tools:

```bash
sudo apt update
sudo apt install -y git ffmpeg python3 python3-venv python3-pip
```

Install **Node.js 20.9+** from [nodejs.org](https://nodejs.org/en/download). Use Python 3.11 or 3.12 if possible; your distribution may ship a newer version.

**2.** Download and run OpenShorts:

```bash
git clone https://github.com/shahilsssvidya-design/openshorts.git
cd openshorts
bash scripts/setup-linux.sh
bash scripts/start-linux.sh
```

> If your Linux `python3` version is not compatible with the AI packages, install Python 3.12 and create `backend/.venv` with that version before running `setup-linux.sh`. Linux support is still experimental.

### ✅ Open the app

After the website and backend have started, open:

- **OpenShorts website:** http://localhost:3000
- **Backend API / diagnostics:** http://127.0.0.1:8000/docs

Click **Sign up** to create a new account on your own computer. Then create your first project.

To stop OpenShorts, press **Ctrl+C** in the terminal(s) running it. Your projects stay saved locally.

> **Private repository?** GitHub cloning only works if you have access. The repository owner must make the repository public (after checking for secrets) or invite you.

---

## 🎥 How to create your first Short

1. Start OpenShorts and log in.
2. Click **Create project** and enter a name.
3. **Upload a video** that belongs to you, or one you have permission to edit.
4. Add subtitles in one of two ways:
   - **Easy automatic option:** install `faster-whisper` using the next section, then use transcription.
   - **No AI option:** click **Import .SRT** and select a subtitle file containing spoken words with timestamps.
5. Click **Discover best moments**.
6. Open a suggested clip. Check that the start and end times make sense.
7. Choose your **Captions**, **Frame**, and **Content** settings.
8. Click **Export MP4**. Download the finished video when it is ready.

Your exported video can be used on YouTube Shorts, Instagram Reels, and other services, subject to each platform's rules.

### Save a whole project

On the project page, use **Export all clips** to render the suggestions, then use **Download full project folder** to get a ZIP with your original, exports, thumbnails, and project information. The ZIP only includes exports that have actually finished rendering.

---

## 💬 Turn speech into subtitles (Whisper)

OpenShorts can use **faster-whisper**, which runs on your computer. The download is optional.

**Mac or Linux** — from the OpenShorts folder:

```bash
backend/.venv/bin/python -m pip install faster-whisper
```

**Windows PowerShell** — from the OpenShorts folder:

```powershell
backend\.venv\Scripts\python.exe -m pip install faster-whisper
```

Restart OpenShorts afterward. The first transcription may download an additional speech model.

The default model is `tiny` (small and fast). You can choose a different model with `WHISPER_MODEL=base` or `WHISPER_MODEL=small` before starting the backend; these may improve results but require more computer resources.

### Subtitle choices in the clip editor

- **Original:** Keep the original speech language in the captions.
- **Hinglish:** Write spoken Hindi in English letters, such as `kaise ho`.
- **English translation:** Translate Hindi speech into English using **local Ollama**. Timings are approximate.
- **No captions:** Turn off the Captions switch.

You can also change font-style presets, colors, size, and position. Captions are burned into exported MP4s when enabled. Check the spelling and timing before publishing.

---

## 🧠 Get better AI titles, descriptions, hashtags, and thumbnails (Qwen)

The basic clip finder may first show a **simple title copied from the transcript**. To replace it with creative suggestions, install local AI and use the dedicated AI buttons.

**1.** Install [Ollama](https://ollama.com/download) and start the Ollama app/service.

**2.** Open a terminal or PowerShell window and download the model:

```bash
ollama pull qwen3:4b
ollama list
```

**3.** Keep Ollama running. It normally serves requests at `http://127.0.0.1:11434`.

**4.** In OpenShorts:

- Open a project with suggested clips.
- Use **AI Enhance All Clips** to rewrite titles, hooks, descriptions, and hashtags for multiple existing clips. Choose a tone and language, then let it finish.
- To work on one clip, open it → **Content** → **Generate with AI**.
- Choose among the generated title and thumbnail ideas, edit anything you want, and click **Apply to clip & save**.
- Use **Download thumbnail** if you want the JPEG file.

The generated descriptions and hashtags can prefill the **Publish to YouTube** window after you save them.

**Please review AI output.** It may misunderstand the video, write a weak title, or invent details. It does not guarantee views. Thumbnail JPEGs are downloaded separately; this version does **not** automatically upload a custom thumbnail to YouTube.

**If you cannot see these AI buttons:** Your copy of the GitHub repository may not include the latest OpenShorts AI Content Studio and AI Metadata upgrades. The repository owner needs to commit and push those files.

---

## 🎮 Make a Short with gameplay at the bottom

Want a talking video on top and Minecraft or Subway Surfers gameplay underneath?

1. Open a suggested clip.
2. Go to the **Frame** tab.
3. Choose **Gameplay Split Screen**.
4. Select **Minecraft** or **Subway Surfers**.
5. Upload your **own or licensed** gameplay MP4.
6. Preview, save, and **Export MP4**.

OpenShorts keeps the main video's sound and mutes the gameplay video. The exported video is vertical. With the latest no-black-bars fix, both sections fill their area; this can crop a little from the edges.

**Gameplay videos are not included in GitHub.** Record your own or use footage you have permission to republish.

---

## ▶️ Publish directly to your own YouTube channel

**Yes, people who clone OpenShorts can use YouTube publishing.** They must connect **their own YouTube channel**. They cannot use the developer's secret Google credentials from GitHub.

This is a **one-time setup for each installation**. You do not need to configure YouTube to use the editor or export MP4 files.

### Part A — Create your free Google API credentials

**1.** Open [Google Cloud Console](https://console.cloud.google.com/) and sign in using a Google account.

**2.** Create a project (for example, `My OpenShorts`).

**3.** Go to **APIs & Services → Library** and enable **YouTube Data API v3**.

**4.** Configure **Google Auth Platform / OAuth consent screen**. Choose an appropriate audience for your project. If the app is in **Testing** mode, add the Google account you will use with YouTube under **Test users**.

**5.** Go to **Clients / Credentials** and create an **OAuth client ID**. Select **Web application** (not Desktop).

**6.** Add this exact **Authorized redirect URI**:

```text
http://localhost:8000/api/youtube/oauth/callback
```

**7.** Save the **Client ID** and **Client Secret** privately. Never upload them to GitHub, put them in frontend files, or send them to strangers.

Google may ask you to complete additional OAuth verification steps if you want to offer a public app to many people. Testing-mode access can be limited to approved test users.

### Part B — Put the credentials in OpenShorts

**Mac or Linux** — from the OpenShorts folder:

```bash
cp backend/.youtube.env.example backend/.youtube.env
```

Open `backend/.youtube.env` in your text editor and replace the placeholders with your own values:

```dotenv
OPENSHORTS_YOUTUBE_CLIENT_ID="YOUR_CLIENT_ID.apps.googleusercontent.com"
OPENSHORTS_YOUTUBE_CLIENT_SECRET="YOUR_PRIVATE_CLIENT_SECRET"
OPENSHORTS_YOUTUBE_CALLBACK="http://localhost:8000/api/youtube/oauth/callback"
OPENSHORTS_FRONTEND_URL="http://localhost:3000"
```

On macOS/Linux, you can also run `chmod 600 backend/.youtube.env` to limit access to that private file.

**Windows PowerShell** — from the OpenShorts folder:

```powershell
Copy-Item backend\.youtube.env.example backend\.youtube.env
notepad backend\.youtube.env
```

Put the same four settings in the file. Save it, then **stop and restart OpenShorts** so the backend can read the credentials.

### Part C — Connect YouTube and publish

1. Open http://localhost:3000 and log into OpenShorts.
2. In the sidebar, open **Account & API**.
3. Under **YouTube publishing**, click **Connect YouTube**.
4. Select your Google/YouTube account and grant the requested upload permission.
5. Open a project and **Export MP4** for the clip you want to upload.
6. In the exported clip list, click **Publish to YouTube**.
7. Check or edit the **title**, **description** (including hashtags), **visibility**, and **Made for kids** setting.
8. Confirm you own or have rights to publish the footage.
9. Press **Upload**. Start with **Private** to test safely.
10. Keep OpenShorts running until the upload completes. Click **View on YouTube** or check YouTube Studio.

**What does OpenShorts upload?** The completed MP4, your chosen title, description, visibility, and audience setting. **YouTube decides whether the uploaded video qualifies as a Short.** It can take time for YouTube to process a video. YouTube may also apply API limits and verification requirements.

**Important:** A YouTube API key alone **cannot publish videos**. Publishing uses Google OAuth and the YouTube Data API upload permission (`youtube.upload`). The YouTube account connection belongs to the person who signs in.

Helpful official guides: [YouTube authentication](https://developers.google.com/youtube/data/guides/authentication) · [YouTube video uploads](https://developers.google.com/youtube/data/reference/rest/v3/videos/insert).

---

## 🔴 Live highlights and channel monitoring (optional)

OpenShorts also includes experimental tools for approved livestream workflows. They are **off by default** or may require additional permissions.

For channel monitoring, make your own YouTube Data API key in Google Cloud, then create the private configuration file:

**Mac / Linux:**

```bash
cp backend/.channel-monitor.env.example backend/.channel-monitor.env
```

**Windows PowerShell:**

```powershell
Copy-Item backend\.channel-monitor.env.example backend\.channel-monitor.env
```

Open the file and set `OPENSHORTS_YOUTUBE_API_KEY` to your own key. For capture features, only if you have the required permissions, you can set `OPENSHORTS_LIVE_RECORDING_ENABLED="1"`. See the comments in the example file for optional creator-provided feeds and other settings.

Restart OpenShorts and open **Live highlights** or **Auto channel monitor** in the sidebar.

> **Limitations:** YouTube can block automatic video downloads or livestream capture. A YouTube OAuth upload connection or API key does **not** bypass those restrictions. For reliable editing, upload your own recordings or use a source the creator has specifically authorized you to access. Automatic live upload, where offered, is **Private-only** and opt-in.

---

## 🧰 Common problems (easy fixes)

| Problem | What to try |
| --- | --- |
| Website does not open | Make sure the website and backend are both running. Check `http://localhost:3000` and `http://127.0.0.1:8000/docs`. |
| `ffmpeg` not found | Install FFmpeg and FFprobe, then open a new terminal. |
| `No module named ...` | Finish the OS setup script. Make sure your Python virtual environment is `backend/.venv`. |
| No automatic subtitles | Install `faster-whisper` in the project virtual environment, restart, or import an `.srt` file. |
| Ollama / Qwen error | Open Ollama, run `ollama list`, and check for `qwen3:4b`. |
| AI titles still look like transcript | Click **AI Enhance All Clips** and wait for a success message, or **Content → Generate with AI** for one clip. |
| Missing AI button | Ensure the GitHub branch actually contains the latest AI source files. |
| Google `redirect_uri_mismatch` | Check that the callback URL in Google Cloud is exactly `http://localhost:8000/api/youtube/oauth/callback`. |
| YouTube access blocked | Check the Google consent screen, test-user list, and app verification status. |
| YouTube upload failed | Check YouTube Studio **before retrying** so you do not accidentally post twice. |
| YouTube URL cannot be imported | YouTube may block downloads. Upload your own video file instead. |
| Next.js `lucide-react.js` or vendor chunk missing | Stop all Next.js servers, delete the generated `.next` (or `.next-dev`) cache, and restart. Do not delete `node_modules` or your project files unnecessarily. |
| ZIP includes no finished clip | Export the clip first. Only completed exports are saved in the project download. |

**Mac/Linux cache command** (run only after stopping Next.js):

```bash
rm -rf frontend/.next frontend/.next-dev
```

**Windows PowerShell cache command** (after stopping Next.js):

```powershell
Remove-Item -Recurse -Force frontend\.next, frontend\.next-dev -ErrorAction SilentlyContinue
```

Do not run `npm run build` in the same build directory while a Next.js development server is running.

---

## 📁 What's in this repository?

```text
openshorts/
├── frontend/                  Website and editor (Next.js)
├── backend/                   Video processing and API (FastAPI)
│   ├── app/                   AI, subtitles, clips, publishing, monitoring
│   └── requirements.txt
├── scripts/                   Start/setup commands for each OS
├── docs/                      Additional technical notes
├── data/                      Created on your computer (not uploaded to Git)
└── README.md                  This guide
```

**A shared GitHub repository contains code, not personal data.** Each installation creates its own local account, video projects, downloads, AI model files, and YouTube authorization.

### For the repository owner: before telling people to clone

Make sure you have actually pushed **all the current code**, not just this README. The latest features require files such as `backend/app/creative_ai.py`, `backend/app/ai_metadata.py`, `backend/app/youtube_publish.py`, `backend/app/media_extras.py`, and their frontend components. Confirm the Windows/Linux scripts have also been committed.

Never publish:

- `data/` (videos, exports, account database, saved Google authorization)
- `backend/.youtube.env` or `backend/.channel-monitor.env` (API credentials)
- `.env.local`, `.venv/`, `node_modules/`, `.next/`, `.next-dev/`
- Browser cookies, private video feeds, or backup folders containing secrets

Review `git status` and staged files before pushing. **Do not share an existing Google OAuth Client Secret if it has been exposed; rotate it.**

If you want other people to legally reuse, modify, and redistribute the code, choose and add a proper `LICENSE` file; a public GitHub repository alone does not grant an open-source license.

---

## ❤️ Help improve OpenShorts

If something breaks, open a GitHub Issue with:

- Your operating system (macOS / Windows / Linux)
- Your Python, Node.js, and FFmpeg versions
- What you clicked and what happened
- The error message **with all secrets and private data removed**

OpenShorts is intended for media you own or have permission to use. Please respect copyrights and the rules of YouTube and other platforms.

**Made for creators who want to build better Shorts, one clip at a time.**
