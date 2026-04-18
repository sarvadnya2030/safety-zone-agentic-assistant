"""Generate natural-language district insight via NIM (explains precomputed scores)."""
import logging
from typing import Dict, Any

from app.agent.nim_client import chat

logger = logging.getLogger(__name__)


async def generate_district_summary(risk_data: Dict[str, Any]) -> str:
    """Use NIM to explain a precomputed risk dict in plain language."""
    district = risk_data.get("district", "the district")
    score = risk_data.get("score", 0)
    label = risk_data.get("label", "Unknown")
    components = risk_data.get("components", {})
    top_events = risk_data.get("top_events", [])

    events_text = "\n".join(
        f"- [{e['severity'].upper()}] {e['hazard_type']}: {e['summary']} ({e['source']}, {e['ts_start']})"
        for e in top_events
    ) or "No recent events found."

    prompt = f"""You are given precomputed safety data for {district}.
DO NOT invent or modify any numbers. Only explain what is shown below.

Risk score: {score} → {label}
Score components:
  - Event-based hazard contribution (weight {components.get('event_weight',0.4):.0%}): {components.get('event_score',0):.3f}
  - Flood inventory prior (weight {components.get('flood_weight',0.3):.0%}): {components.get('flood_prior',0):.3f}
  - Landslide atlas prior (weight {components.get('landslide_weight',0.3):.0%}): {components.get('landslide_prior',0):.3f}

Recent contributing events:
{events_text}

Write 2-3 sentences explaining why {district} is currently {label}.
Cite each event as [source, timestamp]. Do not guess — if data is sparse, say so."""

    messages = [{"role": "user", "content": prompt}]
    try:
        resp = await chat(messages, temperature=0.1, max_tokens=400)
        return resp["content"]
    except Exception as exc:
        logger.error("NIM summary failed: %s", exc)
        return f"{district} is currently rated {label} (score {score:.2f}). NIM explanation unavailable."
