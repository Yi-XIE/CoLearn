from __future__ import annotations

import importlib
from pathlib import Path
import sys

import anyio
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from colearn.api.app import app


async def _run_http_checks() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/sessions",
            json={
                "project_id": "proj-api",
                "project_title": "API Project",
                "title": "Session A",
            },
        )
        assert response.status_code == 200
        payload = response.json()["session"]
        assert payload["project_id"] == "proj-api"

        fetched = await client.get(f"/api/v1/sessions/{payload['session_id']}")
        assert fetched.status_code == 200
        assert fetched.json()["session_id"] == payload["session_id"]


def test_http_session_endpoints() -> None:
    anyio.run(_run_http_checks)


def test_websocket_endpoint_exists() -> None:
    routes = getattr(app, "routes", [])
    assert any(getattr(route, "path", "") == "/api/v1/ws" for route in routes)


class FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)


async def _run_websocket_handler_checks() -> None:
    app_module = importlib.import_module("colearn.api.app")
    assert "cancel_turn" in app_module.WS_HANDLERS
    websocket = FakeWebSocket()
    await app_module.handle_ping(websocket)
    assert websocket.sent[-1]["metadata"]["pong"] is True

    await app_module.handle_subscribe_turn(websocket, {"type": "subscribe_turn", "turn_id": "missing-turn"})
    assert websocket.sent[-1]["type"] == "turn_state"
    assert websocket.sent[-1]["metadata"]["status"] == "missing"


def test_websocket_ping_and_unknown_turn_subscription() -> None:
    anyio.run(_run_websocket_handler_checks)


def test_websocket_start_turn_without_runtime_stream_does_not_fake_tool_events() -> None:
    from colearn.learning.response_contract import LearningTurnResult
    app_module = importlib.import_module("colearn.api.app")
    result = LearningTurnResult(final_text="plain answer", stream_events=[], warnings=["no_stream"])
    events, next_seq = app_module._prepare_runtime_stream_events(
        stream_events=list(result.stream_events or []),
        result=result,
        session_id="ws-no-fake",
        turn_id="turn-1",
        seq=3,
    )
    assert events == []
    assert next_seq == 3


async def _run_running_session_check() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/sessions",
            json={
                "project_id": "proj-running",
                "project_title": "Running Project",
                "title": "Session Running",
            },
        )
        payload = response.json()["session"]
        fetched = await client.get(f"/api/v1/sessions/{payload['session_id']}")
        assert fetched.status_code == 200
        assert "active_turns" in fetched.json()


def test_session_detail_contains_active_turns_field() -> None:
    anyio.run(_run_running_session_check)


async def _run_project_checks() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        created = await client.post(
            "/api/v1/projects",
            json={"title": "Project API", "goal": "Learn matrices", "slug": "project-api"},
        )
        assert created.status_code == 200
        project = created.json()["project"]
        assert project["project_id"] == "project-api"

        fetched = await client.get("/api/v1/projects/project-api")
        assert fetched.status_code == 200
        project_payload = fetched.json()["project"]
        assert project_payload["title"] == "Project API"
        assert "board_updated_at" in project_payload
        assert "latest_review_status" in project_payload


def test_project_endpoints() -> None:
    anyio.run(_run_project_checks)


async def _run_schema_compat_checks() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        ui = await client.put("/api/v1/settings/ui", json={"theme": "light", "language": "zh", "ignored": True})
        assert ui.status_code == 200
        assert ui.json()["ui"]["theme"] == "light"

        memory = await client.put("/api/v1/memory", json={"file": "summary", "content": "session summary"})
        assert memory.status_code == 200
        assert memory.json()["summary"] == "session summary"

        rejected = await client.put("/api/v1/memory", json={"file": "other", "content": ""})
        assert rejected.status_code == 422

        llm_options = await client.get("/api/v1/settings/llm-options")
        assert llm_options.status_code == 200
        assert llm_options.json()["active"]["model_id"] == "gpt-5"


def test_schema_payloads_keep_legacy_extra_fields_compatible() -> None:
    anyio.run(_run_schema_compat_checks)
