# CoLearn 后端收口记录

## 文档定位

这份文档不再保留旧阶段计划的验收叙述，而是记录当前后端已经收口的部分、仍存在的缺口，以及接下来继续施工时的判断基线。

## 当前后端主线

截至当前代码，后端主线已经稳定在下面这条路径上：

- FastAPI 提供 HTTP 与 WebSocket 入口
- `LearningOrchestrator` 负责单轮装配
- `BoardFacts -> TurnPolicy -> LearningEvent` 作为学习状态协议
- `NanobotTurnExecutor` 负责回合执行
- `memory` 与 `lightrag` 通过工具接入
- `RuntimeCompressionBridge` 与 `ProductCompressionBridge` 分别承担运行时压缩与结果压缩
- session / project / memory 通过 JSON state store 持久化

## 已完成的收口项

### 1. LearningSession 时间字段持久化

已经完成：

- `LearningSession` 正式声明 `created_at`、`updated_at`
- `touch_session()` 直接更新 dataclass 字段
- session 保存与重载后不再丢失这两个字段

### 2. store codec 统一

已经完成：

- 新增 `colearn.storage.records`
- `SessionStore`
- `LearningProjectService`
- `EventMemoryStore`

三者都通过统一的 record codec 做 dataclass 与 JSON record 的转换，不再各自维护散落的手写序列化。

### 3. JSON 写入保护

已经完成：

- `JsonStateStore` 对同一路径使用共享锁
- 写入采用原子替换

这降低了并发写入或异常中断时损坏 JSON 文件的风险。

### 4. Background product compression 写回收口

已经完成：

- 后台线程不再直接重复调用 session / project save
- 线程只产出 `ProductCompressionResult`
- orchestrator 通过单一入口合并后台结果

当前后台只 patch review / continuation / compression 状态，不再覆盖主链 messages / board / status。

### 5. source readiness 真正进入下游

已经完成：

- `sync_source_refs()` 与 `build_project_source_profile()` 已封装到 `SourceReadinessPreflight`
- preflight 结果会写入 `project.retrieval_profile`
- 同时会写入 `LearningTurnRequest.metadata["source_profile"]`
- executor prompt 会读取这份 source readiness 提示

当前 preflight 不是死代码。

### 6. LightRAG async / sync 边界重写

已经完成：

- LightRAG client 提供 async sync / retrieve 方法
- 旧 `_run_async()` 线程绕行逻辑已移除
- 同步入口在事件循环中会明确失败
- executor 的 LightRAG tool 走 async retrieval 路径

### 7. API 层状态拆分

已经完成：

- settings、memory docs、skills 等 API-only 状态已迁移到 `colearn.api.state`
- service 可以 reset，便于测试隔离

### 8. WebSocket 生命周期测试

已经完成：

- 真实 `/api/v1/ws` 已有 ASGI 级测试
- 覆盖 ping、missing subscribe、cancel 清理、start_turn 成功、异常清理

## 当前代码真相下的边界

### API schema 不是“全部补齐”

当前状态应表述为“部分收口”，不是“已全部补齐”。已经有明确 schema 的重点入口包括：

- settings ui / catalog / test start
- auth login / register
- session create / update
- project create / update / sources / anchor
- memory update / clear
- WebSocket `start_turn`

但仍有一部分接口和消息层还在继续收口过程中，因此不应把全量 schema 化写成既成事实。

### board_version 不是严格递增写入

当前 `board_version` 语义应理解为：

- 有 stale write 保护
- 冲突时跳过写回并记录 warning

它还不是严格的 compare-and-swap，也不是“只允许基于当前版本递增写入”的完整协议。

### retrieval 仍是 tool-mode

当前实现继续明确采用 tool-mode retrieval：

- preflight 只负责 source readiness
- 真实知识文本由 `lightrag` tool 按需拉取

系统没有恢复为“每轮固定前置 retrieval”。

### request contract 仍保留 retrieval_bundle

`LearningTurnRequest` 仍然带有 `retrieval_bundle` 字段。当前主链没有把它完全移出 contract，这属于已知但暂未继续扩修的边界。

### KnowledgeWorkspaceService 仍是轻量内存服务

当前 knowledge workspace 的事实是：

- 它支持 source library 的轻量管理
- 它支撑 source readiness 计算
- 它本身没有独立持久化

因此文档不应宣称 knowledge workspace 已经深度进入主链持久化。

## 当前回归入口

后端主回归入口继续是：

```bash
python -m pytest tests
```

当前仓库的已知基线是 `32 passed`。如果继续增加测试用例，应在回归完成后同步刷新本文件和实施手册中的基线描述。

## 下一步建议

如果继续按低风险顺序推进，建议优先关注：

1. 剩余裸 payload 的 schema 化
2. WebSocket 消息分发层的类型收口
3. BoardFacts 持久化边界统一
4. `retrieval_bundle` 从 request contract 中移出
5. knowledge workspace 是否需要落盘

## 使用方式

把这份文档当成当前后端真相记录来维护：

- 代码先变化时，及时更新这里的“已完成 / 当前边界”
- 计划先变化时，先确认是否已经落地，再决定是否写入“已完成”

这样可以避免文档提前宣称完成，最后和代码脱节。
