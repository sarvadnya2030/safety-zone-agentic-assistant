"""NVIDIA NIM async chat client — supports nemotron thinking/reasoning models."""
import logging
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI

from app.config import get_settings

logger = logging.getLogger(__name__)
_client: Optional[AsyncOpenAI] = None

# Models that support reasoning_budget + enable_thinking
THINKING_MODELS = {
    "nvidia/nemotron-3-nano-30b-a3b",
    "nvidia/nemotron-4-340b-instruct",
}


def get_nim_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        s = get_settings()
        _client = AsyncOpenAI(
            api_key=s.nvidia_api_key,
            base_url=s.nim_base_url,
        )
    return _client


async def chat(
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict]] = None,
    temperature: float = 0.1,
    max_tokens: int = 2048,
) -> Dict[str, Any]:
    """
    Single chat completion (non-streaming).
    Automatically enables thinking for nemotron reasoning models.
    Returns {role, content, reasoning_content, tool_calls}.
    """
    client = get_nim_client()
    s = get_settings()

    kwargs: Dict[str, Any] = dict(
        model=s.nim_model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    if s.nim_model in THINKING_MODELS:
        if tools:
            # Disable thinking for tool-calling turns — mixing thinking + function calling
            # causes the model to output reasoning as content instead of clean answers
            kwargs["extra_body"] = {
                "reasoning_budget": 0,
                "chat_template_kwargs": {"enable_thinking": False},
            }
        else:
            # Enable thinking for pure synthesis/answer turns
            kwargs["extra_body"] = {
                "reasoning_budget": s.nim_reasoning_budget,
                "chat_template_kwargs": {"enable_thinking": True},
            }

    response = await client.chat.completions.create(**kwargs)
    msg = response.choices[0].message

    # Extract reasoning_content if present (nemotron thinking)
    reasoning = getattr(msg, "reasoning_content", None)
    if reasoning:
        logger.debug("NIM reasoning (%d chars): %s...", len(reasoning), reasoning[:120])

    return {
        "role": msg.role,
        "content": msg.content or "",
        "reasoning_content": reasoning or "",
        "tool_calls": [
            {
                "id": tc.id,
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in (msg.tool_calls or [])
        ],
    }


async def chat_stream(
    messages: List[Dict[str, Any]],
    temperature: float = 0.1,
    max_tokens: int = 4096,
):
    """
    Streaming chat — yields (type, text) tuples.
    type is 'thinking' for reasoning_content chunks, 'content' for answer chunks.
    """
    client = get_nim_client()
    s = get_settings()

    kwargs: Dict[str, Any] = dict(
        model=s.nim_model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
    )

    if s.nim_model in THINKING_MODELS:
        kwargs["extra_body"] = {
            "reasoning_budget": s.nim_reasoning_budget,
            "chat_template_kwargs": {"enable_thinking": True},
        }

    async for chunk in await client.chat.completions.create(**kwargs):
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        reasoning = getattr(delta, "reasoning_content", None)
        if reasoning:
            yield ("thinking", reasoning)
        if delta.content:
            yield ("content", delta.content)
