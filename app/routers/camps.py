from typing import List
from fastapi import APIRouter, Query
from app.schemas import Camp
from app.store.db import query_camps_in_bbox
from app.store.spatial import bbox_from_point, nearest_k
from app.pullers.osm import pull_osm_camps
from app.normalize.event import ingest_camps

router = APIRouter(prefix="/camps", tags=["camps"])


@router.get("", response_model=List[Camp])
async def get_camps(
    lat: float = Query(..., description="Centre latitude"),
    lon: float = Query(..., description="Centre longitude"),
    radius_km: float = Query(20.0, description="Search radius in km"),
    refresh: bool = Query(False, description="Force OSM re-fetch"),
):
    if refresh:
        camps = await pull_osm_camps(lat, lon, radius_m=int(radius_km * 1000))
        if camps:
            ingest_camps(camps)

    min_lat, max_lat, min_lon, max_lon = bbox_from_point(lat, lon, radius_km)
    db_camps = query_camps_in_bbox(min_lat, max_lat, min_lon, max_lon)
    ranked = nearest_k(db_camps, lambda c: c.lat, lambda c: c.lon, lat, lon, radius_km)

    result = []
    for camp, dist in ranked:
        camp.distance_km = round(dist, 2)
        result.append(camp)
    return result[:50]
