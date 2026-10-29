"""Pure interval statistics, semantic validation, and scoped evidence assembly."""
import math
import json
from jsonschema import Draft202012Validator
from .config import ROOT

SCHEMA=json.loads((ROOT/'docs/cow-agent-brief/02-模型结果协议.schema.json').read_text())
PROTOCOL=json.loads((ROOT/'docs/cow-agent-brief/07-智能体工具协议.schema.json').read_text())
EPS=1e-6

def overlap(i,a,b):return max(0,min(i['end_s'],b)-max(i['start_s'],a))

def union(intervals,duration):
    out=[];last=-1
    for i in intervals:
        a,b=i['start_s'],i['end_s']
        if not all(math.isfinite(x) for x in [a,b]) or not 0<=a<b<=duration or a<last-EPS:raise ValueError('区间越界、无序或重叠')
        if out and abs(out[-1][1]-a)<=EPS:out[-1][1]=b
        else:out.append([a,b])
        last=b
    return out

def validate_analysis_result(r,video,context):
    def finite(v):
        if isinstance(v,float) and not math.isfinite(v):raise ValueError('结果包含非有限数值')
        if isinstance(v,dict):
            for x in v.values():finite(x)
        if isinstance(v,list):
            for x in v:finite(x)
    finite(r)
    try:Draft202012Validator(SCHEMA).validate(r)
    except Exception as e:raise ValueError('结果不符合 JSON 协议') from e
    if r['video_id']!=video['id'] or r['analysis_id']!=context['id'] or r['video_sha256']!=video['sha256']:raise ValueError('视频、任务或指纹不匹配')
    d=r['duration_s']
    if not math.isfinite(d) or not math.isfinite(r['sample_interval_s']) or abs(d-video['duration_s'])>max(.1,1/video['fps']):raise ValueError('媒体时长不匹配')
    if context['provider'] in ['mock','command'] and r['source_kind']!=('mock' if context['provider']=='mock' else 'model'):raise ValueError('来源类型与适配器不匹配')
    codes=[x['code'] for x in r['behavior_catalog']]; classes=[x.get('source_class_id') for x in r['behavior_catalog'] if x.get('source_class_id') is not None]
    if len(set(codes))!=len(codes) or len(set(classes))!=len(classes):raise ValueError('类别重复')
    tracks={}; segids=set()
    for t in r['tracks']:
        if t['track_id'] in tracks:raise ValueError('轨迹重复')
        tracks[t['track_id']]=t
        a=union(t['observed_intervals'],d); b=union(t['segments'],d)
        if len(a)!=len(b) or any(abs(x-y)>EPS for i,j in zip(a,b) for x,y in zip(i,j)):raise ValueError('行为区间并集必须等于观察区间并集')
        for s in t['segments']:
            if s['segment_id'] in segids or s['behavior'] not in codes+['unknown']:raise ValueError('片段 ID 重复或行为未知')
            segids.add(s['segment_id'])
    for det in r['detections']:
        t=tracks.get(det['track_id']); x,y,w,h=det['bbox_xywh_norm']; ts=det['time_s']
        if not t or not math.isfinite(ts) or not 0<=ts<d or not any(i['start_s']<=ts<i['end_s'] for i in t['observed_intervals']):raise ValueError('检测时间或轨迹无效')
        if det['behavior'] not in codes+['unknown'] or w<=0 or h<=0 or x-w/2<0 or x+w/2>1 or y-h/2<0 or y+h/2>1:raise ValueError('检测框或类别无效')
    return r

def compute_track_stats(result,track_id,start_s,end_s):
    if not all(math.isfinite(x) for x in [start_s,end_s]) or not 0<=start_s<end_s<=result['duration_s']:raise ValueError('时间范围无效')
    t=next((t for t in result['tracks'] if t['track_id']==track_id),None)
    if t is None:raise ValueError('轨迹不存在')
    observed=sum(overlap(i,start_s,end_s) for i in t['observed_intervals'])
    unknown=sum(overlap(i,start_s,end_s) for i in t['segments'] if i['behavior']=='unknown')
    classified=observed-unknown
    behaviors=[]
    for c in result['behavior_catalog']:
        seg=[s for s in t['segments'] if s['behavior']==c['code'] and overlap(s,start_s,end_s)>0]
        duration=sum(overlap(s,start_s,end_s) for s in seg)
        behaviors.append(dict(code=c['code'],label=c['label'],duration_s=duration,ratio=duration/classified if classified else None,segment_count=len(seg)))
    return dict(analysis_id=result['analysis_id'],track_id=track_id,range=dict(start_s=start_s,end_s=end_s),window_duration_s=end_s-start_s,observed_duration_s=observed,unknown_duration_s=unknown,classified_duration_s=classified,unobserved_duration_s=end_s-start_s-observed,observation_coverage=observed/(end_s-start_s),classification_coverage=classified/observed if observed else None,behaviors=behaviors)

def assemble_answer(draft,registry,context):
    Draft202012Validator(PROTOCOL).validate(draft)
    out=dict(answer_text=draft['answer_text'],limitations=draft['limitations'])
    for field,kind,target in [('fact_refs','fact','facts'),('video_refs','video','video_evidence'),('knowledge_refs','knowledge','knowledge_evidence')]:
        out[target]=[]
        for ref in draft[field]:
            e=registry.get(ref)
            if not e or e['kind']!=kind or e['session_id']!=context['session_id'] or e['analysis_id']!=context['analysis_id']:raise ValueError('引用不属于当前会话和分析')
            out[target].append(e['payload'])
    return out
