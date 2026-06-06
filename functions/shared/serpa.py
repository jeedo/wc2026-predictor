"""Serper.dev news search client for fetching team news."""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_SERPER_URL = "https://google.serper.dev/news"


async def search_team_news(
    team_name: str,
    api_key: str,
    max_results: int | None = None,
) -> list[str]:
    """Return up to `max_results` news snippets for `team_name` at the World Cup.

    Returns an empty list on any network or parse error so callers never crash.
    """
    if max_results is None:
        max_results = int(os.environ.get("SERPA_MAX_RESULTS", "3"))
    query = f"{team_name} FIFA World Cup 2026 injury form squad"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                _SERPER_URL,
                headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
                json={"q": query, "num": max_results},
            )
            if response.status_code in (401, 403):
                logger.error(
                    "Serper API key invalid or unauthorized (HTTP %s) for %r",
                    response.status_code, team_name,
                )
                return []
            if response.status_code == 429:
                logger.warning("Serper rate limit exceeded (HTTP 429) for %r", team_name)
                return []
            response.raise_for_status()
            data: dict[str, Any] = response.json()
    except httpx.TimeoutException as exc:
        logger.warning("Serper news search timed out for %r: %s", team_name, exc)
        return []
    except httpx.HTTPError as exc:
        logger.warning("Serpa news search failed for %r: %s", team_name, exc)
        return []

    snippets: list[str] = []
    for item in data.get("news", [])[:max_results]:
        title = item.get("title", "")
        snippet = item.get("snippet", "")
        if title or snippet:
            snippets.append(f"{title}: {snippet}".strip(": "))
    return snippets
