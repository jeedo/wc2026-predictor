"""Serper.dev Google News client for fetching team news."""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_SERPER_URL = "https://google.serper.dev/news"
_MAX_RETRIES = 3


async def search_team_news(
    team_name: str,
    api_key: str,
    max_results: int | None = None,
) -> list[str]:
    """Return up to `max_results` news headlines for `team_name` at the World Cup.

    Retries on 429 using the x-ratelimit-reset header (Unix timestamp) to know
    exactly how long to wait before the window resets. Falls back to exponential
    backoff if the header is absent. Returns an empty list on auth errors or
    after exhausting retries so callers never crash.
    """
    if max_results is None:
        max_results = int(os.environ.get("SERPA_MAX_RESULTS", "3"))
    query = f"{team_name} FIFA World Cup 2026 injury form squad"
    headers = {
        "X-API-KEY": api_key,
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "q": query,
        "num": max_results,
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                response = await client.post(_SERPER_URL, headers=headers, json=payload)
            except httpx.TimeoutException as exc:
                logger.warning("Serper.dev timed out for %r (attempt %d): %s", team_name, attempt, exc)
                return []
            except httpx.HTTPError as exc:
                logger.warning("Serper.dev request failed for %r (attempt %d): %s", team_name, attempt, exc)
                return []

            if response.status_code in (401, 403):
                logger.error(
                    "Serper.dev key invalid or unauthorized (HTTP %s) for %r",
                    response.status_code, team_name,
                )
                return []

            if response.status_code == 429:
                reset_header = response.headers.get("x-ratelimit-reset")
                if reset_header:
                    wait = max(0.0, float(reset_header) - time.time()) + 0.5
                else:
                    wait = 2.0 ** attempt  # fallback exponential backoff
                logger.warning(
                    "Serper.dev rate limit (429) for %r — waiting %.1fs before retry %d/%d",
                    team_name, wait, attempt, _MAX_RETRIES,
                )
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(wait)
                    continue
                return []

            try:
                response.raise_for_status()
                data: dict[str, Any] = response.json()
            except Exception as exc:
                logger.warning("Serper.dev bad response for %r: %s", team_name, exc)
                return []

            snippets: list[str] = []
            for item in data.get("news", [])[:max_results]:
                title = item.get("title", "")
                snippet = item.get("snippet", "")
                text = snippet or title
                if text:
                    snippets.append(text.strip())
            logger.info("Serper.dev returned %d snippet(s) for %r", len(snippets), team_name)
            return snippets

    return []
