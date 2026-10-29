import {useEffect,useRef,useState} from 'react';
import {Link,useSearchParams} from 'react-router-dom';
import {ArrowRight,BookOpen,Database,Film,MessageSquare,Plus,RefreshCw,ShieldCheck} from 'lucide-react';
import {api,type Analysis,type Video,type Page,type Evidence,type Chunk} from './api/client';
import type {Chat} from './App';

type VideoOption={video:Video;analysis:Analysis};
type Source=Evidence|Chunk;

export default function QuestionPage({showSource,ChatPanel}:{showSource:(s:Source)=>void;ChatPanel:typeof Chat}){
 const [params,setParams]=useSearchParams();
 const analysisId=params.get('analysis');
 const [options,setOptions]=useState<VideoOption[]>([]);
 const [loading,setLoading]=useState(true);
 const [error,setError]=useState('');
 const [tracks,setTracks]=useState<{track_id:string;display_name:string}[]>([]);
 const [track,setTrack]=useState<string|null>(null);
 const [conversation,setConversation]=useState(0);
 const player=useRef<HTMLVideoElement>(null);
 const stop=useRef<number|null>(null);
 const selected=options.find(o=>o.analysis.id===analysisId);

 async function load(){
  setLoading(true);setError('');
  try{
   const videos=await api<Page<Video>>('/videos?limit=100');
   const results=await Promise.allSettled(videos.items.map(video=>api<{analyses:Analysis[]}>(`/videos/${video.id}`).then(d=>d.analyses.filter(a=>a.status==='succeeded').map(analysis=>({video,analysis})))));
   setOptions(results.flatMap(r=>r.status==='fulfilled'?r.value:[]));
   if(results.some(r=>r.status==='rejected'))setError('部分视频分析未能加载，可刷新重试。');
  }catch(e){setError(String(e))}finally{setLoading(false)}
 }
 useEffect(()=>{load()},[]);
 useEffect(()=>{
  let active=true;setTracks([]);setTrack(null);stop.current=null;
  if(analysisId)api<Page<{track_id:string;display_name:string}>>(`/analyses/${analysisId}/tracks`).then(d=>{if(active){setTracks(d.items);setTrack(d.items.length===1?d.items[0].track_id:null)}}).catch(e=>{if(active)setError(String(e))});
  return()=>{active=false};
 },[analysisId]);

 async function seek(segment:{start_s:number;end_s:number}){
  const video=player.current;if(!video)return;
  if(video.readyState===0)await new Promise<void>(resolve=>video.addEventListener('loadedmetadata',()=>resolve(),{once:true}));
  stop.current=segment.end_s;video.currentTime=segment.start_s;video.play().catch(()=>{});
 }
 function newConversation(){
  localStorage.removeItem(`cow-session-qa-${analysisId||'history'}`);
  setConversation(n=>n+1);
 }

 return <div className="qa-page">
  <div className="page-heading">
   <div><div className="eyebrow">ASK YOUR DAIRY ASSISTANT</div><h1>智能问答<span className="heading-dot" aria-hidden="true">.</span></h1><p>直接提问，查询奶牛行为记录、养殖资料与视频证据。</p></div>
   <button className="secondary" onClick={newConversation}><Plus size={16}/>新建对话</button>
  </div>
  <div className="qa-layout">
   <aside className="qa-side">
    <section className="panel qa-scope">
     <div className="panel-heading"><h2><MessageSquare size={17}/>问答范围</h2><button className="icon-button" onClick={load} aria-label="刷新问答数据"><RefreshCw size={15}/></button></div>
     <div className="qa-side-content">
      <label>选择要查询的数据<select aria-label="问答范围" value={analysisId||'history'} onChange={e=>{setError('');setParams(e.target.value==='history'?{}:{analysis:e.target.value})}}>
       <option value="history">五天行为记录与养殖知识</option>
       <optgroup label="已完成的视频分析">{options.map(o=><option key={o.analysis.id} value={o.analysis.id}>{o.video.original_name} · {o.analysis.id.slice(0,6)}</option>)}</optgroup>
      </select></label>
      {loading&&<p className="muted">正在加载可用的视频分析…</p>}
      {!analysisId?<>
       <div className="qa-data-card"><Database size={19}/><div><strong>五天行为记录</strong><p>2023.07.21—07.25 · 16头牛</p></div></div>
       <div className="qa-data-card"><BookOpen size={19}/><div><strong>养殖知识库</strong><p>检索原文、来源与版本</p></div></div>
       <p className="qa-hint">问题中可指定牛号、日期和时间，例如“查询1号牛2023-07-25 10:00到10:30的采食事件”。</p>
       <Link className="text-link" to="/history">查看五天记录 <ArrowRight size={13}/></Link>
      </>:selected?<>
       <div className="qa-data-card"><Film size={19}/><div><strong>{selected.video.original_name}</strong><p>{selected.video.duration_s}秒 · {selected.analysis.source_kind==='mock'?'模拟分析':'模型结果'}</p></div></div>
       <video key={selected.video.id} ref={player} controls preload="metadata" src={selected.video.media_url} aria-label="问答视频证据" onTimeUpdate={()=>{const v=player.current;if(v&&stop.current!==null&&v.currentTime>=stop.current){v.pause();stop.current=null}}}/>
       <label>当前目标<select aria-label="问答目标" value={track||''} onChange={e=>setTrack(e.target.value||null)}><option value="">所有目标</option>{tracks.map(t=><option key={t.track_id} value={t.track_id}>{t.display_name}</option>)}</select></label>
       <p className="qa-hint">点击回答中的片段证据，即可在这里定位播放。可在问题中指定视频内的秒数范围。</p>
       <Link className="text-link" to={`/videos/${selected.video.id}/analyses/${selected.analysis.id}`}>打开完整视频分析 <ArrowRight size={13}/></Link>
      </>:!loading?<p className="qa-hint">所选分析不可用，请选择已有的成功分析，或先上传视频。</p>:null}
     </div>
    </section>
    <section className="panel qa-guide"><ShieldCheck size={21}/><h3>回答有据可查</h3><p>事实卡展示工具统计，资料卡可打开原文。回答会标明数据来源和运行模式。</p><p>历史模型标签未人工复核；模拟视频统计不代表真实识别。</p></section>
    <Link className="button secondary qa-video-link" to="/videos"><Film size={16}/>上传或分析视频</Link>
   </aside>
   <div className="qa-conversation">
    {error&&<div className="error" role="alert">{error}</div>}
    <ChatPanel key={`${analysisId||'history'}-${conversation}`} analysisId={analysisId} track={track} range={null} showSource={showSource} seek={seek} storageScope="qa" disabled={Boolean(analysisId&&!selected)} suggestions={analysisId?['这头牛采食了多久，占比是多少？','分析采食情况，给我片段和统计依据','为什么有一段是灰色？']:['统计1号牛2023-07-21到2023-07-25每天的采食记录','比较1号牛这五天的采食变化','养殖知识：饮水有哪些注意事项和依据？']}/>
   </div>
  </div>
 </div>
}
