from typing import List, Optional
from fastapi import APIRouter, Query
from app.schemas import Event
from app.store.db import query_events

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=List[Event])
async def get_events(
    district: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    since: Optional[str] = Query(None, description="ISO timestamp"),
    hazard_type: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
):
    return query_events(district=district, state=state, since=since,
                        hazard_type=hazard_type, limit=limit)
