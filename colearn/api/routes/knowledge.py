"""Knowledge base routes."""

from __future__ import annotations

import json
import mimetypes
from pathlib import Path
import re
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse

from colearn.api.dependencies import knowledge_task_service, project_service, settings_service

router = APIRouter()

# TODO(harness-cleanup): replace with LightRAG node-derived concepts when graph data wired up
KNOWLEDGE_GRAPH_CONCEPT_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("lightrag", "LightRAG"),
    ("machine learning", "Machine Learning"),
    ("deep learning", "Deep Learning"),
    ("linear algebra", "Linear Algebra"),
    ("regression", "Regression"),
    ("classification", "Classification"),
    ("evaluation", "Evaluation"),
    ("dataset", "Dataset"),
    ("feature", "Feature"),
    ("model", "Model"),
    ("training", "Training"),
    ("agent", "Agent"),
    ("state", "State"),
    ("lesson", "Lesson"),
    ("exercise", "Exercise"),
    ("evidence", "Evidence"),
    ("课程", "课程"),
    ("概念", "概念"),
    ("练习", "练习"),
    ("证据", "证据"),
    ("线性代数", "线性代数"),
    ("函数", "函数"),
    ("模型", "模型"),
)


def _json_sse(events: list[dict[str, Any]]):
    def generate():
        for item in events:
            event_name = str(item.get("event") or "message")
            payload = json.dumps(item.get("data") or {}, ensure_ascii=False)
            yield f"event: {event_name}\ndata: {payload}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


def _normalize_uploads(files: UploadFile | list[UploadFile] | None) -> list[UploadFile]:
    if files is None:
        return []
    if isinstance(files, list):
        return files
    return [files]


def _knowledge_graph_node(
    *,
    node_id: str,
    label: str,
    kind: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": node_id,
        "label": label,
        "kind": kind,
        "metadata": dict(metadata or {}),
    }


def _knowledge_graph_edge(
    *,
    edge_id: str,
    source: str,
    target: str,
    kind: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": edge_id,
        "source": source,
        "target": target,
        "kind": kind,
        "metadata": dict(metadata or {}),
    }


def _title_case_concept_token(value: str) -> str:
    if len(value) <= 3:
        return value.upper()
    return value[:1].upper() + value[1:]


def _concepts_from_file_name(file_name: str) -> list[str]:
    stem = Path(file_name).stem
    searchable = re.sub(r"[^0-9A-Za-z一-鿿]+", " ", stem).strip().lower()
    concepts: list[str] = []
    for needle, label in KNOWLEDGE_GRAPH_CONCEPT_KEYWORDS:
        if needle.lower() in searchable:
            concepts.append(label)
    for token in re.split(r"[^0-9A-Za-z一-鿿]+", stem):
        token = token.strip()
        if not token:
            continue
        if re.search(r"[一-鿿]", token) or len(token) > 2 or token.lower() in {"ai", "ml"}:
            concepts.append(token if re.search(r"[一-鿿]", token) else _title_case_concept_token(token.lower()))
    seen: set[str] = set()
    unique: list[str] = []
    for concept in concepts:
        key = concept.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(concept)
        if len(unique) >= 4:
            break
    return unique


def _knowledge_graph_concept_id(label: str) -> str:
    key = re.sub(r"\s+", "-", label.strip().casefold())
    key = re.sub(r"[^0-9a-zA-Z一-鿿_-]+", "", key)
    return f"concept:{key or 'untitled'}"


def build_knowledge_graph_payload(name: str) -> dict[str, Any]:
    project = project_service.get_project(name)
    files = knowledge_task_service.list_files(name)
    if project is None and not files:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    library_label = project.title if project else name
    library_metadata = {
        "library_id": name,
        "source_count": len(project.source_refs or []) if project else len(files),
        "status": str((project.retrieval_profile or {}).get("last_retrieval_status") or "empty")
        if project
        else "ready",
        "provider": str((project.retrieval_profile or {}).get("provider") or "lightrag") if project else "lightrag",
        "updated_at": str((project.board_facts or {}).get("updated_at") or "") if project else "",
    }
    library_node_id = f"library:{name}"
    nodes = [
        _knowledge_graph_node(
            node_id=library_node_id,
            label=library_label,
            kind="library",
            metadata=library_metadata,
        )
    ]
    edges: list[dict[str, Any]] = []
    concept_ids: set[str] = set()

    for file_item in files:
        file_name = str(file_item.get("name") or Path(str(file_item.get("path") or "")).name or "untitled")
        file_path = str(file_item.get("path") or "")
        file_node_id = f"file:{name}:{file_name}"
        file_metadata = {
            "library_id": name,
            "path": file_path,
            "size": int(file_item.get("size") or 0),
            "modified": int(file_item.get("modified") or 0),
            "mime_type": file_item.get("mime_type"),
        }
        nodes.append(
            _knowledge_graph_node(
                node_id=file_node_id,
                label=file_name,
                kind="file",
                metadata=file_metadata,
            )
        )
        edges.append(
            _knowledge_graph_edge(
                edge_id=f"edge:contains:{library_node_id}:{file_node_id}",
                source=library_node_id,
                target=file_node_id,
                kind="contains",
                metadata={"library_id": name},
            )
        )
        for concept in _concepts_from_file_name(file_name):
            concept_node_id = _knowledge_graph_concept_id(concept)
            if concept_node_id not in concept_ids:
                concept_ids.add(concept_node_id)
                nodes.append(
                    _knowledge_graph_node(
                        node_id=concept_node_id,
                        label=concept,
                        kind="concept",
                        metadata={"source": "filename"},
                    )
                )
            edges.append(
                _knowledge_graph_edge(
                    edge_id=f"edge:mentions:{file_node_id}:{concept_node_id}",
                    source=file_node_id,
                    target=concept_node_id,
                    kind="mentions",
                    metadata={"library_id": name, "source": "filename"},
                )
            )

    return {"nodes": nodes, "edges": edges}


@router.get("/api/v1/knowledge/list")
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


@router.get("/api/v1/knowledge/rag-providers")
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


@router.get("/api/v1/knowledge/supported-file-types")
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


@router.get("/api/v1/knowledge/{name}/graph")
def get_knowledge_graph(name: str) -> dict[str, Any]:
    return build_knowledge_graph_payload(name)


@router.get("/api/v1/knowledge/{name}/files")
def list_knowledge_files(name: str) -> dict[str, Any]:
    return {"files": knowledge_task_service.list_files(name)}


@router.get("/api/v1/knowledge/{name}/files/{file_path:path}")
def get_knowledge_file(name: str, file_path: str) -> FileResponse:
    target = knowledge_task_service.resolve_file(name, file_path)
    if target is None:
        raise HTTPException(status_code=404, detail="Knowledge file not found")
    media_type, _ = mimetypes.guess_type(str(target))
    return FileResponse(target, media_type=media_type or "application/octet-stream", filename=target.name)


@router.post("/api/v1/knowledge/create")
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


@router.post("/api/v1/knowledge/{name}/upload")
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


@router.post("/api/v1/knowledge/{name}/reindex")
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


@router.get("/api/v1/knowledge/tasks/{task_id}/stream")
def knowledge_task_stream(task_id: str) -> StreamingResponse:
    task = knowledge_task_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Knowledge task not found")
    return _json_sse(knowledge_task_service.stream_events(task_id))


@router.websocket("/api/v1/knowledge/{name}/progress/ws")
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