# CoLearn 插件化技术设计文档

> 版本：v1.0  
> 日期：2026-06-01  
> 分支：`插件尝试`  
> 状态：设计已完成，等待实施

## 0. 文档导航

- 本文档：架构设计 + 接口规范 + Hook 映射
- [PLUGIN_IMPLEMENTATION_PLAN.md](./PLUGIN_IMPLEMENTATION_PLAN.md)：5 阶段实施计划 + 任务分解
- [PLUGIN_MIGRATION_GUIDE.md](./PLUGIN_MIGRATION_GUIDE.md)：从现有系统迁移
- [POC_CONTEXTVAR_RESULT.md](./POC_CONTEXTVAR_RESULT.md)：ContextVar 方案 POC 验证报告
- [COUPLING_EVIDENCE.md](./COUPLING_EVIDENCE.md)：当前 10 处耦合的具体代码证据
- [PLUGIN_FEASIBILITY_ANALYSIS.md](./PLUGIN_FEASIBILITY_ANALYSIS.md)：早期可行性分析

---

## 1. 目标与原则

### 目标

把 CoLearn 的学习逻辑（5-stage pipeline、学习状态、LightRAG 检索）从 CoLearn 主仓**抽出**，作为 **nanobot 的外部插件包**（独立 PyPI 包 / 独立 git 子模块），通过 nanobot 的官方扩展点（entry_points + AgentHook + Tool）接入。

### 核心原则

1. **单向依赖**：`colearn-plugin` 依赖 `nanobot`；CoLearn 主仓**不再** `import nanobot.*`
2. **零侵入**：不修改 nanobot 源码，所有交互走官方扩展点
3. **核心优先**：先实现 must_have 功能，nice_to_have 后续迭代
4. **直接替换**：不做并行运行/feature flag，新版本起来旧路径就走完整迁移

### 与"内部插件"方案的取舍

workflow 的 implementation_plan 一度提议 `colearn/plugin/` 子包（CoLearn 内部插件框架）。这个方案适合"想统一 CoLearn 内部所有插件接入点"的场景，但**不解决 nanobot 升级影响**——CoLearn 仍然包着 nanobot。

本文档采用 **`colearn_plugin/` 外部独立包**方案，理由：
- 符合用户原始诉求（"nanobot 升级我不受影响"）
- 插件可以独立版本化、独立发布
- nanobot 升级时爆炸半径仅限插件包，CoLearn 业务代码完全不动

---

## 2. 整体架构

### 2.1 依赖方向（重构前 vs 重构后）

**重构前**（双向耦合，见 [COUPLING_EVIDENCE.md](./COUPLING_EVIDENCE.md) 10 条证据）：

```
CoLearn (NanobotTurnExecutor / tooling / prompting / result_bridge)
   │  伸进 _loop, sessions, tools, model_presets, GOAL_STATE_KEY,
   │  ContextAware, ContextBuilder, RunResult.* ...
   ▼
nanobot
```

**重构后**（单向，CoLearn 通过插件接入 nanobot）：

```
nanobot  (entry_point: nanobot.plugins / nanobot.tools)
   │  按官方协议加载
   ▼
colearn-plugin (独立包)
   │  ContextVar 读 session_id / LearningTurnRequest
   │  AgentHook 监听生命周期
   │  Tool 注册学习工具
   ▼
LearningStateManager (独立 JSON 存储)

CoLearn 主仓 → 通过 colearn-plugin.get_state_manager() 读写状态
（不再持有 bot 实例，不再 import nanobot.*）
```

### 2.2 包结构

```
colearn-plugin/                          # 独立包（独立 git repo 或 monorepo 子目录）
├── pyproject.toml                       # 关键：[project.entry-points."nanobot.plugins"]
│                                        #         colearn = "colearn_plugin.plugin:CoLearnPlugin"
├── README.md                            # 详细使用文档
├── src/
│   └── colearn_plugin/
│       ├── __init__.py                  # 导出 CoLearnPlugin, get_session_id, get_state_manager
│       ├── plugin.py                    # ★ CoLearnPlugin 主类，唯一对接 nanobot 的入口
│       ├── context.py                   # ★ ContextVar 定义 + get/set helpers
│       │
│       ├── hooks/                       # nanobot AgentHook 子类
│       │   ├── __init__.py              # build_hooks() factory
│       │   ├── session_binder.py        # SessionBinder：第一个 hook，往 ContextVar 写 session_id
│       │   ├── preflight.py             # PreflightHook：load session/project/board
│       │   ├── plan.py                  # PlanHook：注入学习计划到 system message
│       │   ├── retrieval.py             # RetrievalHook：LightRAG 检索 + 注入
│       │   ├── stream_bridge.py         # StreamBridgeHook：nanobot 流式事件 → CoLearn 事件
│       │   ├── finalize.py              # FinalizeHook：归一化结果
│       │   └── writeback.py             # WritebackHook：持久化（fast path 同步 + slow path 后台）
│       │
│       ├── tools/                       # nanobot Tool 子类
│       │   ├── __init__.py              # 通过 entry_points 暴露
│       │   ├── lightrag_query.py        # LightRAG 检索工具（替代 ColearnLightRAGTool）
│       │   ├── memory.py                # 学习事件查询工具
│       │   ├── learning_event.py        # 学习事件记录工具
│       │   └── web_search.py            # web 搜索工具（保持现状）
│       │
│       ├── state/                       # 学习状态管理
│       │   ├── __init__.py
│       │   ├── manager.py               # ★ LearningStateManager：load/save/cache
│       │   ├── models.py                # LearningSession, BoardFacts, LearningProject
│       │   ├── records.py               # JSON 序列化器
│       │   ├── store.py                 # JsonFileStore：原子写、文件锁
│       │   ├── cache.py                 # SessionCache：per-session asyncio.Lock
│       │   └── migrations/              # schema_version 迁移器
│       │       └── v0_to_v1.py
│       │
│       ├── pipeline/                    # 5-stage pipeline 内部逻辑
│       │   ├── __init__.py
│       │   ├── orchestrator.py          # PipelineOrchestrator：协调 5 个 stage
│       │   ├── turn_context.py          # TurnContext：跨 stage 状态载体
│       │   ├── preflight.py             # 从 colearn/app/stages/preflight.py 迁移
│       │   ├── plan.py                  # 从 colearn/app/stages/plan.py 迁移
│       │   ├── retrieval.py             # 从 colearn/app/stages/retrieval.py 迁移
│       │   ├── finalize.py              # 从 colearn/app/stages/finalize.py 迁移
│       │   └── writeback.py             # 从 colearn/app/stages/writeback.py 迁移
│       │
│       ├── adapters/                    # nanobot API 适配层（隔离升级影响）
│       │   ├── __init__.py
│       │   ├── run_result.py            # RunResultAdapter：nanobot RunResult → CoLearn 字段
│       │   ├── hook_context.py          # HookContextAdapter：处理 AgentHookContext 字段变化
│       │   └── tool_registry.py         # ToolRegistryFacade：bot.tools / bot._loop.tools 双路径
│       │
│       └── config/
│           ├── __init__.py
│           ├── defaults.py              # 默认配置
│           └── settings.py              # PluginSettings dataclass
│
└── tests/
    ├── conftest.py
    ├── test_context.py                  # ContextVar 在 gather/TaskGroup/run_in_executor 下的隔离
    ├── test_session_binder.py
    ├── test_state_manager.py            # JSON 原子写、并发缓存
    ├── test_hooks_pipeline.py           # 5-stage hook 顺序、幂等
    ├── test_lightrag_tool.py
    └── fixtures/
        └── sample_state.json
```

### 2.3 与 CoLearn 主仓的关系

CoLearn 主仓变更：
- **删除**：`colearn/runtime_v2/` 整个目录（NanobotTurnExecutor、tooling、prompting、result_bridge）
- **删除**：`colearn/app/stages/` 中的 stage 实现（迁移到插件包）
- **删除**：`colearn/learning/board_hooks.py`、`state_hooks.py`、`turn_hooks.py`、`retrieval_hooks.py`（迁移到插件包）
- **保留**：`colearn/learning/state.py`（dataclass 定义，插件 re-export）
- **保留**：`colearn/sessions/`、`colearn/projects/`、`colearn/memory/`、`colearn/knowledge/`（数据层）
- **保留**：`colearn/api/`（HTTP 层）—— 改为通过 `plugin.get_state_manager()` 读写状态

CoLearn 主仓**不再** `import nanobot.*` —— 所有 nanobot 接触点都在插件包里。

---

## 3. 核心机制：ContextVar 传递 session_id

### 3.1 设计

POC 已验证（[POC_CONTEXTVAR_RESULT.md](./POC_CONTEXTVAR_RESULT.md)）：nanobot 的调用链 `bot.run() → loop.process_direct() → runner.run() → hook.*` 全程 await，且 `asyncio.create_task` 自动拷贝父 Context。所以在 `bot.run()` 之前 `set` 的 ContextVar，hook 内部能 `get` 到，且并发 session 之间天然隔离。

### 3.2 三个核心 ContextVar

```python
# colearn_plugin/context.py
from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .pipeline.turn_context import TurnContext
    from .state.models import LearningTurnRequest

_session_id: ContextVar[str | None] = ContextVar("colearn_session_id", default=None)
_turn_id: ContextVar[str | None] = ContextVar("colearn_turn_id", default=None)
_turn_context: ContextVar["TurnContext | None"] = ContextVar(
    "colearn_turn_context", default=None
)
_request: ContextVar["LearningTurnRequest | None"] = ContextVar(
    "colearn_learning_request", default=None
)


def get_session_id() -> str | None:
    return _session_id.get()


def set_session_id(sid: str) -> None:
    _session_id.set(sid)


def get_turn_context() -> "TurnContext | None":
    return _turn_context.get()


def set_turn_context(tc: "TurnContext") -> None:
    _turn_context.set(tc)


def clear_turn_context() -> None:
    _turn_context.set(None)
    _turn_id.set(None)


class NoSessionBoundError(RuntimeError):
    """SessionBinder 未运行就读 session_id 时抛出（说明插件未正确接入 hook 链）。"""
```

### 3.3 落点：SessionBinder

**关键设计**：用一个 `SessionBinder` hook 作为 `_extra_hooks` 列表的**第一个**。它在 `before_iteration` 第一次触发时把 `session_id` 写入 ContextVar，后续所有 hook 和工具就能"零参数"读到。

```python
# colearn_plugin/hooks/session_binder.py
import logging
import uuid
from nanobot.agent.hook import AgentHook, AgentHookContext

from ..context import (
    set_session_id, set_turn_id, get_session_id,
)

_log = logging.getLogger("colearn_plugin.session_binder")


class SessionBinder(AgentHook):
    """第一个 hook —— 必须放在 _extra_hooks[0] 位置。

    iteration==0 时把 session_id 写入 ContextVar。
    iteration>0 时是 no-op（幂等）。
    """

    name = "colearn.session_binder"

    async def before_iteration(self, ctx: AgentHookContext) -> None:
        if ctx.iteration != 0:
            return
        if get_session_id() is not None:
            return  # 上层 wrapper 已 set，不覆盖

        sid = self._resolve_session_id(ctx)
        if not sid:
            _log.warning("session_id 缺失；后续 colearn hooks 会跳过")
            return

        set_session_id(sid)
        set_turn_id(uuid.uuid4().hex)

    @staticmethod
    def _resolve_session_id(ctx: AgentHookContext) -> str | None:
        """三段降级：spec.session_key → messages metadata → None。"""
        # 1. AgentRunSpec.session_key（首选，nanobot 0.2 起 spec 挂在 ctx 上）
        spec = getattr(ctx, "run_spec", None)
        if spec is not None and getattr(spec, "session_key", None):
            return str(spec.session_key)
        # 2. 从 messages 元数据扒（向前兼容）
        for msg in reversed(getattr(ctx, "messages", []) or []):
            md = (msg or {}).get("metadata") or {}
            sid = md.get("session_id") or md.get("colearn_session_id")
            if sid:
                return str(sid)
        return None
```

### 3.4 兜底方案

如果 nanobot 未来在 hook 调用前 `loop.run_in_executor` 切线程池且不透传 context（当前 nanobot 用的是 `asyncio.to_thread` 自动透传，无此问题），SessionBinder 失效。届时启用兜底：

```python
# colearn_plugin/runtime/dispatch_wrapper.py
from nanobot.agent.loop import AgentLoop
from ..context import set_session_id

class ColearnAgentLoop(AgentLoop):
    """覆盖 _dispatch，在 create_task 后立刻 set ContextVar。"""

    async def _dispatch(self, msg):
        # 在 task 入口设置，不依赖 hook
        if hasattr(msg, "session_key") and msg.session_key:
            set_session_id(str(msg.session_key))
        return await super()._dispatch(msg)
```

通过 `PluginSettings.use_dispatch_wrapper=True` 启用。

---

---

## 4. CoLearnPlugin 主类（与 nanobot 唯一对接点）

### 4.1 职责

- 持有 `LearningStateManager`、`PipelineOrchestrator`、`BackgroundTurnFinalizer`
- 在 `install(bot)` 时把 hook 列表挂到 `bot._loop._extra_hooks`
- 通过 `entry_points` 让 nanobot 自动发现

### 4.2 接口

```python
# colearn_plugin/plugin.py
from pathlib import Path
from typing import Any
from importlib.metadata import entry_points

from .config import PluginSettings
from .state import LearningStateManager
from .pipeline import PipelineOrchestrator
from .hooks import build_hooks


class CoLearnPlugin:
    """CoLearn 学习逻辑作为 nanobot 插件的主入口。

    生命周期：
        构造 → install(bot) → [N 个 turn] → shutdown()

    使用：
        # 自动发现（推荐，pyproject.toml 注册了 entry_point）
        plugins = CoLearnPlugin.discover_and_install(bot)

        # 或手动
        plugin = CoLearnPlugin(state_dir=Path("~/.colearn"))
        plugin.install(bot)
    """

    def __init__(
        self,
        *,
        settings: PluginSettings | None = None,
        state_dir: Path | None = None,
    ) -> None:
        """初始化所有自有服务，不持有 bot 引用。

        参数:
            settings: 插件配置；不传则从环境/默认值加载
            state_dir: 学习状态 JSON 存储根目录；默认 ~/.colearn/state
        """
        self.settings = settings or PluginSettings.load()
        resolved_dir = state_dir or self.settings.state_dir
        self.state_manager = LearningStateManager(state_dir=resolved_dir)
        self.orchestrator = PipelineOrchestrator(
            state_manager=self.state_manager,
            settings=self.settings,
        )
        self._bot_ref: Any = None
        self._installed: bool = False

    def install(self, bot: Any) -> None:
        """挂到运行中的 nanobot 实例。

        将插件 hook 链 prepend 到 bot._loop._extra_hooks。
        SessionBinder 必须在第一位（hook 列表 [0] 位置）。

        幂等：重复调用是 no-op（通过 sentinel 属性追踪）。
        """
        if self._installed:
            return

        hooks = build_hooks(
            orchestrator=self.orchestrator,
            state_manager=self.state_manager,
            bot_ref=bot,
        )

        # 通过 ToolRegistryFacade 隔离 bot.tools / bot._loop.tools 双路径
        # 见 §8.3 Adapter 层
        loop = getattr(bot, "_loop", None)
        if loop is None:
            raise RuntimeError("nanobot 实例未暴露 _loop —— 可能是不兼容的版本")

        existing = list(getattr(loop, "_extra_hooks", []) or [])
        loop._extra_hooks = [*hooks, *existing]
        self._bot_ref = bot
        self._installed = True

    @classmethod
    def discover_and_install(
        cls,
        bot: Any,
        *,
        group: str = "nanobot.plugins",
    ) -> list["CoLearnPlugin"]:
        """通过 entry_points 自动发现并安装所有声明为 nanobot.plugins 的插件。

        nanobot 启动时调用一次即可。
        """
        plugins: list[CoLearnPlugin] = []
        for ep in entry_points(group=group):
            plugin_cls = ep.load()
            plugin = plugin_cls()
            plugin.install(bot)
            plugins.append(plugin)
        return plugins

    def shutdown(self, *, timeout: float = 5.0) -> None:
        """优雅关闭：刷盘、释放资源、从 bot._loop 摘除 hook。"""
        if not self._installed:
            return
        self.state_manager.flush()
        self.orchestrator.shutdown(timeout=timeout)
        if self._bot_ref is not None:
            loop = getattr(self._bot_ref, "_loop", None)
            if loop is not None and hasattr(loop, "_extra_hooks"):
                # 摘除属于本插件的 hook（通过 name 前缀识别）
                loop._extra_hooks = [
                    h for h in (loop._extra_hooks or [])
                    if not getattr(h, "name", "").startswith("colearn.")
                ]
        self._installed = False

    def get_state_manager(self) -> LearningStateManager:
        """供 CoLearn 主仓的 API 层、CLI、测试访问学习状态。"""
        return self.state_manager
```

### 4.3 entry_points 注册

```toml
# colearn-plugin/pyproject.toml
[project]
name = "colearn-plugin"
version = "0.1.0"
dependencies = [
    "nanobot >= 0.2.1",  # 关键：声明 nanobot 版本约束
    "httpx",
    "pydantic >= 2.0",
]

[project.entry-points."nanobot.plugins"]
colearn = "colearn_plugin.plugin:CoLearnPlugin"

[project.entry-points."nanobot.tools"]
lightrag_query = "colearn_plugin.tools.lightrag_query:LightRAGQueryTool"
learning_event = "colearn_plugin.tools.learning_event:LearningEventTool"
colearn_memory = "colearn_plugin.tools.memory:ColearnMemoryTool"
```

---

## 5. Hook 映射（CoLearn 5-Stage → nanobot Lifecycle）

| CoLearn Stage | nanobot Hook | 触发时机 | 关键职责 |
|---|---|---|---|
| **SessionBinder** (合成) | `before_iteration` | iteration==0，**hooks[0]** | 写 session_id / turn_id 到 ContextVar |
| **PreflightStage** | `before_iteration` | iteration==0，紧跟 SessionBinder | load session/project，构建 board，判断 learning intent |
| **PlanStage** | `before_iteration` | iteration==0，紧跟 Preflight | 计算 TurnPolicy，注入 system message，best-effort 应用 model_preset |
| **RetrievalStage** | `before_iteration` + `before_execute_tools` | iteration==0 预取 + 工具调用前命中替换 | LightRAG 检索，注入 retrieval bundle |
| **(LLM 执行)** | nanobot 原生 | — | nanobot agent loop 自然运行 |
| **StreamBridge** | `on_stream` / `emit_reasoning` / `before_execute_tools` | 流式过程中 | nanobot 流式事件 → CoLearn StreamEventType |
| **FinalizeStage** | `after_iteration` | 最后一轮（`stop_reason ∈ {stop, length}`） | 归一化结果，提取 LearningEvents，派生新 BoardFacts |
| **WritebackStage** | `after_iteration` | 紧跟 Finalize | **同步**写 session/project；**异步**调度 background 任务 |

### 5.1 关键 hook 草稿

完整草稿（每个 hook 的 `code_sketch`）参见 `docs/PLUGIN_HOOK_SKETCHES.md`（实施时单独维护）。这里只列三个最关键的契约：

**PreflightHook** — 拉学习状态：
```python
async def before_iteration(self, ctx: AgentHookContext) -> None:
    if ctx.iteration != 0:
        return
    sid = get_session_id()
    if not sid:
        return  # SessionBinder 失败，优雅降级

    async with self._sm.session_lock(sid):
        session = await self._sm.get_or_create_session(sid)
        project = await self._sm.get_or_create_project(session.project_id or sid)
        tc = TurnContext(session_id=sid, project_id=project.project_id, ...)
        tc.session, tc.project = session, project
        await self._stage.prepare(tc)  # source_profile, board, snapshot
        set_turn_context(tc)
        if tc.session_mode == "chat" and not tc.is_learning_intent:
            ctx.metadata["colearn.skip"] = True  # 让 plan/retrieval 短路
```

**RetrievalHook** — 双触发点：
```python
async def before_iteration(self, ctx):  # iteration==0 预取
    tc = get_turn_context()
    if tc is None or ctx.metadata.get("colearn.skip"):
        return
    bundle = await self._stage.fetch(tc, query=tc.user_message)
    tc.retrieval_bundle = bundle
    ctx.messages.insert(1, {
        "role": "system",
        "content": self._stage.render_bundle(bundle),
    })

async def before_execute_tools(self, ctx):  # 工具调用前命中替换
    tc = get_turn_context()
    if tc is None:
        return
    for call in ctx.pending_tool_calls:
        if call.name in {"lightrag_query", "colearn_retrieve"}:
            bundle = await self._stage.fetch(tc, query=call.arguments.get("query", ""))
            ctx.set_tool_result(call.id, self._stage.serialize(bundle))
```

**WritebackHook** — fast/slow 双路径：
```python
async def after_iteration(self, ctx):
    tc = get_turn_context()
    if tc is None or tc.result is None:
        return
    try:
        # Fast path: 同步落盘，下个 turn 立即可见
        async with self._sm.session_lock(tc.session_id):
            tc.session.last_turn_result = tc.result
            await self._sm.save_session(tc.session)
            await self._sm.save_project(tc.project)
        # Memory store
        await self._stage.append_memory(tc)
        # Slow path: 后台调度（不 await）
        self._fin.schedule(tc.session_id, lambda: self._stage.background(tc))
    except Exception:
        _log.exception("writeback failed for session=%s", tc.session_id)
    finally:
        clear_turn_context()  # 必须清除，避免污染下一 turn
```

---

## 6. State Schema（学习状态持久化）

### 6.1 存储布局

```
<state_dir>/                              # 默认 ~/.colearn/state/
├── index.json                            # 全局索引
├── sessions/
│   ├── <session_id>.json                 # 每个 session 一个文件
│   └── ...
└── projects/
    ├── <project_id>.json                 # 每个 project 一个文件
    └── ...
```

每个 JSON 文件顶层有 `schema_version` 字段；`index.json` 维护 `session_id → {project_id, updated_at, schema_version}` 映射。

### 6.2 LearningSession 字段（schema_version=1）

| 字段 | 类型 | 用途 |
|---|---|---|
| session_id | str | 主键 |
| project_id | str | 关联 project |
| title / title_is_custom | str / bool | 标题 |
| created_at / updated_at | int (epoch) | 时间戳 |
| mode | "chat" \| "learning" | 模式 |
| turn_mode | str | TurnMode 枚举 (PLAN/LEARN/CHECK/REFLECT/PAUSED) |
| learning_phase | str | LearningPhase 枚举 |
| board_facts | dict | BoardFacts.to_dict() 内联快照 |
| board_version | int | 单调递增 |
| status | "idle" \| "running" \| "finalizing" | |
| source_refs | list[str] | LightRAG 知识源 |
| memory_refs | list[str] | 长期记忆 |
| messages | list[dict] | 对话历史快照 |
| continuation_prompt | str | 下一轮提示 |
| last_turn_result | dict | FinalizeHook 写入 |
| pending_review | dict | 待 CHECK 的题目 |
| active_turn_id | str \| None | 防并发 |
| next_recall | dict | 间隔重复 (next_recall_at, ease_factor, interval_days) |
| profile | dict | 学习者画像 (mastery_level, cognitive_load, learning_style) |

### 6.3 关键持久化策略

- **原子写**：`tempfile + os.replace`，崩溃下不会留半损坏文件
- **并发控制**：`SessionCache` 持 per-session `asyncio.Lock`；进程级用 `index.json` 上 fcntl/msvcrt 锁
- **加载失败**：JSON parse error → 备份原文件 `<path>.corrupt-<ts>` → 用默认值重建，**不让单个坏文件拖垮 turn**
- **缓存淘汰**：`SessionCache` 超过 `session_max_idle_seconds`（默认 1800s）的条目 evict 时强制 flush
- **schema 迁移**：每条 record 顶层 `schema_version` → `migrations.upgrade(payload, target=CURRENT)`

---

## 7. LightRAG 插件化（hybrid 方案）

### 7.1 选型

不做独立 MCP server（无必要的额外进程跳数）。直接做 nanobot Tool，通过 `nanobot.tools` entry_point 发现。预留 MCP wrapper 模板，未来想跨 host 复用时再启用。

### 7.2 接口

```python
# colearn_plugin/tools/lightrag_query.py

@tool_parameters({
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "..."},
        "mode": {"type": "string", "enum": ["mix", "hybrid", "local", "global", "naive", "bypass"]},
        "top_k": {"type": "integer", "minimum": 1, "maximum": 50},
        "file_paths": {"type": "array", "items": {"type": "string"}},
        "include_chunk_text": {"type": "boolean"},
    },
    "required": ["query"],
})
class LightRAGQueryTool(Tool):
    name = "lightrag_query"
    config_key = "lightrag"
    _plugin_discoverable = True

    @classmethod
    def config_cls(cls): return LightRAGConfig
    @classmethod
    def enabled(cls, ctx): return bool(ctx.config.tools.get("lightrag", {}).get("base_url"))
    @classmethod
    def create(cls, ctx): return cls(config=cls._extract_config(ctx))

    async def execute(self, **kwargs):
        # POST {base_url}/query/data with retry/backoff
        # 返回 {status, query, mode, text, chunks, references, warnings}
        ...
```

完整代码（含 httpx 客户端、retry/backoff、错误处理）已在 workflow 产出中给出，落地时直接用。

### 7.3 配置

```yaml
# nanobot config.yaml
tools:
  lightrag:
    base_url: "http://localhost:9621"
    api_key: ""              # 或 LIGHTRAG_API_KEY env
    timeout_seconds: 30
    default_mode: "mix"
    default_top_k: 5
    max_retries: 2
    retry_backoff_seconds: 0.5
```

---

## 8. Adapter 层（隔离 nanobot 升级影响）

针对 [COUPLING_EVIDENCE.md](./COUPLING_EVIDENCE.md) 列出的耦合点，每个都对应一个 adapter，把 nanobot API 变化的影响压到一个文件里：

### 8.1 RunResultAdapter

封装"从 nanobot RunResult 取 content/messages/tools_used"——nanobot 改字段名只改这一处。

### 8.2 HookContextAdapter

封装"从 AgentHookContext 取 session_key/messages/tool_calls"——目前 ctx 的 `run_spec` 字段是 0.2 才有的，未来变化只改 adapter。

### 8.3 ToolRegistryFacade

封装"从 bot 拿 tool registry"——双路径 `bot.tools` / `bot._loop.tools`，并提供 `register/unregister/has/get` 统一签名。

### 8.4 ModelPresetAdapter

封装"应用模型预设"——目前依赖 `bot._loop.set_model_preset`，未来 nanobot 提供公共 API 时只改这里。

### 8.5 GoalStateAdapter

封装"sustained_goal 写到 nanobot session metadata"——但**插件化后这个方法基本可以删**，learning goal 由 `LearningStateManager` 自管，不再写 nanobot session。仅保留作为兼容期 mirror。

---

## 9. 风险与缓解

| 风险 | 等级 | 缓解 |
|---|---|---|
| nanobot 把 hook 调用切到独立 task | 中 | dispatch_wrapper.py 兜底（覆盖 `_dispatch`） |
| `bot._loop._extra_hooks` 改名/移除 | 中 | 在 install() 中用 try/except 优雅失败，提示用户 nanobot 版本不兼容 |
| `AgentHook` 新增方法 | 低 | 基类有空实现，不调用即可；监控 nanobot CHANGELOG |
| ContextVar 在 `run_in_executor` 丢失 | 低 | 当前 nanobot 用 `asyncio.to_thread`（自动透传）；自己写的 hook 用 `copy_context().run` 包装 |
| Subagent 跨 task 拷贝父 context | 中 | 每个 iteration 重新 set，避免子 agent 继承错误 session_id |
| 多进程部署（multiprocessing/uvicorn worker） | N/A | 任何进程内方案都失效，不在本设计范围 |
| 状态文件并发写损坏 | 低 | 原子写 + per-session asyncio.Lock + index.json 进程锁 |

---

## 10. 接下来

→ [PLUGIN_IMPLEMENTATION_PLAN.md](./PLUGIN_IMPLEMENTATION_PLAN.md) 看 5 阶段实施计划

