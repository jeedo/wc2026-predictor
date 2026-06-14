"""Tests for shared/serpa.py — Serper.dev Google News client."""
import os
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch

from shared.serpa import search_team_news


SERPER_SUCCESS = {
    "news": [
        {
            "title": "Germany squad named for World Cup 2026",
            "snippet": "Nagelsmann has selected a 26-man squad...",
            "date": "2 hours ago",
            "link": "https://example.com/1",
        },
        {
            "title": "Germany beat France in final warm-up",
            "snippet": "A late goal from Musiala sealed victory...",
            "date": "1 day ago",
            "link": "https://example.com/2",
        },
    ]
}


def _make_mock_client(status_code: int, json_body: dict):
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = json_body
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)
    return mock_client


@pytest.mark.asyncio
async def test_search_returns_news_snippets():
    with patch("shared.serpa.httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value = _make_mock_client(200, SERPER_SUCCESS)
        results = await search_team_news("Germany", api_key="test-key")

    assert len(results) == 2
    assert "Germany squad named for World Cup 2026" in results[0] or "Nagelsmann" in results[0]


@pytest.mark.asyncio
async def test_search_prefers_snippet_over_title():
    """When snippet is present it should be used; title is the fallback."""
    data = {"news": [{"title": "T", "snippet": "S"}, {"title": "T2", "snippet": ""}]}
    with patch("shared.serpa.httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value = _make_mock_client(200, data)
        results = await search_team_news("Germany", api_key="test-key")

    assert results[0] == "S"
    assert results[1] == "T2"


@pytest.mark.asyncio
async def test_search_respects_max_results():
    with patch("shared.serpa.httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value = _make_mock_client(200, SERPER_SUCCESS)
        results = await search_team_news("Germany", api_key="test-key", max_results=1)

    assert len(results) == 1


@pytest.mark.asyncio
async def test_search_returns_empty_on_http_error():
    with patch("shared.serpa.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=httpx.HTTPError("connection failed"))
        mock_client_cls.return_value = mock_client

        results = await search_team_news("Germany", api_key="test-key")

    assert results == []


@pytest.mark.asyncio
async def test_search_returns_empty_on_empty_news_results():
    with patch("shared.serpa.httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value = _make_mock_client(200, {"news": []})
        results = await search_team_news("Germany", api_key="test-key")

    assert results == []


@pytest.mark.asyncio
async def test_search_sends_correct_request():
    with patch("shared.serpa.httpx.AsyncClient") as mock_client_cls:
        mock_client = _make_mock_client(200, {"news": []})
        mock_client_cls.return_value = mock_client

        await search_team_news("Brazil", api_key="my-key", max_results=5)

    call_args = mock_client.post.call_args
    assert "google.serper.dev" in call_args[0][0]
    headers = call_args[1]["headers"]
    assert headers["X-API-KEY"] == "my-key"
    body = call_args[1]["json"]
    assert "Brazil" in body["q"]
    assert body["num"] == 5


@pytest.mark.asyncio
async def test_search_returns_empty_on_401():
    with patch("shared.serpa.httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value = _make_mock_client(401, {})
        results = await search_team_news("Germany", api_key="bad-key")
    assert results == []


@pytest.mark.asyncio
async def test_search_returns_empty_on_403():
    with patch("shared.serpa.httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value = _make_mock_client(403, {})
        results = await search_team_news("Germany", api_key="bad-key")
    assert results == []


@pytest.mark.asyncio
async def test_search_retries_on_429_then_succeeds():
    """On 429, should wait using x-ratelimit-reset then succeed on retry."""
    import time
    rate_limited = _make_mock_client(429, {})
    rate_limited.post.return_value.headers = {"x-ratelimit-reset": str(int(time.time()) + 1)}
    success = _make_mock_client(200, SERPER_SUCCESS)

    call_count = 0
    async def _post(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return rate_limited.post.return_value
        return success.post.return_value

    with patch("shared.serpa.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=_post)
        mock_client_cls.return_value = mock_client

        with patch("shared.serpa.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            results = await search_team_news("Germany", api_key="test-key")

    assert len(results) == 2
    mock_sleep.assert_called_once()


@pytest.mark.asyncio
async def test_search_returns_empty_after_exhausting_429_retries():
    """After MAX_RETRIES 429 responses, should return []."""
    mock_response = MagicMock()
    mock_response.status_code = 429
    mock_response.headers = {}

    with patch("shared.serpa.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        with patch("shared.serpa.asyncio.sleep", new_callable=AsyncMock):
            results = await search_team_news("Germany", api_key="test-key")

    assert results == []


@pytest.mark.asyncio
async def test_search_uses_reset_header_for_wait_time():
    """429 with x-ratelimit-reset should wait until that timestamp."""
    import time
    future_reset = int(time.time()) + 5

    rate_limited = MagicMock()
    rate_limited.status_code = 429
    rate_limited.headers = {"x-ratelimit-reset": str(future_reset)}

    success = MagicMock()
    success.status_code = 200
    success.raise_for_status = MagicMock()
    success.json.return_value = {"news": []}
    success.headers = {}

    responses = iter([rate_limited, success])

    with patch("shared.serpa.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=lambda *a, **kw: next(responses))
        mock_client_cls.return_value = mock_client

        with patch("shared.serpa.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            with patch("shared.serpa.time.time", return_value=float(future_reset - 5)):
                await search_team_news("Germany", api_key="test-key")

    sleep_arg = mock_sleep.call_args[0][0]
    assert 5.0 <= sleep_arg <= 6.0  # ~5s wait + 0.5s buffer


@pytest.mark.asyncio
async def test_search_returns_empty_on_timeout():
    with patch("shared.serpa.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
        mock_client_cls.return_value = mock_client
        results = await search_team_news("Germany", api_key="test-key")
    assert results == []


@pytest.mark.asyncio
async def test_search_query_includes_context_keywords():
    with patch("shared.serpa.httpx.AsyncClient") as mock_client_cls:
        mock_client = _make_mock_client(200, {"news": []})
        mock_client_cls.return_value = mock_client

        await search_team_news("Germany", api_key="key")

    body = mock_client.post.call_args[1]["json"]
    assert any(kw in body["q"] for kw in ("injury", "form", "squad"))


@pytest.mark.asyncio
async def test_search_uses_env_max_results():
    with patch("shared.serpa.httpx.AsyncClient") as mock_client_cls:
        mock_client = _make_mock_client(200, {"news": []})
        mock_client_cls.return_value = mock_client

        with patch.dict(os.environ, {"SERPA_MAX_RESULTS": "7"}):
            await search_team_news("Germany", api_key="key")

    body = mock_client.post.call_args[1]["json"]
    assert body["num"] == 7
