"""Tests for shared/api_football.py."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.api_football import (
    ApiFootballClient,
    normalise_round,
    fetch_teams,
    fetch_fixtures,
    fetch_standings,
)


def test_normalise_round_group_stage():
    assert normalise_round("Group Stage - 1") == 1
    assert normalise_round("Group Stage - 2") == 2
    assert normalise_round("Group Stage - 3") == 3


def test_normalise_round_unknown_returns_none():
    assert normalise_round("Round of 16") is None
    assert normalise_round("") is None


TEAMS_RESPONSE = {
    "response": [
        {"team": {"id": 1, "name": "Germany"}, "venue": {}},
        {"team": {"id": 2, "name": "Mexico"}, "venue": {}},
    ]
}

FIXTURES_RESPONSE = {
    "response": [
        {
            "fixture": {"id": 101, "status": {"short": "FT"}},
            "league": {"round": "Group Stage - 1"},
            "teams": {
                "home": {"id": 1, "name": "Germany"},
                "away": {"id": 2, "name": "Mexico"},
            },
            "goals": {"home": 2, "away": 0},
            "fixture": {
                "id": 101,
                "date": "2026-06-12T15:00:00+00:00",
                "status": {"short": "FT"},
            },
        }
    ]
}

STANDINGS_RESPONSE = {
    "response": [
        {
            "league": {
                "standings": [
                    [
                        {
                            "team": {"id": 1, "name": "Germany"},
                            "group": "Group A",
                            "rank": 1,
                            "points": 3,
                        }
                    ]
                ]
            }
        }
    ]
}


@pytest.fixture
def mock_httpx_client():
    client = AsyncMock()
    return client


@pytest.fixture
def api_client():
    return ApiFootballClient(api_key="test-key")


@pytest.mark.asyncio
async def test_fetch_teams_returns_list(api_client, mock_httpx_client):
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json = MagicMock(return_value=TEAMS_RESPONSE)
    mock_httpx_client.get = AsyncMock(return_value=response)

    result = await fetch_teams(api_client, mock_httpx_client)

    assert len(result) == 2
    assert result[0]["team"]["name"] == "Germany"


@pytest.mark.asyncio
async def test_fetch_fixtures_normalises_round(api_client, mock_httpx_client):
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json = MagicMock(return_value=FIXTURES_RESPONSE)
    mock_httpx_client.get = AsyncMock(return_value=response)

    result = await fetch_fixtures(api_client, mock_httpx_client, matchday=1)

    assert result[0]["matchday"] == 1


@pytest.mark.asyncio
async def test_fetch_standings_returns_flat_list(api_client, mock_httpx_client):
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json = MagicMock(return_value=STANDINGS_RESPONSE)
    mock_httpx_client.get = AsyncMock(return_value=response)

    result = await fetch_standings(api_client, mock_httpx_client)

    assert len(result) == 1
    assert result[0]["team"]["name"] == "Germany"


@pytest.mark.asyncio
async def test_fetch_fixtures_http_error_propagates(api_client, mock_httpx_client):
    import httpx

    mock_httpx_client.get = AsyncMock(side_effect=httpx.HTTPStatusError(
        "404", request=MagicMock(), response=MagicMock()
    ))

    with pytest.raises(httpx.HTTPStatusError):
        await fetch_fixtures(api_client, mock_httpx_client, matchday=1)
