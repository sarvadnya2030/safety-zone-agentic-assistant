import sqlite3
import json
import logging
from pathlib import Path
from typing import List, Optional
from app.schemas import Event, Camp

logger = logging.getLogger(__name__)
_conn: Optional[sqlite3.Connection] = None


def get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        raise RuntimeError("DB not initialised — call init_db() first")
    return _conn


def init_db(db_path: str) -> None:
    global _conn
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    _conn = sqlite3.connect(db_path, check_same_thread=False)
    _conn.row_factory = sqlite3.Row
    _apply_schema(_conn)
    logger.info("SQLite DB ready at %s", db_path)


def _apply_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS events (
            id          TEXT PRIMARY KEY,
            source      TEXT,
            source_type TEXT,
            hazard_type TEXT,
            severity    TEXT,
            ts_start    TEXT,
            ts_end      TEXT,
            state       TEXT,
            district    TEXT,
            lat         REAL,
            lon         REAL,
            polygon_wkt TEXT,
            summary     TEXT,
            raw_text    TEXT,
            confidence  REAL DEFAULT 1.0
        );
        CREATE INDEX IF NOT EXISTS idx_events_district ON events(district);
        CREATE INDEX IF NOT EXISTS idx_events_ts       ON events(ts_start);
        CREATE INDEX IF NOT EXISTS idx_events_latlon   ON events(lat, lon);
        CREATE INDEX IF NOT EXISTS idx_events_hazard   ON events(hazard_type);

        CREATE TABLE IF NOT EXISTS camps (
            id           TEXT PRIMARY KEY,
            name         TEXT,
            type         TEXT,
            source       TEXT,
            lat          REAL NOT NULL,
            lon          REAL NOT NULL,
            capacity     INTEGER,
            status       TEXT DEFAULT 'unknown',
            confidence   TEXT DEFAULT 'confirmed',
            last_updated TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_camps_latlon ON camps(lat, lon);

        CREATE TABLE IF NOT EXISTS cache (
            key        TEXT PRIMARY KEY,
            value      TEXT,
            fetched_at TEXT,
            ttl_sec    INTEGER
        );
    """)
    conn.commit()


def upsert_events(events: List[Event]) -> int:
    conn = get_conn()
    sql = """
        INSERT OR REPLACE INTO events
          (id, source, source_type, hazard_type, severity, ts_start, ts_end,
           state, district, lat, lon, polygon_wkt, summary, raw_text, confidence)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """
    rows = [
        (e.id, e.source, e.source_type, e.hazard_type, e.severity,
         e.ts_start, e.ts_end, e.state, e.district, e.lat, e.lon,
         e.polygon_wkt, e.summary, e.raw_text, e.confidence)
        for e in events
    ]
    conn.executemany(sql, rows)
    conn.commit()
    return len(rows)


def upsert_camps(camps: List[Camp]) -> int:
    conn = get_conn()
    sql = """
        INSERT OR REPLACE INTO camps
          (id, name, type, source, lat, lon, capacity, status, confidence, last_updated)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """
    rows = [
        (c.id, c.name, c.type, c.source, c.lat, c.lon,
         c.capacity, c.status, c.confidence, c.last_updated)
        for c in camps
    ]
    conn.executemany(sql, rows)
    conn.commit()
    return len(rows)


def query_events(
    district: Optional[str] = None,
    state: Optional[str] = None,
    since: Optional[str] = None,
    hazard_type: Optional[str] = None,
    limit: int = 50,
) -> List[Event]:
    conn = get_conn()
    clauses, params = [], []
    if district:
        clauses.append("LOWER(district) = LOWER(?)")
        params.append(district)
    if state:
        clauses.append("LOWER(state) = LOWER(?)")
        params.append(state)
    if since:
        clauses.append("ts_start >= ?")
        params.append(since)
    if hazard_type:
        clauses.append("LOWER(hazard_type) = LOWER(?)")
        params.append(hazard_type)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"SELECT * FROM events {where} ORDER BY ts_start DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    return [_row_to_event(r) for r in rows]


def query_camps_in_bbox(
    min_lat: float, max_lat: float, min_lon: float, max_lon: float, limit: int = 100
) -> List[Camp]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM camps WHERE lat BETWEEN ? AND ? AND lon BETWEEN ? AND ? LIMIT ?",
        (min_lat, max_lat, min_lon, max_lon, limit),
    ).fetchall()
    return [_row_to_camp(r) for r in rows]


def _row_to_event(r: sqlite3.Row) -> Event:
    d = dict(r)
    return Event(**{k: v for k, v in d.items() if v is not None or k in ("id", "source", "source_type", "hazard_type", "severity", "ts_start", "summary")})


def _row_to_camp(r: sqlite3.Row) -> Camp:
    d = dict(r)
    return Camp(**{k: v for k, v in d.items() if v is not None or k in ("id", "name", "type", "source", "lat", "lon")})
