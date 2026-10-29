import os
from pathlib import Path
from dotenv import load_dotenv

ROOT=Path(__file__).resolve().parents[2]
load_dotenv(ROOT/'.env')
DATA=Path(os.getenv('DATA_DIR',str(ROOT/'data'))).resolve()
DATA.mkdir(parents=True,exist_ok=True)
for name in ['videos','results','documents','jobs']:(DATA/name).mkdir(exist_ok=True)
DATABASE_URL=os.getenv('DATABASE_URL',f'sqlite:///{DATA}/app.sqlite3')
LLM=os.getenv('LLM_PROVIDER','mock')
RETRIEVAL=os.getenv('RETRIEVAL_PROVIDER','lexical')
HISTORY=Path(os.getenv('HISTORY_DB','/data2/geshuyu/mmcows/outputs/five_day_preannotation/behavior.sqlite3'))
