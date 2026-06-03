"""fn_api — HTTP Trigger: serve groups, predictions, fixtures, and accuracy."""
from __future__ import annotations

import copy
import json
import logging
import os
import re
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any

import azure.functions as func
from azure.cosmos import CosmosClient  # sync client — fn_api is synchronous
from azure.storage.queue import QueueClient  # DEBUG: test if this import causes the issue

from shared.cosmos import query_items_sync as query_items
from shared.usage_tracker import PROVIDER_LIMITS

logger = logging.getLogger(__name__)

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
        "SELECT * FROM c ORDER BY c.matchday DESC OFFSET 0 LIMIT 1",
    )
    if not docs:
        return _json_404("No predictions available")
    return _json_200(docs[0])


def _handle_fixtures(
    fixtures_container: Any, predictions_container: Any, matchday: int
) -> func.HttpResponse:
    docs = query_items(
        fixtures_container,
        "SELECT * FROM c WHERE c.matchday = @md",
        parameters=[{"name": "@md", "value": matchday}],
    )

    # Join predictions if available
    try:
        prediction_docs = query_items(
            predictions_container,
            "SELECT * FROM c WHERE c.id = @id",
            parameters=[{"name": "@id", "value": f"prediction-md{matchday}"}],
        )
        if prediction_docs:
            pred_doc = prediction_docs[0]
            # Build lookup: (homeTeam, awayTeam) → {predictedHomeScore, predictedAwayScore}
            pred_lookup: dict[tuple[str, str], dict[str, Any]] = {}
            for group in pred_doc.get("groups", []):
                for match in group.get("matches", []):
                    if match.get("matchday") == matchday:
                        key = (match.get("homeTeam", ""), match.get("awayTeam", ""))
                        pred_lookup[key] = {
                            "predictedHomeScore": match.get("predictedHomeScore"),
                            "predictedAwayScore": match.get("predictedAwayScore"),
                        }

            # Merge predictions onto fixtures (deep copy to avoid mutating originals)
            docs_with_preds = []
            for doc in docs:
                doc_copy = copy.deepcopy(doc)
                key = (doc_copy.get("homeTeam", ""), doc_copy.get("awayTeam", ""))
                if key in pred_lookup:
                    doc_copy["predictedHomeScore"] = pred_lookup[key]["predictedHomeScore"]
                    doc_copy["predictedAwayScore"] = pred_lookup[key]["predictedAwayScore"]
                docs_with_preds.append(doc_copy)
            docs = docs_with_preds
    except Exception as e:
        logger.warning("Failed to join predictions for matchday %s: %s", matchday, e)

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
            (window == "day" and doc_date == today) or
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

    # Compute percentUsed for providers with a limit
    for entry in by_provider.values():
        if entry.get("limit"):
            entry["percentUsed"] = round(entry["callCount"] / entry["limit"] * 100, 2)

    return _json_200({
        "asOf": datetime.now(timezone.utc).isoformat(),
        "providers": list(by_provider.values()),
    })


def _handle_accuracy(scores_container: Any) -> func.HttpResponse:
    docs = query_items(
        scores_container,
        "SELECT * FROM c ORDER BY c.matchday DESC OFFSET 0 LIMIT 1",
    )
    if not docs:
        return _json_404("No accuracy data available")
    return _json_200(docs[0])


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
    teams_container, fixtures_container, predictions_container, scores_container, usage_container = get_containers()

    # Use route_params (populated by the {*route} wildcard) for reliable routing
    route = req.route_params.get("route", "").strip("/")

    if route == "groups":
        return _handle_groups(teams_container)

    if route == "predictions":
        return _handle_predictions(predictions_container)

    if route == "accuracy":
        return _handle_accuracy(scores_container)

    if route == "usage":
        return _handle_usage(usage_container)

    # fixtures/<matchday>
    m = re.fullmatch(r"fixtures/(\d+)", route)
    if m:
        return _handle_fixtures(fixtures_container, predictions_container, int(m.group(1)))

    return _json_404("Route not found")
