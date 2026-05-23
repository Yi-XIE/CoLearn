"""Test FastAPI lifespan shutdown hooks."""

from __future__ import annotations

import importlib

import anyio

app_module = importlib.import_module("colearn.api.app")
deps = importlib.import_module("colearn.api.dependencies")


def test_lifespan_shutdown_calls_orchestrator(monkeypatch):
    shutdown_called: dict[str, bool] = {}

    class FakeOrchestrator:
        def shutdown(self, timeout: float = 5.0) -> None:
            shutdown_called["orchestrator"] = True

    monkeypatch.setattr(deps, "orchestrator", FakeOrchestrator())

    async def exercise() -> None:
        async with app_module.lifespan(app_module.app):
            pass

    anyio.run(exercise)

    assert shutdown_called.get("orchestrator") is True


def test_lifespan_swallows_shutdown_errors(monkeypatch):
    class ExplodingOrchestrator:
        def shutdown(self, timeout: float = 5.0) -> None:
            raise RuntimeError("boom")

    monkeypatch.setattr(deps, "orchestrator", ExplodingOrchestrator())

    async def exercise() -> None:
        async with app_module.lifespan(app_module.app):
            pass

    anyio.run(exercise)
