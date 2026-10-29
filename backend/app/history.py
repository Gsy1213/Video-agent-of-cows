"""Explicit history namespace: never infer identity from an uploaded track."""
import sys
from pathlib import Path
from .config import HISTORY

MODULE=Path('/data2/geshuyu/mmcows/preannotation')
def query_history(cow=1,start='2023-07-21',end='2023-07-25',kind='daily',behavior='feeding',start_time='00:00:00',end_time='24:00:00',limit=10):
    import re
    def normalized(value):
        if not re.fullmatch(r'\d{2}:\d{2}(?::\d{2})?',value):raise ValueError('时间格式须为 HH:MM 或 HH:MM:SS')
        return value+':00' if len(value)==5 else value
    start_time,end_time=normalized(start_time),normalized(end_time)
    if not HISTORY.is_file():raise ValueError('历史预测数据库不存在')
    if str(MODULE) not in sys.path:sys.path.insert(0,str(MODULE))
    from rag import Store
    store=Store(HISTORY)
    try:
        if kind=='events':return store.events(cow,start,end,behavior,start_time,end_time,limit)
        if kind=='compare':return store.compare(cow,start,end,start_time,end_time)
        return store.daily(cow,start,end,start_time,end_time)
    finally:store.close()

def sanitize_history(result):
    """Opaque evidence keys; never expose disk paths or file:// URLs."""
    from .db import Session,Evidence,uid
    def walk(v):
        if isinstance(v,dict):
            if 'image_path' in v:
                ref=uid()
                with Session.begin() as db:db.add(Evidence(ref_id=ref,session_id='history',analysis_id='history',message_id='history',kind='image',payload_json={'path':v['image_path']}))
                v={k:x for k,x in v.items() if k not in ['image_path','image_url']};v['image_url']=f'/api/history/evidence/{ref}'
            return {k:walk(x) for k,x in v.items()}
        if isinstance(v,list):return [walk(x) for x in v]
        return v
    return walk(result)
