"""Structured request/response JSON logs with safe defaults."""

import logging
import sys
from typing import Any

from pythonjsonlogger.json import JsonFormatter

LOG_FIELDS = (
    "request_id",
    "instance",
    "client_ip",
    "action",
    "account_id",
    "result",
    "latency_ms",
    "status_code",
    "financial_request_id",
)
managed_handler: logging.Handler | None = None


class BankingJsonFormatter(JsonFormatter):
    def add_fields(
        self,
        log_record: dict[str, Any],
        record: logging.LogRecord,
        message_dict: dict[str, Any],
    ) -> None:
        super().add_fields(log_record, record, message_dict)
        for field in LOG_FIELDS:
            log_record.setdefault(field, None)

        log_record.setdefault(
            "timestamp",
            self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
        )


def configure_logging(level: str = "INFO") -> None:
    """Replace only the handler installed by this application."""
    global managed_handler
    root = logging.getLogger()
    root.setLevel(level)

    if managed_handler is not None:
        root.removeHandler(managed_handler)
        managed_handler.close()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(BankingJsonFormatter())
    root.addHandler(handler)
    managed_handler = handler


def database_error_fields(exc: Exception) -> dict[str, str | None]:
    """Log only safe diagnostics: never SQL text, parameters or connection URLs."""
    original = getattr(exc, "orig", None)
    diagnostics = getattr(original, "diag", None)
    return {
        "exception_type": type(exc).__name__,
        "database_exception_type": type(original).__name__ if original else None,
        "sqlstate": getattr(original, "sqlstate", None) or getattr(original, "pgcode", None),
        "constraint_name": getattr(diagnostics, "constraint_name", None),
    }
