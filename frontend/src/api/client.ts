import type {components} from './generated';
export type Video=components['schemas']['VideoDTO'];
export type Analysis=components['schemas']['AnalysisDTO'];
export type Detail=components['schemas']['AnalysisDetail'];
export type Stats=components['schemas']['StatsDTO'];
export type Segment=components['schemas']['SegmentDTO'];
export type Doc=components['schemas']['DocumentDTO'];
export type Chunk=components['schemas']['ChunkDTO'];
export type Message=components['schemas']['MessageDTO'];
export type Answer=components['schemas']['Answer'];
export type Evidence=components['schemas']['KnowledgeEvidence'];
export type Page<T>={items:T[];next_cursor:string|null};
export async function api<T>(url:string,options:RequestInit={}):Promise<T>{
 const headers=new Headers(options.headers);
 if(options.body && !(options.body instanceof FormData))headers.set('Content-Type','application/json');
 const res=await fetch('/api'+url,{...options,headers});
 const data=await res.json();
 if(!res.ok)throw new Error(data.error?.message||`请求失败 ${res.status}`);
 return data.data as T;
}
export const post=<T>(url:string,body:unknown)=>api<T>(url,{method:'POST',body:JSON.stringify(body)});
