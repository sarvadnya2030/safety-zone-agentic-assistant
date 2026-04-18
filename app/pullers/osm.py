"""
OSM/Overpass puller — rich infrastructure extraction for safety insights.
Adapted from Ignisia src/osm_only_api/service.py with expanded amenity coverage.

Pulls: relief camps, shelters, hospitals, clinics, pharmacies, water, police,
fire stations, schools/colleges (evacuation use), food, transport, roads,
bridges, power infrastructure, and hazard-relevant land use.
"""
import hashlib
import logging
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.pullers.base import DEFAULT_TIMEOUT, USER_AGENT
from app.schemas import Camp
from app.store.cache import cache_get, cache_set
from app.config import cfg

logger = logging.getLogger(__name__)

OVERPASS_SERVERS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]

# ── Overpass query — comprehensive safety/relief infrastructure ────────────────

INFRA_QUERY = """
[out:json][timeout:30];
(
  /* ── Emergency & relief ── */
  node["amenity"="shelter"](around:{radius},{lat},{lon});
  node["amenity"="refugee_site"](around:{radius},{lat},{lon});
  node["amenity"="social_facility"](around:{radius},{lat},{lon});
  node["emergency"="assembly_point"](around:{radius},{lat},{lon});
  node["emergency"="evacuation_point"](around:{radius},{lat},{lon});
  node["emergency"="disaster_response"](around:{radius},{lat},{lon});

  /* ── Medical ── */
  node["amenity"="hospital"](around:{radius},{lat},{lon});
  way["amenity"="hospital"](around:{radius},{lat},{lon});
  node["amenity"="clinic"](around:{radius},{lat},{lon});
  node["amenity"="pharmacy"](around:{radius},{lat},{lon});
  node["amenity"="doctors"](around:{radius},{lat},{lon});
  node["amenity"="first_aid"](around:{radius},{lat},{lon});
  node["healthcare"](around:{radius},{lat},{lon});

  /* ── Water ── */
  node["amenity"="water_point"](around:{radius},{lat},{lon});
  node["man_made"="water_well"](around:{radius},{lat},{lon});
  node["amenity"="drinking_water"](around:{radius},{lat},{lon});
  node["natural"="spring"](around:{radius},{lat},{lon});
  node["man_made"="water_tower"](around:{radius},{lat},{lon});

  /* ── Food & supplies ── */
  node["amenity"="food_bank"](around:{radius},{lat},{lon});
  node["amenity"="community_centre"](around:{radius},{lat},{lon});
  node["shop"="supermarket"](around:{radius},{lat},{lon});
  node["amenity"="marketplace"](around:{radius},{lat},{lon});

  /* ── Safety & security ── */
  node["amenity"="police"](around:{radius},{lat},{lon});
  node["amenity"="fire_station"](around:{radius},{lat},{lon});
  node["emergency"="fire_hydrant"](around:{radius},{lat},{lon});

  /* ── Evacuation infrastructure ── */
  node["amenity"="school"](around:{radius},{lat},{lon});
  way["amenity"="school"](around:{radius},{lat},{lon});
  node["amenity"="college"](around:{radius},{lat},{lon});
  node["amenity"="university"](around:{radius},{lat},{lon});
  node["building"="civic"](around:{radius},{lat},{lon});
  node["amenity"="townhall"](around:{radius},{lat},{lon});

  /* ── Transport (evacuation routes) ── */
  node["highway"="bus_stop"](around:{radius},{lat},{lon});
  node["railway"="station"](around:{radius},{lat},{lon});
  node["aeroway"="aerodrome"](around:{radius},{lat},{lon});
  node["amenity"="fuel"](around:{radius},{lat},{lon});

  /* ── Power (critical infra) ── */
  node["power"="substation"](around:{radius},{lat},{lon});
  node["man_made"="tower"](around:{radius},{lat},{lon});

  /* ── Hazard indicators ── */
  node["landuse"="industrial"](around:{radius},{lat},{lon});
  way["landuse"="industrial"](around:{radius},{lat},{lon});
  node["landuse"="military"](around:{radius},{lat},{lon});
  way["flood_prone"="yes"](around:{radius},{lat},{lon});
  way["hazard"](around:{radius},{lat},{lon});
);
out center body;
"""

# ── Category definitions ──────────────────────────────────────────────────────

CATEGORY_MAP = {
    # (tag_key, tag_value) → category
    ("amenity", "hospital"):          "medical",
    ("amenity", "clinic"):            "medical",
    ("amenity", "doctors"):           "medical",
    ("amenity", "pharmacy"):          "medical",
    ("amenity", "first_aid"):         "medical",
    ("healthcare", None):             "medical",
    ("amenity", "shelter"):           "shelter",
    ("amenity", "refugee_site"):      "shelter",
    ("amenity", "social_facility"):   "shelter",
    ("emergency", "assembly_point"):  "shelter",
    ("emergency", "evacuation_point"):"shelter",
    ("emergency", "disaster_response"):"shelter",
    ("amenity", "water_point"):       "water",
    ("amenity", "drinking_water"):    "water",
    ("man_made", "water_well"):       "water",
    ("natural", "spring"):            "water",
    ("man_made", "water_tower"):      "water",
    ("amenity", "food_bank"):         "food",
    ("amenity", "community_centre"):  "food",
    ("shop", "supermarket"):          "food",
    ("amenity", "marketplace"):       "food",
    ("amenity", "police"):            "security",
    ("amenity", "fire_station"):      "security",
    ("emergency", "fire_hydrant"):    "security",
    ("amenity", "school"):            "evacuation",
    ("amenity", "college"):           "evacuation",
    ("amenity", "university"):        "evacuation",
    ("building", "civic"):            "evacuation",
    ("amenity", "townhall"):          "evacuation",
    ("highway", "bus_stop"):          "transport",
    ("railway", "station"):           "transport",
    ("aeroway", "aerodrome"):         "transport",
    ("amenity", "fuel"):              "transport",
    ("power", "substation"):          "power",
    ("man_made", "tower"):            "power",
    ("landuse", "industrial"):        "hazard",
    ("landuse", "military"):          "hazard",
    ("flood_prone", "yes"):           "hazard",
    ("hazard", None):                 "hazard",
}

CATEGORY_SAFETY_WEIGHT = {
    "medical":    +2.5,
    "shelter":    +2.0,
    "water":      +1.8,
    "food":       +1.2,
    "security":   +2.0,
    "evacuation": +1.5,
    "transport":  +1.0,
    "power":      -0.5,   # critical infra loss = risk
    "hazard":     -2.5,
}

CAMP_CATEGORIES = {"shelter", "medical", "evacuation"}


# ── Public API ────────────────────────────────────────────────────────────────

async def pull_osm_camps(lat: float, lon: float, radius_m: int = 20000) -> List[Camp]:
    """Pull shelter/medical/evacuation facilities as Camp objects."""
    profile = await pull_osm_infra_profile(lat, lon, radius_m=radius_m)
    camps: List[Camp] = []
    for cat, items in profile["by_category"].items():
        if cat not in CAMP_CATEGORIES:
            continue
        for item in items:
            camps.append(_item_to_camp(item, cat))
    return camps


async def pull_osm_infra_profile(
    lat: float,
    lon: float,
    radius_m: int = 5000,
) -> Dict[str, Any]:
    """
    Full infrastructure profile around a point.
    Returns categorised elements, safety score, and named lists.
    Used by agent tools for rich context.
    """
    ttl = cfg("ttl.osm_sec", 1800)
    key = f"osm:infra:{lat:.4f}:{lon:.4f}:{radius_m}"
    cached = cache_get(key)
    if cached:
        return cached

    query = INFRA_QUERY.format(lat=lat, lon=lon, radius=radius_m)
    elements = await _overpass_query(query)

    # Categorise
    by_category: Dict[str, List[Dict]] = {cat: [] for cat in CATEGORY_SAFETY_WEIGHT}
    for el in elements:
        cat = _categorise(el.get("tags", {}))
        if cat:
            lat_e, lon_e = _get_latlon(el)
            dist = _haversine_km(lat, lon, lat_e, lon_e) if (lat_e and lon_e) else None
            by_category[cat].append({
                "osm_id":   el.get("id"),
                "name":     _name(el.get("tags", {})),
                "type":     cat,
                "lat":      lat_e,
                "lon":      lon_e,
                "distance_km": round(dist, 3) if dist else None,
                "tags":     el.get("tags", {}),
                "confidence": _confidence(el.get("tags", {})),
            })

    # Sort each category by distance
    for cat in by_category:
        by_category[cat].sort(key=lambda x: x["distance_km"] or 99)

    # Compute composite safety score (Ignisia-style)
    score = _compute_safety_score(lat, lon, by_category, radius_m / 1000)

    profile = {
        "center": {"lat": lat, "lon": lon},
        "radius_m": radius_m,
        "element_count": len(elements),
        "safety_score": score,
        "by_category": by_category,
        "category_counts": {cat: len(items) for cat, items in by_category.items()},
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    cache_set(key, profile, ttl)
    return profile


# ── Internal helpers ──────────────────────────────────────────────────────────

async def _overpass_query(query: str) -> List[Dict[str, Any]]:
    last_err = None
    async with httpx.AsyncClient(
        timeout=15.0,  # short per-server timeout so fallback happens fast
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    ) as client:
        for url in OVERPASS_SERVERS:
            try:
                resp = await client.post(url, data={"data": query})
                resp.raise_for_status()
                return resp.json().get("elements", [])
            except Exception as exc:
                logger.warning("Overpass failed url=%s: %s", url, exc)
                last_err = exc
    raise RuntimeError(f"All Overpass servers unavailable: {last_err}")


def _categorise(tags: Dict) -> Optional[str]:
    for (key, val), cat in CATEGORY_MAP.items():
        tag_val = tags.get(key)
        if tag_val is None:
            continue
        if val is None or tag_val == val:
            return cat
    return None


def _name(tags: Dict) -> str:
    return (tags.get("name") or tags.get("amenity") or tags.get("emergency") or
            tags.get("healthcare") or tags.get("shop") or tags.get("landuse") or "unnamed")


def _get_latlon(el: Dict) -> Tuple[Optional[float], Optional[float]]:
    if "lat" in el and "lon" in el:
        return float(el["lat"]), float(el["lon"])
    center = el.get("center", {})
    if center:
        return float(center.get("lat", 0) or 0), float(center.get("lon", 0) or 0)
    return None, None


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat, dlon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _confidence(tags: Dict) -> str:
    if tags.get("name") and (tags.get("amenity") or tags.get("emergency")):
        return "confirmed"
    if tags.get("amenity") or tags.get("emergency"):
        return "reported"
    return "suspected"


def _compute_safety_score(
    lat: float,
    lon: float,
    by_category: Dict[str, List[Dict]],
    radius_km: float,
) -> Dict[str, Any]:
    """
    Compute a composite safety score from OSM infrastructure presence.
    Positive categories (medical, shelter, security) add to score.
    Negative categories (hazard, industrial) subtract.
    Distance-weighted: closer = more influence.
    """
    contributions: Dict[str, float] = {}
    for cat, weight in CATEGORY_SAFETY_WEIGHT.items():
        items = by_category.get(cat, [])
        cat_score = 0.0
        for item in items:
            dist = item.get("distance_km") or radius_km
            proximity = max(0.0, 1.0 - dist / radius_km)
            cat_score += weight * proximity
        contributions[cat] = round(cat_score, 3)

    raw = sum(contributions.values())
    # Sigmoid-style normalise to [0, 1]
    normalised = 1 / (1 + math.exp(-raw / 5))

    return {
        "raw": round(raw, 3),
        "normalised": round(normalised, 3),
        "contributions": contributions,
    }


def _item_to_camp(item: Dict, category: str) -> Camp:
    uid = hashlib.md5(
        f"osm:{item.get('osm_id', item['name'])}:{item.get('lat')}:{item.get('lon')}".encode()
    ).hexdigest()[:16]
    camp_type = {
        "medical": "hospital" if "hospital" in item["name"].lower() else "clinic",
        "shelter": "shelter",
        "evacuation": "evacuation_center",
    }.get(category, "shelter")
    return Camp(
        id=f"osm:{uid}",
        name=item["name"],
        type=camp_type,
        source="osm",
        lat=item["lat"] or 0.0,
        lon=item["lon"] or 0.0,
        status="open",
        confidence=item.get("confidence", "reported"),
        last_updated=item.get("fetched_at"),
    )
