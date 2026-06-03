"""
Integration test — task 26.

Exercises the full data pipeline end-to-end without hitting Azure or any
external service:

  fn_ingest  →  in-memory queue  →  fn_predict  →  fn_api

Cosmos DB is replaced with InMemContainer (dict-backed).
API-Football and Claude are stubbed.
The queue uses asyncio.Queue to verify real message round-trips.
"""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import azure.functions as func

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# In-memory Cosmos DB container
# ---------------------------------------------------------------------------

class InMemContainer:
    def __init__(self):
        self._docs: dict = {}

    def query_items(self, query="", parameters=None, **kwargs):
        # Must return an async iterable for fn_ingest/fn_predict (async CosmosClient)
        # and a sync iterable for fn_api (sync CosmosClient via query_items_sync)
        items = list(self._docs.values())
        async def _aiter():
            for item in items:
                yield item
        # Return object that supports both sync iter (for query_items_sync) and async iter
        class _DualIterable:
            def __iter__(self_):
                return iter(items)
            def __aiter__(self_):
                return _aiter().__aiter__()
        return _DualIterable()

    async def upsert_item(self, body):
        self._docs[body["id"]] = body
        return body

    async def read_item(self, item, partition_key):
        if item not in self._docs:
            raise Exception(f"Not found: {item}")
        return self._docs[item]


# ---------------------------------------------------------------------------
# In-memory Queue that mimics the async Azure QueueClient surface we use
# ---------------------------------------------------------------------------

class InMemQueue:
    def __init__(self):
        self._q: asyncio.Queue = asyncio.Queue()

    async def send_message(self, content: str):
        await self._q.put(content)

    async def receive_one(self) -> str | None:
        try:
            return self._q.get_nowait()
        except asyncio.QueueEmpty:
            return None

    @property
    def size(self) -> int:
        return self._q.qsize()


# ---------------------------------------------------------------------------
# Stub data
# ---------------------------------------------------------------------------

STUB_TEAMS = [
    {"id": i, "name": f"Team{chr(64 + ((i-1)//4 + 1))}{((i-1) % 4) + 1}",
     "group": chr(64 + ((i-1)//4 + 1))}
    for i in range(1, 49)
]

STUB_FIXTURE_NS = {
    "id": 1001,
    "utcDate": "2026-06-12T15:00:00Z",
    "status": "SCHEDULED",
    "matchday": 1,
    "homeTeam": {"id": 1, "name": "TeamA1"},
    "awayTeam": {"id": 2, "name": "TeamA2"},
    "score": {"fullTime": {"home": None, "away": None}},
}

STUB_FIXTURE_FT = {
    "id": 1001,
    "utcDate": "2026-06-12T15:00:00Z",
    "status": "FINISHED",
    "matchday": 1,
    "homeTeam": {"id": 1, "name": "TeamA1"},
    "awayTeam": {"id": 2, "name": "TeamA2"},
    "score": {"fullTime": {"home": 2, "away": 0}},
}

CLAUDE_STUB = json.dumps({
    "predictions": [
        {"group": chr(65 + i), "winner": f"Team{chr(65+i)}1", "runnerUp": f"Team{chr(65+i)}2",
         "reasoning": "Based on available data."}
        for i in range(12)
    ]
})


# ---------------------------------------------------------------------------
# Test 1: fn_ingest seeds 48 teams and upserts the fixture
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ingest_seeds_teams_and_upserts_fixture():
    teams_db = InMemContainer()
    fixtures_db = InMemContainer()
    queue = InMemQueue()

    async def _fixtures_stub(_api, _http, matchday):
        return [STUB_FIXTURE_NS] if matchday == 1 else []

    with (
        patch("fn_ingest.get_containers", return_value=(teams_db, fixtures_db)),
        patch("fn_ingest.get_queue_client", return_value=queue),
        patch("fn_ingest._get_football_data_api_key", return_value="test-key"),
        patch("fn_ingest.FootballDataClient", return_value=MagicMock()),
        patch("fn_ingest.fetch_teams_fd", AsyncMock(return_value=STUB_TEAMS)),
        patch("fn_ingest.fetch_matches_fd", side_effect=_fixtures_stub),
    ):
        from fn_ingest import main as ingest_main
        await ingest_main(MagicMock(past_due=False))

    assert len(teams_db._docs) == 48, "All 48 teams should be seeded"
    assert "fixture-1001" in fixtures_db._docs, "Fixture should be upserted"
    assert queue.size == 0, "No queue message for a non-finished fixture"


# ---------------------------------------------------------------------------
# Test 2: fn_ingest enqueues when fixture transitions NS → FT
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ingest_enqueues_message_on_finish():
    teams_db = InMemContainer()
    teams_db._docs["placeholder"] = {"id": "placeholder"}   # non-empty → skip seed

    fixtures_db = InMemContainer()
    fixtures_db._docs["fixture-1001"] = {
        "id": "fixture-1001", "fixtureId": 1001, "matchday": 1, "status": "NS",
    }

    queue = InMemQueue()

    async def _ft_stub(_api, _http, matchday):
        return [STUB_FIXTURE_FT] if matchday == 1 else []

    with (
        patch("fn_ingest.get_containers", return_value=(teams_db, fixtures_db)),
        patch("fn_ingest.get_queue_client", return_value=queue),
        patch("fn_ingest._get_football_data_api_key", return_value="test-key"),
        patch("fn_ingest.FootballDataClient", return_value=MagicMock()),
        patch("fn_ingest.fetch_teams_fd", AsyncMock(return_value=[])),
        patch("fn_ingest.fetch_matches_fd", side_effect=_ft_stub),
    ):
        from fn_ingest import main as ingest_main
        await ingest_main(MagicMock(past_due=False))

    assert queue.size == 1, "Exactly one message should be enqueued"
    raw = await queue.receive_one()
    payload = json.loads(raw)
    assert payload["matchday"] == 1
    assert payload["fixtureId"] == 1001


# ---------------------------------------------------------------------------
# Test 3: fn_predict reads the queue payload and writes predictions
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_predict_writes_predictions_for_all_groups():
    teams_db = InMemContainer()
    for i in range(12):
        grp = chr(65 + i)
        for j in range(1, 5):
            doc = {"id": f"team-{i*4+j}", "name": f"Team{grp}{j}",
                   "group": grp, "fifaRanking": j, "recentForm": ["W"]}
            teams_db._docs[doc["id"]] = doc

    fixtures_db = InMemContainer()
    predictions_db = InMemContainer()
    scores_db = InMemContainer()

    mock_claude = MagicMock()
    mock_resp = MagicMock()
    mock_resp.content = [MagicMock(text=CLAUDE_STUB)]
    mock_claude.messages.create = AsyncMock(return_value=mock_resp)

    queue_msg = MagicMock()
    queue_msg.get_body.return_value = json.dumps(
        {"matchday": 1, "fixtureId": 1001}
    ).encode()

    with (
        patch("fn_predict.get_containers",
              return_value=(teams_db, fixtures_db, predictions_db, scores_db)),
        patch("fn_predict.get_anthropic_client", return_value=mock_claude),
    ):
        from fn_predict import main as predict_main
        await predict_main(queue_msg)

    assert "prediction-md1" in predictions_db._docs
    doc = predictions_db._docs["prediction-md1"]
    assert doc["matchday"] == 1
    assert len(doc["groups"]) == 12, "All 12 groups should be predicted"
    assert doc["groups"][0]["winner"] == "TeamA1"


# ---------------------------------------------------------------------------
# Test 4: fn_api surfaces the prediction doc written by fn_predict
# ---------------------------------------------------------------------------

def test_api_returns_prediction_written_by_predict():
    predictions_db = InMemContainer()
    predictions_db._docs["prediction-md1"] = {
        "id": "prediction-md1",
        "matchday": 1,
        "generatedAt": "2026-06-12T10:00:00Z",
        "groups": [
            {"group": "A", "winner": "TeamA1", "runnerUp": "TeamA2",
             "reasoning": "Strong form."},
        ],
    }

    req = func.HttpRequest(
        method="GET", url="http://localhost/api/predictions",
        headers={}, params={}, route_params={"route": "predictions"}, body=b"",
    )

    with patch("fn_api.get_containers",
               return_value=(InMemContainer(), InMemContainer(),
                             predictions_db, InMemContainer())):
        from fn_api import main as api_main
        resp = api_main(req)

    assert resp.status_code == 200
    body = json.loads(resp.get_body())
    assert body["matchday"] == 1
    assert body["groups"][0]["winner"] == "TeamA1"


# ---------------------------------------------------------------------------
# Test 5: full pipeline — ingest → queue → predict → api — end-to-end
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_full_pipeline_end_to_end():
    """Simulates one complete tournament cycle."""
    teams_db = InMemContainer()
    fixtures_db = InMemContainer()
    predictions_db = InMemContainer()
    scores_db = InMemContainer()
    queue = InMemQueue()

    # Seed + ingest NS fixture
    async def _fixtures_stub(_api, _http, matchday):
        return [STUB_FIXTURE_FT] if matchday == 1 else []

    with (
        patch("fn_ingest.get_containers", return_value=(teams_db, fixtures_db)),
        patch("fn_ingest.get_queue_client", return_value=queue),
        patch("fn_ingest._get_football_data_api_key", return_value="test-key"),
        patch("fn_ingest.FootballDataClient", return_value=MagicMock()),
        patch("fn_ingest.fetch_teams_fd", AsyncMock(return_value=STUB_TEAMS)),
        patch("fn_ingest.fetch_matches_fd", side_effect=_fixtures_stub),
    ):
        from fn_ingest import main as ingest_main
        await ingest_main(MagicMock(past_due=False))

    assert queue.size == 1, "ingest should have enqueued a predict message"

    # Drain queue → trigger fn_predict
    raw = await queue.receive_one()
    mock_claude = MagicMock()
    mock_resp = MagicMock()
    mock_resp.content = [MagicMock(text=CLAUDE_STUB)]
    mock_claude.messages.create = AsyncMock(return_value=mock_resp)

    queue_msg = MagicMock()
    queue_msg.get_body.return_value = raw.encode() if isinstance(raw, str) else raw

    with (
        patch("fn_predict.get_containers",
              return_value=(teams_db, fixtures_db, predictions_db, scores_db)),
        patch("fn_predict.get_anthropic_client", return_value=mock_claude),
    ):
        from fn_predict import main as predict_main
        await predict_main(queue_msg)

    assert "prediction-md1" in predictions_db._docs

    # Call fn_api and verify response
    req = func.HttpRequest(
        method="GET", url="http://localhost/api/predictions",
        headers={}, params={}, route_params={"route": "predictions"}, body=b"",
    )
    with patch("fn_api.get_containers",
               return_value=(teams_db, fixtures_db, predictions_db, scores_db)):
        from fn_api import main as api_main
        resp = api_main(req)

    assert resp.status_code == 200
    body = json.loads(resp.get_body())
    assert body["matchday"] == 1
    assert len(body["groups"]) == 12
