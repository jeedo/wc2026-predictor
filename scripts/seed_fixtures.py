#!/usr/bin/env python3
"""Manually seed Cosmos DB with real World Cup 2026 fixture data from API-Football."""
import asyncio
import json
import os
import sys
from datetime import datetime

# Add functions directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'functions'))

from azure.cosmos import CosmosClient
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
import httpx


async def get_cosmos_conn_str():
    """Get Cosmos DB connection string from Key Vault or environment."""
    conn_str = os.environ.get("CosmosDbConnectionString", "")
    if conn_str and not conn_str.startswith("@Microsoft.KeyVault"):
        return conn_str

    kv_uri = os.environ.get("KEY_VAULT_URI")
    if not kv_uri:
        raise ValueError("CosmosDbConnectionString and KEY_VAULT_URI not set")

    cred = DefaultAzureCredential()
    client = SecretClient(vault_url=kv_uri, credential=cred)
    secret = client.get_secret("cosmos-connection-string")
    return secret.value


async def get_football_data_api_key():
    """Get API-Football API key from Key Vault or environment."""
    key = os.environ.get("FOOTBALL_DATA_API_KEY", "")
    if key and not key.startswith("@Microsoft.KeyVault"):
        return key

    kv_uri = os.environ.get("KEY_VAULT_URI")
    if not kv_uri:
        raise ValueError("FOOTBALL_DATA_API_KEY and KEY_VAULT_URI not set")

    cred = DefaultAzureCredential()
    client = SecretClient(vault_url=kv_uri, credential=cred)
    secret = client.get_secret("football-data-api-key")
    return secret.value


async def fetch_teams(api_key: str) -> list[dict]:
    """Fetch teams from API-Football."""
    async with httpx.AsyncClient() as http:
        # API-Football doesn't have a dedicated teams endpoint for group stage
        # We'll use the competitions endpoint to get World Cup info
        resp = await http.get(
            "https://v3.football.api-sports.io/competitions",
            headers={"x-apisports-key": api_key},
            params={"name": "World Cup"},
        )
        resp.raise_for_status()
        data = resp.json()

        if not data.get("response"):
            raise ValueError("No World Cup competition found")

        # Get the World Cup season
        wc = data["response"][0]
        season = wc["seasons"][-1]["year"]  # Latest season

        print(f"Fetching World Cup {season} teams...")

        # Get standings to get all teams and groups
        resp = await http.get(
            "https://v3.football.api-sports.io/standings",
            headers={"x-apisports-key": api_key},
            params={"league": wc["id"], "season": season},
        )
        resp.raise_for_status()
        data = resp.json()

        teams = []
        for group_data in data.get("response", []):
            group = group_data.get("group", "")
            for team_info in group_data.get("standings", []):
                t = team_info.get("team", {})
                teams.append({
                    "id": t.get("id"),
                    "name": t.get("name"),
                    "group": group,
                    "fifaRanking": team_info.get("update"),  # Placeholder
                })

        return teams


async def fetch_fixtures(api_key: str) -> list[dict]:
    """Fetch fixtures from API-Football."""
    async with httpx.AsyncClient() as http:
        # Get World Cup competition ID
        resp = await http.get(
            "https://v3.football.api-sports.io/competitions",
            headers={"x-apisports-key": api_key},
            params={"name": "World Cup"},
        )
        resp.raise_for_status()
        data = resp.json()

        if not data.get("response"):
            raise ValueError("No World Cup competition found")

        wc = data["response"][0]
        season = wc["seasons"][-1]["year"]

        print(f"Fetching World Cup {season} fixtures (matchdays 1-3)...")

        fixtures = []
        for matchday in [1, 2, 3]:
            resp = await http.get(
                "https://v3.football.api-sports.io/fixtures",
                headers={"x-apisports-key": api_key},
                params={
                    "league": wc["id"],
                    "season": season,
                    "round": f"Group Stage - Matchday {matchday}",
                },
            )
            resp.raise_for_status()
            data = resp.json()

            for match in data.get("response", []):
                teams = match.get("teams", {})
                goals = match.get("goals", {})
                fixture = match.get("fixture", {})

                status_map = {
                    "FT": "FT",
                    "AET": "FT",
                    "PEN": "FT",
                    "1H": "1H",
                    "HT": "HT",
                    "NS": "NS",
                    "PST": "NS",
                    "SUSP": "NS",
                    "LIVE": "1H",
                }

                fixtures.append({
                    "fixtureId": fixture.get("id"),
                    "matchday": matchday,
                    "kickoff": fixture.get("date", ""),
                    "status": status_map.get(fixture.get("status"), "NS"),
                    "homeTeam": teams.get("home", {}).get("name", ""),
                    "homeTeamId": teams.get("home", {}).get("id"),
                    "awayTeam": teams.get("away", {}).get("name", ""),
                    "awayTeamId": teams.get("away", {}).get("id"),
                    "homeScore": goals.get("home"),
                    "awayScore": goals.get("away"),
                })

        return fixtures


async def main():
    """Seed the database."""
    try:
        conn_str = await get_cosmos_conn_str()
        api_key = await get_football_data_api_key()

        # Fetch data
        teams = await fetch_teams(api_key)
        fixtures = await fetch_fixtures(api_key)

        print(f"Fetched {len(teams)} teams and {len(fixtures)} fixtures")

        # Connect to Cosmos
        cosmos = CosmosClient.from_connection_string(conn_str)
        db = cosmos.get_database_client("wc2026")

        # Seed teams
        teams_container = db.get_container_client("teams")
        print("Clearing and seeding teams...")

        for team_id in [f"team-{t['id']}" for t in teams]:
            try:
                teams_container.delete_item(team_id, partition_key=team_id)
            except:
                pass

        for team in teams:
            doc = {
                "id": f"team-{team['id']}",
                "teamId": team["id"],
                "name": team["name"],
                "group": team["group"],
                "fifaRanking": None,
                "recentForm": [],
                "squadDepth": None,
            }
            teams_container.upsert_item(doc)

        # Seed fixtures
        fixtures_container = db.get_container_client("fixtures")
        print("Clearing and seeding fixtures...")

        for fixture in fixtures:
            fixture_id = f"fixture-{fixture['fixtureId']}"
            try:
                fixtures_container.delete_item(fixture_id, partition_key=fixture['matchday'])
            except:
                pass

        for fixture in fixtures:
            doc = {
                "id": f"fixture-{fixture['fixtureId']}",
                "fixtureId": fixture["fixtureId"],
                "matchday": fixture["matchday"],
                "kickoff": fixture["kickoff"],
                "status": fixture["status"],
                "homeTeam": fixture["homeTeam"],
                "homeTeamId": fixture["homeTeamId"],
                "awayTeam": fixture["awayTeam"],
                "awayTeamId": fixture["awayTeamId"],
                "homeScore": fixture["homeScore"],
                "awayScore": fixture["awayScore"],
            }
            fixtures_container.upsert_item(doc)

        print(f"✅ Seeded {len(teams)} teams and {len(fixtures)} fixtures")

    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
