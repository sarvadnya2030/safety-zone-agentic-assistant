"""ReAct-style agentic loop with NIM tool calling."""
import json
import logging
from typing import Any, Dict, List, Optional

from app.agent.nim_client import chat
from app.agent.tools import TOOL_SPECS, dispatch
from app.agent.prompts import build_messages
from app.config import cfg

logger = logging.getLogger(__name__)


async def run(
    query: str,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    district: Optional[str] = None,
    state: Optional[str] = None,
    max_tool_calls: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Run the agent loop for a user query.
    Returns {answer, tool_calls_made, raw_tool_results}.
    """
    max_calls = max_tool_calls or cfg("agent.max_tool_calls", 5)
    temperature = cfg("agent.temperature", 0.1)

    messages = build_messages(query, lat, lon, district, state)
    tool_calls_made = 0
    raw_tool_results: List[Dict] = []

    for _ in range(max_calls):
        response = await chat(messages, tools=TOOL_SPECS, temperature=temperature)
        # Include reasoning in assistant message if present (nemotron)
        asst_msg: Dict[str, Any] = {"role": "assistant", "content": response["content"]}
        if response.get("reasoning_content"):
            asst_msg["reasoning_content"] = response["reasoning_content"]
        if response["tool_calls"]:
            # NIM requires type="function" on each tool call
            asst_msg["tool_calls"] = [
                {**tc, "type": "function"} for tc in response["tool_calls"]
            ]
        messages.append(asst_msg)

        if not response["tool_calls"]:
            # Final answer — if content empty but reasoning present, use reasoning as answer
            if not response["content"] and response.get("reasoning_content"):
                response["content"] = response["reasoning_content"]
            break

        # Dispatch all tool calls in this turn
        for tc in response["tool_calls"]:
            fn = tc["function"]
            tool_calls_made += 1
            logger.info("tool call: %s(%s)", fn["name"], fn["arguments"][:120])
            try:
                result = await dispatch(fn["name"], fn["arguments"])
            except Exception as exc:
                logger.error("tool %s failed: %s", fn["name"], exc)
                result = {"error": str(exc)}
            raw_tool_results.append({"tool": fn["name"], "result": result})
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": json.dumps(result, default=str),
            })

    # If content still empty (thinking model quirk), force a plain synthesis call
    answer = response["content"] or ""
    if not answer and tool_calls_made > 0:
        messages.append({
            "role": "user",
            "content": "Based on the tool results above, please provide a clear, grounded answer with [source, timestamp] citations for every factual claim.",
        })
        follow_up = await chat(messages, temperature=temperature)  # no tools → thinking enabled for synthesis
        answer = follow_up["content"] or follow_up.get("reasoning_content", "No answer generated.")
        response["reasoning_content"] = follow_up.get("reasoning_content", "")
    elif answer and "[" not in answer and tool_calls_made > 0:
        messages.append({
            "role": "user",
            "content": "Please add [source, timestamp] citations for every factual claim in your answer, or remove unsupported claims.",
        })
        follow_up = await chat(messages, temperature=temperature)
        if follow_up["content"]:
            answer = follow_up["content"]

    return {
        "answer": answer,
        "reasoning_content": response.get("reasoning_content", ""),
        "tool_calls_made": tool_calls_made,
        "raw_tool_results": raw_tool_results,
    }
