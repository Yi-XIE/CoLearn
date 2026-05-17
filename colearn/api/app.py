"""Minimal FastAPI + WebSocket entrypoint for the CoLearn backend."""

from __future__ import annotations

import json
import mimetypes
from pathlib import Path
import time
from typing import Any
from uuid import uuid4

from anyio import to_thread
from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse

from colearn.api.state import (
    AuthStateService,
    KnowledgeTaskService,
    MemoryDocStateService,
    SettingsStateService,
    SettingsTestRunService,
    SkillStateService,
)
from colearn.api.schemas import (
    AuthLoginPayload,
    AuthRegisterPayload,
    CancelTurnPayload,
    MemoryFilePayload,
    MemoryRefreshPayload,
    MemoryUpdatePayload,
    PingPayload,
    ProjectAnchorPayload,
    ProjectCreatePayload,
    ProjectSourcesPayload,
    ProjectUpdatePayload,
    RegeneratePayload,
    SkillPayload,
    SkillTagPayload,
    SkillUpdatePayload,
    SessionCreatePayload,
    SessionUpdatePayload,
    SettingsCatalogPayload,
    SettingsTestStartPayload,
    SettingsUiPayload,
    StartTurnPayload,
    SubscribeTurnPayload,
)
from colearn.api.session_api import serialize_session_detail, serialize_session_summary, touch_session
from colearn.app.learning_orchestrator import LearningOrchestrator
from colearn.projects.models import LearningProject
from colearn.projects.service import LearningProjectService
from colearn.sessions.store import SessionStore
from colearn.storage import JsonStateStore
from colearn.storage.project_session_store import (
    build_stateful_memory_store,
    build_stateful_project_service,
    build_stateful_session_store,
)


state_store = JsonStateStore()
project_service = build_stateful_project_service(state_store.root)
session_store = build_stateful_session_store(state_store.root)
orchestrator = LearningOrchestrator(
    project_service=project_service,
    session_store=session_store,
    memory_store=build_stateful_memory_store(state_store.root),
)

app = FastAPI(title="CoLearn API", version="0.1.0")
turn_streams: dict[str, list[dict[str, Any]]] = {}
turn_index: dict[str, dict[str, Any]] = {}
settings_service = SettingsStateService(JsonStateStore(state_store.root), Path.cwd() / ".env")
memory_doc_service = MemoryDocStateService()
skill_service = SkillStateService()
auth_service = AuthStateService(JsonStateStore(state_store.root))
knowledge_task_service = KnowledgeTaskService(state_root=state_store.root)
settings_test_service = SettingsTestRunService()
AUTH_COOKIE_NAME = "colearn_session"


def _ws_event(
    *,
    type: str,
    source: str = "server",
    stage: str = "turn",
    content: str = "",
    metadata: dict[str, Any] | None = None,
    session_id: str = "",
    turn_id: str = "",
    seq: int = 0,
) -> dict[str, Any]:
    payload = dict(metadata or {})
    payload.setdefault("phase", type)
    payload.setdefault("warnings", [])
    payload.setdefault("tool_events", [])
    return {
        "type": type,
        "source": source,
        "stage": stage,
        "content": content,
        "metadata": payload,
        "session_id": session_id,
        "turn_id": turn_id,
        "seq": seq,
        "timestamp": time.time(),
    }


async def _send_ws_event(websocket: WebSocket, event: dict[str, Any]) -> None:
    turn_id = str(event.get("turn_id") or "")
    if turn_id:
        turn_streams.setdefault(turn_id, []).append(event)
    await websocket.send_json(event)


def _json_sse(events: list[dict[str, Any]]):
    def generate():
        for item in events:
            event_name = str(item.get("event") or "message")
            payload = json.dumps(item.get("data") or {}, ensure_ascii=False)
            yield f"event: {event_name}\ndata: {payload}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


def _message_sse(events: list[dict[str, Any]]):
    def generate():
        for item in events:
            payload = json.dumps(item, ensure_ascii=False)
            yield f"data: {payload}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


def _auth_status_payload(user: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "enabled": True,
        "authenticated": bool(user),
        "user_id": str((user or {}).get("user_id") or ""),
        "username": str((user or {}).get("username") or ""),
        "role": str((user or {}).get("role") or ""),
        "is_admin": bool((user or {}).get("is_admin")),
    }


def _latest_session() -> Any | None:
    sessions = session_store.list_sessions()
    if not sessions:
        return None
    for session in reversed(sessions):
        if str(getattr(session, "continuation_prompt", "") or "").strip():
            return session
    return sessions[-1]


def _extract_blocker_summaries(board_facts: dict[str, Any] | None) -> list[dict[str, str]]:
    blockers = list(dict(board_facts or {}).get("gaps_and_blockers", {}).get("critical_blockers", []) or [])
    results: list[dict[str, str]] = []
    for item in blockers[:6]:
        if isinstance(item, dict):
            label = str(item.get("desc") or item.get("id") or "").strip()
            detail = str(item.get("status") or "critical").strip()
        else:
            label = str(item).strip()
            detail = "critical"
        if label:
            results.append({"label": label, "detail": detail})
    return results


def _current_user(request: Request) -> dict[str, Any] | None:
    return auth_service.user_for_session(request.cookies.get(AUTH_COOKIE_NAME))


def _normalize_uploads(files: UploadFile | list[UploadFile] | None) -> list[UploadFile]:
    if files is None:
        return []
    if isinstance(files, list):
        return files
    return [files]


async def handle_ping(websocket: WebSocket) -> None:
    await websocket.send_json(
        {
            "type": "progress",
            "source": "server",
            "stage": "",
            "content": "",
            "metadata": {"pong": True},
            "timestamp": 0,
        }
    )


def _coerce_subscribe_turn_payload(payload: SubscribeTurnPayload | dict[str, Any]) -> SubscribeTurnPayload:
    if isinstance(payload, SubscribeTurnPayload):
        return payload
    return SubscribeTurnPayload.model_validate(payload)


def _coerce_cancel_turn_payload(payload: CancelTurnPayload | dict[str, Any]) -> CancelTurnPayload:
    if isinstance(payload, CancelTurnPayload):
        return payload
    return CancelTurnPayload.model_validate(payload)


def _coerce_ping_payload(payload: PingPayload | dict[str, Any] | None) -> PingPayload:
    if isinstance(payload, PingPayload):
        return payload
    return PingPayload.model_validate(payload or {"type": "ping"})


async def handle_subscribe_turn(websocket: WebSocket, payload: SubscribeTurnPayload | dict[str, Any]) -> None:
    resolved = _coerce_subscribe_turn_payload(payload)
    turn_id = str(resolved.turn_id or "").strip()
    after_seq = int(resolved.after_seq or 0)
    events = list(turn_streams.get(turn_id) or [])
    if not events:
        record = turn_index.get(turn_id) or {}
        await websocket.send_json(
            _ws_event(
                type="turn_state",
                content="",
                metadata={"phase": "subscribe", "status": "missing", "warnings": ["turn_not_found"]},
                session_id=str(record.get("session_id") or ""),
                turn_id=turn_id,
            )
        )
        return
    for event in events:
        if int(event.get("seq") or 0) > after_seq:
            await websocket.send_json(event)


async def handle_cancel_turn(websocket: WebSocket, payload: CancelTurnPayload | dict[str, Any]) -> None:
    resolved = _coerce_cancel_turn_payload(payload)
    turn_id = str(resolved.turn_id or "").strip()
    record = turn_index.get(turn_id) or {}
    session_id = str(record.get("session_id") or "")
    if session_id:
        session = session_store.get_session(session_id)
        if session is not None:
            session.status = "cancelled"
            session.active_turn_id = None
            session.active_turns = []
            touch_session(session)
            session_store.save_session(session)
    await _send_ws_event(
        websocket,
        _ws_event(
            type="done",
            content="",
            metadata={"phase": "cancelled", "status": "cancelled"},
            session_id=session_id,
            turn_id=turn_id,
            seq=9999,
        ),
    )


async def _send_regenerate_rejected(websocket: WebSocket, session_id: str) -> None:
    await websocket.send_json(
        _ws_event(
            type="error",
            stage="",
            content="Nothing to regenerate.",
            metadata={"turn_terminal": True, "status": "rejected", "reason": "nothing_to_regenerate"},
            session_id=session_id,
            seq=1,
        )
    )


async def _handle_ping_message(websocket: WebSocket, payload: PingPayload | dict[str, Any] | None) -> None:
    _ = _coerce_ping_payload(payload)
    await handle_ping(websocket)


WS_HANDLERS = {
    "ping": _handle_ping_message,
    "subscribe_turn": handle_subscribe_turn,
    "resume_from": handle_subscribe_turn,
    "cancel_turn": handle_cancel_turn,
}


def _prepare_runtime_stream_events(
    *,
    stream_events: list[dict[str, Any]],
    result: Any,
    session_id: str,
    turn_id: str,
    seq: int,
) -> tuple[list[dict[str, Any]], int]:
    prepared: list[dict[str, Any]] = []
    for item in stream_events:
        event = dict(item)
        metadata = dict(event.get("metadata") or {})
        metadata.setdefault("phase", str(event.get("type") or "event"))
        metadata.setdefault("warnings", list(getattr(result, "warnings", []) or []))
        metadata.setdefault("tool_events", list(getattr(result, "tool_events", []) or []))
        event["metadata"] = metadata
        event.setdefault("session_id", session_id)
        event.setdefault("turn_id", turn_id)
        event.setdefault("seq", seq)
        event.setdefault("timestamp", time.time())
        prepared.append(event)
        seq = int(event.get("seq") or seq) + 1
    return prepared, seq


def _append_ws_stream_events(
    *,
    turn_id: str,
    session_id: str,
    result: Any,
    seq: int,
) -> list[dict[str, Any]]:
    stream_events = list(result.stream_events or [])
    prepared_stream_events, seq = _prepare_runtime_stream_events(
        stream_events=stream_events,
        result=result,
        session_id=session_id,
        turn_id=turn_id,
        seq=seq,
    )
    for item in prepared_stream_events:
        turn_streams[turn_id].append(item)
    return prepared_stream_events


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True}


@app.get("/api/v1/system/status")
def system_status() -> dict[str, Any]:
    catalog = settings_service.catalog()
    services = dict(catalog.get("services") or {})
    llm_profile, llm_model = settings_service._resolve_active_selection(services.get("llm"))
    embedding_profile, embedding_model = settings_service._resolve_active_selection(services.get("embedding"))
    return {
        "backend": {"status": "running", "timestamp": str(int(time.time()))},
        "llm": {"status": "ready", "model": str(llm_model.get("model") or "")},
        "embeddings": {"status": "ready", "model": str(embedding_model.get("model") or "")},
        "search": {"status": "ready", "provider": "brave"},
        "services": {
            "api": "ready",
            "sessions": "in_memory",
            "projects": "in_memory",
            "retrieval": "tool_mode",
        },
    }


@app.get("/api/v1/settings")
def get_settings() -> dict[str, Any]:
    return settings_service.settings()


@app.get("/api/v1/settings/catalog")
def get_settings_catalog() -> dict[str, Any]:
    return {"catalog": settings_service.catalog()}


@app.get("/api/v1/settings/providers")
def get_settings_providers() -> dict[str, Any]:
    return {"providers": settings_service.providers()}


@app.get("/api/v1/settings/llm-options")
def get_llm_options() -> dict[str, Any]:
    catalog = settings_service.catalog()
    llm = dict((catalog.get("services") or {}).get("llm") or {})
    profiles = list(llm.get("profiles") or [])
    active = {
        "profile_id": str(llm.get("active_profile_id") or ""),
        "model_id": str(llm.get("active_model_id") or ""),
    }
    options: list[dict[str, Any]] = []
    for profile in profiles:
        for model in list(profile.get("models") or []):
            options.append(
                {
                    "profile_id": str(profile.get("id") or ""),
                    "profile_label": str(profile.get("name") or ""),
                    "model_id": str(model.get("id") or ""),
                    "model_label": str(model.get("name") or model.get("model") or ""),
                    "provider": str(profile.get("binding") or "openai"),
                    "is_default": (
                        str(profile.get("id") or "") == active["profile_id"]
                        and str(model.get("id") or "") == active["model_id"]
                    ),
                }
            )
    return {"active": active, "options": options}


@app.get("/api/v1/skills/list")
def list_skills() -> dict[str, Any]:
    return {"skills": skill_service.list_skills()}


@app.get("/api/v1/skills/{name}")
def get_skill(name: str) -> dict[str, Any]:
    record = skill_service.get_skill(name)
    if not record:
        raise HTTPException(status_code=404, detail="Skill not found")
    return {
        "name": name,
        "description": str(record.get("description") or ""),
        "content": str(record.get("content") or ""),
        "tags": list(record.get("tags") or []),
    }


@app.post("/api/v1/skills/create")
def create_skill(payload: SkillPayload) -> dict[str, Any]:
    skill_service.save_skill(payload.name, {
        "description": payload.description,
        "content": payload.content,
        "tags": list(payload.tags),
    })
    return {
        "name": payload.name,
        "description": payload.description,
        "content": payload.content,
        "tags": list(payload.tags),
    }


@app.put("/api/v1/skills/{name}")
def update_skill(name: str, payload: SkillUpdatePayload) -> dict[str, Any]:
    record = skill_service.get_skill(name)
    if not record:
        raise HTTPException(status_code=404, detail="Skill not found")
    new_name = payload.rename_to or name
    record["description"] = payload.description if payload.description is not None else record.get("description", "")
    record["content"] = payload.content if payload.content is not None else record.get("content", "")
    record["tags"] = list(payload.tags) if payload.tags else list(record.get("tags") or [])
    if new_name != name:
        skill_service.delete_skill(name)
    skill_service.save_skill(new_name, record)
    return {"name": new_name, **record}


@app.delete("/api/v1/skills/{name}")
def delete_skill(name: str) -> dict[str, Any]:
    skill_service.delete_skill(name)
    return {"deleted": True}


@app.get("/api/v1/skills/tags/list")
def list_skill_tags() -> dict[str, Any]:
    return {"tags": skill_service.list_tags()}


@app.post("/api/v1/skills/tags/create")
def create_skill_tag(payload: SkillTagPayload) -> dict[str, Any]:
    skill_service.save_tag(payload.name)
    return {"name": payload.name}


@app.put("/api/v1/skills/tags/{old_name}")
def rename_skill_tag(old_name: str, payload: SkillTagPayload) -> dict[str, Any]:
    new_name = payload.rename_to or payload.name or old_name
    skill_service.rename_tag(old_name, new_name)
    return {"name": new_name}


@app.delete("/api/v1/skills/tags/{name}")
def delete_skill_tag(name: str) -> dict[str, Any]:
    skill_service.delete_tag(name)
    return {"deleted": True}


@app.put("/api/v1/settings/ui")
def update_settings_ui(payload: SettingsUiPayload) -> dict[str, Any]:
    return {"ui": settings_service.update_ui(theme=payload.theme, language=payload.language)}


@app.put("/api/v1/settings/catalog")
def update_settings_catalog(payload: SettingsCatalogPayload) -> dict[str, Any]:
    catalog = payload.catalog
    if isinstance(catalog, dict):
        return {"catalog": settings_service.update_catalog(catalog)}
    return {"catalog": settings_service.catalog()}


@app.post("/api/v1/settings/apply")
def apply_settings_catalog(payload: SettingsCatalogPayload) -> dict[str, Any]:
    catalog = payload.catalog
    return {"catalog": settings_service.apply_catalog(catalog if isinstance(catalog, dict) else None), "applied": True}


@app.post("/api/v1/settings/tests/{service}/start")
def start_settings_test(service: str, payload: SettingsTestStartPayload) -> dict[str, Any]:
    run = settings_test_service.create_run(service, payload.catalog if isinstance(payload.catalog, dict) else {})
    return {"run_id": run["run_id"], "detail": "", "accepted": True}


@app.get("/api/v1/settings/tests/{service}/{run_id}/events")
def settings_test_events(service: str, run_id: str) -> StreamingResponse:
    run = settings_test_service.get_run(run_id)
    if not run or run.get("service") != service:
        raise HTTPException(status_code=404, detail="Test run not found")
    return _message_sse(list(run.get("events") or []))


@app.get("/api/v1/auth/status")
def auth_status(request: Request) -> dict[str, Any]:
    return _auth_status_payload(_current_user(request))


@app.post("/api/v1/auth/login")
def auth_login(payload: AuthLoginPayload, response: Response) -> dict[str, Any]:
    user = auth_service.authenticate(payload.username, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = auth_service.create_session(str(user.get("username") or ""))
    response.set_cookie(AUTH_COOKIE_NAME, token, httponly=True, samesite="lax", path="/")
    return {"ok": True, "user": _auth_status_payload(user)}


@app.post("/api/v1/auth/register")
def auth_register(payload: AuthRegisterPayload, response: Response) -> dict[str, Any]:
    try:
        user = auth_service.register(payload.username, payload.password)
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    token = auth_service.create_session(str(user.get("username") or ""))
    response.set_cookie(AUTH_COOKIE_NAME, token, httponly=True, samesite="lax", path="/")
    return {
        "ok": True,
        "role": user["role"],
        "is_first_user": bool(user.get("is_first_user")),
    }


@app.get("/api/v1/auth/is_first_user")
def auth_is_first_user() -> dict[str, Any]:
    return {"is_first_user": auth_service.is_first_user()}


@app.post("/api/v1/auth/logout")
def auth_logout(request: Request, response: Response) -> dict[str, Any]:
    token = request.cookies.get(AUTH_COOKIE_NAME)
    if token:
        auth_service.delete_session(token)
    response.delete_cookie(AUTH_COOKIE_NAME, path="/")
    return {"ok": True}


@app.get("/api/v1/knowledge/list")
def list_knowledge_bases() -> dict[str, Any]:
    projects = project_service.list_projects()
    knowledge_bases = [
        {
            "id": project.project_id,
            "name": project.title,
            "source_count": len(project.source_refs or []),
            "status": str((project.retrieval_profile or {}).get("last_retrieval_status") or "empty"),
            "provider": str((project.retrieval_profile or {}).get("provider") or "lightrag"),
            "updated_at": str((project.board_facts or {}).get("updated_at") or ""),
            "files": knowledge_task_service.list_files(project.project_id),
        }
        for project in projects
    ]
    return {"knowledge_bases": knowledge_bases}


@app.get("/api/v1/knowledge/rag-providers")
def list_rag_providers() -> dict[str, Any]:
    return {
        "providers": [
            {
                "id": "lightrag",
                "label": "LightRAG",
                "status": "configured",
            }
        ]
    }


@app.get("/api/v1/knowledge/supported-file-types")
def list_supported_file_types() -> dict[str, Any]:
    return {
        "extensions": [
            ".md",
            ".txt",
            ".pdf",
            ".docx",
            ".pptx",
            ".xlsx",
        ],
        "accept": ".md,.txt,.pdf,.docx,.pptx,.xlsx",
        "max_file_size_bytes": 100 * 1024 * 1024,
        "max_pdf_size_bytes": 50 * 1024 * 1024,
    }


@app.get("/api/v1/knowledge/{name}/files")
def list_knowledge_files(name: str) -> dict[str, Any]:
    return {"files": knowledge_task_service.list_files(name)}


@app.get("/api/v1/knowledge/{name}/files/{file_path:path}")
def get_knowledge_file(name: str, file_path: str) -> FileResponse:
    target = knowledge_task_service.resolve_file(name, file_path)
    if target is None:
        raise HTTPException(status_code=404, detail="Knowledge file not found")
    media_type, _ = mimetypes.guess_type(str(target))
    return FileResponse(target, media_type=media_type or "application/octet-stream", filename=target.name)


@app.post("/api/v1/knowledge/create")
async def create_knowledge_base(
    name: str = Form(...),
    rag_provider: str = Form("lightrag"),
    files: UploadFile | list[UploadFile] | None = File(None),
) -> dict[str, Any]:
    uploads: list[tuple[str, bytes, str | None]] = []
    for item in _normalize_uploads(files):
        uploads.append((item.filename or "upload.bin", await item.read(), item.content_type))
    saved = knowledge_task_service.save_files(name, uploads)
    project = project_service.get_project(name) or project_service.create_project(name, title=name)
    project.title = name
    project.source_refs = [str(file["path"]) for file in saved]
    project.retrieval_profile = {
        **dict(project.retrieval_profile or {}),
        "provider": rag_provider,
        "last_retrieval_status": "ready",
    }
    project_service.save_project(project)
    task = knowledge_task_service.create_task(
        kb_name=name,
        kind="create",
        message="Knowledge base created",
        files=saved,
        should_fail=False,
    )
    return {"task_id": task["task_id"], "message": task["message"]}


@app.post("/api/v1/knowledge/{name}/upload")
async def upload_knowledge_files(
    name: str,
    rag_provider: str = Form(""),
    files: UploadFile | list[UploadFile] | None = File(None),
) -> dict[str, Any]:
    uploads: list[tuple[str, bytes, str | None]] = []
    for item in _normalize_uploads(files):
        uploads.append((item.filename or "upload.bin", await item.read(), item.content_type))
    saved = knowledge_task_service.save_files(name, uploads)
    project = project_service.get_project(name) or project_service.create_project(name, title=name)
    existing = {str(path) for path in project.source_refs}
    existing.update(str(file["path"]) for file in saved)
    project.source_refs = sorted(existing)
    project.retrieval_profile = {
        **dict(project.retrieval_profile or {}),
        "provider": rag_provider or str((project.retrieval_profile or {}).get("provider") or "lightrag"),
        "last_retrieval_status": "ready",
    }
    project_service.save_project(project)
    task = knowledge_task_service.create_task(
        kb_name=name,
        kind="upload",
        message=f"Uploaded files to {name}",
        files=saved,
        should_fail=False,
    )
    return {"task_id": task["task_id"], "message": task["message"]}


@app.put("/api/v1/knowledge/default/{name}")
def set_default_knowledge_base(name: str) -> dict[str, Any]:
    return {"ok": True, "default": name}


@app.post("/api/v1/knowledge/{name}/reindex")
def reindex_knowledge_base(name: str) -> dict[str, Any]:
    files = knowledge_task_service.list_files(name)
    if not files:
        task = knowledge_task_service.create_task(
            kb_name=name,
            kind="reindex",
            message=f"Reindex failed for {name}",
            files=[],
            should_fail=True,
        )
        return {"task_id": task["task_id"], "message": task["message"]}
    project = project_service.get_project(name) or project_service.create_project(name, title=name)
    project.retrieval_profile = {
        **dict(project.retrieval_profile or {}),
        "last_retrieval_status": "ready",
    }
    project_service.save_project(project)
    task = knowledge_task_service.create_task(
        kb_name=name,
        kind="reindex",
        message=f"Reindex started for {name}",
        files=files,
        should_fail=False,
    )
    return {"task_id": task["task_id"], "message": task["message"]}


@app.delete("/api/v1/knowledge/{name}")
def delete_knowledge_base(name: str) -> dict[str, Any]:
    return {"deleted": True, "name": name}


@app.get("/api/v1/knowledge/tasks/{task_id}/stream")
def knowledge_task_stream(task_id: str) -> StreamingResponse:
    task = knowledge_task_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Knowledge task not found")
    return _json_sse(knowledge_task_service.stream_events(task_id))


@app.websocket("/api/v1/knowledge/{name}/progress/ws")
async def knowledge_progress_ws(websocket: WebSocket, name: str, task_id: str | None = None) -> None:
    await websocket.accept()
    task = knowledge_task_service.latest_for_kb(name, task_id=task_id)
    if task is None:
        await websocket.send_json(
            {
                "task_id": task_id or "",
                "stage": "idle",
                "message": "",
                "current": 0,
                "total": 0,
                "percent": 0,
                "progress_percent": 0,
            }
        )
    else:
        await websocket.send_json(task.get("progress") or {})
    await websocket.close()


@app.get("/api/v1/memory")
def get_memory() -> dict[str, Any]:
    return memory_doc_service.snapshot()


@app.get("/api/v1/memory/summary")
def get_memory_summary() -> dict[str, Any]:
    snapshot = memory_doc_service.snapshot()
    session = _latest_session()
    board_facts = dict((session.board_facts if session else {}) or {})
    continuity = str(session.continuation_prompt or "").strip() if session is not None else ""
    if not continuity:
        continuity = str(board_facts.get("continuation", {}).get("next_prompt_hint") or "").strip()

    long_term_facts: list[dict[str, str]] = []
    for ref in list(board_facts.get("evidence_refs", []) or [])[:6]:
        if not isinstance(ref, dict):
            continue
        source_ref = str(ref.get("source_ref") or ref.get("source_path") or "").strip()
        tool_name = str(ref.get("tool_name") or "source").strip()
        if source_ref:
            long_term_facts.append({"label": source_ref, "detail": tool_name})

    recent_events = []
    for event in reversed(orchestrator.memory_store.list_events()[-8:]):
        summary = str(event.payload.get("summary") or event.payload.get("review_summary") or event.payload or "").strip()
        recent_events.append(
            {
                "event_id": event.event_id,
                "kind": event.kind,
                "summary": summary,
                "recorded_at": str(event.payload.get("recorded_at") or event.payload.get("timestamp") or ""),
            }
        )

    return {
        **snapshot,
        "current_continuity": continuity,
        "long_term_facts": long_term_facts,
        "blockers": _extract_blocker_summaries(board_facts),
        "recent_events": recent_events,
    }


@app.get("/api/v1/memory/projection")
def memory_projection() -> dict[str, Any]:
    latest_steps: list[dict[str, Any]] = []
    for session in reversed(session_store.list_sessions()):
        project = project_service.get_project(session.project_id) if session.project_id else None
        continuation = str((session.board_facts or {}).get("continuation", {}).get("next_prompt_hint") or "").strip()
        if not continuation:
            continuation = str(session.continuation_prompt or "").strip()
        if not continuation:
            continue
        latest_steps.append(
            {
                "project_id": session.project_id,
                "project_title": project.title if project else session.project_id,
                "step": continuation,
                "recorded_at": getattr(session, "updated_at", int(time.time())),
            }
        )
        if len(latest_steps) >= 10:
            break
    return {
        "profile_projection": {
            "recent_next_steps": latest_steps,
        },
        "mastery_projection": {},
        "recent_events": [],
    }


@app.put("/api/v1/memory")
def update_memory(payload: MemoryUpdatePayload) -> dict[str, Any]:
    file_name = payload.file
    return memory_doc_service.update(file_name, payload.content)


@app.post("/api/v1/memory/refresh")
def refresh_memory(payload: MemoryRefreshPayload | None = None) -> dict[str, Any]:
    _ = payload
    latest_review = ""
    if session_store.list_sessions():
        latest_session = session_store.list_sessions()[-1]
        latest_review = str((latest_session.pending_review or {}).get("summary") or "")
    changed = False
    changed = memory_doc_service.refresh_summary(latest_review)
    return {**get_memory(), "changed": changed}


@app.post("/api/v1/memory/clear")
def clear_memory(payload: MemoryFilePayload) -> dict[str, Any]:
    file_name = payload.file
    return memory_doc_service.update(file_name, "")


@app.get("/api/v1/sessions")
def list_sessions(limit: int = 50, offset: int = 0, project_id: str | None = None) -> dict[str, Any]:
    sessions = session_store.list_sessions()
    if project_id:
        sessions = [item for item in sessions if item.project_id == project_id]
    sliced = sessions[offset : offset + limit]
    return {
        "sessions": [
            serialize_session_summary(item, project_service=project_service)
            for item in sliced
        ]
    }


@app.get("/api/v1/projects")
def list_projects() -> dict[str, Any]:
    projects = []
    for project in project_service.list_projects():
        projects.append(_serialize_project(project))
    return {"projects": projects}


@app.post("/api/v1/projects")
def create_project(payload: ProjectCreatePayload) -> dict[str, Any]:
    project_id = payload.slug.strip() or str(uuid4())
    project = project_service.create_project(project_id, title=payload.title, goal=payload.goal)
    return {"project": _serialize_project(project)}


@app.get("/api/v1/projects/{project_id}")
def get_project(project_id: str) -> dict[str, Any]:
    project = project_service.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"project": _serialize_project(project)}


@app.patch("/api/v1/projects/{project_id}")
def update_project(project_id: str, payload: ProjectUpdatePayload) -> dict[str, Any]:
    project = project_service.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if payload.title is not None:
        project.title = payload.title
    if payload.goal is not None:
        project.goal = payload.goal
    if payload.source_refs is not None:
        project.source_refs = list(payload.source_refs)
    project_service.save_project(project)
    return {"project": _serialize_project(project)}


@app.put("/api/v1/projects/{project_id}/sources")
def save_project_sources(project_id: str, payload: ProjectSourcesPayload) -> dict[str, Any]:
    project = project_service.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    project.source_refs = list(payload.source_refs)
    project.source_subset = list(payload.source_refs)
    project_service.save_project(project)
    return {
        "project": _serialize_project(project),
        "source_refs": list(project.source_refs),
        "source_references": list(payload.source_references),
    }


@app.post("/api/v1/projects/{project_id}/anchor")
def save_project_anchor(project_id: str, payload: ProjectAnchorPayload) -> dict[str, Any]:
    project = project_service.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    project.anchor = {
        "topic": payload.topic,
        "source_refs": list(payload.source_refs),
        "prior_knowledge": payload.prior_knowledge,
        "target_depth": payload.target_depth,
        "preferred_method": payload.preferred_method,
    }
    project.anchor_status = "ready"
    if payload.source_refs:
        project.source_refs = list(payload.source_refs)
    project_service.save_project(project)
    return {"project": _serialize_project(project), "anchor": dict(project.anchor)}


@app.get("/api/v1/projects/{project_id}/latest-review")
def get_latest_project_review(project_id: str) -> dict[str, Any]:
    project = project_service.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    latest = project.latest_review or None
    review_payload = None
    if latest:
        review_payload = {
            "project_id": project.project_id,
            "project_slug": project.project_id,
            "project_title": project.title,
            "session_id": "",
            "timestamp": "",
            "review_path": "",
            "review_summary": str(latest.get("summary") or ""),
            "mastery_points": list(latest.get("points") or []),
            "confusion_points": list(latest.get("confusion_points") or []),
            "next_steps": [],
            "understanding_alignment": {
                "learner_claim": "",
                "target_concept": "",
                "gap": "",
            },
            "references": [],
        }
    return {"project": _serialize_project(project), "latest_review": review_payload}


@app.post("/api/v1/sessions")
def create_session(payload: SessionCreatePayload) -> dict[str, Any]:
    session = session_store.create_session(
        session_id=str(uuid4()),
        project_id=payload.project_id,
        title=payload.title or payload.project_title or payload.project_id,
        turn_mode=payload.turn_mode,
    )
    session.source_refs = list(payload.source_refs)
    session.memory_refs = list(payload.memory_refs)
    touch_session(session)
    session_store.save_session(session)
    project = project_service.get_project(payload.project_id)
    if project is None:
        project = project_service.create_project(
            payload.project_id,
            title=payload.project_title or payload.project_id,
        )
    if payload.source_refs:
        project.source_refs = list(payload.source_refs)
    if payload.memory_refs:
        project.memory_refs = list(payload.memory_refs)
    project_service.save_project(project)
    return {"session": serialize_session_detail(session, project_service=project_service)}


@app.get("/api/v1/sessions/{session_id}")
def get_session(session_id: str) -> dict[str, Any]:
    session = session_store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return serialize_session_detail(session, project_service=project_service)


@app.patch("/api/v1/sessions/{session_id}")
def update_session(session_id: str, payload: SessionUpdatePayload) -> dict[str, Any]:
    session = session_store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    session.title = payload.title or session.title
    touch_session(session)
    session_store.save_session(session)
    return {"session": serialize_session_detail(session, project_service=project_service)}


@app.delete("/api/v1/sessions/{session_id}")
def delete_session(session_id: str) -> dict[str, Any]:
    session = session_store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    del session_store._sessions[session_id]
    return {"deleted": True}


@app.post("/api/v1/sessions/{session_id}/pause")
def pause_session(session_id: str) -> dict[str, Any]:
    session = session_store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    session.turn_mode = "PAUSED"
    session.board_facts = {
        **dict(session.board_facts or {}),
        "current_turn_mode": "PAUSED",
    }
    touch_session(session)
    session_store.save_session(session)
    return {"session": serialize_session_detail(session, project_service=project_service)}


@app.post("/api/v1/sessions/{session_id}/resume")
def resume_session(session_id: str) -> dict[str, Any]:
    session = session_store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.turn_mode == "PAUSED":
        session.turn_mode = "EXPLORE"
        session.board_facts = {
            **dict(session.board_facts or {}),
            "current_turn_mode": "EXPLORE",
        }
    touch_session(session)
    session_store.save_session(session)
    return {"session": serialize_session_detail(session, project_service=project_service)}


@app.websocket("/api/v1/ws")
async def unified_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            raw = await websocket.receive_text()
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                await websocket.send_json(
                    {
                        "type": "error",
                        "source": "server",
                        "stage": "",
                        "content": "WebSocket payload must be a JSON object.",
                        "metadata": {"turn_terminal": True, "status": "failed"},
                        "timestamp": 0,
                    }
                )
                continue
            msg_type = str(payload.get("type") or "")
            try:
                if msg_type == "ping":
                    await _handle_ping_message(websocket, PingPayload.model_validate(payload))
                    continue
                if msg_type in {"subscribe_turn", "resume_from"}:
                    await handle_subscribe_turn(websocket, SubscribeTurnPayload.model_validate(payload))
                    continue
                if msg_type == "cancel_turn":
                    await handle_cancel_turn(websocket, CancelTurnPayload.model_validate(payload))
                    continue
            except Exception as exc:
                await websocket.send_json(
                    {
                        "type": "error",
                        "source": "server",
                        "stage": "",
                        "content": str(exc),
                        "metadata": {"turn_terminal": True, "status": "failed"},
                        "timestamp": 0,
                    }
                )
                continue
            if msg_type == "regenerate":
                try:
                    regenerate = RegeneratePayload.model_validate(payload)
                except Exception as exc:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "source": "server",
                            "stage": "",
                            "content": str(exc),
                            "metadata": {"turn_terminal": True, "status": "failed"},
                            "timestamp": 0,
                        }
                    )
                    continue
                session_id = str(regenerate.session_id or "").strip()
                session = session_store.get_session(session_id)
                if session is None or not session.messages:
                    await _send_regenerate_rejected(websocket, session_id)
                    continue
                last_user = next(
                    (item for item in reversed(session.messages) if item.get("role") == "user"),
                    None,
                )
                if last_user is None:
                    await _send_regenerate_rejected(websocket, session_id)
                    continue
                payload = {
                    "type": "start_turn",
                    "content": str(last_user.get("content") or ""),
                    "session_id": session_id,
                    "project_id": session.project_id,
                    "project_title": session.title,
                    "language": "zh",
                }
                msg_type = "start_turn"
            if msg_type not in {"message", "start_turn"}:
                await websocket.send_json(
                    {
                        "type": "error",
                        "source": "server",
                        "stage": "",
                        "content": f"Unsupported message type: {msg_type}",
                        "metadata": {"turn_terminal": True, "status": "failed"},
                        "timestamp": 0,
                    }
                )
                continue
            try:
                message = StartTurnPayload.model_validate(payload)
            except Exception as exc:
                await websocket.send_json(
                    {
                        "type": "error",
                        "source": "server",
                        "stage": "",
                        "content": str(exc),
                        "metadata": {"turn_terminal": True, "status": "failed"},
                        "timestamp": 0,
                    }
                )
                continue
            session_id = message.session_id or str(uuid4())
            project_id = message.project_id or "default-project"
            project_title = message.project_title or project_id
            turn_id = str(uuid4())
            if session_store.get_session(session_id) is None:
                session = session_store.create_session(
                    session_id=session_id,
                    project_id=project_id,
                    title=project_title,
                )
                touch_session(session)
                session_store.save_session(session)
            session = session_store.get_session(session_id)
            if session is None:
                raise HTTPException(status_code=500, detail="Failed to initialize session")
            session.status = "running"
            session.active_turn_id = turn_id
            session.active_turns = [
                {
                    "id": turn_id,
                    "turn_id": turn_id,
                    "session_id": session_id,
                    "status": "running",
                    "error": "",
                    "created_at": int(time.time()),
                    "updated_at": int(time.time()),
                    "finished_at": None,
                    "last_seq": 0,
                }
            ]
            touch_session(session)
            session_store.save_session(session)
            turn_streams[turn_id] = []
            turn_index[turn_id] = {"session_id": session_id, "project_id": project_id}
            seq = 1
            session_event = {
                "type": "session",
                "source": "server",
                "stage": "session",
                "content": "",
                "metadata": {
                    "session_id": session_id,
                    "turn_id": turn_id,
                    "phase": "session",
                    "warnings": [],
                    "tool_events": [],
                },
                "session_id": session_id,
                "turn_id": turn_id,
                "seq": seq,
                "timestamp": time.time(),
            }
            turn_streams[turn_id].append(session_event)
            await websocket.send_json(session_event)
            seq += 1
            stage_event = {
                "type": "stage_start",
                "source": "server",
                "stage": "turn",
                "content": "",
                "metadata": {"phase": "started", "warnings": [], "tool_events": []},
                "session_id": session_id,
                "turn_id": turn_id,
                "seq": seq,
                "timestamp": time.time(),
            }
            turn_streams[turn_id].append(stage_event)
            await websocket.send_json(stage_event)
            seq += 1
            try:
                result = await to_thread.run_sync(
                    lambda: orchestrator.run_turn(
                        session_id=session_id,
                        project_id=project_id,
                        user_message=message.content,
                        language=message.language,
                        attachments=message.attachments,
                    )
                )
            except Exception as exc:
                session = session_store.get_session(session_id)
                if session is not None:
                    session.status = "failed"
                    session.active_turn_id = None
                    session.active_turns = []
                    touch_session(session)
                    session_store.save_session(session)
                error_event = {
                    "type": "error",
                    "source": "server",
                    "stage": "turn",
                    "content": str(exc),
                    "metadata": {
                        "phase": "error",
                        "status": "failed",
                        "turn_terminal": True,
                        "warnings": [str(exc)],
                        "tool_events": [],
                    },
                    "session_id": session_id,
                    "turn_id": turn_id,
                    "seq": seq,
                    "timestamp": time.time(),
                }
                turn_streams[turn_id].append(error_event)
                await websocket.send_json(error_event)
                continue
            prepared_stream_events = _append_ws_stream_events(
                turn_id=turn_id,
                session_id=session_id,
                result=result,
                seq=seq,
            )
            if prepared_stream_events:
                seq = int(prepared_stream_events[-1].get("seq") or seq) + 1
            for item in prepared_stream_events:
                await websocket.send_json(item)
            content_event = {
                "type": "content",
                "source": "assistant",
                "stage": "turn",
                "content": result.final_text,
                "metadata": {
                    "phase": "content",
                    "turn_mode": result.turn_mode_after,
                    "board_patch": result.board_patch,
                    "warnings": list(result.warnings),
                    "tool_events": list(result.tool_events),
                    "call_id": f"{turn_id}-final",
                    "call_kind": "llm_final_response",
                    "trace_role": "response",
                },
                "session_id": session_id,
                "turn_id": turn_id,
                "seq": seq,
                "timestamp": time.time(),
            }
            seq += 1
            turn_streams[turn_id].append(content_event)
            await websocket.send_json(content_event)
            done_event = {
                "type": "done",
                "source": "server",
                "stage": "turn",
                "content": "",
                "metadata": {
                    "phase": "done",
                    "status": "completed",
                    "warnings": list(result.warnings),
                    "tool_events": list(result.tool_events),
                },
                "session_id": session_id,
                "turn_id": turn_id,
                "seq": seq,
                "timestamp": time.time(),
            }
            turn_streams[turn_id].append(done_event)
            session = session_store.get_session(session_id)
            if session is not None:
                session.status = "completed"
                session.active_turn_id = None
                session.active_turns = []
                touch_session(session)
                session_store.save_session(session)
            await websocket.send_json(done_event)
    except WebSocketDisconnect:
        return


def _serialize_project(project: LearningProject) -> dict[str, Any]:
    source_refs = list(project.source_refs or [])
    memory_refs = list(project.memory_refs or [])
    board_facts = dict(project.board_facts or {})
    latest_review = dict(project.latest_review or {})
    latest_review_status = str(latest_review.get("status") or ("ready" if latest_review.get("summary") else "empty"))
    source_count = len(source_refs)
    session_count = len([item for item in session_store.list_sessions() if item.project_id == project.project_id])
    return {
        "project_id": project.project_id,
        "slug": project.project_id,
        "title": project.title,
        "goal": project.goal,
        "status": "active",
        "created_at": "",
        "updated_at": "",
        "last_active_at": "",
        "source_count": source_count,
        "session_count": session_count,
        "memory_ref_count": len(memory_refs),
        "turn_mode": project.turn_mode,
        "board_facts": board_facts,
        "board_version": int(project.board_version or 1),
        "board_updated_at": str(board_facts.get("updated_at") or ""),
        "latest_review_status": latest_review_status,
        "latest_review": latest_review,
        "source_refs": source_refs,
        "source_references": [],
        "memory_refs": memory_refs,
        "anchor": dict(project.anchor) if project.anchor else None,
    }
