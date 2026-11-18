"""Music upgrade integration tests. Run: PYTHONPATH=backend pytest -q backend/tests/test_background_music.py"""
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

os.environ.setdefault('OPENSHORTS_DATA', tempfile.mkdtemp(prefix='openshorts-music-tests-'))
from fastapi.testclient import TestClient
from app import main, music

client=TestClient(main.app)


def account():
    email=f'music_{time.time_ns()}@example.com'
    r=client.post('/api/auth/signup',json={'email':email,'password':'MusicTestStrong123'})
    assert r.status_code==200,r.text
    return {'Authorization':'Bearer '+r.json()['token']}


def project(h):
    r=client.post('/api/projects',headers=h,json={'title':'Audio Demo'})
    assert r.status_code==200,r.text
    return r.json()['id']


def audio_stream_count(path):
    p=subprocess.run(['ffprobe','-v','error','-show_entries','stream=codec_type','-of','json',str(path)],capture_output=True,text=True,check=True)
    return sum(s.get('codec_type')=='audio' for s in json.loads(p.stdout)['streams'])


def make_video(dest,with_audio=True):
    args=['ffmpeg','-hide_banner','-loglevel','error','-y','-f','lavfi','-i','color=c=blue:s=320x180:r=15:d=3']
    if with_audio:
        args+=['-f','lavfi','-i','sine=frequency=440:sample_rate=24000:duration=3']
    args+=['-t','3','-c:v','mpeg4']
    if with_audio:
        args+=['-c:a','aac']
    args+=[str(dest)]
    subprocess.run(args,check=True,timeout=40)


def test_demo_music_and_project_ownership():
    h=account();second=account();pid=project(h)
    r=client.get('/api/music/presets',headers=h)
    assert r.status_code==200
    assert len(r.json())==3
    for preset in r.json():
        r=client.get('/api/music/presets/'+preset['id']+'/audio',headers=h)
        assert r.status_code==200 and len(r.content)>4000
    assert client.get('/api/music/presets').status_code==401
    assert client.get('/api/projects/'+pid+'/music',headers=second).status_code==404
    assert client.get('/api/projects/'+pid+'/music',headers=h).json()['uploaded'] is False
    demo=music.DEMO_PATH/'night-drive.wav'
    with demo.open('rb') as f:
        response=client.post('/api/projects/'+pid+'/music',headers=h,files={'file':('My Music.wav',f,'audio/wav')})
    assert response.status_code==200,response.text
    assert client.get('/api/projects/'+pid+'/music',headers=h).json()['filename']=='My Music.wav'
    assert client.get('/api/projects/'+pid+'/music/audio',headers=h).status_code==200
    assert client.get('/api/projects/'+pid+'/music/audio',headers=second).status_code==404
    assert client.post('/api/projects/'+pid+'/music',headers=h,files={'file':('fake.wav',b'fake audio','audio/wav')}).status_code==422
    assert client.get('/api/projects/'+pid+'/music',headers=h).json()['uploaded'] is True


def test_validated_selection_and_audio_mix(tmp_path):
    h=account();pid=project(h)
    src=tmp_path/'normal.mp4';make_video(src,True)
    assert audio_stream_count(src)==1
    music.validate_settings('demo:night-drive',.2,1.0)
    for invalid in ('demo:../music','youtube:song','custom/file','random'):
        try:
            music.validate_settings(invalid,.2,1)
        except ValueError:
            pass
        else:
            raise AssertionError('accepted unapproved track '+invalid)
    music.apply_music_to_export(pid,{'start':0,'end':3,'music_track':'demo:night-drive','music_volume':.22,'original_volume':.8},src)
    assert src.exists() and src.stat().st_size>5000 and audio_stream_count(src)==1
    silent=tmp_path/'silent.mp4';make_video(silent,False)
    assert audio_stream_count(silent)==0
    music.apply_music_to_export(pid,{'start':0,'end':3,'music_track':'demo:soft-focus','music_volume':.25,'original_volume':1},silent)
    assert audio_stream_count(silent)==1


def test_default_no_music_is_non_destructive(tmp_path):
    h=account();pid=project(h)
    p=tmp_path/'no_change.mp4';make_video(p,True)
    before=p.read_bytes()
    music.apply_music_to_export(pid,{'music_track':'none','music_volume':.2,'original_volume':1},p)
    assert p.read_bytes()==before


def test_clip_music_save_and_archive(tmp_path):
    from io import BytesIO
    from zipfile import ZipFile
    h=account();pid=project(h)
    clip={'id':'sample123','start':0.0,'end':4.0,'title':'Music Example',
          'score':80,'style':'bold','position':'bottom','color':'#FFFFFF','captions':False}
    main.update(pid,duration=8,clips=json.dumps([clip]))
    r=client.patch(f'/api/projects/{pid}/clips/sample123',headers=h,json={
        'start':0,'end':4,'title':'Music Example','captions':False,
        'music_track':'demo:bright-bounce','music_volume':0.15,'original_volume':0.95})
    assert r.status_code==200,r.text
    assert r.json()['music_track']=='demo:bright-bounce'
    got=client.get(f'/api/projects/{pid}',headers=h).json()['clips'][0]
    assert got['music_volume']==0.15 and got['original_volume']==0.95
    r=client.patch(f'/api/projects/{pid}/clips/sample123',headers=h,json={
        'start':0,'end':4,'title':'Music Example', 'music_track':'demo:not-a-track'})
    assert r.status_code==422

    demo=music.DEMO_PATH/'bright-bounce.wav'
    with demo.open('rb') as f:
        assert client.post(f'/api/projects/{pid}/music',headers=h,files={'file':('Mine.wav',f,'audio/wav')}).status_code==200
    response=client.get(f'/api/projects/{pid}/archive',headers=h)
    assert response.status_code==200,response.text[:100]
    with ZipFile(BytesIO(response.content)) as archive:
        assert any(name.endswith('/music/custom.wav') for name in archive.namelist())
        assert any(name.endswith('/music/name.json') for name in archive.namelist())
