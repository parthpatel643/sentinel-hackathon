"""Structured logging.

JSON in every environment by default, because the ops dashboard and the audit
story both depend on machine-readable logs. Set SENTINEL_LOG_JSON=false for a
readable console during development.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

__all__ = ["configure_logging", "get_logger"]

_configured = False


def configure_logging(*, level: str = "INFO", json_output: bool = True) -> None:
    """Configure structlog and the stdlib root logger. Idempotent."""
    global _configured

    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    processors.append(
        structlog.processors.JSONRenderer() if json_output else structlog.dev.ConsoleRenderer()
    )

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelNamesMapping()[level]),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )
    # force=True: uvicorn attaches its own root-logger handler before this
    # runs, and plain logging.basicConfig() is a documented no-op once any
    # handler already exists — without force=True, every plain
    # `logging.getLogger(__name__).info(...)` call in the app (gov_registry,
    # detection ingest audit signals, ...) would silently vanish instead of
    # reaching stdout. Found while verifying M12's mTLS audit logging.
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level, force=True)
    _configured = True


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    if not _configured:
        configure_logging()
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger
