"""OpenShorts automatic authorized-channel monitoring.

YouTube Data API detects public live broadcasts; an authorized media source
(yt-dlp when accessible, or an explicitly configured creator-provided URL)
feeds local bounded recordings, which become ordinary OpenShorts projects.

This is deliberately a single-machine local worker, NOT a public SaaS queue.
"""
from __future__ import annotations

import json
import os
import queue
import re
import shutil
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app import main as m

router = APIRouter(prefix='/api/channel-watches', tags=['Automatic channel monitor'])
_lock = threading.RLock()
_stop = threading.Event()
_thread: Optional[threading.Thread] = None
_capture_threads: dict[str, threading.Thread] = {}
_capture_stops: dict[str, threading.Event] = {}

# New search.list quota documentation currently defaults to 100 calls/day.
# 20-minute checks consume at most 72 checks/day per monitored channel.
DEFAULT_POLL_SECONDS = 20 * 60
FAST_POLL_SECONDS = 120  # Best-effort public channel feed + low-cost videos.list
SEGMENT_SECONDS = 180
MAX_ACTIVE_WATCHES = 1  # local M2 and modest API quota


class DiscoveryError(RuntimeError):
    pass


class CaptureDenied(RuntimeError):
    pass


def init_db():
    with m.connection() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS channel_watches (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id),
            channel_input TEXT NOT NULL,
            channel_id TEXT NOT NULL,
            channel_title TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            state TEXT NOT NULL DEFAULT 'waiting',
            message TEXT NOT NULL DEFAULT '',
            source_mode TEXT NOT NULL DEFAULT 'youtube',
            auto_export INTEGER NOT NULL DEFAULT 0,
            last_video_id TEXT NOT NULL DEFAULT '',
            blocked_video_id TEXT NOT NULL DEFAULT '',
            segments INTEGER NOT NULL DEFAULT 0,
            dropped_segments INTEGER NOT NULL DEFAULT 0,
            project_ids TEXT NOT NULL DEFAULT '[]',
            next_check INTEGER NOT NULL DEFAULT 0,
            next_fast_check INTEGER NOT NULL DEFAULT 0,
            last_checked INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )''')
        columns={x['name'] for x in db.execute('PRAGMA table_info(channel_watches)')}
        if 'next_fast_check' not in columns:
            db.execute('ALTER TABLE channel_watches ADD COLUMN next_fast_check INTEGER NOT NULL DEFAULT 0')
        # A killed FFmpeg or Python process may leave a stale state. Do not
        # disable the watch: the scheduler resumes it after backend restart.
        db.execute("UPDATE channel_watches SET state='waiting', message='Monitor resumed after server restart', next_check=0 WHERE enabled=1 AND state IN ('capturing','processing','checking')")


def _row(wid: str, uid: str):
    with m.connection() as db:
        r = db.execute('SELECT * FROM channel_watches WHERE id=? AND user_id=?',(wid,uid)).fetchone()
    if not r:
        raise HTTPException(404,'Channel watch not found')
    return dict(r)


def _public(row: dict):
    out = dict(row)
    out['project_ids'] = json.loads(out.get('project_ids') or '[]')
    for fld in ('enabled','auto_export'):
        out[fld] = bool(out[fld])
    return out


def _update(wid: str, **values):
    if not values:
        return
    allowed = {'channel_id','channel_title','enabled','state','message','source_mode',
               'auto_export','last_video_id','blocked_video_id','segments',
               'dropped_segments','project_ids','next_check','next_fast_check','last_checked'}
    if set(values)-allowed:
        raise ValueError('Unsupported watch field')
    values['updated_at'] = m.now()
    with m.connection() as db:
        db.execute('UPDATE channel_watches SET '+', '.join(f'{k}=?' for k in values)+' WHERE id=?',(*values.values(),wid))


def _api_key():
    return os.getenv('OPENSHORTS_YOUTUBE_API_KEY','').strip()


def _google(path: str, params: dict):
    key = _api_key()
    if not key:
        raise DiscoveryError('Add OPENSHORTS_YOUTUBE_API_KEY to backend/.channel-monitor.env and restart OpenShorts')
    query = urllib.parse.urlencode({**params, 'key':key})
    url = 'https://www.googleapis.com/youtube/v3/'+path+'?'+query
    try:
        with urllib.request.urlopen(url, timeout=12) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        if exc.code in (401,403):
            raise DiscoveryError('YouTube Data API rejected the API key or its quota/permissions. Check Google Cloud API restrictions and quotas.')
        raise DiscoveryError(f'YouTube Data API returned HTTP {exc.code}')
    except (urllib.error.URLError,TimeoutError,OSError,ValueError) as exc:
        raise DiscoveryError('Unable to contact the YouTube Data API') from exc


def parse_channel(value: str):
    """Return (kind, id) for an actual channel, handle or video link."""
    raw = value.strip()
    if re.fullmatch(r'UC[a-zA-Z0-9_-]{22}',raw):
        return 'id',raw
    if re.fullmatch(r'@[a-zA-Z0-9._-]{3,40}',raw):
        return 'handle',raw
    p = urllib.parse.urlparse(raw)
    if p.scheme != 'https' or p.hostname not in ('www.youtube.com','youtube.com','m.youtube.com','youtu.be') or p.username or p.password or p.port:
        raise ValueError('Paste a YouTube @handle, /channel/ URL, or public livestream link')
    path = p.path.rstrip('/')
    if re.fullmatch(r'/channel/UC[a-zA-Z0-9_-]{22}',path):
        return 'id',path.split('/')[-1]
    if re.fullmatch(r'/@[a-zA-Z0-9._-]{3,40}(?:/live)?',path):
        return 'handle',path.split('/')[1]
    if p.hostname == 'youtu.be' and re.fullmatch(r'/[a-zA-Z0-9_-]{11}',path):
        return 'video',path[1:]
    if path == '/watch':
        video_id = urllib.parse.parse_qs(p.query).get('v',[''])[0]
        if re.fullmatch(r'[A-Za-z0-9_-]{11}',video_id):
            return 'video',video_id
    if re.fullmatch(r'/live/[A-Za-z0-9_-]{11}',path):
        return 'video',path.split('/')[-1]
    raise ValueError('Use a channel handle, channel URL or livestream video URL')


def resolve_channel(value: str):
    kind, key = parse_channel(value)
    if kind == 'id':
        data = _google('channels',{'part':'snippet','id':key,'maxResults':1})
    elif kind == 'handle':
        data = _google('channels',{'part':'snippet','forHandle':key,'maxResults':1})
    else:
        video = _google('videos',{'part':'snippet','id':key,'maxResults':1})
        items = video.get('items') or []
        if not items:
            raise ValueError('Video not found or not publicly available')
        ch_id = items[0].get('snippet',{}).get('channelId')
        if not ch_id:
            raise ValueError('Could not identify the creator channel')
        data = _google('channels',{'part':'snippet','id':ch_id,'maxResults':1})
    items = data.get('items') or []
    if not items:
        raise ValueError('Channel not found. Check the handle/URL and that it is public.')
    channel = items[0]
    return channel['id'],channel.get('snippet',{}).get('title','YouTube channel')[:120]


def detect_live(channel_id: str):
    """Use official API for *detection*; this API does not provide video media."""
    result = _google('search',{
        'part':'snippet','channelId':channel_id,'eventType':'live','type':'video',
        'order':'date','maxResults':5})
    for item in result.get('items') or []:
        vid = (item.get('id') or {}).get('videoId','')
        if re.fullmatch(r'[A-Za-z0-9_-]{11}',vid):
            return vid
    return None


def detect_live_fast(channel_id: str):
    """Best-effort RSS discovery; livestreams aren't guaranteed to appear in RSS.

    Recheck the latest 8 RSS video IDs with videos.list (one API unit) rather
    than using an expensive public search call every two minutes.
    """
    endpoint='https://www.youtube.com/feeds/videos.xml?channel_id='+urllib.parse.quote(channel_id)
    try:
        with urllib.request.urlopen(urllib.request.Request(endpoint,headers={'User-Agent':'OpenShorts/2.0 channel monitor'}),timeout=8) as resp:
            raw=resp.read(220000)
        root=ET.fromstring(raw)
        ids=[]
        for element in root.findall('.//{http://www.youtube.com/xml/schemas/2015}videoId'):
            if element.text and re.fullmatch(r'[A-Za-z0-9_-]{11}',element.text):
                if element.text not in ids:ids.append(element.text)
            if len(ids)>=8:break
        if not ids:return None
        videos=_google('videos',{'part':'snippet,liveStreamingDetails','id':','.join(ids),'maxResults':8})
        for video in videos.get('items') or []:
            info=video.get('snippet',{})
            live=video.get('liveStreamingDetails',{})
            if info.get('liveBroadcastContent')=='live' or live.get('actualStartTime') and not live.get('actualEndTime'):
                return video.get('id')
    except (urllib.error.URLError,ET.ParseError,ValueError,TimeoutError,OSError,DiscoveryError):
        # RSS may be delayed or unavailable; the 20-minute official search
        # remains the primary authoritative fallback.
        return None
    return None


def _record_source(watch: dict, video_id: str):
    """Media from the creator's authorized feed or yt-dlp when actually permitted."""
    from app import live
    mode = watch['source_mode']
    if mode == 'direct':
        feed = os.getenv('OPENSHORTS_AUTHORIZED_FEED_URL','').strip()
        parsed = urllib.parse.urlparse(feed)
        if parsed.scheme != 'https' or not parsed.netloc or parsed.username or parsed.password or parsed.fragment:
            raise CaptureDenied('Set a creator-provided https:// HLS feed in OPENSHORTS_AUTHORIZED_FEED_URL. Never paste feed credentials into the website.')
        # Intended for a single trusted local instance. Never return/log feed URL.
        return [feed]
    if mode == 'youtube':
        video_url = 'https://www.youtube.com/watch?v='+video_id
        try:
            return live.resolve_sources(video_url)
        except Exception as exc:
            raise CaptureDenied('YouTube playback/capture was rejected. Detection works, but you need an accessible authorized feed or an importable recording. '+str(exc)[:100]) from exc
    raise CaptureDenied('Unsupported capture mode')


def _disk_ok():
    min_free = int(os.getenv('OPENSHORTS_WATCH_MIN_FREE_GB','8')) * 1024**3
    return shutil.disk_usage(m.BASE).free >= min_free


def _process(wid: str, owner: str, number: int, media: Path, auto_export: bool):
    from app import live
    pid,count = live.process_recording(wid,owner,media,number)
    with m.connection() as db:
        row = db.execute('SELECT project_ids,segments FROM channel_watches WHERE id=?',(wid,)).fetchone()
    if row:
        ids = json.loads(row['project_ids'] or '[]')
        ids.append(pid)
        total=int(row['segments'])+1
        _update(wid,segments=total,project_ids=json.dumps(ids[-200:]),
                message=f'Capture {number}: {count} suggested moments; {total} total projects saved')
    if count and auto_export:
        with m.connection() as db:
            project = db.execute('SELECT clips FROM projects WHERE id=?',(pid,)).fetchone()
        clips = json.loads(project['clips'] or '[]') if project else []
        if clips:
            m.update(pid,status='rendering',progress=15)
            m.render_job(pid,owner,clips[0],m.uid())
    return pid,count


def _processor(wid: str, owner: str, jobs: queue.Queue, stop: threading.Event, auto_export: bool):
    while True:
        try:
            task = jobs.get(timeout=1)
        except queue.Empty:
            if stop.is_set():
                return
            continue
        if task is None:
            jobs.task_done()
            return
        number, path = task
        try:
            _process(wid,owner,number,path,auto_export)
        except Exception as exc:
            _update(wid,message=f'Capture {number} processing failed: {str(exc)[:180]}')
            path.unlink(missing_ok=True)
        finally:
            jobs.task_done()


def _capture(watch: dict, video_id: str, cancel: threading.Event):
    from app import live
    wid=watch['id']
    folder=m.BASE/'channel_chunks'/wid
    folder.mkdir(parents=True,exist_ok=True)
    jobs=queue.Queue(maxsize=2)
    consumer=threading.Thread(target=_processor,args=(wid,watch['user_id'],jobs,cancel,bool(watch['auto_export'])),daemon=True)
    consumer.start()
    max_segments=min(max(1,int(os.getenv('OPENSHORTS_WATCH_MAX_SEGMENTS','120'))),120)
    number=int(watch['segments'])
    denied=False
    try:
        for _ in range(max_segments):
            if cancel.is_set(): break
            if not _disk_ok():
                _update(wid,state='blocked',message='Low disk space: capture paused to protect your Mac')
                denied=True;break
            try:
                urls=_record_source(watch,video_id)
                path=folder/f'capture-{number+1:04d}-{int(time.time())}.mkv'
                _update(wid,state='capturing',message=f'Livestream detected. Recording segment #{number+1}; AI processes completed segments in parallel.')
                ok=live.record_chunk(urls,path,SEGMENT_SECONDS,cancel)
                if not ok: break
                if not path.is_file() or path.stat().st_size<4096:
                    raise RuntimeError('Recording empty or incomplete')
                number+=1
                try:
                    jobs.put_nowait((number,path))
                except queue.Full:
                    path.unlink(missing_ok=True)
                    _update(wid,dropped_segments=int(watch['dropped_segments'])+1,
                            message='Your Mac is processing slower than the livestream; skipped a recording window')
                    watch['dropped_segments']+=1
            except CaptureDenied as exc:
                _update(wid,state='blocked',blocked_video_id=video_id,message=str(exc)[:260])
                denied=True
                break
            except Exception as exc:
                _update(wid,state='blocked',blocked_video_id=video_id,
                        message='Stream capture failed: '+str(exc)[:190])
                denied=True
                break
        if not cancel.is_set() and not denied and number:
            _update(wid,message='Capture window limit reached; waiting for this stream to end')
    finally:
        # Finish queued media before returning; no repeated downloader retry storm.
        try:
            jobs.put(None,timeout=5)
        except queue.Full:
            # The processing worker will eventually drain the queue.
            while consumer.is_alive():
                try:
                    jobs.put(None,timeout=2);break
                except queue.Full:continue
        consumer.join(timeout=240)
        # Do not delete queued recordings if processor is still working.
        with _lock:
            _capture_threads.pop(wid,None)
            _capture_stops.pop(wid,None)
        if cancel.is_set():
            _update(wid,state='paused',message='Monitoring paused; completed projects are preserved')
        elif not denied:
            _update(wid,state='waiting',message='Stream segment limit reached. Monitoring continues for the next broadcast.',
                    blocked_video_id=video_id,next_check=int(time.time())+DEFAULT_POLL_SECONDS)


def check_fast(row: dict, now_ts: Optional[int]=None):
    now_ts=int(time.time()) if now_ts is None else now_ts
    _update(row['id'],next_fast_check=now_ts+FAST_POLL_SECONDS)
    video_id=detect_live_fast(row['channel_id'])
    if video_id and video_id != row.get('blocked_video_id'):
        # Reuse the same capture-start logic but avoid another search API call.
        _start_detected(row,video_id)


def _start_detected(row: dict, video_id: str):
    wid=row['id']
    _update(wid,last_video_id=video_id)
    if video_id==row.get('blocked_video_id'):
        _update(wid,state='blocked',message='This broadcast was already handled or its capture was blocked. Retry after fixing access, or wait for the next broadcast.')
        return
    with _lock:
        if any(t.is_alive() for t in _capture_threads.values()):
            _update(wid,state='waiting',message='Another authorized stream is being captured on this Mac')
            return
        cancel=threading.Event()
        thread=threading.Thread(target=_capture,args=(row,video_id,cancel),name=f'channel-capture-{wid[:7]}',daemon=True)
        _capture_stops[wid]=cancel
        _capture_threads[wid]=thread
        thread.start()


def check_one(row: dict, now_ts: Optional[int]=None):
    now_ts = int(time.time()) if now_ts is None else now_ts
    wid=row['id']
    _update(wid,state='checking',message='Checking YouTube for an active livestream',last_checked=now_ts,
            next_check=now_ts+DEFAULT_POLL_SECONDS)
    try:
        video_id=detect_live(row['channel_id'])
    except DiscoveryError as exc:
        _update(wid,state='error',message=str(exc)[:260],next_check=now_ts+3600)
        return
    if not video_id:
        _update(wid,state='waiting',message='Channel is offline. Automatic monitoring continues.',last_video_id='')
        return
    _start_detected(row,video_id)


def tick():
    """Run one synchronous monitoring pass; exported for deterministic tests."""
    with m.connection() as db:
        rows=[dict(r) for r in db.execute('SELECT * FROM channel_watches WHERE enabled=1 ORDER BY created_at LIMIT ?', (MAX_ACTIVE_WATCHES,))]
    now_ts=int(time.time())
    for row in rows:
        with _lock:
            thread=_capture_threads.get(row['id'])
            if thread and thread.is_alive():
                continue
        if row['next_check'] <= now_ts:
            check_one(row,now_ts)
        elif row['next_fast_check'] <= now_ts:
            check_fast(row,now_ts)


def _run():
    while not _stop.wait(4):
        try:
            tick()
        except Exception:
            # Never allow an unexpected parsing/DB error to kill the scheduler.
            pass


def start():
    global _thread
    init_db()
    if os.getenv('OPENSHORTS_LIVE_RECORDING_ENABLED','').lower() not in ('1','true','yes'):
        return
    with _lock:
        if _thread and _thread.is_alive():return
        _stop.clear()
        _thread=threading.Thread(target=_run,name='channel-auto-monitor',daemon=True)
        _thread.start()


def shutdown():
    _stop.set()
    with _lock:
        for ev in _capture_stops.values():ev.set()
    if _thread:_thread.join(timeout=4)


class WatchCreate(BaseModel):
    channel: str = Field(min_length=3,max_length=300)
    source_mode: str = Field(default='youtube',pattern='^(youtube|direct)$')
    auto_export: bool = False
    rights_confirmed: bool = False


@router.get('/config')
def config(user=Depends(m.current_user)):
    return {'recording_enabled':os.getenv('OPENSHORTS_LIVE_RECORDING_ENABLED','').lower() in ('1','true','yes'),
            'discovery_api_configured':bool(_api_key()),
            'direct_feed_configured':bool(os.getenv('OPENSHORTS_AUTHORIZED_FEED_URL','').strip()),
            'poll_minutes':DEFAULT_POLL_SECONDS//60,'fast_poll_minutes':FAST_POLL_SECONDS//60,'segment_seconds':SEGMENT_SECONDS,
            'maximum_active_channels':MAX_ACTIVE_WATCHES}


@router.get('')
def watches(user=Depends(m.current_user)):
    with m.connection() as db:
        rows=db.execute('SELECT * FROM channel_watches WHERE user_id=? ORDER BY created_at DESC',(user['id'],)).fetchall()
    return [_public(dict(x)) for x in rows]


@router.post('',status_code=201)
def create_watch(data:WatchCreate,user=Depends(m.current_user)):
    if not data.rights_confirmed:
        raise HTTPException(422,'Confirm you have the right to record and republish this channel')
    if os.getenv('OPENSHORTS_LIVE_RECORDING_ENABLED','').lower() not in ('1','true','yes'):
        raise HTTPException(503,'Set OPENSHORTS_LIVE_RECORDING_ENABLED=1 on your trusted local backend first')
    if not _api_key():
        raise HTTPException(503,'Configure OPENSHORTS_YOUTUBE_API_KEY in backend/.channel-monitor.env first')
    if data.source_mode == 'direct' and not os.getenv('OPENSHORTS_AUTHORIZED_FEED_URL','').strip():
        raise HTTPException(422,'Configure OPENSHORTS_AUTHORIZED_FEED_URL on the backend before selecting direct feed')
    with m.connection() as db:
        count=db.execute('SELECT count(*) FROM channel_watches WHERE enabled=1').fetchone()[0]
        if count >= MAX_ACTIVE_WATCHES:
            raise HTTPException(409,'This local beta monitors one channel at a time. Pause the previous watch first.')
    try:
        ch_id, ch_title=resolve_channel(data.channel)
    except ValueError as exc:
        raise HTTPException(422,str(exc))
    except DiscoveryError as exc:
        raise HTTPException(503,str(exc))
    wid=m.uid();ts=m.now()
    with m.connection() as db:
        db.execute('''INSERT INTO channel_watches
        (id,user_id,channel_input,channel_id,channel_title,source_mode,auto_export,created_at,updated_at,message)
        VALUES(?,?,?,?,?,?,?,?,?,?)''',
        (wid,user['id'],data.channel,ch_id,ch_title,data.source_mode,int(data.auto_export),ts,ts,'Saved. Checking the channel automatically.'))
    return _public(_row(wid,user['id']))


@router.post('/{wid}/pause')
def pause(wid:str,user=Depends(m.current_user)):
    _row(wid,user['id'])
    with _lock:
        ev=_capture_stops.get(wid)
        if ev: ev.set()
    _update(wid,enabled=0,state='paused',message='Pausing monitoring; any active recording will stop')
    return _public(_row(wid,user['id']))


@router.post('/{wid}/resume')
def resume(wid:str,user=Depends(m.current_user)):
    _row(wid,user['id'])
    with m.connection() as db:
        count=db.execute('SELECT count(*) FROM channel_watches WHERE enabled=1 AND id!=?',(wid,)).fetchone()[0]
    if count >= MAX_ACTIVE_WATCHES:
        raise HTTPException(409,'Pause the active channel before resuming this one')
    _update(wid,enabled=1,state='waiting',message='Monitoring resumed; checking shortly',next_check=0,blocked_video_id='')
    return _public(_row(wid,user['id']))


@router.post('/{wid}/check')
def check_now(wid:str,user=Depends(m.current_user)):
    row=_row(wid,user['id'])
    if not row['enabled']:raise HTTPException(409,'Resume monitoring before checking')
    with _lock:
        t=_capture_threads.get(wid)
        if t and t.is_alive():
            return _public(row)
    # Force a near-term check via scheduler (do not block API requests).
    _update(wid,next_check=0,blocked_video_id='')
    return _public(_row(wid,user['id']))


@router.delete('/{wid}')
def delete(wid:str,user=Depends(m.current_user)):
    _row(wid,user['id'])
    with _lock:
        ev=_capture_stops.get(wid)
        if ev:ev.set()
    with m.connection() as db:
        db.execute('DELETE FROM channel_watches WHERE id=? AND user_id=?',(wid,user['id']))
    return {'deleted':True,'projects_preserved':True}
