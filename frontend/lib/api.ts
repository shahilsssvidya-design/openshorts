export const API=process.env.NEXT_PUBLIC_API_URL||'http://localhost:8000';
export type Segment={start:number;end:number;text:string;words?:{start:number;end:number;text:string}[]};
export type Clip={id:string;start:number;end:number;score:number;ranking_method?:"ai"|"heuristic";quality_metrics?:Record<string,number>;title:string;hook:string;description:string;reason:string;style:string;position:string;color:string;caption_scale:number;captions:boolean;hashtags?:string[];thumbnail_variant?:number;thumbnail_text?:string;gameplay_kind?:"minecraft"|"subway";layout_mode?:"crop"|"fit"|"split";top_fill?:"solid"|"gradient"|"blur";top_color_a?:string;top_color_b?:string;bottom_fill?:"solid"|"gradient"|"blur";bottom_color_a?:string;bottom_color_b?:string;focus_mode?:"auto"|"center"|"left"|"right";caption_language?:"original"|"hinglish"|"english";music_track?:string;music_volume?:number;original_volume?:number};
export type Project={id:string;title:string;status:string;progress:number;error:string|null;source:string|null;source_url:string|null;duration:number;width:number;height:number;clips:Clip[];chat_bursts?:number;transcript:Segment[];created_at:string;updated_at:string};
export type Export={id:string;clip_id:string;created_at:string};
export async function request<T>(path:string,opts:RequestInit={},auth=true):Promise<T>{
 const token=typeof window!=='undefined'?localStorage.getItem('os_token'):null;
 const headers=new Headers(opts.headers);
 if(auth&&token)headers.set('Authorization','Bearer '+token);
 if(opts.body&&!(opts.body instanceof FormData))headers.set('Content-Type','application/json');
 let response:Response;
 try{response=await fetch(API+'/api'+path,{...opts,headers,cache:'no-store'});}catch{throw new Error('Cannot connect to the API. Is the backend running on port 8000?')}
 if(!response.ok){let detail='Request failed ('+response.status+')';try{const body=await response.json();detail=typeof body.detail==='string'?body.detail:JSON.stringify(body.detail||body);}catch{} if(response.status===401&&auth&&typeof window!=='undefined'){localStorage.removeItem('os_token')}throw new Error(detail)}
 return response.json();
}
export const post=<T,>(p:string,body:object)=>request<T>(p,{method:'POST',body:JSON.stringify(body)});
export const patch=<T,>(p:string,body:object)=>request<T>(p,{method:'PATCH',body:JSON.stringify(body)});
export function formatTime(t:number){if(!Number.isFinite(t))return '0:00';const m=Math.floor(t/60),s=Math.floor(t%60);return `${m}:${String(s).padStart(2,'0')}`}
export function duration(t:number){if(t<60)return `${Math.round(t)}s`;return formatTime(t)}
