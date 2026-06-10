"""Daily aggregate usage tracking for external API providers."""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

from azure.cosmos.exceptions import CosmosResourceNotFoundError

logger = logging.getLogger(__name__)

PROVIDER_LIMITS: dict[str, dict[str, Any]] = {
    "football-data": {"limit": 10, "window": "minute"},
    "anthropic":     {"limit": None, "window": "day"},
    "serper":        {"limit": 2500, "window": "month"},
}


async def record_call(
    container: Any | None,
    provider: str,
    **extra: int,
) -> None:
    """Upsert a daily aggregate document for `provider`, incrementing callCount.

    Pass keyword args like inputTokens=1500, outputTokens=300 to accumulate
    additional counters (used for the Anthropic provider).

    No-op when `container` is None so callers don't crash in environments
    where the usage container isn't configured.
    """
    if container is None:
        return

    today = date.today().isoformat()
    doc_id = f"usage-{provider}-{today}"

    try:
        doc: dict[str, Any] = await container.read_item(
            item=doc_id, partition_key=provider
        )
    except CosmosResourceNotFoundError:
        doc = {"id": doc_id, "provider": provider, "date": today, "callCount": 0}

    doc["callCount"] = doc.get("callCount", 0) + 1
    for key, value in extra.items():
        doc[key] = doc.get(key, 0) + value

    try:
        await container.upsert_item(body=doc)
    except Exception as exc:
        logger.warning("Failed to record usage for %s: %s", provider, exc)
