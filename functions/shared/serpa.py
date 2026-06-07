"""SerpApi Google News client for fetching team news."""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_SERPAPI_URL = "https://serpapi.com/search.json"


async def search_team_news(
    team_name: str,
    api_key: str,
    max_results: int | None = None,
) -> list[str]:
    """Return up to `max_results` news headlines for `team_name` at the World Cup.

    Returns an empty list on any network or parse error so callers never crash.
    """
    if max_results is None:
        max_results = int(os.environ.get("SERPA_MAX_RESULTS", "3"))
    query = f"{team_name} FIFA World Cup 2026 injury form squad"
    params: dict[str, str | int] = {
        "engine": "google_news",
        "q": query,
        "api_key": api_key,
        "num": max_results,
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(_SERPAPI_URL, params=params)
            if response.status_code in (401, 403):
                logger.error(
                    "SerpApi key invalid or unauthorized (HTTP %s) for %r",
                    response.status_code, team_name,
                )
                return []
            if response.status_code == 429:
                logger.warning("SerpApi rate limit exceeded (HTTP 429) for %r", team_name)
                return []
            response.raise_for_status()
            data: dict[str, Any] = response.json()
    except httpx.TimeoutException as exc:
        logger.warning("SerpApi news search timed out for %r: %s", team_name, exc)
        return []
    except httpx.HTTPError as exc:
        logger.warning("SerpApi news search failed for %r: %s", team_name, exc)
        return []

    snippets: list[str] = []
    for item in data.get("news_results", [])[:max_results]:
        title = item.get("title", "")
        snippet = item.get("snippet", "")
        text = snippet or title
        if text:
            snippets.append(text.strip())
    return snippets
