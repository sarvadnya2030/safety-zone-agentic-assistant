"""Tool specs (JSON schema) and Python dispatchers for the agent loop."""
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List

from app.config import cfg

logger = logging.getLogger(__name__)

# ── Tool JSON specs ────────────────────────────────────────────────────────────

TOOL_SPECS = [
    {
        "type": "function",
        "function": {
            "name": "fetch_live_alerts",
            "description": (
                "Fetch current hazard alerts from SACHET/NDMA (CAP/RSS), IMD city weather, "
                "NCS/USGS earthquakes, and FSI forest fire hotspots (MODIS/VIIRS, 15-min updates). "
                "Returns normalised Event objects with source, severity, location, and timestamp."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "state": {"type": "string", "description": "Indian state name (optional)"},
                    "district": {"type": "string", "description": "District name (optional)"},
                    "since_hours": {"type": "integer", "description": "How many hours back to look (default 24)", "default": 24},
                    "hazard_type": {"type": "string", "description": "Filter: flood | earthquake | cyclone | landslide | fire | any", "default": "any"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rag_search",
            "description": (
                "Search the knowledge base of NDMA SOPs, ReliefWeb situation reports, "
                "flood inventory, and landslide atlas documents. Returns relevant text "
                "chunks with citations."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Natural language search query"},
                    "top_k": {"type": "integer", "description": "Number of chunks to return (default 6)", "default": 6},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_relief_camps",
            "description": (
                "Find relief camps, shelters, hospitals, and water points near a location. "
                "Returns list of Camp objects with confidence tier."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "lat": {"type": "number", "description": "Latitude of search centre"},
                    "lon": {"type": "number", "description": "Longitude of search centre"},
                    "radius_km": {"type": "number", "description": "Search radius in km (default 20)", "default": 20},
                },
                "required": ["lat", "lon"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_district_risk",
            "description": (
                "Compute and return the deterministic safety risk score for a district. "
                "Returns score (0–1), label (Safe/Moderate/Unsafe), and score components."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "district": {"type": "string", "description": "District name"},
                    "state": {"type": "string", "description": "State name (optional)"},
                },
                "required": ["district"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "osm_area_profile",
            "description": (
                "Get a comprehensive OSM infrastructure profile around a lat/lon point. "
                "Returns categorised lists of: medical (hospitals, clinics, pharmacies), "
                "shelter (relief camps, refugee sites, assembly points), water (wells, drinking water), "
                "food (food banks, markets), security (police, fire stations), "
                "evacuation (schools, colleges, civic halls), transport (bus stops, railway stations), "
                "and hazard indicators (industrial zones, flood-prone areas). "
                "Also returns a composite safety score. Use this for area intelligence queries."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "lat": {"type": "number", "description": "Centre latitude"},
                    "lon": {"type": "number", "description": "Centre longitude"},
                    "radius_m": {"type": "integer", "description": "Search radius in metres (default 5000)", "default": 5000},
                },
                "required": ["lat", "lon"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "spatial_events",
            "description": "Fetch hazard events near a lat/lon point within a radius and time window.",
            "parameters": {
                "type": "object",
                "properties": {
                    "lat": {"type": "number"},
                    "lon": {"type": "number"},
                    "radius_km": {"type": "number", "default": 50},
                    "since_hours": {"type": "integer", "default": 24},
                },
                "required": ["lat", "lon"],
            },
        },
    },
]


# ── Dispatcher ─────────────────────────────────────────────────────────────────

async def dispatch(name: str, arguments: str) -> Any:
    """Route a tool call to the correct async handler."""
    try:
        args = json.loads(arguments) if arguments else {}
    except json.JSONDecodeError:
        args = {}

    if name == "fetch_live_alerts":
        return await _fetch_live_alerts(**args)
    if name == "rag_search":
        return await _rag_search(**args)
    if name == "find_relief_camps":
        return await _find_relief_camps(**args)
    if name == "get_district_risk":
        return await _get_district_risk(**args)
    if name == "osm_area_profile":
        return await _osm_area_profile(**args)
    if name == "spatial_events":
        return await _spatial_events(**args)
    return {"error": f"unknown tool: {name}"}


# ── Handlers ──────────────────────────────────────────────────────────────────

async def _fetch_live_alerts(
    state=None, district=None, since_hours=24, hazard_type="any"
) -> List[Dict]:
    from app.pullers.sachet import pull_sachet_alerts
    from app.pullers.imd import pull_imd_warnings
    from app.pullers.ncs import pull_ncs_earthquakes
    from app.normalize.event import ingest_events
    from app.store.db import query_events

    since_iso = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).isoformat()

    # Pull and ingest (cache internally)
    from app.pullers.fire import pull_fire_alerts
    sachet = await pull_sachet_alerts()
    imd = await pull_imd_warnings()
    ncs = await pull_ncs_earthquakes(since_hours=since_hours)
    fire = await pull_fire_alerts()
    all_events = sachet + imd + ncs + fire
    if all_events:
        ingest_events(all_events)

    ht = None if hazard_type in (None, "any") else hazard_type
    results = query_events(district=district, state=state, since=since_iso, hazard_type=ht, limit=30)
    return [_event_summary(e) for e in results]


async def _rag_search(query: str, top_k: int = 6) -> List[Dict]:
    from app.rag.ingest import get_hybrid_retriever, get_chunk_meta
    retriever = get_hybrid_retriever()
    if retriever is None:
        return [{"error": "RAG index not loaded — run scripts/build_index.py"}]
    results = retriever.retrieve(query, top_k=top_k, rrf_k=cfg("retrieval.rrf_k", 60))
    return [
        {"chunk_id": cid, "score": round(score, 4), **get_chunk_meta(cid)}
        for cid, score in results
    ]


async def _find_relief_camps(lat: float, lon: float, radius_km: float = 20) -> List[Dict]:
    from app.pullers.osm import pull_osm_camps
    from app.normalize.event import ingest_camps
    from app.store.spatial import bbox_from_point, nearest_k
    from app.store.db import query_camps_in_bbox

    camps = await pull_osm_camps(lat, lon, radius_m=int(radius_km * 1000))
    if camps:
        ingest_camps(camps)

    min_lat, max_lat, min_lon, max_lon = bbox_from_point(lat, lon, radius_km)
    db_camps = query_camps_in_bbox(min_lat, max_lat, min_lon, max_lon)

    ranked = nearest_k(db_camps, lambda c: c.lat, lambda c: c.lon, lat, lon, radius_km)
    return [
        {**c.model_dump(), "distance_km": round(d, 2)}
        for c, d in ranked[:20]
    ]


async def _get_district_risk(district: str, state=None) -> Dict:
    from app.insights.scoring import compute_district_risk
    return compute_district_risk(district, state)


async def _osm_area_profile(lat: float, lon: float, radius_m: int = 5000) -> Dict:
    from app.pullers.osm import pull_osm_infra_profile
    profile = await pull_osm_infra_profile(lat, lon, radius_m=radius_m)
    # Trim tags noise for the LLM — keep name, type, distance, confidence per item
    slim = {
        "center": profile["center"],
        "radius_m": profile["radius_m"],
        "element_count": profile["element_count"],
        "safety_score": profile["safety_score"],
        "category_counts": profile["category_counts"],
        "by_category": {
            cat: [
                {"name": it["name"], "distance_km": it["distance_km"],
                 "confidence": it["confidence"]}
                for it in items[:10]  # cap 10 per category
            ]
            for cat, items in profile["by_category"].items()
            if items
        },
    }
    return slim


async def _spatial_events(lat: float, lon: float, radius_km: float = 50, since_hours: int = 24) -> List[Dict]:
    from app.store.db import query_events
    from app.store.spatial import bbox_from_point, nearest_k

    since_iso = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).isoformat()
    min_lat, max_lat, min_lon, max_lon = bbox_from_point(lat, lon, radius_km)
    # Crude bbox first then haversine filter
    events = query_events(since=since_iso, limit=200)
    ranked = nearest_k(events, lambda e: e.lat, lambda e: e.lon, lat, lon, radius_km)
    return [
        {**_event_summary(e), "distance_km": round(d, 2)}
        for e, d in ranked[:30]
    ]


def _event_summary(event) -> Dict:
    return {
        "id": event.id,
        "source": event.source,
        "hazard_type": event.hazard_type,
        "severity": event.severity,
        "ts_start": event.ts_start,
        "state": event.state,
        "district": event.district,
        "summary": event.summary,
        "confidence": event.confidence,
    }
