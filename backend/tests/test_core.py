import copy
import json
from pathlib import Path
import pytest
from backend.app.core import validate_analysis_result, compute_track_stats, assemble_answer

SAMPLE = Path(__file__).resolve().parents[2] / 'docs/cow-agent-brief/03-模型结果样例.json'

def sample():
    return json.loads(SAMPLE.read_text())

def test_contract_and_windows():
    r = sample()
    validate_analysis_result(r, {'id':r['video_id'], 'sha256':r['video_sha256'], 'duration_s':120, 'fps':25}, {'id':r['analysis_id'],'provider':'mock'})
    for a,b,expected in [(0,120,(100,10,90,20,30)),(25,65,(40,10,30,0,25))]:
        s=compute_track_stats(r,'track_001',a,b)
        assert tuple(s[k] for k in ['observed_duration_s','unknown_duration_s','classified_duration_s','unobserved_duration_s']) == expected[:4]
        assert next(x for x in s['behaviors'] if x['code']=='feeding')['duration_s']==expected[4]

@pytest.mark.parametrize('case', ['overlap','gap','wrong_video','duplicate','bbox','nan','outside','duplicate_catalog'])
def test_invalid(case):
    r=sample();v={'id':r['video_id'],'sha256':r['video_sha256'],'duration_s':120,'fps':25}; c={'id':r['analysis_id'],'provider':'mock'}
    if case=='overlap':r['tracks'][0]['segments'][1]['start_s']=19
    if case=='gap':r['tracks'][0]['segments'][1]['start_s']=21
    if case=='wrong_video':r['video_id']='other'
    if case=='duplicate':r['tracks'][0]['segments'][1]['segment_id']='seg_001'
    if case=='bbox':r['detections']=[{'time_s':1,'track_id':'track_001','behavior':'standing','bbox_xywh_norm':[0,0,1,1],'confidence':.5}]
    if case=='nan':r['duration_s']=float('nan')
    if case=='outside':r['tracks'][0]['segments'][-1]['end_s']=121
    if case=='duplicate_catalog':r['behavior_catalog'].append(copy.deepcopy(r['behavior_catalog'][0]))
    with pytest.raises(ValueError): validate_analysis_result(r,v,c)

def test_unknown_empty_and_scope():
    r=sample();r['tracks'][0]['segments']=[{'segment_id':'u','start_s':0,'end_s':100,'behavior':'unknown'}]
    assert all(x['ratio'] is None for x in compute_track_stats(r,'track_001',0,120)['behaviors'])
    draft=dict(answer_text='测试',fact_refs=['f'],video_refs=[],knowledge_refs=[],limitations=[])
    with pytest.raises(ValueError):assemble_answer(draft,{'f':{'kind':'fact','session_id':'other','analysis_id':'a','payload':{}}},{'session_id':'s','analysis_id':'a'})
