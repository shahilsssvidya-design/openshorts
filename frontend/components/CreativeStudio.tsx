'use client';

import React, {useEffect, useState} from 'react';
import {ArrowDownToLine, Check, Copy, Image as ImageIcon, LoaderCircle, Sparkles, WandSparkles} from 'lucide-react';
import {API,request,post,type Clip} from '@/lib/api';

type Ideas = {
  titles:string[];
  thumbnail_texts:string[];
  hook:string;
  description:string;
  hashtags:string[];
  generated_at:string;
  tone:string;
  language:string;
};
type CreativeState = {
  ideas:Ideas|null;
  selected:{title:string;hook:string;description:string;hashtags:string[];thumbnail_variant:number;thumbnail_text:string};
};

type Props={
  projectId:string;
  clip:Clip;
  token:string;
  onApply:(changes:Partial<Clip>)=>void;
};

function AuthThumbnail({path,token,alt}:{path:string;token:string;alt:string}){
  const [src,setSrc]=useState<string|null>(null);
  useEffect(()=>{
    let alive=true,objectUrl:string|null=null;
    setSrc(null);
    fetch(API+'/api'+path,{headers:{Authorization:'Bearer '+token},cache:'no-store'})
      .then(r=>{if(!r.ok)throw new Error('Preview unavailable');return r.blob()})
      .then(b=>{objectUrl=URL.createObjectURL(b);if(alive)setSrc(objectUrl);else URL.revokeObjectURL(objectUrl)})
      .catch(()=>{if(alive)setSrc(null)});
    return()=>{alive=false;if(objectUrl)URL.revokeObjectURL(objectUrl)};
  },[path,token]);
  return src?<img src={src} alt={alt}/>:<div className="os-creative-missing"><ImageIcon size={25}/><span>Preview loading…</span></div>;
}

export default function CreativeStudio({projectId,clip,token,onApply}:Props){
  const [ideas,setIdeas]=useState<Ideas|null>(null);
  const [tone,setTone]=useState('curiosity');
  const [language,setLanguage]=useState('English');
  const [audience,setAudience]=useState('');
  const [generating,setGenerating]=useState(false),[saving,setSaving]=useState(false);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState(''),[message,setMessage]=useState('');
  const [title,setTitle]=useState(clip.title||'');
  const [description,setDescription]=useState(clip.description||'');
  const [hook,setHook]=useState(clip.hook||'');
  const [hashtags,setHashtags]=useState((clip.hashtags||[]).join(' '));
  const [variant,setVariant]=useState(clip.thumbnail_variant||1);
  const [thumbnailText,setThumbnailText]=useState(clip.thumbnail_text||'');
  const [version,setVersion]=useState(0);
  const root='/projects/'+encodeURIComponent(projectId)+'/clips/'+encodeURIComponent(clip.id)+'/creative';

  useEffect(()=>{
    let alive=true;
    setLoading(true);setError('');setMessage('');setIdeas(null);
    setTitle(clip.title||'');setDescription(clip.description||'');setHook(clip.hook||'');
    setHashtags((clip.hashtags||[]).join(' '));setVariant(clip.thumbnail_variant||1);
    setThumbnailText(clip.thumbnail_text||'');
    request<CreativeState>(root).then(d=>{
      if(!alive)return;
      setIdeas(d.ideas);
      if(d.ideas){setTone(d.ideas.tone||'curiosity');setLanguage(d.ideas.language||'English');}
      setTitle(d.selected.title||'');setHook(d.selected.hook||'');
      setDescription(d.selected.description||'');setHashtags((d.selected.hashtags||[]).join(' '));
      const v=d.selected.thumbnail_variant||1;setVariant(v);
      setThumbnailText(d.selected.thumbnail_text||d.ideas?.thumbnail_texts?.[v-1]||'');
    }).catch(e=>{if(alive)setError((e as Error).message)}).finally(()=>{if(alive)setLoading(false)});
    return()=>{alive=false};
    // We intentionally reload only when a different clip is opened.
  },[projectId,clip.id]);

  async function generate(){
    setGenerating(true);setError('');setMessage('');
    try{
      const result=await post<{ideas:Ideas}>(root+'/generate',{tone,language,audience});
      setIdeas(result.ideas);setTitle(result.ideas.titles[0]);
      setDescription(result.ideas.description);setHook(result.ideas.hook);
      setHashtags(result.ideas.hashtags.join(' '));setVariant(1);
      setThumbnailText(result.ideas.thumbnail_texts[0]);setVersion(x=>x+1);
      setMessage('Three new ideas and three real-frame thumbnail designs generated. Review and apply your favorite.');
    }catch(e){setError((e as Error).message)}finally{setGenerating(false)}
  }

  async function apply(){
    if(!ideas)return;
    setSaving(true);setError('');setMessage('');
    try{
      const cleaned=hashtags.split(/[\s,]+/).filter(Boolean).map(h=>h.startsWith('#')?h:'#'+h);
      const result=await post<{clip:Clip;saved:boolean}>(root+'/apply',{
        title:title.trim(),description:description.trim(),hook:hook.trim(),hashtags:cleaned,
        thumbnail_variant:variant,thumbnail_text:thumbnailText.trim()
      });
      onApply(result.clip);
      setVersion(x=>x+1);
      setMessage('Saved! Your clip now uses this title, hook, description and hashtags. You can download the selected thumbnail below.');
    }catch(e){setError((e as Error).message)}finally{setSaving(false)}
  }

  async function downloadThumbnail(){
    setError('');
    try{
      const r=await fetch(API+'/api'+root+'/thumbnail/'+variant,{headers:{Authorization:'Bearer '+token},cache:'no-store'});
      if(!r.ok)throw new Error('Thumbnail not available. Generate options first.');
      const url=URL.createObjectURL(await r.blob());
      const anchor=document.createElement('a');anchor.href=url;
      anchor.download=(title||'Short').replace(/[^\w -]/g,'_').slice(0,60)+'_thumbnail.jpg';
      document.body.appendChild(anchor);anchor.click();anchor.remove();
      window.setTimeout(()=>URL.revokeObjectURL(url),12000);
    }catch(e){setError((e as Error).message)}
  }

  const busy=generating||saving;
  return <div className="os-creative-studio">
    <div className="os-creative-heading"><div className="os-creative-orb"><WandSparkles size={22}/></div>
      <div><h3>AI Content Studio</h3><p>Real title ideas and thumbnails, grounded in this clip. Powered by your local Ollama model.</p></div></div>
    <div className="os-creative-setup">
      <label>Tone<select disabled={busy} value={tone} onChange={e=>setTone(e.target.value)}>
        <option value="curiosity">Curiosity / compelling</option>
        <option value="funny">Funny / playful</option>
        <option value="dramatic">Dramatic / high-energy</option>
        <option value="professional">Professional / clear</option>
      </select></label>
      <label>Language<select disabled={busy} value={language} onChange={e=>setLanguage(e.target.value)}>
        <option>English</option><option>Hinglish</option><option>Hindi</option>
      </select></label>
      <label className="os-creative-audience">Target audience (optional)<input disabled={busy} value={audience} onChange={e=>setAudience(e.target.value)} maxLength={100} placeholder="e.g. gaming fans, tech enthusiasts"/></label>
    </div>
    <button type="button" className="btn btn-primary os-creative-generate" disabled={busy||loading} onClick={generate}>
      {generating?<LoaderCircle className="spin" size={17}/>:<Sparkles size={17}/>}
      {generating?'Qwen is writing ideas and designing thumbnails…':ideas?'Regenerate with AI':'Generate titles, description, hashtags & thumbnails'}
    </button>
    {!ideas&&!loading&&<p className="os-creative-note">The old title and description are transcript extracts. Generate with Qwen to replace them with creative, truthful options. No paid API required.</p>}
    {loading&&<p className="os-creative-note">Loading saved creative ideas…</p>}
    {ideas&&<div className="os-creative-results">
      <div className="os-creative-section-title">Choose a title</div>
      <div className="os-creative-title-options">{ideas.titles.map((candidate,i)=><button type="button" key={i} className={title===candidate?'selected':''} onClick={()=>setTitle(candidate)}><span>0{i+1}</span>{candidate}</button>)}</div>
      <label className="os-creative-field">Final title — editable<input maxLength={100} value={title} onChange={e=>setTitle(e.target.value)}/></label>
      <label className="os-creative-field">Short-form hook<textarea rows={2} maxLength={220} value={hook} onChange={e=>setHook(e.target.value)}/></label>
      <label className="os-creative-field">YouTube description<textarea rows={4} maxLength={3000} value={description} onChange={e=>setDescription(e.target.value)}/></label>
      <label className="os-creative-field">Hashtags<input maxLength={350} value={hashtags} onChange={e=>setHashtags(e.target.value)} placeholder="#Shorts #Gaming #FunnyMoments"/></label>
      <div className="os-creative-section-title">Choose a thumbnail — frames from your actual clip</div>
      <div className="os-creative-thumbnails">{ideas.thumbnail_texts.map((text,i)=><button type="button" key={i} className={variant===i+1?'selected':''} onClick={()=>{setVariant(i+1);setThumbnailText(text)}} aria-pressed={variant===i+1}>
        <AuthThumbnail path={root+'/thumbnail/'+(i+1)+'?v='+ideas.generated_at+'-'+version} token={token} alt={'Thumbnail '+(i+1)+': '+text}/>
        <span>{variant===i+1?<Check size={14}/>:<ImageIcon size={14}/>} Concept {i+1} · {text}</span>
      </button>)}</div>
      <label className="os-creative-field">Selected thumbnail headline — editable<input value={thumbnailText} maxLength={90} onChange={e=>setThumbnailText(e.target.value)}/></label>
      <p className="os-creative-note">Changing thumbnail text takes effect when you save the package. Thumbnails are 9:16 JPEGs made from real frames; no imaginary faces or scenes.</p>
      <div className="os-creative-actions">
        <button className="btn btn-primary" type="button" disabled={busy||!title.trim()||!description.trim()||!hook.trim()||!thumbnailText.trim()} onClick={apply}>{saving?<LoaderCircle className="spin" size={16}/>:<Check size={16}/>} {saving?'Saving package…':'Apply to clip & save'}</button>
        <button className="btn btn-outline" type="button" disabled={busy} onClick={downloadThumbnail}><ArrowDownToLine size={16}/> Download thumbnail</button>
        <button className="btn btn-outline" type="button" onClick={()=>navigator.clipboard.writeText([title,'',description,'',hashtags].join('\n'))}><Copy size={15}/> Copy YouTube text</button>
      </div>
    </div>}
    {message&&<div className="os-creative-success" role="status"><Check size={16}/>{message}</div>}
    {error&&<div className="os-creative-error" role="alert">{error}</div>}
    <p className="os-creative-disclaimer">AI suggests packaging; it cannot guarantee views or virality. Review the claims and footage before publishing. YouTube thumbnail upload is separate from video upload.</p>
  </div>
}
