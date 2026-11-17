'use client';
import React,{useState} from 'react';
import {Sparkles,LoaderCircle} from 'lucide-react';
import {post,type Project} from '@/lib/api';

export default function AIEnhanceAll({p,refresh}:{p:Project;refresh:()=>Promise<void>}){
  const [running,setRunning]=useState(false);
  const [error,setError]=useState('');
  const [message,setMessage]=useState('');
  const [tone,setTone]=useState('curiosity');
  const [language,setLanguage]=useState('English');
  async function enhance(){
    setRunning(true);setError('');setMessage('');
    try{
      const result=await post<{updated:number,total:number}>(`/projects/${p.id}/creative/enhance-all`,{tone,language});
      await refresh();
      setMessage(`AI saved original titles, hooks, descriptions and hashtags for ${result.updated} clips.`);
    }catch(e){setError((e as Error).message)}finally{setRunning(false)}
  }
  return <div className="os-batch-ai">
    <div className="os-batch-ai-controls">
      <select aria-label="AI title tone" value={tone} onChange={e=>setTone(e.target.value)} disabled={running}>
        <option value="curiosity">Curiosity</option><option value="funny">Funny</option>
        <option value="dramatic">Dramatic</option><option value="professional">Professional</option>
      </select>
      <select aria-label="AI packaging language" value={language} onChange={e=>setLanguage(e.target.value)} disabled={running}>
        <option>English</option><option>Hinglish</option><option>Hindi</option>
      </select>
      <button className="btn btn-primary btn-sm" type="button" disabled={running||!p.clips.length||p.status==='analyzing'} onClick={enhance}>
        {running?<LoaderCircle size={15} className="spin"/>:<Sparkles size={15}/>}
        {running?'Qwen is writing clip metadata…':`AI Enhance All ${p.clips.length} Clips`}
      </button>
    </div>
    {running&&<span className="hint">Running local Qwen on each clip. This may take a few minutes on an M2. Don't re-analyze meanwhile.</span>}
    {message&&<span className="hint" role="status">{message}</span>}
    {error&&<span className="form-error" role="alert">{error}</span>}
  </div>;
}
