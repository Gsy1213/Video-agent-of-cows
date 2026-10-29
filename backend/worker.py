"""Single persistent visual worker. Run: python -m backend.worker."""
import json,time,os
from datetime import datetime,timezone,timedelta
from sqlalchemy import select,update
from backend.app.db import *
from backend.app.config import DATA
from backend.app.core import validate_analysis_result
from backend.app.vision import analyze

def tick():
    with Session.begin() as db:
        runtime=db.get(Runtime,'worker')
        if runtime:runtime.heartbeat_at=now()
        else:db.add(Runtime(id='worker',heartbeat_at=now()))
        cutoff=(datetime.now(timezone.utc)-timedelta(seconds=float(os.getenv('WORKER_STALE_S','60')))).isoformat()
        db.execute(update(Analysis).where(Analysis.status=='running',Analysis.heartbeat_at<cutoff).values(status='failed',error_json={'code':'WORKER_INTERRUPTED','message':'Worker 心跳过期'},finished_at=now()))
        a=db.scalar(select(Analysis).where(Analysis.status=='queued').order_by(Analysis.created_at).limit(1))
        if a is None:return False
        aid=a.id
        n=db.execute(update(Analysis).where(Analysis.id==aid,Analysis.status=='queued').values(status='running',owner=str(os.getpid()),attempt=Analysis.attempt+1,heartbeat_at=now(),started_at=now())).rowcount
        if not n:return False
    def heartbeat():
        with Session.begin() as db:
            db.execute(update(Analysis).where(Analysis.id==aid).values(heartbeat_at=now()))
            db.execute(update(Runtime).where(Runtime.id=='worker').values(heartbeat_at=now()))
    try:
        with Session() as db:a=db.get(Analysis,aid);v=db.get(Video,a.video_id)
        r=analyze(a,v,heartbeat);validate_analysis_result(r,obj(v),obj(a))
        key=f'results/{aid}.json'; tmp=DATA/(key+'.tmp');tmp.write_text(json.dumps(r,ensure_ascii=False));tmp.replace(DATA/key)
        with Session.begin() as db:
            for t in r['tracks']:db.add(Track(analysis_id=aid,track_id=t['track_id']))
            db.flush()
            for t in r['tracks']:
                for i in t['observed_intervals']:db.add(Observed(analysis_id=aid,track_id=t['track_id'],**i))
                for s in t['segments']:db.add(Segment(analysis_id=aid,track_id=t['track_id'],**s))
            a=db.get(Analysis,aid);a.status='succeeded';a.result_storage_key=key;a.model_version=r['model_version'];a.source_kind=r['source_kind'];a.finished_at=now()
    except Exception as e:
        with Session.begin() as db:
            a=db.get(Analysis,aid);a.status='failed';a.error_json={'code':'VISION_TIMEOUT' if isinstance(e,TimeoutError) else 'VISION_FAILED','message':str(e)[:250] if isinstance(e,(ValueError,TimeoutError)) else '视觉结果读取或执行失败'};a.finished_at=now()
    return True

if __name__=='__main__':
    init()
    while True:
        tick();time.sleep(.5)
