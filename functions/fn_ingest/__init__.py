"""fn_ingest — Timer Trigger: fetch fixtures from API-Football, seed teams,
upsert to Cosmos DB, and enqueue a message when a match finishes."""
from __future__ import annotations

import json
import logging
import os
from typing import Any

import azure.functions as func
import httpx
from azure.cosmos.aio import CosmosClient
from azure.storage.queue.aio import QueueClient

from shared.api_football import (
    ApiFootballClient,
    fetch_fixtures,
    fetch_teams,
    normalise_round,
)
from shared.cosmos import upsert_item, query_items, read_item

logger = logging.getLogger(__name__)

_MATCHDAYS = [1, 2, 3]


# ---------------------------------------------------------------------------
# Helpers (kept module-level so tests can import them directly)
# ---------------------------------------------------------------------------

def _should_enqueue(old_status: str | None, new_status: str) -> bool:
    return new_status == "FT" and old_status != "FT"


def _build_fixture_doc(raw: dict[str, Any]) -> dict[str, Any]:
    fixture = raw["fixture"]
    return {
        "id": f"fixture-{fixture['id']}",
        "fixtureId": fixture["id"],
        "matchday": raw["matchday"],
        "kickoff": fixture["date"],
        "status": fixture["status"]["short"],
        "homeTeam": raw["teams"]["home"]["name"],
        "homeTeamId": raw["teams"]["home"]["id"],
        "awayTeam": raw["teams"]["away"]["name"],
        "awayTeamId": raw["teams"]["away"]["id"],
        "homeScore": raw["goals"]["home"],
        "awayScore": raw["goals"]["away"],
    }


def _build_team_doc(raw: dict[str, Any]) -> dict[str, Any]:
    team = raw["team"]
    return {
        "id": f"team-{team['id']}",
        "teamId": team["id"],
        "name": team["name"],
        "group": raw.get("group", "Unknown"),
        "fifaRanking": raw.get("fifaRanking"),
        "recentForm": [],
        "squadDepth": None,
    }


# ---------------------------------------------------------------------------
# Azure client factories (patched in tests)
# ---------------------------------------------------------------------------

def get_containers() -> tuple[Any, Any]:
    cosmos = CosmosClient.from_connection_string(os.environ["CosmosDbConnectionString"])
    db = cosmos.get_database_client(os.environ.get("COSMOS_DATABASE_NAME", "wc2026"))
    return db.get_container_client("teams"), db.get_container_client("fixtures")


def get_queue_client() -> QueueClient:
    return QueueClient.from_connection_string(
        os.environ["AzureWebJobsStorage"],
        queue_name=os.environ.get("PREDICT_QUEUE_NAME", "predict-trigger"),
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def main(mytimer: func.TimerRequest) -> None:
    if mytimer.past_due:
        logger.warning("Timer trigger is past due")

    teams_container, fixtures_container = get_containers()
    queue = get_queue_client()
    api = ApiFootballClient.from_env()

    async with httpx.AsyncClient() as http:
        # Seed teams on first run (container empty)
        existing = query_items(teams_container, "SELECT VALUE COUNT(1) FROM c")
        if not existing or existing[0] == 0:
            raw_teams = await fetch_teams(api, http)
            for raw in raw_teams:
                await upsert_item(teams_container, _build_team_doc(raw))
            logger.info("Seeded %d teams", len(raw_teams))

        # Fetch and upsert fixtures for all three matchdays
        for matchday in _MATCHDAYS:
            raw_fixtures = await fetch_fixtures(api, http, matchday)
            for raw in raw_fixtures:
                doc = _build_fixture_doc(raw)
                fixture_id = doc["id"]
                partition_key = doc["matchday"]

                # Determine previous status for transition detection
                try:
                    prev = await read_item(
                        fixtures_container, fixture_id, partition_key
                    )
                    prev_status: str | None = prev.get("status")
                except Exception:
                    prev_status = None

                await upsert_item(fixtures_container, doc)

                if _should_enqueue(prev_status, doc["status"]):
                    message = json.dumps(
                        {"matchday": matchday, "fixtureId": doc["fixtureId"]}
                    )
                    await queue.send_message(message)
                    logger.info(
                        "Enqueued predict trigger for fixture %s matchday %s",
                        doc["fixtureId"],
                        matchday,
                    )
