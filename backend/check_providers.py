import json,os,sys
import httpx
from backend.app import rag,agent
def main():
    failed=False
    for kind,keys in [('llm',['LLM_API_KEY','LLM_MODEL','LLM_BASE_URL']),('embedding',['EMBEDDING_API_KEY','EMBEDDING_MODEL','EMBEDDING_BASE_URL'])]:
        if not all(os.getenv(k) for k in keys):print(kind+': NOT_CONFIGURED');continue
        try:
            if kind=='embedding':
                vectors=rag.embeddings(['奶牛采食','饮水行为']);print(f'embedding: OK dimension={len(vectors[0])} model={os.getenv("EMBEDDING_MODEL")}')
            else:
                tools=agent.tool_schemas()
                messages=[{'role':'user','content':'协议检查：请调用search_knowledge，查询奶牛采食，top_k为1。'}]
                with httpx.Client(timeout=30) as c:
                    url=os.environ['LLM_BASE_URL'].rstrip('/')+'/chat/completions';headers={'Authorization':'Bearer '+os.environ['LLM_API_KEY']}
                    r=c.post(url,headers=headers,json={'model':os.environ['LLM_MODEL'],'messages':messages,'tools':tools,'tool_choice':{'type':'function','function':{'name':'search_knowledge'}}});r.raise_for_status();m=r.json()['choices'][0]['message'];assert m.get('tool_calls')
                    messages.append(m)
                    for call in m['tool_calls']:messages.append({'role':'tool','tool_call_id':call['id'],'content':json.dumps({'ok':True,'data':{'matches':[]},'error':None})})
                    r=c.post(url,headers=headers,json={'model':os.environ['LLM_MODEL'],'messages':messages,'tools':tools,'tool_choice':'none'});r.raise_for_status();assert r.json()['choices'][0]['message'].get('content')
                print('llm: OK tool-call roundtrip')
        except Exception as e:print(kind+': FAILED '+type(e).__name__);failed=True
    return 1 if failed else 0
if __name__=='__main__':sys.exit(main())
