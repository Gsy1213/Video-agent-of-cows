"""Idempotent API ingestion: knowledge + all 80 real cow/day summaries."""
import argparse,json,time
from pathlib import Path
import httpx
from backend.app.config import ROOT,HISTORY

def seed(base='http://127.0.0.1:8000',video=False):
    with httpx.Client(base_url=base,timeout=90) as c:
        existing=c.get('/api/knowledge/documents',params={'limit':100}).raise_for_status().json()['data']['items']
        titles={d['title'] for d in existing}
        rows=[('工程演示：统计口径',ROOT/'fixtures/knowledge/statistics.md','牧知软件统计约定',None,True),('工程演示：轨迹与历史身份',ROOT/'fixtures/knowledge/identity.md','牧知软件身份边界',None,True),('奶牛营养：采食与饮水',ROOT/'fixtures/knowledge/nutrition.md','Merck Veterinary Manual','https://www.merckvetmanual.com/management-and-nutrition/nutrition-dairy-cattle/nutritional-requirements-of-dairy-cattle',False),('热应激与采食观察',ROOT/'fixtures/knowledge/heat-stress.md','University of Wisconsin–Madison Extension','https://dairy.extension.wisc.edu/articles/heat-stress/',False)]
        uploads=[]
        for title,path,source,url,demo in rows:uploads.append((title,path.name,path.read_text(),source,url,demo))
        for path in sorted(HISTORY.parent.glob('*_daily_summaries.jsonl')):
            for line in path.read_text().splitlines():
                r=json.loads(line);title=f'历史行为记录：{r["cow_id"]}号牛 {r["local_date"]}'
                body=f'# {title}\n\n来源：五天预标注汇总，模型预测，未人工复核。时区 America/Chicago。\n\n'
                for key,label in [('observable_feeding_seconds','可观测采食秒数'),('observable_seconds','可观测秒数'),('unknown_seconds','未知秒数'),('pending_seconds','待处理秒数'),('feeding_episode_count','记录采食片段数'),('identity_behavior_coverage','身份行为可观测覆盖率'),('feeding_fraction_of_observable','采食占可观测时长比例')]:body+=f'{label}：{r.get(key)}\n'
                body+='\n两秒采样估计；三路摄像头时间槽去重。跨日身份未经人工确认。不可外推全天真实采食，不作疾病诊断。精确筛选与重算请使用历史查询工具。'
                uploads.append((title,title+'.md',body,f'five_day_preannotation/{path.name}',None,False))
        count=0
        for title,filename,text,source,url,demo in uploads:
            if title in titles:continue
            data={'title':title,'source_title':source,'applicability':'一般背景或未复核历史预测；以原文和人工核验为准','is_demo':str(demo).lower()}
            if url:data['source_url']=url
            res=c.post('/api/knowledge/documents',data=data,files={'file':(filename,text.encode(),'text/markdown')});res.raise_for_status();count+=1
        deadline=time.monotonic()+120
        while time.monotonic()<deadline:
            docs=c.get('/api/knowledge/documents',params={'limit':100}).raise_for_status().json()['data']['items']
            if not any(d['status'] in ['pending','indexing'] for d in docs):break
            time.sleep(.25)
        print(f'Knowledge: {count} uploaded; {sum(d["status"]=="ready" for d in docs)} ready; {sum(d["status"]=="failed" for d in docs)} failed')
        if video:
            videos=c.get('/api/videos',params={'limit':100}).json()['data']['items']
            if not any(v['is_demo'] for v in videos):
                v=c.post('/api/demo').raise_for_status().json()['data'];c.post(f'/api/videos/{v["id"]}/analyses',json={'provider':'mock','scenario':'normal'}).raise_for_status();print('Demo video queued')
        return docs

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--base',default='http://127.0.0.1:8000');p.add_argument('--video',action='store_true');a=p.parse_args();seed(a.base,a.video)
