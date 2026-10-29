import copy,json,os,signal,subprocess,time
from .config import ROOT,DATA

def analyze(a,v,heartbeat):
    if a.provider=='import':
        r=json.loads((DATA/'jobs'/f'{a.id}.json').read_text());r['analysis_id']=a.id;return r
    if a.provider=='mock':
        time.sleep(.4)
        if a.scenario=='provider_failure':raise ValueError('模拟视觉失败场景')
        r=json.loads((ROOT/'docs/cow-agent-brief/03-模型结果样例.json').read_text())
        scale=v.duration_s/120
        r.update(video_id=v.id,analysis_id=a.id,video_sha256=v.sha256,duration_s=v.duration_s,warnings=['模拟结果与视频内容无关；不代表真实识别。'])
        for t in r['tracks']:
            for i in t['observed_intervals']+t['segments']:
                i['start_s']*=scale;i['end_s']*=scale
        if a.scenario=='no_detections':r['tracks']=[]
        if a.scenario=='unknown_only':
            r['tracks'][0]['segments']=[dict(segment_id='unknown_001',start_s=0,end_s=100*scale,behavior='unknown')]
        return r
    argv=json.loads(os.getenv('VISION_COMMAND','[]'))
    if not argv or not isinstance(argv,list) or not all(isinstance(x,str) for x in argv):raise ValueError('CONFIG_REQUIRED: VISION_COMMAND 必须是参数数组')
    out=DATA/'jobs'/f'{a.id}.result.json'
    p=subprocess.Popen(argv+['--input',str(DATA/v.storage_key),'--output',str(out),'--video-id',v.id,'--analysis-id',a.id],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
    deadline=time.monotonic()+float(os.getenv('VISION_TIMEOUT_S','120'))
    try:
        while p.poll() is None:
            heartbeat()
            if time.monotonic()>deadline:raise TimeoutError('VISION_TIMEOUT')
            time.sleep(.25)
        if p.returncode:raise ValueError('VISION_EXIT_NONZERO')
        return json.loads(out.read_text())
    finally:
        if p.poll() is None:
            os.killpg(p.pid,signal.SIGKILL);p.wait()
