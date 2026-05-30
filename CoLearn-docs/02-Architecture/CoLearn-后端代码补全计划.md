# CoLearn 后端收口记录

## 文档定位

这份文档记录当前后端已经收口的部分、仍保留的边界，以及继续施工时应遵守的判断基线。它对应当前代码事实，不是历史计划。

## 当前后端主线

截至当前代码，后端主线稳定在这条路径上：

- FastAPI 提供 HTTP 与 WebSocket 入口（`colearn/api/*`）
- `colearn/server.py` 是统一本地服务入口（单进程单端口，自动拉起 LightRAG）
- `LearningOrchestrator` 负责单轮组装，主链拆成 `colearn/app/stages/*`
- 双模式 + 五段 `LearningPhase` + 三态 `TurnMode`
- `BoardFacts -> TurnPolicy -> LearningEvent` 作为学习状态协议
- `NanobotTurnExecutor` 负责回合执行，挂 nanobot 原生 `AgentHook`
- `memory` / `lightrag` / `web_search` 通过工具方式接入
- `RuntimeCompressionBridge` 与 `ProductCompressionBridge` 分别承担运行时压缩与结果压缩
- session / project / memory 通过 JSON state store 持久化

## API 层结构

`colearn/api/app.py` 已经从单文件巨石收成薄装配层，只负责挂载 router：

- `routes/health.py`
- `routes/settings.py`
- `routes/skills.py`
- `routes/memory.py`
- `routes/projects.py`
- `routes/sessions.py`
- `routes/knowledge.py`
- `ws_handler.py`（WebSocket，内部委托 `api/ws/*`：`frames` / `normalize` / `registry` / `service`）

API-only 的可变状态（settings、memory docs、skills、knowledge task）迁移到 `colearn.api.state` 的可重置 service，便于测试隔离。

> 注意：早期联调阶段补的本地 `auth` 接口（login / register / status / is_first_user）已从当前主线移除，前端也不再依赖。文档不应再把它列为已完成能力。

## 已完成的收口项

### 1. 存储统一

- `LearningSession.created_at / updated_at` 是正式字段，`touch_session()` 直接更新 dataclass 字段
- `colearn.storage.records` 作为统一 record codec
- `SessionStore`、`LearningProjectService`、`EventMemoryStore` 统一走同一套编解码路径

### 2. JSON 写入保护

- `JsonStateStore` 对同一路径使用共享锁
- 写入采用临时文件 + 原子替换

### 3. 后台 product compression 写回收口

- 后台线程只产出 `ProductCompressionResult`
- orchestrator 通过单一入口合并后台结果
- 后台只 patch review / continuation / product compression 状态，不覆盖主链上的 messages / board / status

### 4. Source readiness 进入下游

- `SourceReadinessPreflight` 封装 source 同步与 profile 构建
- 结果写入 `project.retrieval_profile` 与 `LearningTurnRequest.metadata["source_profile"]`
- executor prompt 会读取这份 source readiness 提示

### 5. LightRAG async / sync 边界

- LightRAG client 提供 async / sync 双入口
- 旧 `_run_async()` 线程绕行逻辑已移除
- 同步入口在事件循环中明确失败，executor 走 async retrieval 路径

### 6. 双模式与学习阶段

- session / project 支持 `chat` 与 `learning` 两种 mode
- learning 模式下 `PreflightStage` 解析五段 `LearningPhase`
- chat 模式走轻链路，不构建学习主链上下文、不调度学习型后处理

### 7. nanobot 原生能力接入

- `AgentHook` 真流式（`executor.py` 的 `_StreamHook`）
- `set_model_preset` 按 turn mode 切 preset
- `ContextBuilder.build_system_prompt()` 复用
- Session AutoCompact、Dream consolidation、Board derivation 已挂在 `WritebackStage`
- `long_task / complete_goal / goal_state` 长期目标生命周期

### 8. WebSocket 生命周期测试

- 真实 `/api/v1/ws` 有 ASGI 级测试，覆盖 ping、missing subscribe、cancel 清理、start_turn 成功、异常清理

## 当前代码事实下的边界

### 1. 知识库仍是联调型实现

`KnowledgeWorkspaceService` 负责 source readiness 与轻量 source library 管理，是内存态服务，不是完整知识库主存储。

### 2. API schema 重点收口，不是全部收口

重点入口已 schema 化：settings ui / catalog / test、session create/update、project create/update/sources/anchor、memory update/clear、WebSocket `start_turn`。仍有部分工具型接口与消息层处于收口过程中。

### 3. Board version 不是严格 compare-and-swap

`board_version` 有 stale write 保护，冲突时跳过写回并记录 warning，但不是严格 compare-and-swap。

### 4. Retrieval 仍是 tool-mode

preflight 负责 source readiness，真正知识文本由 `lightrag` tool 按需拉取，不恢复“每轮固定前置 retrieval”。

### 5. `retrieval_bundle` 仍保留在 request contract

`LearningTurnRequest` 仍携带 `retrieval_bundle` 字段，主链未把它完全移出 contract。

## 回归入口

```bash
python -m pytest tests
```

当前测试覆盖 orchestrator pipeline、runtime executor / tooling、retrieval service / cache、board deriver、compression、consolidation、signal extractor、schemas、API app、server env 等（见 `tests/`）。

## 下一步建议

按低风险顺序继续推进时，建议优先关注：

1. 真实页面联调闭环（webui）
2. 知识库 task 状态更接近真实异步过程
3. WebSocket 消息分发层继续强类型化
4. BoardFacts 持久化边界进一步统一
5. `retrieval_bundle` 是否从 request contract 移出

## 使用方式

把这份文档当成当前后端事实记录维护：代码先变化时及时更新“已完成 / 当前边界”；计划先变化时先确认是否落地，再决定是否写入“已完成”。
