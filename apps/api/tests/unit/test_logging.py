"""Tests for structured logging."""

from __future__ import annotations

import json
import logging

from compass_api.core.logging import JsonFormatter


def _record(**extra: object) -> logging.LogRecord:
    record = logging.LogRecord(
        name="compass_api.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="goal %s simulated",
        args=("trip",),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_formatter_emits_single_line_json() -> None:
    output = JsonFormatter().format(_record())

    assert "\n" not in output
    payload = json.loads(output)
    assert payload["level"] == "INFO"
    assert payload["logger"] == "compass_api.test"
    assert payload["message"] == "goal trip simulated"
    assert "timestamp" in payload


def test_formatter_includes_extra_fields() -> None:
    payload = json.loads(JsonFormatter().format(_record(user_id="abc-123", check="database")))

    assert payload["user_id"] == "abc-123"
    assert payload["check"] == "database"
