"""Structured logging configuration for NetBox DeepAgents."""

import logging
import os
import sys
from typing import Any

import structlog
from rich.console import Console
from rich.logging import RichHandler


def setup_logging(level: str = "INFO") -> None:
    """Configure structured logging with rich output."""
    # Get log level from environment or parameter
    log_level = getattr(logging, os.getenv("LOG_LEVEL", level).upper())

    # Configure standard logging for libraries
    logging.basicConfig(
        level=log_level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[
            RichHandler(
                console=Console(stderr=True),
                rich_tracebacks=True,
                show_time=True,
                show_path=False,
            )
        ],
    )

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.dev.ConsoleRenderer() if sys.stderr.isatty() else structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    """Get a configured logger instance."""
    return structlog.get_logger(name)


class MetricsLogger:
    """Logger specifically for metrics tracking."""

    def __init__(self, name: str = "metrics"):
        self.logger = get_logger(name)

    def log_query(self, query: str, success: bool, duration: float, **kwargs: Any) -> None:
        """Log a query with its result and metrics."""
        self.logger.info(
            "query_executed",
            query=query[:100],  # Truncate long queries
            success=success,
            duration_ms=int(duration * 1000),
            **kwargs,
        )

    def log_filter_error(self, filter_pattern: str, error: str, recovered: bool) -> None:
        """Log a filter error and recovery attempt."""
        self.logger.warning(
            "filter_error",
            filter=filter_pattern,
            error=error[:200],
            recovered=recovered,
        )

    def log_model_switch(self, from_model: str, to_model: str, reason: str) -> None:
        """Log a model switch/fallback."""
        self.logger.info(
            "model_switched",
            from_model=from_model,
            to_model=to_model,
            reason=reason,
        )
