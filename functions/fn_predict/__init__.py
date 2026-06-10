"""fn_predict — Queue Trigger: build a Claude prompt, call the API, write predictions."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Any

import azure.functions as func
import anthropic
from pydantic import BaseModel, ConfigDict
from azure.cosmos.aio import CosmosClient

from shared.cosmos import upsert_item, query_items
from shared.serpa import search_team_news
from shared.usage_tracker import record_call
from shared.telemetry import track_event, track_exception
from fn_predict.scoring import compute_accuracy

logger = logging.getLogger(__name__)

# Module-level diagnostic: fires on import, before any invocation. If this
# does NOT appear in App Insights traces, the crash is at import time.
logger.info("fn_predict module loaded")

_MODEL = "claude-sonnet-4-5"
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


class KnockoutMatchPrediction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fixtureId: int
    stage: str
    homeTeam: str
    awayTeam: str
    predictedWinner: str
    predictedHomeScore: int
    predictedAwayScore: int
    confidence: str  # "high", "medium", "low"


class KnockoutPrediction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stage: str
    matches: list[KnockoutMatchPrediction]


class PredictionsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    predictions: list[GroupPrediction]
    knockout: list[KnockoutPrediction] = []


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


def get_news_container() -> Any | None:
    conn_str = os.environ.get("CosmosDbConnectionString")
    if not conn_str:
        return None
    cosmos = CosmosClient.from_connection_string(conn_str)
    db = cosmos.get_database_client(os.environ.get("COSMOS_DATABASE_NAME", "wc2026"))
    return db.get_container_client("news")


def _safe_id(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9\-_]", "-", name).lower()


def get_anthropic_client() -> anthropic.AsyncAnthropic:
    return anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


# ---------------------------------------------------------------------------
# News fetching (parallel with Cosmos cache)
# ---------------------------------------------------------------------------

async def _fetch_news_parallel(
    teams: list[dict[str, Any]],
    serpa_key: str,
    max_results: int,
    today: str,
    news_container: Any | None,
    usage_container: Any | None,
) -> dict[str, list[str]]:
    team_names = [t.get("name", "") for t in teams if t.get("name")]
    cached: dict[str, list[str]] = {}
    uncached: list[str] = []

    if news_container is not None:
        for name in team_names:
            cache_id = f"news-{_safe_id(name)}-{today}"
            try:
                doc = await news_container.read_item(item=cache_id, partition_key=name)
                cached[name] = doc.get("snippets", [])
            except Exception:
                uncached.append(name)
    else:
        uncached = list(team_names)

    if not uncached:
        track_event("fn_predict/news_all_cached", {"cached_count": str(len(cached))})
        return cached

    t0 = time.monotonic()
    tasks = [search_team_news(name, api_key=serpa_key, max_results=max_results) for name in uncached]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    elapsed_ms = int((time.monotonic() - t0) * 1000)

    fetched: dict[str, list[str]] = {}
    error_count = 0
    for name, result in zip(uncached, results):
        if isinstance(result, list):
            snippets = result
        else:
            snippets = []
            error_count += 1
        fetched[name] = snippets
        if news_container is not None:
            cache_id = f"news-{_safe_id(name)}-{today}"
            try:
                await news_container.upsert_item(body={
                    "id": cache_id,
                    "teamName": name,
                    "date": today,
                    "snippets": snippets,
                    "ttl": 43200,
                })
            except Exception as e:
                logger.warning("Failed to cache news for %s: %s", name, e)
        if snippets and usage_container is not None:
            await record_call(usage_container, "serper")

    track_event("fn_predict/news_fetched", {
        "cached_count": str(len(cached)),
        "fetched_count": str(len(fetched)),
        "error_count": str(error_count),
        "elapsed_ms": str(elapsed_ms),
    })
    return {**cached, **fetched}


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

    # Separate group stage from knockout fixtures
    group_fixtures = [
        f for f in fixtures
        if isinstance(f.get("matchday"), int) or f.get("stage") == "GROUP_STAGE" or not f.get("stage")
    ]
    knockout_fixtures_all = [
        f for f in fixtures
        if f.get("stage") and f.get("stage") != "GROUP_STAGE" and not isinstance(f.get("matchday"), int)
    ]
    # Only include knockout fixtures where both teams are known
    knockout_fixtures = [
        f for f in knockout_fixtures_all
        if f.get("homeTeam") not in (None, "TBD", "") and f.get("awayTeam") not in (None, "TBD", "")
    ]

    completed = [f for f in group_fixtures if f.get("status") == "FT"]
    upcoming = [f for f in group_fixtures if f.get("status") not in ("FT", "1H", "2H", "HT", "ET", "P")]

    team_to_group: dict[str, str] = {t["name"]: t.get("group", "?") for t in teams}
    upcoming_by_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for f in upcoming:
        g = team_to_group.get(f.get("homeTeam", ""), "?")
        upcoming_by_group[g].append(f)

    completed_by_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for f in completed:
        g = team_to_group.get(f.get("homeTeam", ""), "?")
        completed_by_group[g].append(f)

    has_knockout = bool(knockout_fixtures)
    knockout_schema_extra = ""
    if has_knockout:
        knockout_schema_extra = (
            ', "knockout": [{"stage": "LAST_32", "matches": ['
            '{"fixtureId": 0, "stage": "LAST_32", "homeTeam": "...", "awayTeam": "...", '
            '"predictedWinner": "...", "predictedHomeScore": 0, "predictedAwayScore": 0, '
            '"confidence": "high|medium|low"}]}]'
        )

    schema = (
        '{"predictions": ['
        '{"group": "A", "winner": "...", "runnerUp": "...", "confidence": "high|medium|low", "reasoning": "...", '
        '"matches": [{"homeTeam": "...", "awayTeam": "...", "matchday": 1, '
        '"predictedHomeScore": 0, "predictedAwayScore": 0, "confidence": "high|medium|low"}]}'
        ']'
        + knockout_schema_extra
        + '}'
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
        if completed_by_group[letter]:
            lines.append("  Completed results:")
            for f in completed_by_group[letter]:
                lines.append(
                    f"    {f['homeTeam']} {f['homeScore']}–{f['awayScore']} {f['awayTeam']} (MD{f['matchday']})"
                )
        if upcoming_by_group[letter]:
            lines.append("  Upcoming fixtures (predict scores for each):")
            for f in upcoming_by_group[letter]:
                lines.append(
                    f"    MD{f['matchday']}: {f['homeTeam']} vs {f['awayTeam']}"
                )

    if has_knockout:
        lines.append("\nKNOCKOUT FIXTURES (predict winner and score for each — include in 'knockout' field):")
        knockout_by_stage: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for f in knockout_fixtures:
            knockout_by_stage[f.get("stage", "UNKNOWN")].append(f)
        for stage_name in sorted(knockout_by_stage.keys()):
            lines.append(f"\n{stage_name}:")
            for f in knockout_by_stage[stage_name]:
                kickoff = (f.get("kickoff") or "")[:10]
                lines.append(
                    f"  [{f.get('fixtureId')}] {f['homeTeam']} vs {f['awayTeam']} ({kickoff})"
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
    track_event("fn_predict/invoked")
    asyncio.run(_main_async(msg))


async def _main_async(msg: func.QueueMessage) -> None:
    stage = "init"
    matchday: int = -1
    try:
        payload = json.loads(msg.get_body().decode())
        matchday = payload["matchday"]
        correlation_id = payload.get("correlationId", "unknown")
        logger.info("Generating predictions for matchday %s correlationId=%s", matchday, correlation_id)
        track_event("fn_predict/started", {"matchday": str(matchday)})

        stage = "containers"
        teams_container, fixtures_container, predictions_container, scores_container = get_containers()
        usage_container = get_usage_container()
        news_container = get_news_container()
        claude = get_anthropic_client()
        logger.info("Containers and clients initialized")

        stage = "data_load"
        logger.info("Querying teams...")
        teams = await query_items(teams_container, "SELECT * FROM c")
        fixtures = await query_items(fixtures_container, "SELECT * FROM c")
        track_event("fn_predict/data_loaded", {
            "matchday": str(matchday),
            "teams_count": str(len(teams)),
            "fixtures_count": str(len(fixtures)),
        })

        stage = "news"
        news: dict[str, list[str]] = {}
        serpa_key = os.environ.get("SERPA_API_KEY")
        if serpa_key:
            max_results = int(os.environ.get("SERPA_MAX_RESULTS", "3"))
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            news = await _fetch_news_parallel(
                teams, serpa_key, max_results, today, news_container, usage_container
            )
        else:
            track_event("fn_predict/news_skipped", {"reason": "no_serpa_key"})

        news_team_count = sum(1 for v in news.values() if v)
        prompt = _build_prompt(teams=teams, fixtures=fixtures, news=news or None)
        logger.info(
            "Prompt built: %d chars, %d teams with news",
            len(prompt), news_team_count,
        )
        track_event("fn_predict/prompt_built", {
            "matchday": str(matchday),
            "prompt_chars": str(len(prompt)),
            "news_teams": str(news_team_count),
        })

        stage = "claude"
        t0 = time.monotonic()
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
        claude_ms = int((time.monotonic() - t0) * 1000)

        usage = response.usage
        await record_call(
            usage_container, "anthropic",
            inputTokens=usage.input_tokens,
            outputTokens=usage.output_tokens,
        )
        track_event("fn_predict/claude_complete", {
            "matchday": str(matchday),
            "input_tokens": str(usage.input_tokens),
            "output_tokens": str(usage.output_tokens),
            "elapsed_ms": str(claude_ms),
            "model": _MODEL,
        })

        stage = "write"
        raw_text = response.content[0].text  # type: ignore[union-attr]
        predictions = _parse_claude_response(raw_text)

        # Parse knockout predictions (empty list if not present)
        try:
            full_response = json.loads(raw_text)
            knockout_predictions: list[dict[str, Any]] = full_response.get("knockout", [])
        except Exception:
            knockout_predictions = []

        now = datetime.now(timezone.utc).isoformat()
        prediction_doc: dict[str, Any] = {
            "id": "predictions-all",
            "matchday": matchday,
            "generatedAt": now,
            "groups": predictions,
            "knockout": knockout_predictions,
        }
        await upsert_item(predictions_container, prediction_doc)
        logger.info(
            "Wrote %d group predictions: id=%s matchday=%s generatedAt=%s",
            len(predictions), prediction_doc["id"], matchday, now,
        )
        track_event("fn_predict/prediction_written", {
            "matchday": str(matchday),
            "groups_count": str(len(predictions)),
        })

        stage = "accuracy"
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
            track_event("fn_predict/accuracy_scored", {
                "matchday": str(matchday),
                "score": str(accuracy["score"]),
                "total_groups": str(accuracy["totalGroups"]),
            })

        track_event("fn_predict/completed", {"matchday": str(matchday), "stage": stage})

    except Exception as e:
        logger.error("Error generating predictions at stage=%s matchday=%s: %s", stage, matchday, str(e), exc_info=True)
        track_exception(e, {"stage": stage, "matchday": str(matchday)})
        raise
