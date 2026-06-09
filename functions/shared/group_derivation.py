"""Group assignment fetching from Football Data API standings."""
import asyncio
import logging
from typing import Any

import httpx

from shared.football_data import _TRANSIENT_ERRORS

logger = logging.getLogger(__name__)


async def fetch_groups_from_standings(api_key: str) -> dict[str, str]:
    """Fetch group assignments from Football Data API standings endpoint.

    Returns dict mapping team name -> group letter (A-L).
    Fetches official group data from the standings endpoint which is the
    authoritative source for group assignments.
    """
    headers = {"X-Auth-Token": api_key}
    url = "https://api.football-data.org/v4/competitions/2000/standings"

    last_exc: Exception = RuntimeError("unreachable")
    async with httpx.AsyncClient() as client:
        for attempt in range(3):
            try:
                resp = await client.get(url, headers=headers, timeout=10)
                break
            except _TRANSIENT_ERRORS as exc:
                last_exc = exc
                if attempt < 2:
                    delay = 2 ** (attempt + 1)
                    logger.warning(
                        "Transient error on attempt %d/3, retrying in %ds: %s",
                        attempt + 1, delay, exc,
                    )
                    await asyncio.sleep(delay)
        else:
            raise last_exc

    if resp.status_code != 200:
        raise ValueError(f"Failed to fetch standings: {resp.status_code}")

    data = resp.json()
    standings = data.get("standings", [])

    team_to_group: dict[str, str] = {}

    for standing in standings:
        group_name = standing.get("group", "")
        group_letter = group_name.replace("Group ", "").strip()

        table = standing.get("table", [])
        for entry in table:
            team = entry.get("team", {})
            team_name = team.get("name")
            if team_name:
                team_to_group[team_name] = group_letter

    return team_to_group
