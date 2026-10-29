import os,tempfile
import pytest
os.environ['DATA_DIR']=tempfile.mkdtemp(prefix='cow-agent-test-')
os.environ.pop('DATABASE_URL',None)
os.environ['LLM_PROVIDER']='mock'
os.environ['RETRIEVAL_PROVIDER']='lexical'

@pytest.fixture(scope='session',autouse=True)
def synthetic_test_video():
    from backend.app.media import synthetic_demo_media
    path,_=synthetic_demo_media()
    old=os.environ.get('DEMO_VIDEO_PATH')
    os.environ['DEMO_VIDEO_PATH']=str(path)
    yield
    if old is None:os.environ.pop('DEMO_VIDEO_PATH',None)
    else:os.environ['DEMO_VIDEO_PATH']=old
