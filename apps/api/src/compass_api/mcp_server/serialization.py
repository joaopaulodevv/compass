"""Turning engine results into JSON the agent can read.

The engine returns frozen dataclasses full of `Decimal`, `date`, `UUID` and enums. One
generic converter handles all of them, so adding a field to a result type never means
updating a hand-written mapping that silently drops it.

Amounts become **strings**, exactly as they do over HTTP: a JSON number would hand the
consumer a float to round badly, and a language model reading `"2400.00"` is no more
confused than one reading `2400.0` - while the downstream code that acts on it keeps the
exact value.
"""

from __future__ import annotations

import dataclasses
import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any


def to_jsonable(value: Any) -> Any:
    """Convert engine output into JSON-safe primitives, recursively."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: to_jsonable(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set):
        return [to_jsonable(item) for item in value]
    return value
