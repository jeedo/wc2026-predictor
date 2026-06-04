"""HTTP client for football-data.org v4 API."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.football-data.org/v4"
_COMPETITION_CODE = "WC"
_COMPETITION_ID = "2000"


@dataclass
class FootballDataClient:
    api_key: str

    @property
    def headers(self) -> dict[str, str]:
        return {"X-Auth-Token": self.api_key}

    @classmethod
    def from_env(cls) -> "FootballDataClient":
        return cls(api_key=os.environ["FOOTBALL_DATA_API_KEY"])


async def fetch_teams_fd(
    client: FootballDataClient, http: httpx.AsyncClient
) -> list[dict[str, Any]]:
    """Fetch all 48 WC2026 teams from football-data.org."""
    url = f"{_BASE_URL}/competitions/{_COMPETITION_ID}/teams"
    logger.info("Fetching teams from: %s", url)
    resp = await http.get(url, headers=client.headers)
    resp.raise_for_status()
    teams = resp.json().get("teams", [])
    logger.info("Fetched %d teams from Football Data API", len(teams))
    return teams


async def fetch_standings_fd(
    client: FootballDataClient, http: httpx.AsyncClient
) -> list[dict[str, Any]]:
    """Fetch group standings from football-data.org."""
    url = f"{_BASE_URL}/competitions/{_COMPETITION_ID}/standings"
    logger.info("Fetching standings from: %s", url)
    resp = await http.get(url, headers=client.headers)
    resp.raise_for_status()
    flat: list[dict[str, Any]] = []
    for stage in resp.json().get("standings", []):
        if stage.get("type") == "GROUP":
            flat.extend(stage.get("table", []))
    logger.info("Fetched standings for %d teams", len(flat))
    return flat


async def fetch_matches_fd(
    client: FootballDataClient, http: httpx.AsyncClient,
    matchday: int,
) -> list[dict[str, Any]]:
    """Fetch fixtures for a given matchday."""
    url = f"{_BASE_URL}/competitions/{_COMPETITION_ID}/matches"
    logger.info("Fetching matches for matchday %d from: %s", matchday, url)
    resp = await http.get(
        url,
        headers=client.headers,
        params={"matchday": matchday},
    )
    resp.raise_for_status()
    matches = resp.json().get("matches", [])
    logger.info("Fetched %d matches for matchday %d", len(matches), matchday)
    return matches
