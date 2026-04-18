"""NCS (National Centre for Seismology) earthquake feed puller."""
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from typing import List

from app.pullers.base import fetch_json
from app.schemas import Event
from app.store.cache import cache_get, cache_set
from app.config import cfg

logger = logging.getLogger(__name__)

# NCS data portal: https://seismo.gov.in/data-portal (SSL cert issues in many environments)
# USGS FDSN service is the reliable real-time fallback — covers India bbox
NCS_API_URL = "https://seismo.gov.in/fdsnws/event/1/query"
NCS_FALLBACK_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"


async def pull_ncs_earthquakes(since_hours: int = 24) -> List[Event]:
    ttl = cfg("ttl.alerts_sec", 300)
    key = f"ncs:quakes:{since_hours}h"
    cached = cache_get(key)
    if cached:
        return [Event(**e) for e in cached]

    start_time = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).strftime(
        "%Y-%m-%dT%H:%M:%S"
    )
    events: List[Event] = []

    try:
        data = await fetch_json(
            [NCS_API_URL],
            params={"starttime": start_time, "endtime": "now"},
        )
        events = _parse_ncs(data)
    except Exception as exc:
        logger.warning("NCS pull failed: %s — trying USGS fallback", exc)
        try:
            data = await fetch_json(
                [NCS_FALLBACK_URL],
                params={
                    "format": "geojson",
                    "starttime": start_time,
                    "minlatitude": 6,
                    "maxlatitude": 38,
                    "minlongitude": 68,
                    "maxlongitude": 98,
                    "orderby": "time",
                },
            )
            events = _parse_usgs(data)
        except Exception as exc2:
            logger.error("USGS fallback failed: %s", exc2)

    cache_set(key, [e.model_dump() for e in events], ttl)
    return events


def _parse_ncs(data) -> List[Event]:
    events = []
    items = data if isinstance(data, list) else data.get("features", [])
    for item in items[:50]:
        if isinstance(item, dict) and "properties" in item:
            return _parse_usgs({"features": items})
        if not isinstance(item, dict):
            continue
        mag = float(item.get("magnitude", item.get("mag", 0)))
        lat = item.get("latitude", item.get("lat"))
        lon = item.get("longitude", item.get("lon"))
        depth = item.get("depth", 0)
        ts = item.get("datetime", item.get("time", datetime.now(timezone.utc).isoformat()))
        place = item.get("place", item.get("region", "India"))
        uid = hashlib.md5(f"ncs:{lat}:{lon}:{ts}".encode()).hexdigest()[:16]
        events.append(Event(
            id=f"ncs:{uid}",
            source="NCS/India",
            source_type="api",
            hazard_type="earthquake",
            severity=_mag_to_severity(mag),
            ts_start=str(ts),
            lat=float(lat) if lat else None,
            lon=float(lon) if lon else None,
            summary=f"M{mag} earthquake near {place}, depth {depth}km",
            confidence=0.98,
        ))
    return events


def _parse_usgs(data) -> List[Event]:
    events = []
    for feature in data.get("features", [])[:50]:
        props = feature.get("properties", {})
        geo = feature.get("geometry", {})
        coords = geo.get("coordinates", [None, None, None])
        mag = float(props.get("mag", 0) or 0)
        place = props.get("place", "unknown")
        ts_ms = props.get("time")
        ts = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat() if ts_ms else datetime.now(timezone.utc).isoformat()
        uid = hashlib.md5(f"usgs:{feature.get('id', ts)}".encode()).hexdigest()[:16]
        events.append(Event(
            id=f"usgs:{uid}",
            source="USGS/NCS-fallback",
            source_type="api",
            hazard_type="earthquake",
            severity=_mag_to_severity(mag),
            ts_start=ts,
            lat=float(coords[1]) if coords[1] is not None else None,
            lon=float(coords[0]) if coords[0] is not None else None,
            summary=f"M{mag} earthquake: {place}",
            confidence=0.95,
        ))
    return events


def _mag_to_severity(mag: float) -> str:
    if mag >= 6.0:
        return "critical"
    if mag >= 5.0:
        return "high"
    if mag >= 4.0:
        return "moderate"
    return "low"
