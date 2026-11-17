import os,tempfile,subprocess,time
os.environ['OPENSHORTS_DATA']=tempfile.mkdtemp(prefix='openshorts-test-')
from fastapi.testclient import TestClient
from app.main import app, rank_clips, parse_srt
client=TestClient(app)
def auth():
    email=f'tester{time.time_ns()}@example.com'
    r=client.post('/api/auth/signup',json={'email':email,'password':'StrongPassword123'})
    assert r.status_code==200,r.text
    return {'Authorization':'Bearer '+r.json()['token']}
def test_auth_and_project_crud():
    h=auth()
    assert client.get('/api/auth/me',headers=h).status_code==200
    p=client.post('/api/projects',headers=h,json={'title':'Demo'});assert p.status_code==200
    pid=p.json()['id']
    assert client.get(f'/api/projects/{pid}',headers=h).json()['title']=='Demo'
    assert client.patch(f'/api/projects/{pid}',headers=h,json={'title':'Renamed'}).json()['title']=='Renamed'
    assert len(client.get('/api/projects',headers=h).json())==1
    assert client.delete(f'/api/projects/{pid}',headers=h).status_code==200
    assert client.get(f'/api/projects/{pid}',headers=h).status_code==404
def test_auth_rejection():
    assert client.get('/api/projects').status_code==401
    assert client.post('/api/auth/signup',json={'email':'bad','password':'abc'}).status_code==422
def test_transcript_and_ranking():
    # Use a realistic stretch of dialogue: current clip ranking requires a
    # substantial amount of speech, not just two short subtitle fragments.
    srt = (
        '1\n00:00:00,000 --> 00:00:12,000\n'
        'Why does this problem happen and how can we solve it together today?\n\n'
        '2\n00:00:12,000 --> 00:00:24,000\n'
        'First we learn the simplest trick and understand the mistake everyone makes.\n\n'
        '3\n00:00:24,000 --> 00:00:36,000\n'
        'Finally the result is surprising because the solution works even better now.\n'
    )
    subs = parse_srt(srt)
    assert len(subs) == 3
    clips = rank_clips(subs, 40)
    assert clips and clips[0]['end'] > clips[0]['start']
    assert clips[0]['end'] <= 40

def test_upload_analyze_export():
    h=auth();pid=client.post('/api/projects',headers=h,json={'title':'Video test'}).json()['id']
    tmp=tempfile.NamedTemporaryFile(suffix='.mp4',delete=False);tmp.close()
    subprocess.run(['ffmpeg','-loglevel','error','-y','-f','lavfi','-i','color=c=blue:s=480x270:r=15','-f','lavfi','-i','sine=frequency=440:sample_rate=44100','-t','9','-c:v','mpeg4','-c:a','aac',tmp.name],check=True)
    with open(tmp.name,'rb') as f:
        r=client.post(f'/api/projects/{pid}/upload',headers=h,files={'file':('demo.mp4',f,'video/mp4')})
    assert r.status_code==200,r.text
    srt='1\n00:00:00,000 --> 00:00:03,000\nWhy this is important\n\n2\n00:00:03,000 --> 00:00:06,000\nThe best way to learn\n\n3\n00:00:06,000 --> 00:00:09,000\nNever stop creating'
    r=client.post(f'/api/projects/{pid}/transcript',headers=h,files={'file':('demo.srt',srt,'text/plain')});assert r.status_code==200,r.text
    r=client.post(f'/api/projects/{pid}/analyze',headers=h);assert r.status_code==200,r.text
    p=client.get(f'/api/projects/{pid}',headers=h).json();assert p['status']=='ready',p.get('error')
    clip=p['clips'][0]
    r=client.patch(f'/api/projects/{pid}/clips/{clip["id"]}',headers=h,json={'start':clip['start'],'end':clip['end'],'title':clip['title'],'captions':True});assert r.status_code==200,r.text
    r=client.post(f'/api/projects/{pid}/clips/{clip["id"]}/export',headers=h);assert r.status_code==200,r.text
    p=client.get(f'/api/projects/{pid}',headers=h).json();assert p['status']=='ready',p['error']
    exports=client.get(f'/api/projects/{pid}/exports',headers=h).json();assert len(exports)==1
    assert client.get(f'/api/exports/{exports[0]["id"]}/download',headers=h).status_code==200
