"""fn_api — HTTP Trigger: serve groups, predictions, fixtures, and accuracy."""
from __future__ import annotations

import asyncio
import copy
import json
import logging
import os
import re
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any
from urllib.parse import unquote

import azure.functions as func
from azure.cosmos import CosmosClient, PartitionKey  # sync client — fn_api is synchronous
from azure.storage.queue import QueueClient

from shared.cosmos import query_items_sync as query_items
from shared.usage_tracker import PROVIDER_LIMITS
from fn_predict import PredictionsResponse

logger = logging.getLogger(__name__)
logger.info("fn_api module loaded successfully")

_FIXTURE_ROUTE = re.compile(r"/api/fixtures/(\d+)$")


# ---------------------------------------------------------------------------
# Azure client factory (patched in tests)
# ---------------------------------------------------------------------------

def get_containers() -> tuple[Any, Any, Any, Any, Any]:
    cosmos = CosmosClient.from_connection_string(
        os.environ["CosmosDbConnectionString"],
        connection_verify=True,
    )
    db = cosmos.get_database_client(os.environ.get("COSMOS_DATABASE_NAME", "wc2026"))
    return (
        db.get_container_client("teams"),
        db.get_container_client("fixtures"),
        db.get_container_client("predictions"),
        db.get_container_client("scores"),
        db.get_container_client("usage"),
    )


def get_queue_client() -> QueueClient:
    from azure.storage.queue import BinaryBase64EncodePolicy
    return QueueClient.from_connection_string(
        os.environ["AzureWebJobsStorage"],
        queue_name=os.environ.get("PREDICT_QUEUE_NAME", "predict-trigger"),
        message_encode_policy=BinaryBase64EncodePolicy(),
    )


def get_status_queue_clients() -> tuple[QueueClient, QueueClient]:
    conn = os.environ["AzureWebJobsStorage"]
    queue_name = os.environ.get("PREDICT_QUEUE_NAME", "predict-trigger")
    return (
        QueueClient.from_connection_string(conn, queue_name=queue_name),
        QueueClient.from_connection_string(conn, queue_name=f"{queue_name}-poison"),
    )


def get_ingest_queue_client() -> QueueClient:
    from azure.storage.queue import BinaryBase64EncodePolicy
    return QueueClient.from_connection_string(
        os.environ["AzureWebJobsStorage"],
        queue_name=os.environ.get("INGEST_QUEUE_NAME", "ingest-trigger"),
        message_encode_policy=BinaryBase64EncodePolicy(),
    )


def get_news_container() -> Any:
    cosmos = CosmosClient.from_connection_string(
        os.environ["CosmosDbConnectionString"],
        connection_verify=True,
    )
    db = cosmos.get_database_client(os.environ.get("COSMOS_DATABASE_NAME", "wc2026"))
    return db.get_container_client("news")


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------

def _handle_groups(teams_container: Any) -> func.HttpResponse:
    teams = query_items(teams_container, "SELECT * FROM c")
    by_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for t in teams:
        by_group[t.get("group", "?")].append(t)
    groups = [{"group": g, "teams": ts} for g, ts in sorted(by_group.items())]
    return _json_200({"groups": groups})


def _handle_predictions(predictions_container: Any) -> func.HttpResponse:
    docs = query_items(
        predictions_container,
        "SELECT * FROM c WHERE c.id = 'predictions-all'",
    )
    if not docs:
        return _json_404("No predictions available")
    doc = max(docs, key=lambda d: d.get("generatedAt", ""))
    if len(docs) > 1:
        logger.warning(
            "Found %d prediction docs for id='predictions-all' — returning newest (generatedAt=%s matchday=%s)",
            len(docs), doc.get("generatedAt"), doc.get("matchday"),
        )
    logger.info(
        "Serving prediction doc generatedAt=%s matchday=%s groups=%d",
        doc.get("generatedAt"), doc.get("matchday"), len(doc.get("groups", [])),
    )
    return _json_200(doc)


def _handle_fixtures(
    fixtures_container: Any, predictions_container: Any, matchday: int
) -> func.HttpResponse:
    try:
        docs = query_items(
            fixtures_container,
            "SELECT * FROM c WHERE c.matchday = @md",
            parameters=[{"name": "@md", "value": matchday}],
        )
    except Exception as e:
        logger.error("Error querying fixtures for matchday %s: %s", matchday, str(e), exc_info=True)
        return _json_404(f"Fixtures not available for matchday {matchday}")

    # Join predictions if available
    try:
        prediction_docs = query_items(
            predictions_container,
            "SELECT * FROM c WHERE c.id = 'predictions-all'",
        )
        if prediction_docs:
            pred_doc = max(prediction_docs, key=lambda d: d.get("generatedAt", ""))
            groups = pred_doc.get("groups", [])
            logger.info("Found predictions document with %d groups", len(groups))

            # Build lookup: (homeTeam, awayTeam) → {predictedHomeScore, predictedAwayScore}
            pred_lookup: dict[tuple[str, str], dict[str, Any]] = {}
            matches_for_md = 0
            for group in groups:
                for match in group.get("matches", []):
                    if match.get("matchday") == matchday:
                        matches_for_md += 1
                        key = (match.get("homeTeam", ""), match.get("awayTeam", ""))
                        pred_lookup[key] = {
                            "predictedHomeScore": match.get("predictedHomeScore"),
                            "predictedAwayScore": match.get("predictedAwayScore"),
                        }

            logger.info("Found %d prediction matches for matchday %d", matches_for_md, matchday)
            logger.debug("Prediction lookup keys: %s", list(pred_lookup.keys())[:5])

            # Merge predictions onto fixtures (deep copy to avoid mutating originals)
            docs_with_preds = []
            matched_count = 0
            for doc in docs:
                doc_copy = copy.deepcopy(doc)
                key = (doc_copy.get("homeTeam", ""), doc_copy.get("awayTeam", ""))
                if key in pred_lookup:
                    doc_copy["predictedHomeScore"] = pred_lookup[key]["predictedHomeScore"]
                    doc_copy["predictedAwayScore"] = pred_lookup[key]["predictedAwayScore"]
                    matched_count += 1
                    logger.debug("Matched prediction for %s vs %s", key[0], key[1])
                docs_with_preds.append(doc_copy)

            logger.info("Matched %d/%d fixtures with predictions for matchday %d", matched_count, len(docs), matchday)
            docs = docs_with_preds
        else:
            logger.warning("No predictions document found (expected id: 'predictions-all')")
    except Exception as e:
        logger.warning("Failed to join predictions for matchday %s: %s", matchday, e, exc_info=True)

    return _json_200({"matchday": matchday, "fixtures": docs})


def _handle_usage(usage_container: Any) -> func.HttpResponse:
    today = date.today().isoformat()
    this_month = today[:7]

    docs = query_items(usage_container, "SELECT * FROM c")

    by_provider: dict[str, dict[str, Any]] = {}
    for doc in docs:
        provider = doc.get("provider", "unknown")
        cfg = PROVIDER_LIMITS.get(provider, {})
        window = cfg.get("window", "day")
        doc_date: str = doc.get("date", "")

        is_current = (
            (window in ("day", "minute") and doc_date == today) or
            (window == "month" and doc_date.startswith(this_month))
        )
        if not is_current:
            continue

        if provider not in by_provider:
            by_provider[provider] = {
                "name": provider,
                "callCount": 0,
                "limit": cfg.get("limit"),
                "window": window,
            }

        entry = by_provider[provider]
        entry["callCount"] = entry.get("callCount", 0) + doc.get("callCount", 0)
        for extra_key in ("inputTokens", "outputTokens"):
            if extra_key in doc:
                entry[extra_key] = entry.get(extra_key, 0) + doc[extra_key]

    # Compute percentUsed for providers with a limit (skip minute-window — daily aggregate vs per-minute limit is not meaningful)
    for entry in by_provider.values():
        if entry.get("limit") and entry.get("window") != "minute":
            entry["percentUsed"] = round(entry["callCount"] / entry["limit"] * 100, 2)

    return _json_200({
        "asOf": datetime.now(timezone.utc).isoformat(),
        "providers": list(by_provider.values()),
    })


def _handle_fixtures_by_stage(fixtures_container: Any, stage: str) -> func.HttpResponse:
    try:
        docs = query_items(
            fixtures_container,
            "SELECT * FROM c WHERE c.stage = @stage",
            parameters=[{"name": "@stage", "value": stage}],
        )
    except Exception as e:
        logger.error("Error querying fixtures for stage %s: %s", stage, str(e), exc_info=True)
        return _json_404(f"Fixtures not available for stage {stage}")
    return _json_200({"stage": stage, "fixtures": docs})


def _handle_news(news_container: Any, team_name: str) -> func.HttpResponse:
    docs = query_items(
        news_container,
        "SELECT * FROM c WHERE c.teamName = @team ORDER BY c.date DESC OFFSET 0 LIMIT 1",
        parameters=[{"name": "@team", "value": team_name}],
    )
    if docs:
        doc = docs[0]
        return _json_200({
            "teamName": doc["teamName"],
            "snippets": doc.get("snippets", []),
            "date": doc.get("date"),
        })
    return _json_200({"teamName": team_name, "snippets": [], "date": None})


def _handle_accuracy(scores_container: Any) -> func.HttpResponse:
    docs = query_items(
        scores_container,
        "SELECT * FROM c ORDER BY c.matchday DESC OFFSET 0 LIMIT 1",
    )
    if not docs:
        return _json_404("No accuracy data available")
    return _json_200(docs[0])


def _handle_status(
    teams_container: Any,
    fixtures_container: Any,
    predictions_container: Any,
    queue_client: Any,
    poison_client: Any,
) -> func.HttpResponse:
    # Prediction metadata (lightweight — no groups payload)
    prediction_status: dict[str, Any] | None = None
    try:
        pred_docs = query_items(
            predictions_container,
            "SELECT c.id, c.generatedAt, c.matchday, c.groups FROM c WHERE c.id = 'predictions-all'",
        )
        if pred_docs:
            doc = max(pred_docs, key=lambda d: d.get("generatedAt", ""))
            prediction_status = {
                "generatedAt": doc.get("generatedAt"),
                "matchday": doc.get("matchday"),
                "groupCount": len(doc.get("groups", [])),
            }
    except Exception as e:
        logger.warning("status: failed to query predictions: %s", e)

    # Queue depths
    queue_status: dict[str, Any] | None = None
    try:
        props = queue_client.get_queue_properties()
        poison_props = poison_client.get_queue_properties()
        queue_status = {
            "approximateMessageCount": props.approximate_message_count,
            "poisonMessageCount": poison_props.approximate_message_count,
        }
    except Exception as e:
        logger.warning("status: failed to query queue: %s", e)

    # Team count
    teams_status: dict[str, Any] | None = None
    try:
        teams = query_items(teams_container, "SELECT c.id FROM c")
        teams_status = {"count": len(teams)}
    except Exception as e:
        logger.warning("status: failed to query teams: %s", e)

    # Fixture counts
    fixtures_status: dict[str, Any] | None = None
    try:
        fixtures = query_items(fixtures_container, "SELECT c.id, c.status FROM c")
        finished = sum(1 for f in fixtures if f.get("status") == "FT")
        fixtures_status = {"total": len(fixtures), "finished": finished}
    except Exception as e:
        logger.warning("status: failed to query fixtures: %s", e)

    return _json_200({
        "prediction": prediction_status,
        "queue": queue_status,
        "teams": teams_status,
        "fixtures": fixtures_status,
    })


def _ensure_cosmos_containers() -> tuple[Any, Any, Any, Any, Any]:
    """Ensure required Cosmos containers exist, create if missing."""
    cosmos = CosmosClient.from_connection_string(os.environ["CosmosDbConnectionString"])
    db = cosmos.get_database_client(os.environ.get("COSMOS_DATABASE_NAME", "wc2026"))

    containers_config = {
        "fixtures": "/matchday",
        "teams": "/group",
        "predictions": "/matchday",
        "scores": "/matchday",
        "usage": "/provider",
    }

    for container_name, partition_key in containers_config.items():
        try:
            container = db.get_container_client(container_name)
            container.read()
            logger.info("Container '%s' exists", container_name)
        except Exception as e:
            logger.info("Creating container '%s' with partition key '%s'", container_name, partition_key)
            try:
                db.create_container(
                    id=container_name,
                    partition_key=PartitionKey(path=partition_key),
                    offer_throughput=400,
                )
                logger.info("Container '%s' created successfully", container_name)
            except Exception as create_err:
                logger.warning("Could not create container '%s': %s", container_name, str(create_err))

    return (
        db.get_container_client("teams"),
        db.get_container_client("fixtures"),
        db.get_container_client("predictions"),
        db.get_container_client("scores"),
        db.get_container_client("usage"),
    )


def _handle_ingest(req: func.HttpRequest) -> func.HttpResponse:
    """Enqueue an ingest job and return 202 immediately."""
    import uuid
    queue = get_ingest_queue_client()
    correlation_id = str(uuid.uuid4())
    message = json.dumps({"correlationId": correlation_id}).encode()
    queue.send_message(message)
    logger.info("Enqueued ingest trigger: correlationId=%s", correlation_id)
    return func.HttpResponse(
        body=json.dumps({"status": "queued"}),
        status_code=202,
        mimetype="application/json",
    )


def _handle_predictions_generate(
    teams_container: Any,
    fixtures_container: Any,
    predictions_container: Any,
    usage_container: Any,
    req: func.HttpRequest,
) -> func.HttpResponse:
    """Generate predictions on-demand via Claude."""
    try:
        body = req.get_json()
        matchday = body.get("matchday", 1)
    except ValueError:
        matchday = 1

    if not isinstance(matchday, int) or matchday < 1 or matchday > 3:
        return func.HttpResponse(
            body=json.dumps({"error": "matchday must be an integer between 1 and 3"}),
            status_code=400,
            mimetype="application/json",
        )

    logger.info("Generating predictions for matchday %s on-demand", matchday)

    try:
        # Fetch teams and fixtures
        teams = query_items(teams_container, "SELECT * FROM c")
        fixtures = query_items(fixtures_container, "SELECT * FROM c")

        # Build prompt
        from fn_predict import _build_prompt, _parse_claude_response
        prompt = _build_prompt(teams=teams, fixtures=fixtures, news=None)

        # Call Claude with structured outputs
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        response = client.beta.messages.parse(
            model="claude-sonnet-4-5",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
            output_config={
                "format": {
                    "type": "json_schema",
                    "schema": PredictionsResponse.model_json_schema(),
                }
            },
            betas=["structured-outputs-2025-11-13"],
        )

        # Record usage (non-fatal; sync container requires sync call)
        from shared.usage_tracker import record_call_sync
        try:
            record_call_sync(usage_container, "anthropic",
                             inputTokens=response.usage.input_tokens,
                             outputTokens=response.usage.output_tokens)
        except Exception as exc:
            logger.warning("Failed to record anthropic usage: %s", exc)

        # Parse and store predictions (structured output returns pure JSON)
        raw_text = response.content[0].text  # type: ignore[union-attr]
        logger.info("Claude structured response: %d chars", len(raw_text))

        predictions = _parse_claude_response(raw_text)
        logger.info("Parsed %d groups from Claude response", len(predictions))

        now = datetime.now(timezone.utc).isoformat()
        prediction_doc = {
            "id": "predictions-all",
            "generatedAt": now,
            "groups": predictions,
        }
        predictions_container.upsert_item(prediction_doc)

        logger.info("Generated and stored %d group predictions", len(predictions))

        return _json_200({
            "status": "generated",
            "matchday": matchday,
            "groups": len(predictions),
            "message": "Predictions generated successfully",
            "claudeResponseLength": len(raw_text),
            "parsedGroups": len(predictions),
            "claudeResponseSample": raw_text[:300]  # First 300 chars for debugging
        })

    except Exception as e:
        logger.error("Error generating predictions: %s", str(e), exc_info=True)
        return func.HttpResponse(
            body=json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json",
        )


def _handle_predictions_trigger(
    queue_client: QueueClient, req: func.HttpRequest
) -> func.HttpResponse:
    try:
        body = req.get_json()
        matchday = body.get("matchday", 1)
    except ValueError:
        return func.HttpResponse(
            body=json.dumps({"error": "Invalid JSON"}),
            status_code=400,
            mimetype="application/json",
        )

    if not isinstance(matchday, int) or matchday < 1 or matchday > 3:
        return func.HttpResponse(
            body=json.dumps({"error": "matchday must be an integer between 1 and 3"}),
            status_code=400,
            mimetype="application/json",
        )

    import uuid
    correlation_id = str(uuid.uuid4())
    message = json.dumps({"matchday": matchday, "fixtureId": None, "correlationId": correlation_id}).encode()
    queue_client.send_message(message)
    logger.info("Enqueued prediction trigger: matchday=%s correlationId=%s", matchday, correlation_id)

    return _json_200({"status": "queued", "matchday": matchday})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _json_200(body: Any) -> func.HttpResponse:
    return func.HttpResponse(
        body=json.dumps(body),
        status_code=200,
        mimetype="application/json",
        headers={"Access-Control-Allow-Origin": "*"},
    )


def _json_404(message: str) -> func.HttpResponse:
    return func.HttpResponse(
        body=json.dumps({"error": message}),
        status_code=404,
        mimetype="application/json",
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main(req: func.HttpRequest) -> func.HttpResponse:
    route = req.route_params.get("route", "").strip("/")
    method = req.method
    logger.info("API request: %s %s", method, route)

    try:
        teams_container, fixtures_container, predictions_container, scores_container, usage_container = get_containers()
    except Exception as e:
        logger.error("Error getting containers: %s", str(e), exc_info=True)
        return func.HttpResponse(
            body=json.dumps({"error": "Service unavailable"}),
            status_code=503,
            mimetype="application/json",
        )

    try:
        if route == "ingest" and req.method == "POST":
            logger.info("Ingest request received")
            return _handle_ingest(req)

        if route == "groups":
            return _handle_groups(teams_container)

        if route == "predictions" and req.method == "GET":
            return _handle_predictions(predictions_container)

        if route == "predictions/generate" and req.method == "POST":
            return _handle_predictions_generate(
                teams_container,
                fixtures_container,
                predictions_container,
                usage_container,
                req,
            )

        if route == "predictions/trigger" and req.method == "POST":
            queue_client = get_queue_client()
            return _handle_predictions_trigger(queue_client, req)

        if route == "accuracy":
            return _handle_accuracy(scores_container)

        if route == "status":
            queue_client, poison_client = get_status_queue_clients()
            return _handle_status(
                teams_container, fixtures_container, predictions_container,
                queue_client, poison_client,
            )

        if route == "usage":
            return _handle_usage(usage_container)

        # fixtures/stage/<stage_name>
        m = re.fullmatch(r"fixtures/stage/([A-Z0-9_]+)", route)
        if m:
            return _handle_fixtures_by_stage(fixtures_container, m.group(1))

        # fixtures/<matchday>
        m = re.fullmatch(r"fixtures/(\d+)", route)
        if m:
            return _handle_fixtures(fixtures_container, predictions_container, int(m.group(1)))

        # news/<team>
        m = re.fullmatch(r"news/(.+)", route)
        if m:
            team_name = unquote(m.group(1))
            news_container = get_news_container()
            return _handle_news(news_container, team_name)

        return _json_404("Route not found")
    except Exception as e:
        logger.error("Error handling route %s: %s", route, str(e), exc_info=True)
        return func.HttpResponse(
            body=json.dumps({"error": "Internal server error"}),
            status_code=500,
            mimetype="application/json",
        )
