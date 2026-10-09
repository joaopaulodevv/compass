"""Structured logging setup.

Logs are emitted as single-line JSON so that any log backend (Datadog is the intended
one) can ingest them without the application depending on a vendor SDK.

Financial data is sensitive: log identifiers and outcomes, never raw transactions,
balances or credentials.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any, override

from compass_api.core.config import Settings

_RESERVED_RECORD_KEYS = frozenset(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {
    "asctime",
    "message",
    "taskName",
}


class JsonFormatter(logging.Formatter):
    """Minimal JSON log formatter with support for `extra=` fields."""

    @override
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        payload.update(
            {
                key: value
                for key, value in record.__dict__.items()
                if key not in _RESERVED_RECORD_KEYS
            }
        )
        return json.dumps(payload, default=str)


def configure_logging(settings: Settings) -> None:
    """Install the JSON formatter on the root logger. Idempotent."""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.log_level.value)

    # Uvicorn ships its own handlers; let records bubble up to the root logger instead.
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
