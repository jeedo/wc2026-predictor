"""fn_predict — Queue Trigger: build a Claude prompt, call the API, write predictions."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import azure.functions as func
import anthropic
from azure.cosmos.aio import CosmosClient

from shared.cosmos import upsert_item, query_items
from fn_predict.scoring import compute_accuracy

logger = logging.getLogger(__name__)

_MODEL = "claude-haiku-4-5-20251001"
_MAX_TOKENS = 4096


# ---------------------------------------------------------------------------
# Azure client factories (patched in tests)
# ---------------------------------------------------------------------------

def get_containers() -> tuple[Any, Any, Any, Any]:
    cosmos = CosmosClient.from_connection_string(os.environ["CosmosDbConnectionString"])
    db = cosmos.get_database_client(os.environ.get("COSMOS_DATABASE_NAME", "wc2026"))
    return (
        db.get_container_client("teams"),
        db.get_container_client("fixtures"),
        db.get_container_client("predictions"),
        db.get_container_client("scores"),
    )


def get_anthropic_client() -> anthropic.AsyncAnthropic:
    return anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def _build_prompt(teams: list[dict[str, Any]], fixtures: list[dict[str, Any]]) -> str:
    from collections import defaultdict

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for team in teams:
        groups[team.get("group", "?")].append(team)

    completed = [f for f in fixtures if f.get("status") == "FT"]

    lines = [
        "You are a football analyst. Predict the FIFA World Cup 2026 group stage outcomes.",
        "For each group, predict the winner and runner-up based on the data below.",
        "Respond ONLY with valid JSON matching this schema exactly:",
        '{"predictions": [{"group": "A", "winner": "...", "runnerUp": "...", "reasoning": "..."}]}',
        "",
        "GROUP DATA:",
    ]

    for letter in sorted(groups.keys()):
        lines.append(f"\nGroup {letter}:")
        for t in groups[letter]:
            form = "".join(t.get("recentForm", []))
            lines.append(f"  - {t['name']} | FIFA rank: {t.get('fifaRanking', 'N/A')} | form: {form or 'none'}")

    if completed:
        lines.append("\nCOMPLETED RESULTS:")
        for f in completed:
            lines.append(
                f"  {f['homeTeam']} {f['homeScore']}–{f['awayScore']} {f['awayTeam']} (MD{f['matchday']})"
            )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def _parse_claude_response(text: str) -> list[dict[str, Any]]:
    try:
        data = json.loads(text)
        return data.get("predictions", [])
    except (json.JSONDecodeError, AttributeError):
        logger.error("Failed to parse Claude response: %.200s", text)
        return []


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def main(msg: func.QueueMessage) -> None:
    payload = json.loads(msg.get_body().decode())
    matchday: int = payload["matchday"]
    logger.info("Generating predictions for matchday %s", matchday)

    teams_container, fixtures_container, predictions_container, scores_container = get_containers()
    claude = get_anthropic_client()

    teams = await query_items(teams_container, "SELECT * FROM c")
    fixtures = await query_items(fixtures_container, "SELECT * FROM c")

    prompt = _build_prompt(teams=teams, fixtures=fixtures)

    response = await claude.messages.create(
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )

    raw_text = response.content[0].text
    predictions = _parse_claude_response(raw_text)

    now = datetime.now(timezone.utc).isoformat()

    prediction_doc: dict[str, Any] = {
        "id": f"prediction-md{matchday}",
        "matchday": matchday,
        "generatedAt": now,
        "groups": predictions,
    }
    await upsert_item(predictions_container, prediction_doc)
    logger.info("Wrote %d group predictions for matchday %s", len(predictions), matchday)

    # Accuracy scoring against completed fixtures
    finished_fixtures = [f for f in fixtures if f.get("status") == "FT"]
    if finished_fixtures and predictions:
        standings = await query_items(
            fixtures_container,
            "SELECT * FROM c WHERE c.status = 'FT'",
        )
        accuracy = compute_accuracy(predictions, standings)
        score_doc: dict[str, Any] = {
            "id": f"score-md{matchday}",
            "matchday": matchday,
            "evaluatedAt": now,
            **accuracy,
        }
        await upsert_item(scores_container, score_doc)
        logger.info(
            "Accuracy for matchday %s: %s/%s",
            matchday, accuracy["score"], accuracy["totalGroups"],
        )
