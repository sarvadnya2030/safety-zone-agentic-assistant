"""ReliefWeb API puller for situation reports and humanitarian updates."""
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from typing import List

from app.pullers.base import fetch_json
from app.schemas import Event
from app.store.cache import cache_get, cache_set
from app.config import cfg

logger = logging.getLogger(__name__)

RELIEFWEB_API = "https://api.reliefweb.int/v1/reports"


async def pull_reliefweb_sitreps(country: str = "IND", limit: int = 20) -> List[Event]:
    ttl = cfg("ttl.reliefweb_sec", 86400)
    key = f"reliefweb:sitreps:{country}"
    cached = cache_get(key)
    if cached:
        return [Event(**e) for e in cached]

    payload = {
        "filter": {
            "operator": "AND",
            "conditions": [
                {"field": "primary_country.iso3", "value": country},
                {"field": "format.name", "value": "Situation Report"},
            ],
        },
        "sort": ["date.created:desc"],
        "limit": limit,
        "fields": {"include": ["title", "body", "date", "source", "url", "primary_country"]},
    }

    events: List[Event] = []
    try:
        data = await fetch_json(
            [RELIEFWEB_API],
            params={"appname": "civilian-safety-monitor"},
        )
        events = _parse_reliefweb(data)
    except Exception as exc:
        logger.error("ReliefWeb pull failed: %s", exc)

    cache_set(key, [e.model_dump() for e in events], ttl)
    return events


def _parse_reliefweb(data) -> List[Event]:
    events = []
    for item in data.get("data", [])[:20]:
        fields = item.get("fields", {})
        title = fields.get("title", "Situation report")
        body = fields.get("body", "")
        date_info = fields.get("date", {})
        ts = date_info.get("created", datetime.now(timezone.utc).isoformat()) if isinstance(date_info, dict) else datetime.now(timezone.utc).isoformat()
        source_list = fields.get("source", [{}])
        source_name = source_list[0].get("name", "ReliefWeb") if source_list else "ReliefWeb"
        url = fields.get("url", "")

        uid = hashlib.md5(f"rw:{title[:80]}".encode()).hexdigest()[:16]
        events.append(Event(
            id=f"reliefweb:{uid}",
            source=source_name,
            source_type="bulletin",
            hazard_type="unknown",
            severity="moderate",
            ts_start=str(ts),
            summary=title,
            raw_text=body[:2000] if body else title,
            confidence=0.85,
        ))
    return events
