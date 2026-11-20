"""Offline API + upload tests. Run from OpenShorts_2.0/backend with pytest -q tests/test_youtube_publish.py."""
import os
import time
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main as app_main
from app import youtube_publish as yp


@pytest.fixture
def client(monkeypatch):
    # Fresh isolated SQLite storage for test only (never user data).
    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as d:
        monkeypatch.setattr(app_main,'BASE',Path(d))
        monkeypatch.setattr(app_main,'DB',Path(d)/'test.sqlite')
        monkeypatch.setattr(app_main,'FILES',Path(d)/'media')
        app_main.FILES.mkdir()
        app_main.init_db()
        yp.init(app_main)
        monkeypatch.setenv('OPENSHORTS_YOUTUBE_CLIENT_ID','fake-id.apps.googleusercontent.com')
        monkeypatch.setenv('OPENSHORTS_YOUTUBE_CLIENT_SECRET','fake-secret')
        with TestClient(app_main.app) as c:
            yield c


def signup(c,email):
    result = c.post('/api/auth/signup',json={'email':email,'password':'password123'})
    assert result.status_code==200,result.text
    return {'Authorization':'Bearer '+result.json()['token']},result.json()['user']['id']


def test_connection_and_oauth_state_is_single_use(client,monkeypatch):
    headers,user_id=signup(client,'owner@test.dev')
    assert client.get('/api/youtube/status',headers=headers).json()['connected'] is False
    r=client.post('/api/youtube/authorize',headers=headers)
    assert r.status_code==200,r.text
    from urllib.parse import urlparse,parse_qs
    params=parse_qs(urlparse(r.json()['authorization_url']).query)
    assert params['scope']==[yp.SCOPE]
    assert params['code_challenge_method']==['S256']
    assert 'state' in params
    monkeypatch.setattr(yp,'_token_request',lambda data: {'access_token':'fake-token','refresh_token':'fake-refresh','expires_in':3600})
    first=client.get('/api/youtube/oauth/callback',params={'state':params['state'][0],'code':'fake-code'})
    assert first.status_code==200,first.text
    assert client.get('/api/youtube/status',headers=headers).json()['connected'] is True
    second=client.get('/api/youtube/oauth/callback',params={'state':params['state'][0],'code':'fake-code'})
    assert second.status_code==400
    with app_main.connection() as db:
        token=db.execute('SELECT encrypted_token FROM yt_accounts WHERE user_id=?',(user_id,)).fetchone()['encrypted_token']
    assert b'fake-refresh' not in token


def test_publish_ownership_validation_and_no_accidental_public(client,monkeypatch):
    h1,uid1=signup(client,'one@test.dev')
    h2,uid2=signup(client,'two@test.dev')
    path=app_main.FILES/'fake.mp4'
    path.write_bytes(b'0'*1024)
    with app_main.connection() as db:
        db.execute('INSERT INTO projects(id,user_id,title,status,created_at,updated_at) VALUES(?,?,?,?,?,?)',('project-test',uid1,'Test','ready',app_main.now(),app_main.now()))
        db.execute('INSERT INTO exports VALUES(?,?,?,?,?,?)',('test-export-id', 'project-test',uid1,'clip-test',str(path),app_main.now()))
    yp._save_creds(uid1,{'access_token':'x','refresh_token':'y','expires_at':int(time.time())+3600})
    yp._save_creds(uid2,{'access_token':'x','refresh_token':'y','expires_at':int(time.time())+3600})
    payload={'export_id':'test-export-id','title':'A short','description':'', 'privacy':'private','made_for_kids':False,'rights_confirmed':True,'clip_reviewed':True}
    forbidden=client.post('/api/youtube/uploads',headers=h2,json=payload)
    assert forbidden.status_code==404
    not_confirmed=client.post('/api/youtube/uploads',headers=h1,json={**payload,'rights_confirmed':False})
    assert not_confirmed.status_code==422
    # Use mocked job to ensure no Google request occurs.
    monkeypatch.setattr(yp,'_upload_job',lambda *args: None)
    response=client.post('/api/youtube/uploads',headers=h1,json=payload)
    assert response.status_code==202,response.text
    assert response.json()['privacy']=='private'
    duplicate=client.post('/api/youtube/uploads',headers=h1,json=payload)
    assert duplicate.status_code==409
    with app_main.connection() as db:
        db.execute('INSERT INTO exports VALUES(?,?,?,?,?,?)',
                   ('second-export-id', 'project-test', uid1, 'clip-test', str(path), app_main.now()))
    second = {**payload, 'export_id': 'second-export-id'}
    assert client.post('/api/youtube/uploads', headers=h1, json=second).status_code == 409
    yp._update_upload(response.json()['id'], status='failed', error='HTTP 400 uploadLimitExceeded')
    assert client.post('/api/youtube/uploads', headers=h1, json=second).status_code == 409
    assert client.post('/api/youtube/uploads', headers=h1,
                       json={**second, 'studio_retry_confirmed': True}).status_code == 202
    unauthorized=client.get('/api/youtube/uploads/'+response.json()['id'],headers=h2)
    assert unauthorized.status_code==404


def test_resumable_two_chunks():
    data=b'x'*(yp.CHUNK_SIZE+10)
    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as d:
        path=Path(d)/'video.mp4';path.write_bytes(data)
        calls=[]
        def handler(req):
            calls.append(req)
            if len(calls)==1:
                assert req.headers['content-range']==f'bytes 0-{yp.CHUNK_SIZE-1}/{len(data)}'
                return httpx.Response(308,headers={'Range':f'bytes=0-{yp.CHUNK_SIZE-1}'})
            assert req.headers['content-range']==f'bytes {yp.CHUNK_SIZE}-{len(data)-1}/{len(data)}'
            return httpx.Response(201,json={'id':'abcdefghijk'})
        progress=[]
        with httpx.Client(transport=httpx.MockTransport(handler)) as hc:
            video_id=yp._upload_chunks(hc,'https://www.googleapis.com/upload/youtube/v3/videos?upload_id=fake','token',path,len(data),progress.append)
        assert video_id=='abcdefghijk'
        assert progress[-1]==100


def test_reject_external_upload_uri():
    assert yp._valid_upload_url('https://www.googleapis.com/upload/youtube/v3/videos?upload_id=x')
    assert not yp._valid_upload_url('https://evil.example.com/steal')
    assert not yp._valid_upload_url('http://www.googleapis.com/upload/youtube/v3/videos')


def test_live_autopublish_requires_explicit_authorization(client, monkeypatch):
    import importlib.util
    if importlib.util.find_spec('app.live') is None:
        pytest.skip('Live Highlights upgrade not installed')
    from app import live
    live.init()
    headers,_=signup(client,'live@test.dev')
    url='https://www.youtube.com/live/abcdefghijk'
    payload={'url':url,'auto_export':True,'auto_publish':True,'made_for_kids':False,'rights_confirmed':False}
    r=client.post('/api/live',headers=headers,json=payload)
    assert r.status_code==422
    r=client.post('/api/live',headers=headers,json={**payload,'rights_confirmed':True})
    assert r.status_code==422  # Even authorized live sessions require manual review.
