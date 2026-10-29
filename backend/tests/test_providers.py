import copy,json,os,sys,time,uuid
from types import SimpleNamespace
from pathlib import Path
import httpx,pytest
from backend.app import agent,rag
from backend.app.vision import analyze
from backend.app.core import validate_analysis_result
from backend.app.config import DATA,ROOT

def objects(tmp_path):
    v=SimpleNamespace(id='video',storage_key='videos/input.mp4',sha256='b'*64,duration_s=120,fps=25)
    a=SimpleNamespace(id=uuid.uuid4().hex,provider='command',scenario=None)
    return v,a

@pytest.mark.parametrize('mode',['success','nonzero','timeout','bad_json','wrong_hash'])
def test_command_adapter(tmp_path,monkeypatch,mode):
    v,a=objects(tmp_path)
    sample=json.loads((ROOT/'docs/cow-agent-brief/03-模型结果样例.json').read_text())
    sample.update(video_id=v.id,analysis_id=a.id,video_sha256=v.sha256,source_kind='model')
    if mode=='wrong_hash':sample['video_sha256']='c'*64
    runner=tmp_path/'runner.py'
    code="import sys,json,time\n"
    if mode=='nonzero':code+='sys.exit(4)\n'
    elif mode=='timeout':code+='time.sleep(10)\n'
    elif mode=='bad_json':code+="open(sys.argv[sys.argv.index('--output')+1],'w').write('bad')\n"
    else:code+=f"json.dump({sample!r},open(sys.argv[sys.argv.index('--output')+1],'w'))\n"
    runner.write_text(code);monkeypatch.setenv('VISION_COMMAND',json.dumps([sys.executable,str(runner)]));monkeypatch.setenv('VISION_TIMEOUT_S','.3');beats=[]
    if mode=='success':
        r=analyze(a,v,lambda:beats.append(1));validate_analysis_result(r,vars(v),vars(a));assert beats
    else:
        with pytest.raises((ValueError,TimeoutError)):validate_analysis_result(analyze(a,v,lambda:beats.append(1)),vars(v),vars(a))

def test_embedding_transport_and_persistent_chroma(monkeypatch):
    original=httpx.Client
    def serve(request):
        body=json.loads(request.content);assert body['model']=='embedding-protocol-test'
        return httpx.Response(200,json={'data':[{'index':i,'embedding':[1.,0.,0.] if '采食' in t else [0.,1.,0.]} for i,t in enumerate(body['input'])]})
    monkeypatch.setenv('EMBEDDING_API_KEY','test-only');monkeypatch.setenv('EMBEDDING_MODEL','embedding-protocol-test');monkeypatch.setenv('EMBEDDING_BASE_URL','http://stub/v1')
    monkeypatch.setattr(rag.httpx,'Client',lambda **kw:original(transport=httpx.MockTransport(serve),**kw))
    vectors=rag.embeddings(['采食行为','量子卫星']);assert len(vectors[0])==3
    col,_=rag.collection(3);col.upsert(ids=['positive'],embeddings=[vectors[0]],documents=['采食行为'])
    assert col.query(query_embeddings=[vectors[0]],n_results=1)['distances'][0][0]==pytest.approx(0)
    assert col.query(query_embeddings=[vectors[1]],n_results=1)['distances'][0][0]==pytest.approx(1)
    # Reopen persisted collection, no default model download.
    second,_=rag.collection(3);assert second.get(ids=['positive'])['documents']==['采食行为']

def test_api_tool_protocol(monkeypatch):
    original=httpx.Client;seen=[]
    def serve(request):
        body=json.loads(request.content);seen.append(body)
        if len(seen)==1:
            assert any(t['function']['name']=='get_behavior_stats' for t in body['tools'])
            msg={'role':'assistant','content':None,'tool_calls':[{'id':'provider_call_1','type':'function','function':{'name':'get_behavior_stats','arguments':json.dumps({'track_id':'track_001','start_s':None,'end_s':None})}}]}
        else:
            assert body['messages'][-1]['role']=='tool';assert body['messages'][-1]['tool_call_id']=='provider_call_1'
            msg={'role':'assistant','content':json.dumps({'answer_text':'事实见工具卡。','fact_refs':['known'],'video_refs':[],'knowledge_refs':[],'limitations':[]})}
        return httpx.Response(200,json={'choices':[{'message':msg}]})
    monkeypatch.setattr(agent,'LLM','api');monkeypatch.setenv('LLM_BASE_URL','http://stub/v1');monkeypatch.setenv('LLM_API_KEY','test-only');monkeypatch.setenv('LLM_MODEL','tool-protocol-test')
    monkeypatch.setattr(agent.httpx,'Client',lambda **kw:original(transport=httpx.MockTransport(serve),**kw))
    s={'rounds':0,'deadline':time.monotonic()+10,'context':{'history':False},'messages':[{'role':'user','content':'采食多久'}]}
    first=agent.model(s);assert first['calls'][0]['call_id']=='provider_call_1'
    second=agent.model({**s,**first,'messages':first['messages']+[{'role':'tool','tool_call_id':'provider_call_1','content':'{}'}]})
    assert second['draft']['fact_refs']==['known'];assert len(seen)==2

def test_missing_provider_no_fallback(monkeypatch):
    monkeypatch.setattr(agent,'LLM','api');monkeypatch.delenv('LLM_API_KEY',raising=False)
    s={'rounds':0,'deadline':time.monotonic()+10,'context':{'history':False},'messages':[]}
    assert 'CONFIG_REQUIRED' in agent.model(s)['error']

def test_pdf_ocr_and_chunks(tmp_path):
    from pypdf import PdfWriter
    writer=PdfWriter();writer.add_blank_page(width=200,height=200)
    blank=tmp_path/'scan.pdf'
    with blank.open('wb') as f:writer.write(f)
    with pytest.raises(ValueError,match='OCR'):rag.parse(blank)
    txt=tmp_path/'long.md';text='# 说明\n\n'+'中文段落'*400;txt.write_text(text)
    chunks=rag.parse(txt);assert len(chunks)>2;assert all(len(c['text'])<=600 for c in chunks);assert len({c['ordinal'] for c in chunks})==len(chunks)
