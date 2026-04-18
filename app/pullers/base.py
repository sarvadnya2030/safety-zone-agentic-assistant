"""Async HTTP client with primary/fallback URL pattern (adapted from Ignisia)."""
import logging
from typing import Any, Dict, List, Optional, Tuple
import httpx

logger = logging.getLogger(__name__)
DEFAULT_TIMEOUT = 20.0
USER_AGENT = "CivilianSafetyMonitor/1.0"


async def fetch_json(
    urls: List[str],
    *,
    params: Optional[Dict] = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> Any:
    last_err: Optional[Exception] = None
    async with httpx.AsyncClient(
        timeout=timeout, headers={"User-Agent": USER_AGENT}, follow_redirects=True
    ) as client:
        for url in dict.fromkeys(urls):
            try:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                return resp.json()
            except Exception as exc:
                logger.warning("fetch_json failed url=%s err=%s", url, exc)
                last_err = exc
    raise RuntimeError(f"All URLs failed. Last error: {last_err}")


async def fetch_text(
    urls: List[str],
    *,
    params: Optional[Dict] = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> str:
    last_err: Optional[Exception] = None
    async with httpx.AsyncClient(
        timeout=timeout, headers={"User-Agent": USER_AGENT}, follow_redirects=True
    ) as client:
        for url in dict.fromkeys(urls):
            try:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                return resp.text
            except Exception as exc:
                logger.warning("fetch_text failed url=%s err=%s", url, exc)
                last_err = exc
    raise RuntimeError(f"All URLs failed. Last error: {last_err}")
