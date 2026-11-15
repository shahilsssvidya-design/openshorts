"""Offline tests for persisted automatic channel detection and watch API."""
import os
import json
import sqlite3
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from app import main as m
from app import channel_monitor as cm

@pytest.fixture
def env(monkeypatch):
    with TemporaryDirectory() as folder:
        monkeypatch.setattr(m,'BASE',Path(folder))
        monkeypatch.setattr(m,'DB',Path(folder)/'test.sqlite')
        monkeypatch.setattr(m,'FILES',Path(folder)/'media')
        m.FILES.mkdir()
        m.init_db()
        cm.init_db()
        monkeypatch.setenv('OPENSHORTS_YOUTUBE_API_KEY','testing-not-real')
        monkeypatch.setenv('OPENSHORTS_LIVE_RECORDING_ENABLED','1')
        with TestClient(m.app) as client:
            response=client.post('/api/auth/signup',json={'email':'monitor@test.dev','password':'password123'})
            assert response.status_code==200,response.text
            auth={'Authorization':'Bearer '+response.json()['token']}
            yield client,auth,response.json()['user']['id']


def test_url_parsing_and_no_ssrf():
    assert cm.parse_channel('@SomeCreator')==('handle','@SomeCreator')
    assert cm.parse_channel('https://youtube.com/@SomeCreator/live')==('handle','@SomeCreator')
    assert cm.parse_channel('https://www.youtube.com/watch?v=D5g1E5mwMWw')==('video','D5g1E5mwMWw')
    with pytest.raises(ValueError):cm.parse_channel('http://localhost:8080/internal')
    with pytest.raises(ValueError):cm.parse_channel('https://evil.example/@SomeCreator/live')


def test_google_api_discovery(monkeypatch):
    def google(path,params):
        if path=='channels':return {'items':[{'id':'UC'+'a'*22,'snippet':{'title':'Creator'}}]}
        if path=='search':return {'items':[{'id':{'videoId':'D5g1E5mwMWw'}}]}
    monkeypatch.setattr(cm,'_google',google)
    assert cm.resolve_channel('@creator')==('UC'+'a'*22,'Creator')
    assert cm.detect_live('UC'+'a'*22)=='D5g1E5mwMWw'


def test_channel_crud_ownership_pause_resume_and_restart(env,monkeypatch):
    client,auth,owner=env
    monkeypatch.setattr(cm,'resolve_channel',lambda x: ('UC'+'a'*22,'Creator Alpha'))
    denied=client.post('/api/channel-watches',json={'channel':'@CreatorAlpha'},headers=auth)
    assert denied.status_code==422
    created=client.post('/api/channel-watches',json={'channel':'@CreatorAlpha','rights_confirmed':True},headers=auth)
    assert created.status_code==201,created.text
    wid=created.json()['id']
    assert created.json()['enabled'] is True
    assert len(client.get('/api/channel-watches',headers=auth).json())==1
    denied_duplicate=client.post('/api/channel-watches',json={'channel':'@CreatorBeta','rights_confirmed':True},headers=auth)
    assert denied_duplicate.status_code==409
    pause=client.post('/api/channel-watches/'+wid+'/pause',headers=auth)
    assert pause.status_code==200 and pause.json()['state']=='paused'
    resume=client.post('/api/channel-watches/'+wid+'/resume',headers=auth)
    assert resume.status_code==200 and resume.json()['state']=='waiting'
    cm._update(wid,state='capturing')
    cm.init_db()
    assert cm._row(wid,owner)['state']=='waiting'
    deleted=client.delete('/api/channel-watches/'+wid,headers=auth)
    assert deleted.status_code==200 and deleted.json()['projects_preserved']


def test_check_live_and_offline(env,monkeypatch):
    client,auth,owner=env
    monkeypatch.setattr(cm,'resolve_channel',lambda x: ('UC'+'a'*22,'Creator'))
    wid=client.post('/api/channel-watches',json={'channel':'@CreatorX','rights_confirmed':True},headers=auth).json()['id']
    monkeypatch.setattr(cm,'detect_live',lambda channel:None)
    row=cm._row(wid,owner)
    cm.check_one(row,1000)
    assert cm._row(wid,owner)['state']=='waiting'
    assert cm._row(wid,owner)['next_check']==1000+cm.DEFAULT_POLL_SECONDS
    # Simulate known blocked broadcast: no duplicate capture retries.
    cm._update(wid,blocked_video_id='D5g1E5mwMWw')
    monkeypatch.setattr(cm,'detect_live',lambda channel:'D5g1E5mwMWw')
    cm.check_one(cm._row(wid,owner),2000)
    assert cm._row(wid,owner)['state']=='blocked'
    assert cm._row(wid,owner)['last_video_id']=='D5g1E5mwMWw'


def test_discovery_works_when_capture_is_blocked(env,monkeypatch):
    client,auth,owner=env
    monkeypatch.setattr(cm,'resolve_channel',lambda x: ('UC'+'a'*22,'Creator'))
    wid=client.post('/api/channel-watches',json={'channel':'@CreatorX','rights_confirmed':True},headers=auth).json()['id']
    from app import live
    monkeypatch.setattr(live,'resolve_sources',lambda u: (_ for _ in ()).throw(RuntimeError('Sign in to confirm')))
    row=cm._row(wid,owner)
    with pytest.raises(cm.CaptureDenied,match='YouTube playback/capture was rejected'):
        cm._record_source(row,'D5g1E5mwMWw')


def test_api_key_only_backend_and_no_private_feed_in_response(env,monkeypatch):
    client,auth,_=env
    monkeypatch.setenv('OPENSHORTS_AUTHORIZED_FEED_URL','https://private.example.com/tokenized-secret.m3u8')
    response=client.get('/api/channel-watches/config',headers=auth)
    assert response.status_code==200
    assert response.json()['direct_feed_configured']
    assert 'tokenized-secret' not in response.text
    assert 'testing-not-real' not in response.text


def test_fast_rss_discovery_finds_live_broadcast(monkeypatch):
    xml=b'''<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns:yt="http://www.youtube.com/xml/schemas/2015">
    <entry><yt:videoId>D5g1E5mwMWw</yt:videoId></entry></feed>'''
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def read(self,size):return xml
    monkeypatch.setattr(cm.urllib.request,'urlopen',lambda *args,**kwargs: Response())
    def fake_google(path,params):
        assert path=='videos'
        return {'items':[{'id':'D5g1E5mwMWw','snippet':{'liveBroadcastContent':'live'}}]}
    monkeypatch.setattr(cm,'_google',fake_google)
    assert cm.detect_live_fast('UC'+'a'*22)=='D5g1E5mwMWw'
