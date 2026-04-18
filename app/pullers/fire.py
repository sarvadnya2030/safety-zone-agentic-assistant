"""
Forest Fire Alerts puller.
Source: https://fsiforestfire.gov.in — ISRO MODIS/VIIRS data, updates every 15 min.
Endpoints:
  /FirePointSearch  — near-real-time fire hotspots (POST form)
  /LargeForestFire/CurrentLFF — active large forest fires
"""
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import httpx

from app.pullers.base import USER_AGENT, DEFAULT_TIMEOUT
from app.schemas import Event
from app.store.cache import cache_get, cache_set
from app.config import cfg

logger = logging.getLogger(__name__)

FSI_BASE = "https://fsiforestfire.gov.in"
FSI_FIRE_SEARCH = f"{FSI_BASE}/FirePointSearch"
FSI_LFF_CURRENT = f"{FSI_BASE}/LargeForestFire/CurrentLFF"

# MODIS/VIIRS fire data — state-level queries
PRIORITY_STATES = [
    "Uttarakhand", "Himachal Pradesh", "Uttaranchal",
    "Odisha", "Jharkhand", "Chhattisgarh", "Madhya Pradesh",
    "Maharashtra", "Karnataka", "Andhra Pradesh", "Telangana",
    "Assam", "Mizoram", "Manipur", "Nagaland",
]


async def pull_fire_alerts() -> List[Event]:
    ttl = cfg("ttl.alerts_sec", 300)
    cached = cache_get("fire:alerts")
    if cached:
        return [Event(**e) for e in cached]

    events: List[Event] = []

    # Current large forest fires
    try:
        lff_events = await _fetch_large_fires()
        events.extend(lff_events)
    except Exception as exc:
        logger.warning("FSI large fire fetch failed: %s", exc)

    # NRT fire points for priority states (last 24h, sample a few states)
    now = datetime.now(timezone.utc)
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    today = now.strftime("%Y-%m-%d")

    for state in PRIORITY_STATES[:6]:  # cap at 6 states to avoid hammering
        try:
            state_events = await _fetch_fire_points(state, yesterday, today)
            events.extend(state_events)
        except Exception as exc:
            logger.debug("FSI fire point fetch failed for %s: %s", state, exc)

    cache_set("fire:alerts", [e.model_dump() for e in events], ttl)
    return events


async def _fetch_large_fires() -> List[Event]:
    async with httpx.AsyncClient(
        timeout=DEFAULT_TIMEOUT, headers={"User-Agent": USER_AGENT}
    ) as client:
        resp = await client.get(FSI_LFF_CURRENT)
        resp.raise_for_status()
        return _parse_html_fires(resp.text, source="FSI/LargeForestFire", severity="high")


async def _fetch_fire_points(state: str, from_date: str, to_date: str) -> List[Event]:
    """POST to FirePointSearch for a given state and date range."""
    form_data = {
        "from_date": from_date,
        "to_date": to_date,
        "sensor": "Both",
        "state": state,
    }
    async with httpx.AsyncClient(
        timeout=DEFAULT_TIMEOUT + 10, headers={"User-Agent": USER_AGENT}
    ) as client:
        resp = await client.post(FSI_FIRE_SEARCH, data=form_data)
        resp.raise_for_status()
        return _parse_html_fires(resp.text, source="FSI/MODIS-VIIRS", severity="moderate",
                                 default_state=state)


def _parse_html_fires(html: str, source: str, severity: str, default_state: Optional[str] = None) -> List[Event]:
    """Extract fire hotspot records from FSI HTML response."""
    import re
    events = []
    now_iso = datetime.now(timezone.utc).isoformat()

    if "no fire points found" in html.lower() or "no large forest fire" in html.lower():
        return []

    # Try to extract tabular data rows: lat, lon, date, state, etc.
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.IGNORECASE | re.DOTALL)
    for row in rows[1:]:  # skip header
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.IGNORECASE | re.DOTALL)
        cells = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
        if len(cells) < 3:
            continue

        # Try to find lat/lon in cells
        lat, lon = None, None
        for cell in cells:
            try:
                val = float(cell)
                if 6 <= val <= 38 and lat is None:
                    lat = val
                elif 68 <= val <= 98 and lon is None:
                    lon = val
            except ValueError:
                pass

        state = default_state
        for cell in cells:
            if len(cell) > 3 and any(s.lower() in cell.lower() for s in PRIORITY_STATES):
                state = cell
                break

        text = " | ".join(c for c in cells if c)
        uid = hashlib.md5(f"fire:{text[:80]}".encode()).hexdigest()[:16]
        events.append(Event(
            id=f"fire:{uid}",
            source=source,
            source_type="api",
            hazard_type="fire",
            severity=severity,
            ts_start=now_iso,
            state=state,
            lat=lat,
            lon=lon,
            summary=f"Forest fire detected: {text[:200]}",
            raw_text=text,
            confidence=0.88,
        ))

    # If no structured rows found, create a single summary event
    if not events and len(html) > 200:
        fire_text = re.sub(r"<[^>]+>", " ", html)
        fire_text = re.sub(r"\s+", " ", fire_text).strip()[:300]
        uid = hashlib.md5(f"fire:html:{fire_text[:60]}".encode()).hexdigest()[:16]
        events.append(Event(
            id=f"fire:summary:{uid}",
            source=source,
            source_type="api",
            hazard_type="fire",
            severity=severity,
            ts_start=now_iso,
            state=default_state,
            summary=f"Forest fire activity detected ({default_state or 'India'})",
            raw_text=fire_text,
            confidence=0.65,
        ))

    return events[:30]
