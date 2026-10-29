import uuid
from datetime import datetime,timezone
from sqlalchemy import create_engine,event,Column,String,Float,Integer,Boolean,JSON,ForeignKey,ForeignKeyConstraint,UniqueConstraint
from sqlalchemy.orm import declarative_base,sessionmaker
from .config import DATABASE_URL

def uid():return uuid.uuid4().hex
def now():return datetime.now(timezone.utc).isoformat()
engine=create_engine(DATABASE_URL,connect_args={'check_same_thread':False,'timeout':30})
@event.listens_for(engine,'connect')
def setup(db,_):
    db.execute('PRAGMA journal_mode=WAL');db.execute('PRAGMA busy_timeout=30000');db.execute('PRAGMA foreign_keys=ON')
Session=sessionmaker(engine,expire_on_commit=False)
Base=declarative_base()
class Video(Base):
    __tablename__='videos'
    id=Column(String,primary_key=True,default=uid);original_name=Column(String);storage_key=Column(String,unique=True);sha256=Column(String);duration_s=Column(Float);fps=Column(Float);width=Column(Integer);height=Column(Integer);is_demo=Column(Boolean,default=False);created_at=Column(String,default=now)
class Analysis(Base):
    __tablename__='analyses'
    id=Column(String,primary_key=True,default=uid);video_id=Column(String,ForeignKey('videos.id'));provider=Column(String);status=Column(String,default='queued');scenario=Column(String);config_json=Column(JSON,default=dict);model_version=Column(String);source_kind=Column(String);external_analysis_id=Column(String);input_hash=Column(String);idempotency_key=Column(String,unique=True);owner=Column(String);attempt=Column(Integer,default=0);heartbeat_at=Column(String);error_json=Column(JSON);result_storage_key=Column(String);created_at=Column(String,default=now);started_at=Column(String);finished_at=Column(String)
class Track(Base):
    __tablename__='tracks'
    analysis_id=Column(String,ForeignKey('analyses.id'),primary_key=True);track_id=Column(String,primary_key=True)
class Observed(Base):
    __tablename__='observed_intervals'
    id=Column(String,primary_key=True,default=uid);analysis_id=Column(String);track_id=Column(String);start_s=Column(Float);end_s=Column(Float)
    __table_args__=(ForeignKeyConstraint(['analysis_id','track_id'],['tracks.analysis_id','tracks.track_id']),)
class Segment(Base):
    __tablename__='segments'
    analysis_id=Column(String,primary_key=True);segment_id=Column(String,primary_key=True);track_id=Column(String);behavior=Column(String);start_s=Column(Float);end_s=Column(Float)
    __table_args__=(ForeignKeyConstraint(['analysis_id','track_id'],['tracks.analysis_id','tracks.track_id']),)
class Document(Base):
    __tablename__='documents'
    id=Column(String,primary_key=True,default=uid);title=Column(String);source_title=Column(String);source_url=Column(String);applicability=Column(String);is_demo=Column(Boolean,default=False);active_version=Column(Integer);created_at=Column(String,default=now);deleted_at=Column(String)
class Version(Base):
    __tablename__='document_versions'
    document_id=Column(String,ForeignKey('documents.id'),primary_key=True);version=Column(Integer,primary_key=True);content_hash=Column(String);storage_key=Column(String);status=Column(String,default='pending');error_json=Column(JSON);index_fingerprint=Column(String);created_at=Column(String,default=now)
class Chunk(Base):
    __tablename__='chunks'
    id=Column(String,primary_key=True,default=uid);document_id=Column(String,ForeignKey('documents.id'));version=Column(Integer);text=Column(String);page=Column(Integer);section=Column(String);ordinal=Column(Integer);vector_id=Column(String)
class ChatSession(Base):
    __tablename__='chat_sessions'
    id=Column(String,primary_key=True,default=uid);analysis_id=Column(String,ForeignKey('analyses.id'));selected_track_id=Column(String);selected_range_json=Column(JSON);created_at=Column(String,default=now)
class Turn(Base):
    __tablename__='chat_turns'
    id=Column(String,primary_key=True,default=uid);session_id=Column(String,ForeignKey('chat_sessions.id'));client_message_id=Column(String);input_hash=Column(String);status=Column(String);assistant_id=Column(String)
    __table_args__=(UniqueConstraint('session_id','client_message_id'),)
class SessionSelection(Base):
    __tablename__='session_ui_selections'
    session_id=Column(String,ForeignKey('chat_sessions.id'),primary_key=True);ui_json=Column(JSON)
class Message(Base):
    __tablename__='messages'
    id=Column(String,primary_key=True,default=uid);session_id=Column(String,ForeignKey('chat_sessions.id'));client_message_id=Column(String);role=Column(String);status=Column(String);content_json=Column(JSON);created_at=Column(String,default=now)
class ToolCall(Base):
    __tablename__='tool_calls'
    id=Column(String,primary_key=True,default=uid);message_id=Column(String,ForeignKey('messages.id'));name=Column(String);arguments_json=Column(JSON);result_json=Column(JSON);started_at=Column(String);finished_at=Column(String);status=Column(String)
class Evidence(Base):
    __tablename__='evidence_records'
    ref_id=Column(String,primary_key=True);session_id=Column(String);analysis_id=Column(String);message_id=Column(String);kind=Column(String);payload_json=Column(JSON);created_at=Column(String,default=now)
class Runtime(Base):
    __tablename__='runtime'
    id=Column(String,primary_key=True);heartbeat_at=Column(String)

def init():Base.metadata.create_all(engine)
def obj(row):return {c.name:getattr(row,c.name) for c in row.__table__.columns}
