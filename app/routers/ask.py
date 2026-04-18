from fastapi import APIRouter
from app.schemas import AskRequest, AskResponse, Citation
from app.agent import loop

router = APIRouter(prefix="/ask", tags=["assistant"])


@router.post("", response_model=AskResponse)
async def ask(req: AskRequest):
    result = await loop.run(
        query=req.query,
        lat=req.lat,
        lon=req.lon,
        district=req.district,
        state=req.state,
    )
    # Extract events/camps from raw tool results for the response
    events_used, camps_used = [], []
    for tr in result.get("raw_tool_results", []):
        tool = tr.get("tool", "")
        res = tr.get("result", [])
        if not isinstance(res, list):
            continue
        if tool in ("fetch_live_alerts", "spatial_events"):
            from app.schemas import Event
            for item in res:
                if isinstance(item, dict) and "hazard_type" in item:
                    try:
                        events_used.append(Event(**item))
                    except Exception:
                        pass
        if tool == "find_relief_camps":
            from app.schemas import Camp
            for item in res:
                if isinstance(item, dict) and "lat" in item:
                    try:
                        camps_used.append(Camp(**item))
                    except Exception:
                        pass

    return AskResponse(
        answer=result["answer"],
        reasoning=result.get("reasoning_content") or None,
        citations=[],
        tool_calls_made=result["tool_calls_made"],
        events_used=events_used[:10],
        camps_used=camps_used[:10],
    )
