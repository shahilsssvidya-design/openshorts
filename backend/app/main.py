"""OpenShorts 2.0 API — local-first, persistent, no paid dependency required."""
import os, json, re, time, uuid, shutil, sqlite3, hashlib, hmac, secrets, subprocess, threading, traceback, math, tempfile
from pathlib import Path
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
from typing import Optional
import jwt
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, Header, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

BASE = Path(os.getenv('OPENSHORTS_DATA', str(Path(__file__).resolve().parents[2] / 'data'))).resolve()
BASE.mkdir(parents=True, exist_ok=True)
DB = BASE / 'openshorts.db'
FILES = BASE / 'media'; FILES.mkdir(exist_ok=True)
SECRET = os.getenv('SECRET_KEY')
if not SECRET:
    keyfile = BASE / '.jwt-secret'
    if not keyfile.exists():
        keyfile.write_text(secrets.token_urlsafe(48)); keyfile.chmod(0o600)
    SECRET = keyfile.read_text().strip()
MAX_BYTES = int(os.getenv('MAX_UPLOAD_MB', '1024')) * 1024 * 1024
CORS = os.getenv('CORS_ORIGINS', 'http://localhost:3000,http://127.0.0.1:3000').split(',')
app = FastAPI(title='OpenShorts 2.0', version='2.0.0')
app.add_middleware(CORSMiddleware, allow_origins=CORS, allow_credentials=True, allow_methods=['*'], allow_headers=['*'])

@contextmanager
def connection():
    con = sqlite3.connect(DB, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    try:
        yield con
        con.commit()
    finally:
        con.close()

def init_db():
    with connection() as c:
        c.execute('PRAGMA journal_mode=WAL')
        c.executescript('''CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,email TEXT UNIQUE NOT NULL,password TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),title TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'draft',progress INTEGER DEFAULT 0,error TEXT,source TEXT,source_url TEXT,media_path TEXT,duration REAL DEFAULT 0,width INTEGER DEFAULT 0,height INTEGER DEFAULT 0,transcript TEXT DEFAULT '[]',clips TEXT DEFAULT '[]',created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS exports(id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES projects(id),user_id TEXT NOT NULL REFERENCES users(id),clip_id TEXT NOT NULL,path TEXT NOT NULL,created_at TEXT NOT NULL);''')
init_db()

def now(): return datetime.now(timezone.utc).isoformat()
def uid(): return uuid.uuid4().hex
def rowdict(row):
    if not row: return None
    d = dict(row)
    for k in ('transcript','clips'):
        if k in d:
            try: d[k] = json.loads(d[k] or '[]')
            except Exception: d[k] = []
    d.pop('media_path', None)
    return d

def password_hash(password):
    salt = os.urandom(16)
    return salt.hex()+':'+hashlib.pbkdf2_hmac('sha256',password.encode(),salt,260000).hex()
def verify_password(password, saved):
    try:
        salt, digest = saved.split(':')
        return hmac.compare_digest(hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),260000),bytes.fromhex(digest))
    except Exception: return False

def token(user_id): return jwt.encode({'sub':user_id,'exp':datetime.now(timezone.utc)+timedelta(days=14)},SECRET,algorithm='HS256')
def current_user(authorization: Optional[str]=Header(None)):
    try:
        if not authorization or not authorization.startswith('Bearer '): raise ValueError('token required')
        payload=jwt.decode(authorization[7:], SECRET, algorithms=['HS256'])
        with connection() as c: row=c.execute('SELECT id,email,created_at FROM users WHERE id=?',(payload['sub'],)).fetchone()
        if not row: raise ValueError('unknown user')
        return dict(row)
    except Exception: raise HTTPException(401,'Sign in required or session expired')

def get_project(project_id, user_id):
    with connection() as c: row=c.execute('SELECT * FROM projects WHERE id=? AND user_id=?',(project_id,user_id)).fetchone()
    if not row: raise HTTPException(404,'Project not found')
    return dict(row)
def update(pid, **kwargs):
    kwargs['updated_at']=now()
    with connection() as c: c.execute('UPDATE projects SET '+','.join(k+'=?' for k in kwargs)+' WHERE id=?',(*kwargs.values(),pid))

def run(*args, timeout=600):
    p=subprocess.run(list(map(str,args)),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=timeout)
    if p.returncode: raise RuntimeError(p.stderr[-1600:] or f'Command failed: {args[0]}')
    return p.stdout

def probe(path):
    info=json.loads(run('ffprobe','-v','error','-show_entries','format=duration:stream=codec_type,width,height','-of','json',path,timeout=30))
    video=next((s for s in info.get('streams',[]) if s.get('codec_type')=='video'),None)
    if not video: raise ValueError('No video stream detected')
    return float(info.get('format',{}).get('duration') or 0),int(video.get('width') or 0),int(video.get('height') or 0)

class Auth(BaseModel):
    email:str
    password:str
class ProjectCreate(BaseModel):
    title:str=Field(min_length=1,max_length=160)
class URLInput(BaseModel):
    url:str
class ClipEdit(BaseModel):
    start:float=Field(ge=0)
    end:float=Field(gt=0)
    title:str=Field(min_length=1,max_length=160)
    style:str='bold'
    position:str='bottom'
    color:str='#FFFFFF'
    captions:bool=True
    caption_scale:float=Field(default=1,ge=.6,le=1.6)
    gameplay_kind:str='minecraft'
    layout_mode:str='crop'
    top_fill:str='gradient'
    top_color_a:str='#4B2F85'
    top_color_b:str='#171126'
    bottom_fill:str='gradient'
    bottom_color_a:str='#171126'
    bottom_color_b:str='#4B2F85'
    focus_mode:str='auto'
    caption_language:str='original'
    music_track:str='none'
    music_volume:float=Field(default=0.20,ge=0,le=1)
    original_volume:float=Field(default=1.0,ge=0,le=1)
class SettingsPayload(BaseModel):
    title:Optional[str]=None

@app.get('/api/health')
def health(): return {'ok':True,'ffmpeg':bool(shutil.which('ffmpeg')),'ffprobe':bool(shutil.which('ffprobe')),'transcription_available':transcriber_available()}
def transcriber_available():
    try: import faster_whisper; return True
    except ImportError: return False
@app.post('/api/auth/signup')
def signup(data:Auth):
    email=data.email.lower().strip()
    if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+',email): raise HTTPException(422,'Enter a valid email address')
    if len(data.password)<8: raise HTTPException(422,'Password must have at least 8 characters')
    u=uid()
    try:
        with connection() as c: c.execute('INSERT INTO users VALUES(?,?,?,?)',(u,email,password_hash(data.password),now()))
    except sqlite3.IntegrityError: raise HTTPException(409,'Email already registered')
    return {'token':token(u),'user':{'id':u,'email':email}}
@app.post('/api/auth/login')
def login(data:Auth):
    with connection() as c: row=c.execute('SELECT * FROM users WHERE email=?',(data.email.lower().strip(),)).fetchone()
    if not row or not verify_password(data.password,row['password']): raise HTTPException(401,'Invalid email or password')
    return {'token':token(row['id']),'user':{'id':row['id'],'email':row['email']}}
@app.get('/api/auth/me')
def me(u=Depends(current_user)): return u
@app.get('/api/projects')
def projects(u=Depends(current_user)):
    with connection() as c: rows=c.execute('SELECT * FROM projects WHERE user_id=? ORDER BY created_at DESC',(u['id'],)).fetchall()
    return [rowdict(r) for r in rows]
@app.post('/api/projects')
def create_project(data:ProjectCreate,u=Depends(current_user)):
    pid=uid(); date=now()
    with connection() as c: c.execute('INSERT INTO projects(id,user_id,title,status,created_at,updated_at) VALUES(?,?,?,?,?,?)',(pid,u['id'],data.title,'draft',date,date))
    (FILES/pid).mkdir(exist_ok=True)
    return rowdict(get_project(pid,u['id']))
@app.get('/api/projects/{pid}')
def project(pid:str,u=Depends(current_user)): return rowdict(get_project(pid,u['id']))
@app.patch('/api/projects/{pid}')
def patch_project(pid:str,data:SettingsPayload,u=Depends(current_user)):
    get_project(pid,u['id'])
    if data.title is not None:
        if not data.title.strip(): raise HTTPException(422,'Title cannot be empty')
        update(pid,title=data.title.strip()[:160])
    return rowdict(get_project(pid,u['id']))
@app.delete('/api/projects/{pid}')
def delete_project(pid:str,u=Depends(current_user)):
    get_project(pid,u['id'])
    with connection() as c:
        c.execute('DELETE FROM exports WHERE project_id=?',(pid,))
        c.execute('DELETE FROM projects WHERE id=? AND user_id=?',(pid,u['id']))
    shutil.rmtree(FILES/pid,ignore_errors=True)
    return {'deleted':True}

ALLOWED={'.mp4','.mov','.mkv','.webm','.m4v','.avi'}
@app.post('/api/projects/{pid}/upload')
async def upload(pid:str,file:UploadFile=File(...),u=Depends(current_user)):
    get_project(pid,u['id'])
    ext=Path(file.filename or '').suffix.lower()
    if ext not in ALLOWED: raise HTTPException(415,'Upload MP4, MOV, MKV, WEBM, M4V or AVI')
    folder=FILES/pid; folder.mkdir(exist_ok=True)
    dest=folder/('source'+ext)
    size=0
    try:
        with dest.open('wb') as out:
            while chunk:=await file.read(1024*1024):
                size+=len(chunk)
                if size>MAX_BYTES: raise HTTPException(413,'File exceeds maximum configured upload size')
                out.write(chunk)
        duration,w,h=probe(dest)
        if duration<1: raise HTTPException(422,'Video is too short')
    except Exception as e:
        dest.unlink(missing_ok=True)
        if isinstance(e,HTTPException): raise
        raise HTTPException(422,f'Invalid video: {str(e)[:300]}')
    update(pid,media_path=str(dest),source='upload',source_url=None,duration=duration,width=w,height=h,status='uploaded',progress=0,error=None,clips='[]',transcript='[]')
    return rowdict(get_project(pid,u['id']))

YT_PATTERN=re.compile(r'^https?://(?:www\.|m\.)?(?:youtube\.com/(?:watch\?|shorts/|live/)|youtu\.be/)',re.I)
@app.post('/api/projects/{pid}/youtube')
def youtube(pid:str,data:URLInput,tasks:BackgroundTasks,u=Depends(current_user)):
    get_project(pid,u['id'])
    if not YT_PATTERN.match(data.url): raise HTTPException(422,'Enter a YouTube video URL')
    if not shutil.which('yt-dlp'): raise HTTPException(503,'yt-dlp not installed. Run pip install yt-dlp')
    update(pid,status='importing',progress=5,error=None,source='youtube',source_url=data.url)
    tasks.add_task(import_youtube,pid,data.url)
    return {'status':'importing'}
def import_youtube(pid,url):
    try:
        directory=FILES/pid
        run('yt-dlp','--cookies-from-browser','brave','--js-runtimes','node','--no-playlist','--max-filesize','1G','-f','bv*[height<=1080]+ba/b[height<=1080]/b','--merge-output-format','mp4','-o',str(directory/'source.%(ext)s'),url,timeout=1200)
        media=next((p for p in directory.glob('source.*') if p.suffix in ALLOWED),None)
        if not media: raise RuntimeError('No playable video downloaded')
        duration,w,h=probe(media)
        update(pid,status='uploaded',progress=0,media_path=str(media),duration=duration,width=w,height=h)
    except Exception as exc: update(pid,status='failed',error=str(exc)[:500],progress=0)

# Human-readable SRT import is useful without a local speech model.
def parse_srt(raw):
    chunks=[]
    for block in re.split(r'\n\s*\n',raw.replace('\r','')):
        lines=block.strip().splitlines()
        timeline=next((i for i,line in enumerate(lines) if '-->' in line),None)
        if timeline is None: continue
        matches=re.findall(r'(\d\d):(\d\d):(\d\d)[,.](\d+)',lines[timeline])
        if len(matches)!=2: continue
        def stamp(x): return int(x[0])*3600+int(x[1])*60+int(x[2])+int(x[3].ljust(3,'0')[:3])/1000
        start,end=map(stamp,matches)
        txt=re.sub('<[^>]+>','', ' '.join(lines[timeline+1:])).strip()
        if txt and end>start: chunks.append({'start':start,'end':end,'text':txt})
    return chunks
@app.post('/api/projects/{pid}/transcript')
async def transcript_upload(pid:str,file:UploadFile=File(...),u=Depends(current_user)):
    row=get_project(pid,u['id'])
    if not row['media_path']: raise HTTPException(409,'Upload video first')
    raw=(await file.read(2*1024*1024)).decode('utf-8-sig',errors='replace')
    transcript=parse_srt(raw)
    if not transcript: raise HTTPException(422,'No valid SRT subtitle segments found')
    update(pid,transcript=json.dumps(transcript),status='transcribed',progress=60,error=None)
    return {'segments':len(transcript)}

@app.post('/api/projects/{pid}/analyze')
def analyze(pid:str,tasks:BackgroundTasks,u=Depends(current_user)):
    row=get_project(pid,u['id'])
    if not row['media_path']: raise HTTPException(409,'Add a video first')
    if row['status'] in ('analyzing','rendering','importing'): raise HTTPException(409,'Already processing')
    update(pid,status='analyzing',progress=3,error=None)
    tasks.add_task(analyze_job,pid)
    return {'status':'analyzing'}

def ensure_transcript(pid,path):
    with connection() as c: row=c.execute('SELECT transcript,duration FROM projects WHERE id=?',(pid,)).fetchone()
    existing=json.loads(row['transcript'] or '[]')
    if existing: return existing
    update(pid,progress=16)
    # Whisper is optional and runs fully locally. Model downloads on first use.
    if transcriber_available():
        from faster_whisper import WhisperModel
        model_name=os.getenv('WHISPER_MODEL','tiny')
        model=WhisperModel(model_name,device='cpu',compute_type='int8',cpu_threads=4)
        segments,_=model.transcribe(str(path),beam_size=2,word_timestamps=True,vad_filter=True)
        transcript=[]
        for s in segments:
            words=[{'start':round(w.start,2),'end':round(w.end,2),'text':w.word.strip()} for w in (s.words or [])]
            transcript.append({'start':round(s.start,2),'end':round(s.end,2),'text':s.text.strip(),'words':words})
        if transcript:
            update(pid,transcript=json.dumps(transcript))
            return transcript
    # Search subtitles embedded in user-provided video; never invent transcript.
    subs=FILES/pid/'embedded.srt'
    try:
        run('ffmpeg','-y','-i',str(path),'-map','0:s:0',str(subs),timeout=120)
        found=parse_srt(subs.read_text(errors='replace'))
        if found:
            update(pid,transcript=json.dumps(found))
            return found
    except Exception: pass
    raise RuntimeError('No transcript available. Install faster-whisper (pip install faster-whisper), or upload an SRT transcript in the workspace.')

HOOK_WORDS={'how','why','secret','never','best','mistake','truth','actually','imagine','discover','surprising','important','first','million','easy','learn','warning','stop','powerful','crazy','nobody','biggest','proven'}
def rank_clips(transcript,duration):
    """Rank complete speech moments, adding setup and keeping natural clip boundaries.

    Produces 30-120 second clips where video length permits. No cloud model is
    required; this is a better timestamp heuristic, not semantic AI understanding.
    """
    if not transcript or duration <= 0:
        return []
    segments = sorted((s for s in transcript if s.get('text') and float(s.get('end', 0)) > float(s.get('start', 0))),
                      key=lambda x: float(x['start']))
    if not segments:
        return []

    MIN_LENGTH, MAX_LENGTH = 30.0, 120.0
    # Broad hook vocabulary (including romanized Hindi); keyword scoring is only a hint.
    cues = set(HOOK_WORDS) | {'but', 'because', 'however', 'problem', 'result', 'instead', 'finally',
                             'lekin', 'kyunki', 'kaise', 'kyu', 'kyun', 'dekho', 'suno', 'pata', 'galti'}
    candidates = []
    import bisect
    starts = [float(s['start']) for s in segments]

    def bounded_window(core_idx, target):
        """Capture the setup BEFORE a hook and extend through its concluding thought."""
        anchor = segments[core_idx]
        a = float(anchor['start'])
        # Return to the beginning of the preceding thought (up to ~15 seconds).
        earliest = max(0.0, a - 16.0)
        begin_idx = core_idx
        while begin_idx > 0:
            previous = segments[begin_idx - 1]
            gap = float(segments[begin_idx]['start']) - float(previous['end'])
            if float(previous['start']) < earliest or gap > 2.8:
                break
            begin_idx -= 1
        start = max(0.0, float(segments[begin_idx]['start']) - 1.8)
        # The required length is never longer than the source itself.
        min_needed = min(MIN_LENGTH, float(duration))
        if duration - start < min_needed:
            start = max(0.0, duration - min_needed)
        desired_end = min(duration, start + target)
        minimum_end = min(duration, start + min_needed)
        # Pick an actual transcript boundary closest to desired duration, within 120s.
        possible = []
        for s in segments[core_idx:]:
            endpoint = min(float(duration), float(s['end']) + .65)
            if endpoint < minimum_end - .05:
                continue
            if endpoint > start + MAX_LENGTH + .05:
                break
            text = s['text'].rstrip()
            closing = 4 if text.endswith(('.', '!', '?', '।', '॥')) else 0
            possible.append((abs(endpoint - desired_end) - closing, endpoint))
        end = min(possible, key=lambda t: t[0])[1] if possible else min(duration, start + MAX_LENGTH)
        if end - start < min_needed - .05:
            end = min(duration, start + min_needed)
        if end - start > MAX_LENGTH:
            end = start + MAX_LENGTH
        return round(start, 2), round(end, 2)

    # Evaluate hook anchors throughout the entire video, not only early segments.
    # Skip dense successive anchors to reduce duplicate candidate windows.
    for i, seg in enumerate(segments):
        if float(seg['start']) >= duration - 5:
            continue
        for target in (40.0, 65.0, 90.0, 115.0):
            start, end = bounded_window(i, target)
            if end - start < min(MIN_LENGTH, duration) - .05:
                continue
            window = [s for s in segments if float(s['start']) < end and float(s['end']) > start]
            if not window:
                continue
            speech = ' '.join(s['text'].strip() for s in window)
            words = re.findall(r"\b[\w']+\b", speech.lower())
            if len(words) < 10:
                continue
            hook_words = re.findall(r"\b[\w']+\b", str(seg['text']).lower())
            hook_score = sum(1 for w in hook_words if w in cues)
            density = len(words) / max(1.0, end - start)
            # Reward speech continuity, expressive punctuation, and segment-local hooks.
            score = round(min(99, 35 + min(23, density * 6) + min(22, hook_score * 8)
                              + min(10, speech.count('?') * 3 + speech.count('!') * 2)
                              + min(9, len(words) / 25)), 1)
            title_words = str(seg['text']).strip().split()[:10]
            title = (' '.join(title_words).strip(' ,.?!।').capitalize() or 'Highlighted moment')[:78]
            candidates.append({'start': start, 'end': end, 'score': score,
                               'title': title,
                               'hook': str(seg['text'])[:160],
                               'description': speech[:280],
                               'reason': f'Complete moment with lead-in • {round(end-start)} seconds',
                               'style': 'bold', 'position': 'bottom', 'color': '#FFFFFF',
                               'caption_scale': 1, 'captions': True})

    candidates.sort(key=lambda c: (-c['score'], c['start']))
    selected = []
    for item in candidates:
        # Overlap measured against the shorter clip; avoids showing the same moment repeatedly.
        if all(max(0.0, min(item['end'], x['end']) - max(item['start'], x['start'])) <
               .35 * min(item['end'] - item['start'], x['end'] - x['start']) for x in selected):
            item['id'] = uid()[:12]
            selected.append(item)
        if len(selected) >= 12:
            break
    return selected

def analyze_job(pid):
    try:
        with connection() as c: row=c.execute('SELECT media_path,duration FROM projects WHERE id=?',(pid,)).fetchone()
        transcript=ensure_transcript(pid,row['media_path'])
        update(pid,progress=74)
        from .moment_intelligence import choose_moments
        clips=choose_moments(transcript,float(row['duration']),fallback_ranker=rank_clips,
                             progress=lambda value: update(pid,progress=value))
        for clip in clips:
            clip['id']=uid()[:12]
        if not clips: raise RuntimeError('No usable speech segments for clips')
        update(pid,clips=json.dumps(clips),status='ready',progress=100,error=None)
    except Exception as e: update(pid,status='failed',error=str(e)[:650],progress=0)

@app.patch('/api/projects/{pid}/clips/{clip_id}')
def edit_clip(pid:str,clip_id:str,data:ClipEdit,u=Depends(current_user)):
    row=get_project(pid,u['id']); clips=json.loads(row['clips'] or '[]')
    item=next((x for x in clips if x['id']==clip_id),None)
    if not item: raise HTTPException(404,'Clip not found')
    if data.end<=data.start or data.end>row['duration']+.1: raise HTTPException(422,'Invalid trim interval')
    if data.style not in ('bold','minimal','outline','highlight'): raise HTTPException(422,'Unknown caption style')
    if data.position not in ('bottom','middle','top'): raise HTTPException(422,'Unknown caption position')
    if data.focus_mode not in ('auto','center','left','right'): raise HTTPException(422,'Unknown focus mode')
    if data.gameplay_kind not in ('minecraft','subway'): raise HTTPException(422,'Invalid gameplay choice')
    if data.caption_language not in ('original','hinglish','english'): raise HTTPException(422,'Unknown caption language')
    if not re.fullmatch(r'#[a-fA-F0-9]{6}',data.color): raise HTTPException(422,'Invalid hex color')
    from .fit_layout import validate_style
    try: validate_style(data.model_dump())
    except ValueError as exc: raise HTTPException(422,str(exc))
    try: os_music.validate_settings(data.music_track, data.music_volume, data.original_volume)
    except ValueError as exc: raise HTTPException(422,str(exc))
    item.update(data.model_dump()); update(pid,clips=json.dumps(clips))
    return item

# ASS subtitles: per-word karaoke animation; when ASR supplies word timings we respect them.
def ass_color(hexcolor): return '&H'+hexcolor[5:7]+hexcolor[3:5]+hexcolor[1:3]+'&'
def ass_escape(s): return s.replace('\\','').replace('{','').replace('}','').replace('\n',' ')
def make_ass(pid,clip,transcript):
    from .english_captions import translate_phrases
    from .hinglish import romanize
    start,end=clip['start'],clip['end']
    style=clip.get('style','bold'); fontsize=round(65*clip.get('caption_scale',1))
    fontsize=max(32,min(110,fontsize))
    outline=4 if style in ('bold','outline') else 2
    shadow=2 if style=='bold' else 0
    primary=ass_color(clip.get('color','#FFFFFF'))
    secondary='&H00E8A447&' if style=='highlight' else primary
    alignment={'bottom':2,'middle':5,'top':8}.get(clip.get('position'),2)
    header=f'''[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nWrapStyle: 2\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Default,Arial,{fontsize},{primary},{secondary},&H00101010&,&H80000000&,-1,0,0,0,100,100,0,0,1,{outline},{shadow},{alignment},70,70,230,1\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n'''
    def ts(t):
        t=max(0,t); return f'{int(t//3600)}:{int(t//60)%60:02d}:{int(t)%60:02d}.{int((t%1)*100):02d}'
    mode=clip.get('caption_language','original')
    groups=[]
    for seg in transcript:
        ss=max(start,float(seg['start'])); ee=min(end,float(seg['end']))
        if ee<=ss: continue
        words=[w for w in seg.get('words',[]) if float(w['end'])>start and float(w['start'])<end]
        if not words:
            tokens=seg['text'].split()
            if not tokens: continue
            delta=(float(seg['end'])-float(seg['start']))/len(tokens)
            words=[{'start':float(seg['start'])+i*delta,'end':float(seg['start'])+(i+1)*delta,'text':w} for i,w in enumerate(tokens)]
        for j in range(0,len(words),4):
            group=words[j:j+4]
            gs=max(start,float(group[0]['start']))
            ge=min(end,float(group[-1]['end']))
            if ge<=gs: continue
            groups.append((gs,ge,group))
    english=[]
    if mode=='english':
        english=translate_phrases([' '.join(w['text'] for w in group) for _,_,group in groups])
    events=[]
    for i,(gs,ge,group) in enumerate(groups):
        if mode=='english':
            # Translation changes word count. Spread highlighted output words
            # across the original phrase duration (approximate, not forced alignment).
            out_words=english[i].split()
            total_cs=max(1,round((ge-gs)*100))
            base=max(1,total_cs//max(1,len(out_words)))
            kara=''.join('{\\kf'+str(base)+'}'+ass_escape(w.upper())+' ' for w in out_words).strip()
        else:
            kara=' '.join('{\\kf'+str(max(1,round((float(w['end'])-float(w['start']))*100)))+'}'+ass_escape((romanize(w['text']) if mode=='hinglish' else w['text']).upper()) for w in group)
        events.append(f'Dialogue: 0,{ts(gs-start)},{ts(ge-start)},Default,,0,0,0,,{kara}')
    path=FILES/pid/(f'{clip["id"]}.ass'); path.write_text(header+'\n'.join(events),encoding='utf-8')
    return path

def face_center(path,start):
    """Best-effort face center from a sampled frame; safe fallback to centered crop."""
    try:
        import cv2
        cap=cv2.VideoCapture(str(path)); cap.set(cv2.CAP_PROP_POS_MSEC,(start+1)*1000)
        ok,frame=cap.read(); cap.release()
        if not ok: return .5
        cascade=cv2.CascadeClassifier(cv2.data.haarcascades+'haarcascade_frontalface_default.xml')
        gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
        faces=cascade.detectMultiScale(gray,1.15,5,minSize=(35,35))
        if len(faces):
            x,y,w,h=sorted(faces,key=lambda f:f[2]*f[3],reverse=True)[0]
            return max(.15,min(.85,(x+w/2)/frame.shape[1]))
    except Exception: pass
    return .5

@app.post('/api/projects/{pid}/clips/{clip_id}/export')
def export(pid:str,clip_id:str,tasks:BackgroundTasks,u=Depends(current_user)):
    row=get_project(pid,u['id']); clip=next((x for x in json.loads(row['clips'] or '[]') if x['id']==clip_id),None)
    if not clip: raise HTTPException(404,'Clip not found')
    if row['status']=='rendering': raise HTTPException(409,'Rendering another clip')
    export_id=uid()
    update(pid,status='rendering',progress=5,error=None)
    tasks.add_task(render_job,pid,u['id'],clip,export_id)
    return {'export_id':export_id,'status':'rendering'}

def render_job(pid,user_id,clip,export_id):
    from .smart_crop import crop_filter
    try:
        with connection() as c: row=c.execute('SELECT media_path,transcript,width,height FROM projects WHERE id=?',(pid,)).fetchone()
        path=Path(row['media_path'])
        if not path.is_file(): raise RuntimeError('Source video is missing')
        start,end=clip['start'],clip['end']
        if clip.get('layout_mode','crop') == 'split':
            update(pid, progress=25)
            ass=make_ass(pid,clip,json.loads(row['transcript'] or '[]')) if clip.get('captions',True) else None
            dest=media_extras.title_export_path(pid,clip,export_id)
            update(pid, progress=45)
            media_extras.render_split(path,start,end,clip,ass,dest,pid)
            os_music.apply_music_to_export(pid,clip,dest)
            with connection() as c: c.execute('INSERT INTO exports VALUES(?,?,?,?,?,?)',(export_id,pid,user_id,clip['id'],str(dest),now()))
            update(pid,status='ready',progress=100,error=None)
            return
        if clip.get('layout_mode','crop') == 'fit':
            from .fit_layout import render_fit
            update(pid,progress=25)
            ass=make_ass(pid,clip,json.loads(row['transcript'] or '[]')) if clip.get('captions',True) else None
            dest=media_extras.title_export_path(pid,clip,export_id)
            update(pid,progress=45)
            render_fit(path,start,end,clip,ass,dest,row['width'],row['height'])
            os_music.apply_music_to_export(pid,clip,dest)
            with connection() as c: c.execute('INSERT INTO exports VALUES(?,?,?,?,?,?)',(export_id,pid,user_id,clip['id'],str(dest),now()))
            update(pid,status='ready',progress=100,error=None)
            return
        w,h=row['width'],row['height']
        vf=crop_filter(path,start,end,w,h,clip.get('focus_mode','auto'))
        update(pid,progress=25)
        if clip.get('captions',True):
            ass=make_ass(pid,clip,json.loads(row['transcript'] or '[]'))
            # escape path per ffmpeg filter syntax
            escaped=str(ass).replace('\\','\\\\').replace(':','\\:').replace("'","\\'").replace(',','\\,')
            vf+=f",ass=filename='{escaped}'"
        dest=media_extras.title_export_path(pid,clip,export_id)
        update(pid,progress=45)
        run('ffmpeg','-hide_banner','-loglevel','error','-y','-ss',start,'-i',path,'-t',end-start,'-vf',vf,'-c:v','libx264','-preset','veryfast','-crf','23','-pix_fmt','yuv420p','-c:a','aac','-b:a','160k','-movflags','+faststart',dest,timeout=1800)
        if not dest.exists() or dest.stat().st_size<1000: raise RuntimeError('MP4 render did not produce a usable file')
        os_music.apply_music_to_export(pid,clip,dest)
        with connection() as c: c.execute('INSERT INTO exports VALUES(?,?,?,?,?,?)',(export_id,pid,user_id,clip['id'],str(dest),now()))
        update(pid,status='ready',progress=100,error=None)
    except Exception as exc: update(pid,status='failed',progress=0,error=str(exc)[:650])

@app.get('/api/projects/{pid}/source')
def source(pid:str,u=Depends(current_user)):
    row=get_project(pid,u['id'])
    if not row['media_path'] or not Path(row['media_path']).exists(): raise HTTPException(404,'Source not found')
    return FileResponse(row['media_path'],media_type='video/mp4')
@app.get('/api/projects/{pid}/exports')
def exports(pid:str,u=Depends(current_user)):
    get_project(pid,u['id'])
    with connection() as c: rows=c.execute('SELECT id,clip_id,created_at FROM exports WHERE project_id=? AND user_id=? ORDER BY created_at DESC',(pid,u['id'])).fetchall()
    return [dict(r) for r in rows]
@app.get('/api/exports/{eid}/download')
def download(eid:str,u=Depends(current_user)):
    with connection() as c: row=c.execute('SELECT * FROM exports WHERE id=? AND user_id=?',(eid,u['id'])).fetchone()
    if not row or not Path(row['path']).exists(): raise HTTPException(404,'Export not found')
    return FileResponse(row['path'],media_type='video/mp4',filename=Path(row['path']).name)

# OpenShorts Live Highlights Upgrade
from app.live import router as live_router, init as live_init
live_init()
app.include_router(live_router)

# OpenShorts YouTube Publisher Upgrade
import sys
from app.youtube_publish import init as youtube_publish_init, router as youtube_publish_router
youtube_publish_init(sys.modules[__name__])
app.include_router(youtube_publish_router)

# OpenShorts automatic channel monitor (durable)
from app import channel_monitor
app.include_router(channel_monitor.router)

@app.on_event("startup")
def channel_monitor_start():
    channel_monitor.start()

@app.on_event("shutdown")
def channel_monitor_stop():
    channel_monitor.shutdown()

# OpenShorts Media Extras Upgrade — thumbnail, folder ZIP and gameplay routes.
import sys as _os_sys
from app import media_extras
media_extras.init(_os_sys.modules[__name__])
app.include_router(media_extras.router)

# OpenShorts AI Content Studio — grounded Ollama packaging + real-frame thumbnails.
import sys as _os_creative_sys
from app import creative_ai
creative_ai.init(_os_creative_sys.modules[__name__])
app.include_router(creative_ai.router)

# OpenShorts AI Metadata Fix: optional project-wide Qwen enrichment.
from app import ai_metadata as _os_ai_metadata
_os_ai_metadata.init(__import__(__name__, fromlist=['app']))
app.include_router(_os_ai_metadata.router)

# OpenShorts Background Music Upgrade — authenticated library + original demos.
import sys as _os_music_sys
from app import music as os_music
os_music.init(_os_music_sys.modules[__name__])
app.include_router(os_music.router)
