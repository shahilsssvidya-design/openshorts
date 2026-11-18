'use client';
import React,{useCallback,useEffect,useRef,useState} from 'react';
import {Music2,UploadCloud,Volume2,CheckCircle2,AlertCircle} from 'lucide-react';
import {API,request,type Clip} from '@/lib/api';

type Preset={id:string;name:string;mood:string;bpm:number};
type MusicStatus={uploaded:boolean;filename:string|null};
const BUILT_IN:Preset[]=[
  {id:'night-drive',name:'Night Drive',mood:'Cinematic synth / steady energy',bpm:108},
  {id:'bright-bounce',name:'Bright Bounce',mood:'Upbeat / playful',bpm:120},
  {id:'soft-focus',name:'Soft Focus',mood:'Warm ambient / calm',bpm:90},
];

export default function BackgroundMusic({pid,clip,token,onChange}:{pid:string;clip:Clip;token:string;onChange:(changes:Partial<Clip>)=>void}){
  const [status,setStatus]=useState<MusicStatus>({uploaded:false,filename:null});
  const [presets,setPresets]=useState<Preset[]>(BUILT_IN);
  const [previewUrl,setPreviewUrl]=useState('');
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [notice,setNotice]=useState('');
  const audioRef=useRef<HTMLAudioElement>(null);
  const inputRef=useRef<HTMLInputElement>(null);
  const selected=clip.music_track||'none';
  const musicVolume=clip.music_volume??0.20;
  const voiceVolume=clip.original_volume??1;
  const reload=useCallback(async()=>{
    const s=await request<MusicStatus>('/projects/'+pid+'/music');
    setStatus(s);
  },[pid]);

  useEffect(()=>{void reload().catch(e=>setError((e as Error).message));
    void request<Preset[]>('/music/presets').then(setPresets).catch(()=>{});
  },[reload]);

  useEffect(()=>{
    let active=true;let url='';
    setPreviewUrl('');
    if(selected==='none')return;
    const endpoint=selected==='custom'?`/projects/${pid}/music/audio`:`/music/presets/${selected.slice(5)}/audio`;
    fetch(`${API}/api${endpoint}`,{headers:{Authorization:`Bearer ${token}`}})
      .then(r=>{if(!r.ok)throw Error('Selected music is not available. Upload it again if needed.');return r.blob();})
      .then(b=>{url=URL.createObjectURL(b);if(active)setPreviewUrl(url);else URL.revokeObjectURL(url);})
      .catch(e=>{if(active)setError((e as Error).message)});
    return ()=>{active=false;if(url)URL.revokeObjectURL(url)};
  },[selected,pid,token,status.filename]);

  useEffect(()=>{
    const audio=audioRef.current;
    if(audio)audio.volume=Math.min(1,Math.max(0,musicVolume));
  },[musicVolume,previewUrl]);

  // Synchronize the soundtrack with the clip player's play, pause and seek actions.
  useEffect(()=>{
    function sync(e:Event){
      const audio=audioRef.current;
      if(!audio || selected==='none' || !previewUrl)return;
      const d=(e as CustomEvent<{type:string;time:number;start:number}>).detail;
      if(!d)return;
      if(d.type==='pause'){audio.pause();return;}
      const elapsed=Math.max(0,d.time-Number(clip.start||0));
      if(Number.isFinite(audio.duration)&&audio.duration>0){
        const target=elapsed%audio.duration;
        if(Math.abs(audio.currentTime-target)>0.7)audio.currentTime=target;
      }
      if(d.type==='play')void audio.play().catch(()=>{});
    }
    window.addEventListener('os-preview-audio',sync);
    return ()=>window.removeEventListener('os-preview-audio',sync);
  },[selected,previewUrl,clip.start]);

  async function upload(file?:File){
    if(!file)return;
    if(file.size>60*1024*1024){setError('The maximum music file size is 60 MB.');return;}
    setBusy(true);setError('');setNotice('');
    try{
      const form=new FormData();form.append('file',file);
      await request(`/projects/${pid}/music`,{method:'POST',body:form});
      await reload();onChange({music_track:'custom'});
      setNotice('Your music is uploaded. Save changes to keep it on this clip.');
    }catch(e){setError((e as Error).message)}finally{setBusy(false)}
  }

  function choose(track:string){setError('');setNotice('');onChange({music_track:track});}
  return <div className="control-panel os-music-panel">
    <div className="os-music-header"><Music2 size={22}/><div><strong>Background Music</strong><p>Add an instrumental under your original voice. Music loops automatically to the end of your Short.</p></div></div>
    <div className="control-group"><label>CHOOSE YOUR SOUND</label>
      <div className="os-music-grid">
        <button type="button" className={'os-music-choice '+(selected==='none'?'chosen':'')} onClick={()=>choose('none')}>
          <strong>No music</strong><small>Original voice only</small>{selected==='none'&&<CheckCircle2 size={16}/>}
        </button>
        {presets.map(p=><button type="button" key={p.id} className={'os-music-choice '+(selected==='demo:'+p.id?'chosen':'')} onClick={()=>choose('demo:'+p.id)}>
          <strong>{p.name}</strong><small>{p.mood}</small><em>{p.bpm} BPM · Original demo</em>{selected==='demo:'+p.id&&<CheckCircle2 size={16}/>}
        </button>)}
        <button type="button" className={'os-music-choice '+(selected==='custom'?'chosen':'')} disabled={!status.uploaded} onClick={()=>choose('custom')}>
          <strong>My uploaded track</strong><small>{status.filename||'Upload a song below first'}</small>{selected==='custom'&&<CheckCircle2 size={16}/>}
        </button>
      </div>
    </div>
    <div className="control-group"><label>UPLOAD YOUR OWN MUSIC</label>
      <input ref={inputRef} hidden type="file" accept="audio/*,.mp3,.m4a,.aac,.flac,.ogg,.opus,.wma,.wav" onChange={e=>{void upload(e.target.files?.[0]);e.target.value='';}}/>
      <button type="button" className="btn btn-outline" disabled={busy} onClick={()=>inputRef.current?.click()}><UploadCloud size={16}/>{busy?'Uploading audio…':status.uploaded?'Replace music':'Choose an audio file'}</button>
      <p className="hint">MP3, WAV, M4A, FLAC, OGG and other common audio files · max 60 MB. Use music you have permission to publish.</p>
    </div>
    {selected!=='none'&&previewUrl&&<div className="os-music-listen"><label>LISTEN TO SELECTED TRACK</label><audio ref={audioRef} controls loop preload="metadata" src={previewUrl} aria-label="Listen to music"/><p className="hint">Play the video preview to hear the track alongside the video. The final export mixes both audio tracks.</p></div>}
    {selected!=='none'&&<div className="control-group"><label><Volume2 size={15}/> MUSIC VOLUME <span>{Math.round(musicVolume*100)}%</span></label><input type="range" min="0" max="1" step="0.05" value={musicVolume} onChange={e=>onChange({music_volume:Number(e.target.value)})}/></div>}
    <div className="control-group"><label><Volume2 size={15}/> ORIGINAL VIDEO VOLUME <span>{Math.round(voiceVolume*100)}%</span></label><input type="range" min="0" max="1" step="0.05" value={voiceVolume} onChange={e=>onChange({original_volume:Number(e.target.value)})}/></div>
    <p className="hint">Recommended for speaking clips: music at 10–25%, original voice at 100%. The original source file stays unchanged. Click Save changes, then Export MP4.</p>
    {notice&&<p className="os-music-notice"><CheckCircle2 size={15}/>{notice}</p>}
    {error&&<p className="form-error"><AlertCircle size={15}/>{error}</p>}
  </div>;
}
