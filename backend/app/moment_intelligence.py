"""Visual-aware, offline gaming moment selection for OpenShorts.

Speech proposes complete Shorts, while actual decoded frames provide lightweight
motion/lighting evidence. This is a heuristic, NOT semantic visual understanding.
"""
from __future__ import annotations
import math, re, shutil, subprocess
from pathlib import Path

FRAME_BYTES=96*54
REACTIONS={'what','wait','wow','no','way','crazy','insane','whoa','oh','wtf','omg','bro','bruh','look','how','why','npc','bug','crash','fail','failed','impossible','funny','laugh','hahaha','damn','finally','happened','dead'}

def _t(s,k): return float(s.get(k,0))

def _windows(segments,duration):
    if not segments or duration<4: return []
    stride=max(1,math.ceil(len(segments)/180))
    anchors=set(range(0,len(segments),stride))|{len(segments)-1}
    proposed={}
    for idx in sorted(anchors):
        anchor=_t(segments[idx],'start')
        for target in (18,26,36,46):
            start=max(0.,anchor-2)
            if duration<target: start=0.
            limit=min(duration,start+target)
            # Cut at real subtitle endings, so dialogue doesn't stop mid-sentence.
            nearby=[s for s in segments if start+7<=_t(s,'end')<=min(duration,limit+4)]
            if nearby:
                close=min(nearby,key=lambda s: abs(_t(s,'end')-limit)-(2 if str(s['text']).rstrip().endswith(('.','!','?')) else 0))
                end=min(duration,_t(close,'end')+.35)
            else: end=limit
            if end-start < min(8.,duration-.01): continue
            proposed[(round(start,1),round(end,1))]=(start,end)
    return list(proposed.values())

def _speech(transcript,start,end):
    window=[s for s in transcript if _t(s,'start')<end and _t(s,'end')>start]
    if not window: return None
    speech=' '.join(str(s.get('text','')).strip() for s in window).strip()
    tokens=re.findall(r"[\w']+",speech.lower())
    if len(tokens)<7: return None
    density=len(tokens)/max(1,end-start)
    intro=[s for s in window if _t(s,'start')<start+4.5]
    tail=[s for s in window if _t(s,'start')>=start+.6*(end-start)]
    it=re.findall(r"[\w']+",' '.join(s['text'] for s in intro).lower())
    lt=re.findall(r"[\w']+",' '.join(s['text'] for s in tail).lower())
    hook=min(1.,sum(t in REACTIONS for t in it)/2)
    payoff=min(1.,sum(t in REACTIONS for t in lt)/2)
    punctuation=min(1.,(speech.count('!')+speech.count('?'))/3)
    closing=1. if any(str(s['text']).rstrip().endswith(('.','!','?')) for s in window[-2:]) else .4
    score=22+24*min(1.,density/2.1)+18*hook+19*payoff+7*punctuation+10*closing
    if density<.7: score-=18
    intro_text=' '.join(s['text'] for s in window[:2]).strip()
    title=re.sub(r'\s+',' ',intro_text).strip(' .,!?:;')[:75] or 'Highlight'
    return {'speech_score':round(max(0,min(100,score)),1),'hook_score':round(hook*100,1),
            'payoff_score':round(payoff*100,1),'density':round(density,2),'title':title,
            'hook':intro_text[:160],'description':speech[:280]}

def _visual(source,start,end):
    """Sample raw 96x54 greyscale frames at 2fps, capped at 35 seconds."""
    if not source or not Path(source).is_file() or not shutil.which('ffmpeg'): return None
    length=min(35.,max(0.,end-start))
    if length<2: return None
    cmd=['ffmpeg','-hide_banner','-loglevel','error','-ss',f'{start:.2f}',
         '-i',str(source),'-t',f'{length:.2f}','-an',
         '-vf','fps=2,scale=96:54,format=gray','-f','rawvideo','pipe:1']
    try: result=subprocess.run(cmd,capture_output=True,timeout=25,check=False)
    except (OSError,subprocess.TimeoutExpired): return None
    if result.returncode: return None
    buf=result.stdout
    frames=[buf[i:i+FRAME_BYTES] for i in range(0,len(buf),FRAME_BYTES) if len(buf[i:i+FRAME_BYTES])==FRAME_BYTES]
    if len(frames)<3: return None
    brightness=sum(sum(frame)/FRAME_BYTES for frame in frames)/len(frames)
    diff=[sum(abs(a-b) for a,b in zip(frames[j-1],frames[j]))/FRAME_BYTES for j in range(1,len(frames))]
    avg=sum(diff)/len(diff)
    tail=diff[max(0,len(diff)//2):]
    final=sum(tail)/len(tail)
    return {'visual_activity':round(min(100,avg/35*100),1),
            'final_action':round(min(100,final/35*100),1),
            'lighting':round(min(100,max(0,brightness-24)/75*100),1),
            'static':avg<6,'dark':brightness<38}

def choose_moments(transcript,duration,fallback_ranker=None,progress=None,source=None):
    """Pick at most eight varied 8-46s windows with hook/action/payoff signals."""
    duration=float(duration)
    valid=[s for s in transcript if str(s.get('text','')).strip() and _t(s,'end')>_t(s,'start')]
    valid.sort(key=lambda s:_t(s,'start'))
    if not valid: return []
    proposed=[]
    for start,end in _windows(valid,duration):
        speech=_speech(valid,start,end)
        if speech is not None: proposed.append((speech['speech_score'],start,end,speech))
    if not proposed:
        return fallback_ranker(valid,duration)[:8] if fallback_ranker is not None else []
    proposed.sort(key=lambda p:p[0],reverse=True)
    # Spend the expensive visual pass on distinct moments throughout the video.
    shortlist=[]
    for candidate in proposed:
        _,start,end,_=candidate
        if any(max(0.,min(end,other[2])-max(start,other[1])) >
               .65*min(end-start,other[2]-other[1]) for other in shortlist):
            continue
        shortlist.append(candidate)
        if len(shortlist)>=24: break
    finalists=[]
    for i,(_,start,end,speech) in enumerate(shortlist):
        visual=_visual(source,start,end)
        if visual is None:
            score=min(72.,speech['speech_score']*.78)
            metrics={'visual_activity':None,'lighting':None,'payoff':speech['payoff_score'],
                     'speech_density':speech['density'],'visual_verified':False}
        else:
            score=(.54*speech['speech_score']+.23*visual['visual_activity']+
                   .13*visual['final_action']+.10*visual['lighting'])
            if visual['static']: score=min(score,57.)
            if visual['dark']: score=min(score,72.)
            metrics={'visual_activity':visual['visual_activity'],'final_action':visual['final_action'],
                     'lighting':visual['lighting'],'payoff':speech['payoff_score'],
                     'speech_density':speech['density'],'visual_verified':True}
        finalists.append({'start':round(start,2),'end':round(end,2),
                          'score':round(max(0,min(99,score)),1),'ranking_method':'heuristic',
                          'quality_metrics':metrics,'title':speech['title'],'hook':speech['hook'],
                          'description':speech['description'],
                          'reason':('Speech hook + visual activity signals; verify final payoff' if visual
                                    else 'Speech-only candidate; visual check unavailable'),
                          'style':'outline','position':'middle','color':'#FFFFFF',
                          'caption_scale':.9,'captions':True})
        if progress: progress(min(93,74+int(19*(i+1)/len(shortlist))))
    finalists.sort(key=lambda c:(-c['score'],c['start']))
    selected=[]
    for item in finalists:
        overlaps=any(max(0.,min(item['end'],old['end'])-max(item['start'],old['start']))>
                     .35*min(item['end']-item['start'],old['end']-old['start']) for old in selected)
        if not overlaps: selected.append(item)
        if len(selected)>=8: break
    return selected
