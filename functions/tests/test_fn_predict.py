"""Tests for fn_predict — queue trigger function."""
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fn_predict import _main_async, _build_prompt, _parse_claude_response, _fetch_news_parallel


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
    assert "UPCOMING" in prompt.upper() or "SCHEDULED" in prompt.upper() or "FIXTURE" in prompt.upper()


def test_build_prompt_schema_includes_matches():
    teams = [_make_team("A", "Germany"), _make_team("A", "Mexico")]
    prompt = _build_prompt(teams=teams, fixtures=[])
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


def _group_of_fixture_in_prompt(prompt: str, fixture_substring: str) -> str | None:
    """Return the group letter of the most recent standalone 'Group X:' heading
    before the line containing fixture_substring. Returns None if not found."""
    import re
    current_group = None
    for line in prompt.split("\n"):
        m = re.match(r"^Group ([A-Z]):\s*$", line.strip())
        if m:
            current_group = m.group(1)
        if fixture_substring in line:
            return current_group
    return None


def test_build_prompt_fixtures_grouped_by_group():
    """Upcoming fixtures must appear under their group's detail section.

    Reproduces issue #19: Netherlands (Group F) vs Sweden (Group F) was
    appearing in Group E predictions because _build_prompt listed all upcoming
    fixtures flat and Claude had to guess the group — getting it wrong.

    Groups G+ are included so the flat fixture section (if still present) falls
    under Group G, making the assertion fail on unpatched code.
    """
    teams = [
        _make_team("E", "Germany"), _make_team("E", "Ecuador"),
        _make_team("E", "Ivory Coast"), _make_team("E", "Curaçao"),
        _make_team("F", "Netherlands"), _make_team("F", "Sweden"),
        _make_team("F", "Japan"), _make_team("F", "Tunisia"),
        _make_team("G", "Spain"), _make_team("G", "Morocco"),  # group after F
    ]
    fixtures = [
        _make_fixture(2, "Netherlands", "Sweden", "NS"),
        _make_fixture(2, "Germany", "Ivory Coast", "NS"),
    ]
    prompt = _build_prompt(teams=teams, fixtures=fixtures)

    assert _group_of_fixture_in_prompt(prompt, "Netherlands vs Sweden") == "F", (
        "Netherlands vs Sweden must appear under the Group F detail section"
    )
    assert _group_of_fixture_in_prompt(prompt, "Germany vs Ivory Coast") == "E", (
        "Germany vs Ivory Coast must appear under the Group E detail section"
    )


def test_build_prompt_completed_results_grouped_by_group():
    """Completed results must also appear under their group's detail section."""
    teams = [
        _make_team("E", "Germany"), _make_team("E", "Ecuador"),
        _make_team("F", "Netherlands"), _make_team("F", "Sweden"),
        _make_team("G", "Spain"), _make_team("G", "Morocco"),
    ]
    fixtures = [
        _make_fixture(1, "Netherlands", "Sweden", "FT", 2, 1),
        _make_fixture(1, "Germany", "Ecuador", "FT", 3, 0),
    ]
    prompt = _build_prompt(teams=teams, fixtures=fixtures)

    assert _group_of_fixture_in_prompt(prompt, "Netherlands 2–1") == "F", (
        "Netherlands result must appear under the Group F detail section"
    )
    assert _group_of_fixture_in_prompt(prompt, "Germany 3") == "E", (
        "Germany result must appear under the Group E detail section"
    )


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
# Helpers for integration tests
# ---------------------------------------------------------------------------

CLAUDE_PREDICTIONS = json.dumps({
    "predictions": [
        {"group": "A", "winner": "Germany", "runnerUp": "Mexico", "reasoning": "..."}
    ]
})


def _make_claude_mock():
    mock_response = MagicMock()
    mock_response.usage = MagicMock(input_tokens=100, output_tokens=50)
    mock_response.content = [MagicMock(text=CLAUDE_PREDICTIONS)]
    mock_claude = MagicMock()
    mock_claude.beta.messages.parse = AsyncMock(return_value=mock_response)
    return mock_claude, mock_response


@pytest.fixture
def queue_msg():
    msg = MagicMock()
    msg.get_body.return_value = json.dumps({"matchday": 1, "fixtureId": 101}).encode()
    return msg


# ---------------------------------------------------------------------------
# _main_async — integration tests
# ---------------------------------------------------------------------------

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

    mock_claude, _ = _make_claude_mock()

    with (
        patch("fn_predict.get_containers", return_value=(
            mock_teams_container, mock_fixtures_container, mock_predictions_container, MagicMock()
        )),
        patch("fn_predict.get_news_container", return_value=None),
        patch("fn_predict.get_anthropic_client", return_value=mock_claude),
    ):
        await _main_async(queue_msg)

    mock_predictions_container.upsert_item.assert_called_once()
    doc = mock_predictions_container.upsert_item.call_args[1]["body"]
    assert doc["id"] == "predictions-all"
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

    mock_claude, _ = _make_claude_mock()

    with (
        patch("fn_predict.get_containers", return_value=(
            mock_teams_container, mock_fixtures_container, mock_predictions_container, MagicMock()
        )),
        patch("fn_predict.get_news_container", return_value=None),
        patch("fn_predict.get_anthropic_client", return_value=mock_claude),
        patch("fn_predict.search_team_news", new=AsyncMock(return_value=["Germany news headline"])) as mock_search,
        patch.dict(os.environ, {"SERPA_API_KEY": "test-serpa-key"}),
    ):
        await _main_async(queue_msg)

    mock_search.assert_called()
    prompt_sent = mock_claude.beta.messages.parse.call_args[1]["messages"][0]["content"]
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

    mock_claude, _ = _make_claude_mock()

    env_without_serpa = {k: v for k, v in os.environ.items() if k != "SERPA_API_KEY"}
    with (
        patch("fn_predict.get_containers", return_value=(
            mock_teams_container, mock_fixtures_container, mock_predictions_container, MagicMock()
        )),
        patch("fn_predict.get_news_container", return_value=None),
        patch("fn_predict.get_anthropic_client", return_value=mock_claude),
        patch("fn_predict.search_team_news", new=AsyncMock()) as mock_search,
        patch.dict(os.environ, env_without_serpa, clear=True),
    ):
        await _main_async(queue_msg)

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

    mock_claude, _ = _make_claude_mock()

    with (
        patch("fn_predict.get_containers", return_value=(
            mock_teams_container, mock_fixtures_container, mock_predictions_container, MagicMock()
        )),
        patch("fn_predict.get_news_container", return_value=None),
        patch("fn_predict.get_anthropic_client", return_value=mock_claude),
    ):
        await _main_async(queue_msg)
        await _main_async(queue_msg)

    assert mock_predictions_container.upsert_item.call_count == 2
    calls = mock_predictions_container.upsert_item.call_args_list
    assert calls[0][1]["body"]["id"] == calls[1][1]["body"]["id"]


# ---------------------------------------------------------------------------
# _fetch_news_parallel — unit tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_news_fetch_is_parallel():
    """All teams should be fetched concurrently via asyncio.gather."""
    teams = [_make_team("A", "Germany"), _make_team("B", "Brazil"), _make_team("C", "France")]

    with patch("fn_predict.search_team_news", new=AsyncMock(return_value=["headline"])) as mock_search:
        result = await _fetch_news_parallel(
            teams, serpa_key="key", max_results=3, today="2026-06-06",
            news_container=None, usage_container=None,
        )

    assert mock_search.call_count == 3
    assert "Germany" in result
    assert "Brazil" in result
    assert "France" in result


@pytest.mark.asyncio
async def test_news_cached_after_fetch():
    """After fetching, snippets should be upserted into the news container."""
    teams = [_make_team("A", "Germany")]
    mock_news_container = MagicMock()
    mock_news_container.read_item = AsyncMock(side_effect=Exception("not found"))
    mock_news_container.upsert_item = AsyncMock()

    with patch("fn_predict.search_team_news", new=AsyncMock(return_value=["headline"])):
        await _fetch_news_parallel(
            teams, serpa_key="key", max_results=3, today="2026-06-06",
            news_container=mock_news_container, usage_container=None,
        )

    mock_news_container.upsert_item.assert_called_once()
    cached_doc = mock_news_container.upsert_item.call_args[1]["body"]
    assert cached_doc["teamName"] == "Germany"
    assert cached_doc["snippets"] == ["headline"]
    assert "ttl" in cached_doc


@pytest.mark.asyncio
async def test_news_served_from_cache():
    """Cached teams should not trigger a new Serper API call."""
    teams = [_make_team("A", "Germany")]
    mock_news_container = MagicMock()
    mock_news_container.read_item = AsyncMock(return_value={
        "id": "news-germany-2026-06-06",
        "teamName": "Germany",
        "snippets": ["cached headline"],
    })

    with patch("fn_predict.search_team_news", new=AsyncMock()) as mock_search:
        result = await _fetch_news_parallel(
            teams, serpa_key="key", max_results=3, today="2026-06-06",
            news_container=mock_news_container, usage_container=None,
        )

    mock_search.assert_not_called()
    assert result["Germany"] == ["cached headline"]


# ---------------------------------------------------------------------------
# Observability logging (issue #23)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_predict_logs_doc_id_and_matchday(caplog):
    """fn_predict logs doc id='predictions-all' and matchday at INFO on every write."""
    import logging

    mock_teams_container = MagicMock()
    mock_teams_container.query_items = MagicMock(
        return_value=_async_iter([_make_team("A", "Germany")])
    )
    mock_fixtures_container = MagicMock()
    mock_fixtures_container.query_items = MagicMock(return_value=_async_iter([]))
    mock_predictions_container = MagicMock()
    mock_predictions_container.upsert_item = AsyncMock()
    mock_claude, _ = _make_claude_mock()

    queue_msg = MagicMock()
    queue_msg.get_body.return_value = json.dumps({"matchday": 1, "fixtureId": None}).encode()

    with (
        patch("fn_predict.get_containers", return_value=(
            mock_teams_container, mock_fixtures_container, mock_predictions_container, MagicMock()
        )),
        patch("fn_predict.get_news_container", return_value=None),
        patch("fn_predict.get_anthropic_client", return_value=mock_claude),
        caplog.at_level(logging.INFO, logger="fn_predict"),
    ):
        await _main_async(queue_msg)

    messages = [r.message for r in caplog.records if r.levelno == logging.INFO]
    assert any("predictions-all" in m for m in messages), \
        f"Expected INFO log with 'predictions-all', got: {messages}"
    assert any("matchday" in m.lower() and "1" in m for m in messages), \
        f"Expected INFO log with matchday=1, got: {messages}"


# ---------------------------------------------------------------------------
# Correlation ID
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_predict_logs_correlation_id(caplog):
    """fn_predict logs the correlationId from the queue message."""
    import logging
    mock_teams_container = MagicMock()
    mock_teams_container.query_items = MagicMock(return_value=_async_iter([]))
    mock_fixtures_container = MagicMock()
    mock_fixtures_container.query_items = MagicMock(return_value=_async_iter([]))
    mock_predictions_container = MagicMock()
    mock_predictions_container.query_items = MagicMock(return_value=_async_iter([]))
    mock_predictions_container.upsert_item = AsyncMock()
    mock_claude, _ = _make_claude_mock()

    queue_msg = MagicMock()
    queue_msg.get_body.return_value = json.dumps(
        {"matchday": 1, "fixtureId": None, "correlationId": "corr-xyz-5678"}
    ).encode()

    with (
        patch("fn_predict.get_containers", return_value=(
            mock_teams_container, mock_fixtures_container, mock_predictions_container, MagicMock()
        )),
        patch("fn_predict.get_news_container", return_value=None),
        patch("fn_predict.get_anthropic_client", return_value=mock_claude),
        caplog.at_level(logging.INFO, logger="fn_predict"),
    ):
        await _main_async(queue_msg)

    assert any("corr-xyz-5678" in r.message for r in caplog.records), \
        "fn_predict must log the correlationId from the queue message"


# ---------------------------------------------------------------------------
# Fix: do not write empty prediction doc when Claude returns no groups
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_predict_does_not_write_when_predictions_empty():
    """When Claude returns 0 groups, fn_predict must raise and NOT overwrite the predictions doc."""
    msg = MagicMock()
    msg.get_body.return_value = json.dumps({"matchday": 1, "fixtureId": None}).encode()

    mock_teams_container = MagicMock()
    mock_teams_container.query_items = MagicMock(return_value=_async_iter([_make_team("A", "Germany")]))
    mock_fixtures_container = MagicMock()
    mock_fixtures_container.query_items = MagicMock(return_value=_async_iter([]))
    mock_predictions_container = MagicMock()
    mock_predictions_container.upsert_item = AsyncMock()

    mock_response = MagicMock()
    mock_response.usage = MagicMock(input_tokens=100, output_tokens=10)
    mock_response.content = [MagicMock(text='{"predictions": []}')]
    mock_claude = MagicMock()
    mock_claude.beta.messages.parse = AsyncMock(return_value=mock_response)

    with (
        patch("fn_predict.get_containers", return_value=(
            mock_teams_container, mock_fixtures_container, mock_predictions_container, MagicMock()
        )),
        patch("fn_predict.get_news_container", return_value=None),
        patch("fn_predict.get_anthropic_client", return_value=mock_claude),
    ):
        with pytest.raises(RuntimeError, match="empty predictions"):
            await _main_async(msg)

    mock_predictions_container.upsert_item.assert_not_called()


# ---------------------------------------------------------------------------
# Fix: resolve matchday="full" to the highest finished group matchday
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_predict_resolves_full_matchday_from_finished_fixtures():
    """`matchday='full'` resolves to the highest completed group-stage matchday."""
    msg = MagicMock()
    msg.get_body.return_value = json.dumps(
        {"matchday": "full", "correlationId": "test-corr"}
    ).encode()

    fixtures_data = [
        _make_fixture(1, "Germany", "Mexico", "FT"),
        _make_fixture(2, "Germany", "Poland", "FT"),
        _make_fixture(3, "Germany", "France", "NS"),  # not finished
    ]
    mock_teams_container = MagicMock()
    mock_teams_container.query_items = MagicMock(return_value=_async_iter([_make_team("A", "Germany")]))
    mock_fixtures_container = MagicMock()
    # Use side_effect so each query call gets a fresh async generator
    mock_fixtures_container.query_items = MagicMock(
        side_effect=lambda **kwargs: _async_iter(list(fixtures_data))
    )
    mock_predictions_container = MagicMock()
    mock_predictions_container.upsert_item = AsyncMock()
    mock_scores_container = MagicMock()
    mock_scores_container.upsert_item = AsyncMock()

    mock_claude, _ = _make_claude_mock()

    with (
        patch("fn_predict.get_containers", return_value=(
            mock_teams_container, mock_fixtures_container, mock_predictions_container, mock_scores_container
        )),
        patch("fn_predict.get_news_container", return_value=None),
        patch("fn_predict.get_anthropic_client", return_value=mock_claude),
    ):
        await _main_async(msg)

    doc = mock_predictions_container.upsert_item.call_args[1]["body"]
    assert doc["matchday"] == 2, f"Expected matchday=2 (highest FT), got {doc['matchday']}"


@pytest.mark.asyncio
async def test_predict_resolves_full_matchday_defaults_to_3_when_no_finished_fixtures():
    """`matchday='full'` defaults to 3 when there are no finished group-stage fixtures."""
    msg = MagicMock()
    msg.get_body.return_value = json.dumps(
        {"matchday": "full", "correlationId": "test-corr"}
    ).encode()

    mock_teams_container = MagicMock()
    mock_teams_container.query_items = MagicMock(return_value=_async_iter([_make_team("A", "Germany")]))
    mock_fixtures_container = MagicMock()
    mock_fixtures_container.query_items = MagicMock(return_value=_async_iter([
        _make_fixture(1, "Germany", "Mexico", "NS"),
        _make_fixture(2, "Germany", "Poland", "NS"),
    ]))
    mock_predictions_container = MagicMock()
    mock_predictions_container.upsert_item = AsyncMock()

    mock_claude, _ = _make_claude_mock()

    with (
        patch("fn_predict.get_containers", return_value=(
            mock_teams_container, mock_fixtures_container, mock_predictions_container, MagicMock()
        )),
        patch("fn_predict.get_news_container", return_value=None),
        patch("fn_predict.get_anthropic_client", return_value=mock_claude),
    ):
        await _main_async(msg)

    doc = mock_predictions_container.upsert_item.call_args[1]["body"]
    assert doc["matchday"] == 3, f"Expected default matchday=3, got {doc['matchday']}"


# ---------------------------------------------------------------------------
# Knockout stage support (issue #32)
# ---------------------------------------------------------------------------

def _make_knockout_fixture(
    fixture_id: int,
    stage: str,
    home: str = "TBD",
    away: str = "TBD",
    status: str = "NS",
    home_score: int | None = None,
    away_score: int | None = None,
) -> dict:
    return {
        "id": f"fixture-{fixture_id}",
        "fixtureId": fixture_id,
        "matchday": stage,
        "stage": stage,
        "homeTeam": home,
        "awayTeam": away,
        "homeScore": home_score,
        "awayScore": away_score,
        "status": status,
        "kickoff": "2026-06-28T19:00:00Z",
    }


def test_build_prompt_includes_knockout_section_for_known_teams():
    """Knockout fixtures with known (non-TBD) teams appear in the prompt."""
    teams = [_make_team("A", "Germany"), _make_team("A", "Mexico")]
    fixtures = [
        _make_knockout_fixture(537417, "LAST_32", "Germany", "Mexico"),
    ]
    prompt = _build_prompt(teams=teams, fixtures=fixtures)
    assert "Germany vs Mexico" in prompt
    assert "LAST_32" in prompt or "knockout" in prompt.lower()


def test_build_prompt_omits_tbd_knockout_matches():
    """Knockout fixtures where both teams are TBD are excluded from the prompt."""
    teams = [_make_team("A", "Germany")]
    fixtures = [
        _make_knockout_fixture(537417, "LAST_32", "TBD", "TBD"),
        _make_knockout_fixture(537418, "LAST_32", "TBD", "TBD"),
    ]
    prompt = _build_prompt(teams=teams, fixtures=fixtures)
    assert "537417" not in prompt
    assert "537418" not in prompt


def test_build_prompt_includes_some_known_knockout_excludes_tbd():
    """Only non-TBD knockout matches appear; TBD pairs are excluded."""
    teams = [_make_team("A", "Germany"), _make_team("A", "Brazil")]
    fixtures = [
        _make_knockout_fixture(1, "LAST_32", "Germany", "Brazil"),
        _make_knockout_fixture(2, "LAST_32", "TBD", "TBD"),
    ]
    prompt = _build_prompt(teams=teams, fixtures=fixtures)
    assert "Germany vs Brazil" in prompt
    assert str(2) not in prompt or "TBD vs TBD" not in prompt


def test_build_prompt_knockout_schema_included_when_knockout_present():
    """When knockout fixtures with known teams exist, the schema includes knockout field."""
    teams = [_make_team("A", "Germany"), _make_team("A", "Brazil")]
    fixtures = [_make_knockout_fixture(1, "LAST_32", "Germany", "Brazil")]
    prompt = _build_prompt(teams=teams, fixtures=fixtures)
    assert "knockout" in prompt


def test_predict_stores_knockout_in_prediction_doc(queue_msg):
    """_main_async stores knockout predictions in the prediction document."""
    import asyncio

    CLAUDE_WITH_KNOCKOUT = json.dumps({
        "predictions": [
            {"group": "A", "winner": "Germany", "runnerUp": "Mexico", "reasoning": "..."}
        ],
        "knockout": [
            {
                "stage": "LAST_32",
                "matches": [
                    {
                        "fixtureId": 537417,
                        "stage": "LAST_32",
                        "homeTeam": "Germany",
                        "awayTeam": "Mexico",
                        "predictedWinner": "Germany",
                        "predictedHomeScore": 2,
                        "predictedAwayScore": 1,
                        "confidence": "high",
                    }
                ],
            }
        ],
    })

    mock_teams_container = MagicMock()
    mock_teams_container.query_items = MagicMock(
        return_value=_async_iter([_make_team("A", "Germany")])
    )
    mock_fixtures_container = MagicMock()
    mock_fixtures_container.query_items = MagicMock(return_value=_async_iter([]))
    mock_predictions_container = MagicMock()
    mock_predictions_container.upsert_item = AsyncMock()

    mock_response = MagicMock()
    mock_response.usage = MagicMock(input_tokens=100, output_tokens=50)
    mock_response.content = [MagicMock(text=CLAUDE_WITH_KNOCKOUT)]
    mock_claude = MagicMock()
    mock_claude.beta.messages.parse = AsyncMock(return_value=mock_response)

    with (
        patch("fn_predict.get_containers", return_value=(
            mock_teams_container, mock_fixtures_container, mock_predictions_container, MagicMock()
        )),
        patch("fn_predict.get_news_container", return_value=None),
        patch("fn_predict.get_anthropic_client", return_value=mock_claude),
    ):
        asyncio.run(_main_async(queue_msg))

    doc = mock_predictions_container.upsert_item.call_args[1]["body"]
    assert "knockout" in doc
    assert len(doc["knockout"]) == 1
    assert doc["knockout"][0]["stage"] == "LAST_32"
    assert doc["knockout"][0]["matches"][0]["predictedWinner"] == "Germany"
