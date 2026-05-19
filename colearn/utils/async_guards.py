"""Async/sync boundary guards."""

from __future__ import annotations

import asyncio


def reject_sync_inside_event_loop(caller: str) -> None:
    """Raise RuntimeError if called from within an active asyncio event loop.

    Protects sync entry points that internally call asyncio.run() — nesting
    asyncio.run() inside an active loop is illegal and would deadlock.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return
    raise RuntimeError(f"{caller} cannot run inside an active event loop.")
