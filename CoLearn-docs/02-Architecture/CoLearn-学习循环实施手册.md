# CoLearn 学习循环实施手册

## 文档目的

这份手册面向工程实现，记录当前学习循环已经落地的形态、回归方式，以及仍保留的实现边界。它是当前代码的施工说明，不是目标蓝图。

## 当前最小闭环

当前后端具备以下学习循环能力：

- FastAPI HTTP 接口创建项目、会话、知识库资源
- `/api/v1/ws` 发起实时学习回合
- `LearningOrchestrator` 组装单轮学习请求
- 双模式（Chat / Learning）+ 五段 `LearningPhase`（INTAKE/DIAGNOSE/READY/REFLECT/RECALL）+ 三态 `TurnMode`（LEARN/CHECK/PAUSED）
- `BoardFacts -> TurnPolicy -> LearningEvent` 三层状态链
- `NanobotTurnExecutor` 作为执行器，挂 nanobot 原生 `AgentHook` 真流式
- `memory` / `lightrag` / `web_search` 以工具方式按需接入
- runtime compression 与 product compression 都已接上
- session / project / memory 落到 JSON state store

## 主链阶段（stages）

主链已从单个 orchestrator 方法拆成 `colearn/app/stages/*` 的阶段类，`LearningOrchestrator._run_turn_pipeline()` 的执行顺序：

1. `PreflightStage` — 解析/创建 session 与 project，判定 session mode 与 learning phase，跑 source readiness，构建初始 Board / Snapshot
2. `PlanStage` — 仅在需要时生成/重排 `LearningPlan`（首次进入、换题、计划缺失），并按 mastery 跳过已掌握节点
3. 长期目标同步 — learning 模式调用 `executor.sync_sustained_goal()`（nanobot 原生 goal）；chat 模式则收口已有 goal
4. `RetrievalStage` — learning 模式按需取证（LightRAG + 轻量并行检索）；chat 模式直接 skip
5. `sync_project_retrieval_profile` — 把 source readiness + prefetch 状态写回 `project.retrieval_profile`
6. `ExecuteStage` — 组 prompt、设 model preset、挂工具、跑 executor，拿到 `LearningTurnResult`
7. `FinalizeStage` — 组装 `last_turn_result` 等产物
8. 长期目标收尾 — 计划全部完成或回到 `PAUSED` 时自动 `complete_goal`
9. `WritebackStage` — 统一写回 session / project / memory，调度后台 product compression、dream consolidation、board derivation

## 单轮流程

### 1. 请求进入

WebSocket `start_turn` / `message` 进入 `/api/v1/ws`（`colearn/api/ws_handler.py`，内部委托 `colearn/api/ws/*`）后，会准备 session、标记 `status=running`、写入 `active_turn_id`，并先发 `session` 与 `stage_start` 事件。

### 2. orchestrator 组装

按上面的 stages 顺序执行。Chat Mode 走轻链路：不跑 PlanStage 学习逻辑、不取证、不调度学习型后台后处理。

### 3. executor 执行

`NanobotTurnExecutor`：

- 用 nanobot `ContextBuilder.build_system_prompt()` 生成基础 system prompt，再叠加 CoLearn 学习上下文（`runtime_v2/prompting.py`）
- 从 `metadata["source_profile"]` 注入 source readiness 提示
- 按 `enabled_tools` 挂载 `memory` / `lightrag` / `web_search`（`runtime_v2/tooling.py`）
- 若 `request.model_preset` 存在，先 `set_model_preset` 再跑
- 挂 `AgentHook` 把 runtime 的 delta / tool call / reasoning 实时写入 stream channel
- 把返回值规范化成 `LearningTurnResult`

### 4. 结果写回

主链写回会更新：`session.board_facts / board_version / messages / last_turn_result / continuation_prompt / status / learning_phase`，以及 `project.board_facts / board_version / retrieval_profile / current_main_goal`，并写 `EventMemoryStore`。

### 5. 后台后处理

后台 product compression、dream consolidation、board derivation 结束后只补写 review / continuation / product compression 状态，不覆盖主链已写入的 messages / board / status。Chat Mode 不调度这些学习型后处理。

## 已落地的对齐项

- 状态持久化：`created_at/updated_at` 为正式字段，`SessionStore`/`LearningProjectService`/`EventMemoryStore` 统一走 `colearn.storage.records`
- JSON 写入保护：`JsonStateStore` 按路径共享锁 + 临时文件原子替换
- 后台压缩竞态缓解：后台线程只产出 `ProductCompressionResult`，orchestrator 单一入口合并
- source readiness 进入请求与 prompt
- LightRAG async / sync 双入口，旧 `_run_async()` 绕行已移除
- API 状态拆分到 `colearn.api.state` 的可重置 service
- nanobot 原生能力接入：`AgentHook` 流式、`set_model_preset`、`ContextBuilder`、`AutoCompact`、`Dream`、`long_task / complete_goal / goal_state`

## 当前仍保留的实现边界

- API schema 只做到重点收口，并非全部 payload 强类型化
- `board_version` 是 stale write 保护，不是严格 compare-and-swap
- `BoardFacts` 运行时 dataclass、持久化 dict，类型边界未统一
- `retrieval_bundle` 仍保留在 request contract
- `parallel_support` 仍是轻量并行检索，未替换为 `SubagentManager`
- `KnowledgeWorkspaceService` 仍是轻量服务，不是独立知识库主存储

## 回归方式

后端主回归入口：

```bash
python -m pytest tests
```

前端回归入口（`webui/`，Vitest）：

```bash
cd webui
pnpm test
```

## 维护建议

维护学习循环时遵守两个顺序：先更新本目录协议与装配文档，再修改 orchestrator / stages / executor / API / 状态层代码。这样前后端和文档更容易保持同一个事实面。
