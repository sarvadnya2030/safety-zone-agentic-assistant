"""SACHET NDMA CAP/RSS alert puller."""
import hashlib
import logging
from datetime import datetime, timezone
from typing import List

from app.pullers.base import fetch_text
from app.schemas import Event
from app.store.cache import cache_get, cache_set
from app.config import cfg

logger = logging.getLogger(__name__)

# CAP RSS feed (primary) + HTML scrape fallbacks
SACHET_RSS_URLS = [
    "https://sachet.ndma.gov.in/CapFeed",
    "https://sachet.ndma.gov.in/cap_public_website/FetchAllAlertDetails",
    "https://sachet.ndma.gov.in/cap_public_website/FetchActiveAlerts",
]


async def pull_sachet_alerts() -> List[Event]:
    ttl = cfg("ttl.alerts_sec", 300)
    cached = cache_get("sachet:alerts")
    if cached:
        return [Event(**e) for e in cached]

    try:
        import feedparser
        text = await fetch_text(SACHET_RSS_URLS)
        feed = feedparser.parse(text)
        events = _parse_feed(feed)
    except Exception as exc:
        logger.error("SACHET pull failed: %s", exc)
        return []

    cache_set("sachet:alerts", [e.model_dump() for e in events], ttl)
    return events


def _parse_feed(feed) -> List[Event]:
    events = []
    for entry in feed.get("entries", []):
        title = entry.get("title", "")
        summary = entry.get("summary", title)
        published = entry.get("published", datetime.now(timezone.utc).isoformat())
        link = entry.get("link", "")
        tags = entry.get("tags", [])

        state, district = _extract_location(title + " " + summary)
        severity = _extract_severity(title + " " + summary)
        hazard = _extract_hazard(title + " " + summary)

        uid = hashlib.md5(f"sachet:{link or title}".encode()).hexdigest()[:16]
        events.append(Event(
            id=f"sachet:{uid}",
            source="SACHET/NDMA",
            source_type="rss",
            hazard_type=hazard,
            severity=severity,
            ts_start=published,
            state=state,
            district=district,
            summary=summary[:500],
            raw_text=summary,
            confidence=0.95,
        ))
    return events


def _extract_severity(text: str) -> str:
    t = text.lower()
    if any(w in t for w in ("red alert", "extreme", "critical", "severe", "very heavy")):
        return "critical"
    if any(w in t for w in ("orange alert", "high", "heavy rain", "warning")):
        return "high"
    if any(w in t for w in ("yellow alert", "watch", "moderate")):
        return "moderate"
    return "low"


def _extract_hazard(text: str) -> str:
    t = text.lower()
    if any(w in t for w in ("flood", "inundation", "waterlogging")):
        return "flood"
    if any(w in t for w in ("cyclone", "hurricane", "storm surge")):
        return "cyclone"
    if any(w in t for w in ("earthquake", "tremor", "seismic")):
        return "earthquake"
    if any(w in t for w in ("landslide", "mudslide")):
        return "landslide"
    if any(w in t for w in ("fire", "wildfire", "blaze")):
        return "fire"
    if any(w in t for w in ("heatwave", "heat wave")):
        return "heatwave"
    return "unknown"


def _extract_location(text: str):
    INDIAN_STATES = [
        "Maharashtra", "Kerala", "Karnataka", "Tamil Nadu", "Andhra Pradesh",
        "Odisha", "West Bengal", "Gujarat", "Rajasthan", "Bihar", "Assam",
        "Uttarakhand", "Himachal Pradesh", "Jammu", "Kashmir", "Manipur",
        "Nagaland", "Mizoram", "Tripura", "Meghalaya", "Sikkim", "Goa",
        "Punjab", "Haryana", "Uttar Pradesh", "Madhya Pradesh", "Chhattisgarh",
        "Jharkhand", "Telangana", "Arunachal Pradesh",
    ]
    state = next((s for s in INDIAN_STATES if s.lower() in text.lower()), None)
    return state, None
