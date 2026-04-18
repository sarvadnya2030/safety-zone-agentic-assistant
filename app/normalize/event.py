"""Normalise raw puller output and persist to SQLite."""
import logging
from typing import List

from app.schemas import Event, Camp
from app.store.db import upsert_events, upsert_camps

logger = logging.getLogger(__name__)


def ingest_events(events: List[Event]) -> int:
    if not events:
        return 0
    n = upsert_events(events)
    logger.info("ingested %d events", n)
    return n


def ingest_camps(camps: List[Camp]) -> int:
    if not camps:
        return 0
    n = upsert_camps(camps)
    logger.info("ingested %d camps", n)
    return n
