from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from colearn.app.learning_orchestrator import LearningOrchestrator
from colearn.compression import ProductCompressionResult
from colearn.knowledge import KnowledgeWorkspaceService
from colearn.learning.response_contract import LearningTurnResult
from colearn.learning.state import BoardFacts, Blocker, GapsAndBlockers, LearningStateSnapshot, ProgressFacts, StudentSnapshot
from colearn.learning.state_hooks import after_turn_payload
from colearn.learning.turn_contract import LearningTurnRequest
from colearn.memory.store import EventMemoryStore, MemoryEvent
from colearn.projects.models import LearningProject
from colearn.projects.service import LearningProjectService
from colearn.runtime_v2.result_bridge import normalize_learning_turn_result
from colearn.sessions.store import SessionStore
from colearn.storage.json_store import JsonStateStore


@dataclass
class FakeExecutor:
    def run_turn(self, *, request: LearningTurnRequest) -> LearningTurnResult:
        self.last_request = request
        return LearningTurnResult(
            final_text=f"Answering: {request.user_message}",
            board_before=request.board_facts,
            board_after=request.board_facts,
            turn_mode_before=request.metadata.get("turn_mode_before", "EXPLORE"),
            turn_mode_after=request.turn_mode,
            retrieval_bundle=request.retrieval_bundle,
            raw_learning_result={"tool_events": [], "raw_messages": []},
        )

    def finalize(
        self,
        *,
        request: LearningTurnRequest,
        final_text: str,
        learning_result: dict | None = None,
    ) -> LearningTurnResult:
        return normalize_learning_turn_result(
            request=request,
            final_text=final_text,
            learning_result=learning_result,
        )


class FakeRetrievalService:
    def sync_source_refs(self, *, project_id: str, source_refs: list[str], libraries=None):
        _ = (project_id, libraries)
        return {
            "project_id": project_id,
            "enabled": True,
            "synced": bool(source_refs),
            "source_count": len(source_refs),
            "indexed_paths": list(source_refs),
            "sync_status": "synced" if source_refs else "empty",
            "warnings": [],
        }


class FailingProductCompression:
    def compress(self, **kwargs):
        raise RuntimeError("compression offline")


def test_orchestrator_writes_back_review_and_memory_events(tmp_path):
    root = tmp_path / ".colearn" / "state"
    project_service = LearningProjectService(state_store=JsonStateStore(root))
    project = project_service.create_project("proj-1", "Linear Algebra")
    project.anchor = {"topic": "matrix multiplication"}
    project.anchor_status = "ready"
    source_file = tmp_path / "source.md"
    source_file.write_text("Matrix multiplication composes linear maps.", encoding="utf-8")
    project.source_refs = [str(source_file)]
    project_service.save_project(project)

    session_store = SessionStore(state_store=JsonStateStore(root))
    session = session_store.create_session(session_id="sess-1", project_id="proj-1")
    session.source_refs = [str(source_file)]
    session_store.save_session(session)

    orchestrator = LearningOrchestrator(
        project_service=project_service,
        session_store=session_store,
        executor=FakeExecutor(),
        memory_store=EventMemoryStore(state_store=JsonStateStore(root)),
        retrieval_service=FakeRetrievalService(),
    )

    result = orchestrator.run_turn(
        session_id="sess-1",
        project_id="proj-1",
        user_message="Explain why matrix multiplication is not commutative.",
    )

    saved_session = session_store.get_session("sess-1")
    saved_project = project_service.get_project("proj-1")

    assert result.turn_mode_after == "EXPLORE"
    assert saved_session is not None
    assert saved_project is not None
    assert len(saved_session.messages) == 2
    assert "board_patch" in saved_session.last_turn_result
    assert saved_session.continuation_prompt
    assert saved_session.board_facts["current_turn_mode"] == "EXPLORE"
    assert saved_project.board_facts["current_turn_mode"] == "EXPLORE"

    time.sleep(0.05)
    saved_session = session_store.get_session("sess-1")
    saved_project = project_service.get_project("proj-1")
    assert saved_session is not None
    assert saved_project is not None
    assert saved_session.pending_review["summary"]
    assert saved_project.latest_review["summary"]
    assert len(orchestrator.memory_store.list_events_for_session("sess-1")) == 3
    assert saved_session.board_facts["updated_at"]
    assert saved_session.last_turn_result["product_compression"]["status"] == "completed"


def test_dream_consolidation_builds_structured_event(tmp_path):
    root = tmp_path / ".colearn" / "state"
    project_service = LearningProjectService(state_store=JsonStateStore(root))
    project = project_service.create_project("proj-dream", "Dream")
    session_store = SessionStore(state_store=JsonStateStore(root))
    session = session_store.create_session(session_id="sess-dream", project_id="proj-dream")
    memory_store = EventMemoryStore(state_store=JsonStateStore(root))
    for idx in range(20):
        memory_store.append(
            MemoryEvent(
                event_id=f"evt-{idx}",
                kind="review_written",
                payload={"session_id": "sess-dream", "project_id": "proj-dream", "summary": f"fact {idx}"},
            )
        )
    orchestrator = LearningOrchestrator(
        project_service=project_service,
        session_store=session_store,
        executor=FakeExecutor(),
        memory_store=memory_store,
        retrieval_service=FakeRetrievalService(),
    )

    payload = orchestrator._consolidate_dream_events(
        project=project,
        session=session,
        recent_events=memory_store.list_events()[-20:],
        fallback_text="fallback text",
    )

    assert payload["source"] == "dream_consolidation"
    assert payload["recent_event_count"] == 20
    assert payload["summary"].startswith("fact 0")


def test_session_autocompact_keeps_tail_and_continuation(tmp_path):
    root = tmp_path / ".colearn" / "state"
    orchestrator = LearningOrchestrator(
        project_service=LearningProjectService(state_store=JsonStateStore(root)),
        session_store=SessionStore(state_store=JsonStateStore(root)),
        executor=FakeExecutor(),
        memory_store=EventMemoryStore(state_store=JsonStateStore(root)),
        retrieval_service=FakeRetrievalService(),
    )
    session = orchestrator.session_store.create_session(session_id="sess-compact", project_id="proj-compact")
    session.continuation_prompt = "keep going"
    session.messages = [{"role": "user", "content": f"message {idx}"} for idx in range(30)]

    orchestrator._maybe_compact_session(session)

    assert len(session.messages) == orchestrator.SESSION_AUTOCOMPACT_KEEP_TAIL + 1
    assert session.messages[0]["content"].startswith("[compacted history]")
    assert session.messages[-1]["content"] == "message 29"


def test_before_turn_adds_runtime_turn_metadata(tmp_path):
    root = tmp_path / ".colearn" / "state"
    project_service = LearningProjectService(state_store=JsonStateStore(root))
    project = project_service.create_project("proj-meta", "Metadata")
    project.anchor = {"topic": "runtime metadata"}
    project.anchor_status = "ready"
    project_service.save_project(project)

    session_store = SessionStore(state_store=JsonStateStore(root))
    session = session_store.create_session(session_id="sess-meta", project_id="proj-meta")
    session.board_facts = {
        "project_id": "proj-meta",
        "session_id": "sess-meta",
        "current_turn_mode": "EXPLORE",
        "board_version": 4,
        "current_progress": {
            "active_node_id": "node-meta",
            "active_node_label": "Node Meta",
            "completed_node_ids": [],
            "path_node_ids": [],
        },
        "student_snapshot": {
            "mastery_level": 0.4,
            "cognitive_load": "NORMAL",
            "last_user_intent_raw": "",
        },
        "gaps_and_blockers": {
            "critical_blockers": [],
            "unverified_gaps": [],
        },
        "continuation": {
            "next_prompt_hint": "continue metadata",
            "last_completed_turn_id": "",
        },
        "evidence_refs": [],
    }
    session_store.save_session(session)

    executor = FakeExecutor()
    orchestrator = LearningOrchestrator(
        project_service=project_service,
        session_store=session_store,
        executor=executor,
        memory_store=EventMemoryStore(state_store=JsonStateStore(root)),
        retrieval_service=FakeRetrievalService(),
    )

    orchestrator.run_turn(
        session_id="sess-meta",
        project_id="proj-meta",
        user_message="Continue this node.",
    )

    request = executor.last_request
    assert request.metadata["turn_mode_before"] == "EXPLORE"
    assert request.metadata["board_version_before"] == 4
    assert request.metadata["active_node_id_before"] == "node-meta"
    assert request.metadata["active_node_label_before"] == "Node Meta"
    assert request.metadata["continuation_prompt_before"] == "continue metadata"
    assert request.metadata["enabled_tools_before"] == ["memory", "lightrag"]
    assert request.metadata["source_readiness_before"] in {"", "empty", "unavailable", "partial", "ready"}
    assert request.metadata["allowed_tools_before"] == ["memory", "lightrag"]
    assert request.metadata["policy_restrictions"] == []


def test_orchestrator_persists_learning_state_writeback(tmp_path):
    root = tmp_path / ".colearn" / "state"
    project_service = LearningProjectService(state_store=JsonStateStore(root))
    project = project_service.create_project("proj-learning", "Learning")
    project.anchor = {"topic": "learning state"}
    project.anchor_status = "ready"
    project_service.save_project(project)

    session_store = SessionStore(state_store=JsonStateStore(root))
    session = session_store.create_session(session_id="sess-learning", project_id="proj-learning")
    session.board_facts = {
        "project_id": "proj-learning",
        "session_id": "sess-learning",
        "current_turn_mode": "EXPLORE",
        "board_version": 1,
        "current_progress": {
            "active_node_id": "node-1",
            "active_node_label": "Node 1",
            "completed_node_ids": [],
            "path_node_ids": [],
        },
        "student_snapshot": {
            "mastery_level": 0.1,
            "cognitive_load": "NORMAL",
            "last_user_intent_raw": "",
        },
        "gaps_and_blockers": {
            "critical_blockers": [],
            "unverified_gaps": [],
        },
        "continuation": {
            "next_prompt_hint": "继续推进",
            "last_completed_turn_id": "",
        },
        "evidence_refs": [],
    }
    session_store.save_session(session)

    orchestrator = LearningOrchestrator(
        project_service=project_service,
        session_store=session_store,
        executor=FakeExecutor(),
        memory_store=EventMemoryStore(state_store=JsonStateStore(root)),
        retrieval_service=FakeRetrievalService(),
    )

    result = orchestrator.run_turn(
        session_id="sess-learning",
        project_id="proj-learning",
        user_message="Please continue.",
    )

    saved_session = session_store.get_session("sess-learning")
    saved_project = project_service.get_project("proj-learning")

    assert result.final_text
    assert saved_session is not None
    assert saved_project is not None
    assert saved_session.board_facts["continuation"]["next_prompt_hint"]
    assert saved_session.last_turn_result["runtime_v2"]["closure_applied"] is True
    assert saved_project.board_facts["continuation"]["next_prompt_hint"]


def test_product_compression_failure_keeps_main_result(tmp_path):
    root = tmp_path / ".colearn" / "state"
    project_service = LearningProjectService(state_store=JsonStateStore(root))
    project = project_service.create_project("proj-fail", "Failure Safety")
    project.anchor = {"topic": "safety"}
    project_service.save_project(project)
    session_store = SessionStore(state_store=JsonStateStore(root))
    session_store.create_session(session_id="sess-fail", project_id="proj-fail")

    orchestrator = LearningOrchestrator(
        project_service=project_service,
        session_store=session_store,
        executor=FakeExecutor(),
        memory_store=EventMemoryStore(state_store=JsonStateStore(root)),
        product_compression=FailingProductCompression(),
        retrieval_service=FakeRetrievalService(),
    )

    result = orchestrator.run_turn(
        session_id="sess-fail",
        project_id="proj-fail",
        user_message="Explain safe async writeback.",
    )

    time.sleep(0.05)
    saved_session = session_store.get_session("sess-fail")
    assert saved_session is not None
    assert result.final_text
    assert saved_session.last_turn_result["final_text"] == result.final_text
    assert saved_session.last_turn_result["product_compression"]["status"] == "failed"
    assert any("product_compression_failed" in item for item in saved_session.last_turn_result["warnings"])


def test_background_result_only_patches_review_fields(tmp_path):
    root = tmp_path / ".colearn" / "state"
    project_service = LearningProjectService(state_store=JsonStateStore(root))
    project = project_service.create_project("proj-bg", "Background")
    session_store = SessionStore(state_store=JsonStateStore(root))
    session = session_store.create_session(session_id="sess-bg", project_id="proj-bg")
    session.status = "completed"
    session.active_turn_id = None
    session.active_turns = []
    session.messages = [{"role": "assistant", "content": "main result"}]
    session.board_version = 7
    session.board_facts = {"board_version": 7, "current_turn_mode": "VERIFY"}
    session.last_turn_result = {"final_text": "main result", "warnings": [], "product_compression": {"status": "scheduled"}}
    session_store.save_session(session)

    orchestrator = LearningOrchestrator(
        project_service=project_service,
        session_store=session_store,
        executor=FakeExecutor(),
        memory_store=EventMemoryStore(state_store=JsonStateStore(root)),
        retrieval_service=FakeRetrievalService(),
    )
    request = LearningTurnRequest(
        session_id="sess-bg",
        project_id="proj-bg",
        user_message="background",
        board_facts=BoardFacts(project_id="proj-bg", session_id="sess-bg", board_version=1),
    )
    orchestrator.apply_background_result(
        session_id="sess-bg",
        project_id="proj-bg",
        request=request,
        board=request.board_facts,
        product_output=ProductCompressionResult(
            review_summary="review",
            continuation_prompt="continue",
            board_patch={"board_version": 2},
        ),
        error=None,
        status_payload={"status": "scheduled", "started_at": 1, "finished_at": None, "error": "", "base_board_version": 1},
    )

    saved_session = session_store.get_session("sess-bg")
    assert saved_session is not None
    assert saved_session.messages == [{"role": "assistant", "content": "main result"}]
    assert saved_session.board_version == 7
    assert saved_session.board_facts["current_turn_mode"] == "VERIFY"
    assert saved_session.status == "completed"
    assert saved_session.active_turns == []
    assert saved_session.pending_review["summary"] == "review"
    assert saved_session.continuation_prompt == "continue"
    assert saved_session.last_turn_result["product_compression"]["status"] == "completed"
    assert "product_compression_stale_board_skipped" in saved_session.last_turn_result["warnings"]


def test_board_version_conflict_keeps_newer_board(tmp_path):
    root = tmp_path / ".colearn" / "state"
    project_service = LearningProjectService(state_store=JsonStateStore(root))
    current_project = project_service.create_project("proj-conflict", "Conflict")
    current_project.board_version = 3
    current_project.board_facts = {
        "project_id": "proj-conflict",
        "session_id": "sess-conflict",
        "current_turn_mode": "VERIFY",
        "board_version": 3,
    }
    project_service.save_project(current_project)
    session_store = SessionStore(state_store=JsonStateStore(root))
    current_session = session_store.create_session(session_id="sess-conflict", project_id="proj-conflict")
    current_session.board_version = 3
    current_session.board_facts = {
        "project_id": "proj-conflict",
        "session_id": "sess-conflict",
        "current_turn_mode": "VERIFY",
        "board_version": 3,
    }
    session_store.save_session(current_session)
    orchestrator = LearningOrchestrator(
        project_service=project_service,
        session_store=session_store,
        executor=FakeExecutor(),
        memory_store=EventMemoryStore(state_store=JsonStateStore(root)),
        retrieval_service=FakeRetrievalService(),
    )

    stale_board = BoardFacts(project_id="proj-conflict", session_id="sess-conflict", board_version=1)
    result_board = BoardFacts(
        project_id="proj-conflict",
        session_id="sess-conflict",
        current_turn_mode="EXPLORE",
        board_version=2,
    )
    request = LearningTurnRequest(
        session_id="sess-conflict",
        project_id="proj-conflict",
        user_message="stale turn",
        board_facts=stale_board,
    )
    result = LearningTurnResult(
        final_text="stale answer",
        board_before=stale_board,
        board_after=result_board,
        turn_mode_after="EXPLORE",
    )
    stale_session = current_session.__class__(
        session_id="sess-conflict",
        project_id="proj-conflict",
        board_facts=stale_board.to_dict(),
        board_version=1,
    )
    stale_project = LearningProject(
        project_id="proj-conflict",
        title="Conflict",
        board_facts=stale_board.to_dict(),
        board_version=1,
    )

    orchestrator._write_back(
        project=stale_project,
        session=stale_session,
        request=request,
        result=result,
    )

    saved_session = session_store.get_session("sess-conflict")
    saved_project = project_service.get_project("proj-conflict")
    assert saved_session is not None
    assert saved_project is not None
    assert saved_session.board_version == 3
    assert saved_session.board_facts["current_turn_mode"] == "VERIFY"
    assert saved_project.board_version == 3
    assert saved_project.board_facts["current_turn_mode"] == "VERIFY"
    assert "board_version_conflict_session_write_skipped" in saved_session.last_turn_result["warnings"]
    assert "board_version_conflict_project_write_skipped" in saved_session.last_turn_result["warnings"]


def test_after_turn_events_are_json_safe_and_attach_evidence(tmp_path):
    root = tmp_path / ".colearn" / "state"
    project_service = LearningProjectService(state_store=JsonStateStore(root))
    project = project_service.create_project("proj-events", "Events")
    session_store = SessionStore(state_store=JsonStateStore(root))
    session = session_store.create_session(session_id="sess-events", project_id="proj-events")
    request = LearningTurnRequest(
        session_id="sess-events",
        project_id="proj-events",
        user_message="I am confused and do not understand this node yet.",
        source_references=[{"source_ref": str(tmp_path / "note.md")}],
    )
    request = request.__class__(
        **{
            **request.__dict__,
            "board_facts": request.board_facts.__class__(
                project_id="proj-events",
                session_id="sess-events",
                current_progress=request.board_facts.current_progress.__class__(
                    active_node_id="node-1",
                    active_node_label="Node 1",
                ),
            ),
        }
    )

    payload = after_turn_payload(
        project=project,
        session=session,
        request=request,
        final_text="Node 1 is completed.",
        tool_events=[{"tool_name": "lightrag"}],
    )

    json.dumps([event.__dict__ for event in payload["learning_events"]], ensure_ascii=False)
    event_types = {event.type for event in payload["learning_events"]}
    assert "NODE_COMPLETED" in event_types
    assert "BLOCKER_FOUND" in event_types
    assert "EVIDENCE_ATTACHED" in event_types
    assert payload["board_after"].evidence_refs[0]["tool_name"] == "lightrag"
    assert payload["turn_mode_after"] == "CORRECTION"
    assert payload["turn_mode_before"] == "EXPLORE"
    assert payload["writeback_envelope"]["base_board_version"] == 1
    assert payload["writeback_envelope"]["resolved_board_version"] == payload["board_after"].board_version
    assert "NODE_COMPLETED" in payload["writeback_envelope"]["event_types"]


def test_memory_store_search_events() -> None:
    store = EventMemoryStore(state_store=JsonStateStore(Path.cwd() / ".colearn" / "test-state"))
    store.append(
        MemoryEvent(
            event_id="1",
            kind="review_written",
            payload={"session_id": "s1", "project_id": "p1", "summary": "matrix multiplication is not commutative"},
        )
    )
    store.append(
        MemoryEvent(
            event_id="2",
            kind="turn_completed",
            payload={"session_id": "s1", "project_id": "p1", "turn_mode": "EXPLORE", "summary": "matrix multiplication is not commutative"},
        )
    )
    hits = store.search_events(query="matrix", session_id="s1")
    assert len(hits) == 1
    assert hits[0].event_id == "1"


def test_knowledge_workspace_builds_source_profile(tmp_path: Path) -> None:
    service = KnowledgeWorkspaceService()
    library = service.create_library("lib-1", "Math")
    source_file = tmp_path / "note.md"
    source_file.write_text("matrix", encoding="utf-8")
    service.attach_source(library_id=library.library_id, source_path=str(source_file))
    profile = service.build_project_source_profile(
        source_refs=[str(source_file)],
        indexed_paths=[str(source_file)],
        sync_status="synced",
    )
    assert profile["readiness"] == "ready"
    assert profile["sources"][0]["indexed"] is True


def test_source_profile_reaches_request_metadata_and_prompt(tmp_path: Path) -> None:
    root = tmp_path / ".colearn" / "state"
    project_service = LearningProjectService(state_store=JsonStateStore(root))
    project = project_service.create_project("proj-source", "Sources")
    source_file = tmp_path / "source.md"
    source_file.write_text("source body", encoding="utf-8")
    project.source_refs = [str(source_file)]
    project_service.save_project(project)
    session_store = SessionStore(state_store=JsonStateStore(root))
    session_store.create_session(session_id="sess-source", project_id="proj-source")
    executor = FakeExecutor()
    orchestrator = LearningOrchestrator(
        project_service=project_service,
        session_store=session_store,
        executor=executor,
        memory_store=EventMemoryStore(state_store=JsonStateStore(root)),
        retrieval_service=FakeRetrievalService(),
    )

    orchestrator.run_turn(
        session_id="sess-source",
        project_id="proj-source",
        user_message="Use sources",
    )

    request = executor.last_request
    profile = request.metadata["source_profile"]
    assert profile["readiness"] in {"ready", "partial", "empty", "unavailable"}
    assert "sync" in profile
    saved_project = project_service.get_project("proj-source")
    assert saved_project is not None
    assert saved_project.retrieval_profile["readiness"] == profile["readiness"]
    from colearn.runtime_v2.executor import NanobotTurnExecutor

    prompt = NanobotTurnExecutor()._build_prompt(request)
    assert "Source readiness:" in prompt


def test_default_nanobot_executor_receives_constructor_dependencies(tmp_path: Path) -> None:
    root = tmp_path / ".colearn" / "state"
    memory_store = EventMemoryStore(state_store=JsonStateStore(root))
    orchestrator = LearningOrchestrator(
        project_service=LearningProjectService(state_store=JsonStateStore(root)),
        session_store=SessionStore(state_store=JsonStateStore(root)),
        memory_store=memory_store,
    )
    assert getattr(orchestrator.executor, "retrieval_service", None) is orchestrator.retrieval_service
    assert getattr(orchestrator.executor, "memory_store", None) is memory_store


def test_runtime_v2_prompt_includes_learning_state_lines() -> None:
    from colearn.runtime_v2.prompting import build_turn_prompt

    request = LearningTurnRequest(
        session_id="sess-ls",
        project_id="proj-ls",
        project_title="Learning State",
        user_message="Help me move forward",
        continuation_prompt="Focus on the next proof step.",
        board_facts=BoardFacts(
            project_id="proj-ls",
            session_id="sess-ls",
            current_progress=ProgressFacts(
                active_node_id="node-proof",
                active_node_label="Proof by induction",
            ),
            student_snapshot=StudentSnapshot(
                mastery_level=0.42,
                cognitive_load="HIGH",
            ),
            gaps_and_blockers=GapsAndBlockers(
                critical_blockers=[Blocker(id="blk-1", desc="Confuses base case and induction step")],
                unverified_gaps=["Cannot explain why the induction hypothesis is sufficient"],
            ),
            evidence_refs=[{"source_ref": "note-1"}],
        ),
        state_projection=LearningStateSnapshot(
            active_node_id="node-proof",
            active_node_label="Proof by induction",
            mastery_level=0.42,
            cognitive_load="HIGH",
        ),
    )

    prompt = build_turn_prompt(request)

    assert "Learning focus: Proof by induction" in prompt
    assert "Learner state: mastery=0.42; cognitive_load=HIGH" in prompt
    assert "Critical blockers: Confuses base case and induction step" in prompt
    assert "Unverified gaps: Cannot explain why the induction hypothesis is sufficient" in prompt
    assert "Continuation hint: Focus on the next proof step." in prompt
    assert "Evidence refs attached: 1" in prompt


def test_runtime_v2_result_bridge_attaches_board_summary() -> None:
    from colearn.runtime_v2.result_bridge import normalize_learning_turn_result as normalize_v2_result

    request = LearningTurnRequest(
        session_id="sess-summary",
        project_id="proj-summary",
        project_title="Board Summary",
        user_message="Summarize the current state",
        turn_mode="VERIFY",
        board_facts=BoardFacts(
            project_id="proj-summary",
            session_id="sess-summary",
            current_turn_mode="VERIFY",
            current_progress=ProgressFacts(
                active_node_id="node-verify",
                active_node_label="Verify inference",
            ),
            student_snapshot=StudentSnapshot(
                mastery_level=0.75,
                cognitive_load="NORMAL",
            ),
            gaps_and_blockers=GapsAndBlockers(
                critical_blockers=[Blocker(id="blk-2", desc="Needs evidence for step 3")],
                unverified_gaps=["Missing justification for the transformation"],
            ),
        ),
        state_projection=LearningStateSnapshot(
            active_node_id="node-verify",
            active_node_label="Verify inference",
            mastery_level=0.75,
            cognitive_load="NORMAL",
        ),
    )

    result = normalize_v2_result(
        request=request,
        final_text="Here is the current state.",
        learning_result={"tool_events": [], "raw_messages": []},
    )

    board_summary = result.metadata["runtime_v2_board_summary"]
    assert board_summary["turn_mode"] == "VERIFY"
    assert board_summary["active_node_id"] == "node-verify"
    assert board_summary["active_node_label"] == "Verify inference"
    assert board_summary["mastery_level"] == 0.75
    assert board_summary["cognitive_load"] == "NORMAL"
    assert board_summary["critical_blocker_count"] == 1
    assert board_summary["unverified_gap_count"] == 1
    assert result.raw_learning_result["runtime_v2"]["board_summary"] == board_summary


def test_runtime_v2_learning_closure_marks_runtime_metadata() -> None:
    from colearn.runtime_v2.learning_closure import build_learning_closure

    project = LearningProject(project_id="proj-closure", title="Closure")
    session = SessionStore().create_session(session_id="sess-closure", project_id="proj-closure")
    request = LearningTurnRequest(
        session_id="sess-closure",
        project_id="proj-closure",
        user_message="Finish this learning turn",
        board_facts=BoardFacts(project_id="proj-closure", session_id="sess-closure"),
    )

    payload = build_learning_closure(
        project=project,
        session=session,
        request=request,
        final_text="Turn finished.",
        raw_learning_result={"tool_events": [{"tool_name": "lightrag"}]},
        warnings=["runtime_note"],
    )

    assert payload["runtime_v2"]["closure_applied"] is True
    assert payload["warnings"] == ["runtime_note"]
    assert payload["tool_events"] == [{"tool_name": "lightrag"}]
    assert "board_after" in payload


def test_runtime_v2_tooling_registers_memory_and_lightrag(monkeypatch) -> None:
    from colearn.runtime_v2.tooling import install_colearn_tools

    class FakeRegistry:
        def __init__(self) -> None:
            self.items: dict[str, object] = {}

        def has(self, name: str) -> bool:
            return name in self.items

        def unregister(self, name: str) -> None:
            self.items.pop(name, None)

        def register(self, tool: object) -> None:
            self.items[getattr(tool, "name")] = tool

    class FakeLoop:
        def __init__(self) -> None:
            self.tools = FakeRegistry()

    class FakeBot:
        def __init__(self) -> None:
            self._loop = FakeLoop()

    class FakeTool:
        async def execute(self, **kwargs):
            return ""

    def fake_tool_parameters(_schema):
        def decorator(cls):
            return cls
        return decorator

    monkeypatch.setitem(
        sys.modules,
        "nanobot.agent.tools.base",
        SimpleNamespace(Tool=FakeTool, tool_parameters=fake_tool_parameters),
    )

    bot = FakeBot()
    request = LearningTurnRequest(
        session_id="sess-tools",
        project_id="proj-tools",
        user_message="Find the source",
        enabled_tools=["memory", "lightrag"],
    )

    install_colearn_tools(bot=bot, request=request, workspace=Path.cwd())

    assert "memory" in bot._loop.tools.items
    assert "lightrag" in bot._loop.tools.items
