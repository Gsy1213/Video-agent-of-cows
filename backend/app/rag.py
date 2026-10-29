import hashlib,math,os,re,unicodedata,threading
import httpx
from sqlalchemy import select,func
from pypdf import PdfReader
from .config import DATA,RETRIEVAL
from .db import Session,Document,Version,Chunk,uid,now,obj

LOCK=threading.RLock()
def tokens(text):
    text=unicodedata.normalize('NFKC',text).lower()
    words=set(re.findall(r'[a-z0-9_]+',text))
    for run in re.findall(r'[\u4e00-\u9fff]+',text):
        for n in (2,3):words.update(run[i:i+n] for i in range(len(run)-n+1))
    return words

def parse(path):
    if path.suffix.lower()=='.pdf':
        pages=[(i+1,p.extract_text() or '') for i,p in enumerate(PdfReader(path).pages)]
    else:pages=[(None,path.read_text(encoding='utf-8'))]
    if not any(t.strip() for _,t in pages):raise ValueError('文档无文本层，需要 OCR，本版不支持')
    chunks=[]
    for page,text in pages:
        section=None
        for paragraph in re.split(r'\n\s*\n',text):
            if paragraph.startswith('#'):section=paragraph.splitlines()[0].lstrip('# ').strip()
            for i in range(0,max(1,len(paragraph)),500):
                part=paragraph[i:i+600].strip()
                if part:chunks.append(dict(text=part,page=page,section=section,ordinal=len(chunks)))
                if i+600>=len(paragraph):break
    return chunks

def embeddings(texts):
    key=os.getenv('EMBEDDING_API_KEY');model=os.getenv('EMBEDDING_MODEL');base=os.getenv('EMBEDDING_BASE_URL')
    if not all([key,model,base]):raise ValueError('CONFIG_REQUIRED: embedding 未配置')
    with httpx.Client(timeout=30) as c:
        r=c.post(base.rstrip('/')+'/embeddings',headers={'Authorization':f'Bearer {key}'},json={'model':model,'input':texts});r.raise_for_status()
    rows=sorted(r.json()['data'],key=lambda x:x['index']);vectors=[x['embedding'] for x in rows]
    if len(vectors)!=len(texts) or not vectors or not vectors[0] or any(len(v)!=len(vectors[0]) or any(not isinstance(x,(int,float)) or not math.isfinite(x) for x in v) for v in vectors):raise ValueError('embedding 返回维度或数值无效')
    return vectors

def collection(dimension):
    import chromadb
    signature=hashlib.sha256(f'{os.getenv("EMBEDDING_BASE_URL")}|{os.getenv("EMBEDDING_MODEL")}|{dimension}|v1'.encode()).hexdigest()[:24]
    client=chromadb.PersistentClient(path=str(DATA/'chroma'))
    return client.get_or_create_collection('cow_'+signature,metadata={'hnsw:space':'cosine'}),signature

def index_version(document_id,version):
    with LOCK:
        try:
            with Session.begin() as db:
                v=db.get(Version,(document_id,version));v.status='indexing';path=DATA/v.storage_key
            chunks=parse(path);rows=[dict(id=uid(),document_id=document_id,version=version,**x) for x in chunks]
            fingerprint='lexical-ngram-v1'
            if RETRIEVAL=='vector':
                vectors=embeddings([x['text'] for x in rows]);col,fingerprint=collection(len(vectors[0]))
                col.upsert(ids=[x['id'] for x in rows],embeddings=vectors,documents=[x['text'] for x in rows])
                for x in rows:x['vector_id']=x['id']
            with Session.begin() as db:
                doc=db.get(Document,document_id)
                if doc.deleted_at:return
                for x in db.scalars(select(Chunk).where(Chunk.document_id==document_id,Chunk.version==version)):db.delete(x)
                db.add_all(Chunk(**x) for x in rows)
                v=db.get(Version,(document_id,version));v.status='ready';v.index_fingerprint=fingerprint;v.error_json=None
                if doc.active_version is None or version>=doc.active_version:doc.active_version=version
        except Exception as e:
            with Session.begin() as db:
                v=db.get(Version,(document_id,version));v.status='failed';v.error_json={'code':'INDEX_FAILED','message':str(e)[:150] if isinstance(e,ValueError) else '文档解析或向量服务失败'}

def chunk_dto(c,d):
    return dict(id=c.id,document_id=d.id,version=c.version,title=d.title,text=c.text,page=c.page,section=c.section,source_url=d.source_url,is_demo=d.is_demo,source_status='deleted' if d.deleted_at else 'active' if c.version==d.active_version else 'updated')

def search(query,top_k=5):
    with LOCK,Session() as db:
        active=list(db.execute(select(Chunk,Document).join(Document,Document.id==Chunk.document_id).join(Version,(Version.document_id==Chunk.document_id)&(Version.version==Chunk.version)).where(Document.deleted_at.is_(None),Document.active_version==Chunk.version,Version.status=='ready')))
        scores={}
        if RETRIEVAL=='vector':
            vec=embeddings([query]);col,signature=collection(len(vec[0]))
            if col.count():
                found=col.query(query_embeddings=vec,n_results=min(col.count(),max(100,top_k*20)))
                scores={i:1-d for i,d in zip(found['ids'][0],found['distances'][0]) if d<=float(os.getenv('VECTOR_MAX_DISTANCE','0.6'))}
        else:
            q=tokens(query)
            for c,d in active:
                ct=tokens(c.text+' '+d.title);shared=q&ct
                if shared:scores[c.id]=len(shared)/math.sqrt(max(1,len(q)*len(ct)))
        hits=sorted([dict(chunk=chunk_dto(c,d),score=scores[c.id]) for c,d in active if c.id in scores],key=lambda x:(-x['score'],x['chunk']['id']))[:top_k]
        return dict(retrieval_mode=RETRIEVAL,matches=hits,warnings=['关键词离线检索；分数不是概率。'] if RETRIEVAL=='lexical' else ['向量余弦相似度；分数不是概率。'])

def document_dto(db,d):
    versions=list(db.scalars(select(Version).where(Version.document_id==d.id).order_by(Version.version.desc())))
    v=versions[0] if versions else None
    return dict(id=d.id,title=d.title,source_title=d.source_title,source_url=d.source_url,applicability=d.applicability,is_demo=d.is_demo,active_version=d.active_version,latest_version=v.version if v else 0,status='deleting' if d.deleted_at else v.status if v else 'pending',chunk_count=db.scalar(select(func.count()).select_from(Chunk).where(Chunk.document_id==d.id,Chunk.version==d.active_version)),error=v.error_json if v else None,created_at=d.created_at)

def cleanup_document(document_id):
    with LOCK,Session() as db:
        rows=list(db.scalars(select(Chunk).where(Chunk.document_id==document_id,Chunk.vector_id.is_not(None))))
        versions=list(db.scalars(select(Version).where(Version.document_id==document_id)))
        if not rows:return
        import chromadb
        client=chromadb.PersistentClient(path=str(DATA/'chroma'))
        names={c.name for c in client.list_collections()}
        for v in versions:
            name='cow_'+(v.index_fingerprint or '')
            if name in names:
                ids=[r.vector_id for r in rows if r.version==v.version]
                if ids:client.get_collection(name).delete(ids=ids)
