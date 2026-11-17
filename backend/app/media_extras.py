"""OpenShorts: clip thumbnails, titled exports, project archives and split-screen gameplay.
All routes are user-owned; playback files and tokens never leave the trusted backend.
"""
from __future__ import annotations
import json
import os
import re
import shutil
import subprocess
import tempfile
import unicodedata
import uuid
import zipfile
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Header, BackgroundTasks
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

router = APIRouter(prefix='/api')
M = None
def auth(authorization: Optional[str] = Header(None)):
    return M.current_user(authorization)

KINDS = ('minecraft', 'subway')
ALLOWED = ('.mp4', '.mov', '.mkv', '.webm', '.m4v', '.avi')

def init(module):
    global M
    M = module

def safe_title(s: str, max_length: int = 70) -> str:
    s = unicodedata.normalize('NFKC', s or '')
    s = re.sub(r'[^\w\- .]+', '_', s, flags=re.UNICODE)
    s = re.sub(r'[\s_]+', '_', s).strip('._-')
    return s[:max_length].rstrip('._-') or 'Untitled'

def title_export_path(pid: str, clip: dict, export_id: str) -> Path:
    folder = M.FILES / pid / 'exports'
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{safe_title(clip.get('title', 'Short'))}_{clip['id'][:7]}_{export_id[:8]}.mp4"

def gameplay_path(pid: str, kind: str) -> Optional[Path]:
    if kind not in KINDS:
        return None
    folder = M.FILES / pid / 'gameplay'
    for ext in ALLOWED:
        path = folder / (kind + ext)
        if path.is_file():
            return path
    return None

@router.get('/projects/{pid}/gameplay')
def gameplay_status(pid: str, u=Depends(auth)):
    M.get_project(pid, u['id'])
    return {kind: {'uploaded': bool(path := gameplay_path(pid, kind)), 'filename': path.name if path else None} for kind in KINDS}

@router.post('/projects/{pid}/gameplay/{kind}')
async def gameplay_upload(pid: str, kind: str, file: UploadFile = File(...), u=Depends(auth)):
    M.get_project(pid, u['id'])
    if kind not in KINDS:
        raise HTTPException(422, 'Choose Minecraft or Subway Surfers')
    ext = Path(file.filename or '').suffix.lower()
    if ext not in ALLOWED:
        raise HTTPException(415, 'Choose an MP4, MOV, MKV, WEBM, M4V or AVI gameplay video')
    folder = M.FILES / pid / 'gameplay'
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / f'.{uuid.uuid4().hex}{ext}'
    size = 0
    try:
        with tmp.open('wb') as out:
            while data := await file.read(1024 * 1024):
                size += len(data)
                if size > M.MAX_BYTES:
                    raise HTTPException(413, 'Gameplay exceeds upload size limit')
                out.write(data)
        duration, w, h = M.probe(tmp)
        if duration < 1 or w < 16 or h < 16:
            raise ValueError('Gameplay must contain a valid video track')
        for other in folder.glob(kind + '.*'):
            if other.suffix in ALLOWED:
                other.unlink(missing_ok=True)
        dest = folder / (kind + ext)
        os.replace(tmp, dest)
    except Exception as exc:
        tmp.unlink(missing_ok=True)
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(422, 'Invalid gameplay video: ' + str(exc)[:250])
    return {'kind': kind, 'uploaded': True, 'filename': dest.name, 'duration': round(duration, 2)}

@router.get('/projects/{pid}/gameplay/{kind}/preview')
def gameplay_preview(pid: str, kind: str, u=Depends(auth)):
    M.get_project(pid, u['id'])
    src = gameplay_path(pid, kind)
    if not src:
        raise HTTPException(404, 'Upload a gameplay video first')
    return FileResponse(src, media_type='video/mp4')

def _thumbnail(pid: str, name: str, src: Path, moment: float) -> Path:
    folder = M.FILES / pid / 'thumbnails'
    folder.mkdir(parents=True, exist_ok=True)
    stamp = f'{src.stat().st_size}-{src.stat().st_mtime_ns}'
    import hashlib
    digest = hashlib.sha256((stamp + ':' + str(round(moment, 2))).encode()).hexdigest()[:12]
    dest = folder / f'{name}_{digest}.jpg'
    if dest.is_file() and dest.stat().st_size > 300:
        return dest
    temp = folder / f'.{uuid.uuid4().hex}.jpg'
    try:
        p = subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-ss', str(max(0, moment)), '-i', str(src), '-frames:v', '1', '-vf', 'scale=480:-2:force_original_aspect_ratio=decrease', '-q:v', '4', str(temp)], capture_output=True, text=True, timeout=45)
        if p.returncode or not temp.is_file() or temp.stat().st_size < 300:
            raise RuntimeError(p.stderr[-300:] or 'Thumbnail unavailable')
        os.replace(temp, dest)
    finally:
        temp.unlink(missing_ok=True)
    return dest

@router.get('/projects/{pid}/thumbnail')
def project_thumbnail(pid: str, u=Depends(auth)):
    row = M.get_project(pid, u['id'])
    path = Path(row['media_path']) if row.get('media_path') else None
    if not path or not path.exists():
        raise HTTPException(404, 'No source video')
    try:
        thumbnail = _thumbnail(pid, 'project', path, min(max(0, row.get('duration', 0) * .12), max(0, row.get('duration', 0) - .2)))
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        raise HTTPException(422, str(exc)[:180])
    return FileResponse(thumbnail, media_type='image/jpeg')

@router.get('/projects/{pid}/clips/{clip_id}/thumbnail')
def clip_thumbnail(pid: str, clip_id: str, u=Depends(auth)):
    row = M.get_project(pid, u['id'])
    clip = next((c for c in json.loads(row['clips'] or '[]') if c['id'] == clip_id), None)
    if not clip:
        raise HTTPException(404, 'Clip not found')
    path = Path(row['media_path']) if row.get('media_path') else None
    if not path or not path.exists():
        raise HTTPException(404, 'No source video')
    time = min(float(clip['end']) - 0.05, float(clip['start']) + min(2.0, (float(clip['end'])-float(clip['start'])) / 2))
    try:
        thumbnail = _thumbnail(pid, safe_title(clip_id, 32), path, time)
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        raise HTTPException(422, str(exc)[:180])
    return FileResponse(thumbnail, media_type='image/jpeg')

def _ass_arg(path: Path) -> str:
    escaped = str(path).replace('\\', '\\\\').replace(':', '\\:').replace("'", "\\'").replace(',', '\\,').replace('[','\\[').replace(']','\\]')
    return f"ass=filename='{escaped}'"

def render_split(source: Path, start: float, end: float, clip: dict, subtitle: Optional[Path], dest: Path, pid: str):
    """1080×1920: center-cropped full-bleed main above muted full-bleed gameplay."""
    kind = clip.get('gameplay_kind', 'minecraft')
    game = gameplay_path(pid, kind)
    if not game:
        raise RuntimeError(f'Upload a {kind.title()} gameplay video in Frame → Split Screen before exporting')
    if end <= start:
        raise ValueError('Clip end must be after start')
    duration = float(end - start)
    graph = (
        '[0:v]fps=30,scale=1080:960:force_original_aspect_ratio=increase:flags=lanczos,'
        'crop=1080:960,setsar=1,format=yuv420p[top];'
        '[1:v]fps=30,scale=1080:960:force_original_aspect_ratio=increase:flags=lanczos,'
        'crop=1080:960,setsar=1,format=yuv420p[bottom];'
        '[top][bottom]vstack=inputs=2,format=yuv420p'
    )
    if subtitle:
        graph += ',' + _ass_arg(subtitle)
    graph += '[vout]'
    cmd = ['ffmpeg','-hide_banner','-loglevel','error','-y','-ss',str(start),'-i',str(source), '-stream_loop','-1','-i',str(game), '-filter_complex',graph,'-map','[vout]','-map','0:a?', '-t',str(duration),'-c:v','libx264','-preset','veryfast','-crf','23','-pix_fmt','yuv420p','-c:a','aac','-b:a','160k','-movflags','+faststart',str(dest)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    except subprocess.TimeoutExpired as exc:
        dest.unlink(missing_ok=True)
        raise RuntimeError('Split screen render timed out') from exc
    if proc.returncode:
        dest.unlink(missing_ok=True)
        raise RuntimeError('Split screen rendering failed: ' + proc.stderr[-1400:])
    if not dest.is_file() or dest.stat().st_size < 1000:
        raise RuntimeError('Split screen export produced no MP4')

def _export_all(pid: str, user_id: str):
    try:
        row = M.get_project(pid, user_id)
        clips = json.loads(row['clips'] or '[]')
        errors = []
        for i, clip in enumerate(clips):
            M.update(pid, status='rendering', progress=round(4 + 90 * i / max(1, len(clips))))
            M.render_job(pid, user_id, clip, M.uid())
            latest = M.get_project(pid, user_id)
            if latest['status'] == 'failed':
                errors.append(f"{clip.get('title', clip['id'])}: {latest['error']}")
        M.update(pid, status='failed' if errors else 'ready', progress=100 if not errors else 0,
                 error=(' | '.join(errors))[:650] if errors else None)
    except Exception as exc:
        M.update(pid, status='failed', progress=0, error=('Batch export failed: '+str(exc))[:650])

@router.post('/projects/{pid}/export-all')
def export_all(pid: str, tasks: BackgroundTasks, u=Depends(auth)):
    row = M.get_project(pid, u['id'])
    if row['status'] in ('rendering', 'importing', 'analyzing'):
        raise HTTPException(409, 'Project is already processing')
    if not row.get('media_path') or not Path(row['media_path']).is_file():
        raise HTTPException(409, 'Upload the source video first')
    clips = json.loads(row['clips'] or '[]')
    if not clips:
        raise HTTPException(409, 'Analyze the source to find clips first')
    M.update(pid, status='rendering', progress=1, error=None)
    tasks.add_task(_export_all, pid, u['id'])
    return {'queued': len(clips), 'status': 'rendering'}

@router.get('/projects/{pid}/archive')
def project_archive(pid: str, u=Depends(auth)):
    row = M.get_project(pid, u['id'])
    clips = json.loads(row['clips'] or '[]')
    folder_name = safe_title(row['title'], 60) + '_' + pid[:8]
    folder = M.FILES / pid
    tmp = folder / f'.archive_{uuid.uuid4().hex}.zip'
    with M.connection() as c:
        exports = [dict(x) for x in c.execute('SELECT id,clip_id,path,created_at FROM exports WHERE project_id=? AND user_id=? ORDER BY created_at',(pid, u['id'])).fetchall()]
    metadata = {'project': {'id': pid, 'title': row['title'], 'source_url': row.get('source_url'), 'duration': row['duration'], 'created_at':row['created_at']}, 'clips': clips, 'exports': [{k:x[k] for k in ('id','clip_id','created_at')} for x in exports]}
    try:
        with zipfile.ZipFile(tmp,'w',compression=zipfile.ZIP_STORED,allowZip64=True) as archive:
            archive.writestr(folder_name+'/project.json', json.dumps(metadata,indent=2,ensure_ascii=False))
            archive.writestr(folder_name+'/transcript.json', json.dumps(json.loads(row['transcript'] or '[]'), indent=2,ensure_ascii=False))
            if row.get('media_path') and Path(row['media_path']).is_file():
                src = Path(row['media_path'])
                archive.write(src, folder_name+'/original/'+safe_title(row['title'])+src.suffix)
            for x in exports:
                path = Path(x['path'])
                if path.is_file():
                    clip = next((c for c in clips if c['id']==x['clip_id']), {})
                    filename = f"{safe_title(clip.get('title', path.stem))}_{x['id'][:8]}.mp4"
                    archive.write(path,folder_name+'/clips/'+filename)
            for path in (folder/'gameplay').glob('*') if (folder/'gameplay').is_dir() else []:
                if path.is_file() and path.suffix in ALLOWED:
                    archive.write(path, folder_name+'/gameplay/'+path.name)
            # AI Content Studio: include only generated creative assets (no secrets/tokens).
            for asset in (folder/'creative').rglob('*') if (folder/'creative').is_dir() else []:
                if asset.is_file() and asset.suffix.lower() in ('.jpg', '.json'):
                    archive.write(asset, folder_name+'/'+str(asset.relative_to(folder)))
            # Include only actual clip stills (create lazily if not requested by UI).
            if row.get('media_path') and Path(row['media_path']).is_file():
                source = Path(row['media_path'])
                for clip in clips:
                    try:
                        moment = min(float(clip['end'])-.05, float(clip['start'])+min(2.,(float(clip['end'])-float(clip['start']))/2))
                        still = _thumbnail(pid, safe_title(clip['id'],32), source, moment)
                        archive.write(still, folder_name+'/thumbnails/'+safe_title(clip['title'])+'_'+clip['id'][:8]+'.jpg')
                    except Exception:
                        pass
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    return FileResponse(tmp,media_type='application/zip',filename=folder_name+'.zip',background=BackgroundTask(lambda:tmp.unlink(missing_ok=True)))
