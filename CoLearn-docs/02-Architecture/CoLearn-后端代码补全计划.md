# CoLearn 后端收口记录

## 文档定位

这份文档不再承担“待实施计划”的角色，而是记录当前后端已经收口的部分、仍保留的边界，以及后续继续施工时应遵守的判断基线。

它对应的是当前代码事实，不是历史计划。

## 当前后端主线

截至当前代码，后端主线已经稳定在下面这条路径上：

- FastAPI 提供 HTTP 与 WebSocket 入口
- `LearningOrchestrator` 负责单轮组装
- `BoardFacts -> TurnPolicy -> LearningEvent` 作为学习状态协议
- `NanobotTurnExecutor` 负责回合执行
- `memory` 与 `lightrag` 通过工具方式接入
- `RuntimeCompressionBridge` 与 `ProductCompressionBridge` 分别承担运行时压缩与结果压缩
- session / project / memory 通过 JSON state store 持久化

## 已完成的收口项

### 1. Session / Project / Memory 存储统一

已经完成：

- `LearningSession.created_at`、`updated_at` 成为正式字段
- `touch_session()` 直接更新 dataclass 字段
- `colearn.storage.records` 作为统一 record codec
- `SessionStore`、`LearningProjectService`、`EventMemoryStore` 统一走同一套编解码路径

这意味着 session / project / memory 不再各自维护散落的手写序列化逻辑。

### 2. JSON 写入保护

已经完成：

- `JsonStateStore` 对同一路径使用共享锁
- 写入采用临时文件 + 原子替换

这降低了并发写入或异常中断时损坏 JSON 文件的风险。

### 3. Background product compression 写回收口

已经完成：

- 后台线程不再直接整对象写回 session / project store
- 线程只负责产出 `ProductCompressionResult`
- orchestrator 通过单一入口合并后台结果

当前后台只 patch review / continuation / product compression 状态，不再覆盖主链上的 messages / board / status。

### 4. Source readiness 真正进入下游

已经完成：

- `sync_source_refs()` 与 `build_project_source_profile()` 已封装到 `SourceReadinessPreflight`
- preflight 结果会写入 `project.retrieval_profile`
- 同时会写入 `LearningTurnRequest.metadata["source_profile"]`
- executor prompt 会读取这份 source readiness 提示

当前 preflight 不是死字段，而是已有下游消费者。

### 5. LightRAG async / sync 边界重写

已经完成：

- LightRAG client 提供 async sync / retrieve 入口
- 旧 `_run_async()` 线程绕行逻辑已移除
- 同步入口在事件循环中会明确失败
- executor 的 LightRAG tool 走 async retrieval 路径

### 6. API 层状态拆分

已经完成：

- settings、memory docs、skills 这类 API-only 状态迁移到 `colearn.api.state`
- service 可 reset，便于测试隔离
- 本轮新增了：
  - `AuthStateService`
  - `KnowledgeTaskService`
  - `SettingsTestRunService`

### 7. 联调补齐接口

已经完成一版本地联调用补齐：

- `GET /api/v1/auth/status`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/register`
- `GET /api/v1/auth/is_first_user`
- `POST /api/v1/auth/logout`
- `GET /api/v1/knowledge/tasks/{task_id}/stream`
- `WS /api/v1/knowledge/{name}/progress/ws`
- `GET /api/v1/knowledge/{name}/files/{file_path}`
- `GET /api/v1/settings/tests/{service}/{run_id}/events`

这一轮的目标是前后端联调对齐，不是生产级认证或完整任务平台。

### 8. WebSocket 生命周期测试

已经完成：

- 真实 `/api/v1/ws` 已有 ASGI 级测试
- 覆盖 ping、missing subscribe、cancel 清理、start_turn 成功、异常清理

### 9. 本轮回归状态

当前已确认：

- `pytest tests/test_api_app.py` 通过
- `npm run test:node` 通过

## 当前代码事实下的边界

### 1. 认证是本地轻量实现

当前认证的事实是：

- 使用本地状态存储保存用户与 session
- 依赖 cookie 维持登录态
- 目标是支撑本地联调

它还不是生产级认证体系，不应在文档中表述为正式安全方案。

### 2. 知识库任务系统是联调型实现

当前知识库 task / progress 的事实是：

- 已有稳定 task id
- 已有 SSE task stream
- 已有 progress WebSocket
- 已支持文件保存、列文件、取文件、reindex

但它仍然属于轻量任务实现，不应宣称已经具备完整后台任务基础设施。

### 3. API schema 不是“全部补齐”

当前状态应表述为“重点接口已收口”，不是“全部协议已收口”。

已经有明确 schema 的重点入口包括：

- settings ui / catalog / test start
- auth login / register
- session create / update
- project create / update / sources / anchor
- memory update / clear
- WebSocket `start_turn`

仍有一部分接口和消息层继续处于收口过程中，尤其是部分工具型接口与 WebSocket 消息分发层。

### 4. Board version 不是严格 compare-and-swap

当前 `board_version` 的语义应理解为：

- 有 stale write 保护
- 冲突时跳过写回并记录 warning

它还不是严格 compare-and-swap，也不是完整的基于当前版本递增写入协议。

### 5. Retrieval 仍是 tool-mode

当前实现继续明确采用 tool-mode retrieval：

- preflight 负责 source readiness
- 真正知识文本由 `lightrag` tool 按需拉取

系统没有恢复为“每轮固定前置 retrieval”。

### 6. `retrieval_bundle` 仍保留在 request contract

`LearningTurnRequest` 仍携带 `retrieval_bundle` 字段。

当前主链没有把它完全移出 contract，这属于已知但暂未继续扩修的边界。

### 7. Knowledge workspace 仍是轻量服务

当前 knowledge workspace 的事实是：

- 支持 source library 的轻量管理
- 支撑 source readiness 计算
- API 层已支持文件与任务链路
- workspace service 本身没有独立持久化模型

因此文档不应宣称 knowledge workspace 已完全演进为独立知识库主存储。

## 当前回归入口

后端主回归入口仍然是：

```bash
python -m pytest tests
```

如果继续增加后端测试用例，应在回归完成后同步刷新本文档中的基线描述。

## 下一步建议

如果继续按低风险顺序推进，建议优先关注：

1. 真实页面联调闭环
2. 知识库 task 状态更接近真实异步过程
3. Settings diagnostics 事件流体验收口
4. 认证页面与 401 跳转闭环
5. WebSocket 消息分发层继续强类型化

## 使用方式

把这份文档当成当前后端事实记录来维护：

- 代码先变化时，及时更新“已完成 / 当前边界”
- 计划先变化时，先确认是否已经落地，再决定是否写入“已完成”

这样可以避免文档提前宣布完成，最后和代码脱节。
