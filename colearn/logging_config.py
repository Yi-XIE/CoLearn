"""Centralized logging configuration for CoLearn."""

from __future__ import annotations

import json
import logging
import os
import sys

from colearn.logging_context import _ContextFilter

_CONFIGURED = False
_LOG_FORMAT = os.getenv("COLEARN_LOG_FORMAT", "text")


def get_logger(name: str) -> logging.Logger:
    global _CONFIGURED
    if not _CONFIGURED:
        _configure_root()
        _CONFIGURED = True
    return logging.getLogger(name)


def _configure_root() -> None:
    handler = logging.StreamHandler(sys.stderr)
    if _LOG_FORMAT == "json":
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s %(levelname)-5s [%(name)s] [req=%(request_id)s turn=%(turn_id)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
    handler.addFilter(_ContextFilter())
    root = logging.getLogger("colearn")
    root.setLevel(logging.INFO)
    if not root.handlers:
        root.addHandler(handler)


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", "-"),
            "turn_id": getattr(record, "turn_id", "-"),
            "msg": record.getMessage(),
        }, ensure_ascii=False)
