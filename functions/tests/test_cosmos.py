"""Tests for shared/cosmos.py — upsert and point-read helpers."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.cosmos import CosmosClient, upsert_item, read_item, query_items


def _async_iter(items):
    """Return an async iterable backed by a plain list."""
    async def _gen():
        for item in items:
            yield item
    return _gen()


@pytest.fixture
def mock_container():
    container = MagicMock()
    container.upsert_item = AsyncMock(return_value={"id": "abc", "group": "A"})
    container.read_item = AsyncMock(return_value={"id": "abc", "group": "A"})
    container.query_items = MagicMock(return_value=_async_iter([{"id": "1"}, {"id": "2"}]))
    return container


@pytest.mark.asyncio
async def test_upsert_item_calls_container(mock_container):
    doc = {"id": "abc", "group": "A", "name": "Germany"}
    result = await upsert_item(mock_container, doc)
    mock_container.upsert_item.assert_called_once_with(body=doc)
    assert result["id"] == "abc"


@pytest.mark.asyncio
async def test_read_item_returns_document(mock_container):
    result = await read_item(mock_container, item_id="abc", partition_key="A")
    mock_container.read_item.assert_called_once_with(item="abc", partition_key="A")
    assert result["id"] == "abc"


@pytest.mark.asyncio
async def test_query_items_returns_list(mock_container):
    results = await query_items(mock_container, query="SELECT * FROM c")
    mock_container.query_items.assert_called_once_with(
        query="SELECT * FROM c", enable_cross_partition_query=True
    )
    assert len(results) == 2


@pytest.mark.asyncio
async def test_upsert_item_propagates_exception(mock_container):
    mock_container.upsert_item.side_effect = RuntimeError("Cosmos error")
    with pytest.raises(RuntimeError, match="Cosmos error"):
        await upsert_item(mock_container, {"id": "fail"})
