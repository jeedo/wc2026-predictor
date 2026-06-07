"""Cosmos DB helper functions for all four containers."""
from __future__ import annotations

import os
from typing import Any

from azure.cosmos.aio import CosmosClient  # noqa: F401 – re-exported for callers
from azure.cosmos.aio import CosmosClient as _CosmosClient


def get_client() -> _CosmosClient:
    connection_string = os.environ["CosmosDbConnectionString"]
    return _CosmosClient.from_connection_string(connection_string)


async def upsert_item(container: Any, doc: dict[str, Any]) -> dict[str, Any]:
    return await container.upsert_item(body=doc)


async def read_item(
    container: Any, item_id: str, partition_key: Any
) -> dict[str, Any]:
    return await container.read_item(item=item_id, partition_key=partition_key)


async def query_items(
    container: Any,
    query: str,
    parameters: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Async iteration over AsyncItemPaged — for use with the async CosmosClient."""
    kwargs: dict[str, Any] = {"query": query}
    if parameters:
        kwargs["parameters"] = parameters
    results: list[dict[str, Any]] = []
    async for item in container.query_items(**kwargs):
        results.append(item)
    return results


def query_items_sync(
    container: Any,
    query: str,
    parameters: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """For use with the sync CosmosClient (fn_api)."""
    kwargs: dict[str, Any] = {"query": query, "enable_cross_partition_query": True}
    if parameters:
        kwargs["parameters"] = parameters
    return list(container.query_items(**kwargs))
