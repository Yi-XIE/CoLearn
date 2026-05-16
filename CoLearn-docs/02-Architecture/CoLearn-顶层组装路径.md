# CoLearn 顶层组装路径

## 文档目的

这份文档只描述当前后端的顶层组装关系、主链边界和工具定位，不记录阶段性完成度。

它对应的是：

- `colearn/api/app.py`
- `colearn/app/learning_orchestrator.py`
- `colearn/runtime/turn_executor.py`
- 以及相关状态、检索、压缩模块的当前实现

## 一次学习回合的主链

当前单轮学习回合的组装顺序如下：

1. `FastAPI / WebSocket` 接收请求
2. `LearningOrchestrator.run_turn()` 负责回合级组装
3. `SourceReadinessPreflight` 同步 source refs，并生成 source readiness 概览
4. `state_hooks` 从 session / project 重建 `BoardFacts`，再计算 `TurnPolicy` 和 `LearningStateSnapshot`
5. `build_learning_turn_request()` 把运行时上下文压成 `LearningTurnRequest`
6. `RuntimeCompressionBridge` 对请求做运行时压缩
7. `NanobotTurnExecutor` 执行主回合，并在 tool registry 中按需挂载 `memory` 与 `lightrag`
8. `after_turn_payload()` 生成 `board_after`、`learning_events`、`board_patch`、`memory_events`
9. `normalize_learning_turn_result()` 产出统一的 `LearningTurnResult`
10. orchestrator 同步写回 session / project，并异步安排 product compression
11. `apply_background_result()` 在后台结果返回后，仅补充 review / continuation / product compression 状态

## 入口层

### HTTP

当前保留的主要 HTTP 路由包括：

- `/api/v1/sessions`
- `/api/v1/projects`
- `/api/v1/knowledge`
- `/api/v1/memory`
- `/api/v1/settings`
- `/api/v1/auth`

这些接口主要负责资源管理、配置读写、知识库任务流，以及会话与项目的列表详情。

### WebSocket

实时学习回合继续走 `/api/v1/ws`。

当前支持的消息类型有：

- `ping`
- `subscribe_turn`
- `resume_from`
- `cancel_turn`
- `regenerate`
- `message`
- `start_turn`

WebSocket 事件流保持同一路径输出。当前会发送：

- `session`
- `stage_start`
- `content`
- `done`
- `error`

如果 executor 返回真实 `stream_events`，API 层会原样补齐公共元数据后转发，不再合成假的 tool / thinking 事件序列。

## Orchestrator 的职责

`LearningOrchestrator` 是当前后端的主装配层，负责：

- 解析或创建 session / project
- 执行 source readiness preflight
- 构建 Board / Policy / Snapshot
- 构建 `LearningTurnRequest`
- 调用 runtime compression 和 executor
- 把学习结果转换成 session / project / memory 的持久化状态
- 安排后台 product compression

它不直接承担模型推理细节，也不直接承担 LightRAG HTTP 调用；这些能力分别下沉到 executor 和 retrieval adapter。

## Learning State 的位置

当前学习状态是三层结构：

1. `BoardFacts`：跨回合持久事实
2. `TurnPolicy`：每轮即时策略投影
3. `LearningEvent`：回合后对 Board 的增量更新来源

运行时的事实源以 session 为主，project 上的 `board_facts` 是镜像副本，用于项目列表展示和跨 session 恢复。

## Source Readiness 与检索

当前检索链路分成两部分：

### preflight

`SourceReadinessPreflight` 会做两件事：

- 调用 `RetrievalService.sync_source_refs()` 同步 source refs
- 调用 `KnowledgeWorkspaceService.build_project_source_profile()` 生成 readiness 概览

其结果会同时进入：

- `project.retrieval_profile`
- `LearningTurnRequest.metadata["source_profile"]`

### 实际知识检索

真正的文本检索不是在 orchestrator 前置完成，而是在 `NanobotTurnExecutor` 安装的 `lightrag` tool 中按需触发。

也就是说：

- preflight 负责告诉模型“知识源现在准备得怎么样”
- 实际拉取知识文本由模型在回合中决定是否调用 tool

这是当前明确采用的 tool-mode 设计，不是每轮固定前置 retrieval。

## Memory 的位置

Memory 也保持工具模式：

- `memory` tool 优先从 `EventMemoryStore` 搜索事件
- 如果搜索不到，再回退到 request 附带的 `memory_references`

会话结束后，`after_turn_payload()` 会把关键结果落成 `memory_events`，再由 orchestrator 追加到 `EventMemoryStore`。

## 压缩链路

当前压缩分两层：

- `RuntimeCompressionBridge`：回合执行前压缩 prompt / request
- `ProductCompressionBridge`：回合完成后生成 review summary 和 continuation prompt

后台压缩不再再次整对象覆盖 session / project。当前实现改成：

- 后台线程只计算 `ProductCompressionResult`
- 结果统一回到 `apply_background_result()`
- 仅 patch `pending_review`、`continuation_prompt`、`last_turn_result.product_compression`、`project.latest_review`

这可以避免后台线程和主链并发整对象写回。

## 持久化边界

当前仍然使用 JSON state store，而不是数据库。重要边界如下：

- `SessionStore`、`LearningProjectService`、`EventMemoryStore` 都通过 `colearn.storage.records` 做统一编解码
- `JsonStateStore` 对同一路径写入使用共享 `RLock`
- 写入采用原子替换，降低文件损坏风险

这套方案已经解决了之前 session / project / memory 三套序列化风格不一致的问题，但仍然属于轻量文件存储方案，不包含 migration 机制。

## Knowledge 模块的当前位置

当前知识库能力分成两层：

1. API 层的 knowledge task / file 服务
   - 支持创建知识库、上传文件、列文件、查看文件、触发 reindex、查看 task stream
2. `KnowledgeWorkspaceService`
   - 负责 source readiness 计算与轻量 source library 管理

需要注意：

- `KnowledgeWorkspaceService` 仍是内存态服务，没有单独持久化
- 当前最重要职责是支撑 source readiness，而不是承担完整知识库主存储

## 当前明确保留的技术债

以下内容在当前代码中仍然保留，但不是这一轮要继续扩修的范围：

- `LearningTurnRequest.retrieval_bundle` 仍在 contract 中，尚未移出到纯运行时上下文
- `board_version` 当前是 stale write 保护与冲突跳过，不是严格单步递增写入协议
- `BoardFacts` 在运行时是 dataclass，在持久化层仍以 `dict` 形式保存
- knowledge workspace 本身没有独立持久化

## 回归入口

当前后端继续以：

```bash
python -m pytest tests
```

作为主回归入口。

前端与契约侧的配套回归入口：

```bash
cd web
npm run test:node
```

如果接口或状态协议继续演化，应优先更新本目录中的协议与装配文档，再补代码说明。
