"""Live end-to-end smoke test — real DeepSeek LLM call through full pipeline.

Boots the orchestrator with a real NanobotTurnExecutor (no fakes) and runs
a single turn. Reports which stages actually fired vs short-circuited.

Run from D:\\CoLearn-nightly:
    python -m tests.live_smoke
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "third_party" / "nanobot-core"))

# Required env (caller may override before invoking)
os.environ.setdefault("DEEPSEEK_API_KEY", "")
os.environ.setdefault("DEEPSEEK_API_BASE", "https://api.deepseek.com")
os.environ.setdefault("DEEPSEEK_MODEL", "deepseek-v4-flash")
os.environ.setdefault("COLEARN_NANOBOT_TOKEN_ISSUE_SECRET", "")
os.environ.setdefault("COLEARN_TURN_TIMEOUT", "60")

# Use a throwaway state dir so we don't pollute the real one.
TMP_STATE = tempfile.mkdtemp(prefix="colearn-smoke-")
os.environ["COLEARN_STATE_ROOT"] = TMP_STATE


def _expand_config() -> Path:
    """Expand ${VAR} in nanobot config — same trick server.py uses."""
    raw_path = ROOT / ".colearn" / "nanobot-v0.2-slim.config.json"
    expanded = os.path.expandvars(raw_path.read_text(encoding="utf-8"))
    tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    tmp.write(expanded)
    tmp.close()
    return Path(tmp.name)


def _print_section(title: str) -> None:
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")


def main() -> int:
    if not os.environ.get("DEEPSEEK_API_KEY"):
        print("DEEPSEEK_API_KEY not set in env — abort.")
        return 1

    _print_section("Phase A: import + wire orchestrator (real components)")
    from colearn.app.learning_orchestrator import LearningOrchestrator
    from colearn.compression import ProductCompressionBridge, RuntimeCompressionBridge
    from colearn.knowledge import KnowledgeWorkspaceService
    from colearn.memory.store import EventMemoryStore
    from colearn.projects.service import LearningProjectService
    from colearn.retrieval.service import RetrievalService
    from colearn.runtime_v2.executor import NanobotTurnExecutor
    from colearn.sessions.store import SessionStore

    config_path = _expand_config()
    workspace = ROOT / ".colearn" / "nanobot-workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    retrieval = RetrievalService(workspace=workspace)
    print(f"  retrieval client    : {type(retrieval._lightrag_client).__name__ if retrieval._lightrag_client else 'NONE'}")
    print(f"  retrieval err       : {retrieval._lightrag_error}")

    executor = NanobotTurnExecutor(
        workspace=workspace,
        config_path=config_path,
        retrieval_service=retrieval,
        memory_store=None,
    )
    orch = LearningOrchestrator(
        project_service=LearningProjectService(),
        session_store=SessionStore(),
        memory_store=EventMemoryStore(),
        knowledge_service=KnowledgeWorkspaceService(),
        retrieval_service=retrieval,
        executor=executor,
        runtime_compression=RuntimeCompressionBridge(),
        product_compression=ProductCompressionBridge(),
    )
    print("  orchestrator ready  : OK")

    _print_section("Phase B: live turn via run_turn_async (real LLM)")
    stream_log: list[dict] = []

    def on_stream(ev: dict) -> None:
        et = ev.get("type") or ev.get("event") or ""
        stream_log.append({"type": et, "len": len(str(ev.get("content") or ""))})

    t0 = time.time()
    try:
        result = asyncio.run(
            orch.run_turn_async(
                session_id="smoke-1",
                user_message="One sentence: what is photosynthesis?",
                project_id="smoke-project",
                stream_emit=on_stream,
            )
        )
        elapsed_ms = int((time.time() - t0) * 1000)
        print(f"  turn elapsed        : {elapsed_ms} ms")
        print(f"  final_text          : {(result.final_text or '')[:160]!r}")
        print(f"  warnings            : {list(result.warnings)}")
        print(f"  turn_mode_after     : {result.turn_mode_after}")
        print(f"  raw_messages count  : {len(result.raw_learning_result.get('raw_messages') or [])}")
    except Exception as exc:
        print(f"  TURN FAILED         : {type(exc).__name__}: {exc}")
        traceback.print_exc()
        return 2

    _print_section("Phase C: stream events seen")
    if not stream_log:
        print("  (none — streaming may be disabled or hooks not wired)")
    else:
        from collections import Counter
        counts = Counter(item["type"] for item in stream_log)
        for kind, n in counts.most_common():
            print(f"  {kind:24s} : {n}")

    _print_section("Phase D: stage-by-stage state inspection")
    session = orch.session_store.get_session("smoke-1")
    project = orch.project_service.get_project("smoke-project")
    events = orch.memory_store.list_events()
    print(f"  session.messages     : {len(session.messages) if session else 0}")
    print(f"  session.board_version: {session.board_version if session else '-'}")
    print(f"  session.turn_mode    : {session.turn_mode if session else '-'}")
    print(f"  project.anchor_status: {project.anchor_status if project else '-'}")
    print(f"  memory events        : {len(events)}")
    if events:
        from collections import Counter
        print(f"  event kinds          : {dict(Counter(e.kind for e in events))}")

    _print_section("Phase E: cache + retrieval status")
    print(f"  retrieval cache stats: {retrieval._cache.stats}")
    last = (session.last_turn_result or {}) if session else {}
    runtime_v2 = (last.get("runtime_v2") or {})
    retr = (runtime_v2.get("retrieval") or {})
    print(f"  retrieval_hits       : {len(retr.get('retrieval_hits') or [])}")
    print(f"  retrieval_misses     : {len(retr.get('retrieval_misses') or [])}")
    print(f"  prefetched refs      : {len(retr.get('prefetched_references') or [])}")

    _print_section("Phase F: second turn — should be cache hit if same query/sources")
    t1 = time.time()
    asyncio.run(
        orch.run_turn_async(
            session_id="smoke-1",
            user_message="Now in two sentences.",
            project_id="smoke-project",
            stream_emit=lambda ev: None,
        )
    )
    print(f"  2nd turn elapsed     : {int((time.time() - t1) * 1000)} ms")
    print(f"  retrieval cache stats: {retrieval._cache.stats}")

    print("\nDONE.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
