"""Pure-Python spatial helpers — no PostGIS dependency."""
import math
from typing import List, Tuple, TypeVar

T = TypeVar("T")


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def bbox_from_point(lat: float, lon: float, radius_km: float) -> Tuple[float, float, float, float]:
    """Return (min_lat, max_lat, min_lon, max_lon) bounding box."""
    deg_lat = radius_km / 111.0
    deg_lon = radius_km / (111.0 * math.cos(math.radians(lat)))
    return lat - deg_lat, lat + deg_lat, lon - deg_lon, lon + deg_lon


def nearest_k(
    items: List[T],
    lat_fn,
    lon_fn,
    center_lat: float,
    center_lon: float,
    radius_km: float,
    k: int = 20,
) -> List[Tuple[T, float]]:
    """Return up to k items within radius_km, sorted by distance."""
    results = []
    for item in items:
        ilat, ilon = lat_fn(item), lon_fn(item)
        if ilat is None or ilon is None:
            continue
        d = haversine_km(center_lat, center_lon, ilat, ilon)
        if d <= radius_km:
            results.append((item, d))
    results.sort(key=lambda x: x[1])
    return results[:k]
