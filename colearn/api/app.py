"""Minimal FastAPI + WebSocket entrypoint for the CoLearn backend."""

from __future__ import annotations

import json
import time
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect

from colearn.api.schemas import (
    ProjectAnchorPayload,
    ProjectCreatePayload,
    ProjectSourcesPayload,
    ProjectUpdatePayload,
    MemoryFilePayload,
    MemoryUpdatePayload,
    SkillPayload,
    SkillTagPayload,
    SkillUpdatePayload,
    SessionCreatePayload,
    SessionUpdatePayload,
    SettingsCatalogPayload,
    SettingsUiPayload,
    StartTurnPayload,
)
from colearn.api.session_api import serialize_session_detail, serialize_session_summary, touch_session
from colearn.app.learning_orchestrator import LearningOrchestrator
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
memory_docs: dict[str, str] = {"summary": "", "profile": ""}
memory_updated_at: dict[str, str | None] = {"summary": None, "profile": None}
skills_state: dict[str, Any] = {
    "skills": {},
    "tags": {},
}
settings_state: dict[str, Any] = {
    "ui": {
        "theme": "dark",
        "language": "zh",
    },
    "catalog": {
        "version": 1,
        "services": {
            "llm": {
                "active_profile_id": "default-llm-profile",
                "active_model_id": "default-llm-model",
                "profiles": [
                    {
                        "id": "default-llm-profile",
                        "name": "Default LLM",
                        "binding": "openai",
                        "base_url": "https://api.openai.com/v1",
                        "api_key": "",
                        "api_version": "",
                        "extra_headers": {},
                        "proxy": "",
                        "models": [
                            {
                                "id": "default-llm-model",
                                "name": "GPT-5",
                                "model": "gpt-5",
                                "context_window": "128000",
                                "context_window_source": "default",
                            }
                        ],
                    }
                ],
            },
            "embedding": {
                "active_profile_id": "default-embedding-profile",
                "active_model_id": "default-embedding-model",
                "profiles": [
                    {
                        "id": "default-embedding-profile",
                        "name": "Default Embedding",
                        "binding": "openai",
                        "base_url": "https://api.openai.com/v1",
                        "api_key": "",
                        "api_version": "",
                        "extra_headers": {},
                        "proxy": "",
                        "models": [
                            {
                                "id": "default-embedding-model",
                                "name": "text-embedding-3-large",
                                "model": "text-embedding-3-large",
                                "dimension": "3072",
                                "send_dimensions": True,
                                "supported_dimensions": "256,1024,3072",
                            }
                        ],
                    }
                ],
            },
            "search": {
                "active_profile_id": "default-search-profile",
                "profiles": [
                    {
                        "id": "default-search-profile",
                        "name": "Default Search",
                        "provider": "brave",
                        "binding": None,
                        "base_url": "",
                        "api_key": "",
                        "api_version": "",
                        "extra_headers": {},
                        "proxy": "",
                        "models": [],
                    }
                ],
            },
        },
    },
    "providers": {
        "llm": [
            {"value": "openai", "label": "OpenAI", "base_url": "https://api.openai.com/v1"},
        ],
        "embedding": [
            {
                "value": "openai",
                "label": "OpenAI",
                "base_url": "https://api.openai.com/v1",
                "default_dim": "3072",
            },
        ],
        "search": [
            {"value": "brave", "label": "Brave Search"},
            {"value": "tavily", "label": "Tavily"},
            {"value": "perplexity", "label": "Perplexity"},
        ],
    },
}


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


async def handle_subscribe_turn(websocket: WebSocket, payload: dict[str, Any]) -> None:
    turn_id = str(payload.get("turn_id") or "").strip()
    after_seq = int(payload.get("after_seq") or payload.get("seq") or 0)
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


async def handle_cancel_turn(websocket: WebSocket, payload: dict[str, Any]) -> None:
    turn_id = str(payload.get("turn_id") or "").strip()
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


async def _handle_ping_message(websocket: WebSocket, payload: dict[str, Any]) -> None:
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


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True}


@app.get("/api/v1/system/status")
def system_status() -> dict[str, Any]:
    return {
        "backend": {"status": "running", "timestamp": str(int(time.time()))},
        "llm": {"status": "ready", "model": "gpt-5"},
        "embeddings": {"status": "ready", "model": "text-embedding-3-large"},
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
    return {
        "ui": dict(settings_state["ui"]),
        "catalog": settings_state["catalog"],
        "providers": settings_state["providers"],
    }


@app.get("/api/v1/settings/catalog")
def get_settings_catalog() -> dict[str, Any]:
    return {"catalog": settings_state["catalog"]}


@app.get("/api/v1/settings/providers")
def get_settings_providers() -> dict[str, Any]:
    return {"providers": settings_state["providers"]}


@app.get("/api/v1/settings/llm-options")
def get_llm_options() -> dict[str, Any]:
    active = {
        "profile_id": "default",
        "model_id": "gpt-5",
    }
    return {
        "active": active,
        "options": [
            {
                "profile_id": "default",
                "profile_label": "Default",
                "model_id": "gpt-5",
                "model_label": "GPT-5",
                "provider": "openai",
                "is_default": True,
            }
        ],
    }


@app.get("/api/v1/skills/list")
def list_skills() -> dict[str, Any]:
    skills = []
    for name, record in skills_state["skills"].items():
        skills.append(
            {
                "name": name,
                "description": str(record.get("description") or ""),
                "tags": list(record.get("tags") or []),
            }
        )
    return {"skills": skills}


@app.get("/api/v1/skills/{name}")
def get_skill(name: str) -> dict[str, Any]:
    record = dict(skills_state["skills"].get(name) or {})
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
    skills_state["skills"][payload.name] = {
        "description": payload.description,
        "content": payload.content,
        "tags": list(payload.tags),
    }
    return {
        "name": payload.name,
        "description": payload.description,
        "content": payload.content,
        "tags": list(payload.tags),
    }


@app.put("/api/v1/skills/{name}")
def update_skill(name: str, payload: SkillUpdatePayload) -> dict[str, Any]:
    record = dict(skills_state["skills"].get(name) or {})
    if not record:
        raise HTTPException(status_code=404, detail="Skill not found")
    new_name = payload.rename_to or name
    record["description"] = payload.description if payload.description is not None else record.get("description", "")
    record["content"] = payload.content if payload.content is not None else record.get("content", "")
    record["tags"] = list(payload.tags) if payload.tags else list(record.get("tags") or [])
    if new_name != name:
        del skills_state["skills"][name]
    skills_state["skills"][new_name] = record
    return {"name": new_name, **record}


@app.delete("/api/v1/skills/{name}")
def delete_skill(name: str) -> dict[str, Any]:
    skills_state["skills"].pop(name, None)
    return {"deleted": True}


@app.get("/api/v1/skills/tags/list")
def list_skill_tags() -> dict[str, Any]:
    return {"tags": sorted(skills_state["tags"].keys())}


@app.post("/api/v1/skills/tags/create")
def create_skill_tag(payload: SkillTagPayload) -> dict[str, Any]:
    skills_state["tags"][payload.name] = payload.name
    return {"name": payload.name}


@app.put("/api/v1/skills/tags/{old_name}")
def rename_skill_tag(old_name: str, payload: SkillTagPayload) -> dict[str, Any]:
    new_name = payload.rename_to or payload.name or old_name
    if old_name in skills_state["tags"]:
      skills_state["tags"].pop(old_name, None)
    skills_state["tags"][new_name] = new_name
    return {"name": new_name}


@app.delete("/api/v1/skills/tags/{name}")
def delete_skill_tag(name: str) -> dict[str, Any]:
    skills_state["tags"].pop(name, None)
    return {"deleted": True}


@app.put("/api/v1/settings/ui")
def update_settings_ui(payload: SettingsUiPayload) -> dict[str, Any]:
    ui = settings_state["ui"]
    ui["theme"] = str(payload.theme or ui["theme"])
    ui["language"] = str(payload.language or ui["language"])
    return {"ui": dict(ui)}


@app.put("/api/v1/settings/catalog")
def update_settings_catalog(payload: SettingsCatalogPayload) -> dict[str, Any]:
    catalog = payload.catalog
    if isinstance(catalog, dict):
        settings_state["catalog"] = catalog
    return {"catalog": settings_state["catalog"]}


@app.post("/api/v1/settings/apply")
def apply_settings_catalog(payload: SettingsCatalogPayload) -> dict[str, Any]:
    catalog = payload.catalog
    if isinstance(catalog, dict):
        settings_state["catalog"] = catalog
    return {"catalog": settings_state["catalog"], "applied": True}


@app.post("/api/v1/settings/tests/{service}/start")
def start_settings_test(service: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {"run_id": f"{service}-dry-run", "detail": "", "accepted": True}


@app.get("/api/v1/knowledge/list")
def list_knowledge_bases() -> dict[str, Any]:
    projects = project_service.list_projects()
    knowledge_bases = [
        {
            "id": project.project_id,
            "name": project.title,
            "source_count": len(project.source_refs or []),
            "status": str((project.retrieval_profile or {}).get("last_retrieval_status") or "empty"),
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
    project = next((item for item in project_service.list_projects() if item.title == name or item.project_id == name), None)
    if project is None:
        return {"files": []}
    files = []
    for source_ref in list(project.source_refs or []):
        files.append(
            {
                "name": source_ref.split("\\")[-1].split("/")[-1],
                "size": 0,
                "modified": 0,
                "mime_type": None,
            }
        )
    return {"files": files}


@app.post("/api/v1/knowledge/create")
async def create_knowledge_base() -> dict[str, Any]:
    return {"task_id": str(uuid4()), "message": "Knowledge base created"}


@app.post("/api/v1/knowledge/{name}/upload")
async def upload_knowledge_files(name: str) -> dict[str, Any]:
    return {"task_id": str(uuid4()), "message": f"Uploaded files to {name}"}


@app.put("/api/v1/knowledge/default/{name}")
def set_default_knowledge_base(name: str) -> dict[str, Any]:
    return {"ok": True, "default": name}


@app.post("/api/v1/knowledge/{name}/reindex")
def reindex_knowledge_base(name: str) -> dict[str, Any]:
    return {"task_id": str(uuid4()), "message": f"Reindex started for {name}"}


@app.delete("/api/v1/knowledge/{name}")
def delete_knowledge_base(name: str) -> dict[str, Any]:
    return {"deleted": True, "name": name}


@app.get("/api/v1/memory")
def get_memory() -> dict[str, Any]:
    return {
        "summary": memory_docs["summary"],
        "profile": memory_docs["profile"],
        "summary_updated_at": memory_updated_at["summary"],
        "profile_updated_at": memory_updated_at["profile"],
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
    memory_docs[file_name] = payload.content
    memory_updated_at[file_name] = str(int(time.time()))
    return get_memory()


@app.post("/api/v1/memory/refresh")
def refresh_memory(payload: dict[str, Any]) -> dict[str, Any]:
    latest_review = ""
    if session_store.list_sessions():
        latest_session = session_store.list_sessions()[-1]
        latest_review = str((latest_session.pending_review or {}).get("summary") or "")
    changed = False
    if latest_review and latest_review != memory_docs["summary"]:
        memory_docs["summary"] = latest_review
        memory_updated_at["summary"] = str(int(time.time()))
        changed = True
    return {**get_memory(), "changed": changed}


@app.post("/api/v1/memory/clear")
def clear_memory(payload: MemoryFilePayload) -> dict[str, Any]:
    file_name = payload.file
    memory_docs[file_name] = ""
    memory_updated_at[file_name] = str(int(time.time()))
    return get_memory()


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
            msg_type = str(payload.get("type") or "")
            handler = WS_HANDLERS.get(msg_type)
            if handler is not None:
                await handler(websocket, payload)
                continue
            if msg_type == "regenerate":
                session_id = str(payload.get("session_id") or "").strip()
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
            message = StartTurnPayload.model_validate(payload)
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
                result = orchestrator.run_turn(
                    session_id=session_id,
                    project_id=project_id,
                    user_message=message.content,
                    language=message.language,
                    attachments=message.attachments,
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


def _serialize_project(project) -> dict[str, Any]:
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
