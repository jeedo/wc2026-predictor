"""fn_ingest — Timer Trigger: fetch fixtures, seed teams, and enqueue on FINISHED."""
from __future__ import annotations

import json
import logging
import os
from typing import Any

import azure.functions as func
import httpx
from azure.cosmos.aio import CosmosClient
from azure.storage.queue.aio import QueueClient
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

from shared.football_data import FootballDataClient, fetch_teams_fd, fetch_matches_fd
from shared.cosmos import upsert_item, query_items, read_item
from shared.usage_tracker import record_call

logger = logging.getLogger(__name__)

_MATCHDAYS = [1, 2, 3]


# ---------------------------------------------------------------------------
# Environment & secrets
# ---------------------------------------------------------------------------

def _get_football_data_api_key() -> str:
    """Read FOOTBALL_DATA_API_KEY from env or Key Vault.

    On Linux Consumption, KV references may not auto-resolve.
    Fall back to explicit SDK access if env var is a KV reference string.
    """
    val = os.environ.get("FOOTBALL_DATA_API_KEY", "")

    # If it's already a real key, use it
    if val and not val.startswith("@Microsoft.KeyVault"):
        return val

    # Otherwise, read directly from Key Vault
    kv_uri = os.environ.get("KEY_VAULT_URI")
    if not kv_uri:
        raise ValueError("FOOTBALL_DATA_API_KEY and KEY_VAULT_URI not set")

    cred = DefaultAzureCredential()
    client = SecretClient(vault_url=kv_uri, credential=cred)
    secret = client.get_secret("football-data-api-key")
    return secret.value


# ---------------------------------------------------------------------------
# Helpers (kept module-level so tests can import them directly)
# ---------------------------------------------------------------------------

def _should_enqueue(old_status: str | None, new_status: str) -> bool:
    return new_status == "FT" and old_status != "FT"


def _build_fixture_doc(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalise a football-data.org match record to our schema."""
    score = raw.get("score", {})
    ft = score.get("fullTime", {})
    status_map = {"FINISHED": "FT", "IN_PLAY": "1H", "PAUSED": "HT",
                  "TIMED": "NS", "SCHEDULED": "NS"}
    status_raw = raw.get("status", "NS")
    return {
        "id": f"fixture-{raw['id']}",
        "fixtureId": raw["id"],
        "matchday": raw.get("matchday", 1),
        "kickoff": raw.get("utcDate", ""),
        "status": status_map.get(status_raw, status_raw),
        "homeTeam": raw["homeTeam"]["name"],
        "homeTeamId": raw["homeTeam"]["id"],
        "awayTeam": raw["awayTeam"]["name"],
        "awayTeamId": raw["awayTeam"]["id"],
        "homeScore": ft.get("home"),
        "awayScore": ft.get("away"),
    }


def _build_team_doc(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalise a football-data.org team record to our schema."""
    return {
        "id": f"team-{raw['id']}",
        "teamId": raw["id"],
        "name": raw["name"],
        "shortName": raw.get("shortName", raw["name"]),
        "crestUrl": raw.get("crest", ""),
        "group": raw.get("group") or "Unknown",
        "fifaRanking": None,
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


def get_usage_container() -> Any | None:
    conn_str = os.environ.get("CosmosDbConnectionString")
    if not conn_str:
        return None
    cosmos = CosmosClient.from_connection_string(conn_str)
    db = cosmos.get_database_client(os.environ.get("COSMOS_DATABASE_NAME", "wc2026"))
    return db.get_container_client("usage")


def get_queue_client() -> QueueClient:
    return QueueClient.from_connection_string(
        os.environ["AzureWebJobsStorage"],
        queue_name=os.environ.get("PREDICT_QUEUE_NAME", "predict-trigger"),
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def main(mytimer: func.TimerRequest) -> None:
    logger.info("fn_ingest starting (timer trigger)")

    if mytimer.past_due:
        logger.warning("Timer trigger is past due")

    try:
        teams_container, fixtures_container = get_containers()
        queue = get_queue_client()

        try:
            api_key = _get_football_data_api_key()
            api = FootballDataClient(api_key=api_key)
            logger.info("Football-data API client initialized")
        except Exception as e:
            logger.error("Failed to get football-data API key: %s", str(e), exc_info=True)
            raise
    except Exception as e:
        logger.error("Fatal error in fn_ingest: %s", str(e), exc_info=True)
        raise

    usage_container = get_usage_container()

    async with httpx.AsyncClient() as http:
        # Seed teams on first run (container empty)
        logger.info("Checking if teams need seeding...")
        existing = await query_items(teams_container, "SELECT VALUE COUNT(1) FROM c")
        if not existing or existing[0] == 0:
            logger.info("Teams container empty, fetching from API-Football...")
            raw_teams = await fetch_teams_fd(api, http)
            await record_call(usage_container, "api-football")
            for raw in raw_teams:
                await upsert_item(teams_container, _build_team_doc(raw))
            logger.info("Seeded %d teams", len(raw_teams))
        else:
            logger.info("Teams already seeded (%d teams)", existing[0] if existing else 0)

        # Fetch and upsert fixtures for all three matchdays
        logger.info("Fetching fixtures for matchdays 1-3...")
        total_upserted = 0
        total_enqueued = 0
        for matchday in _MATCHDAYS:
            logger.info("Processing matchday %s", matchday)
            raw_fixtures = await fetch_matches_fd(api, http, matchday)
            await record_call(usage_container, "api-football")
            logger.info("Fetched %d fixtures for matchday %s", len(raw_fixtures), matchday)

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
                total_upserted += 1

                if _should_enqueue(prev_status, doc["status"]):
                    message = json.dumps(
                        {"matchday": matchday, "fixtureId": doc["fixtureId"]}
                    )
                    await queue.send_message(message)
                    total_enqueued += 1
                    logger.info(
                        "Enqueued predict trigger for fixture %s matchday %s",
                        doc["fixtureId"],
                        matchday,
                    )

        logger.info("Ingest complete: %d fixtures upserted, %d prediction triggers enqueued", total_upserted, total_enqueued)

    logger.info("fn_ingest completed successfully")
