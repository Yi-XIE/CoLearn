"""Logging context variables for request_id and turn_id injection."""

from __future__ import annotations

import logging
from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
turn_id_var: ContextVar[str] = ContextVar("turn_id", default="-")


class _ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        record.turn_id = turn_id_var.get()
        return True
