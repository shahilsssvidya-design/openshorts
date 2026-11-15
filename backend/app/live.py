"""OpenShorts Live Highlights (local development beta).

A single owner-authorized YouTube live source is sampled at the live edge into
bounded recordings. Each recorded segment becomes a normal OpenShorts project,
so existing captions, framing, trimming, export and retention workflows apply.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app import main as m

router = APIRouter(prefix='/api/live', tags=['Live highlights'])
STOP = {}
THREADS = {}

class NotLiveYet(RuntimeError):
    pass
LOCK = threading.Lock()


def init():
    with m.connection() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS live_sessions (
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
            url TEXT NOT NULL, label TEXT NOT NULL,
            state TEXT NOT NULL, message TEXT NOT NULL DEFAULT '',
            chunks INTEGER NOT NULL DEFAULT 0, project_ids TEXT NOT NULL DEFAULT '[]',
            auto_export INTEGER NOT NULL DEFAULT 1,
            started_at TEXT NOT NULL, updated_at TEXT NOT NULL
        )''')
        # OpenShorts YouTube auto-publish integration
        columns = {r['name'] for r in c.execute('PRAGMA table_info(live_sessions)')}
        if 'auto_publish' not in columns:
            c.execute('ALTER TABLE live_sessions ADD COLUMN auto_publish INTEGER NOT NULL DEFAULT 0')
        if 'auto_publish_count' not in columns:
            c.execute('ALTER TABLE live_sessions ADD COLUMN auto_publish_count INTEGER NOT NULL DEFAULT 0')
        if 'made_for_kids' not in columns:
            c.execute('ALTER TABLE live_sessions ADD COLUMN made_for_kids INTEGER')
        c.execute("UPDATE live_sessions SET state='stopped', message='Interrupted by server restart; start a new session' WHERE state IN ('starting','waiting','recording','analyzing')")


def validate_url(url: str) -> str:
    """Restrict user-supplied inputs to direct YouTube live/video or channel live URLs."""
    try: parsed = urlparse(url.strip())
    except Exception: raise ValueError('Invalid URL')
    domain = (parsed.hostname or '').lower().rstrip('.')
    if parsed.scheme != 'https' or domain not in ('youtube.com', 'www.youtube.com', 'm.youtube.com', 'youtu.be'):
        raise ValueError('Use a valid https://www.youtube.com/live/... or /@channel/live URL')
    if parsed.username or parsed.password or parsed.port or parsed.fragment:
        raise ValueError('Unsupported YouTube URL')
    path = parsed.path
    if not (path.startswith('/watch') or path.startswith('/live/') or path.startswith('/@') and path.endswith('/live') or domain == 'youtu.be' and len(path) > 1):
        raise ValueError('Paste a YouTube live video URL or a channel /live URL')
    if len(url) > 350: raise ValueError('URL too long')
    return url.strip()


def update_session(sid, **fields):
    fields['updated_at'] = m.now()
    with m.connection() as c:
        c.execute('UPDATE live_sessions SET ' + ', '.join(f'{k}=?' for k in fields) + ' WHERE id=?', (*fields.values(),sid))


def session(sid, user):
    with m.connection() as c:
        row = c.execute('SELECT * FROM live_sessions WHERE id=? AND user_id=?',(sid,user)).fetchone()
    if not row: raise HTTPException(404,'Live session not found')
    result = dict(row)
    result['project_ids'] = json.loads(result['project_ids'])
    return result


def executable():
    return [sys.executable, '-m', 'yt_dlp']


def downloader_args():
    args = executable() + ['--no-playlist','--no-warnings','--js-runtimes','node']
    browser = os.getenv('OPENSHORTS_LIVE_COOKIE_BROWSER','').strip().lower()
    if browser:
        if browser not in ('brave','chrome','firefox','safari'):
            raise RuntimeError('Invalid OPENSHORTS_LIVE_COOKIE_BROWSER')
        args += ['--cookies-from-browser',browser]
    return args


def resolve_sources(url):
    """Use public/authorized video format URLs; never log them (they can be signed)."""
    command = downloader_args() + ['-f','bv*[height<=720]+ba/b[height<=720]','--print','%(live_status)s','--get-url',url]
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=65)
    except subprocess.TimeoutExpired:
        raise RuntimeError('YouTube source lookup timed out')
    if proc.returncode:
        msg = proc.stderr or ''
        if 'Sign in to confirm' in msg or 'LOGIN_REQUIRED' in msg:
            raise RuntimeError('YouTube requires account verification. Check your local permitted browser configuration or use a direct upload.')
        if (urlparse(url).path.startswith('/@') and ('not live' in msg.lower() or 'not currently live' in msg.lower() or 'video unavailable' in msg.lower())) or 'will begin in' in msg.lower():
            raise NotLiveYet('The channel has not started streaming')
        raise RuntimeError('Cannot access live stream; confirm it is live and you have permission. ' + re.sub(r'https?://\S+', '[URL]',msg)[-220:])
    if 'is_live' not in proc.stdout.splitlines():
        raise NotLiveYet('Channel is not live yet')
    urls = [line.strip() for line in proc.stdout.splitlines() if line.strip().startswith('https://')]
    if not 1 <= len(urls) <= 2:
        raise RuntimeError('Could not find usable live video/audio formats')
    return urls


def record_chunk(urls, output: Path, seconds: int, stop: threading.Event):
    """Record bounded media at the live edge, avoiding an endless downloader process."""
    args = ['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y']
    for src in urls:
        args.extend(['-rw_timeout','20000000','-i',src])
    args += ['-map','0:v:0']
    args += ['-map','1:a:0' if len(urls)>1 else '0:a:0?']
    args += ['-t',str(seconds),'-c','copy',str(output)]
    proc = subprocess.Popen(args,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    deadline=time.monotonic()+seconds+100
    try:
        while proc.poll() is None:
            if stop.is_set():
                proc.terminate()
                try: proc.wait(timeout=8)
                except subprocess.TimeoutExpired: proc.kill()
                return False
            if time.monotonic()>deadline:
                proc.kill()
                raise RuntimeError('Live capture exceeded the expected time window')
            time.sleep(.5)
        stderr = proc.stderr.read().decode('utf8', errors='replace')[-240:]
        if proc.returncode:
            raise RuntimeError('FFmpeg live capture failed. ' + re.sub(r'https?://\S+','[URL]',stderr))
        return True
    finally:
        if proc.poll() is None: proc.kill()
        if proc.stderr: proc.stderr.close()


def ai_candidates(segments, duration):
    """Use local Ollama if available, with a conservative transcript-only fallback."""
    if not segments: return []
    transcript = '\n'.join(f"[{float(s['start']):.1f}-{float(s['end']):.1f}] {s['text']}" for s in segments)[:11000]
    instruction = (
        '/no_think\nYou are a short-form editor. Find up to 3 genuinely noteworthy moments: '
        'funny reversals, a surprising claim, a compelling hook, an emotional reaction, '
        'a strong explanation or a payoff. Never invent dialogue or events. '
        'Include the setup BEFORE the important moment and a natural ending. '
        'Use only times within the provided recording. Each clip should be 30 to 120 seconds, '
        'except clips near the end of a shorter recording. Avoid mundane filler. '
        'Return ONLY JSON as {"clips":[{"start":number,"end":number,"score":number,'
        '"title":string,"reason":string}]} where score is 0-100. '
        'If nothing stands out return {"clips":[]}.\n'
        f'Recording duration: {duration:.1f} seconds\nTRANSCRIPT:\n{transcript}'
    )
    model_ok=False
    try:
        body = json.dumps({'model':os.getenv('OLLAMA_MODEL','qwen3:4b'), 'prompt':instruction,
                           'stream':False, 'format':'json', 'options':{'temperature':0.2,'num_predict':650}}).encode()
        req = urllib.request.Request('http://127.0.0.1:11434/api/generate',data=body,
                                     headers={'Content-Type':'application/json'},method='POST')
        with urllib.request.urlopen(req,timeout=95) as resp:
            data=json.loads(resp.read(100000))
        raw=json.loads(data.get('response','{}'))
        candidates=raw.get('clips',[])
        model_ok=isinstance(candidates,list)
    except (ValueError,KeyError,urllib.error.URLError,TimeoutError, OSError):
        candidates=[]
    results=[]
    for candidate in candidates[:5]:
        try:
            start=max(0,float(candidate['start'])-7)  # context buffer
            end=min(duration,float(candidate['end'])+3)
            if end-start<30 and duration>=30:
                start=max(0,min(start,duration-30))
                end=min(duration,start+30)
            if end-start>120: end=start+120
            if end-start<12: continue
            score=max(0,min(100,float(candidate.get('score',50))))
            if score<70: continue
            title=str(candidate.get('title','Live moment')).strip()[:78]
            results.append({'id':m.uid()[:12],'start':round(start,2),'end':round(end,2),
                'score':round(score,1),'title':title or 'Live moment',
                'hook':title,'description':str(candidate.get('reason',''))[:240],
                'reason':'Ollama transcript review: '+str(candidate.get('reason',''))[:130],
                'captions':True,'style':'bold','position':'bottom','color':'#FFFFFF','caption_scale':1})
        except (TypeError,ValueError,KeyError): continue
    # If AI is unreachable, fall back to the upgraded rank_clips (if installed).
    if not results and not model_ok:
        ranked = m.rank_clips(segments,duration)
        results = [c for c in ranked if c['end']-c['start']>=30][:3]
        for clip in results: clip['reason']='Transcript-based fallback · '+str(clip.get('reason',''))
    return results[:3]


def process_recording(session_id, user_id, path, number):
    length,w,h = m.probe(path)
    if length<22: raise RuntimeError('Stream recording too short to analyze')
    pid = m.uid(); ts = m.now()
    target = m.FILES / pid
    target.mkdir(parents=True,exist_ok=True)
    dest=target/'source.mkv'
    shutil.move(str(path),str(dest))
    with m.connection() as c:
        c.execute("""INSERT INTO projects(id,user_id,title,status,progress,source,source_url,media_path,duration,width,height,transcript,clips,created_at,updated_at)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
          (pid,user_id,f'Live capture #{number}', 'analyzing',10,'live',None,str(dest),length,w,h,'[]','[]',ts,ts))
    transcript = m.ensure_transcript(pid,str(dest))
    clips=ai_candidates(transcript,length)
    if not clips:
        m.update(pid,status='ready',progress=100,error=None,clips='[]')
    else:
        m.update(pid,status='ready',progress=100,error=None,clips=json.dumps(clips))
    return pid,len(clips)


def worker(sid,user_id,url,chunk_seconds,auto_export,stop):
    from shutil import rmtree
    folder = m.BASE/'live_chunks'/sid
    folder.mkdir(parents=True,exist_ok=True)
    with m.connection() as c:
        live_row=c.execute('SELECT auto_publish,made_for_kids FROM live_sessions WHERE id=?',(sid,)).fetchone()
    auto_publish=bool(live_row['auto_publish']) if live_row else False
    made_for_kids=bool(live_row['made_for_kids']) if live_row and live_row['made_for_kids'] is not None else None
    num=0; failures=0; posted=0
    try:
        while not stop.is_set() and num < 20:
            try:
                update_session(sid,state='recording',message='Checking stream and recording next live segment')
                sources=resolve_sources(url)
                path=folder/f'chunk-{num+1:04d}.mkv'
                if not record_chunk(sources,path,chunk_seconds,stop): break
                update_session(sid,state='analyzing',message=f'Transcribing and finding highlights in capture #{num+1}')
                pid,count=process_recording(sid,user_id,path,num+1)
                with m.connection() as c:
                    row=c.execute('SELECT project_ids FROM live_sessions WHERE id=?',(sid,)).fetchone()
                    ids=json.loads(row['project_ids'])
                ids.append(pid)
                num+=1; failures=0
                if count and auto_export:
                    with m.connection() as c:
                        clips=json.loads(c.execute('SELECT clips FROM projects WHERE id=?',(pid,)).fetchone()['clips'])
                    m.update(pid,status='rendering',progress=15)
                    m.render_job(pid,user_id,clips[0],m.uid())
                    if auto_publish and posted < 3 and not stop.is_set():
                        from app.youtube_publish import publish_private_auto
                        with m.connection() as c:
                            exp=c.execute('SELECT id FROM exports WHERE project_id=? AND user_id=? ORDER BY created_at DESC LIMIT 1',(pid,user_id)).fetchone()
                        if exp:
                            try:
                                result=publish_private_auto(exp['id'],user_id,clips[0]['title'],clips[0].get('description',''),bool(made_for_kids))
                                if result['status']=='published':
                                    posted += 1
                                    update_session(sid,auto_publish_count=posted)
                                else:
                                    update_session(sid,message='Auto-upload failed: '+str(result['error'])[:140])
                            except Exception as ex:
                                update_session(sid,message='Auto-upload failed: '+str(ex)[:140])
                update_session(sid,chunks=num,project_ids=json.dumps(ids),message=f'Capture #{num} analyzed · {count} suggested highlights' + (' · Auto-export attempted' if count and auto_export else ''))
            except NotLiveYet:
                update_session(sid,state='waiting',message='Channel is offline. Checking again in 45 seconds.')
                if stop.wait(45): break
                continue
            except Exception as exc:
                failures+=1
                update_session(sid,message=f'Capture attempt {failures} failed: {str(exc)[:175]}')
                if failures>=3: raise
                if stop.wait(12): break
    except Exception as exc:
        update_session(sid,state='failed',message=str(exc)[:300])
    finally:
        with m.connection() as c:
            row=c.execute('SELECT state FROM live_sessions WHERE id=?',(sid,)).fetchone()
        if row and row['state']!='failed':
            update_session(sid,state='stopped',message=('Reached the 20-capture safety limit. Start a new session to continue.' if num>=20 else 'Stopped. Captured projects remain available.'))
        with LOCK:
            THREADS.pop(sid,None)
            STOP.pop(sid,None)
        rmtree(folder,ignore_errors=True)


class StartLive(BaseModel):
    url:str=Field(min_length=10,max_length=350)
    label:str=Field(default='My livestream',min_length=1,max_length=100)
    chunk_seconds:int=Field(default=120,ge=60,le=120)
    auto_export:bool=True
    auto_publish:bool=False
    made_for_kids:bool | None=None
    rights_confirmed:bool=False

@router.post('')
def start_live(data:StartLive,u=Depends(m.current_user)):
    if data.auto_publish:
        if not data.auto_export or data.made_for_kids is None or not data.rights_confirmed:
            raise HTTPException(422,'Private auto-publish requires Auto export, audience choice, and confirmed rights')
        from app.youtube_publish import _oauth_ready, _load_creds
        if not _oauth_ready() or not _load_creds(u['id']):
            raise HTTPException(409,'Connect your YouTube account from Account & API before enabling auto-publish')
    try: url = validate_url(data.url)
    except ValueError as e: raise HTTPException(422,str(e))
    if not m.transcriber_available():
        raise HTTPException(503,'Install faster-whisper in backend/.venv before starting live analysis')
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        raise HTTPException(503,'FFmpeg/FFprobe is required for live capture')
    if not os.getenv('OPENSHORTS_LIVE_RECORDING_ENABLED','').lower() in ('1','true','yes'):
        raise HTTPException(503,'Live recording is disabled. Set OPENSHORTS_LIVE_RECORDING_ENABLED=1 on your trusted local backend')
    with LOCK:
        if THREADS:
            raise HTTPException(409,'One live channel at a time on this Mac. Stop the existing session first.')
        sid = m.uid()
        with m.connection() as c:
            c.execute('''INSERT INTO live_sessions(id,user_id,url,label,state,message,auto_export,auto_publish,made_for_kids,started_at,updated_at)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?)''',(sid,u['id'],url,data.label.strip(),'starting','Preparing capture',int(data.auto_export),int(data.auto_publish),int(data.made_for_kids) if data.made_for_kids is not None else None,m.now(),m.now()))
        stop=threading.Event()
        thread=threading.Thread(target=worker,args=(sid,u['id'],url,data.chunk_seconds,data.auto_export,stop),daemon=True,name=f'live-{sid[:7]}')
        STOP[sid]=stop
        THREADS[sid]=thread
        thread.start()
    return session(sid,u['id'])

@router.get('')
def list_live(u=Depends(m.current_user)):
    with m.connection() as c:
        rows=c.execute('SELECT id FROM live_sessions WHERE user_id=? ORDER BY started_at DESC LIMIT 20',(u['id'],)).fetchall()
    return [session(r['id'],u['id']) for r in rows]

@router.get('/{sid}')
def get_live(sid:str,u=Depends(m.current_user)):
    return session(sid,u['id'])

@router.post('/{sid}/stop')
def stop_live(sid:str,u=Depends(m.current_user)):
    found=session(sid,u['id'])
    with LOCK:
        ev=STOP.get(sid)
        if ev: ev.set()
    if found['state'] not in ('stopped','failed'):
        update_session(sid,message='Stop requested; finishing current operation')
    return session(sid,u['id'])
