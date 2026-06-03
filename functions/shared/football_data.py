"""HTTP client for football-data.org v4 API."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

_BASE_URL = "https://api.football-data.org/v4"
_COMPETITION = "WC"
_SEASON = 2026


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
    resp = await http.get(
        f"{_BASE_URL}/competitions/{_COMPETITION}/teams",
        headers=client.headers,
        params={"season": _SEASON},
    )
    resp.raise_for_status()
    return resp.json().get("teams", [])


async def fetch_standings_fd(
    client: FootballDataClient, http: httpx.AsyncClient
) -> list[dict[str, Any]]:
    """Fetch group standings from football-data.org."""
    resp = await http.get(
        f"{_BASE_URL}/competitions/{_COMPETITION}/standings",
        headers=client.headers,
        params={"season": _SEASON},
    )
    resp.raise_for_status()
    flat: list[dict[str, Any]] = []
    for stage in resp.json().get("standings", []):
        if stage.get("type") == "GROUP":
            flat.extend(stage.get("table", []))
    return flat


async def fetch_matches_fd(
    client: FootballDataClient, http: httpx.AsyncClient,
    matchday: int,
) -> list[dict[str, Any]]:
    """Fetch fixtures for a given matchday."""
    resp = await http.get(
        f"{_BASE_URL}/competitions/{_COMPETITION}/matches",
        headers=client.headers,
        params={"season": _SEASON, "matchday": matchday},
    )
    resp.raise_for_status()
    return resp.json().get("matches", [])
