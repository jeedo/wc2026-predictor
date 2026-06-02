"""Tests for fn_predict — queue trigger function."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fn_predict import main as predict_main, _build_prompt, _parse_claude_response


# ---------------------------------------------------------------------------
# _build_prompt
# ---------------------------------------------------------------------------

def _make_team(group: str, name: str, rank: int = 1, points: int = 0) -> dict:
    return {
        "id": f"team-{name}",
        "name": name,
        "group": group,
        "fifaRanking": rank,
        "recentForm": ["W", "D", "L"],
    }


def _make_fixture(matchday: int, home: str, away: str, status: str = "FT", hg: int = 1, ag: int = 0) -> dict:
    return {
        "matchday": matchday,
        "homeTeam": home,
        "awayTeam": away,
        "homeScore": hg,
        "awayScore": ag,
        "status": status,
    }


def test_build_prompt_includes_all_groups():
    teams = [_make_team(chr(65 + i), f"Team{i}A") for i in range(12)]
    teams += [_make_team(chr(65 + i), f"Team{i}B") for i in range(12)]
    prompt = _build_prompt(teams=teams, fixtures=[])
    for letter in "ABCDEFGHIJKL":
        assert letter in prompt


def test_build_prompt_includes_team_names():
    teams = [_make_team("A", "Germany"), _make_team("A", "Mexico")]
    prompt = _build_prompt(teams=teams, fixtures=[])
    assert "Germany" in prompt
    assert "Mexico" in prompt


def test_build_prompt_includes_completed_results():
    fixtures = [_make_fixture(1, "Germany", "Mexico", "FT", 2, 0)]
    teams = [_make_team("A", "Germany"), _make_team("A", "Mexico")]
    prompt = _build_prompt(teams=teams, fixtures=fixtures)
    assert "Germany" in prompt
    assert "2" in prompt


# ---------------------------------------------------------------------------
# _parse_claude_response
# ---------------------------------------------------------------------------

VALID_RESPONSE = json.dumps({
    "predictions": [
        {"group": "A", "winner": "Germany", "runnerUp": "Mexico", "reasoning": "Strong form"}
    ]
})


def test_parse_valid_response():
    result = _parse_claude_response(VALID_RESPONSE)
    assert len(result) == 1
    assert result[0]["group"] == "A"
    assert result[0]["winner"] == "Germany"


def test_parse_malformed_response_returns_empty():
    result = _parse_claude_response("not json at all")
    assert result == []


def test_parse_missing_predictions_key_returns_empty():
    result = _parse_claude_response('{"wrong_key": []}')
    assert result == []


# ---------------------------------------------------------------------------
# main — idempotent write
# ---------------------------------------------------------------------------

@pytest.fixture
def queue_msg():
    msg = MagicMock()
    msg.get_body.return_value = json.dumps({"matchday": 1, "fixtureId": 101}).encode()
    return msg


CLAUDE_PREDICTIONS = json.dumps({
    "predictions": [
        {"group": "A", "winner": "Germany", "runnerUp": "Mexico", "reasoning": "..."}
    ]
})


@pytest.mark.asyncio
async def test_predict_writes_prediction_doc(queue_msg):
    mock_teams_container = MagicMock()
    mock_teams_container.query_items = MagicMock(
        return_value=iter([_make_team("A", "Germany")])
    )
    mock_fixtures_container = MagicMock()
    mock_fixtures_container.query_items = MagicMock(return_value=iter([]))
    mock_predictions_container = MagicMock()
    mock_predictions_container.upsert_item = AsyncMock()

    mock_claude = MagicMock()
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=CLAUDE_PREDICTIONS)]
    mock_claude.messages.create = AsyncMock(return_value=mock_msg)

    with (
        patch("fn_predict.get_containers", return_value=(
            mock_teams_container, mock_fixtures_container, mock_predictions_container, MagicMock()
        )),
        patch("fn_predict.get_anthropic_client", return_value=mock_claude),
    ):
        await predict_main(queue_msg)

    mock_predictions_container.upsert_item.assert_called_once()
    doc = mock_predictions_container.upsert_item.call_args[1]["body"]
    assert doc["matchday"] == 1
    assert len(doc["groups"]) == 1


@pytest.mark.asyncio
async def test_predict_overwrites_on_second_call(queue_msg):
    """Second call with same matchday should overwrite (idempotent)."""
    mock_teams_container = MagicMock()
    mock_teams_container.query_items = MagicMock(
        return_value=iter([_make_team("A", "Germany")])
    )
    mock_fixtures_container = MagicMock()
    mock_fixtures_container.query_items = MagicMock(return_value=iter([]))
    mock_predictions_container = MagicMock()
    mock_predictions_container.upsert_item = AsyncMock()

    mock_claude = MagicMock()
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=CLAUDE_PREDICTIONS)]
    mock_claude.messages.create = AsyncMock(return_value=mock_msg)

    with (
        patch("fn_predict.get_containers", return_value=(
            mock_teams_container, mock_fixtures_container, mock_predictions_container, MagicMock()
        )),
        patch("fn_predict.get_anthropic_client", return_value=mock_claude),
    ):
        await predict_main(queue_msg)
        await predict_main(queue_msg)

    # upsert called twice — both on the same doc id (idempotent via Cosmos upsert)
    assert mock_predictions_container.upsert_item.call_count == 2
    calls = mock_predictions_container.upsert_item.call_args_list
    assert calls[0][1]["body"]["id"] == calls[1][1]["body"]["id"]
