# CoLearn 学习循环实施手册

## 文档目的

这份手册面向工程实现，记录当前学习循环已经落地的形态、回归方式，以及还保留的缺口。它不是目标蓝图，而是当前代码的施工说明。

## 当前最小闭环

当前后端已经具备以下学习循环闭环能力：

- FastAPI HTTP 接口可创建项目、会话、知识库资源
- `/api/v1/ws` 可发起实时学习回合
- `LearningOrchestrator` 可组装单轮学习请求
- `BoardFacts -> TurnPolicy -> LearningEvent` 三层状态链已接入
- `NanobotTurnExecutor` 已作为当前执行器
- `memory` 和 `lightrag` 以工具方式接入
- runtime compression 与 product compression 都已接上
- session / project / memory 均可落到 JSON state store

## 当前单轮流程

### 1. 请求进入

WebSocket `start_turn` 或 `message` 进入 `/api/v1/ws` 后，API 层会：

- 准备 session
- 标记 `status=running`
- 写入 `active_turn_id` 和 `active_turns`
- 先发 `session` 与 `stage_start` 事件

### 2. orchestrator 装配

`LearningOrchestrator.run_turn()` 当前执行顺序：

1. 获取或创建 session / project
2. 计算 source readiness
3. 构建 Learning Board
4. 生成 Turn Policy 和 Snapshot
5. 构建 `LearningTurnRequest`
6. 执行 runtime compression
7. 调用 executor
8. 生成 `after_turn_payload`
9. 统一写回 session / project / memory
10. 安排后台 product compression

### 3. executor 执行

`NanobotTurnExecutor` 当前行为：

- 根据 request 组 prompt
- 从 `metadata["source_profile"]` 注入 source readiness 提示
- 按 `enabled_tools` 挂载 `memory` / `lightrag`
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

### 5. 后台 review

后台 product compression 结束后，当前只补写：

- `session.pending_review`
- `session.continuation_prompt`
- `session.last_turn_result.product_compression`
- `project.latest_review`

## 已完成的对齐项

### 状态持久化

以下问题已经收口：

- `LearningSession.created_at / updated_at` 已是正式字段
- `touch_session()` 直接写 dataclass 字段，不再动态 `setattr`
- `SessionStore`、`LearningProjectService`、`EventMemoryStore` 已统一改用 `colearn.storage.records`

### JSON 写入保护

`JsonStateStore` 当前已经具备：

- 按路径共享锁
- 原子替换写入

这解决了多实例或后台结果写回时最明显的文件覆盖风险。

### 后台压缩竞态缓解

后台线程不再直接重复整对象写 store。当前模式是：

- 线程只负责计算 `ProductCompressionResult`
- orchestrator 统一合并结果

这样避免了后台线程把主链刚写入的 messages / board / status 整体冲掉。

### source readiness 真正进入请求

当前 preflight 结果不只写到 `project.retrieval_profile`，还会进入：

- `LearningTurnRequest.metadata["source_profile"]`
- executor prompt 的 source readiness 提示

这意味着 preflight 已经有下游消费者，不再是纯展示字段。

### LightRAG async 边界

LightRAG 适配层已经改成显式 async / sync 双入口：

- async 路径供事件循环内调用
- sync 路径在已有事件循环中会明确拒绝

旧的 `_run_async()` 线程绕行逻辑已经移除。

### API 层状态拆分

`settings_state`、`memory_docs`、`skills_state` 这类全局可变字典已经拆到 `colearn.api.state` 中的可重置 service。

## 当前仍保留的实现边界

### API schema 只做到部分收口

当前已经 schema 化的重点入口包括：

- settings catalog / ui / test start
- auth login / register
- memory update / clear
- session / project 主要写接口
- WebSocket `start_turn`

但“全部 payload 都已强类型化”这件事还没成立。当前仍有继续收口空间，尤其是部分工具型接口和 WebSocket 消息分发层。

### Board version

当前 `board_version` 的能力是：

- 防止明显 stale write 覆盖较新 Board
- 发生冲突时跳过写入并记录 warning

它还不是严格的 compare-and-swap 或严格递增写入协议。

### BoardFacts 的双重表示

当前 Board 在运行时是 dataclass，在 session / project JSON 中仍是 dict。这个边界是可用的，但还没有收紧成单一类型流。

### retrieval_bundle

`LearningTurnRequest.retrieval_bundle` 仍保留在 request contract 中。当前主链仍以 tool-mode retrieval 为主，没有在回合前把真实检索文本写进去。

### KnowledgeWorkspaceService

`KnowledgeWorkspaceService` 当前主要负责 source readiness 与轻量 source library 管理，仍是内存态服务，不是完整知识库主存储。

## 当前回归方式

后端继续使用下面这条命令作为主回归入口：

```bash
python -m pytest tests
```

当前仓库的已知基线是 `32 passed`。后续如果补充测试导致用例数变化，应同步更新本目录文档中的基线描述。

## 本轮之后优先关注的事项

如果继续推进后端收口，建议优先看这几项：

1. WebSocket 消息分发层继续强类型化
2. `memory refresh` 等剩余裸 payload 入口收口
3. BoardFacts 持久化边界进一步统一
4. `retrieval_bundle` 是否从 request contract 移出
5. knowledge workspace 是否需要持久化

## 使用建议

维护学习循环时，建议遵守两个顺序：

1. 先更新本目录协议和装配文档
2. 再修改 orchestrator、executor、API 或状态层代码

这样前后端和文档更容易保持同一个事实面。
