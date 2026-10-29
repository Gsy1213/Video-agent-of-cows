"""Isolated test API + actual worker subprocess; no mocked browser endpoints."""
import os,tempfile,subprocess,sys
os.environ['DATA_DIR']=tempfile.mkdtemp(prefix='cow-agent-e2e-')
os.environ.pop('DATABASE_URL',None)
os.environ['LLM_PROVIDER']='mock';os.environ['RETRIEVAL_PROVIDER']='lexical'
from backend.app.db import init
from backend.app.media import synthetic_demo_media
init()
test_video,_=synthetic_demo_media()
os.environ['DEMO_VIDEO_PATH']=str(test_video)
worker=subprocess.Popen([sys.executable,'-m','backend.worker'])
try:
    import uvicorn
    uvicorn.run('backend.app.main:app',host='127.0.0.1',port=8011)
finally:
    worker.terminate();worker.wait(timeout=5)
