from __future__ import annotations

import importlib
import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace

import anyio
import httpx
from colearn.api.session_api import serialize_session_summary
from colearn.memory.store import MemoryEvent

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
        assert payload["mode"] == "chat"
        assert payload["turn_mode"] == "PAUSED"

        fetched = await client.get(f"/api/v1/sessions/{payload['session_id']}")
        assert fetched.status_code == 200
        assert fetched.json()["session_id"] == payload["session_id"]

        untitled = await client.post(
            "/api/v1/sessions",
            json={
                "project_id": "proj-empty-title",
                "project_title": "CoLearn",
            },
        )
        assert untitled.status_code == 200
        untitled_payload = untitled.json()["session"]
        assert untitled_payload["title"] == ""

        renamed = await client.patch(
            f"/api/v1/sessions/{untitled_payload['session_id']}",
            json={"title": "用户输入的第一句话"},
        )
        assert renamed.status_code == 200
        assert renamed.json()["session"]["title"] == "用户输入的第一句话"

        learning = await client.post(
            "/api/v1/sessions",
            json={
                "project_id": "proj-api-learning",
                "project_title": "API Learning Project",
                "mode": "learning",
            },
        )
        assert learning.status_code == 200
        learning_payload = learning.json()["session"]
        assert learning_payload["mode"] == "learning"
        assert learning_payload["turn_mode"] == "LEARN"

        sessions_route = importlib.import_module("colearn.api.routes.sessions")

        class FakeExecutor:
            def __init__(self) -> None:
                self.completed_goal: dict[str, str] | None = None

            def complete_sustained_goal(self, *, session_id: str, recap: str = "") -> dict[str, str]:
                self.completed_goal = {"session_id": session_id, "recap": recap}
                return {"status": "completed"}

        fake_executor = FakeExecutor()
        original_orchestrator = sessions_route.orchestrator
        sessions_route.orchestrator = SimpleNamespace(executor=fake_executor)
        try:
            paused = await client.post(f"/api/v1/sessions/{learning_payload['session_id']}/pause")
            assert paused.status_code == 200
            assert paused.json()["session"]["turn_mode"] == "PAUSED"
            assert fake_executor.completed_goal == {
                "session_id": learning_payload["session_id"],
                "recap": "Learning session paused.",
            }
        finally:
            sessions_route.orchestrator = original_orchestrator

        resumed = await client.post(f"/api/v1/sessions/{learning_payload['session_id']}/resume")
        assert resumed.status_code == 200
        resumed_payload = resumed.json()["session"]
        assert resumed_payload["mode"] == "learning"
        assert resumed_payload["turn_mode"] == "LEARN"
        assert resumed_payload["board_facts"]["current_turn_mode"] == "LEARN"


def test_http_session_endpoints() -> None:
    anyio.run(_run_http_checks)


def test_session_summary_uses_first_user_message_as_default_title() -> None:
    app_module = importlib.import_module("colearn.api.app")
    session = app_module.session_store.create_session(
        session_id="summary-first-user-title",
        project_id="proj-summary-title",
        title="",
    )
    session.messages = [
        {"role": "user", "content": "This is the first user sentence used as the default session title."},
        {"role": "assistant", "content": "Got it, I will help analyze it."},
    ]
    app_module.session_store.save_session(session)

    summary = serialize_session_summary(session, project_service=app_module.project_service)

    assert summary["title"] == "This is the first user sentence used as the default sessi..."
    assert summary["last_message"] == "This is the first user sentence used as the default session title."














def test_turn_mode_maps_to_model_preset() -> None:
    from colearn.learning.state import BoardFacts, ProgressFacts, GapsAndBlockers, ContinuationFacts, StudentSnapshot
    from colearn.learning.state_hooks import policy

    board = BoardFacts(
        current_turn_mode="VERIFY",
        current_progress=ProgressFacts(active_node_id="node-1", active_node_label="Node 1"),
        student_snapshot=StudentSnapshot(),
        gaps_and_blockers=GapsAndBlockers(),
        continuation=ContinuationFacts(),
    )
    decision = policy(board=board, user_message="check")
    assert decision.model_preset == "deep"


def test_turn_request_bridges_workspace_and_model_preset() -> None:
    from colearn.learning.state import BoardFacts, ProgressFacts, GapsAndBlockers, ContinuationFacts, StudentSnapshot, TurnPolicy
    from colearn.runtime_v2.context_bridge import build_learning_turn_request

    request = build_learning_turn_request(
        session_id="s1",
        user_message="hello",
        project_id="p1",
        project_title="P1",
        turn_mode="VERIFY",
        board_facts=BoardFacts(
            current_turn_mode="VERIFY",
            current_progress=ProgressFacts(active_node_id="node-1", active_node_label="Node 1"),
            student_snapshot=StudentSnapshot(),
            gaps_and_blockers=GapsAndBlockers(),
            continuation=ContinuationFacts(),
        ),
        turn_policy=TurnPolicy(turn_mode="VERIFY", model_preset="deep"),
        metadata={"workspace": "D:/Colearn-nightly"},
    )
    assert request.model_preset == "deep"
    assert request.metadata["workspace"] == "D:/Colearn-nightly"


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


async def _run_session_listing_sort_checks() -> None:
    app_module = importlib.import_module("colearn.api.app")
    project_id = "sorting-check-project"
    oldest = app_module.session_store.create_session(
        session_id="sorting-check-oldest",
        project_id=project_id,
        title="oldest",
    )
    oldest.updated_at = 100
    oldest.created_at = 100
    app_module.session_store.save_session(oldest)

    middle = app_module.session_store.create_session(
        session_id="sorting-check-middle",
        project_id=project_id,
        title="middle",
    )
    middle.updated_at = 200
    middle.created_at = 200
    app_module.session_store.save_session(middle)

    newest = app_module.session_store.create_session(
        session_id="sorting-check-newest",
        project_id=project_id,
        title="newest",
    )
    newest.updated_at = 300
    newest.created_at = 300
    app_module.session_store.save_session(newest)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            f"/api/v1/sessions?project_id={project_id}&limit=2",
        )
        assert response.status_code == 200
        sessions = response.json()["sessions"]
        assert [item["session_id"] for item in sessions] == [
            "sorting-check-newest",
            "sorting-check-middle",
        ]


def test_session_listing_orders_by_most_recent_first_before_limit() -> None:
    anyio.run(_run_session_listing_sort_checks)


async def _run_project_checks() -> None:
    app_module = importlib.import_module("colearn.api.app")
    app_module.session_store.create_session(
        session_id="project-api-session",
        project_id="project-api",
        title="Project API Session",
    )
    session = app_module.session_store.get_session("project-api-session")
    assert session is not None
    session.updated_at = 99
    session.board_version = 5
    session.board_facts = {
        "project_id": "project-api",
        "session_id": "project-api-session",
        "board_version": 5,
        "updated_at": "2026-05-22T00:00:00Z",
        "current_turn_mode": "VERIFY",
    }
    session.pending_review = {"summary": "session review", "status": "ready"}
    app_module.session_store.save_session(session)
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
        assert project_payload["board_facts"]["session_id"] == "project-api-session"
        assert project_payload["board_version"] == 5
        assert project_payload["board_updated_at"] == "2026-05-22T00:00:00Z"
        assert project_payload["latest_review"]["summary"] == "session review"


def test_project_endpoints() -> None:
    anyio.run(_run_project_checks)


async def _run_knowledge_list_uses_latest_session_board_check() -> None:
    app_module = importlib.import_module("colearn.api.app")
    project = app_module.project_service.get_project("kb-session-board")
    if project is None:
        project = app_module.project_service.create_project("kb-session-board", title="KB Session Board")
    project.board_facts = {"updated_at": "legacy-project-board"}
    app_module.project_service.save_project(project)
    session = app_module.session_store.create_session(
        session_id="kb-session-board-session",
        project_id="kb-session-board",
        title="KB Session Board Session",
    )
    session.updated_at = 123
    session.board_facts = {"updated_at": "latest-session-board"}
    app_module.session_store.save_session(session)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        listing = await client.get("/api/v1/knowledge/list")
        assert listing.status_code == 200
        item = next(row for row in listing.json()["knowledge_bases"] if row["id"] == "kb-session-board")
        assert item["updated_at"] == "latest-session-board"

        graph = await client.get("/api/v1/knowledge/kb-session-board/graph")
        assert graph.status_code == 200
        library = next(node for node in graph.json()["nodes"] if node["id"] == "library:kb-session-board")
        assert library["metadata"]["updated_at"] == "latest-session-board"


def test_knowledge_list_uses_latest_session_board() -> None:
    anyio.run(_run_knowledge_list_uses_latest_session_board_check)


async def _run_schema_compat_checks() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        ui = await client.put("/api/v1/settings/ui", json={"theme": "light", "language": "zh", "ignored": True})
        assert ui.status_code == 200
        assert ui.json()["ui"]["theme"] == "light"

        memory_settings = await client.put("/api/v1/settings/memory", json={"enabled": False, "ignored": True})
        assert memory_settings.status_code == 200
        assert memory_settings.json()["memory"]["enabled"] is False

        memory = await client.put("/api/v1/memory", json={"file": "summary", "content": "session summary"})
        assert memory.status_code == 200
        assert memory.json()["summary"] == "session summary"

        rejected = await client.put("/api/v1/memory", json={"file": "other", "content": ""})
        assert rejected.status_code == 422

        llm_options = await client.get("/api/v1/settings/llm-options")
        assert llm_options.status_code == 200
        assert llm_options.json()["active"]["model_id"] == "deepseek-v4-flash"

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
    app_module.settings_service.update_memory_settings(enabled=False)

    app_module.settings_service.reset()
    app_module.memory_doc_service.reset()

    assert app_module.settings_service.settings()["ui"]["theme"] == "dark"
    assert app_module.settings_service.memory_settings()["enabled"] is True
    assert app_module.memory_doc_service.snapshot()["summary"] == ""






class FakeWebSocketOrchestrator:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.last_kwargs = {}
        self.executor = None

    def run_turn(self, **kwargs):
        self.last_kwargs = dict(kwargs)
        if self.fail:
            raise RuntimeError("ws orchestrator failed")
        from colearn.learning.response_contract import LearningTurnResult

        if kwargs.get("stream_emit"):
            kwargs["stream_emit"](
                {
                    "type": "content_delta",
                    "content": "live chunk",
                    "metadata": {"phase": "content_delta", "runtime_event_index": 0},
                }
            )
        return LearningTurnResult(
            final_text=f"WS answer: {kwargs['user_message']}",
            turn_mode_after="EXPLORE",
            warnings=[],
            tool_events=[],
            stream_events=[
                {
                    "type": "content_delta",
                    "content": "live chunk",
                    "metadata": {"phase": "content_delta", "runtime_event_index": 0},
                }
            ],
        )


async def _run_ws_cancel_bridge_check() -> None:
    from colearn.api import ws_handler

    sent: list[dict[str, object]] = []

    async def send_event(event: dict[str, object]) -> None:
        sent.append(event)

    class FakeExecutor:
        def __init__(self) -> None:
            self.cancelled_session_id: str | None = None
            self.completed_goal: dict[str, str] | None = None

        def cancel_session(self, session_id: str) -> bool:
            self.cancelled_session_id = session_id
            return True

        def complete_sustained_goal(self, *, session_id: str, recap: str = "") -> dict[str, str]:
            self.completed_goal = {"session_id": session_id, "recap": recap}
            return {"status": "completed"}

    executor = FakeExecutor()
    turn = ws_handler.ActiveTurn(turn_id="turn-1", session_id="session-1", started_at=1.0)
    ws_handler.remember_active_turn(turn)
    original = getattr(ws_handler._deps, "orchestrator", None)
    ws_handler._deps.orchestrator = SimpleNamespace(executor=executor)
    try:
        await ws_handler._handle_cancel_turn(frame={"turn_id": "turn-1"}, send_event=send_event)
        assert turn.cancel_requested is True
        assert executor.cancelled_session_id == "session-1"
        assert executor.completed_goal == {"session_id": "session-1", "recap": "Learning turn cancelled."}
        assert sent == []
    finally:
        ws_handler._deps.orchestrator = original


def test_ws_cancel_turn_bridges_to_executor() -> None:
    anyio.run(_run_ws_cancel_bridge_check)


async def _run_ws_execute_turn_goal_state_check() -> None:
    from colearn.api.ws import service
    from colearn.learning.response_contract import LearningTurnResult

    sent: list[dict[str, object]] = []

    async def send_event(event: dict[str, object]) -> None:
        sent.append(event)

    class FakeOrchestrator:
        async def run_turn_async(self, **kwargs):
            kwargs["stream_emit"](
                {
                    "type": "content_delta",
                    "content": "live",
                    "metadata": {"phase": "content_delta"},
                }
            )
            return LearningTurnResult(
                final_text="done",
                raw_learning_result={
                    "runtime_v2": {
                        "goal_state": {
                            "active": True,
                            "objective": "WS Goal",
                            "ui_summary": "WS Summary",
                        }
                    }
                },
            )

    turn = service.ActiveTurn(turn_id="turn-goal-1", session_id="session-goal-1", started_at=1.0)
    turn.add_subscriber("test", send_event)
    original = getattr(service._deps, "orchestrator", None)
    service._deps.orchestrator = FakeOrchestrator()
    try:
        await service.execute_turn(
            turn=turn,
            user_message="learn websockets",
            project_id="project-goal-1",
            project_title="Project Goal",
            language="zh-CN",
            attachments=[],
            requested_skills=[],
            requested_mode="learning",
        )
    finally:
        service._deps.orchestrator = original

    turn_frames = [item for item in sent if "type" in item]
    frame_types = [item["type"] for item in turn_frames]
    assert frame_types == ["content_delta", "content", "goal_state", "turn_state", "done"]
    goal_frames = [item for item in turn_frames if item["type"] == "goal_state"]
    assert goal_frames[0]["metadata"]["goal_state"] == {
        "active": True,
        "objective": "WS Goal",
        "ui_summary": "WS Summary",
    }
    assert turn_frames[-2]["metadata"]["status"] == "completed"
    assert turn_frames[-1]["metadata"]["status"] == "completed"
    assert sent[-1] == {"event": "session_updated", "chat_id": "session-goal-1"}


def test_ws_execute_turn_emits_goal_state_frame() -> None:
    anyio.run(_run_ws_execute_turn_goal_state_check)










async def _run_knowledge_task_checks() -> None:
    app_module = importlib.import_module("colearn.api.app")
    app_module.knowledge_task_service.reset()
    shutil.rmtree(app_module.state_store.root / "knowledge" / "kb-alpha", ignore_errors=True)
    shutil.rmtree(app_module.state_store.root / "knowledge" / "kb-missing", ignore_errors=True)
    lightrag_config = Path.cwd() / ".colearn" / "lightrag.json"
    lightrag_backup = lightrag_config.read_text(encoding="utf-8") if lightrag_config.exists() else None
    if lightrag_config.exists():
        lightrag_config.unlink()
    ai_seed = Path.cwd() / "artificial-intelligence-notes.md"
    ai_seed.write_text("Artificial intelligence, machine learning, retrieval augmented generation.", encoding="utf-8")
    transport = httpx.ASGITransport(app=app)
    try:
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

            imported = await client.post("/api/v1/knowledge/kb-alpha/import-local")
            assert imported.status_code == 200
            assert imported.json()["task_id"]

            listing_after_import = await client.get("/api/v1/knowledge/kb-alpha/files")
            names = {item["name"] for item in listing_after_import.json()["files"]}
            assert "alpha.txt" in names
            assert "artificial-intelligence-notes.md" in names

            assert lightrag_config.exists()
            lightrag_payload = json.loads(lightrag_config.read_text(encoding="utf-8"))
            assert lightrag_payload["enabled"] is True
            assert lightrag_payload["provider"]["name"] == "local"

            graph = await client.get("/api/v1/knowledge/kb-alpha/graph")
            assert graph.status_code == 200
            graph_payload = graph.json()
            assert isinstance(graph_payload["nodes"], list)
            assert isinstance(graph_payload["edges"], list)
            assert graph_payload["visualization_url"] is None
            assert any(
                node["id"] == "library:kb-alpha" and node["kind"] == "library"
                for node in graph_payload["nodes"]
            )
            assert any(
                node["id"] == "file:kb-alpha:alpha.txt" and node["kind"] == "file"
                for node in graph_payload["nodes"]
            )
            assert any(
                node["label"] == "Alpha" and node["kind"] == "concept"
                for node in graph_payload["nodes"]
            )
            assert any(
                edge["source"] == "library:kb-alpha"
                and edge["target"] == "file:kb-alpha:alpha.txt"
                and edge["kind"] == "contains"
                for edge in graph_payload["edges"]
            )
            assert any(edge["kind"] == "mentions" for edge in graph_payload["edges"])

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
    finally:
        ai_seed.unlink(missing_ok=True)
        if lightrag_backup is None:
            lightrag_config.unlink(missing_ok=True)
        else:
            lightrag_config.write_text(lightrag_backup, encoding="utf-8")


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




async def _run_memory_summary_checks() -> None:
    app_module = importlib.import_module("colearn.api.app")
    app_module.memory_doc_service.reset()
    app_module.memory_doc_service.update("summary", "已沉淀的长期记忆")
    session = app_module.session_store.create_session(
        session_id="memory-summary-session",
        project_id="memory-summary-project",
        title="Memory Summary",
    )
    session.continuation_prompt = "继续验证关键结论。"
    session.board_facts = {
        "continuation": {"next_prompt_hint": "继续验证关键结论。"},
        "gaps_and_blockers": {
            "critical_blockers": [{"id": "blk-1", "desc": "缺少证据支持"}],
        },
        "evidence_refs": [{"source_ref": "note.md", "tool_name": "lightrag"}],
    }
    app_module.session_store.save_session(session)
    app_module.orchestrator.memory_store.append(
        MemoryEvent(
            event_id="evt-1",
            kind="review_written",
            payload={"summary": "需要进一步核对证据", "session_id": session.session_id},
        )
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/memory/summary")
        assert response.status_code == 200
        payload = response.json()
        assert payload["summary"] == "已沉淀的长期记忆"
        assert payload["current_continuity"] == "继续验证关键结论。"
        assert payload["blockers"][0]["label"] == "缺少证据支持"
        assert payload["long_term_facts"][0]["label"] == "note.md"
        assert payload["recent_events"][0]["summary"] == "需要进一步核对证据"


def test_memory_summary_endpoint() -> None:
    anyio.run(_run_memory_summary_checks)


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
    assert "DEEPSEEK_API_BASE=https://api.deepseek.com" in env_text
    assert "DEEPSEEK_MODEL=deepseek-v4-flash" in env_text
    assert "EMBEDDING_BASE_URL=https://api.siliconflow.cn/v1/embeddings" in env_text
    assert "EMBEDDING_MODEL=Qwen/Qwen3-Embedding-8B" in env_text

    config_path = Path(app_module.settings_service.settings()["runtime"]["config_path"])
    assert config_path.exists()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    assert config["agents"]["defaults"]["provider"] == "deepseek"
    assert config["agents"]["defaults"]["model"] == "deepseek-v4-flash"
    assert config["providers"] == {
        "deepseek": {
            "apiKey": "${DEEPSEEK_API_KEY}",
            "apiBase": "https://api.deepseek.com",
        }
    }


def test_settings_apply_persists_state_and_env() -> None:
    anyio.run(_run_settings_apply_persistence_checks)
