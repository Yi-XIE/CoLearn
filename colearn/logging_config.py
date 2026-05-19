"""Centralized logging configuration for CoLearn."""

from __future__ import annotations

import logging
import sys


_CONFIGURED = False


def get_logger(name: str) -> logging.Logger:
    global _CONFIGURED
    if not _CONFIGURED:
        _configure_root()
        _CONFIGURED = True
    return logging.getLogger(name)


def _configure_root() -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root = logging.getLogger("colearn")
    root.setLevel(logging.INFO)
    if not root.handlers:
        root.addHandler(handler)
