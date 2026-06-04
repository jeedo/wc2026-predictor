"""Group assignment fetching from Football Data API standings."""
from typing import Any
import httpx


async def fetch_groups_from_standings(api_key: str) -> dict[str, str]:
    """Fetch group assignments from Football Data API standings endpoint.

    Returns dict mapping team name -> group letter (A-L).
    Fetches official group data from the standings endpoint which is the
    authoritative source for group assignments.
    """
    headers = {"X-Auth-Token": api_key}

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://api.football-data.org/v4/competitions/2000/standings",
            headers=headers,
            timeout=10
        )

    if resp.status_code != 200:
        raise ValueError(f"Failed to fetch standings: {resp.status_code}")

    data = resp.json()
    standings = data.get("standings", [])

    team_to_group: dict[str, str] = {}

    for standing in standings:
        group_name = standing.get("group", "")
        # Extract letter from "Group A", "Group B", etc.
        group_letter = group_name.replace("Group ", "").strip()

        table = standing.get("table", [])
        for entry in table:
            team = entry.get("team", {})
            team_name = team.get("name")
            if team_name:
                team_to_group[team_name] = group_letter

    return team_to_group
