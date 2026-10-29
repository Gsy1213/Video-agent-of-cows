from typing import Generic,TypeVar,Literal,Any
from pydantic import BaseModel,ConfigDict,Field,model_validator

class Strict(BaseModel):model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
class Range(Strict):
    start_s:float=Field(ge=0)
    end_s:float=Field(gt=0)
    @model_validator(mode='after')
    def ordered(self):
        if self.end_s<=self.start_s:raise ValueError('起点必须小于终点')
        return self
class VideoDTO(Strict):
    id:str;original_name:str;duration_s:float;fps:float;width:int;height:int;sha256:str;is_demo:bool;media_url:str;created_at:str
class AnalysisDTO(Strict):
    id:str;video_id:str;provider:str;status:str;source_kind:str|None;model_version:str|None;progress:float|None;warnings:list[str];error:dict|None;created_at:str;started_at:str|None;finished_at:str|None
class Behavior(Strict):
    code:str;label:str;definition:str;source_class_id:int|None=None
class AnalysisDetail(Strict):
    analysis:AnalysisDTO;behavior_catalog:list[Behavior];duration_s:float
class TrackDTO(Strict):
    analysis_id:str;track_id:str;display_name:str
class SegmentDTO(Strict):
    analysis_id:str;segment_id:str;track_id:str;behavior:str;start_s:float;end_s:float
class BehaviorStats(Strict):
    code:str;label:str;duration_s:float;ratio:float|None;segment_count:int
class TrackStats(Strict):
    analysis_id:str;track_id:str;range:Range;window_duration_s:float;observed_duration_s:float;unknown_duration_s:float;classified_duration_s:float;unobserved_duration_s:float;observation_coverage:float;classification_coverage:float|None;behaviors:list[BehaviorStats]
class StatsDTO(Strict):
    range:Range;items:list[TrackStats];basis:Literal['classified_duration']
class DocumentDTO(Strict):
    id:str;title:str;source_title:str;source_url:str|None;applicability:str;is_demo:bool;active_version:int|None;latest_version:int;status:str;chunk_count:int;error:dict|None;created_at:str
class ChunkDTO(Strict):
    id:str;document_id:str;version:int;title:str;text:str;page:int|None;section:str|None;source_url:str|None;is_demo:bool;source_status:str
class SearchMatch(Strict):chunk:ChunkDTO;score:float
class SearchDTO(Strict):retrieval_mode:str;matches:list[SearchMatch];warnings:list[str]
class SessionDTO(Strict):
    id:str;analysis_id:str|None;selected_track_id:str|None;selected_range:Range|None;created_at:str
class Fact(Strict):
    ref_id:str;analysis_id:str;track_id:str;range:Range;metric:str;behavior:str|None;label:str;value:float|None;unit:Literal['seconds','ratio','count']
class VideoEvidence(SegmentDTO):ref_id:str;video_id:str
class KnowledgeEvidence(Strict):
    ref_id:str;document_id:str;document_version:int;chunk_id:str;title:str;text:str;page:int|None;section:str|None;source_url:str|None;is_demo:bool;source_status:str
class Trace(Strict):tool:str;status:str;duration_ms:int
class Modes(Strict):vision:str;llm:str;retrieval:str
class Answer(Strict):
    answer_text:str;facts:list[Fact];video_evidence:list[VideoEvidence];knowledge_evidence:list[KnowledgeEvidence];limitations:list[str];execution_trace:list[Trace];modes:Modes;history_records:list[dict[str,Any]]=Field(default_factory=list)
class MessageDTO(Strict):
    id:str;session_id:str;client_message_id:str;role:str;status:str;text:str;answer:Answer|None;created_at:str
class CreateAnalysis(Strict):
    provider:Literal['mock','command']='mock'
    scenario:Literal['normal','no_detections','unknown_only','provider_failure']='normal'
    @model_validator(mode='after')
    def check(self):
        if self.provider=='command' and self.scenario!='normal':raise ValueError('command 不接受演示场景')
        return self
class CreateSession(Strict):analysis_id:str|None=None
class SendMessage(Strict):
    client_message_id:str=Field(min_length=1,max_length=120)
    text:str=Field(min_length=1,max_length=4000)
    selected_track_id:str|None=None
    range:Range|None=None
class SearchRequest(Strict):query:str=Field(min_length=1,max_length=2000);top_k:int=Field(default=5,ge=1,le=10)
class HistoryRequest(Strict):
    cow:int=Field(default=1,ge=1,le=16)
    start:str='2023-07-21';end:str='2023-07-25';kind:Literal['daily','events','compare']='daily';behavior:str='feeding';start_time:str='00:00:00';end_time:str='24:00:00';limit:int=Field(default=10,ge=1,le=50)
T=TypeVar('T')
class Envelope(BaseModel,Generic[T]):data:T;request_id:str
class Page(BaseModel,Generic[T]):items:list[T];next_cursor:str|None
class SegmentPage(Page[SegmentDTO]):applied_range:Range
class VideoDetail(Strict):video:VideoDTO;analyses:list[AnalysisDTO]
