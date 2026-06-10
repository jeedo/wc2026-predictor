"""Tests for Azure SDK log suppression — issue #39."""
import logging
import importlib


def test_azure_cosmos_logger_set_to_warning():
    import shared  # noqa: F401 — trigger __init__ side-effect
    assert logging.getLogger("azure.cosmos").level == logging.WARNING


def test_azure_http_policy_logger_set_to_warning():
    import shared  # noqa: F401
    assert logging.getLogger("azure.core.pipeline.policies.http_logging_policy").level == logging.WARNING


def test_own_loggers_not_affected():
    """fn_* and shared loggers must not be silenced by the SDK suppression."""
    import shared  # noqa: F401
    for name in ("fn_ingest", "fn_predict", "fn_api", "shared"):
        lvl = logging.getLogger(name).level
        assert lvl != logging.WARNING, f"{name} logger should not be forced to WARNING"
