"""
Deterministic district risk scoring.
LLM never produces a score — it only explains these precomputed values.
"""
import json
import math
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from app.config import cfg
from app.store.db import query_events

logger = logging.getLogger(__name__)

SEVERITY_WEIGHT = {"low": 0.1, "moderate": 0.3, "high": 0.6, "critical": 1.0}

# Geo priors loaded lazily from GeoJSON files
_flood_priors: Optional[Dict[str, float]] = None
_landslide_priors: Optional[Dict[str, float]] = None


def compute_district_risk(district: str, state: Optional[str] = None) -> Dict[str, Any]:
    events = query_events(district=district, state=state, limit=100)

    decay_hours = cfg("scoring.time_decay_hours", 24)
    flood_w = cfg("scoring.flood_prior_weight", 0.3)
    landslide_w = cfg("scoring.landslide_prior_weight", 0.3)

    # Event-based hazard score with time decay
    event_score = 0.0
    now = datetime.now(timezone.utc)
    for ev in events:
        w = SEVERITY_WEIGHT.get(ev.severity, 0.1)
        age_h = _event_age_hours(ev.ts_start, now)
        decay = math.exp(-age_h / decay_hours)
        event_score += w * decay

    # Normalise event score to [0, 1) range
    event_score_norm = 1 - math.exp(-event_score)

    flood_prior = _get_flood_prior(district)
    landslide_prior = _get_landslide_prior(district)

    # Weighted combination (1 - flood_w - landslide_w is the event weight)
    event_weight = 1.0 - flood_w - landslide_w
    final_score = (
        event_weight * event_score_norm
        + flood_w * flood_prior
        + landslide_w * landslide_prior
    )
    final_score = min(max(final_score, 0.0), 1.0)

    safe_t = cfg("scoring.safe_threshold", 0.3)
    unsafe_t = cfg("scoring.unsafe_threshold", 0.7)
    if final_score < safe_t:
        label = "Safe"
    elif final_score < unsafe_t:
        label = "Moderate"
    else:
        label = "Unsafe"

    return {
        "district": district,
        "state": state,
        "score": round(final_score, 4),
        "label": label,
        "components": {
            "event_score": round(event_score_norm, 4),
            "flood_prior": round(flood_prior, 4),
            "landslide_prior": round(landslide_prior, 4),
            "event_weight": event_weight,
            "flood_weight": flood_w,
            "landslide_weight": landslide_w,
        },
        "active_events": len(events),
        "top_events": [
            {"hazard_type": e.hazard_type, "severity": e.severity,
             "ts_start": e.ts_start, "source": e.source, "summary": e.summary[:120]}
            for e in events[:5]
        ],
    }


def _event_age_hours(ts_start: str, now: datetime) -> float:
    try:
        ts = datetime.fromisoformat(ts_start)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return max((now - ts).total_seconds() / 3600, 0)
    except Exception:
        return 0.0


def _get_flood_prior(district: str) -> float:
    global _flood_priors
    if _flood_priors is None:
        _flood_priors = _load_geo_priors("flood_inventory.geojson")
    return _flood_priors.get(district.lower(), 0.1)


def _get_landslide_prior(district: str) -> float:
    global _landslide_priors
    if _landslide_priors is None:
        _landslide_priors = _load_geo_priors("landslide_atlas.geojson")
    return _landslide_priors.get(district.lower(), 0.05)


def _load_geo_priors(filename: str) -> Dict[str, float]:
    geo_dir = Path(cfg("data.geo_dir", "data/geo"))
    path = geo_dir / filename
    if not path.exists():
        logger.warning("Geo prior file not found: %s — using default 0.1", path)
        return {}
    try:
        with open(path) as f:
            data = json.load(f)
        priors: Dict[str, float] = {}
        for feature in data.get("features", []):
            props = feature.get("properties", {})
            name = props.get("district", props.get("name", ""))
            risk = float(props.get("risk_score", props.get("frequency", 0.1)))
            if name:
                priors[name.lower()] = min(max(risk, 0.0), 1.0)
        return priors
    except Exception as exc:
        logger.error("Failed to load geo priors %s: %s", filename, exc)
        return {}
