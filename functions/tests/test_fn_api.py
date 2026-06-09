"""Tests for fn_api — HTTP Trigger endpoints."""
import json
from unittest.mock import MagicMock, patch

import pytest
import azure.functions as func

from fn_api import main as api_main


def _make_request(method: str = "GET", url: str = "http://localhost/api/groups", params: dict | None = None, body: bytes | None = None) -> func.HttpRequest:
    # Derive route param from URL so routing uses route_params["route"]
    path = url.split("?")[0]
    route = path.split("/api/", 1)[-1] if "/api/" in path else ""
    return func.HttpRequest(
        method=method,
        url=url,
        headers={},
        params=params or {},
        route_params={"route": route},
        body=body or b"",
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
        {
            "group": "A",
            "winner": "Germany",
            "runnerUp": "Mexico",
            "confidence": "high",
            "reasoning": "Strong",
            "matches": [
                {"homeTeam": "Germany", "awayTeam": "Mexico", "matchday": 1, "predictedHomeScore": 2, "predictedAwayScore": 0, "confidence": "high"},
            ],
        },
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
    containers = _mock_containers(fixtures=FIXTURE_DOCS, predictions=[PREDICTION_DOC])

    with patch("fn_api.get_containers", return_value=containers):
        resp = api_main(req)

    assert resp.status_code == 200
    body = _json_body(resp)
    assert "fixtures" in body
    assert body["fixtures"][0]["homeTeam"] == "Germany"
    # Verify predictions were joined
    assert body["fixtures"][0]["predictedHomeScore"] == 2
    assert body["fixtures"][0]["predictedAwayScore"] == 0


def test_get_fixtures_without_predictions():
    """Fixtures without predictions should still be returned."""
    req = _make_request(url="http://localhost/api/fixtures/1")
    containers = _mock_containers(fixtures=FIXTURE_DOCS, predictions=[])

    with patch("fn_api.get_containers", return_value=containers):
        resp = api_main(req)

    assert resp.status_code == 200
    body = _json_body(resp)
    assert "fixtures" in body
    assert body["fixtures"][0]["homeTeam"] == "Germany"
    # Predicted scores should not be present
    assert "predictedHomeScore" not in body["fixtures"][0]
    assert "predictedAwayScore" not in body["fixtures"][0]


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


def test_trigger_predictions_enqueues_message():
    req = _make_request(
        method="POST",
        url="http://localhost/api/predictions/trigger",
        params={"route": "predictions/trigger"},
        body=json.dumps({"matchday": 1}).encode("utf-8"),
    )

    mock_queue = MagicMock()
    containers = _mock_containers()

    with patch("fn_api.get_containers", return_value=containers):
        with patch("fn_api.get_queue_client", return_value=mock_queue):
            resp = api_main(req)

    assert resp.status_code == 200
    body = _json_body(resp)
    assert body["status"] == "queued"
    assert body["matchday"] == 1
    mock_queue.send_message.assert_called_once()


def test_trigger_predictions_defaults_to_matchday_1():
    req = _make_request(
        method="POST",
        url="http://localhost/api/predictions/trigger",
        params={"route": "predictions/trigger"},
        body=b"{}",
    )

    mock_queue = MagicMock()
    containers = _mock_containers()

    with patch("fn_api.get_containers", return_value=containers):
        with patch("fn_api.get_queue_client", return_value=mock_queue):
            resp = api_main(req)

    assert resp.status_code == 200
    body = _json_body(resp)
    assert body["matchday"] == 1


def test_trigger_predictions_rejects_invalid_matchday():
    req = _make_request(
        method="POST",
        url="http://localhost/api/predictions/trigger",
        params={"route": "predictions/trigger"},
        body=json.dumps({"matchday": -1}).encode("utf-8"),
    )

    mock_queue = MagicMock()
    containers = _mock_containers()

    with patch("fn_api.get_containers", return_value=containers):
        with patch("fn_api.get_queue_client", return_value=mock_queue):
            resp = api_main(req)

    assert resp.status_code == 400
    body = _json_body(resp)
    assert "error" in body
    mock_queue.send_message.assert_not_called()


# ---------------------------------------------------------------------------
# GET /api/status (issue #24)
# ---------------------------------------------------------------------------

def _make_queue_props(count: int = 0) -> MagicMock:
    props = MagicMock()
    props.approximate_message_count = count
    return props


def test_status_returns_200():
    req = _make_request(url="http://localhost/api/status")
    containers = _mock_containers(
        teams=TEAM_DOCS,
        predictions=[PREDICTION_DOC],
        fixtures=FIXTURE_DOCS,
    )
    mock_queue = MagicMock()
    mock_queue.get_queue_properties.return_value = _make_queue_props(0)
    mock_poison = MagicMock()
    mock_poison.get_queue_properties.return_value = _make_queue_props(0)

    with patch("fn_api.get_containers", return_value=containers):
        with patch("fn_api.get_status_queue_clients", return_value=(mock_queue, mock_poison)):
            resp = api_main(req)

    assert resp.status_code == 200
    body = _json_body(resp)
    assert "prediction" in body
    assert "queue" in body
    assert "teams" in body
    assert "fixtures" in body


def test_status_prediction_metadata():
    req = _make_request(url="http://localhost/api/status")
    containers = _mock_containers(predictions=[PREDICTION_DOC])
    mock_queue = MagicMock()
    mock_queue.get_queue_properties.return_value = _make_queue_props(0)
    mock_poison = MagicMock()
    mock_poison.get_queue_properties.return_value = _make_queue_props(0)

    with patch("fn_api.get_containers", return_value=containers):
        with patch("fn_api.get_status_queue_clients", return_value=(mock_queue, mock_poison)):
            resp = api_main(req)

    body = _json_body(resp)
    assert body["prediction"]["generatedAt"] == PREDICTION_DOC["generatedAt"]
    assert body["prediction"]["matchday"] == PREDICTION_DOC["matchday"]
    assert body["prediction"]["groupCount"] == len(PREDICTION_DOC["groups"])


def test_status_queue_message_counts():
    req = _make_request(url="http://localhost/api/status")
    containers = _mock_containers()
    mock_queue = MagicMock()
    mock_queue.get_queue_properties.return_value = _make_queue_props(3)
    mock_poison = MagicMock()
    mock_poison.get_queue_properties.return_value = _make_queue_props(1)

    with patch("fn_api.get_containers", return_value=containers):
        with patch("fn_api.get_status_queue_clients", return_value=(mock_queue, mock_poison)):
            resp = api_main(req)

    body = _json_body(resp)
    assert body["queue"]["approximateMessageCount"] == 3
    assert body["queue"]["poisonMessageCount"] == 1


def test_status_team_and_fixture_counts():
    req = _make_request(url="http://localhost/api/status")
    finished = {**FIXTURE_DOCS[0], "status": "FT"}
    scheduled = {**FIXTURE_DOCS[0], "id": "fixture-102", "status": "NS"}
    containers = _mock_containers(teams=TEAM_DOCS, fixtures=[finished, scheduled])
    mock_queue = MagicMock()
    mock_queue.get_queue_properties.return_value = _make_queue_props(0)
    mock_poison = MagicMock()
    mock_poison.get_queue_properties.return_value = _make_queue_props(0)

    with patch("fn_api.get_containers", return_value=containers):
        with patch("fn_api.get_status_queue_clients", return_value=(mock_queue, mock_poison)):
            resp = api_main(req)

    body = _json_body(resp)
    assert body["teams"]["count"] == len(TEAM_DOCS)
    assert body["fixtures"]["total"] == 2
    assert body["fixtures"]["finished"] == 1


def test_status_degrades_gracefully_on_queue_error():
    """A queue error should not fail the whole status response."""
    req = _make_request(url="http://localhost/api/status")
    containers = _mock_containers(teams=TEAM_DOCS)
    mock_queue = MagicMock()
    mock_queue.get_queue_properties.side_effect = Exception("queue unavailable")
    mock_poison = MagicMock()
    mock_poison.get_queue_properties.side_effect = Exception("queue unavailable")

    with patch("fn_api.get_containers", return_value=containers):
        with patch("fn_api.get_status_queue_clients", return_value=(mock_queue, mock_poison)):
            resp = api_main(req)

    assert resp.status_code == 200
    body = _json_body(resp)
    assert body["queue"] is None


def test_status_no_prediction_returns_null_prediction():
    req = _make_request(url="http://localhost/api/status")
    containers = _mock_containers(predictions=[])
    mock_queue = MagicMock()
    mock_queue.get_queue_properties.return_value = _make_queue_props(0)
    mock_poison = MagicMock()
    mock_poison.get_queue_properties.return_value = _make_queue_props(0)

    with patch("fn_api.get_containers", return_value=containers):
        with patch("fn_api.get_status_queue_clients", return_value=(mock_queue, mock_poison)):
            resp = api_main(req)

    assert resp.status_code == 200
    body = _json_body(resp)
    assert body["prediction"] is None


# ---------------------------------------------------------------------------
# Observability / logging (issue #23)
# ---------------------------------------------------------------------------

def test_get_predictions_returns_newest_when_multiple_docs(caplog):
    """When multiple predictions-all docs exist (different Cosmos partitions),
    the newest by generatedAt is returned and a WARNING is logged."""
    old_doc = {**PREDICTION_DOC, "generatedAt": "2026-06-04T20:56:46Z", "matchday": None}
    new_doc = {**PREDICTION_DOC, "generatedAt": "2026-06-08T04:13:32Z", "matchday": 1}

    req = _make_request(url="http://localhost/api/predictions")
    containers = _mock_containers(predictions=[old_doc, new_doc])

    import logging
    with patch("fn_api.get_containers", return_value=containers):
        with caplog.at_level(logging.WARNING, logger="fn_api"):
            resp = api_main(req)

    assert resp.status_code == 200
    body = _json_body(resp)
    assert body["generatedAt"] == "2026-06-08T04:13:32Z"
    assert any("2" in r.message and "prediction" in r.message.lower() for r in caplog.records if r.levelno == logging.WARNING), \
        "Expected a WARNING log mentioning multiple prediction docs"


def test_get_predictions_logs_served_doc(caplog):
    """fn_api logs which prediction doc it's serving at INFO level."""
    req = _make_request(url="http://localhost/api/predictions")
    containers = _mock_containers(predictions=[PREDICTION_DOC])

    import logging
    with patch("fn_api.get_containers", return_value=containers):
        with caplog.at_level(logging.INFO, logger="fn_api"):
            resp = api_main(req)

    assert resp.status_code == 200
    assert any("prediction" in r.message.lower() and r.levelno == logging.INFO for r in caplog.records), \
        "Expected an INFO log about the prediction doc being served"


def test_trigger_logs_enqueued_message(caplog):
    """fn_api logs the message payload when enqueuing a prediction trigger."""
    req = _make_request(
        method="POST",
        url="http://localhost/api/predictions/trigger",
        params={"route": "predictions/trigger"},
        body=json.dumps({"matchday": 2}).encode("utf-8"),
    )
    mock_queue = MagicMock()
    containers = _mock_containers()

    import logging
    with patch("fn_api.get_containers", return_value=containers):
        with patch("fn_api.get_queue_client", return_value=mock_queue):
            with caplog.at_level(logging.INFO, logger="fn_api"):
                api_main(req)

    assert any("matchday" in r.message and "2" in r.message for r in caplog.records), \
        "Expected an INFO log containing the matchday from the enqueued message"




def test_ingest_message_contains_correlation_id():
    """POST /api/ingest enqueues a message containing a correlationId."""
    req = _make_request(method="POST", url="http://localhost/api/ingest")
    mock_queue = MagicMock()
    containers = _mock_containers()

    with patch("fn_api.get_containers", return_value=containers):
        with patch("fn_api.get_ingest_queue_client", return_value=mock_queue):
            api_main(req)

    msg = json.loads(mock_queue.send_message.call_args[0][0])
    assert "correlationId" in msg, "ingest queue message must include correlationId"
    assert len(msg["correlationId"]) == 36, "correlationId should be a UUID"


def test_predictions_trigger_message_contains_correlation_id():
    """POST /api/predictions/trigger enqueues a message containing a correlationId."""
    req = _make_request(
        method="POST",
        url="http://localhost/api/predictions/trigger",
        body=json.dumps({"matchday": 1}).encode(),
    )
    mock_queue = MagicMock()
    containers = _mock_containers()

    with patch("fn_api.get_containers", return_value=containers):
        with patch("fn_api.get_queue_client", return_value=mock_queue):
            api_main(req)

    msg = json.loads(mock_queue.send_message.call_args[0][0])
    assert "correlationId" in msg, "predict-trigger message must include correlationId"
    assert len(msg["correlationId"]) == 36, "correlationId should be a UUID"


def test_ingest_logs_correlation_id(caplog):
    """POST /api/ingest logs the correlationId it generates."""
    import logging
    req = _make_request(method="POST", url="http://localhost/api/ingest")
    containers = _mock_containers()

    with patch("fn_api.get_containers", return_value=containers):
        with patch("fn_api.get_ingest_queue_client", return_value=MagicMock()):
            with caplog.at_level(logging.INFO, logger="fn_api"):
                api_main(req)

    assert any("correlationId" in r.message for r in caplog.records), \
        "Expected INFO log containing correlationId"


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
