"""Tests for fn_api — HTTP Trigger endpoints."""
import json
from unittest.mock import MagicMock, patch

import pytest
import azure.functions as func

from fn_api import main as api_main


def _make_request(method: str = "GET", url: str = "http://localhost/api/groups", params: dict | None = None) -> func.HttpRequest:
    # Derive route param from URL so routing uses route_params["route"]
    path = url.split("?")[0]
    route = path.split("/api/", 1)[-1] if "/api/" in path else ""
    return func.HttpRequest(
        method=method,
        url=url,
        headers={},
        params=params or {},
        route_params={"route": route},
        body=b"",
    )


def _json_body(resp: func.HttpResponse) -> dict:
    return json.loads(resp.get_body())


# ---------------------------------------------------------------------------
# GET /groups
# ---------------------------------------------------------------------------

TEAM_DOCS = [
    {"id": "team-1", "name": "Germany", "group": "A", "fifaRanking": 15},
    {"id": "team-2", "name": "Mexico", "group": "A", "fifaRanking": 10},
    {"id": "team-3", "name": "Brazil", "group": "B", "fifaRanking": 1},
    {"id": "team-4", "name": "Argentina", "group": "B", "fifaRanking": 2},
]

PREDICTION_DOC = {
    "id": "prediction-md1",
    "matchday": 1,
    "generatedAt": "2026-06-12T10:00:00Z",
    "groups": [
        {"group": "A", "winner": "Germany", "runnerUp": "Mexico", "reasoning": "Strong"},
    ],
}

FIXTURE_DOCS = [
    {"id": "fixture-101", "matchday": 1, "homeTeam": "Germany", "awayTeam": "Mexico",
     "homeScore": 2, "awayScore": 0, "status": "FT", "kickoff": "2026-06-12T15:00:00Z"},
]

SCORE_DOC = {
    "id": "score-md1",
    "matchday": 1,
    "evaluatedAt": "2026-06-12T22:00:00Z",
    "score": 1,
    "totalGroups": 1,
    "groups": [
        {"group": "A", "correct": True, "predictedWinner": "Germany", "actualWinner": "Germany",
         "predictedRunnerUp": "Mexico", "actualRunnerUp": "Mexico"},
    ],
}


def _mock_containers(teams=None, fixtures=None, predictions=None, scores=None, usage=None):
    mc_teams = MagicMock()
    mc_teams.query_items = MagicMock(return_value=iter(teams or []))

    mc_fixtures = MagicMock()
    mc_fixtures.query_items = MagicMock(return_value=iter(fixtures or []))

    mc_predictions = MagicMock()
    mc_predictions.query_items = MagicMock(return_value=iter(predictions or []))

    mc_scores = MagicMock()
    mc_scores.query_items = MagicMock(return_value=iter(scores or []))

    mc_usage = MagicMock()
    mc_usage.query_items = MagicMock(return_value=iter(usage or []))

    return mc_teams, mc_fixtures, mc_predictions, mc_scores, mc_usage


def test_get_groups_returns_all_groups():
    req = _make_request(url="http://localhost/api/groups")
    containers = _mock_containers(teams=TEAM_DOCS)

    with patch("fn_api.get_containers", return_value=containers):
        resp = api_main(req)

    assert resp.status_code == 200
    body = _json_body(resp)
    assert "groups" in body
    assert len(body["groups"]) == 2  # A and B


def test_get_predictions_returns_latest():
    req = _make_request(url="http://localhost/api/predictions")
    containers = _mock_containers(predictions=[PREDICTION_DOC])

    with patch("fn_api.get_containers", return_value=containers):
        resp = api_main(req)

    assert resp.status_code == 200
    body = _json_body(resp)
    assert body["matchday"] == 1
    assert len(body["groups"]) == 1


def test_get_predictions_empty_returns_404():
    req = _make_request(url="http://localhost/api/predictions")
    containers = _mock_containers(predictions=[])

    with patch("fn_api.get_containers", return_value=containers):
        resp = api_main(req)

    assert resp.status_code == 404


def test_get_fixtures_by_matchday():
    req = _make_request(url="http://localhost/api/fixtures/1")
    containers = _mock_containers(fixtures=FIXTURE_DOCS)

    with patch("fn_api.get_containers", return_value=containers):
        resp = api_main(req)

    assert resp.status_code == 200
    body = _json_body(resp)
    assert "fixtures" in body
    assert body["fixtures"][0]["homeTeam"] == "Germany"


def test_get_accuracy_returns_score():
    req = _make_request(url="http://localhost/api/accuracy")
    containers = _mock_containers(scores=[SCORE_DOC])

    with patch("fn_api.get_containers", return_value=containers):
        resp = api_main(req)

    assert resp.status_code == 200
    body = _json_body(resp)
    assert body["score"] == 1
    assert body["totalGroups"] == 1


def test_get_accuracy_empty_returns_404():
    req = _make_request(url="http://localhost/api/accuracy")
    containers = _mock_containers(scores=[])

    with patch("fn_api.get_containers", return_value=containers):
        resp = api_main(req)

    assert resp.status_code == 404


def test_unknown_route_returns_404():
    req = _make_request(url="http://localhost/api/unknown")
    containers = _mock_containers()

    with patch("fn_api.get_containers", return_value=containers):
        resp = api_main(req)

    assert resp.status_code == 404


def test_response_shape_accuracy():
    """Verify accuracy response includes per-group breakdown."""
    req = _make_request(url="http://localhost/api/accuracy")
    containers = _mock_containers(scores=[SCORE_DOC])

    with patch("fn_api.get_containers", return_value=containers):
        resp = api_main(req)

    body = _json_body(resp)
    assert "groups" in body
    assert body["groups"][0]["correct"] is True


def test_response_shape_predictions():
    """Verify predictions response includes reasoning."""
    req = _make_request(url="http://localhost/api/predictions")
    containers = _mock_containers(predictions=[PREDICTION_DOC])

    with patch("fn_api.get_containers", return_value=containers):
        resp = api_main(req)

    body = _json_body(resp)
    assert body["groups"][0]["reasoning"] == "Strong"


# ---------------------------------------------------------------------------
# GET /usage
# ---------------------------------------------------------------------------

from datetime import date as _date

USAGE_DOCS = [
    {
        "id": f"usage-api-football-{_date.today().isoformat()}",
        "provider": "api-football",
        "date": _date.today().isoformat(),
        "callCount": 8,
    },
    {
        "id": f"usage-anthropic-{_date.today().isoformat()}",
        "provider": "anthropic",
        "date": _date.today().isoformat(),
        "callCount": 2,
        "inputTokens": 20000,
        "outputTokens": 1500,
    },
    {
        "id": f"usage-serper-{_date.today().isoformat()}",
        "provider": "serper",
        "date": _date.today().isoformat(),
        "callCount": 96,
    },
]


def test_get_usage_returns_providers():
    req = _make_request(url="http://localhost/api/usage")
    containers = _mock_containers(usage=USAGE_DOCS)

    with patch("fn_api.get_containers", return_value=containers):
        resp = api_main(req)

    assert resp.status_code == 200
    body = _json_body(resp)
    assert "providers" in body
    names = [p["name"] for p in body["providers"]]
    assert "api-football" in names
    assert "anthropic" in names


def test_get_usage_includes_limit_and_percent():
    req = _make_request(url="http://localhost/api/usage")
    containers = _mock_containers(usage=USAGE_DOCS)

    with patch("fn_api.get_containers", return_value=containers):
        resp = api_main(req)

    body = _json_body(resp)
    af = next(p for p in body["providers"] if p["name"] == "api-football")
    assert af["callCount"] == 8
    assert af["limit"] == 100
    assert af["percentUsed"] == pytest.approx(8.0)


def test_get_usage_returns_empty_providers_when_no_data():
    req = _make_request(url="http://localhost/api/usage")
    containers = _mock_containers(usage=[])

    with patch("fn_api.get_containers", return_value=containers):
        resp = api_main(req)

    assert resp.status_code == 200
    body = _json_body(resp)
    assert body["providers"] == []
