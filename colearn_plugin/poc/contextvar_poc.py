"""ContextVar POC: 验证能否通过 ContextVar 把 session_id 传到 nanobot AgentHook 内部。

核心假设：
- nanobot.run() → loop.process_direct() → runner.run() → hook.before_iteration() 全程 await 链。
- asyncio 中 ContextVar 沿着 await 链自动传播，且每个 task 有独立 copy。
- 所以在 bot.run() 之前 set ContextVar，hook 内部就能 get 到。

POC 不依赖真 LLM —— 我们 mock 一个 provider，只验证传递机制。
"""

from __future__ import annotations

import asyncio
import sys
from contextvars import ContextVar
from pathlib import Path

# 让 bundled nanobot 可被 import
NANOBOT_ROOT = Path("/Users/xieyi/CoLearn/third_party/nanobot-0.2.0/nanobot-0.2.0")
sys.path.insert(0, str(NANOBOT_ROOT))

from nanobot.agent.hook import AgentHook, AgentHookContext  # noqa: E402

# ---------------------------------------------------------------------------
# 1. 定义 ContextVar —— 这是插件用来传 session_id 的"暗管道"
# ---------------------------------------------------------------------------
colearn_session_id_var: ContextVar[str | None] = ContextVar(
    "colearn_session_id", default=None
)


# ---------------------------------------------------------------------------
# 2. 一个会从 ContextVar 读取 session_id 的 hook
# ---------------------------------------------------------------------------
class SessionAwareHook(AgentHook):
    """模拟 CoLearn 插件的 hook：在生命周期方法中读取 session_id。"""

    def __init__(self) -> None:
        super().__init__()
        self.observed: list[tuple[str, str | None]] = []  # (lifecycle, session_id)

    async def before_iteration(self, context: AgentHookContext) -> None:
        sid = colearn_session_id_var.get()
        self.observed.append(("before_iteration", sid))

    async def after_iteration(self, context: AgentHookContext) -> None:
        sid = colearn_session_id_var.get()
        self.observed.append(("after_iteration", sid))

    async def before_execute_tools(self, context: AgentHookContext) -> None:
        sid = colearn_session_id_var.get()
        self.observed.append(("before_execute_tools", sid))


# ---------------------------------------------------------------------------
# 3. 模拟 nanobot 的 await 调用链
#    我们不启真 LLM —— 只验证 ContextVar 是否能跨越多层 async 函数
# ---------------------------------------------------------------------------
async def fake_nanobot_run(hook: SessionAwareHook) -> None:
    """模拟 bot.run() → loop.process_direct() → runner.run() 的多层 await。"""
    await fake_loop_process_direct(hook)


async def fake_loop_process_direct(hook: SessionAwareHook) -> None:
    """模拟 AgentLoop.process_direct()。"""
    await fake_runner_run(hook)


async def fake_runner_run(hook: SessionAwareHook) -> None:
    """模拟 AgentRunner.run() 的多次迭代调用 hook。"""
    for iteration in range(2):
        ctx = AgentHookContext(iteration=iteration, messages=[])
        await hook.before_iteration(ctx)
        await asyncio.sleep(0)  # 让出 event loop —— 检验 task 切换不会丢失 ContextVar
        await hook.before_execute_tools(ctx)
        await asyncio.sleep(0)
        await hook.after_iteration(ctx)


# ---------------------------------------------------------------------------
# 4. 三个测试场景
# ---------------------------------------------------------------------------
async def test_basic_propagation() -> bool:
    """场景 1：单一会话，ContextVar 应贯穿整个调用链。"""
    print("\n=== 场景 1: 单一会话传播 ===")
    hook = SessionAwareHook()
    token = colearn_session_id_var.set("session_alpha")
    try:
        await fake_nanobot_run(hook)
    finally:
        colearn_session_id_var.reset(token)

    print(f"hook 观察到 {len(hook.observed)} 次调用：")
    for stage, sid in hook.observed:
        print(f"  {stage:25s} -> session_id={sid!r}")

    ok = all(sid == "session_alpha" for _, sid in hook.observed)
    print(f"结果: {'✅ PASS' if ok else '❌ FAIL'}")
    return ok


async def test_concurrent_sessions() -> bool:
    """场景 2：两个会话并发跑，ContextVar 必须各自隔离 —— 这才是真考验。"""
    print("\n=== 场景 2: 并发会话隔离 ===")

    async def run_session(session_id: str, hook: SessionAwareHook) -> None:
        token = colearn_session_id_var.set(session_id)
        try:
            await fake_nanobot_run(hook)
        finally:
            colearn_session_id_var.reset(token)

    hook_a = SessionAwareHook()
    hook_b = SessionAwareHook()

    # 关键：用 gather 让两个会话真正并发交错
    await asyncio.gather(
        run_session("session_alpha", hook_a),
        run_session("session_beta", hook_b),
    )

    a_ok = all(sid == "session_alpha" for _, sid in hook_a.observed)
    b_ok = all(sid == "session_beta" for _, sid in hook_b.observed)

    print(f"hook_a 观察到的 session_id: {set(sid for _, sid in hook_a.observed)}")
    print(f"hook_b 观察到的 session_id: {set(sid for _, sid in hook_b.observed)}")
    print(f"结果: {'✅ PASS' if (a_ok and b_ok) else '❌ FAIL（隔离失败！）'}")
    return a_ok and b_ok


async def test_unset_var() -> bool:
    """场景 3：没 set ContextVar 时，hook get 到 None（不应抛错）。"""
    print("\n=== 场景 3: 未设置时的优雅降级 ===")
    hook = SessionAwareHook()
    await fake_nanobot_run(hook)

    all_none = all(sid is None for _, sid in hook.observed)
    print(f"hook 观察到的值: {set(sid for _, sid in hook.observed)}")
    print(f"结果: {'✅ PASS' if all_none else '❌ FAIL'}")
    return all_none


# ---------------------------------------------------------------------------
# 5. 入口
# ---------------------------------------------------------------------------
async def main() -> int:
    print("=" * 60)
    print("ContextVar POC: 验证 session_id 跨 nanobot AgentHook 传递")
    print("=" * 60)

    results = [
        await test_basic_propagation(),
        await test_concurrent_sessions(),
        await test_unset_var(),
    ]

    print("\n" + "=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"总结: {passed}/{total} 通过")
    if passed == total:
        print("✅ ContextVar 方案可行 —— 可以作为 session_id 传递机制")
        return 0
    else:
        print("❌ ContextVar 方案有问题 —— 需要 fallback")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
