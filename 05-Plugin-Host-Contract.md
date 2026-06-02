# CoLearn Plugin Host Contract
> 版本：v0.1  
> 基线：NanoBot `v0.2.1` 本地源码  
> 日期：2026-06-01  
> 状态：Phase 0 宿主契约冻结稿

## 0. 文档定位

这份文档定义的是 **CoLearn 挂接 NanoBot 的最小宿主契约**。

它的目标不是宣称 NanoBot 已经拥有一套完整、公开、长期承诺的通用插件 API，而是把当前 `v0.2.1` 本地源码里**已经能确认、可以收口依赖**的接口面整理出来，让 CoLearn 后续只通过 `colearn_*` 薄适配层接入宿主。

这份契约服务于下面这个边界：

```text
Wiki = CoLearn 的知识真相
状态机 + 黑板 = CoLearn 的学习真相
NanoBot = 宿主执行层
colearn_* adapters = 唯一宿主耦合层
```

CoLearn v1 明确不包含 `LightRAG`。

---

## 1. 契约依据

本文件基于 `D:\CoLearn-plugins\nanobot-0.2.1` 本地源码确认，关键证据如下：

| 能力面 | 源码位置 | 结论 |
|---|---|---|
| turn 直接执行入口 | `nanobot/agent/loop.py:1692` | `AgentLoop.process_direct(...)` 是当前最直接、最贴近宿主真实执行链的 turn 入口 |
| hook 生命周期 | `nanobot/agent/hook.py:14`, `:31` | `AgentHookContext` 与 `AgentHook` 已形成最小生命周期接口 |
| tool 注册表 | `nanobot/agent/tools/registry.py:8` | `ToolRegistry` 具备注册、卸载、查询、执行与 schema 暴露能力 |
| tool 插件发现 | `nanobot/agent/tools/loader.py:20`, `:68`, `:86` | `entry_points(group="nanobot.tools")` 已存在，但只能视为增强路径 |
| entry point 测试 | `tests/agent/test_tool_loader_entrypoints.py:42` | `nanobot.tools` 的 entry point 发现有测试覆盖 |
| session 管理 | `nanobot/session/manager.py:373`, `:399`, `:537` | `SessionManager` 提供 `get_or_create(...)` 与 `save(...)`，session 暴露 `messages`、`metadata` |
| SDK facade | `nanobot/nanobot.py:23`, `:37`, `:71` | `Nanobot.from_config(...)` 与 `Nanobot.run(...)` 说明“按次挂 hook”是实际用法 |
| Apps manifest 词汇 | `nanobot/apps/protocol.py:12`, `:24` | 宿主已有 `agent-app.v1` manifest 基础词汇 |
| WebUI 视图壳 | `webui/src/App.tsx:63`, `:899`, `:902`, `:1056` | 当前真实壳体视图是 `chat / settings / apps`，`apps` 是可复用入口 |

---

## 2. 契约目标

### 2.1 目标

1. 让 CoLearn 作为插件挂在 NanoBot 上，随宿主版本演进仍可重新接回
2. 让 CoLearn 的知识真相与学习状态真相保留在 `.colearn/`
3. 把对 NanoBot 的所有依赖压缩在 `colearn_*` 适配层
4. 为后续图谱按钮、弹窗、页面能力预留明确扩展位

### 2.2 非目标

1. 不把 NanoBot 当前内部实现误写成“官方稳定插件 API”
2. 不让 CoLearn 直接依赖 NanoBot 的下划线内部字段
3. 不把 NanoBot session 当作 CoLearn 学习状态的唯一真相
4. 不在 v1 引入 `LightRAG`

---

## 3. 契约原则

### 3.1 真相归属

- 课程知识真相：`.colearn/wiki/`
- 学习状态真相：`.colearn/state/sessions/.../session.json`
- 宿主会话镜像：NanoBot `Session.messages` 与 `Session.metadata`

NanoBot session 可以做镜像、缓存、最近对话重放，但不承载 CoLearn 的唯一学习真相。

### 3.2 模式路由

CoLearn 在宿主上不是“有时存在有时不存在”，而是**始终挂载，按模式控制介入深度**：

- `SessionMode = CHAT | LEARNING`
- `TurnMode = LEARN | CHECK | PAUSED`，仅在 `LEARNING` 内生效

### 3.3 耦合收口

任何 NanoBot 版本变化，原则上只允许修改：

- `colearn_turn_runner`
- `colearn_hooks`
- `colearn_tool_registry`
- `colearn_session`
- `colearn_ui_extensions`

其余 Wiki、黑板、状态机、图谱数据、学习逻辑不跟着宿主改。

---

## 4. CoLearn 可依赖的宿主契约面

## 4.1 Turn Runner 契约

当前最可靠的宿主 turn 执行入口，是 `AgentLoop.process_direct(...)`：

```python
async def process_direct(
    self,
    content: str,
    session_key: str = "cli:direct",
    channel: str = "cli",
    chat_id: str = "direct",
    media: list[str] | None = None,
    on_progress = None,
    on_stream = None,
    on_stream_end = None,
) -> OutboundMessage | None:
    ...
```

CoLearn 不直接在业务逻辑里散落调用宿主 loop，而是统一封装为：

```python
class CoLearnTurnRunner(Protocol):
    async def run_turn(
        self,
        *,
        content: str,
        session_key: str,
        channel: str,
        chat_id: str,
        media: list[str] | None = None,
        on_progress = None,
        on_stream = None,
        on_stream_end = None,
    ) -> Any: ...
```

### 设计结论

- `process_direct(...)` 是 CoLearn `run_turn(...)` 的真实后端映射
- `Nanobot.run(...)` 可以作为程序化 facade 参考，但不是 CoLearn 直接绑定的主契约
- CoLearn 只依赖“能跑一轮 turn”这件事，不依赖 loop 内部排队、锁、WebUI 广播等细节

## 4.2 Hook 生命周期契约

`nanobot/agent/hook.py` 已经形成一套最小 hook 面：

```python
class AgentHook:
    async def before_iteration(self, context): ...
    async def on_stream(self, context, delta: str): ...
    async def on_stream_end(self, context, *, resuming: bool): ...
    async def before_execute_tools(self, context): ...
    async def after_iteration(self, context): ...
    def finalize_content(self, context, content: str | None) -> str | None: ...
```

`AgentHookContext` 当前暴露的核心字段包括：

- `iteration`
- `messages`
- `response`
- `usage`
- `tool_calls`
- `tool_results`
- `tool_events`
- `final_content`
- `stop_reason`
- `error`

### 设计结论

- CoLearn 的前置注入、静默监控、学习事件抽取、黑板写回，都通过 `AgentHook` 完成
- `before_iteration` 负责 session 绑定、模式判断、上下文注入
- `on_stream` / `on_stream_end` 负责流式旁路观察
- `before_execute_tools` 负责工具调用前的学习上下文控制
- `after_iteration` 负责学习事件抽取与黑板写回
- `finalize_content` 只用于轻量尾部整理，不承载学习真相计算

## 4.3 Tool Registry 契约

`ToolRegistry` 目前具备以下公共能力：

- `register(tool)`
- `unregister(name)`
- `get(name)`
- `get_definitions()`
- `prepare_call(name, params)`
- `execute(name, params)`

CoLearn 对 tool 层的依赖收口为：

```python
class CoLearnToolRegistry(Protocol):
    def register(self, tool) -> None: ...
    def unregister(self, name: str) -> None: ...
    def get(self, name: str): ...
    def get_definitions(self) -> list[dict]: ...
```

### 设计结论

- CoLearn v1 的 `/colearn`、`/learn` 等入口，以**显式注册**为主
- `nanobot.tools` entry point 发现已经存在，但只视为增强能力
- 不能把外部自动发现当作首版唯一接入方式

## 4.4 Session 契约

`SessionManager` 当前提供：

- `get_or_create(key: str) -> Session`
- `save(session, fsync: bool = False) -> None`

`Session` 当前至少稳定暴露：

- `key`
- `messages`
- `metadata`

CoLearn 只把 NanoBot session 当作宿主镜像层，适配接口定义为：

```python
class CoLearnSessionStore(Protocol):
    def get_or_create(self, key: str): ...
    def save(self, session, *, fsync: bool = False) -> None: ...
```

### 设计结论

- 宿主 session 负责最近对话历史与宿主视角的 metadata
- `.colearn/state/.../session.json` 负责 `blackboard.learning` 与 `blackboard.runtime`
- 两边允许互相投影，但 CoLearn 不把学习真相只写进宿主 `metadata`

## 4.5 Apps / UI Manifest 基础契约

NanoBot 当前已有：

- `APP_PROTOCOL_SCHEMA = "agent-app.v1"`
- `app_manifest(...)`

同时 WebUI 当前真实壳体视图为：

- `chat`
- `settings`
- `apps`

### 设计结论

- `agent-app.v1` 是 CoLearn UI 接入的**基础词汇**
- `apps` 是 NanoBot `v0.2.1` 当前最稳妥的宿主 UI 入口
- 但当前源码**没有确认存在通用“页面级插件注入 API”**

因此，CoLearn 在 UI 层的策略是：

1. 先挂接 `apps` 入口
2. 再由宿主补固定扩展槽位
3. 插件只声明数据与视图意图，不直接注入任意前端 bundle

---

## 5. CoLearn 薄适配层定义

建议把所有宿主耦合点固定在以下文件：

```text
colearn/
  colearn_adapters/
    colearn_host_contract.py
    colearn_turn_runner.py
    colearn_tool_registry.py
    colearn_session.py
    colearn_ui_extensions.py
  colearn_hooks/
    colearn_session_binder.py
    colearn_blackboard_monitors.py
    colearn_preflight.py
    colearn_finalize.py
  colearn_tools/
    colearn_command.py
  colearn_context.py
```

对应职责如下：

| 适配层 | 职责 |
|---|---|
| `colearn_turn_runner` | 把 CoLearn 的 turn 执行请求映射到 `process_direct(...)` |
| `colearn_tool_registry` | 显式注册、卸载、查询 CoLearn tools |
| `colearn_session` | 读写 NanoBot session 镜像层 |
| `colearn_ui_extensions` | 基于 `agent-app.v1` 与宿主固定槽位生成 UI 声明 |
| `colearn_context` | 把当前 turn 绑定到当前 session 与黑板引用 |
| `colearn_blackboard_monitors` | turn 开始/结束时静默更新 `blackboard.runtime` |

---

## 6. CHAT 与 LEARNING 的宿主参与方式

## 6.1 统一原则

宿主每次都跑 NanoBot turn loop，CoLearn 决定自己是浅介入还是深介入。

## 6.2 CHAT 模式

当 `SessionMode = CHAT` 时：

- 不加载 `blackboard.learning`
- 不运行学习状态机主链
- 不注入 Wiki 学习上下文
- 只保留轻量 `blackboard.runtime` 监听
- `/colearn` 仍然可用

适配层只需要：

1. 绑定当前 session
2. 静默更新运行态黑板
3. 允许用户显式切入学习模式

## 6.3 LEARNING 模式

当 `SessionMode = LEARNING` 时：

- 加载 `.colearn/state/sessions/.../session.json`
- 读取 `blackboard.learning`
- 查询 Wiki 当前节点、先修关系、误区与练习
- 按 `TurnMode` 注入学习上下文
- turn 结束后写回学习事件、进度、blocker 与 continuation

## 6.4 模式切换原则

首版建议按下面的优先级判断进入学习模式：

1. 显式 UI 入口：从 `apps` 打开 CoLearn
2. 显式命令：`/learn`、`/colearn`
3. 显式意图：学习计划、系统带学、测一测、继续上次课程
4. session 粘性：已进入 `LEARNING` 的 session 默认保持

普通闲聊默认留在 `CHAT`，不自动强切。

---

## 7. UI 扩展契约

## 7.1 当前已确认的宿主能力

在 `NanoBot v0.2.1` 里，前端已经具备页面壳切换能力，但当前能确认的只有：

- `chat`
- `settings`
- `apps`

因此可以确认：

- 宿主前端**可以承载新增视图**
- 但当前还**没有公开稳定的通用插件页面注入协议**

## 7.2 CoLearn 的 UI 接入策略

CoLearn 不直接把任意 React bundle 塞进 NanoBot。

更稳的方式是宿主补一层**固定槽位 + 固定容器**：

- `apps`
- `thread_toolbar`
- `modal`
- `page`

其中：

- `apps`：当前最安全的首版入口
- `thread_toolbar`：后续放“知识图谱”按钮
- `modal`：后续放轻量图谱弹窗
- `page`：后续放完整图谱页

## 7.3 Manifest 扩展原则

CoLearn 的 UI 声明应当**建立在** `agent-app.v1` 基础上，而不是另起炉灶。

建议的扩展方式是：

1. 继续保留 `schema = "agent-app.v1"`
2. 在 `capabilities` 或宿主扩展字段里声明固定槽位
3. 数据通过宿主 API 或插件数据接口返回
4. 渲染由宿主内建容器负责

示意结构如下：

```json
{
  "schema": "agent-app.v1",
  "id": "colearn",
  "display_name": "CoLearn",
  "description": "K12 AI and STEAM learning workspace",
  "category": "education",
  "source": "local",
  "capabilities": [
    {
      "type": "entry",
      "slot": "apps"
    },
    {
      "type": "view",
      "slot": "modal",
      "container": "graph"
    }
  ]
}
```

注意：上面 `slot`、`container` 这类字段属于 **CoLearn 与宿主共同约定的扩展字段**，不是当前 NanoBot `v0.2.1` 已公开承诺的通用标准。

## 7.4 图谱展示的数据契约

图谱视图建议返回**纯数据**，不要让插件直接控制前端实现：

```json
{
  "nodes": [
    {
      "id": "ml.model.basic",
      "label": "什么是模型",
      "kind": "concept",
      "state": "active"
    }
  ],
  "edges": [
    {
      "source": "ml.data.basic",
      "target": "ml.model.basic",
      "kind": "prerequisite"
    }
  ],
  "focus_node_id": "ml.model.basic"
}
```

宿主负责把它渲染成：

- 卡片
- 弹窗
- 页面

插件只负责提供当前 session 对应的数据。

---

## 8. 明确不作为稳定契约的部分

以下内容即使今天存在，也**不应**被 CoLearn 当作稳定宿主接口：

- `AgentLoop._extra_hooks`
- `AgentLoop._session_locks`
- `AgentLoop._pending_queues`
- `AgentLoop._webui_turns`
- 任何 `_` 开头的内部缓存或内部状态
- loop 内部未公开的方法链
- WebUI 当前具体组件树与 DOM 结构

这里有一个边界要写死：

- `Nanobot.run(..., hooks=[...])` 说明“按次挂 hook”是现实用法
- 但 CoLearn 不直接依赖它背后如何操作 `_extra_hooks`

也就是说，**可以承认它存在，但不能把内部字段当契约**。

---

## 9. 兼容性策略

这份契约写死在当前本地源码基线：

- NanoBot 版本：`v0.2.1`
- 源码位置：`third_party/nanobot-0.2.1/`

后续 NanoBot 升级时，兼容性检查只看五类面：

1. `process_direct(...)` 是否仍可映射为 `colearn_turn_runner`
2. `AgentHook` 生命周期是否仍可挂接
3. `ToolRegistry` 是否仍能显式注册工具
4. `SessionManager` 是否仍可读写 session 镜像
5. `agent-app.v1` 与 `apps` 入口是否仍存在

只要这五类面仍在，CoLearn 其余主体逻辑就不应大改。

---

## 10. 落地结论

对 CoLearn 来说，当前最干净的宿主接入结论是：

1. **后端接入**：以 `process_direct + AgentHook + ToolRegistry + SessionManager` 为最小宿主面
2. **前端接入**：以 `agent-app.v1 + apps` 为首版入口
3. **产品分流**：用 `SessionMode = CHAT | LEARNING` 决定插件介入深度
4. **状态真相**：继续保留在 `.colearn/`
5. **升级策略**：让 `colearn_*` 适配层吸收 NanoBot 漂移

所以，CoLearn 不是“把自己塞进 NanoBot 里面”，而是：

**把 NanoBot 当宿主，把 CoLearn 的学习内核、黑板、Wiki、图谱都留在自己这边，只接一层稳定得多的薄契约。**
