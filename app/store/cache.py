"""On-disk TTL cache using SQLite cache table."""
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from app.store.db import get_conn

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _seconds_since(iso_ts: str) -> float:
    try:
        ts = datetime.fromisoformat(iso_ts)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - ts).total_seconds()
    except Exception:
        return float("inf")


def cache_get(key: str) -> Optional[Any]:
    conn = get_conn()
    row = conn.execute(
        "SELECT value, fetched_at, ttl_sec FROM cache WHERE key = ?", (key,)
    ).fetchone()
    if row is None:
        return None
    age = _seconds_since(row["fetched_at"])
    if age > row["ttl_sec"]:
        logger.debug("cache miss (expired) key=%s age=%.0fs", key, age)
        return None
    return json.loads(row["value"])


def cache_set(key: str, value: Any, ttl_sec: int) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO cache (key, value, fetched_at, ttl_sec) VALUES (?,?,?,?)",
        (key, json.dumps(value, default=str), _now_iso(), ttl_sec),
    )
    conn.commit()
