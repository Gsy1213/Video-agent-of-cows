import hashlib,json,logging,os,threading,time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime,timezone
from pathlib import Path
from typing import Annotated
from fastapi import FastAPI,File,Form,UploadFile,Request,Query,Header
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse,FileResponse,Response
from sqlalchemy import select,func
from sqlalchemy.exc import IntegrityError
from .config import ROOT,DATA,LLM,RETRIEVAL,HISTORY
from .db import *
from .schemas import *
from .core import compute_track_stats
from .pagination import paginate
from . import rag,media
from .history import query_history,sanitize_history

POOL=ThreadPoolExecutor(max_workers=1,thread_name_prefix='knowledge-index')
SESSION_LOCK=threading.Lock()
class APIError(Exception):
    def __init__(self,status,code,message,details=None):self.status=status;self.code=code;self.message=message;self.details=details
def fail(status,code,message):raise APIError(status,code,message)
@asynccontextmanager
async def lifespan(app):
    init()
    with Session.begin() as db:
        for v in db.scalars(select(Version).where(Version.status=='indexing')):v.status='failed';v.error_json={'code':'INDEX_INTERRUPTED','message':'索引中断，请重建'}
        pending=[(v.document_id,v.version) for v in db.scalars(select(Version).where(Version.status=='pending'))]
        # API restart closes in-flight turns explicitly, preserving failures.
        for t in db.scalars(select(Turn).where(Turn.status=='processing')):
            t.status='failed';m=db.get(Message,t.assistant_id)
            if m:m.status='failed';m.content_json={'text':'服务重启，对话中断，请用新消息重试。','answer':None}
    for d,v in pending:POOL.submit(rag.index_version,d,v)
    yield

app=FastAPI(title='牧知 · 奶牛行为分析智能体',version='1.0.0',lifespan=lifespan)
@app.middleware('http')
async def request_id(request,call_next):
    request.state.request_id=uid();response=await call_next(request);response.headers['X-Request-ID']=request.state.request_id;return response
@app.exception_handler(APIError)
async def api_error(req,e):return JSONResponse(status_code=e.status,content={'error':{'code':e.code,'message':e.message,'details':e.details},'request_id':req.state.request_id})
@app.exception_handler(RequestValidationError)
async def validation_error(req,e):return JSONResponse(status_code=422,content={'error':{'code':'INVALID_REQUEST','message':'请求参数无效，请检查目标、范围或文件。','details':None},'request_id':req.state.request_id})
@app.exception_handler(ValueError)
async def value_error(req,e):return JSONResponse(status_code=422,content={'error':{'code':'INVALID_INPUT','message':str(e)[:200],'details':None},'request_id':req.state.request_id})
@app.exception_handler(Exception)
async def internal_error(req,e):
    logging.exception('request %s',req.state.request_id)
    return JSONResponse(status_code=500,content={'error':{'code':'INTERNAL_ERROR','message':'服务执行失败，可凭请求编号查询日志。','details':None},'request_id':req.state.request_id})
def ok(req,data):return {'data':data,'request_id':req.state.request_id}
def get(db,model,id):
    row=db.get(model,id)
    if row is None:fail(404,'NOT_FOUND','记录不存在')
    return row
def video_dto(v):return dict(id=v.id,original_name=v.original_name,duration_s=v.duration_s,fps=v.fps,width=v.width,height=v.height,sha256=v.sha256,is_demo=v.is_demo,media_url=f'/api/videos/{v.id}/media',created_at=v.created_at)
def result(a):
    if a.status!='succeeded':fail(409,'ANALYSIS_NOT_READY','分析尚未成功完成')
    return json.loads((DATA/a.result_storage_key).read_text())
def analysis_dto(a):
    warnings=result(a)['warnings'] if a.status=='succeeded' else []
    return dict(id=a.id,video_id=a.video_id,provider=a.provider,status=a.status,source_kind=a.source_kind,model_version=a.model_version,progress=None,warnings=warnings,error=a.error_json,created_at=a.created_at,started_at=a.started_at,finished_at=a.finished_at)
def message_dto(m):return dict(id=m.id,session_id=m.session_id,client_message_id=m.client_message_id,role=m.role,status=m.status,text=m.content_json.get('text',''),answer=m.content_json.get('answer'),created_at=m.created_at)
def session_dto(s):return dict(id=s.id,analysis_id=s.analysis_id,selected_track_id=s.selected_track_id,selected_range=s.selected_range_json,created_at=s.created_at)
def selected(r,track_id,start_s,end_s):
    if (start_s is None)!=(end_s is None):fail(422,'INVALID_RANGE','起止时间须同时填写')
    a,b=(0,r['duration_s']) if start_s is None else (start_s,end_s)
    if not 0<=a<b<=r['duration_s']:fail(422,'INVALID_RANGE','时间范围超出视频或起点不小于终点')
    tracks=[t for t in r['tracks'] if track_id in [None,'*',t['track_id']]]
    if track_id not in [None,'*'] and not tracks:fail(404,'TRACK_NOT_FOUND','目标不存在于当前分析')
    return a,b,tracks

@app.get('/api/health')
def health(request:Request):
    with Session() as db:
        worker=db.get(Runtime,'worker');alive=bool(worker and (datetime.now(timezone.utc)-datetime.fromisoformat(worker.heartbeat_at)).total_seconds()<15)
    return ok(request,dict(status='ok',db_ready=True,worker_alive=alive,modes={'vision':os.getenv('VISION_PROVIDER','mock'),'llm':LLM,'retrieval':RETRIEVAL},providers={'vision':'configured' if os.getenv('VISION_COMMAND') else 'not_configured','llm':'configured' if all(os.getenv(k) for k in ['LLM_API_KEY','LLM_MODEL','LLM_BASE_URL']) else 'not_configured','embedding':'configured' if all(os.getenv(k) for k in ['EMBEDDING_API_KEY','EMBEDDING_MODEL','EMBEDDING_BASE_URL']) else 'not_configured'}))

@app.post('/api/videos',status_code=201,response_model=Envelope[VideoDTO])
def upload_video(request:Request,file:UploadFile=File(...)):
    key=f'videos/{uid()}.mp4';path=DATA/key;total=0
    try:
        with path.open('wb') as f:
            while block:=file.file.read(1024*1024):
                total+=len(block)
                if total>float(os.getenv('MAX_VIDEO_MB','500'))*1024**2:fail(413,'FILE_TOO_LARGE','视频超过体积上限')
                f.write(block)
        meta=media.probe(path)
        if meta['duration_s']>float(os.getenv('MAX_VIDEO_SECONDS','600')):fail(422,'VIDEO_TOO_LONG','视频超过时长上限')
        with Session.begin() as db:
            v=Video(original_name=Path(file.filename or 'video.mp4').name,storage_key=key,**meta);db.add(v);db.flush();dto=video_dto(v)
        return ok(request,dto)
    except Exception:
        path.unlink(missing_ok=True);raise

@app.post('/api/demo',status_code=201,response_model=Envelope[VideoDTO])
def seed_demo(request:Request):
    path,meta=media.demo_media()
    with Session.begin() as db:
        name=Path(os.getenv('DEMO_VIDEO_PATH','/data2/geshuyu/5.mp4')).name
        v=Video(original_name=f'演示视频 · {name}',storage_key=str(path.relative_to(DATA)),is_demo=True,**meta);db.add(v);db.flush();dto=video_dto(v)
    return ok(request,dto)

@app.get('/api/videos',response_model=Envelope[Page[VideoDTO]])
def list_videos(request:Request,limit:int=Query(20,ge=1,le=100),cursor:str|None=None):
    with Session() as db:rows=[video_dto(v) for v in db.scalars(select(Video).order_by(Video.created_at.desc(),Video.id))]
    return ok(request,paginate(rows,limit,cursor))
@app.get('/api/videos/{id}',response_model=Envelope[VideoDetail])
def video_detail(id:str,request:Request):
    with Session() as db:return ok(request,dict(video=video_dto(get(db,Video,id)),analyses=[analysis_dto(a) for a in db.scalars(select(Analysis).where(Analysis.video_id==id).order_by(Analysis.created_at.desc()))]))
@app.get('/api/videos/{id}/media')
def get_media(id:str):
    with Session() as db:v=get(db,Video,id)
    return FileResponse(DATA/v.storage_key,media_type='video/mp4')

def create_analysis(db,v,provider,scenario,key,input_hash,external=None):
    if key:
        old=db.scalar(select(Analysis).where(Analysis.idempotency_key==key))
        if old:
            if old.input_hash!=input_hash or old.video_id!=v.id:fail(409,'IDEMPOTENCY_CONFLICT','同一请求键对应不同输入')
            return old
    a=Analysis(video_id=v.id,provider=provider,scenario=scenario,idempotency_key=key,input_hash=input_hash,external_analysis_id=external,source_kind='mock' if provider=='mock' else None,config_json={'provider':provider,'scenario':scenario});db.add(a);db.flush();return a
@app.post('/api/videos/{id}/analyses',status_code=202,response_model=Envelope[AnalysisDTO])
def start_analysis(id:str,payload:CreateAnalysis,request:Request,idempotency_key:str|None=Header(None)):
    if payload.provider=='command' and not os.getenv('VISION_COMMAND'):fail(503,'CONFIG_REQUIRED','真实视觉命令尚未配置')
    digest=hashlib.sha256(json.dumps(payload.model_dump(),sort_keys=True).encode()).hexdigest()
    with Session.begin() as db:
        a=create_analysis(db,get(db,Video,id),payload.provider,payload.scenario,idempotency_key,digest);dto=analysis_dto(a)
    return ok(request,dto)
@app.post('/api/videos/{id}/analyses/import',status_code=202,response_model=Envelope[AnalysisDTO])
def import_analysis(id:str,request:Request,file:UploadFile=File(...)):
    raw=file.file.read(20*1024**2+1)
    if len(raw)>20*1024**2:fail(413,'FILE_TOO_LARGE','结果文件过大')
    try:r=json.loads(raw)
    except Exception:fail(422,'INVALID_JSON','结果不是有效 JSON')
    if not isinstance(r,dict):fail(422,'INVALID_JSON','结果须为对象')
    digest=hashlib.sha256(raw).hexdigest();key=f'import:{id}:{digest}'
    with Session.begin() as db:
        a=create_analysis(db,get(db,Video,id),'import',None,key,digest,r.get('analysis_id'))
        (DATA/'jobs'/f'{a.id}.json').write_bytes(raw);dto=analysis_dto(a)
    return ok(request,dto)
@app.get('/api/analyses/{id}',response_model=Envelope[AnalysisDetail])
def analysis_detail(id:str,request:Request):
    with Session() as db:
        a=get(db,Analysis,id);v=get(db,Video,a.video_id)
        return ok(request,dict(analysis=analysis_dto(a),behavior_catalog=result(a)['behavior_catalog'] if a.status=='succeeded' else [],duration_s=v.duration_s))
@app.get('/api/analyses/{id}/tracks',response_model=Envelope[Page[TrackDTO]])
def tracks(id:str,request:Request,limit:int=Query(20,ge=1,le=100),cursor:str|None=None):
    with Session() as db:r=result(get(db,Analysis,id))
    return ok(request,paginate([dict(analysis_id=id,track_id=t['track_id'],display_name='目标 '+t['track_id']) for t in r['tracks']],limit,cursor,{'analysis':id}))
@app.get('/api/analyses/{id}/stats',response_model=Envelope[StatsDTO])
def stats(id:str,request:Request,track_id:str|None=None,start_s:float|None=None,end_s:float|None=None):
    with Session() as db:r=result(get(db,Analysis,id))
    a,b,ts=selected(r,track_id,start_s,end_s)
    return ok(request,dict(range=dict(start_s=a,end_s=b),items=[compute_track_stats(r,t['track_id'],a,b) for t in ts],basis='classified_duration'))
@app.get('/api/analyses/{id}/segments',response_model=Envelope[SegmentPage])
def segments(id:str,request:Request,track_id:str|None=None,start_s:float|None=None,end_s:float|None=None,behavior:str|None=None,limit:int=Query(20,ge=1,le=100),cursor:str|None=None):
    with Session() as db:r=result(get(db,Analysis,id))
    a,b,ts=selected(r,track_id,start_s,end_s)
    if behavior and behavior not in [c['code'] for c in r['behavior_catalog']]+['unknown']:fail(422,'INVALID_BEHAVIOR','未知行为类别')
    rows=sorted([dict(analysis_id=id,track_id=t['track_id'],**s) for t in ts for s in t['segments'] if s['start_s']<b and s['end_s']>a and (not behavior or s['behavior']==behavior)],key=lambda x:(x['start_s'],x['segment_id']))
    page=paginate(rows,limit,cursor,{'analysis':id,'track':track_id,'a':a,'b':b,'behavior':behavior});page['applied_range']=dict(start_s=a,end_s=b)
    return ok(request,page)
@app.get('/api/analyses/{id}/observed')
def observed(id:str,request:Request):
    with Session() as db:r=result(get(db,Analysis,id))
    return ok(request,[dict(track_id=t['track_id'],intervals=t['observed_intervals']) for t in r['tracks']])
@app.get('/api/analyses/{id}/detections')
def detections(id:str,request:Request,time_s:float=Query(0,ge=0)):
    with Session() as db:r=result(get(db,Analysis,id))
    return ok(request,dict(time_s=time_s,sample_interval_s=r['sample_interval_s'],items=[d for d in r['detections'] if abs(d['time_s']-time_s)<=r['sample_interval_s']/2][:100]))

@app.post('/api/chat/sessions',status_code=201,response_model=Envelope[SessionDTO])
def create_session(payload:CreateSession,request:Request):
    with Session.begin() as db:
        if payload.analysis_id:get(db,Analysis,payload.analysis_id)
        cs=ChatSession(analysis_id=payload.analysis_id);db.add(cs);db.flush();dto=session_dto(cs)
    return ok(request,dto)
@app.get('/api/chat/sessions/{id}/messages',response_model=Envelope[Page[MessageDTO]])
def messages(id:str,request:Request,limit:int=Query(100,ge=1,le=100),cursor:str|None=None):
    with Session() as db:
        get(db,ChatSession,id);rows=[message_dto(m) for m in db.scalars(select(Message).where(Message.session_id==id).order_by(Message.created_at,Message.id))]
        for row in rows:
            if row['answer']:
                for e in row['answer']['knowledge_evidence']:
                    d=db.get(Document,e['document_id']);e['source_status']='deleted' if not d or d.deleted_at else 'active' if d.active_version==e['document_version'] else 'updated'
    return ok(request,paginate(rows,limit,cursor,{'session':id}))
@app.post('/api/chat/sessions/{id}/messages',response_model=Envelope[MessageDTO])
def send(id:str,payload:SendMessage,request:Request):
    from .agent import graph
    digest=hashlib.sha256(json.dumps(payload.model_dump(),sort_keys=True).encode()).hexdigest()
    with SESSION_LOCK,Session.begin() as db:
        cs=get(db,ChatSession,id);old=db.scalar(select(Turn).where(Turn.session_id==id,Turn.client_message_id==payload.client_message_id))
        if old:
            if old.input_hash!=digest:fail(409,'IDEMPOTENCY_CONFLICT','消息键已用于不同内容')
            if old.status=='processing':fail(409,'MESSAGE_PROCESSING','此消息正在处理')
            return ok(request,message_dto(get(db,Message,old.assistant_id)))
        if db.scalar(select(Turn).where(Turn.session_id==id,Turn.status=='processing')):fail(409,'SESSION_BUSY','当前会话正在处理消息')
        if cs.analysis_id:
            analysis=get(db,Analysis,cs.analysis_id)
            if analysis.status=='succeeded':
                r=result(analysis);selected(r,payload.selected_track_id,payload.range.start_s if payload.range else None,payload.range.end_s if payload.range else None)
        selection={'track_id':payload.selected_track_id,'range':payload.range.model_dump() if payload.range else None}
        previous=db.get(SessionSelection,id)
        if not previous or previous.ui_json!=selection:
            cs.selected_track_id=selection['track_id'];cs.selected_range_json=selection['range']
            if previous:previous.ui_json=selection
            else:db.add(SessionSelection(session_id=id,ui_json=selection))
        db.add(Message(session_id=id,client_message_id=payload.client_message_id,role='user',status='succeeded',content_json={'text':payload.text}));db.flush()
        m=Message(session_id=id,client_message_id=payload.client_message_id,role='assistant',status='processing',content_json={'text':''});db.add(m);db.flush();mid=m.id
        db.add(Turn(session_id=id,client_message_id=payload.client_message_id,input_hash=digest,status='processing',assistant_id=mid))
    try:state=graph.invoke({'session_id':id,'message_id':mid,'text':payload.text},{'recursion_limit':30})
    except Exception:
        logging.exception('Graph failed message=%s',mid)
        with Session.begin() as db:
            m=db.get(Message,mid);m.status='failed';m.content_json={'text':'智能体执行失败，请重试。','answer':None};db.scalar(select(Turn).where(Turn.assistant_id==mid)).status='failed'
        raise APIError(502,'AGENT_FAILED','智能体执行失败',{'message_id':mid})
    with Session() as db:dto=message_dto(db.get(Message,mid))
    if state.get('error'):raise APIError(409 if state['error']=='ANALYSIS_NOT_READY' else 503 if 'CONFIG_REQUIRED' in state['error'] else 502,'AGENT_FAILED','解释不可用，已保存本轮记录。',{'message_id':mid})
    return ok(request,dto)

@app.get('/api/knowledge/documents',response_model=Envelope[Page[DocumentDTO]])
def documents(request:Request,limit:int=Query(20,ge=1,le=100),cursor:str|None=None):
    with Session() as db:rows=[rag.document_dto(db,d) for d in db.scalars(select(Document).where(Document.deleted_at.is_(None)).order_by(Document.created_at.desc(),Document.id))]
    return ok(request,paginate(rows,limit,cursor))
def add_version(db,d,file):
    suffix=Path(file.filename or '').suffix.lower()
    if suffix not in ['.txt','.md','.pdf']:fail(422,'INVALID_DOCUMENT','只支持 TXT、MD、文本 PDF')
    raw=file.file.read(20*1024**2+1)
    if len(raw)>20*1024**2:fail(413,'FILE_TOO_LARGE','文档超过20MB')
    digest=hashlib.sha256(raw).hexdigest()
    old=db.scalar(select(Version).where(Version.document_id==d.id,Version.content_hash==digest).order_by(Version.version.desc()))
    if old:return old
    version=(db.scalar(select(func.max(Version.version)).where(Version.document_id==d.id)) or 0)+1
    key=f'documents/{uid()}{suffix}';(DATA/key).write_bytes(raw)
    v=Version(document_id=d.id,version=version,content_hash=digest,storage_key=key);db.add(v);db.flush();return v
@app.post('/api/knowledge/documents',status_code=202,response_model=Envelope[DocumentDTO])
def upload_document(request:Request,file:UploadFile=File(...),title:str=Form(...),source_title:str=Form(...),source_url:str|None=Form(None),applicability:str=Form(''),is_demo:bool=Form(False)):
    if source_url and not source_url.startswith(('https://','http://')):fail(422,'INVALID_URL','来源仅支持 http/https')
    with Session.begin() as db:
        d=Document(title=title,source_title=source_title,source_url=source_url,applicability=applicability,is_demo=is_demo);db.add(d);db.flush();v=add_version(db,d,file);dto=rag.document_dto(db,d);did,ver=d.id,v.version
    POOL.submit(rag.index_version,did,ver);return ok(request,dto)
@app.post('/api/knowledge/documents/{id}/versions',status_code=202,response_model=Envelope[DocumentDTO])
def update_document(id:str,request:Request,file:UploadFile=File(...)):
    with Session.begin() as db:
        d=get(db,Document,id)
        if d.deleted_at:fail(409,'DOCUMENT_DELETED','文档已删除')
        v=add_version(db,d,file);dto=rag.document_dto(db,d);ver=v.version;pending=v.status=='pending'
    if pending:POOL.submit(rag.index_version,id,ver)
    return ok(request,dto)
@app.post('/api/knowledge/documents/{id}/reindex',status_code=202,response_model=Envelope[DocumentDTO])
def reindex(id:str,request:Request):
    with Session.begin() as db:
        d=get(db,Document,id)
        if d.deleted_at:fail(409,'DOCUMENT_DELETED','文档已删除')
        v=db.scalar(select(Version).where(Version.document_id==id).order_by(Version.version.desc()))
        pending=v.status=='failed'
        if pending:v.status='pending'
        dto=rag.document_dto(db,d);ver=v.version
    if pending:POOL.submit(rag.index_version,id,ver)
    return ok(request,dto)
@app.get('/api/knowledge/documents/{id}')
def document_detail(id:str,request:Request):
    with Session() as db:
        d=get(db,Document,id)
        return ok(request,dict(document=rag.document_dto(db,d),versions=[obj(v) | {'storage_key':None} for v in db.scalars(select(Version).where(Version.document_id==id))],chunks={'items':[rag.chunk_dto(c,d) for c in db.scalars(select(Chunk).where(Chunk.document_id==id,Chunk.version==d.active_version).order_by(Chunk.ordinal).limit(100))],'next_cursor':None}))
@app.get('/api/knowledge/chunks/{id}',response_model=Envelope[ChunkDTO])
def chunk_detail(id:str,request:Request):
    with Session() as db:
        c=get(db,Chunk,id);d=get(db,Document,c.document_id)
        if d.deleted_at or c.version!=d.active_version:fail(404,'SOURCE_INACTIVE','来源已更新或删除，请查看对话快照')
        return ok(request,rag.chunk_dto(c,d))
@app.delete('/api/knowledge/documents/{id}',status_code=202)
def delete_document(id:str,request:Request):
    with Session.begin() as db:d=get(db,Document,id);d.deleted_at=now()
    POOL.submit(rag.cleanup_document,id)
    return ok(request,dict(document_id=id,status='deleting'))
@app.post('/api/knowledge/search',response_model=Envelope[SearchDTO])
def knowledge_search(payload:SearchRequest,request:Request):
    try:return ok(request,rag.search(**payload.model_dump()))
    except Exception as e:raise APIError(503 if isinstance(e,ValueError) else 502,'RETRIEVAL_FAILED','检索服务未配置或调用失败')

@app.post('/api/history/query')
def history_query(payload:HistoryRequest,request:Request):return ok(request,sanitize_history(query_history(**payload.model_dump())))
@app.get('/api/history/status')
def history_status(request:Request):
    return ok(request,{'available':HISTORY.is_file(),'dates':['2023-07-21','2023-07-22','2023-07-23','2023-07-24','2023-07-25'],'cow_ids':list(range(1,17)),'timezone':'America/Chicago','label_source':'model_prediction','reviewed':False})
@app.get('/api/history/evidence/{ref}')
def history_image(ref:str):
    with Session() as db:
        e=get(db,Evidence,ref)
        if e.kind!='image':fail(404,'NOT_FOUND','证据不存在')
        path=Path(e.payload_json['path'])
    # Only database-derived image paths; ref is opaque, no path parameter.
    if not path.is_file():fail(404,'IMAGE_MISSING','原图缺失')
    return FileResponse(path)

@app.get('/api/analyses/{id}/report')
def report(id:str,format:Literal['md','json']='json',track_id:str|None=None,start_s:float|None=None,end_s:float|None=None,session_id:str|None=None):
    with Session() as db:
        a=get(db,Analysis,id);r=result(a);lo,hi,ts=selected(r,track_id,start_s,end_s)
        answers=[]
        if session_id:
            cs=get(db,ChatSession,session_id)
            if cs.analysis_id!=id:fail(422,'SESSION_MISMATCH','会话不属于当前分析')
            answers=[m.content_json for m in db.scalars(select(Message).where(Message.session_id==session_id,Message.role=='assistant').order_by(Message.created_at))]
        data=dict(analysis=analysis_dto(a),range={'start_s':lo,'end_s':hi},basis='classified_duration',statistics=[compute_track_stats(r,t['track_id'],lo,hi) for t in ts],modes={'vision':r['source_kind'],'llm':LLM,'retrieval':RETRIEVAL},answers=answers,limitations=r['warnings']+['行为占比以已识别行为时长为分母；短视频不代表全天，不作疾病诊断。'])
    if format=='json':return Response(json.dumps(data,ensure_ascii=False,indent=2),media_type='application/json',headers={'Content-Disposition':f'attachment; filename="report-{id}.json"'})
    text='# 奶牛行为分析报告\n\n'+f'分析编号：{id}\n\n范围：{lo}–{hi}秒；视觉：{r["source_kind"]}；对话：{LLM}；检索：{RETRIEVAL}\n\n行为占比分母：已识别行为时长。\n\n'
    for row in data['statistics']:
        text+=f'## {row["track_id"]}\n\n|行为|时长（秒）|占已识别时长|记录片段数|\n|---|---:|---:|---:|\n'
        for b in row['behaviors']:text+=f'|{b["label"]}|{b["duration_s"]}|{b["ratio"]}|{b["segment_count"]}|\n'
    text+='\n## 限制\n\n'+'\n'.join('- '+x for x in data['limitations'])
    if answers:text+='\n\n## 对话与出处快照\n\n```json\n'+json.dumps(answers,ensure_ascii=False,indent=2)+'\n```\n'
    return Response(text,media_type='text/markdown; charset=utf-8',headers={'Content-Disposition':f'attachment; filename="report-{id}.md"'})

DIST=ROOT/'frontend/dist'
@app.get('/{path:path}',include_in_schema=False)
def spa(path:str):
    if path=='api' or path.startswith('api/'):fail(404,'NOT_FOUND','API 不存在')
    target=(DIST/path).resolve()
    if DIST.resolve() in target.parents and target.is_file():return FileResponse(target)
    if (DIST/'index.html').is_file():return FileResponse(DIST/'index.html')
    fail(404,'FRONTEND_NOT_BUILT','请启动 Vite 或构建前端')
