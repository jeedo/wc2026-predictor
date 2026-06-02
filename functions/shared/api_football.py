"""HTTP client for API-Football v3 (api-sports.io)."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

import httpx

_BASE_URL = "https://v3.football.api-sports.io"
_LEAGUE = 1
_SEASON = 2026
_ROUND_RE = re.compile(r"^Group Stage - (\d+)$")


@dataclass
class ApiFootballClient:
    api_key: str

    @property
    def headers(self) -> dict[str, str]:
        return {"x-apisports-key": self.api_key}

    @classmethod
    def from_env(cls) -> "ApiFootballClient":
        return cls(api_key=os.environ["APISPORTS_API_KEY"])


def normalise_round(round_str: str) -> int | None:
    """Convert 'Group Stage - N' to integer N, or None for non-group rounds."""
    m = _ROUND_RE.match(round_str)
    return int(m.group(1)) if m else None


async def fetch_teams(
    client: ApiFootballClient, http: httpx.AsyncClient
) -> list[dict[str, Any]]:
    resp = await http.get(
        f"{_BASE_URL}/teams",
        headers=client.headers,
        params={"league": _LEAGUE, "season": _SEASON},
    )
    resp.raise_for_status()
    return resp.json()["response"]


async def fetch_fixtures(
    client: ApiFootballClient,
    http: httpx.AsyncClient,
    matchday: int,
) -> list[dict[str, Any]]:
    resp = await http.get(
        f"{_BASE_URL}/fixtures",
        headers=client.headers,
        params={
            "league": _LEAGUE,
            "season": _SEASON,
            "round": f"Group Stage - {matchday}",
        },
    )
    resp.raise_for_status()
    raw = resp.json()["response"]
    for item in raw:
        item["matchday"] = matchday
    return raw


async def fetch_standings(
    client: ApiFootballClient, http: httpx.AsyncClient
) -> list[dict[str, Any]]:
    resp = await http.get(
        f"{_BASE_URL}/standings",
        headers=client.headers,
        params={"league": _LEAGUE, "season": _SEASON},
    )
    resp.raise_for_status()
    flat: list[dict[str, Any]] = []
    for entry in resp.json()["response"]:
        for group in entry["league"]["standings"]:
            flat.extend(group)
    return flat
