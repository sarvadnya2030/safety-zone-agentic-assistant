"""Agent loop smoke test with mocked NIM responses."""
import json
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_agent_loop_no_tools():
    """Agent returns direct answer when NIM makes no tool calls."""
    from app.agent.loop import run

    mock_response = {
        "role": "assistant",
        "content": "Currently no major alerts. [SACHET/NDMA, 2024-04-18T06:00:00Z]",
        "tool_calls": [],
    }
    with patch("app.agent.loop.chat", new=AsyncMock(return_value=mock_response)):
        result = await run("What are current alerts in Maharashtra?", state="Maharashtra")

    assert "alert" in result["answer"].lower()
    assert result["tool_calls_made"] == 0


@pytest.mark.asyncio
async def test_agent_loop_with_tool_call():
    """Agent dispatches a tool call and includes result in final answer."""
    from app.agent.loop import run

    tool_response = {
        "role": "assistant",
        "content": "",
        "tool_calls": [{
            "id": "call_001",
            "function": {
                "name": "fetch_live_alerts",
                "arguments": json.dumps({"state": "Maharashtra", "since_hours": 24}),
            },
        }],
    }
    final_response = {
        "role": "assistant",
        "content": "Maharashtra has 2 active flood alerts. [SACHET/NDMA, 2024-04-18T06:00:00Z]",
        "tool_calls": [],
    }

    mock_tool_result = [
        {"id": "sachet:abc", "source": "SACHET/NDMA", "hazard_type": "flood",
         "severity": "critical", "ts_start": "2024-04-18T06:00:00Z",
         "state": "Maharashtra", "district": "Raigad",
         "summary": "Extremely heavy rainfall in Raigad", "confidence": 0.95}
    ]

    with patch("app.agent.loop.chat", new=AsyncMock(side_effect=[tool_response, final_response])):
        with patch("app.agent.tools._fetch_live_alerts", new=AsyncMock(return_value=mock_tool_result)):
            result = await run("What are current alerts in Maharashtra?", state="Maharashtra")

    assert result["tool_calls_made"] == 1
    assert "Maharashtra" in result["answer"]


def test_scoring_deterministic():
    """Risk score computation is deterministic — same input produces same output."""
    import sqlite3
    from unittest.mock import patch
    with patch("app.insights.scoring.query_events", return_value=[]):
        with patch("app.insights.scoring._get_flood_prior", return_value=0.4):
            with patch("app.insights.scoring._get_landslide_prior", return_value=0.1):
                from app.insights.scoring import compute_district_risk
                r1 = compute_district_risk("TestDistrict")
                r2 = compute_district_risk("TestDistrict")
    assert r1["score"] == r2["score"]
    assert r1["label"] in ("Safe", "Moderate", "Unsafe")
