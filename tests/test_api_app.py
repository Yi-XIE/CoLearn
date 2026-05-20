from __future__ import annotations

import importlib
import json
from pathlib import Path
import shutil
import sys

import anyio
import httpx
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

        fetched = await client.get(f"/api/v1/sessions/{payload['session_id']}")
        assert fetched.status_code == 200
        assert fetched.json()["session_id"] == payload["session_id"]


def test_http_session_endpoints() -> None:
    anyio.run(_run_http_checks)














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

    app_module.settings_service.reset()
    app_module.memory_doc_service.reset()

    assert app_module.settings_service.settings()["ui"]["theme"] == "dark"
    assert app_module.memory_doc_service.snapshot()["summary"] == ""






class FakeWebSocketOrchestrator:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.last_kwargs = {}

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

        graph = await client.get("/api/v1/knowledge/kb-alpha/graph")
        assert graph.status_code == 200
        graph_payload = graph.json()
        assert isinstance(graph_payload["nodes"], list)
        assert isinstance(graph_payload["edges"], list)
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


def test_settings_apply_persists_state_and_env() -> None:
    anyio.run(_run_settings_apply_persistence_checks)
