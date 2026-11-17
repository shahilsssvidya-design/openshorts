'use client';

import {useEffect, useState} from 'react';
import {request, post} from '@/lib/api';

type Connection = {configured: boolean; connected: boolean; scope: string};
type UploadRecord = {
  id: string; status: 'queued'|'uploading'|'published'|'failed';
  progress: number; video_id: string|null; youtube_url: string|null;
  error: string|null; privacy: string; title: string;
};

export function YouTubeConnection(){
  const [status,setStatus]=useState<Connection|null>(null);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const refresh=async()=>{try{setStatus(await request<Connection>('/youtube/status'));setError('')}catch(e){setError((e as Error).message)}};
  useEffect(()=>{void refresh()},[]);
  async function connect(){
    setBusy(true);setError('');
    try{
      const response=await post<{authorization_url:string}>('/youtube/authorize',{});
      window.location.assign(response.authorization_url);
    }catch(e){setError((e as Error).message);setBusy(false)}
  }
  async function disconnect(){
    if(!window.confirm('Disconnect YouTube from OpenShorts? Existing YouTube uploads will remain on your channel.'))return;
    setBusy(true);setError('');
    try{await request('/youtube/connection',{method:'DELETE'});await refresh()}
    catch(e){setError((e as Error).message)}finally{setBusy(false)}
  }
  return <div className="settings-card yt-connect-card">
    <h2><span className="yt-mark">▶</span> YouTube publishing</h2>
    <p>Upload completed Shorts directly to your own YouTube channel. Google authorization is stored securely on the backend, not in your browser.</p>
    {status? <>
      <div className="yt-status"><span className={'yt-dot '+(status.connected?'connected':'')}/>
        {status.connected?'YouTube account connected':status.configured?'Ready to connect':'YouTube API not configured'}
      </div>
      {!status.configured?<p className="hint">Add your Google OAuth Web application client ID and secret to the backend environment, then restart OpenShorts. See the upgrade README.</p>:null}
      {status.connected?
        <button type="button" disabled={busy} onClick={disconnect} className="btn btn-outline">{busy?'Disconnecting…':'Disconnect YouTube'}</button>:
        <button type="button" disabled={busy||!status.configured} onClick={connect} className="btn btn-primary">{busy?'Opening Google…':'Connect YouTube'}</button>
      }
    </>:<p className="hint">Checking YouTube connection…</p>}
    {error&&<p role="alert" className="form-error">{error}</p>}
    <p className="hint">OpenShorts requests only upload permission. Google may ask you to verify or authorize this development app. You can revoke access in your Google Account.</p>
  </div>
}

export function YouTubePublisher({exportId,clipTitle,clipDescription=''}:{exportId:string;clipTitle:string;clipDescription?:string}){
  const [open,setOpen]=useState(false);
  const [connection,setConnection]=useState<Connection|null>(null);
  const [title,setTitle]=useState(clipTitle.slice(0,100));
  const [description,setDescription]=useState(clipDescription.slice(0,5000));
  const [privacy,setPrivacy]=useState<'private'|'unlisted'|'public'>('private');
  const [madeForKids,setMadeForKids]=useState<'unknown'|'yes'|'no'>('unknown');
  const [rights,setRights]=useState(false);
  const [status,setStatus]=useState<UploadRecord|null>(null);
  const [error,setError]=useState('');
  const [busy,setBusy]=useState(false);
  useEffect(()=>{let active=true;
    request<UploadRecord|null>('/youtube/exports/'+exportId+'/upload')
      .then(x=>{if(active)setStatus(x)}).catch(()=>{});
    return()=>{active=false};
  },[exportId]);
  useEffect(()=>{if(!status||!['queued','uploading'].includes(status.status))return;
    const id=window.setInterval(()=>{
      request<UploadRecord>('/youtube/uploads/'+status.id).then(setStatus).catch(e=>setError((e as Error).message));
    },1800);
    return()=>window.clearInterval(id);
  },[status?.id,status?.status]);
  async function show(){
    setOpen(true);setError('');
    try{setConnection(await request<Connection>('/youtube/status'))}
    catch(e){setError((e as Error).message)}
  }
  async function publish(){
    if(!connection?.connected){setError('Connect YouTube from Account & API first.');return}
    if(!rights||madeForKids==='unknown'||!title.trim()){setError('Enter a title, choose the audience, and confirm upload rights.');return}
    if(privacy==='public'&&!window.confirm('Publish this Short publicly on YouTube now?'))return;
    setBusy(true);setError('');
    try{
      const result=await post<UploadRecord>('/youtube/uploads',{
        export_id:exportId,title:title.trim(),description,privacy,
        made_for_kids:madeForKids==='yes',rights_confirmed:rights
      });
      setStatus(result);
    }catch(e){setError((e as Error).message)}finally{setBusy(false)}
  }
  const running=status?.status==='queued'||status?.status==='uploading';
  return <>
    <button className="btn btn-outline btn-sm" type="button" onClick={show}>
      <span className="yt-mark">▶</span> {status?.status==='published'?'YouTube video':'Publish to YouTube'}
    </button>
    {open&&<div className="yt-modal-backdrop" role="presentation" onMouseDown={e=>{if(e.target===e.currentTarget)setOpen(false)}}>
      <div className="yt-modal" role="dialog" aria-modal="true" aria-label="Publish to YouTube">
        <div className="yt-modal-head"><div><span className="yt-eyebrow">OPENSHORTS / DISTRIBUTE</span><h2>Publish to YouTube</h2></div>
          <button type="button" className="yt-close" aria-label="Close" onClick={()=>setOpen(false)}>×</button></div>
        {status?.status==='published'?<div className="yt-success">
          <h3>Uploaded successfully</h3><p>Your Short was sent to YouTube with {status.privacy} visibility.</p>
          {status.youtube_url&&<a href={status.youtube_url} target="_blank" rel="noopener noreferrer" className="btn btn-primary">View on YouTube ↗</a>}
        </div>:running?<div className="yt-progress"><h3>Uploading your Short…</h3>
          <div className="yt-track"><div style={{width:status.progress+'%'}}/></div>
          <p>{status.progress}% uploaded. Keep OpenShorts running until this finishes.</p>
          <p className="hint">You can close this dialog and reopen it later to check the upload.</p>
        </div>:<>
          {status?.status==='failed'&&<div className="yt-error">Previous upload failed: {status.error}
            <p>Check YouTube Studio before retrying; a network failure can sometimes occur after a video has been received.</p>
          </div>}
          {connection&&!connection.connected&&<div className="yt-error">Connect your YouTube account under <a href="/account">Account & API</a> before publishing.</div>}
          {!connection&&!error&&<p>Checking your YouTube connection…</p>}
          <label className="yt-label">Title<input maxLength={100} value={title} onChange={e=>setTitle(e.target.value)} placeholder="An unforgettable moment…"/></label>
          <label className="yt-label">Description<textarea rows={4} maxLength={5000} value={description} onChange={e=>setDescription(e.target.value)} placeholder="Describe this Short…"/></label>
          <div className="yt-grid">
            <label className="yt-label">Visibility
              <select value={privacy} onChange={e=>setPrivacy(e.target.value as typeof privacy)}>
                <option value="private">Private — only you</option>
                <option value="unlisted">Unlisted — link only</option>
                <option value="public">Public — everyone</option>
              </select>
            </label>
            <label className="yt-label">Audience
              <select value={madeForKids} onChange={e=>setMadeForKids(e.target.value as typeof madeForKids)}>
                <option value="unknown">Choose audience…</option>
                <option value="no">Not made for kids</option>
                <option value="yes">Made for kids</option>
              </select>
            </label>
          </div>
          <label className="yt-rights"><input type="checkbox" checked={rights} onChange={e=>setRights(e.target.checked)}/>
            <span>I own this content or have permission to publish it on YouTube.</span></label>
          <p className="hint">Uploads only after you press Publish. Start with Private when testing. YouTube determines Shorts eligibility after upload.</p>
          {error&&<p role="alert" className="yt-error">{error}</p>}
          <button className="btn btn-primary yt-submit" disabled={busy||!connection?.connected||!rights||madeForKids==='unknown'||!title.trim()} onClick={publish}>
            {busy?'Starting upload…':privacy==='public'?'Publish publicly':'Upload as '+privacy}
          </button>
        </>}
      </div>
    </div>}
  </>;
}
