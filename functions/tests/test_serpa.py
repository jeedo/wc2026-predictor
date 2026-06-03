"""Tests for shared/serpa.py — Serper.dev news search client."""
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


@pytest.mark.asyncio
async def test_search_returns_news_snippets():
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = SERPER_SUCCESS

    with patch("shared.serpa.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        results = await search_team_news("Germany", api_key="test-key")

    assert len(results) == 2
    assert "Germany squad named for World Cup 2026" in results[0]
    assert "Nagelsmann has selected" in results[0]


@pytest.mark.asyncio
async def test_search_respects_max_results():
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = SERPER_SUCCESS

    with patch("shared.serpa.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

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
async def test_search_returns_empty_on_empty_news_key():
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"news": []}

    with patch("shared.serpa.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        results = await search_team_news("Germany", api_key="test-key")

    assert results == []


@pytest.mark.asyncio
async def test_search_sends_correct_query():
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"news": []}

    with patch("shared.serpa.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        await search_team_news("Brazil", api_key="my-key", max_results=5)

    call_kwargs = mock_client.post.call_args
    assert "google.serper.dev" in call_kwargs[0][0]
    payload = call_kwargs[1]["json"]
    assert "Brazil" in payload["q"]
    assert payload["num"] == 5
    headers = call_kwargs[1]["headers"]
    assert headers["X-API-KEY"] == "my-key"
