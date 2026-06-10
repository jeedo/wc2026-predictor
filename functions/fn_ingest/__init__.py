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
from azure.storage.queue import BinaryBase64EncodePolicy
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

from shared.football_data import FootballDataClient, fetch_teams_fd, fetch_matches_fd, fetch_knockout_matches_fd
from shared.cosmos import upsert_item, query_items, read_item
from shared.usage_tracker import record_call
from shared.group_derivation import fetch_groups_from_standings

logger = logging.getLogger(__name__)

_MATCHDAYS = [1, 2, 3]
KNOCKOUT_STAGES = ["LAST_32", "LAST_16", "QUARTER_FINALS", "SEMI_FINALS", "THIRD_PLACE", "FINAL"]


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
    if secret.value is None:
        raise ValueError("football-data-api-key secret has no value")
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
    stage = raw.get("stage") or "GROUP_STAGE"
    matchday_raw = raw.get("matchday")
    matchday = matchday_raw if matchday_raw is not None else stage
    home_name = (raw.get("homeTeam") or {}).get("name") or "TBD"
    away_name = (raw.get("awayTeam") or {}).get("name") or "TBD"
    home_id = (raw.get("homeTeam") or {}).get("id")
    away_id = (raw.get("awayTeam") or {}).get("id")
    return {
        "id": f"fixture-{raw['id']}",
        "fixtureId": raw["id"],
        "matchday": matchday,
        "stage": stage,
        "kickoff": raw.get("utcDate", ""),
        "status": status_map.get(status_raw, status_raw),
        "homeTeam": home_name,
        "homeTeamId": home_id,
        "awayTeam": away_name,
        "awayTeamId": away_id,
        "homeScore": ft.get("home"),
        "awayScore": ft.get("away"),
    }


def _build_team_doc(raw: dict[str, Any], group: str | None = None) -> dict[str, Any]:
    """Normalise a football-data.org team record to our schema.

    If group is provided, use it. Otherwise fall back to API data or "Unknown".
    """
    return {
        "id": f"team-{raw['id']}",
        "teamId": raw["id"],
        "name": raw["name"],
        "shortName": raw.get("shortName", raw["name"]),
        "crestUrl": raw.get("crest", ""),
        "group": group or raw.get("group") or "Unknown",
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
        message_encode_policy=BinaryBase64EncodePolicy(),
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def main(msg: func.QueueMessage) -> None:
    logger.info("fn_ingest starting (queue trigger) payload=%s", msg.get_body().decode()[:200])

    payload: dict = {}
    try:
        payload = json.loads(msg.get_body().decode())
    except Exception:
        pass
    correlation_id: str = payload.get("correlationId") or str(__import__("uuid").uuid4())
    logger.info("fn_ingest correlationId=%s", correlation_id)

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
        # Fetch group assignments from standings endpoint
        logger.info("Fetching group assignments from Football Data API...")
        team_to_group = await fetch_groups_from_standings(api_key)
        await record_call(usage_container, "api-football")
        logger.info("Fetched %d group assignments from standings", len(team_to_group))

        # Fetch all fixtures for matchdays 1-3
        logger.info("Fetching fixtures for matchdays 1-3 from 2026 World Cup...")
        all_fixtures = []
        for matchday in _MATCHDAYS:
            raw_fixtures = await fetch_matches_fd(api, http, matchday)
            await record_call(usage_container, "api-football")
            all_fixtures.extend(raw_fixtures)

        # Fetch knockout stage fixtures
        logger.info("Fetching knockout stage fixtures...")
        all_knockout: list[dict] = []
        for stage in KNOCKOUT_STAGES:
            raw_knockout = await fetch_knockout_matches_fd(api, http, stage)
            await record_call(usage_container, "api-football")
            all_knockout.extend(raw_knockout)
        logger.info("Fetched %d knockout fixtures across %d stages", len(all_knockout), len(KNOCKOUT_STAGES))

        # Seed teams on first run (container empty)
        logger.info("Checking if teams need seeding...")
        existing = await query_items(teams_container, "SELECT VALUE COUNT(1) FROM c")
        if not existing or existing[0] == 0:
            logger.info("Teams container empty, fetching 2026 World Cup teams from Football Data API...")
            raw_teams = await fetch_teams_fd(api, http)
            await record_call(usage_container, "api-football")

            logger.info("Processing %d teams into Cosmos DB documents", len(raw_teams))
            by_group: dict[str, list[str]] = {}
            for raw in raw_teams:
                team_name = raw.get("name", "Unknown")
                # Use derived group if available, otherwise use API data or default
                team_group = team_to_group.get(team_name) or raw.get("group") or "Unknown"
                if team_group not in by_group:
                    by_group[team_group] = []
                by_group[team_group].append(team_name)
                await upsert_item(teams_container, _build_team_doc(raw, group=team_group))

            logger.info("Seeded %d teams in %d groups", len(raw_teams), len(by_group))
            for group in sorted(by_group.keys()):
                logger.info("  Group %s: %s", group, ", ".join(by_group[group]))
        else:
            logger.info("Teams already seeded (%d teams)", existing[0] if existing else 0)

        # Upsert fixtures for all three matchdays
        logger.info("Upserting fixtures for matchdays 1-3...")
        total_upserted = 0
        total_enqueued = 0
        fixture_summary = {}

        for matchday in _MATCHDAYS:
            logger.info("Processing matchday %d", matchday)
            # Filter pre-fetched fixtures by matchday
            matchday_fixtures = [f for f in all_fixtures if f.get("matchday") == matchday]

            if not matchday_fixtures:
                logger.warning("No fixtures found for matchday %d", matchday)
                continue

            logger.info("Processing %d fixtures for matchday %d", len(matchday_fixtures), matchday)
            fixture_summary[matchday] = {"count": len(matchday_fixtures), "enqueued": 0}

            for raw in matchday_fixtures:
                doc = _build_fixture_doc(raw)
                fixture_id = doc["id"]
                partition_key = doc["matchday"]

                # Log fixture details
                home_team = doc.get("homeTeam", "Unknown")
                away_team = doc.get("awayTeam", "Unknown")
                logger.debug("Upserting fixture: %s vs %s (MD%d)", home_team, away_team, matchday)

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
                        {"matchday": matchday, "fixtureId": doc["fixtureId"], "correlationId": correlation_id}
                    ).encode()
                    await queue.send_message(message)
                    total_enqueued += 1
                    fixture_summary[matchday]["enqueued"] += 1
                    logger.info(
                        "Enqueued prediction trigger for %s vs %s (MD%d)",
                        home_team,
                        away_team,
                        matchday,
                    )

        # Upsert knockout fixtures
        knockout_upserted = 0
        knockout_enqueued = 0
        for raw in all_knockout:
            doc = _build_fixture_doc(raw)
            fixture_id = doc["id"]
            partition_key = doc["matchday"]  # stage string for knockout
            stage_name = doc.get("stage", "UNKNOWN")

            try:
                prev = await read_item(fixtures_container, fixture_id, partition_key)
                prev_status = prev.get("status")
            except Exception:
                prev_status = None

            await upsert_item(fixtures_container, doc)
            knockout_upserted += 1

            if _should_enqueue(prev_status, doc["status"]):
                message = json.dumps(
                    {"matchday": stage_name, "fixtureId": doc["fixtureId"], "correlationId": correlation_id}
                ).encode()
                await queue.send_message(message)
                knockout_enqueued += 1
                logger.info(
                    "Enqueued prediction trigger for knockout %s vs %s (%s)",
                    doc.get("homeTeam"), doc.get("awayTeam"), stage_name,
                )

        total_upserted += knockout_upserted
        total_enqueued += knockout_enqueued
        logger.info("Knockout ingest: %d fixtures upserted, %d triggers enqueued", knockout_upserted, knockout_enqueued)

        logger.info("Ingest complete: %d fixtures upserted, %d prediction triggers enqueued", total_upserted, total_enqueued)
        for matchday in sorted(fixture_summary.keys()):
            info = fixture_summary[matchday]
            logger.info("  Matchday %d: %d fixtures (%d enqueued)", matchday, info["count"], info["enqueued"])

    logger.info("fn_ingest completed successfully")
