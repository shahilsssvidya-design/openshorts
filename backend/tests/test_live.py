"""Offline tests: no YouTube credentials or network access required."""
import json
import time
import urllib.request
from io import BytesIO

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app import live

client=TestClient(app)


def auth():
    r=client.post('/api/auth/signup',json={'email':f'live{time.time_ns()}@example.com','password':'testpass123'})
    assert r.status_code==200
    return {'Authorization':'Bearer '+r.json()['token']}


def test_validate_url():
    assert live.validate_url('https://www.youtube.com/@channel/live')
    assert live.validate_url('https://www.youtube.com/watch?v=nvVoEFG3-As')
    for invalid in ('http://www.youtube.com/live/foo', 'https://evil.com/foo',
                    'https://www.youtube.com.evil.com/live/foo', 'https://127.0.0.1/live/foo'):
        with pytest.raises(ValueError): live.validate_url(invalid)


def test_requires_auth_and_explicit_opt_in(monkeypatch):
    monkeypatch.delenv('OPENSHORTS_LIVE_RECORDING_ENABLED',raising=False)
    h=auth()
    assert client.get('/api/live').status_code==401
    assert client.post('/api/live',headers=h,json={'url':'https://www.youtube.com/@test/live'}).status_code==503
    assert client.get('/api/live',headers=h).json()==[]


def test_start_stop_sessions(monkeypatch):
    monkeypatch.setenv('OPENSHORTS_LIVE_RECORDING_ENABLED','1')
    monkeypatch.setattr(live.m,'transcriber_available',lambda: True)
    monkeypatch.setattr(live,'worker',lambda sid,user,url,secs,autox,stop: stop.wait(5))
    h=auth();other=auth()
    r=client.post('/api/live',headers=h,json={'url':'https://www.youtube.com/@test/live','label':'Test stream','chunk_seconds':90})
    assert r.status_code==200,r.text
    sid=r.json()['id']
    assert client.get('/api/live/'+sid,headers=other).status_code==404
    assert client.post('/api/live',headers=other,json={'url':'https://www.youtube.com/@other/live'}).status_code==409
    assert client.get('/api/live',headers=h).json()[0]['id']==sid
    assert client.post('/api/live/'+sid+'/stop',headers=h).status_code==200
    thread=live.THREADS.pop(sid)
    thread.join(timeout=2)
    live.STOP.pop(sid,None)


def test_ai_context_and_empty_result(monkeypatch):
    class Response:
        def __init__(self,data): self.data=data
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,*args):return self.data
    segment=[{'start':0,'end':60,'text':'And here is the big surprise!'}]
    data=json.dumps({'response':json.dumps({'clips':[{'start':17,'end':54,'score':98,'title':'Amazing surprise','reason':'Unexpected twist'}]})}).encode()
    monkeypatch.setattr(urllib.request,'urlopen',lambda *args,**kwargs: Response(data))
    result=live.ai_candidates(segment,60)
    assert len(result)==1 and result[0]['start']<=10 and result[0]['end']>=54
    no_hits=json.dumps({'response':'{"clips":[]}'}).encode()
    monkeypatch.setattr(urllib.request,'urlopen',lambda *args,**kwargs: Response(no_hits))
    assert live.ai_candidates(segment,60)==[]
