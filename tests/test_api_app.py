from __future__ import annotations

import importlib
import json
from pathlib import Path
import shutil
import sys

import anyio
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from colearn.api.app import app


class ASGIWebSocketClient:
    def __init__(self, app, task_group) -> None:
        self.app = app
        self.task_group = task_group
        self.to_app_send = None
        self.to_app_receive = None
        self.from_app_send = None
        self.from_app_receive = None

    async def connect(self, path: str = "/api/v1/ws") -> None:
        self.to_app_send, self.to_app_receive = anyio.create_memory_object_stream(50)
        self.from_app_send, self.from_app_receive = anyio.create_memory_object_stream(50)
        scope = {
            "type": "websocket",
            "asgi": {"version": "3.0"},
            "scheme": "ws",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": [],
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
            "subprotocols": [],
        }

        async def receive():
            return await self.to_app_receive.receive()

        async def send(message):
            await self.from_app_send.send(message)

        self.task_group.start_soon(self.app, scope, receive, send)
        await self.to_app_send.send({"type": "websocket.connect"})
        accepted = await self.from_app_receive.receive()
        assert accepted["type"] == "websocket.accept"

    async def send_json(self, payload: dict) -> None:
        await self.to_app_send.send({"type": "websocket.receive", "text": json.dumps(payload)})

    async def receive_json(self) -> dict:
        with anyio.fail_after(2):
            while True:
                message = await self.from_app_receive.receive()
                if message["type"] == "websocket.send":
                    return json.loads(message.get("text") or "{}")

    async def disconnect(self) -> None:
        await self.to_app_send.send({"type": "websocket.disconnect", "code": 1000})


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
        assert llm_options.json()["active"]["model_id"] == "deepseek-v4-flash"

        settings_test = await client.post(
            "/api/v1/settings/tests/llm/start",
            json={"catalog": {"version": 1}, "ignored": True},
        )
        assert settings_test.status_code == 200
        payload = settings_test.json()
        assert payload["run_id"].startswith("llm-")
        assert payload["accepted"] is True

        refresh_empty = await client.post("/api/v1/memory/refresh", json={})
        assert refresh_empty.status_code == 200
        assert "changed" in refresh_empty.json()

        refresh_legacy = await client.post("/api/v1/memory/refresh", json={"ignored": True})
        assert refresh_legacy.status_code == 200
        assert "changed" in refresh_legacy.json()


def test_schema_payloads_keep_legacy_extra_fields_compatible() -> None:
    anyio.run(_run_schema_compat_checks)


def test_api_state_services_reset_without_cross_test_leakage() -> None:
    app_module = importlib.import_module("colearn.api.app")
    app_module.settings_service.update_ui(theme="light", language="en")
    app_module.memory_doc_service.update("summary", "leak")
    app_module.skill_service.save_skill("leak", {"description": "", "content": "", "tags": []})

    app_module.settings_service.reset()
    app_module.memory_doc_service.reset()
    app_module.skill_service.reset()

    assert app_module.settings_service.settings()["ui"]["theme"] == "dark"
    assert app_module.memory_doc_service.snapshot()["summary"] == ""
    assert app_module.skill_service.list_skills() == []


async def _run_real_websocket_lifecycle_checks() -> None:
    app_module = importlib.import_module("colearn.api.app")

    async with anyio.create_task_group() as task_group:
        ws = ASGIWebSocketClient(app, task_group)
        await ws.connect()
        await ws.send_json({"type": "ping"})
        assert (await ws.receive_json())["metadata"]["pong"] is True
        await ws.send_json({"type": "subscribe_turn", "turn_id": "missing-real-turn"})
        missing = await ws.receive_json()
        assert missing["type"] == "turn_state"
        assert missing["metadata"]["status"] == "missing"
        await ws.disconnect()
        task_group.cancel_scope.cancel()

    session = app_module.session_store.create_session(
        session_id="ws-cancel-session",
        project_id="ws-project",
        title="WS Cancel",
    )
    session.status = "running"
    session.active_turn_id = "ws-cancel-turn"
    session.active_turns = [{"turn_id": "ws-cancel-turn"}]
    app_module.session_store.save_session(session)
    app_module.turn_index["ws-cancel-turn"] = {"session_id": "ws-cancel-session", "project_id": "ws-project"}

    async with anyio.create_task_group() as task_group:
        ws = ASGIWebSocketClient(app, task_group)
        await ws.connect()
        await ws.send_json({"type": "cancel_turn", "turn_id": "ws-cancel-turn"})
        cancelled = await ws.receive_json()
        assert cancelled["metadata"]["status"] == "cancelled"
        saved = app_module.session_store.get_session("ws-cancel-session")
        assert saved is not None
        assert saved.active_turns == []
        await ws.disconnect()
        task_group.cancel_scope.cancel()


def test_real_websocket_ping_subscribe_and_cancel() -> None:
    anyio.run(_run_real_websocket_lifecycle_checks)


class FakeWebSocketOrchestrator:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    def run_turn(self, **kwargs):
        if self.fail:
            raise RuntimeError("ws orchestrator failed")
        from colearn.learning.response_contract import LearningTurnResult

        return LearningTurnResult(
            final_text=f"WS answer: {kwargs['user_message']}",
            turn_mode_after="EXPLORE",
            warnings=[],
            tool_events=[],
            stream_events=[],
        )


async def _run_real_websocket_start_and_error_checks() -> None:
    app_module = importlib.import_module("colearn.api.app")
    original_orchestrator = app_module.orchestrator
    try:
        app_module.orchestrator = FakeWebSocketOrchestrator()
        async with anyio.create_task_group() as task_group:
            ws = ASGIWebSocketClient(app, task_group)
            await ws.connect()
            await ws.send_json(
                {
                    "type": "start_turn",
                    "session_id": "ws-start-session",
                    "project_id": "ws-project",
                    "project_title": "WS Project",
                    "content": "hello",
                    "language": "zh",
                }
            )
            received = []
            while True:
                event = await ws.receive_json()
                received.append(event["type"])
                if event["type"] == "done":
                    break
            assert "session" in received
            assert "content" in received
            saved = app_module.session_store.get_session("ws-start-session")
            assert saved is not None
            assert saved.active_turns == []
            await ws.disconnect()
            task_group.cancel_scope.cancel()

        app_module.orchestrator = FakeWebSocketOrchestrator(fail=True)
        async with anyio.create_task_group() as task_group:
            ws = ASGIWebSocketClient(app, task_group)
            await ws.connect()
            await ws.send_json(
                {
                    "type": "start_turn",
                    "session_id": "ws-error-session",
                    "project_id": "ws-project",
                    "project_title": "WS Project",
                    "content": "fail",
                    "language": "zh",
                }
            )
            while True:
                event = await ws.receive_json()
                if event["type"] == "error":
                    break
            saved = app_module.session_store.get_session("ws-error-session")
            assert saved is not None
            assert saved.active_turns == []
            assert saved.status == "failed"
            await ws.disconnect()
            task_group.cancel_scope.cancel()
    finally:
        app_module.orchestrator = original_orchestrator


def test_real_websocket_start_turn_and_error_cleanup() -> None:
    anyio.run(_run_real_websocket_start_and_error_checks)


async def _run_auth_checks() -> None:
    app_module = importlib.import_module("colearn.api.app")
    app_module.auth_service.reset()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        first = await client.get("/api/v1/auth/is_first_user")
        assert first.status_code == 200
        assert first.json()["is_first_user"] is True

        register = await client.post(
            "/api/v1/auth/register",
            json={"username": "yi", "password": "secret"},
        )
        assert register.status_code == 200
        assert register.json()["role"] == "admin"
        assert register.json()["is_first_user"] is True
        assert "colearn_session=" in register.headers.get("set-cookie", "")

        duplicate = await client.post(
            "/api/v1/auth/register",
            json={"username": "yi", "password": "secret"},
        )
        assert duplicate.status_code == 409

        status = await client.get("/api/v1/auth/status")
        assert status.status_code == 200
        assert status.json()["authenticated"] is True
        assert status.json()["username"] == "yi"

        logout = await client.post("/api/v1/auth/logout")
        assert logout.status_code == 200

        anonymous = await client.get("/api/v1/auth/status")
        assert anonymous.status_code == 200
        assert anonymous.json()["authenticated"] is False

        failed_login = await client.post(
            "/api/v1/auth/login",
            json={"username": "yi", "password": "wrong"},
        )
        assert failed_login.status_code == 401

        good_login = await client.post(
            "/api/v1/auth/login",
            json={"username": "yi", "password": "secret"},
        )
        assert good_login.status_code == 200
        assert good_login.json()["ok"] is True


def test_auth_endpoints() -> None:
    anyio.run(_run_auth_checks)


async def _run_knowledge_task_checks() -> None:
    app_module = importlib.import_module("colearn.api.app")
    app_module.knowledge_task_service.reset()
    shutil.rmtree(app_module.state_store.root / "knowledge" / "kb-alpha", ignore_errors=True)
    shutil.rmtree(app_module.state_store.root / "knowledge" / "kb-missing", ignore_errors=True)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        create = await client.post(
            "/api/v1/knowledge/create",
            data={
                "name": "kb-alpha",
                "rag_provider": "lightrag",
            },
            files=[("files", ("alpha.txt", b"hello world", "text/plain"))],
        )
        assert create.status_code == 200
        task_id = create.json()["task_id"]

        stream = await client.get(f"/api/v1/knowledge/tasks/{task_id}/stream")
        assert stream.status_code == 200
        text = stream.text
        assert "event: process_log" in text
        assert "event: progress" in text
        assert "event: complete" in text

        listing = await client.get("/api/v1/knowledge/kb-alpha/files")
        assert listing.status_code == 200
        files = listing.json()["files"]
        assert len(files) == 1
        assert files[0]["name"] == "alpha.txt"

        fetched = await client.get("/api/v1/knowledge/kb-alpha/files/alpha.txt")
        assert fetched.status_code == 200
        assert fetched.text == "hello world"

        missing = await client.get("/api/v1/knowledge/kb-alpha/files/missing.txt")
        assert missing.status_code == 404

        reindex_ok = await client.post("/api/v1/knowledge/kb-alpha/reindex")
        assert reindex_ok.status_code == 200
        assert reindex_ok.json()["task_id"]

        reindex_fail = await client.post("/api/v1/knowledge/kb-missing/reindex")
        assert reindex_fail.status_code == 200
        failed_stream = await client.get(
            f"/api/v1/knowledge/tasks/{reindex_fail.json()['task_id']}/stream"
        )
        assert "event: failed" in failed_stream.text


def test_knowledge_task_and_file_endpoints() -> None:
    anyio.run(_run_knowledge_task_checks)


async def _run_settings_events_checks() -> None:
    app_module = importlib.import_module("colearn.api.app")
    app_module.settings_test_service.reset()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        start = await client.post(
            "/api/v1/settings/tests/search/start",
            json={"catalog": {"version": 2}},
        )
        assert start.status_code == 200
        run_id = start.json()["run_id"]

        events = await client.get(f"/api/v1/settings/tests/search/{run_id}/events")
        assert events.status_code == 200
        body = events.text
        assert '"type": "running"' in body
        assert '"type": "completed"' in body

        missing = await client.get("/api/v1/settings/tests/search/missing-run/events")
        assert missing.status_code == 404


def test_settings_test_events_endpoint() -> None:
    anyio.run(_run_settings_events_checks)


async def _run_settings_apply_persistence_checks() -> None:
    app_module = importlib.import_module("colearn.api.app")
    app_module.settings_service.reset()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        catalog = app_module.settings_service.catalog()
        response = await client.post("/api/v1/settings/apply", json={"catalog": catalog})
        assert response.status_code == 200
        assert response.json()["applied"] is True

    settings_path = app_module.state_store.root / "settings_state.json"
    assert settings_path.exists()
    saved = json.loads(settings_path.read_text(encoding="utf-8"))
    assert saved["catalog"]["services"]["llm"]["active_model_id"] == "deepseek-v4-flash"

    env_path = Path.cwd() / ".env"
    assert env_path.exists()
    env_text = env_path.read_text(encoding="utf-8")
    assert "OPENAI_API_BASE=https://api.deepseek.com" in env_text
    assert "OPENAI_MODEL=deepseek-v4-flash" in env_text
    assert "EMBEDDING_BASE_URL=https://api.siliconflow.cn/v1/embeddings" in env_text
    assert "EMBEDDING_MODEL=Qwen/Qwen3-Embedding-8B" in env_text


def test_settings_apply_persists_state_and_env() -> None:
    anyio.run(_run_settings_apply_persistence_checks)
