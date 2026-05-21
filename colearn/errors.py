"""CoLearn exception hierarchy for structured error handling."""

from __future__ import annotations


class CoLearnError(Exception):
    """Base exception for all CoLearn errors."""


class CoLearnTransientError(CoLearnError):
    """Transient failure that may succeed on retry (network timeout, temporary unavailability)."""


class CoLearnPermanentError(CoLearnError):
    """Permanent failure that will not resolve with retries (config error, missing resource)."""


class CoLearnDegradedError(CoLearnError):
    """Non-fatal failure where the system can continue with reduced functionality."""
