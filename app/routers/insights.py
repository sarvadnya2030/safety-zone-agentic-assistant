from typing import Optional
from fastapi import APIRouter, Query
from app.schemas import DistrictRisk
from app.insights.scoring import compute_district_risk
from app.insights.summary import generate_district_summary

router = APIRouter(prefix="/insights", tags=["insights"])


@router.get("/district/{district}", response_model=DistrictRisk)
async def district_risk(
    district: str,
    state: Optional[str] = Query(None),
    explain: bool = Query(False, description="Add LLM explanation"),
):
    risk = compute_district_risk(district, state)
    explanation = None
    if explain:
        explanation = await generate_district_summary(risk)
    return DistrictRisk(
        district=risk["district"],
        state=risk.get("state"),
        score=risk["score"],
        label=risk["label"],
        components=risk["components"],
        active_events=risk["active_events"],
        explanation=explanation,
    )
