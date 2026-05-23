"""End-to-end smoke with REAL LightRAG-HKU + DeepSeek + SiliconFlow embedding.

1) Loads .env
2) Configures project with the 4 AI/ML knowledge docs as source_refs
3) Runs orchestrator.run_turn_async — should now show retrieval_hits > 0
4) Runs a 2nd turn with same query — should hit the retrieval cache
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "third_party" / "nanobot-core"))


def _load_env() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"'))


def main() -> int:
    _load_env()
    if not os.environ.get("DEEPSEEK_API_KEY"):
        print("DEEPSEEK_API_KEY missing — aborting.")
        return 1
    if not os.environ.get("SILICONFLOW_API_KEY"):
        print("SILICONFLOW_API_KEY missing — aborting.")
        return 1
    os.environ.setdefault("COLEARN_NANOBOT_TOKEN_ISSUE_SECRET", "")
    os.environ.setdefault("COLEARN_TURN_TIMEOUT", "180")

    tmp_state = tempfile.mkdtemp(prefix="colearn-rag-smoke-")
    os.environ["COLEARN_STATE_ROOT"] = tmp_state

    from colearn.app.learning_orchestrator import LearningOrchestrator
    from colearn.compression import ProductCompressionBridge, RuntimeCompressionBridge
    from colearn.knowledge import KnowledgeWorkspaceService
    from colearn.memory.store import EventMemoryStore
    from colearn.projects.service import LearningProjectService
    from colearn.retrieval.service import RetrievalService
    from colearn.runtime_v2.executor import NanobotTurnExecutor
    from colearn.sessions.store import SessionStore

    workspace = ROOT / ".colearn" / "nanobot-workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    config_path = ROOT / ".colearn" / "nanobot-v0.2-slim.config.json"
    expanded = os.path.expandvars(config_path.read_text(encoding="utf-8"))
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        f.write(expanded)
        config_tmp = Path(f.name)

    retrieval = RetrievalService(workspace=workspace)
    print(f"  retrieval client : {type(retrieval._lightrag_client).__name__ if retrieval._lightrag_client else 'NONE'}")
    if retrieval._lightrag_error:
        print(f"  ERROR: {retrieval._lightrag_error}")
        return 2

    executor = NanobotTurnExecutor(
        workspace=workspace,
        config_path=config_tmp,
        retrieval_service=retrieval,
        memory_store=None,
    )
    project_service = LearningProjectService()
    orch = LearningOrchestrator(
        project_service=project_service,
        session_store=SessionStore(),
        memory_store=EventMemoryStore(),
        knowledge_service=KnowledgeWorkspaceService(),
        retrieval_service=retrieval,
        executor=executor,
        runtime_compression=RuntimeCompressionBridge(),
        product_compression=ProductCompressionBridge(),
    )

    kb_dir = ROOT / ".colearn" / "knowledge-base" / "ai-ml"
    source_refs = [str(p) for p in sorted(kb_dir.glob("*.md"))]
    print(f"\n  source_refs ({len(source_refs)}):")
    for s in source_refs:
        print(f"    - {s}")

    project = project_service.create_project(
        "ai-ml-tutor",
        title="AI/ML Tutor",
    )
    project.source_refs = source_refs
    project_service.save_project(project)

    print("\n=== Turn 1 (cold; will index + query LightRAG) ===")
    stream_count = 0

    def emit(_):
        nonlocal stream_count
        stream_count += 1

    t0 = time.time()
    try:
        result = asyncio.run(
            orch.run_turn_async(
                session_id="rag-1",
                user_message="什么是 Transformer 的自注意力机制？关键公式是什么？",
                project_id="ai-ml-tutor",
                stream_emit=emit,
            )
        )
    except Exception as exc:
        import traceback
        traceback.print_exc()
        print(f"\nTurn 1 FAILED: {type(exc).__name__}: {exc}")
        return 3
    elapsed_1 = int((time.time() - t0) * 1000)
    print(f"  elapsed: {elapsed_1} ms, stream events: {stream_count}")
    print(f"  final: {(result.final_text or '')[:240]!r}")

    session = orch.session_store.get_session("rag-1")
    last = (session.last_turn_result or {})
    runtime_v2 = (last.get("runtime_v2") or {})
    retr = runtime_v2.get("retrieval") or {}
    hits = retr.get("retrieval_hits") or []
    refs = retr.get("prefetched_references") or []
    bundle_q = retr.get("retrieval_query_context", {}).get("final_query")
    print(f"\n  retrieval_hits     : {len(hits)}")
    print(f"  prefetched_refs    : {len(refs)}")
    if refs:
        for r in refs[:3]:
            print(f"    - {r.get('source_ref') or r.get('source_path') or r.get('title')}")
    print(f"  retrieval_query    : {bundle_q!r}")
    print(f"  cache stats        : {retrieval._cache.stats}")

    print("\n=== Turn 2 (same query class; expecting cache hit) ===")
    t1 = time.time()
    asyncio.run(
        orch.run_turn_async(
            session_id="rag-1",
            user_message="再讲一下多头注意力是怎么并行的？",
            project_id="ai-ml-tutor",
            stream_emit=lambda _: None,
        )
    )
    elapsed_2 = int((time.time() - t1) * 1000)
    print(f"  elapsed: {elapsed_2} ms")
    print(f"  cache stats        : {retrieval._cache.stats}")

    print("\nDONE.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
