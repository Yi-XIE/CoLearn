# ContextVar POC 验证报告

> 日期：2026-06-01  
> 分支：`插件尝试`  
> commit：3d8166b 之后

## 目标

验证能否通过 Python `ContextVar` 在不修改 nanobot 源码的前提下，把 CoLearn 的 `session_id` 传到 nanobot 的 `AgentHook` 内部。这是整个插件化方案能否成立的**最关键技术风险**——如果传不进去，hook 就无法关联到 CoLearn 的学习状态，整个方案需要回退到"在 messages 注入特殊标记"或"fork nanobot"。

## 关键调用链分析

通读 `nanobot 0.2.0` 源码确认，从 SDK 入口到 hook 触发，全程在同一个 async task 中：

```
bot.run(message, session_key=...)                       # nanobot.py:73
  └─ await self._loop.process_direct(...)               # nanobot.py:93
      └─ await runner.run(spec)                         # agent/runner.py:235
          └─ await hook.before_iteration(context)       # agent/runner.py:278
          └─ await hook.before_execute_tools(context)   # agent/runner.py:322
          └─ await hook.after_iteration(context)        # agent/runner.py:356
```

**结论**：调用链无 `loop.run_in_executor`、无 `asyncio.create_task` 把 hook 派发到独立 task —— 全程 await 链。`ContextVar` 在此场景下沿调用栈自动传播。

## POC 设计

POC 不依赖真 LLM provider，用 `fake_nanobot_run` 模拟同样的 await 嵌套结构，并 mock `AgentHook` 的生命周期方法。三个测试场景：

1. **单一会话传播**：`set` 一次，hook 多次读取，每次读到同一个值
2. **并发会话隔离**（**真考验**）：两个 session 用 `asyncio.gather` 并发跑，要求 hook_a 只看到 alpha，hook_b 只看到 beta，不能串号
3. **优雅降级**：未 set 时，`get(default=None)` 返回 None，不抛错

POC 在每个 hook 调用之间插入 `await asyncio.sleep(0)`，强制 event loop 切换，确保即使 task 交错执行，ContextVar 隔离仍然成立。

## 测试结果

```
=== 场景 1: 单一会话传播 ===
hook 观察到 6 次调用：
  before_iteration          -> session_id='session_alpha'
  before_execute_tools      -> session_id='session_alpha'
  after_iteration           -> session_id='session_alpha'
  before_iteration          -> session_id='session_alpha'
  before_execute_tools      -> session_id='session_alpha'
  after_iteration           -> session_id='session_alpha'
结果: ✅ PASS

=== 场景 2: 并发会话隔离 ===
hook_a 观察到的 session_id: {'session_alpha'}
hook_b 观察到的 session_id: {'session_beta'}
结果: ✅ PASS

=== 场景 3: 未设置时的优雅降级 ===
hook 观察到的值: {None}
结果: ✅ PASS

总结: 3/3 通过
```

## 结论

**ContextVar 方案可行**，正式作为 CoLearn 插件的 `session_id` 传递机制。

### 使用模式

```python
from contextvars import ContextVar

_session_var: ContextVar[str | None] = ContextVar("colearn_session_id", default=None)

# 在 bot.run() 调用前设置
async def colearn_turn(session_id: str, message: str) -> RunResult:
    token = _session_var.set(session_id)
    try:
        return await bot.run(message, session_key=session_id, hooks=[learning_hook])
    finally:
        _session_var.reset(token)

# 在 hook 内部读取
class LearningHook(AgentHook):
    async def before_iteration(self, ctx: AgentHookContext) -> None:
        sid = _session_var.get()
        if sid is None:
            return  # 不在 colearn 上下文中，跳过
        learning_session = await self.state_manager.load(sid)
        # ... 注入学习计划等
```

### 关键约束

1. **必须用 `try/finally + reset(token)`**：避免 ContextVar 泄漏到上层调用栈，污染后续 turn
2. **必须设置 `default=None`**：让插件可以与不带 colearn 上下文的 nanobot 调用共存
3. **如果未来 nanobot 改用 `asyncio.create_task` 调用 hook**：ContextVar 仍会传播（`create_task` 默认 copy 当前 context），但要监控这个变化

## 后续动作

- ✅ 验证完成，可以基于 ContextVar 设计 `LearningHook`
- ⏳ 等待 workflow `w17lxj3ns` 完成完整技术设计（hook 映射、状态管理、目录结构等）
- ⏳ workflow 完成后开始 Phase 1 实施

## 文件

- POC 源码：[colearn_plugin/poc/contextvar_poc.py](../colearn_plugin/poc/contextvar_poc.py)
- 运行命令：`python3 colearn_plugin/poc/contextvar_poc.py`
