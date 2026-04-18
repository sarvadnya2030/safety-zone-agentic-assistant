"""
IMD weather puller.
Primary: city weather HTML pages at city.imd.gov.in (public, no auth).
Secondary: mausam.imd.gov.in warning bulletins RSS/HTML.
Note: full JSON API requires IP whitelisting via city.imd.gov.in/citywx/api_request.php
"""
import hashlib
import logging
import re
from datetime import datetime, timezone
from typing import List, Optional

from app.pullers.base import fetch_text
from app.schemas import Event
from app.store.cache import cache_get, cache_set
from app.config import cfg

logger = logging.getLogger(__name__)

# Public city weather pages — no auth required
# city_id list: https://city.imd.gov.in/citywx/city_weather.php
IMD_CITY_URL = "https://city.imd.gov.in/citywx/responsive"
IMD_WARNING_RSS = "https://mausam.imd.gov.in/imd_latest/contents/warning_bulletin.php"

# Key Indian cities with IMD station IDs
# IDs sourced from imd-weather-rest open-source wrappers
MAJOR_CITIES = [
    ("Mumbai",     "Maharashtra", 43003),
    ("Delhi",      "Delhi",       42182),
    ("Chennai",    "Tamil Nadu",  43279),
    ("Kolkata",    "West Bengal", 42809),
    ("Pune",       "Maharashtra", 43063),
    ("Hyderabad",  "Telangana",   43128),
    ("Bengaluru",  "Karnataka",   43295),
    ("Ahmedabad",  "Gujarat",     42647),
    ("Jaipur",     "Rajasthan",   42360),
    ("Bhubaneswar","Odisha",      43150),
    ("Guwahati",   "Assam",       42410),
    ("Kochi",      "Kerala",      43371),
    ("Thiruvananthapuram", "Kerala", 43369),
    ("Patna",      "Bihar",       42492),
    ("Dehradun",   "Uttarakhand", 42316),
    ("Shimla",     "Himachal Pradesh", 42333),
    ("Srinagar",   "Jammu & Kashmir", 42028),
]


async def pull_imd_warnings() -> List[Event]:
    ttl = cfg("ttl.alerts_sec", 300)
    cached = cache_get("imd:warnings")
    if cached:
        return [Event(**e) for e in cached]

    events: List[Event] = []

    # Pull city weather pages concurrently for warning signals
    for city_name, state, city_id in MAJOR_CITIES:
        try:
            text = await fetch_text([f"{IMD_CITY_URL}?id={city_id}"])
            city_events = _parse_city_weather(text, city_name, state, city_id)
            events.extend(city_events)
        except Exception as exc:
            logger.debug("IMD city %s (id=%s) fetch failed: %s", city_name, city_id, exc)
            continue

    # Also try warning bulletin page
    try:
        text = await fetch_text([IMD_WARNING_RSS])
        events.extend(_parse_warning_bulletin(text))
    except Exception as exc:
        logger.debug("IMD warning bulletin fetch failed: %s", exc)

    if not events:
        logger.warning("IMD: no data retrieved from any source")

    cache_set("imd:warnings", [e.model_dump() for e in events], ttl)
    return events


def _parse_city_weather(html: str, city_name: str, state: str, city_id: int) -> List[Event]:
    """Extract weather warnings from IMD city weather HTML page."""
    events = []
    now_iso = datetime.now(timezone.utc).isoformat()

    # Look for warning/alert keywords in the HTML
    warning_patterns = [
        (r"(red\s+alert[^<]{0,200})", "critical"),
        (r"(orange\s+alert[^<]{0,200})", "high"),
        (r"(yellow\s+alert[^<]{0,200})", "moderate"),
        (r"(heavy\s+rain(?:fall)?[^<]{0,150})", "high"),
        (r"(very\s+heavy\s+rain[^<]{0,150})", "critical"),
        (r"(cyclone[^<]{0,150})", "critical"),
        (r"(thunderstorm[^<]{0,150})", "moderate"),
        (r"(heat\s+wave[^<]{0,150})", "high"),
        (r"(cold\s+wave[^<]{0,150})", "moderate"),
    ]

    found_warnings = []
    for pattern, severity in warning_patterns:
        matches = re.findall(pattern, html, re.IGNORECASE)
        for m in matches[:2]:
            text = re.sub(r"<[^>]+>", " ", m).strip()
            text = re.sub(r"\s+", " ", text)
            if len(text) > 10:
                found_warnings.append((text, severity))

    # Deduplicate by text similarity
    seen = set()
    for text, severity in found_warnings:
        key = text[:50].lower()
        if key in seen:
            continue
        seen.add(key)
        hazard = _classify_hazard(text)
        uid = hashlib.md5(f"imd:{city_id}:{text[:60]}".encode()).hexdigest()[:16]
        events.append(Event(
            id=f"imd:{uid}",
            source="IMD",
            source_type="api",
            hazard_type=hazard,
            severity=severity,
            ts_start=now_iso,
            state=state,
            district=city_name,
            summary=f"IMD {city_name}: {text[:200]}",
            raw_text=text,
            confidence=0.85,
        ))

    return events


def _parse_warning_bulletin(html: str) -> List[Event]:
    """Parse IMD warning bulletin page for state-level warnings."""
    events = []
    now_iso = datetime.now(timezone.utc).isoformat()

    # Extract warning text blocks
    lines = [re.sub(r"<[^>]+>", " ", line).strip()
             for line in html.split("\n") if len(line.strip()) > 30]

    for line in lines[:50]:
        line = re.sub(r"\s+", " ", line).strip()
        if not any(kw in line.lower() for kw in ("warning", "alert", "heavy", "cyclone", "watch")):
            continue
        severity = _classify_severity(line)
        if severity == "low":
            continue
        uid = hashlib.md5(f"imd:bulletin:{line[:80]}".encode()).hexdigest()[:16]
        events.append(Event(
            id=f"imd:bulletin:{uid}",
            source="IMD",
            source_type="bulletin",
            hazard_type=_classify_hazard(line),
            severity=severity,
            ts_start=now_iso,
            summary=line[:300],
            raw_text=line,
            confidence=0.8,
        ))

    return events[:20]


def _classify_hazard(text: str) -> str:
    t = text.lower()
    if any(w in t for w in ("flood", "heavy rain", "rainfall", "inundation")):
        return "flood"
    if any(w in t for w in ("cyclone", "depression", "landfall", "storm surge")):
        return "cyclone"
    if "heatwave" in t or "heat wave" in t:
        return "heatwave"
    if "thunderstorm" in t or "lightning" in t:
        return "storm"
    if "cold wave" in t or "fog" in t:
        return "cold_wave"
    return "weather"


def _classify_severity(text: str) -> str:
    t = text.lower()
    if any(w in t for w in ("extremely heavy", "red alert", "very high", "very heavy")):
        return "critical"
    if any(w in t for w in ("heavy", "orange", "warning", "high alert")):
        return "high"
    if any(w in t for w in ("moderate", "yellow", "watch")):
        return "moderate"
    return "low"
