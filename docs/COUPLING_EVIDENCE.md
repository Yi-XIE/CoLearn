# CoLearn ↔ nanobot 耦合证据档案

> 日期：2026-06-01  
> 用途：把 workflow 给出的"10 个耦合问题"落到具体代码片段，作为插件化重构的基础资料。

每条证据格式：
- **耦合形式**：CoLearn 怎么"伸进"了 nanobot 的内部
- **证据**：具体文件:行号 + 关键代码
- **失败模式**：nanobot 升级时这里会怎么坏
- **插件化后归属**：重构后这段逻辑住在哪、走什么接口

---

## 1. 私有属性 `bot._loop` 的多处访问

**耦合形式**：CoLearn 直接访问 `nanobot.Nanobot` 的私有 `_loop` 属性，从中拿 sessions、tools、model_presets、_cancel_active_tasks。

**证据 A — 模型预设**：[colearn/runtime_v2/executor.py:257-274](../colearn/runtime_v2/executor.py)

```python
def _apply_model_preset(self, *, bot, preset, request) -> None:
    loop = getattr(bot, "_loop", None)
    if loop is None or not hasattr(loop, "set_model_preset"):
        request.metadata.setdefault("_runtime_warnings", []).append("model_preset_runtime_unavailable")
        return
    available = set((getattr(loop, "model_presets", {}) or {}).keys())
    ...
    loop.set_model_preset(resolved)
```

**证据 B — 取消任务**：[colearn/runtime_v2/executor.py:229-245](../colearn/runtime_v2/executor.py)

```python
def cancel_session(self, session_id: str) -> bool:
    ...
    bot_loop = getattr(self._bot, "_loop", None)
    if bot_loop is None or not hasattr(bot_loop, "_cancel_active_tasks"):
        return False
    future = asyncio.run_coroutine_threadsafe(
        bot_loop._cancel_active_tasks(session_id),  # 私有方法
        loop,
    )
```

**证据 C — sustained goal 改写 session metadata**：[colearn/runtime_v2/executor.py:333-359](../colearn/runtime_v2/executor.py)

```python
from nanobot.session.goal_state import GOAL_STATE_KEY, parse_goal_state

bot = self._get_bot()
sessions = getattr(getattr(bot, "_loop", None), "sessions", None)
session = sessions.get_or_create(session_id)
metadata = session.metadata
metadata[GOAL_STATE_KEY] = {
    "status": "active",
    "objective": objective,
    ...
}
```

**失败模式**：
- nanobot 把 `_loop` 改名/拆分 → AttributeError
- `set_model_preset` 接口变更 → 静默降级到 default
- `GOAL_STATE_KEY` 重命名或 schema 改 → 学习目标同步失效但不报错
- `_cancel_active_tasks` 是带下划线的私有 API，nanobot 可能任何小版本删掉

**插件化后归属**：
- 模型预设 → `LearningHook.before_iteration` 里通过 nanobot 公共 API 走（如果有），没有就自己持有 model 选择逻辑
- 取消任务 → CoLearn 自己的 cancel_check 回调（已经有了），不再依赖 nanobot 内部
- sustained goal → 不再写 nanobot session metadata。learning goal 完全住在 `LearningStateManager`，独立 JSON 存储

---

## 2. 工具注册表 `bot.tools` / `bot._loop.tools` 的双路径访问

**耦合形式**：每个 turn 都要重新绑定/注册 CoLearn 工具到 nanobot 的工具注册表，且要兼容两种访问路径。

**证据**：[colearn/runtime_v2/tooling.py:93-107](../colearn/runtime_v2/tooling.py)

```python
def _resolve_tool_registry(*, bot, request) -> ToolRegistryLike:
    registry = getattr(bot, "tools", None)
    if registry is not None:
        return registry

    loop = getattr(bot, "_loop", None)
    registry = getattr(loop, "tools", None)
    if registry is not None:
        _append_runtime_warning(request, "tool_registry_private_api_fallback")
        return registry

    raise RuntimeError(
        "CoLearn tools requested but nanobot exposes no compatible tool registry. "
        "Expected bot.tools or bot._loop.tools."
    )
```

**证据**：[colearn/runtime_v2/tooling.py:404-490](../colearn/runtime_v2/tooling.py)（`register_colearn_tools` 调用 `registry.register/unregister/has/get`）

**失败模式**：
- nanobot 把 ToolRegistry 接口换签名（比如 `register` 改成 `add_tool`）→ AttributeError
- nanobot 把 `tools` 完全移到 SessionManager 维度 → 双路径 fallback 全失效

**插件化后归属**：
- LightRAG / memory / web_search / emit_learning_events 四个工具改成走 nanobot **官方插件入口**（entry_point `nanobot.tools` 或 MCP）
- 每个 turn 不再"动态 bind 上下文"，改用 ContextVar 让工具内部 `get()` 当前 `LearningTurnRequest`（和 session_id 同一套机制）

---

## 3. 流式 Hook `_StreamHook` 嵌在 executor 内部

**耦合形式**：CoLearn 把 `_StreamHook` 定义成 `NanobotTurnExecutor` 的内部类，紧贴 `AgentHook` 的生命周期方法实现 stream/reasoning/tool_call 桥接。

**证据**：[colearn/runtime_v2/executor.py:94-100](../colearn/runtime_v2/executor.py) + 调用点 [executor.py:209](../colearn/runtime_v2/executor.py)

```python
class _StreamHook(AgentHook):
    def __init__(self, emit):
        super().__init__()
        self._emit = emit

    def wants_streaming(self) -> bool:
        return True
    # ... on_stream / emit_reasoning / before_execute_tools / after_iteration
```

**失败模式**：
- nanobot 给 `AgentHook` 加新生命周期方法 → 不调（因为基类有空实现）但可能错过新事件
- 改方法签名（如 `on_stream(context, delta)` → `on_stream(context, delta, kind)`）→ 静默丢事件或 TypeError

**插件化后归属**：
- 抽出独立模块 `colearn_plugin/hooks/stream_bridge.py`
- 仍然 subclass `AgentHook`（这是 nanobot 给的官方扩展点，可接受）
- 但在 hook 和 CoLearn `StreamEventType` 之间放一个 **HookAdapter**，集中处理 nanobot 升级时的方法签名变化
- 加一个 nanobot 版本检测：启动时打印 `AgentHook.__abstractmethods__` / dir，发现新方法时记日志

---

## 4. ContextBuilder 的 `channel='colearn'` 硬编码

**耦合形式**：构建 system prompt 时硬编码一个 nanobot 不知道的 channel 名。

**证据**：[colearn/runtime_v2/prompting.py](../colearn/runtime_v2/prompting.py) `from nanobot.agent.context import ContextBuilder` + 后续调用 `ContextBuilder(workspace).build_system_prompt(skill_names, channel='colearn')`

**失败模式**：
- nanobot 收紧 channel 校验 → ValueError
- nanobot 移除 `channel` 参数 → TypeError

**插件化后归属**：
- 不依赖 nanobot 的 `ContextBuilder`，CoLearn 插件自己拼 system prompt
- 把"学习 phase / 计划 / mastery"这部分由 `LearningHook.before_iteration` 用 `messages.append({"role": "system", ...})` 注入，而不是改 ContextBuilder

---

## 5. `bot.run()` 返回值的隐式契约

**耦合形式**：[executor.py:227](../colearn/runtime_v2/executor.py) `return result.content, result.messages, result.tools_used` —— 假设返回的对象有这三个属性，但 nanobot `RunResult` 字段无版本协议。

**失败模式**：
- nanobot 把 `tools_used` 改成 `tool_calls` → AttributeError
- 返回值改成 dict → 全部 break

**插件化后归属**：
- 在插件内部包一个 `RunResultAdapter`，集中所有"从 nanobot 返回值取 CoLearn 想要字段"的逻辑
- 如果未来 nanobot RunResult 改了，只改这一个 adapter

---

## 6. 工具的 `ContextAware` 协议（未文档化）

**耦合形式**：`ColearnLightRAGTool` 实现 `ContextAware` 接口，期望 nanobot 在执行工具前调 `set_context(RequestContext)`。这是 nanobot 内部约定，没有公开文档。

**证据**：[colearn/runtime_v2/tooling.py](../colearn/runtime_v2/tooling.py) `from nanobot.agent.tools.context import ContextAware, RequestContext`

**失败模式**：
- nanobot 改了 ContextAware 调用时机 → 工具拿到的 context 是上一个 turn 的，数据串号
- nanobot 删掉 ContextAware → 工具无法获取 per-turn 信息

**插件化后归属**：
- **彻底放弃** `ContextAware`
- 工具改成从 ContextVar 读 `LearningTurnRequest`（和 session_id 一样的机制）—— 已 POC 验证可行
- 这样工具是无状态的，只要 ContextVar 在 `bot.run()` 之前 set，工具内部 `get()` 就拿到当前 turn 的数据

---

## 7. session_key 隔离语义

**耦合形式**：`bot.run(prompt, session_key=session_key, ...)` 假设 nanobot 会按 key 隔离对话历史，但隔离粒度和持久化语义没合同。

**证据**：[executor.py:206-210](../colearn/runtime_v2/executor.py)

**失败模式**：
- nanobot 改了 session_key 的 hash 规则 → 历史"消失"
- nanobot 把 session 改成进程级共享 → 跨用户串号（严重）

**插件化后归属**：
- 对话历史 CoLearn **自己存**（已经有 `SessionStore`），不依赖 nanobot 的 session 持久化
- session_key 只用作"this turn 的临时上下文 key"，不再期待跨 turn 的数据落在 nanobot session 里

---

## 8. 模型预设名称硬编码

**耦合形式**：CoLearn 代码里硬编码 `'explore'`、`'deep'` 这俩 nanobot 预设名。

**证据**：[executor.py:262-266](../colearn/runtime_v2/executor.py)

```python
available = set((getattr(loop, "model_presets", {}) or {}).keys())
resolved = preset
if available and preset not in available:
    request.metadata.setdefault("_runtime_warnings", []).append(f"model_preset_missing:{preset}")
    resolved = "default" if "default" in available else ""
```

**失败模式**：用户的 nanobot 配置里没这俩预设 → 静默降级到 default 或""，行为变化但用户没察觉

**插件化后归属**：
- 在插件配置里显式声明：`learning_modes.explore.model = ...` / `learning_modes.deep.model = ...`
- 不再依赖 nanobot 的预设系统，插件直接控制模型选择

---

## 9. `Nanobot.from_config()` + workspace/config_path 假设

**耦合形式**：[executor.py:289-318](../colearn/runtime_v2/executor.py) 假设 `Nanobot.from_config(config_path=..., workspace=...)` 这个签名，且实例化后会自然有 `tools` 注册表。

**失败模式**：构造签名变 → TypeError，整个 `_get_bot()` lazy init 失败

**插件化后归属**：
- 仍需调用 `Nanobot.from_config()` —— 这是 nanobot 给的官方入口，避不开
- 但不再在 CoLearn 自己的代码里 new bot；改成"插件由 nanobot 加载，nanobot 自己 new 自己"
- CoLearn 主流程不持有 bot 实例，只通过插件入口与之交互

---

## 10. 结果归一化桥 `result_bridge.py`

**耦合形式**：[colearn/runtime_v2/result_bridge.py](../colearn/runtime_v2/result_bridge.py) 把 nanobot 原始结果 + CoLearn 内部 `closure_payload` 合并成 `LearningTurnResult`。这个桥既知道 nanobot 字段又知道 CoLearn 字段，是双向耦合。

**失败模式**：nanobot 结果结构变 → 桥要改；CoLearn 学习结果结构变 → 桥也要改

**插件化后归属**：
- 拆成两半：
  - `RunResultAdapter`（见 #5）—— 只懂 nanobot 端
  - `LearningTurnResultBuilder` —— 只懂 CoLearn 端
- 拼接发生在 `LearningHook.after_iteration` 的最末尾，不再有"双向桥"概念

---

## 重构后的依赖方向

**现状**（双向耦合）：

```
CoLearn (NanobotTurnExecutor / tooling / prompting / result_bridge)
   │
   │  伸进 _loop, sessions, tools, model_presets, GOAL_STATE_KEY,
   │  ContextAware, ContextBuilder, RunResult.* ...
   ▼
nanobot
```

**目标**（单向，CoLearn 是 nanobot 的插件）：

```
nanobot  (entry_point: nanobot.plugins / nanobot.tools)
   │
   │  按官方协议加载 colearn-plugin
   ▼
colearn-plugin
   │
   │  通过 ContextVar 读 session_id / LearningTurnRequest
   │  通过 AgentHook 监听生命周期
   │  通过 Tool 注册学习工具
   │
   ▼
LearningStateManager (独立 JSON 存储，与 nanobot session 解耦)
```

CoLearn 主仓不再 `import nanobot.*` —— 所有 nanobot 接触点都搬到插件包里。这样 nanobot 升级影响的爆炸半径就只剩插件包，CoLearn 业务逻辑（learning/, sessions/, projects/, memory/, knowledge/）完全不受影响。

---

## 接下来

设计 workflow `w17lxj3ns` 还在跑。它会给出：
1. ContextVar POC 的形式化分析（已手动验证，互为印证）
2. 完整的目录结构 / 接口签名 / hook 映射
3. LightRAG 插件设计（Tool vs MCP 选型 + 代码）
4. 学习状态插件设计（must_have / should_have / nice_to_have 分级）
5. 5 阶段实施计划

workflow 出完，结合本文档的 10 处具体证据，就能把每条耦合落到一个具体的迁移任务上。
