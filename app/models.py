from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Modality(str, Enum):
    TRANSCRIPT = "transcript"
    FRAME = "frame"
    OCR = "ocr"
    VISION = "vision"
    IMAGE = "image"
    DOCUMENT = "document"


class EdgeMethod(str, Enum):
    TEMPORAL = "temporal"
    PROVENANCE = "provenance"
    ENTITY_MATCH = "entity_match"
    EMBEDDING = "embedding"
    LLM = "llm"


class SourceType(str, Enum):
    VIDEO = "video"
    PDF = "pdf"
    IMAGE = "image"


class SourceStatus(str, Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class Source(BaseModel):
    id: str
    filename: str
    source_type: SourceType
    path: str
    duration: Optional[float] = None
    status: SourceStatus = SourceStatus.UPLOADED
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class Observation(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    modality: Modality
    content: str
    source_id: str
    source_path: str
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    timestamp: Optional[float] = None
    confidence: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class SemanticEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    summary: str
    source_id: str
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    entities: List[str] = Field(default_factory=list)
    confidence: Optional[float] = None
    created_at: datetime = Field(default_factory=utc_now)


class Entity(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    normalized_name: str
    entity_type: Optional[str] = None
    confidence: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class EvidenceEdge(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    source_node_id: str
    target_node_id: str
    relation: str
    confidence: Optional[float] = None
    method: EdgeMethod
    evidence_observation_ids: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class EventObservation(BaseModel):
    event_id: str
    observation_id: str
    created_at: datetime = Field(default_factory=utc_now)
