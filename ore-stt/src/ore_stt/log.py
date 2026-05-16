"""structlog setup (ARCHITECTURE.md §9): JSON lines to stdout."""

from __future__ import annotations

import logging
import sys
from typing import cast

import structlog


def configure_logging(level: str = "INFO") -> None:
    """Configure structlog to emit JSON to stdout. Idempotent enough for startup."""
    min_level = getattr(logging, level.upper(), logging.INFO)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(min_level),
        logger_factory=structlog.PrintLoggerFactory(sys.stdout),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.BoundLogger:
    """Return a bound logger tagged with ``service: ore-stt``."""
    return cast("structlog.BoundLogger", structlog.get_logger(name, service="ore-stt"))
