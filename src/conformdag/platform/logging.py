"""Structured JSON logging for the platform tier (no new dependencies)."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, cast

from conformdag.security.redaction import credential_name_like, redact_credentials

RESERVED_ATTRS = frozenset(
    {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "taskName",
        "message",
    }
)


def _sanitize_structured_value(value: object) -> object:
    if isinstance(value, str):
        return redact_credentials(value)
    if isinstance(value, Mapping):
        mapping = cast(Mapping[object, object], value)
        sanitized: dict[object, object] = {}
        for key, item in mapping.items():
            sanitized[key] = (
                "[REDACTED]" if isinstance(key, str) and credential_name_like(key) else _sanitize_structured_value(item)
            )
        return sanitized
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        sequence = cast(Sequence[object], value)
        return [_sanitize_structured_value(item) for item in sequence]
    return value


class JsonFormatter(logging.Formatter):
    """Render log records as single-line JSON objects with extra fields."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": _sanitize_structured_value(record.getMessage()),
        }
        for key, value in record.__dict__.items():
            if key not in RESERVED_ATTRS and not key.startswith("_"):
                payload[key] = "[REDACTED]" if credential_name_like(key) else _sanitize_structured_value(value)
        if record.exc_info:
            payload["exc_info"] = _sanitize_structured_value(self.formatException(record.exc_info))
        return json.dumps(payload, default=str)


def install_json_logging() -> None:
    """Attach the JSON formatter to ConformDAG's logger namespace exactly once."""
    logger = logging.getLogger("conformdag")
    logger.propagate = False
    for handler in logger.handlers:
        if isinstance(handler.formatter, JsonFormatter):
            return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
