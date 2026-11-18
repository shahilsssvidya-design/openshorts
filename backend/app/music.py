"""OpenShorts music library and non-destructive audio-only export mixing.

Three original sample WAVs ship with this module. Custom audio is project-scoped.
No paid APIs, third-party songs, or external downloads are required.
"""
from __future__ import annotations

import json
import mimetypes
import os
import subprocess
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse

router = APIRouter(prefix='/api')
M = None

PRESETS = {
    'night-drive': {'id': 'night-drive', 'name': 'Night Drive', 'mood': 'Cinematic synth / steady energy', 'bpm': 108},
    'bright-bounce': {'id': 'bright-bounce', 'name': 'Bright Bounce', 'mood': 'Upbeat / playful', 'bpm': 120},
    'soft-focus': {'id': 'soft-focus', 'name': 'Soft Focus', 'mood': 'Warm ambient / calm', 'bpm': 90},
}
SUPPORTED = {'.mp3', '.wav', '.m4a', '.aac', '.flac', '.ogg', '.opus', '.wma'}
MAX_MUSIC_BYTES = 60 * 1024 * 1024
DEMO_PATH = Path(__file__).with_name('demo_music')


def init(main):
    global M
    M = main


def auth(authorization: Optional[str] = Header(None)):
    return M.current_user(authorization)


def validate_settings(track, volume, original_volume):
    if track != 'none' and track != 'custom' and not (isinstance(track, str) and track.startswith('demo:') and track[5:] in PRESETS):
        raise ValueError('Choose No music, a built-in demo track, or your uploaded track')
    if not (0 <= volume <= 1):
        raise ValueError('Music volume must be between 0 and 100%')
    if not (0 <= original_volume <= 1):
        raise ValueError('Original audio volume must be between 0 and 100%')


def uploaded_music(pid: str) -> Optional[Path]:
    folder = M.FILES / pid / 'music'
    for p in folder.iterdir() if folder.is_dir() else ():
        if p.is_file() and p.stem == 'custom' and p.suffix.lower() in SUPPORTED:
            return p
    return None


def choose_music(pid: str, track: str) -> Optional[Path]:
    if track == 'none':
        return None
    if track == 'custom':
        music = uploaded_music(pid)
        if not music:
            raise RuntimeError('Upload your background music in the Music tab before exporting')
        return music
    if track.startswith('demo:') and track[5:] in PRESETS:
        music = DEMO_PATH / f'{track[5:]}.wav'
        if music.is_file():
            return music
        raise RuntimeError('Built-in demo track was not installed. Re-run the Background Music installer')
    raise RuntimeError('Unknown music selection')


def _audio_info(path: Path):
    result = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type:format=duration', '-of', 'json', str(path)],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode:
        raise ValueError('ffprobe could not read this audio file')
    data = json.loads(result.stdout)
    if not any(s.get('codec_type') == 'audio' for s in data.get('streams', [])):
        raise ValueError('File has no audio track')
    duration = float(data.get('format', {}).get('duration') or 0)
    if not 0.1 <= duration <= 2 * 3600:
        raise ValueError('Music duration must be between 0.1 seconds and 2 hours')
    return duration


@router.get('/music/presets')
def list_presets(u=Depends(auth)):
    return list(PRESETS.values())


@router.get('/music/presets/{track_id}/audio')
def preview_preset(track_id: str, u=Depends(auth)):
    if track_id not in PRESETS:
        raise HTTPException(404, 'Demo track not found')
    path = DEMO_PATH / (track_id + '.wav')
    if not path.is_file():
        raise HTTPException(503, 'Demo music file missing from this installation')
    return FileResponse(path, media_type='audio/wav')


@router.get('/projects/{pid}/music')
def music_status(pid: str, u=Depends(auth)):
    M.get_project(pid, u['id'])
    p = uploaded_music(pid)
    meta = M.FILES / pid / 'music' / 'name.json'
    display = None
    if meta.is_file():
        try:
            display = json.loads(meta.read_text()).get('filename')
        except (ValueError, OSError):
            pass
    return {'uploaded': bool(p), 'filename': display or (p.name if p else None)}


@router.post('/projects/{pid}/music')
async def upload_music(pid: str, file: UploadFile = File(...), u=Depends(auth)):
    M.get_project(pid, u['id'])
    suffix = Path(file.filename or '').suffix.lower()
    if suffix not in SUPPORTED:
        raise HTTPException(415, 'Upload MP3, WAV, M4A, AAC, FLAC, OGG, OPUS, or WMA audio')
    folder = M.FILES / pid / 'music'
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / ('.upload-' + uuid.uuid4().hex + suffix)
    total = 0
    try:
        with tmp.open('wb') as out:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_MUSIC_BYTES:
                    raise HTTPException(413, 'Music file exceeds the 60 MB upload limit')
                out.write(chunk)
        seconds = _audio_info(tmp)
        dest = folder / ('custom' + suffix)
        os.replace(tmp, dest)
        for other in folder.glob('custom.*'):
            if other != dest and other.suffix.lower() in SUPPORTED:
                other.unlink(missing_ok=True)
        display = Path(file.filename or 'My music').name[:140]
        (folder / 'name.json').write_text(json.dumps({'filename': display}), encoding='utf-8')
        return {'uploaded': True, 'filename': display, 'duration': round(seconds, 2)}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(422, 'Could not read music file: ' + str(exc)[:180])
    finally:
        tmp.unlink(missing_ok=True)
        await file.close()


@router.get('/projects/{pid}/music/audio')
def preview_upload(pid: str, u=Depends(auth)):
    M.get_project(pid, u['id'])
    p = uploaded_music(pid)
    if not p:
        raise HTTPException(404, 'Upload a music file first')
    return FileResponse(p, media_type=mimetypes.guess_type(p.name)[0] or 'application/octet-stream')


def apply_music_to_export(pid: str, clip: dict, exported_path: Path):
    """Remux rendered MP4 with a music mix, video copied bit-for-bit.

    Called once for every layout after the main video render and before saving
    the export DB row. The gameplay source remains muted in the split renderer.
    """
    track = clip.get('music_track', 'none') or 'none'
    music_volume = float(clip.get('music_volume', 0.20))
    source_volume = float(clip.get('original_volume', 1.0))
    validate_settings(track, music_volume, source_volume)
    if track == 'none' and source_volume == 1:
        return
    music = choose_music(pid, track)
    if not exported_path.is_file():
        raise RuntimeError('Cannot mix music: the video render is missing')

    ffinfo = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type:format=duration', '-of', 'json', str(exported_path)],
        capture_output=True, text=True, timeout=30,
    )
    if ffinfo.returncode:
        raise RuntimeError('Could not inspect rendered video for audio mixing')
    info = json.loads(ffinfo.stdout)
    has_audio = any(x.get('codec_type') == 'audio' for x in info.get('streams', []))
    duration = float(info.get('format', {}).get('duration') or (float(clip['end']) - float(clip['start'])))
    if duration <= 0:
        raise RuntimeError('Cannot mix audio into an empty video')
    if not music and not has_audio:
        return

    tmp = exported_path.with_name('.music-' + uuid.uuid4().hex + '.mp4')
    command = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', str(exported_path)]
    if music:
        command.extend(['-stream_loop', '-1', '-i', str(music)])
    if music and music_volume > 0:
        fade_duration = min(0.75, duration / 3)
        fade_start = max(0, duration - fade_duration)
        bg = f'[1:a:0]volume={music_volume:.3f},atrim=duration={duration:.4f},afade=t=out:st={fade_start:.4f}:d={fade_duration:.4f}[bg]'
        if has_audio:
            graph = (f'[0:a:0]volume={source_volume:.3f}[voice];' + bg +
                     ';[voice][bg]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,alimiter=limit=0.96[aout]')
        else:
            graph = bg + ';[bg]alimiter=limit=0.96[aout]'
    elif has_audio:
        graph = f'[0:a:0]volume={source_volume:.3f}[aout]'
    else:
        return
    command.extend(['-filter_complex', graph, '-map', '0:v:0', '-map', '[aout]', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '160k', '-t', f'{duration:.4f}', '-movflags', '+faststart', str(tmp)])
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=600)
        if result.returncode or not tmp.is_file() or tmp.stat().st_size < 1000:
            raise RuntimeError('Music mixing failed: ' + (result.stderr[-1000:] if result.stderr else 'no audio output'))
        os.replace(tmp, exported_path)
    finally:
        tmp.unlink(missing_ok=True)
