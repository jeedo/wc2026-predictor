"""Tests for shared/serpa.py — SerpApi Google News client."""
import os
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch

from shared.serpa import search_team_news


SERPAPI_SUCCESS = {
    "news_results": [
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
    mock_client.get = AsyncMock(return_value=mock_response)
    return mock_client


@pytest.mark.asyncio
async def test_search_returns_news_snippets():
    with patch("shared.serpa.httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value = _make_mock_client(200, SERPAPI_SUCCESS)
        results = await search_team_news("Germany", api_key="test-key")

    assert len(results) == 2
    assert "Germany squad named for World Cup 2026" in results[0] or "Nagelsmann" in results[0]


@pytest.mark.asyncio
async def test_search_prefers_snippet_over_title():
    """When snippet is present it should be used; title is the fallback."""
    data = {"news_results": [{"title": "T", "snippet": "S"}, {"title": "T2", "snippet": ""}]}
    with patch("shared.serpa.httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value = _make_mock_client(200, data)
        results = await search_team_news("Germany", api_key="test-key")

    assert results[0] == "S"
    assert results[1] == "T2"


@pytest.mark.asyncio
async def test_search_respects_max_results():
    with patch("shared.serpa.httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value = _make_mock_client(200, SERPAPI_SUCCESS)
        results = await search_team_news("Germany", api_key="test-key", max_results=1)

    assert len(results) == 1


@pytest.mark.asyncio
async def test_search_returns_empty_on_http_error():
    with patch("shared.serpa.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=httpx.HTTPError("connection failed"))
        mock_client_cls.return_value = mock_client

        results = await search_team_news("Germany", api_key="test-key")

    assert results == []


@pytest.mark.asyncio
async def test_search_returns_empty_on_empty_news_results():
    with patch("shared.serpa.httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value = _make_mock_client(200, {"news_results": []})
        results = await search_team_news("Germany", api_key="test-key")

    assert results == []


@pytest.mark.asyncio
async def test_search_sends_correct_query():
    with patch("shared.serpa.httpx.AsyncClient") as mock_client_cls:
        mock_client = _make_mock_client(200, {"news_results": []})
        mock_client_cls.return_value = mock_client

        await search_team_news("Brazil", api_key="my-key", max_results=5)

    call_kwargs = mock_client.get.call_args
    assert "serpapi.com" in call_kwargs[0][0]
    params = call_kwargs[1]["params"]
    assert "Brazil" in params["q"]
    assert params["num"] == 5
    assert params["api_key"] == "my-key"
    assert params["engine"] == "google_news"


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
async def test_search_returns_empty_on_429():
    with patch("shared.serpa.httpx.AsyncClient") as mock_client_cls:
        mock_client_cls.return_value = _make_mock_client(429, {})
        results = await search_team_news("Germany", api_key="test-key")
    assert results == []


@pytest.mark.asyncio
async def test_search_returns_empty_on_timeout():
    with patch("shared.serpa.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
        mock_client_cls.return_value = mock_client
        results = await search_team_news("Germany", api_key="test-key")
    assert results == []


@pytest.mark.asyncio
async def test_search_query_includes_context_keywords():
    with patch("shared.serpa.httpx.AsyncClient") as mock_client_cls:
        mock_client = _make_mock_client(200, {"news_results": []})
        mock_client_cls.return_value = mock_client

        await search_team_news("Germany", api_key="key")

    params = mock_client.get.call_args[1]["params"]
    assert any(kw in params["q"] for kw in ("injury", "form", "squad"))


@pytest.mark.asyncio
async def test_search_uses_env_max_results():
    with patch("shared.serpa.httpx.AsyncClient") as mock_client_cls:
        mock_client = _make_mock_client(200, {"news_results": []})
        mock_client_cls.return_value = mock_client

        with patch.dict(os.environ, {"SERPA_MAX_RESULTS": "7"}):
            await search_team_news("Germany", api_key="key")

    params = mock_client.get.call_args[1]["params"]
    assert params["num"] == 7
