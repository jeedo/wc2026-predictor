"""Tests for shared/usage_tracker.py."""
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.usage_tracker import record_call, PROVIDER_LIMITS
from azure.cosmos.exceptions import CosmosResourceNotFoundError


def _make_container(existing_doc=None):
    container = MagicMock()
    if existing_doc is None:
        container.read_item = AsyncMock(
            side_effect=CosmosResourceNotFoundError(message="not found", response=MagicMock())
        )
    else:
        container.read_item = AsyncMock(return_value=existing_doc)
    container.upsert_item = AsyncMock()
    return container


@pytest.mark.asyncio
async def test_record_call_creates_new_doc():
    container = _make_container()
    await record_call(container, "api-football")

    container.upsert_item.assert_called_once()
    doc = container.upsert_item.call_args[1]["body"]
    assert doc["provider"] == "api-football"
    assert doc["callCount"] == 1
    assert doc["date"] == date.today().isoformat()


@pytest.mark.asyncio
async def test_record_call_increments_existing():
    existing = {
        "id": f"usage-api-football-{date.today().isoformat()}",
        "provider": "api-football",
        "date": date.today().isoformat(),
        "callCount": 5,
    }
    container = _make_container(existing_doc=existing)
    await record_call(container, "api-football")

    doc = container.upsert_item.call_args[1]["body"]
    assert doc["callCount"] == 6


@pytest.mark.asyncio
async def test_record_call_tracks_tokens():
    container = _make_container()
    await record_call(container, "anthropic", inputTokens=1500, outputTokens=300)

    doc = container.upsert_item.call_args[1]["body"]
    assert doc["inputTokens"] == 1500
    assert doc["outputTokens"] == 300


@pytest.mark.asyncio
async def test_record_call_accumulates_tokens_on_existing():
    existing = {
        "id": f"usage-anthropic-{date.today().isoformat()}",
        "provider": "anthropic",
        "date": date.today().isoformat(),
        "callCount": 2,
        "inputTokens": 10000,
        "outputTokens": 800,
    }
    container = _make_container(existing_doc=existing)
    await record_call(container, "anthropic", inputTokens=2000, outputTokens=400)

    doc = container.upsert_item.call_args[1]["body"]
    assert doc["callCount"] == 3
    assert doc["inputTokens"] == 12000
    assert doc["outputTokens"] == 1200


@pytest.mark.asyncio
async def test_record_call_noop_when_container_is_none():
    # Should not raise even with no container
    await record_call(None, "api-football")


def test_provider_limits_has_known_providers():
    assert "api-football" in PROVIDER_LIMITS
    assert "anthropic" in PROVIDER_LIMITS
    assert "serper" in PROVIDER_LIMITS
