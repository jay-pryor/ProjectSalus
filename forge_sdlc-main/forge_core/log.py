"""Structured logging for the Forge CLI.

Logs go to stderr so they don't contaminate JSON stdout.
Each CLI invocation gets a correlation_id.
"""

import logging
import sys
import uuid

import structlog


def configure(verbose: bool = False) -> None:
    """Configure structured logging for the current process."""
    log_level = logging.DEBUG if verbose else logging.WARNING

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=False,
    )


def bind_correlation_id(session_id: str | None = None) -> str:
    """Bind a correlation ID to the current context."""
    cid = session_id or str(uuid.uuid4())[:8]
    structlog.contextvars.bind_contextvars(correlation_id=cid)
    return cid


def safe_log(event: str, level: str = "info", **kwargs) -> None:
    """Log without crashing if stderr is closed or logging misconfigured."""
    try:
        getattr(structlog.get_logger(), level)(event, **kwargs)
    except (ValueError, OSError, AttributeError):
        try:
            sys.stderr.write(f"DROPPED LOG: {event} {kwargs}\n")
        except Exception:
            pass
