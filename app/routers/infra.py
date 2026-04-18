"""GET /infra — OSM infrastructure profile around a lat/lon."""
from typing import Any, Dict
from fastapi import APIRouter, Query
from app.pullers.osm import pull_osm_infra_profile

router = APIRouter(prefix="/infra", tags=["infrastructure"])


@router.get("", response_model=Dict[str, Any])
async def area_infra_profile(
    lat: float = Query(..., description="Centre latitude"),
    lon: float = Query(..., description="Centre longitude"),
    radius_m: int = Query(5000, description="Search radius in metres (max 20000)"),
):
    radius_m = min(radius_m, 20000)
    return await pull_osm_infra_profile(lat, lon, radius_m=radius_m)
