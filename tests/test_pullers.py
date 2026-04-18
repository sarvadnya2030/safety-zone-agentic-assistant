"""Tests for puller parsers against frozen fixtures."""
import json
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def test_sachet_parser():
    import feedparser
    from app.pullers.sachet import _parse_feed
    xml = (FIXTURES / "sachet_rss.xml").read_text()
    feed = feedparser.parse(xml)
    events = _parse_feed(feed)
    assert len(events) == 2
    assert any(e.hazard_type == "flood" for e in events)
    assert any(e.severity == "critical" for e in events)
    assert all(e.source == "SACHET/NDMA" for e in events)


def test_ncs_usgs_parser():
    from app.pullers.ncs import _parse_usgs
    data = json.loads((FIXTURES / "ncs_quakes.json").read_text())
    events = _parse_usgs(data)
    assert len(events) == 2
    assert all(e.hazard_type == "earthquake" for e in events)
    mags = [e.summary for e in events]
    assert any("4.2" in s for s in mags)


def test_severity_classifier():
    from app.pullers.sachet import _extract_severity
    assert _extract_severity("Red Alert extremely heavy rainfall") == "critical"
    assert _extract_severity("Orange Alert heavy rain warning") == "high"
    assert _extract_severity("Yellow Alert watch") == "moderate"
    assert _extract_severity("normal conditions") == "low"


def test_hazard_classifier():
    from app.pullers.sachet import _extract_hazard
    assert _extract_hazard("flood warning inundation") == "flood"
    assert _extract_hazard("cyclone landfall expected") == "cyclone"
    assert _extract_hazard("earthquake tremor felt") == "earthquake"
    assert _extract_hazard("landslide mudslide risk") == "landslide"
