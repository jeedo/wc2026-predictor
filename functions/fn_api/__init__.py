"""fn_api — HTTP Trigger: serve groups, predictions, fixtures, and accuracy."""
from __future__ import annotations

import json
import logging
import os
import re
from collections import defaultdict
from typing import Any

import azure.functions as func
from azure.cosmos import CosmosClient  # sync client — fn_api is synchronous

from shared.cosmos import query_items_sync as query_items

logger = logging.getLogger(__name__)

_FIXTURE_ROUTE = re.compile(r"/api/fixtures/(\d+)$")


# ---------------------------------------------------------------------------
# Azure client factory (patched in tests)
# ---------------------------------------------------------------------------

def get_containers() -> tuple[Any, Any, Any, Any]:
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


def _handle_fixtures(fixtures_container: Any, matchday: int) -> func.HttpResponse:
    docs = query_items(
        fixtures_container,
        "SELECT * FROM c WHERE c.matchday = @md",
        parameters=[{"name": "@md", "value": matchday}],
    )
    return _json_200({"matchday": matchday, "fixtures": docs})


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
    teams_container, fixtures_container, predictions_container, scores_container = get_containers()
    path = req.url.split("?")[0]

    if path.endswith("/api/groups"):
        return _handle_groups(teams_container)

    if path.endswith("/api/predictions"):
        return _handle_predictions(predictions_container)

    if path.endswith("/api/accuracy"):
        return _handle_accuracy(scores_container)

    m = _FIXTURE_ROUTE.search(path)
    if m:
        return _handle_fixtures(fixtures_container, int(m.group(1)))

    return _json_404("Route not found")
