"""Tests for fn_predict — queue trigger function."""
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fn_predict import main as predict_main, _build_prompt, _parse_claude_response


def _async_iter(items):
    async def _gen():
        for item in items:
            yield item
    return _gen()


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


def test_build_prompt_includes_upcoming_fixtures():
    upcoming = [_make_fixture(1, "Germany", "Mexico", "NS")]
    teams = [_make_team("A", "Germany"), _make_team("A", "Mexico")]
    prompt = _build_prompt(teams=teams, fixtures=upcoming)
    assert "Germany" in prompt
    assert "Mexico" in prompt
    # Should mention upcoming matches so Claude can predict them
    assert "UPCOMING" in prompt.upper() or "SCHEDULED" in prompt.upper() or "FIXTURE" in prompt.upper()


def test_build_prompt_schema_includes_matches():
    teams = [_make_team("A", "Germany"), _make_team("A", "Mexico")]
    prompt = _build_prompt(teams=teams, fixtures=[])
    # Prompt schema must instruct Claude to return match-level predictions
    assert "matches" in prompt


def test_build_prompt_includes_fixture_teams():
    fixtures = [
        _make_fixture(1, "Germany", "Mexico", "NS"),
        _make_fixture(2, "Germany", "Poland", "NS"),
    ]
    teams = [_make_team("A", "Germany"), _make_team("A", "Mexico"), _make_team("A", "Poland")]
    prompt = _build_prompt(teams=teams, fixtures=fixtures)
    assert "Poland" in prompt


def test_build_prompt_includes_team_news():
    teams = [_make_team("A", "Germany"), _make_team("A", "Mexico")]
    news = {"Germany": ["Germany win warm-up 2-0", "Musiala fit after injury"]}
    prompt = _build_prompt(teams=teams, fixtures=[], news=news)
    assert "Germany win warm-up 2-0" in prompt
    assert "Musiala fit after injury" in prompt


def test_build_prompt_without_news_still_works():
    teams = [_make_team("A", "Germany")]
    prompt = _build_prompt(teams=teams, fixtures=[])
    assert "Germany" in prompt


def test_build_prompt_news_section_label():
    teams = [_make_team("A", "Germany")]
    news = {"Germany": ["Some headline"]}
    prompt = _build_prompt(teams=teams, fixtures=[], news=news)
    assert "NEWS" in prompt.upper() or "news" in prompt.lower()


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


def test_parse_response_preserves_matches():
    response = json.dumps({
        "predictions": [
            {
                "group": "A",
                "winner": "Germany",
                "runnerUp": "Mexico",
                "reasoning": "Strong",
                "matches": [
                    {"homeTeam": "Germany", "awayTeam": "Mexico", "matchday": 1,
                     "predictedHomeScore": 2, "predictedAwayScore": 1}
                ],
            }
        ]
    })
    result = _parse_claude_response(response)
    assert len(result) == 1
    assert "matches" in result[0]
    assert result[0]["matches"][0]["predictedHomeScore"] == 2


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
        return_value=_async_iter([_make_team("A", "Germany")])
    )
    mock_fixtures_container = MagicMock()
    mock_fixtures_container.query_items = MagicMock(return_value=_async_iter([]))
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
async def test_predict_fetches_news_when_serpa_key_set(queue_msg):
    mock_teams_container = MagicMock()
    mock_teams_container.query_items = MagicMock(
        return_value=_async_iter([_make_team("A", "Germany")])
    )
    mock_fixtures_container = MagicMock()
    mock_fixtures_container.query_items = MagicMock(return_value=_async_iter([]))
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
        patch("fn_predict.search_team_news", new=AsyncMock(return_value=["Germany news headline"])) as mock_search,
        patch.dict(os.environ, {"SERPA_API_KEY": "test-serpa-key"}),
    ):
        await predict_main(queue_msg)

    mock_search.assert_called()
    # Prompt sent to Claude should include the news headline
    prompt_sent = mock_claude.messages.create.call_args[1]["messages"][0]["content"]
    assert "Germany news headline" in prompt_sent


@pytest.mark.asyncio
async def test_predict_skips_news_when_no_serpa_key(queue_msg):
    mock_teams_container = MagicMock()
    mock_teams_container.query_items = MagicMock(
        return_value=_async_iter([_make_team("A", "Germany")])
    )
    mock_fixtures_container = MagicMock()
    mock_fixtures_container.query_items = MagicMock(return_value=_async_iter([]))
    mock_predictions_container = MagicMock()
    mock_predictions_container.upsert_item = AsyncMock()

    mock_claude = MagicMock()
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=CLAUDE_PREDICTIONS)]
    mock_claude.messages.create = AsyncMock(return_value=mock_msg)

    env_without_serpa = {k: v for k, v in os.environ.items() if k != "SERPA_API_KEY"}
    with (
        patch("fn_predict.get_containers", return_value=(
            mock_teams_container, mock_fixtures_container, mock_predictions_container, MagicMock()
        )),
        patch("fn_predict.get_anthropic_client", return_value=mock_claude),
        patch("fn_predict.search_team_news", new=AsyncMock()) as mock_search,
        patch.dict(os.environ, env_without_serpa, clear=True),
    ):
        await predict_main(queue_msg)

    mock_search.assert_not_called()


@pytest.mark.asyncio
async def test_predict_overwrites_on_second_call(queue_msg):
    """Second call with same matchday should overwrite (idempotent)."""
    mock_teams_container = MagicMock()
    mock_teams_container.query_items = MagicMock(
        return_value=_async_iter([_make_team("A", "Germany")])
    )
    mock_fixtures_container = MagicMock()
    mock_fixtures_container.query_items = MagicMock(return_value=_async_iter([]))
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
