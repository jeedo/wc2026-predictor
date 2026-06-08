"""Tests for fn_ingest — queue trigger function."""
import json
from unittest.mock import AsyncMock, MagicMock, patch, call

import azure.functions as func
import pytest

from fn_ingest import main as ingest_main, _should_enqueue, _build_fixture_doc


def _queue_msg_mock():
    msg = MagicMock(spec=func.QueueMessage)
    msg.get_body.return_value = b"{}"
    return msg


def _async_iter(items):
    async def _gen():
        for item in items:
            yield item
    return _gen()


# ---------------------------------------------------------------------------
# _should_enqueue
# ---------------------------------------------------------------------------
def test_should_enqueue_when_transitions_to_finished():
    assert _should_enqueue(old_status="NS", new_status="FT") is True


def test_should_enqueue_false_when_already_finished():
    assert _should_enqueue(old_status="FT", new_status="FT") is False


def test_should_enqueue_false_when_not_finished():
    assert _should_enqueue(old_status="NS", new_status="1H") is False


def test_should_enqueue_true_on_first_insert_finished():
    assert _should_enqueue(old_status=None, new_status="FT") is True


# ---------------------------------------------------------------------------
# _build_fixture_doc
# ---------------------------------------------------------------------------
def test_build_fixture_doc_fields():
    raw = {
        "id": 101,
        "utcDate": "2026-06-12T15:00:00Z",
        "status": "FINISHED",
        "matchday": 1,
        "homeTeam": {"id": 1, "name": "Germany"},
        "awayTeam": {"id": 2, "name": "Mexico"},
        "score": {"fullTime": {"home": 2, "away": 0}},
    }
    doc = _build_fixture_doc(raw)
    assert doc["id"] == "fixture-101"
    assert doc["fixtureId"] == 101
    assert doc["matchday"] == 1
    assert doc["status"] == "FT"
    assert doc["homeScore"] == 2
    assert doc["awayScore"] == 0


# ---------------------------------------------------------------------------
# main — integration-style with mocked Azure SDK
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ingest_seeds_teams_on_first_run():
    """When teams container is empty, all fetched teams should be upserted."""
    timer = _queue_msg_mock()

    mock_teams_container = MagicMock()
    mock_teams_container.query_items = MagicMock(return_value=_async_iter([]))  # empty
    mock_teams_container.upsert_item = AsyncMock()

    mock_fixtures_container = MagicMock()
    mock_fixtures_container.query_items = MagicMock(return_value=_async_iter([]))
    mock_fixtures_container.read_item = AsyncMock(side_effect=Exception("not found"))
    mock_fixtures_container.upsert_item = AsyncMock()

    mock_queue = AsyncMock()

    fake_teams = [
        {"id": i, "name": f"Team{i}", "group": "A"}
        for i in range(1, 5)
    ]
    fake_fixtures: list = []

    with (
        patch("fn_ingest.get_containers", return_value=(mock_teams_container, mock_fixtures_container)),
        patch("fn_ingest.get_queue_client", return_value=mock_queue),
        patch("fn_ingest._get_football_data_api_key", return_value="test-key"),
        patch("fn_ingest.FootballDataClient", return_value=MagicMock()),
        patch("fn_ingest.fetch_teams_fd", AsyncMock(return_value=fake_teams)),
        patch("fn_ingest.fetch_matches_fd", AsyncMock(return_value=fake_fixtures)),
        patch("fn_ingest.fetch_groups_from_standings", AsyncMock(return_value={})),
    ):
        await ingest_main(timer)

    assert mock_teams_container.upsert_item.call_count == 4


@pytest.mark.asyncio
async def test_ingest_enqueues_on_finished_transition():
    """When a fixture transitions to FT, a queue message should be sent."""
    timer = _queue_msg_mock()

    mock_teams_container = MagicMock()
    mock_teams_container.query_items = MagicMock(return_value=_async_iter([1]))  # not empty

    mock_fixtures_container = MagicMock()
    mock_fixtures_container.read_item = AsyncMock(
        return_value={"id": "fixture-101", "status": "NS"}  # previously NS
    )
    mock_fixtures_container.upsert_item = AsyncMock()

    mock_queue = AsyncMock()
    mock_queue.send_message = AsyncMock()

    finished_fixture = {
        "id": 101,
        "utcDate": "2026-06-12T15:00:00Z",
        "status": "FINISHED",
        "matchday": 1,
        "homeTeam": {"id": 1, "name": "Germany"},
        "awayTeam": {"id": 2, "name": "Mexico"},
        "score": {"fullTime": {"home": 2, "away": 0}},
    }

    async def _fixtures_by_matchday(_api, _http, matchday):
        return [finished_fixture] if matchday == 1 else []

    with (
        patch("fn_ingest.get_containers", return_value=(mock_teams_container, mock_fixtures_container)),
        patch("fn_ingest.get_queue_client", return_value=mock_queue),
        patch("fn_ingest._get_football_data_api_key", return_value="test-key"),
        patch("fn_ingest.FootballDataClient", return_value=MagicMock()),
        patch("fn_ingest.fetch_teams_fd", AsyncMock(return_value=[])),
        patch("fn_ingest.fetch_matches_fd", side_effect=_fixtures_by_matchday),
        patch("fn_ingest.fetch_groups_from_standings", AsyncMock(return_value={})),
    ):
        await ingest_main(timer)

    mock_queue.send_message.assert_called_once()
    msg_payload = json.loads(mock_queue.send_message.call_args[0][0])
    assert msg_payload["matchday"] == 1
    assert msg_payload["fixtureId"] == 101


# ---------------------------------------------------------------------------
# Observability logs (issue #12 focus)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ingest_logs_start_and_completion(caplog):
    """fn_ingest logs trigger source, run_id, and a completion summary."""
    import logging
    msg = _queue_msg_mock()

    mock_teams_container = MagicMock()
    mock_teams_container.query_items = MagicMock(return_value=_async_iter([1]))
    mock_fixtures_container = MagicMock()
    mock_fixtures_container.query_items = MagicMock(return_value=_async_iter([]))
    mock_fixtures_container.read_item = AsyncMock(side_effect=Exception("not found"))
    mock_fixtures_container.upsert_item = AsyncMock()

    with (
        patch("fn_ingest.get_containers", return_value=(mock_teams_container, mock_fixtures_container)),
        patch("fn_ingest.get_queue_client", return_value=AsyncMock()),
        patch("fn_ingest._get_football_data_api_key", return_value="test-key"),
        patch("fn_ingest.FootballDataClient", return_value=MagicMock()),
        patch("fn_ingest.fetch_teams_fd", AsyncMock(return_value=[])),
        patch("fn_ingest.fetch_matches_fd", AsyncMock(return_value=[])),
        patch("fn_ingest.fetch_groups_from_standings", AsyncMock(return_value={})),
        caplog.at_level(logging.INFO, logger="fn_ingest"),
    ):
        await ingest_main(msg)

    messages = [r.message for r in caplog.records if r.levelno == logging.INFO]
    assert any("queue" in m.lower() or "starting" in m.lower() for m in messages), \
        f"Expected start log mentioning queue trigger, got: {messages}"
    assert any("complete" in m.lower() or "finish" in m.lower() or "done" in m.lower() for m in messages), \
        f"Expected completion summary log, got: {messages}"


@pytest.mark.asyncio
async def test_ingest_logs_enqueue_event(caplog):
    """fn_ingest logs when it enqueues a predict-trigger message (key audit event)."""
    import logging
    msg = _queue_msg_mock()

    mock_teams_container = MagicMock()
    mock_teams_container.query_items = MagicMock(return_value=_async_iter([1]))
    mock_fixtures_container = MagicMock()
    mock_fixtures_container.read_item = AsyncMock(return_value={"id": "fixture-101", "status": "NS"})
    mock_fixtures_container.upsert_item = AsyncMock()
    mock_queue = AsyncMock()
    mock_queue.send_message = AsyncMock()

    finished_fixture = {
        "id": 101, "utcDate": "2026-06-12T15:00:00Z", "status": "FINISHED",
        "matchday": 1,
        "homeTeam": {"id": 1, "name": "Germany"}, "awayTeam": {"id": 2, "name": "Mexico"},
        "score": {"fullTime": {"home": 2, "away": 0}},
    }

    async def _ft_stub(_api, _http, matchday):
        return [finished_fixture] if matchday == 1 else []

    with (
        patch("fn_ingest.get_containers", return_value=(mock_teams_container, mock_fixtures_container)),
        patch("fn_ingest.get_queue_client", return_value=mock_queue),
        patch("fn_ingest._get_football_data_api_key", return_value="test-key"),
        patch("fn_ingest.FootballDataClient", return_value=MagicMock()),
        patch("fn_ingest.fetch_teams_fd", AsyncMock(return_value=[])),
        patch("fn_ingest.fetch_matches_fd", side_effect=_ft_stub),
        patch("fn_ingest.fetch_groups_from_standings", AsyncMock(return_value={})),
        caplog.at_level(logging.INFO, logger="fn_ingest"),
    ):
        await ingest_main(msg)

    messages = [r.message for r in caplog.records]
    assert any("enqueue" in m.lower() or "predict" in m.lower() for m in messages), \
        f"Expected log mentioning predict queue enqueue, got: {messages}"
    assert any("matchday" in m.lower() and "1" in m for m in messages if "enqueue" in m.lower() or "predict" in m.lower()), \
        f"Expected enqueue log to include matchday, got: {messages}"


# ---------------------------------------------------------------------------
# fn_api POST /api/ingest — enqueue-and-return-202
# ---------------------------------------------------------------------------

def test_api_ingest_enqueues_and_returns_202():
    """POST /api/ingest should enqueue to ingest-trigger and return 202 immediately."""
    from fn_api import main as api_main
    from tests.test_fn_api import _make_request, _mock_containers

    req = _make_request(method="POST", url="http://localhost/api/ingest")
    containers = _mock_containers()
    mock_ingest_queue = MagicMock()

    with (
        patch("fn_api.get_containers", return_value=containers),
        patch("fn_api.get_ingest_queue_client", return_value=mock_ingest_queue),
    ):
        resp = api_main(req)

    assert resp.status_code == 202
    mock_ingest_queue.send_message.assert_called_once()


def test_api_ingest_logs_enqueue(caplog):
    """POST /api/ingest logs the enqueue action."""
    import logging
    from fn_api import main as api_main
    from tests.test_fn_api import _make_request, _mock_containers

    req = _make_request(method="POST", url="http://localhost/api/ingest")
    containers = _mock_containers()

    with (
        patch("fn_api.get_containers", return_value=containers),
        patch("fn_api.get_ingest_queue_client", return_value=MagicMock()),
        caplog.at_level(logging.INFO, logger="fn_api"),
    ):
        api_main(req)

    messages = [r.message for r in caplog.records if r.levelno == logging.INFO]
    assert any("ingest" in m.lower() and ("enqueue" in m.lower() or "queue" in m.lower()) for m in messages), \
        f"Expected INFO log about enqueueing ingest, got: {messages}"
