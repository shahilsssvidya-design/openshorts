"""OpenShorts YouTube publishing integration.

Local-first OAuth (Google web client), per-user encrypted tokens, and official
YouTube Data API v3 resumable uploads. This module MUST run only on a trusted
backend. Never store OAuth tokens in the browser or expose its secret files.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode, urlparse

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Header, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

router = APIRouter(prefix='/api/youtube', tags=['YouTube Publisher'])
AUTH_ENDPOINT = 'https://accounts.google.com/o/oauth2/v2/auth'
TOKEN_ENDPOINT = 'https://oauth2.googleapis.com/token'
UPLOAD_ENDPOINT = 'https://www.googleapis.com/upload/youtube/v3/videos'
SCOPE = 'https://www.googleapis.com/auth/youtube.upload'
CHUNK_SIZE = 8 * 1024 * 1024  # YouTube chunk boundaries must be multiples of 256 KiB

# Set by init() after import from app.main, avoiding circular imports.
_core = None


def _now():
    return datetime.now(timezone.utc).isoformat()


def _config():
    client = os.getenv('OPENSHORTS_YOUTUBE_CLIENT_ID', '').strip()
    secret = os.getenv('OPENSHORTS_YOUTUBE_CLIENT_SECRET', '').strip()
    callback = os.getenv('OPENSHORTS_YOUTUBE_CALLBACK', 'http://localhost:8000/api/youtube/oauth/callback').strip()
    frontend = os.getenv('OPENSHORTS_FRONTEND_URL', 'http://localhost:3000').rstrip('/')
    if not callback.startswith('http://localhost:') and not callback.startswith('http://127.0.0.1:') and not callback.startswith('https://'):
        raise RuntimeError('YouTube callback must use HTTPS, or localhost for local development')
    return client, secret, callback, frontend


def _oauth_ready():
    c, s, _, _ = _config()
    return bool(c and s)


def _fernet():
    # Encryption key stays local and outside ZIP; chmod 0600 on macOS.
    folder = _core.BASE
    file = folder / '.youtube-fernet-key'
    if not file.exists():
        fd = os.open(file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            with os.fdopen(fd, 'wb') as f:
                f.write(Fernet.generate_key())
        except BaseException:
            file.unlink(missing_ok=True)
            raise
    return Fernet(file.read_bytes())


def init(core):
    global _core
    _core = core
    with _core.connection() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS yt_oauth_pending (
          state TEXT PRIMARY KEY, user_id TEXT NOT NULL, code_verifier TEXT NOT NULL,
          expires_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS yt_accounts (
          user_id TEXT PRIMARY KEY, encrypted_token BLOB NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS yt_uploads (
          id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
          export_id TEXT NOT NULL, title TEXT NOT NULL, description TEXT NOT NULL,
          privacy TEXT NOT NULL, made_for_kids INTEGER NOT NULL,
          status TEXT NOT NULL, progress INTEGER NOT NULL DEFAULT 0,
          video_id TEXT, error TEXT,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_yt_uploads_owner_export ON yt_uploads(user_id, export_id);
        ''')


def _load_creds(user_id):
    with _core.connection() as db:
        row = db.execute('SELECT encrypted_token FROM yt_accounts WHERE user_id=?', (user_id,)).fetchone()
    if not row:
        return None
    try:
        return json.loads(_fernet().decrypt(row['encrypted_token']).decode())
    except (ValueError, InvalidToken):
        raise RuntimeError('Saved YouTube authorization could not be decrypted; reconnect your account')


def _save_creds(user_id, tokens):
    encrypted = _fernet().encrypt(json.dumps(tokens).encode())
    with _core.connection() as db:
        db.execute('INSERT OR REPLACE INTO yt_accounts VALUES(?,?,?)', (user_id, encrypted, _now()))


def _update_upload(upload_id, **columns):
    columns['updated_at'] = _now()
    with _core.connection() as db:
        db.execute('UPDATE yt_uploads SET ' + ','.join(f'{k}=?' for k in columns) + ' WHERE id=?', (*columns.values(), upload_id))


def _get_upload(upload_id, user_id):
    with _core.connection() as db:
        r = db.execute('SELECT * FROM yt_uploads WHERE id=? AND user_id=?', (upload_id, user_id)).fetchone()
    if not r:
        raise HTTPException(404, 'Upload not found')
    d = dict(r)
    d.pop('user_id', None)
    d['made_for_kids'] = bool(d['made_for_kids'])
    d['youtube_url'] = f'https://www.youtube.com/watch?v={d["video_id"]}' if d['video_id'] else None
    return d


def _valid_upload_url(location):
    p = urlparse(location)
    return p.scheme == 'https' and p.hostname in ('www.googleapis.com', 'youtube.googleapis.com', 'upload.youtube.com')


def _token_request(data):
    with httpx.Client(timeout=30) as client:
        response = client.post(TOKEN_ENDPOINT, data=data)
    if response.status_code >= 400:
        raise RuntimeError('Google authorization was rejected. Check OAuth setup or reconnect your channel.')
    return response.json()


def _get_access(user_id):
    creds = _load_creds(user_id)
    if not creds:
        raise RuntimeError('Connect your YouTube account from Account & API first')
    if int(creds.get('expires_at', 0)) > time.time() + 90:
        return creds['access_token']
    client_id, client_secret, _, _ = _config()
    if not creds.get('refresh_token'):
        raise RuntimeError('Google session expired; please reconnect YouTube')
    tokens = _token_request({
        'client_id': client_id, 'client_secret': client_secret,
        'refresh_token': creds['refresh_token'], 'grant_type': 'refresh_token'
    })
    creds['access_token'] = tokens['access_token']
    creds['expires_at'] = int(time.time()) + int(tokens.get('expires_in', 3600))
    if tokens.get('refresh_token'):
        creds['refresh_token'] = tokens['refresh_token']
    _save_creds(user_id, creds)
    return creds['access_token']


def _error_message(response):
    try:
        data = response.json()
        err = data.get('error', data)
        codes = ', '.join(str(item.get('reason', '')) for item in err.get('errors', []) if isinstance(item, dict))
        reason = err.get('message') or err.get('error_description') or str(err)
        reason = f'{codes}: {reason}' if codes else reason
    except (ValueError, AttributeError, TypeError):
        reason = response.text[:250]
    return f'YouTube API returned HTTP {response.status_code}: {reason[:280]}'



def _current_user(authorization: str | None = Header(None)):
    return _core.current_user(authorization)


class PublishRequest(BaseModel):
    export_id: str = Field(min_length=8, max_length=80)
    title: str = Field(min_length=1, max_length=100)
    description: str = Field(default='', max_length=5000)
    privacy: str = 'private'
    made_for_kids: bool
    rights_confirmed: bool
    clip_reviewed: bool = False
    studio_retry_confirmed: bool = False


@router.get('/status')
def status(user=Depends(_current_user)):
    with _core.connection() as db:
        connected = db.execute('SELECT 1 FROM yt_accounts WHERE user_id=?', (user['id'],)).fetchone() is not None
    return {'configured': _oauth_ready(), 'connected': connected, 'scope': SCOPE}


@router.post('/authorize')
def authorize(user=Depends(_current_user)):
    client_id, client_secret, callback, _ = _config()
    if not client_id or not client_secret:
        raise HTTPException(503, 'Configure OPENSHORTS_YOUTUBE_CLIENT_ID and OPENSHORTS_YOUTUBE_CLIENT_SECRET on your backend first')
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    with _core.connection() as db:
        db.execute('DELETE FROM yt_oauth_pending WHERE expires_at < ?', (int(time.time()),))
        db.execute('INSERT INTO yt_oauth_pending VALUES(?,?,?,?)', (state, user['id'], verifier, int(time.time()) + 600))
    params = {
        'client_id': client_id,
        'redirect_uri': callback,
        'response_type': 'code',
        'scope': SCOPE,
        'state': state,
        'access_type': 'offline',
        'prompt': 'consent',
        'code_challenge': challenge,
        'code_challenge_method': 'S256',
    }
    return {'authorization_url': AUTH_ENDPOINT + '?' + urlencode(params)}


def _callback_page(message, ok=False):
    _, _, _, frontend = _config()
    # All HTML text is fixed. No arbitrary Google parameters are reflected.
    title = 'YouTube connected!' if ok else 'YouTube connection failed'
    return HTMLResponse(
        f'<!doctype html><html><head><meta name="referrer" content="no-referrer">'
        f'<title>{title}</title><style>'
        'body{background:#101015;color:#efecfc;font:16px system-ui;max-width:540px;'
        'margin:12vh auto;padding:24px}a{color:#ad8eff}h1{letter-spacing:-.03em}'
        f'</style></head><body><h1>{title}</h1><p>{message}</p>'
        f'<a href="{frontend}/account">Return to OpenShorts</a></body></html>',
        status_code=200 if ok else 400,
        headers={'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer'},
    )


@router.get('/oauth/callback')
def oauth_callback(state: str = Query(''), code: str = Query(''), error: str = Query('')):
    if not state or (not code and not error):
        return _callback_page('Missing authorization response.')
    with _core.connection() as db:
        entry = db.execute('SELECT * FROM yt_oauth_pending WHERE state=?', (state,)).fetchone()
        db.execute('DELETE FROM yt_oauth_pending WHERE state=?', (state,))
    if not entry or entry['expires_at'] < int(time.time()):
        return _callback_page('Authorization expired or was already used. Start again from Account & API.')
    if error:
        return _callback_page('Authorization was canceled or declined. No access was saved.')
    try:
        client_id, client_secret, callback, _ = _config()
        tokens = _token_request({
            'code': code, 'client_id': client_id, 'client_secret': client_secret,
            'redirect_uri': callback, 'grant_type': 'authorization_code',
            'code_verifier': entry['code_verifier'],
        })
        if 'access_token' not in tokens:
            raise ValueError('No access token returned')
        prev = _load_creds(entry['user_id']) or {}
        refresh_token = tokens.get('refresh_token') or prev.get('refresh_token')
        if not refresh_token:
            raise ValueError('No refresh token returned; reconnect and allow offline access')
        _save_creds(entry['user_id'], {
            'access_token': tokens['access_token'],
            'refresh_token': refresh_token,
            'expires_at': int(time.time()) + int(tokens.get('expires_in', 3600)),
        })
    except Exception:
        return _callback_page('Google authorization failed. Verify client credentials, redirect URI, and test-user settings.')
    return _callback_page('Your YouTube channel is ready to receive video uploads from OpenShorts.', True)


@router.delete('/connection')
def disconnect(user=Depends(_current_user)):
    with _core.connection() as db:
        db.execute('DELETE FROM yt_accounts WHERE user_id=?', (user['id'],))
    return {'disconnected': True, 'note': 'Local credentials deleted. Revoke OpenShorts access in your Google account to fully revoke granted access.'}


@router.get('/exports/{export_id}/upload')
def latest_upload(export_id: str, user=Depends(_current_user)):
    with _core.connection() as db:
        row = db.execute('''
            SELECT u.id FROM exports requested
            JOIN exports previous ON previous.project_id=requested.project_id AND previous.clip_id=requested.clip_id
                                  AND previous.user_id=requested.user_id
            JOIN yt_uploads u ON u.export_id=previous.id AND u.user_id=previous.user_id
            WHERE requested.id=? AND requested.user_id=? ORDER BY u.created_at DESC LIMIT 1
        ''', (export_id, user['id'])).fetchone()
    return _get_upload(row['id'], user['id']) if row else None


@router.get('/uploads/{upload_id}')
def upload_status(upload_id: str, user=Depends(_current_user)):
    return _get_upload(upload_id, user['id'])


@router.post('/uploads', status_code=202)
def start_upload(payload: PublishRequest, tasks: BackgroundTasks, user=Depends(_current_user)):
    if not _oauth_ready():
        raise HTTPException(503, 'YouTube API credentials are not configured')
    if not _load_creds(user['id']):
        raise HTTPException(409, 'Connect your YouTube channel from Account & API first')
    if payload.privacy not in ('private', 'unlisted', 'public'):
        raise HTTPException(422, 'Choose private, unlisted, or public visibility')
    if not payload.rights_confirmed:
        raise HTTPException(422, 'Confirm you have permission to upload this video')
    if not payload.clip_reviewed:
        raise HTTPException(422, 'Review the exported clip before uploading')
    title = payload.title.strip()
    if not title:
        raise HTTPException(422, 'A title is required')
    with _core.connection() as db:
        row = db.execute('SELECT id,path,project_id,clip_id FROM exports WHERE id=? AND user_id=?', (payload.export_id, user['id'])).fetchone()
    if not row or not Path(row['path']).is_file():
        raise HTTPException(404, 'Exported MP4 not found. Export the clip first.')
    if not Path(row['path']).resolve().is_relative_to(_core.FILES.resolve()):
        raise HTTPException(403, 'Invalid export path')
    with _core.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        existing = db.execute('''
            SELECT u.status FROM yt_uploads u
            LEFT JOIN exports e ON e.id=u.export_id AND e.user_id=u.user_id
            WHERE u.user_id=? AND (u.export_id=? OR (e.project_id=? AND e.clip_id=?))
        ''', (user['id'], payload.export_id, row['project_id'], row['clip_id'])).fetchall()
        if any(item['status'] != 'failed' for item in existing):
            raise HTTPException(409, 'This clip already has a YouTube upload. Check its status.')
        limit = db.execute(
            "SELECT 1 FROM yt_uploads WHERE user_id=? AND status='failed' AND updated_at >= ? "
            "AND (lower(error) LIKE '%uploadlimitexceeded%' OR lower(error) LIKE '%upload limit%')",
            (user['id'], (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()),
        ).fetchone()
        if (existing or limit) and not payload.studio_retry_confirmed:
            raise HTTPException(409, 'Check YouTube Studio for an existing video and confirm uploads are available before retrying.')
        upload_id = secrets.token_hex(16)
        db.execute('INSERT INTO yt_uploads(id,user_id,export_id,title,description,privacy,made_for_kids,status,progress,video_id,error,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (upload_id, user['id'], payload.export_id, title, payload.description, payload.privacy, int(payload.made_for_kids), 'queued', 0, None, None, _now(), _now()))
    tasks.add_task(_upload_job, upload_id, user['id'], str(row['path']))
    return _get_upload(upload_id, user['id'])


def _start_resumable(client, access_token, title, description, privacy, made_for_kids, size):
    metadata = {
        'snippet': {'title': title, 'description': description, 'categoryId': '22'},
        'status': {'privacyStatus': privacy, 'selfDeclaredMadeForKids': made_for_kids},
    }
    r = client.post(UPLOAD_ENDPOINT,
        params={'uploadType': 'resumable', 'part': 'snippet,status'},
        headers={'Authorization': f'Bearer {access_token}',
                 'X-Upload-Content-Type': 'video/mp4', 'X-Upload-Content-Length': str(size)},
        json=metadata)
    if r.status_code not in (200, 201):
        raise RuntimeError(_error_message(r))
    location = r.headers.get('Location', '')
    if not _valid_upload_url(location):
        raise RuntimeError('Unexpected upload endpoint from Google; refusing to send video')
    return location


def _upload_chunks(client, uri, access_token, video_path, size, update_progress):
    offset = 0
    with video_path.open('rb') as file:
        while offset < size:
            file.seek(offset)
            chunk = file.read(min(CHUNK_SIZE, size - offset))
            if not chunk:
                raise RuntimeError('Video file changed during upload')
            last = offset + len(chunk) - 1
            r = client.put(uri,
                headers={'Authorization': f'Bearer {access_token}',
                         'Content-Type': 'video/mp4',
                         'Content-Range': f'bytes {offset}-{last}/{size}'},
                content=chunk)
            if r.status_code in (200, 201):
                video_id = r.json().get('id')
                if not isinstance(video_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{6,32}', video_id):
                    raise RuntimeError('Google did not return a valid video ID; check YouTube Studio')
                update_progress(100)
                return video_id
            if r.status_code == 308:
                acknowledged = r.headers.get('Range', '')
                m = re.fullmatch(r'bytes=0-(\d+)', acknowledged)
                next_offset = int(m.group(1)) + 1 if m else 0
                if next_offset <= offset:
                    raise RuntimeError('YouTube did not acknowledge the uploaded chunk; check YouTube Studio before retrying')
                offset = next_offset
                update_progress(min(99, int(100 * offset / size)))
                continue
            raise RuntimeError(_error_message(r))
    raise RuntimeError('Upload finished without confirmation; check YouTube Studio before retrying')


def _upload_job(upload_id, user_id, path):
    try:
        with _core.connection() as db:
            row = db.execute('SELECT * FROM yt_uploads WHERE id=? AND user_id=?', (upload_id, user_id)).fetchone()
        file = Path(path)
        size = file.stat().st_size
        if size < 1000:
            raise RuntimeError('Exported MP4 is missing or empty')
        access = _get_access(user_id)
        _update_upload(upload_id, status='uploading', progress=1)
        timeout = httpx.Timeout(connect=30, read=180, write=180, pool=30)
        with httpx.Client(timeout=timeout, follow_redirects=False) as client:
            uri = _start_resumable(client, access, row['title'], row['description'], row['privacy'], bool(row['made_for_kids']), size)
            vid = _upload_chunks(client, uri, access, file, size, lambda pct: _update_upload(upload_id, progress=pct))
        _update_upload(upload_id, status='published', progress=100, video_id=vid, error=None)
    except Exception as ex:
        # Do not auto-retry ambiguous network failures: repeated POSTs may cause duplicate videos.
        _update_upload(upload_id, status='failed', error=(str(ex)[:350] + ' — Check YouTube Studio before retrying to avoid duplicate uploads.'))
