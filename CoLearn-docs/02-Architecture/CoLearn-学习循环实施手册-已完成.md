# CoLearn 学习循环实施手册

## 文档目的

这份手册面向工程实现，记录当前学习循环已经落地的形态、回归方式，以及仍保留的实现边界。

它不是目标蓝图，而是当前代码的施工说明。

## 当前最小闭环

当前后端已经具备以下学习循环闭环能力：

- FastAPI HTTP 接口可创建项目、会话、知识库资源、设置、记忆和技能数据
- `/api/v1/ws` 可发起实时学习回合
- `LearningOrchestrator` 可组装单轮学习请求
- `BoardFacts -> TurnPolicy -> LearningEvent` 三层状态链已接入
- source readiness preflight 已进入 request metadata 和 prompt
- `retrieval_focus -> prefetch_bundle -> retrieval_evidence_map` 已进入主链
- `NanobotTurnExecutor` 作为当前执行器
- `memory` 和 `lightrag` 以工具方式接入
- runtime compression 与 product compression 都已接上
- session / project / memory / settings / auth 通过 JSON state store 或状态 service 管理

## 当前单轮流程

### 1. 请求进入

WebSocket `start_turn` 或 `message` 进入 `/api/v1/ws` 后，API 层会：

- 准备 session
- 标记 `status=running`
- 写入 `active_turn_id` 和 `active_turns`
- 先发 `session` 与 `stage_start` 事件

`ping`、`subscribe_turn`、`resume_from`、`cancel_turn`、`regenerate` 也有对应处理逻辑。

### 2. orchestrator 组装

`LearningOrchestrator.run_turn()` 当前执行顺序：

1. 获取或创建 session / project
2. 计算 source readiness
3. 构建 Learning Board 和 State Snapshot
4. 根据 Board 生成 `retrieval_focus` 和 `retrieval_reason`
5. 调用 `RetrievalService.build_bundle()` 做回合前预取
6. 把 `retrieval_bundle`、`prefetched_references`、`retrieval_focus` 写入 request
7. 生成 Turn Policy
8. 构建 `LearningTurnRequest`
9. 执行 `before_turn()`，补齐 turn envelope metadata
10. 执行 runtime compression
11. 调用 executor
12. 生成 learning closure
13. 规范化 `LearningTurnResult`
14. 构建 retrieval writeback：`retrieval_hits`、`retrieval_misses`、`retrieval_evidence_map`
15. 统一写回 session / project / memory
16. 安排后台 product compression

### 3. executor 执行

`NanobotTurnExecutor` 当前行为：

- 根据 request 组 prompt
- 从 `metadata["source_profile"]` 注入 source readiness 提示
- 从 `metadata["retrieval_focus"]`、`metadata["prefetched_references"]`、`metadata["retrieval_reason"]` 注入 retrieval 提示
- 按 `enabled_tools` 挂载 `memory` / `lightrag`
- 如果 request 带 `model_preset`，在 nanobot loop 上设置 preset
- 运行 nanobot
- 把返回值规范化成 `LearningTurnResult`

### 4. 结果写回

主链写回当前会更新：

- `session.board_facts`
- `session.board_version`
- `session.messages`
- `session.last_turn_result`
- `session.continuation_prompt`
- `session.status`
- `project.board_facts`
- `project.board_version`
- `project.retrieval_profile`
- `project.current_main_goal`
- `EventMemoryStore`

`session.last_turn_result` 当前会保留：

- `final_text`
- `warnings`
- `board_patch`
- `tool_events`
- `stream_events`
- `raw_learning_result`
- `runtime_v2`
- `knowledge_support_summary`
- `blocker_support_refs`
- `continuation_retrieval_hint`
- `retrieval_hits`
- `retrieval_misses`
- `retrieval_evidence_map`
- `writeback_envelope`
- `turn_mode_before`
- `turn_mode_after`
- `base_board_version`
- `resolved_board_version`
- `product_compression`

### 5. 后台 review

后台 product compression 结束后，当前只补写：

- `session.pending_review`
- `session.continuation_prompt`
- `session.last_turn_result.product_compression`
- `project.latest_review`

后台线程不直接整对象覆盖 session / project 主链结果。

## 已完成的对齐项

### 1. 状态持久化

以下问题已经收口：

- `LearningSession.created_at / updated_at` 已是正式字段
- `touch_session()` 直接写 dataclass 字段
- `SessionStore`、`LearningProjectService`、`EventMemoryStore` 已统一改用 `colearn.storage.records`

### 2. JSON 写入保护

`JsonStateStore` 当前已经具备：

- 按路径共享锁
- 临时文件写入
- 原子替换

这解决了多实例或后台结果写回时最明显的文件覆盖风险。

### 3. 后台压缩竞态缓解

后台线程不再直接重复整对象写 store。当前模式是：

- 线程只负责计算 `ProductCompressionResult`
- orchestrator 统一合并结果

这样避免了后台线程把主链刚写入的 messages / board / status 整体冲掉。

### 4. source readiness 真正进入请求

当前 preflight 结果不只写到 `project.retrieval_profile`，还会进入：

- `LearningTurnRequest.metadata["source_profile"]`
- executor prompt 的 source readiness 提示

这意味着 preflight 已经有下游消费者，不再是纯展示字段。

### 5. retrieval prefetch 与写回

当前已经落地：

- `build_retrieval_focus()`
- `build_retrieval_reason()`
- `RetrievalService.build_bundle()`
- `LearningTurnRequest.retrieval_bundle`
- `prefetched_references`
- `runtime_v2.retrieval`
- `retrieval_hits`
- `retrieval_misses`
- `retrieval_evidence_map`
- `knowledge_support_summary`
- `blocker_support_refs`
- `continuation_retrieval_hint`

这使 LightRAG 不再只是回合中可调用工具，也开始成为状态驱动的背景知识支持层。

### 6. LightRAG async / sync 边界

LightRAG 适配层已经改成显式 async / sync 双入口：

- async 路径供事件循环内调用
- sync 路径在已有事件循环中会明确拒绝
- runtime_v2 的 `lightrag` tool 走 async retrieval 路径

旧的 `_run_async()` 线程绕行逻辑已经移除。

### 7. API 层状态拆分

`settings_state`、`memory_docs`、`skills_state` 这类全局可变字典已经拆到 `colearn.api.state` 中的可重置 service。

当前 API-only service 包括：

- `SettingsStateService`
- `MemoryDocStateService`
- `SkillStateService`
- `AuthStateService`
- `KnowledgeTaskService`
- `SettingsTestRunService`

### 8. 联调补齐接口

为配合前端联调，当前后端已补齐：

- auth 状态与登录注册
- knowledge task stream / progress ws / file route
- settings diagnostics events
- memory summary / projection / refresh / clear
- project source / anchor / latest review
- session pause / resume / delete

这使当前学习循环不再只停留在聊天主链，而是补到了知识库、记忆与 settings 配套入口。

## 当前仍保留的实现边界

### 1. API schema 只做到重点收口

当前已经 schema 化的重点入口包括：

- settings catalog / ui / test start
- auth login / register
- memory update / refresh / clear
- session / project 主要写接口
- WebSocket `start_turn` / `ping` / `subscribe_turn` / `cancel_turn` / `regenerate`

但“全部 payload 都已强类型化”还不成立。

### 2. Board version

当前 `board_version` 的能力是：

- 防止明显 stale write 覆盖较新 Board
- 发生冲突时跳过写入并记录 warning

它还不是严格 compare-and-swap 或严格单步递增写入协议。

### 3. BoardFacts 的双重表示

当前 Board 在运行时是 dataclass，在 session / project JSON 中仍是 dict。

这个边界是可用的，但还没有收紧成单一类型流。

### 4. retrieval_bundle

`LearningTurnRequest.retrieval_bundle` 现在会承载回合前 `prefetch_bundle`。

当前它还不是经过模式筛选、压缩摘要和引用裁剪后的 `prompt_support_bundle`，也没有替代回合中的 `lightrag` tool。

### 5. KnowledgeWorkspaceService 与 KnowledgeTaskService

`KnowledgeWorkspaceService` 当前主要负责 source readiness 与轻量 source library 管理。

`KnowledgeTaskService` 负责本地联调用任务、文件保存、文件列表、SSE 和 progress WebSocket。它仍是轻量任务实现，不是完整后台任务基础设施。

### 6. retrieval prefetch 的失败边界

当 source refs 存在时，`RetrievalService.build_bundle()` 会尝试 LightRAG 或 fallback source preview。

这条链路已经可用，但 orchestrator 外层还没有独立的 prefetch 降级保护层；后续若要提升稳态体验，应把 prefetch failure 转成可写入 request 的 warning，而不是让整轮学习失败。

## 当前回归方式

后端主回归入口：

```bash
python -m pytest tests
```

前端当前回归入口：

```bash
cd webui
npm run test
npm run build
```

前端开发入口：

```bash
cd webui
npm run dev
```

## 本轮之后优先关注的事项

如果继续推进后端收口，建议优先看这几项：

1. 把 `prefetched_references` 进一步筛成 `prompt_support_bundle`
2. WebSocket 消息分发层继续强类型化
3. `memory refresh` 等剩余工具型入口继续收口
4. BoardFacts 持久化边界进一步统一
5. retrieval tool 返回 evidence 与 prefetch evidence map 合并
6. knowledge task 从联调型实现升级成更接近真实异步过程
7. auth 与 settings 页面联调闭环继续硬化

## 使用建议

维护学习循环时，建议遵守两个顺序：

1. 先更新本目录协议与装配文档
2. 再修改 orchestrator、executor、API 或状态层代码

这样前后端和文档更容易保持同一个事实面。
