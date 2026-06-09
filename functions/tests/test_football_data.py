"""Tests for shared/football_data.py — retry behavior on transient connection errors."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from shared.football_data import FootballDataClient, fetch_teams_fd, fetch_matches_fd, fetch_standings_fd


@pytest.fixture
def client():
    return FootballDataClient(api_key="test-key")


def _ok_response(data: dict) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value=data)
    return resp


# ---------------------------------------------------------------------------
# fetch_matches_fd
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_matches_retries_on_remote_protocol_error(client):
    """RemoteProtocolError triggers a retry; second attempt succeeds."""
    ok = _ok_response({"matches": [{"id": 1}]})
    http = AsyncMock()
    http.get = AsyncMock(side_effect=[httpx.RemoteProtocolError("Server disconnected"), ok])

    with patch("asyncio.sleep", new_callable=AsyncMock):
        result = await fetch_matches_fd(client, http, matchday=1)

    assert result == [{"id": 1}]
    assert http.get.call_count == 2


@pytest.mark.asyncio
async def test_fetch_matches_retries_on_connect_error(client):
    ok = _ok_response({"matches": [{"id": 2}]})
    http = AsyncMock()
    http.get = AsyncMock(side_effect=[httpx.ConnectError("Connection refused"), ok])

    with patch("asyncio.sleep", new_callable=AsyncMock):
        result = await fetch_matches_fd(client, http, matchday=1)

    assert result == [{"id": 2}]
    assert http.get.call_count == 2


@pytest.mark.asyncio
async def test_fetch_matches_retries_on_read_timeout(client):
    ok = _ok_response({"matches": [{"id": 3}]})
    http = AsyncMock()
    http.get = AsyncMock(side_effect=[httpx.ReadTimeout("Timed out"), ok])

    with patch("asyncio.sleep", new_callable=AsyncMock):
        result = await fetch_matches_fd(client, http, matchday=1)

    assert result == [{"id": 3}]
    assert http.get.call_count == 2


@pytest.mark.asyncio
async def test_fetch_matches_does_not_retry_on_http_status_error(client):
    """HTTP 4xx/5xx from the API must not be retried."""
    http = AsyncMock()
    http.get = AsyncMock(side_effect=httpx.HTTPStatusError(
        "404", request=MagicMock(), response=MagicMock(status_code=404)
    ))

    with pytest.raises(httpx.HTTPStatusError):
        await fetch_matches_fd(client, http, matchday=1)

    assert http.get.call_count == 1


@pytest.mark.asyncio
async def test_fetch_matches_raises_after_max_attempts(client):
    """After 3 failed attempts the transient exception is re-raised."""
    http = AsyncMock()
    http.get = AsyncMock(side_effect=httpx.RemoteProtocolError("Server disconnected"))

    with patch("asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(httpx.RemoteProtocolError):
            await fetch_matches_fd(client, http, matchday=1)

    assert http.get.call_count == 3


# ---------------------------------------------------------------------------
# fetch_teams_fd
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_teams_retries_on_transient_error(client):
    ok = _ok_response({"teams": [{"id": 10}]})
    http = AsyncMock()
    http.get = AsyncMock(side_effect=[httpx.ConnectError(""), ok])

    with patch("asyncio.sleep", new_callable=AsyncMock):
        result = await fetch_teams_fd(client, http)

    assert result == [{"id": 10}]
    assert http.get.call_count == 2


@pytest.mark.asyncio
async def test_fetch_teams_does_not_retry_on_http_status_error(client):
    http = AsyncMock()
    http.get = AsyncMock(side_effect=httpx.HTTPStatusError(
        "403", request=MagicMock(), response=MagicMock(status_code=403)
    ))

    with pytest.raises(httpx.HTTPStatusError):
        await fetch_teams_fd(client, http)

    assert http.get.call_count == 1


# ---------------------------------------------------------------------------
# fetch_standings_fd
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_standings_retries_on_transient_error(client):
    ok = _ok_response({"standings": []})
    http = AsyncMock()
    http.get = AsyncMock(side_effect=[httpx.RemoteProtocolError(""), ok])

    with patch("asyncio.sleep", new_callable=AsyncMock):
        result = await fetch_standings_fd(client, http)

    assert result == []
    assert http.get.call_count == 2


# ---------------------------------------------------------------------------
# fetch_groups_from_standings (group_derivation)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_groups_retries_on_transient_error():
    """fetch_groups_from_standings retries on transient connection errors."""
    from shared.group_derivation import fetch_groups_from_standings

    ok = MagicMock()
    ok.status_code = 200
    ok.json = MagicMock(return_value={
        "standings": [
            {"group": "Group A", "table": [{"team": {"name": "Germany"}}]}
        ]
    })

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=[httpx.RemoteProtocolError(""), ok])
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("httpx.AsyncClient", return_value=mock_client),
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):
        result = await fetch_groups_from_standings("test-key")

    assert result == {"Germany": "A"}
    assert mock_client.get.call_count == 2


@pytest.mark.asyncio
async def test_fetch_groups_does_not_retry_on_non_200():
    """fetch_groups_from_standings raises ValueError on non-200 and does not retry."""
    from shared.group_derivation import fetch_groups_from_standings

    bad = MagicMock()
    bad.status_code = 429

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=bad)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(ValueError, match="Failed to fetch standings"):
            await fetch_groups_from_standings("test-key")

    assert mock_client.get.call_count == 1
