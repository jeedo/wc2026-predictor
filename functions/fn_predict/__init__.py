"""fn_predict — Queue Trigger: build a Claude prompt, call the API, write predictions."""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import azure.functions as func
import anthropic
from pydantic import BaseModel, ConfigDict
from azure.cosmos.aio import CosmosClient

from shared.cosmos import upsert_item, query_items
from shared.serpa import search_team_news
from shared.usage_tracker import record_call
from fn_predict.scoring import compute_accuracy

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-4-5"  # Upgraded to Sonnet for structured outputs
_MAX_TOKENS = 4096


# Pydantic models for structured output
class PredictedMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    homeTeam: str
    awayTeam: str
    matchday: int
    predictedHomeScore: int
    predictedAwayScore: int
    confidence: str  # "high", "medium", "low"


class GroupPrediction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    group: str
    winner: str
    runnerUp: str
    confidence: str
    reasoning: str
    matches: list[PredictedMatch]


class PredictionsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    predictions: list[GroupPrediction]


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


def get_usage_container() -> Any | None:
    conn_str = os.environ.get("CosmosDbConnectionString")
    if not conn_str:
        return None
    cosmos = CosmosClient.from_connection_string(conn_str)
    db = cosmos.get_database_client(os.environ.get("COSMOS_DATABASE_NAME", "wc2026"))
    return db.get_container_client("usage")


def get_anthropic_client() -> anthropic.AsyncAnthropic:
    return anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def _build_prompt(
    teams: list[dict[str, Any]],
    fixtures: list[dict[str, Any]],
    news: dict[str, list[str]] | None = None,
) -> str:
    from collections import defaultdict

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for team in teams:
        groups[team.get("group", "?")].append(team)

    completed = [f for f in fixtures if f.get("status") == "FT"]
    upcoming = [f for f in fixtures if f.get("status") not in ("FT", "1H", "2H", "HT", "ET", "P")]

    # Group upcoming fixtures by group letter via team lookup
    team_to_group: dict[str, str] = {t["name"]: t.get("group", "?") for t in teams}
    upcoming_by_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for f in upcoming:
        g = team_to_group.get(f.get("homeTeam", ""), "?")
        upcoming_by_group[g].append(f)

    schema = (
        '{"predictions": ['
        '{"group": "A", "winner": "...", "runnerUp": "...", "confidence": "high|medium|low", "reasoning": "...", '
        '"matches": [{"homeTeam": "...", "awayTeam": "...", "matchday": 1, '
        '"predictedHomeScore": 0, "predictedAwayScore": 0, "confidence": "high|medium|low"}]}'
        ']}'
    )

    lines = [
        "You are a football analyst. Predict the FIFA World Cup 2026 group stage outcomes.",
        "CRITICAL: You MUST predict for ALL groups listed below.",
        "CRITICAL: Do NOT invent groups or team assignments. Use ONLY the group assignments provided.",
        "For each group, predict: the winner, runner-up, confidence level (high/medium/low), reasoning, and the score of every upcoming fixture.",
        "Rate your confidence for each group and each predicted match score.",
        "",
        "REQUIRED GROUP ASSIGNMENTS (DO NOT CHANGE):",
    ]

    # Build group assignments dynamically from team data
    for letter in sorted(groups.keys()):
        team_names = [t["name"] for t in groups[letter]]
        lines.append(f"Group {letter}: {', '.join(team_names)}")

    lines.extend([
        "",
        "Respond ONLY with valid JSON matching this schema exactly:",
        schema,
        "",
        "DETAILED GROUP DATA:",
    ])

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

    if upcoming:
        lines.append("\nUPCOMING FIXTURES (predict scores for each):")
        for f in upcoming:
            lines.append(
                f"  MD{f['matchday']}: {f['homeTeam']} vs {f['awayTeam']}"
            )

    if news:
        lines.append("\nRECENT TEAM NEWS:")
        for team_name, snippets in news.items():
            if snippets:
                lines.append(f"  {team_name}:")
                for snippet in snippets:
                    lines.append(f"    - {snippet}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def _parse_claude_response(text: str) -> list[dict[str, Any]]:
    """Parse Claude's prediction response. With structured outputs, response is pure JSON."""
    try:
        data = json.loads(text)
        return data.get("predictions", [])
    except json.JSONDecodeError as e:
        logger.error("Failed to parse Claude structured output: %s. Response: %.200s", str(e), text)
        return []


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main(msg: func.QueueMessage) -> None:
    logger.info("Prediction queue message received")
    asyncio.run(_main_async(msg))


async def _main_async(msg: func.QueueMessage) -> None:
    try:
        payload = json.loads(msg.get_body().decode())
        matchday: int = payload["matchday"]
        logger.info("Generating predictions for matchday %s", matchday)

        teams_container, fixtures_container, predictions_container, scores_container = get_containers()
        usage_container = get_usage_container()
        claude = get_anthropic_client()
        logger.info("Containers and clients initialized")

        logger.info("Querying teams...")
        teams = await query_items(teams_container, "SELECT * FROM c")
        fixtures = await query_items(fixtures_container, "SELECT * FROM c")

        news: dict[str, list[str]] = {}
        serpa_key = os.environ.get("SERPA_API_KEY")
        if serpa_key:
            for team in teams:
                team_name = team.get("name", "")
                if team_name:
                    news[team_name] = await search_team_news(team_name, api_key=serpa_key)
                    await record_call(usage_container, "serper")

        prompt = _build_prompt(teams=teams, fixtures=fixtures, news=news or None)

        # Use structured outputs to guarantee valid JSON
        response = await claude.beta.messages.parse(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
            output_config={
                "format": {
                    "type": "json_schema",
                    "schema": PredictionsResponse.model_json_schema(),
                }
            },
            betas=["structured-outputs-2025-11-13"],
        )

        usage = response.usage
        await record_call(
            usage_container, "anthropic",
            inputTokens=usage.input_tokens,
            outputTokens=usage.output_tokens,
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
    except Exception as e:
        logger.error("Error generating predictions for matchday: %s", str(e), exc_info=True)
        raise
