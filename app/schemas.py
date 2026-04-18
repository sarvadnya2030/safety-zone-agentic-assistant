from __future__ import annotations
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field


class Event(BaseModel):
    id: str
    source: str
    source_type: str  # api | rss | dataset | bulletin
    hazard_type: str  # flood | earthquake | cyclone | landslide | conflict | fire | unknown
    severity: str     # low | moderate | high | critical
    ts_start: str
    ts_end: Optional[str] = None
    state: Optional[str] = None
    district: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    polygon_wkt: Optional[str] = None
    summary: str
    raw_text: Optional[str] = None
    confidence: float = 1.0


class Camp(BaseModel):
    id: str
    name: str
    type: str          # relief_camp | shelter | evacuation_center | hospital | water_point | suspected_camp
    source: str        # osm | government | imagery | reported
    lat: float
    lon: float
    capacity: Optional[int] = None
    status: str = "unknown"
    confidence: str = "confirmed"  # confirmed | reported | suspected
    last_updated: Optional[str] = None
    distance_km: Optional[float] = None


class Citation(BaseModel):
    source: str
    source_type: str
    timestamp: Optional[str] = None
    url: Optional[str] = None


class AskRequest(BaseModel):
    query: str
    lat: Optional[float] = None
    lon: Optional[float] = None
    district: Optional[str] = None
    state: Optional[str] = None


class AskResponse(BaseModel):
    answer: str
    reasoning: Optional[str] = None   # nemotron thinking chain
    citations: List[Citation] = []
    tool_calls_made: int = 0
    events_used: List[Event] = []
    camps_used: List[Camp] = []


class DistrictRisk(BaseModel):
    district: str
    state: Optional[str] = None
    score: float
    label: str  # Safe | Moderate | Unsafe
    components: Dict[str, Any] = {}
    active_events: int = 0
    explanation: Optional[str] = None
