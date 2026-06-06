"""Direct App Insights telemetry via opencensus-ext-azure.

Uses AzureLogHandler instead of the Azure Functions logging bridge so that
flush() can be called explicitly — guaranteeing data is sent even when the
worker process crashes before normal teardown.
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_ai_logger: logging.Logger | None = None


def _get_ai_logger() -> logging.Logger | None:
    global _ai_logger
    if _ai_logger is not None:
        return _ai_logger

    conn_str = os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING")
    ikey = os.environ.get("APPINSIGHTS_INSTRUMENTATIONKEY")
    if not conn_str and not ikey:
        return None

    try:
        from opencensus.ext.azure.log_exporter import AzureLogHandler

        key = conn_str or f"InstrumentationKey={ikey}"
        handler = AzureLogHandler(connection_string=key)
        handler.flush_interval = 0  # send immediately on flush()

        ai = logging.getLogger("wc2026.telemetry")
        ai.setLevel(logging.INFO)
        if not ai.handlers:
            ai.addHandler(handler)
        ai.propagate = False
        _ai_logger = ai
        return _ai_logger
    except Exception as exc:
        logger.warning("AzureLogHandler init failed: %s", exc)
        return None


def _flush() -> None:
    ai = _get_ai_logger()
    if ai is None:
        return
    for h in ai.handlers:
        try:
            h.flush()
        except Exception:
            pass


def track_event(
    name: str,
    properties: dict[str, Any] | None = None,
) -> None:
    """Log a custom event to App Insights and flush immediately.

    Appears in App Insights under customEvents / traces with custom dimensions.
    """
    ai = _get_ai_logger()
    if ai is None:
        logger.info("event:%s %s", name, properties or {})
        return
    ai.info(
        name,
        extra={"custom_dimensions": {"event": name, **(properties or {})}},
    )
    _flush()


def track_metric(name: str, value: float, properties: dict[str, Any] | None = None) -> None:
    """Log a named metric value as a trace with custom dimensions."""
    track_event(f"metric:{name}", {"value": str(value), **(properties or {})})


def track_exception(exc: Exception, properties: dict[str, Any] | None = None) -> None:
    """Log an exception with context and flush immediately."""
    ai = _get_ai_logger()
    dims = {"event": "fn_predict/error", "error_type": type(exc).__name__, **(properties or {})}
    if ai is None:
        logger.error("exception: %s %s", exc, dims)
        return
    ai.exception(
        str(exc),
        exc_info=(type(exc), exc, exc.__traceback__),
        extra={"custom_dimensions": dims},
    )
    _flush()
