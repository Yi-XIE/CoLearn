"""Lightweight CLI for nanobot exec tool to call CoLearn without MCP overhead."""

from __future__ import annotations

import json
import sys
from typing import Any

from colearn.memory.store import EventMemoryStore
from colearn.paths import colearn_repo_root, colearn_state_root
from colearn.projects.service import LearningProjectService
from colearn.retrieval.service import RetrievalService
from colearn.sessions.store import LearningSession, SessionStore
from colearn.storage import JsonStateStore
from colearn.storage.records import memory_event_to_record, project_to_record, session_to_record


def _store() -> JsonStateStore:
    return JsonStateStore(colearn_state_root())


def _out(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def cmd_list_projects() -> None:
    svc = LearningProjectService(state_store=_store())
    _out([project_to_record(p) for p in svc.list_projects()])


def cmd_list_sessions(project_id: str = "") -> None:
    store = SessionStore(state_store=_store())
    sessions = [
        session_to_record(s) for s in store.list_sessions()
        if not project_id or s.project_id == project_id
    ]
    _out(sessions)


def cmd_search_memory(query: str, session_id: str = "", project_id: str = "", limit: str = "5") -> None:
    ms = EventMemoryStore(state_store=_store())
    events = ms.search_events(query=query, session_id=session_id, project_id=project_id, limit=int(limit))
    _out([memory_event_to_record(e) for e in events])


def cmd_retrieve(project_id: str, query: str, session_id: str = "") -> None:
    svc = LearningProjectService(state_store=_store())
    project = svc.get_project(project_id)
    if not project:
        _out({"error": "project_not_found"})
        return
    ss = SessionStore(state_store=_store())
    session = ss.get_session(session_id) if session_id else None
    if session is None:
        session = LearningSession(
            session_id=session_id or "cli-readonly",
            project_id=project_id,
            source_refs=list(project.source_subset or project.source_refs),
        )
    rs = RetrievalService(workspace=colearn_repo_root())
    bundle = rs.build_bundle(project=project, session=session, query=query, libraries=None)
    _out({
        "query": getattr(bundle, "query", ""),
        "text": getattr(bundle, "text", ""),
        "references": list(getattr(bundle, "references", []) or []),
        "retrieval_status": getattr(bundle, "retrieval_status", ""),
    })


def cmd_get_board(session_id: str) -> None:
    ss = SessionStore(state_store=_store())
    session = ss.get_session(session_id)
    if not session:
        _out({"error": "session_not_found"})
        return
    bf = session.board_facts or {}
    _out({
        "session_id": session.session_id,
        "turn_mode": session.turn_mode or bf.get("current_turn_mode", "EXPLORE"),
        "board_version": session.board_version,
        "mastery_level": (bf.get("student_snapshot") or {}).get("mastery_level", 0),
        "cognitive_load": (bf.get("student_snapshot") or {}).get("cognitive_load", "NORMAL"),
        "active_node": (bf.get("current_progress") or {}).get("active_node_label", ""),
        "completed_nodes": (bf.get("current_progress") or {}).get("completed_node_ids", []),
        "blockers": (bf.get("gaps_and_blockers") or {}).get("critical_blockers", []),
        "unverified_gaps": (bf.get("gaps_and_blockers") or {}).get("unverified_gaps", []),
        "next_prompt_hint": (bf.get("continuation") or {}).get("next_prompt_hint", ""),
    })


def cmd_get_session_detail(session_id: str, messages: str = "5") -> None:
    ss = SessionStore(state_store=_store())
    session = ss.get_session(session_id)
    if not session:
        _out({"error": "session_not_found"})
        return
    n = int(messages)
    recent = []
    for msg in (session.messages or [])[-n:]:
        recent.append({
            "role": msg.get("role", ""),
            "content": (msg.get("content") or "")[:200],
            "turn_id": msg.get("turn_id", ""),
        })
    _out({
        "session_id": session.session_id,
        "project_id": session.project_id,
        "title": session.title,
        "status": session.status,
        "turn_mode": session.turn_mode,
        "board_facts": session.board_facts,
        "recent_messages": recent,
        "source_refs": session.source_refs,
    })


def cmd_list_concepts(project_id: str) -> None:
    import re
    from pathlib import Path
    kb_dir = Path(colearn_state_root()) / "knowledge" / project_id
    if not kb_dir.exists():
        _out({"project_id": project_id, "concepts": [], "total": 0})
        return
    concepts = []
    seen: set[str] = set()
    for path in sorted(kb_dir.rglob("*")):
        if not path.is_file():
            continue
        stem = path.stem
        for token in re.split(r"[^0-9A-Za-z一-鿿]+", stem):
            token = token.strip()
            if not token or len(token) < 2:
                continue
            key = token.casefold()
            if key in seen:
                continue
            seen.add(key)
            concepts.append({"label": token, "source": path.name})
    _out({"project_id": project_id, "concepts": concepts, "total": len(concepts)})


COMMANDS = {
    "list_projects": cmd_list_projects,
    "list_sessions": cmd_list_sessions,
    "search_memory": cmd_search_memory,
    "retrieve": cmd_retrieve,
    "get_board": cmd_get_board,
    "get_session_detail": cmd_get_session_detail,
    "list_concepts": cmd_list_concepts,
}


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print("Usage: python -m colearn.cli <command> [--key value ...]")
        print(f"Commands: {', '.join(COMMANDS)}")
        sys.exit(0)
    cmd_name = args[0]
    fn = COMMANDS.get(cmd_name)
    if fn is None:
        print(f"Unknown command: {cmd_name}", file=sys.stderr)
        sys.exit(1)
    kwargs: dict[str, str] = {}
    i = 1
    while i < len(args):
        if args[i].startswith("--"):
            key = args[i][2:].replace("-", "_")
            val = args[i + 1] if i + 1 < len(args) else ""
            kwargs[key] = val
            i += 2
        else:
            i += 1
    fn(**kwargs)


if __name__ == "__main__":
    main()
