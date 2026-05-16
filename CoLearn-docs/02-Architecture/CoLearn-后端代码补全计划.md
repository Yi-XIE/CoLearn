# CoLearn 后端代码补全计划

日期：2026-05-16  
归属架构层：02-Architecture / 后端代码补全计划

## 目标

本计划用于把当前后端从“最小闭环已跑通”推进到“可持续迭代的产品化后端”。

当前基线已经成立：

1. FastAPI 产品入口可用。
2. `LearningTurnRequest` 是 runtime 唯一入口。
3. `LearningTurnResult` 是 runtime 唯一出口。
4. Learning Board、Policy、Learning Events 已形成闭环。
5. Memory 与 LightRAG 已作为 nanobot 工具接入。
6. runtime compression 位于主路，product compression 位于后台。
7. 后端测试基线为 `python -m pytest tests`，当前结果为 15 passed。

补全原则：

1. 不恢复每轮前置 retrieval。
2. 不新增第二条 agent loop。
3. 不让 product compression 阻塞用户主回复。
4. 不破坏现有 `/api/v1` 路由和前端调用。

## 第一阶段：工程底座收口

状态：已完成

目标：让仓库、忽略规则、测试入口稳定下来。

实施内容：

1. 在 `D:\Colearn-nightly` 初始化 git 仓库。
2. 根目录维护 `.gitignore`，忽略本地状态、缓存、依赖目录、构建产物、日志和密钥文件。
3. 将源码、测试、架构文档、`third_party/nanobot-core`、`web/package-lock.json` 纳入版本管理候选范围。
4. 保持 `.colearn/state`、`.colearn/test-state`、`.colearn/pytest-cache` 为本地运行数据，不纳入版本管理。

验收标准：

1. `git status --short` 不显示 `web/node_modules`、`web/dist`、Python 缓存或 `.colearn` 本地状态。
2. `python -m pytest tests` 通过。
3. 本文档不包含未完成占位符、损坏字符或成片乱码。

## 第二阶段：Learning Board 写回强化

状态：已完成

目标：让 Board 成为稳定的事实源，避免后台任务覆盖主链结果。

实施内容：

1. 为 Board 写回补齐 `updated_at`，使用 ISO 8601 UTC 字符串。
2. 在 session 与 project 写回时校验 `board_version`，只允许基于当前版本递增写入。
3. 将同步主链写回与后台 product compression 写回拆成不同 patch 类型。
4. 后台写回只更新 review、continuation、memory projection 等产品化字段，不覆盖较新的 `current_progress`、`gaps_and_blockers`。
5. 为冲突写回记录 warning，并保留用户主回复。

验收标准：

1. 同一 session 连续两轮写回时，Board version 单调递增。
2. 后台 finalizer 基于旧 Board 版本完成时，不覆盖新一轮同步 Board。
3. session 与 project 的 `board_facts` 保持一致。

## 第三阶段：Learning Events 结构化补强

状态：已完成

目标：让事件能更准确地驱动 Board patch，而不是只依赖简单启发式。

实施内容：

1. 保留 `CONTINUATION_UPDATED`、`NODE_STARTED`、`NODE_COMPLETED`、`BLOCKER_FOUND`。
2. 新增 `EVIDENCE_ATTACHED`，用于记录本轮引用过的 source ref、tool name、chunk id。
3. 统一事件 payload 为 JSON 可序列化字段。
4. 在 `after_turn_payload()` 中输出事件列表、board patch、memory events，并保证三者使用同一 updated board。
5. 增加事件 reducer 测试，覆盖节点完成、blocker 新增、证据引用追加。

验收标准：

1. 所有 Learning Events 可 `json.dumps`。
2. `NODE_COMPLETED` 不重复追加已完成节点。
3. `BLOCKER_FOUND` 使用稳定 id 去重。
4. `EVIDENCE_ATTACHED` 能进入 Board 的 `evidence_refs`。

## 第四阶段：WebSocket Turn Lifecycle 补齐

状态：已完成

目标：让前端能稳定感知回合启动、流式输出、取消、失败和完成。

实施内容：

1. `start_turn` 创建 `turn_id`，写入 session 的 `active_turn_id` 与 `active_turns`。
2. 每个 WebSocket turn event 携带 `turn_id`、`phase`、`warnings`、`tool_events`。
3. `cancel_turn` 清理 active turn，并发送 cancel ack。
4. 异常路径发送 error event，同时清理 session active turn。
5. `subscribe_turn` 可以读取最近一次 turn 状态，供前端刷新后恢复。

验收标准：

1. 正常完成后 active turn 为空。
2. cancel 后 active turn 为空。
3. runtime 异常后 active turn 为空，session 主数据不损坏。
4. 前端无需新增破坏性路由即可读取 turn 状态。

## 第五阶段：Product Compression 后台安全

状态：已完成

目标：后台整理可追踪、可失败、可重试，不影响主路。

实施内容：

1. `BackgroundTurnFinalizer` 捕获异常并写入 session/project 的 compression warning。
2. 后台结果写入前检查 Board version，避免覆盖更新的 Board。
3. 为后台产物增加 `status`、`started_at`、`finished_at`、`error`。
4. memory projection 只追加事件，不删除既有 memory。
5. review summary 与 continuation prompt 写入单独字段，并同步到 latest review。

验收标准：

1. 后台异常时，用户主回复仍已保存。
2. session 可以看到 compression 失败原因。
3. 后台成功时，latest review 与 continuation prompt 可恢复到下一轮上下文。

## 第六阶段：工具箱与 Retrieval 观测性

状态：已完成

目标：保持 LightRAG / Memory 作为工具，同时让失败和调用结果可观察。

实施内容：

1. Memory tool 返回命中的 memory event id、kind、summary。
2. LightRAG tool 返回 retrieval status、source refs、warnings、文本片段。
3. 工具失败时返回可读 observation，不抛出导致主链中断的异常。
4. `LearningTurnResult.raw_learning_result` 保留 `tool_events`，用于 API 与 WebSocket 展示。
5. project retrieval profile 展示 source readiness、last sync status、last tool usage。

验收标准：

1. 无检索需求的回合不会强制调用 LightRAG。
2. LightRAG 不可用时主回复可继续，并带 warning。
3. Memory 与 LightRAG 的调用记录能在 turn result 中看到。

## 第七阶段：API Schema 收紧

状态：已完成

目标：把当前宽松 dict payload 收成明确 schema，同时保持兼容。

实施内容：

1. 为 settings、memory、knowledge、WebSocket 消息补充 Pydantic payload。
2. 旧字段继续接受，新字段优先使用。
3. session/project 返回体增加 `board_version`、`board_updated_at`、`latest_review_status`。
4. 错误响应统一为 `{"error": {"code": string, "message": string}}` 的兼容结构。
5. 为 schema 兼容性增加 API 测试。

验收标准：

1. 现有前端调用不需要改路由。
2. 旧 payload 仍可通过测试。
3. 新增字段能被前端渐进使用。

## 测试矩阵

每次阶段完成后运行：

```powershell
python -m pytest tests
```

新增测试场景：

1. Board version 冲突不会覆盖较新 Board。
2. 后台 product compression 失败时，session 主结果保留。
3. WebSocket cancel 后 active turn 被清理。
4. LightRAG tool 失败时主回复继续返回 warning。
5. Learning Events 全部 JSON 可序列化。
6. 新增 API schema 兼容旧 payload。

## 当前优先级

1. 已完成 git 初始化与忽略规则。
2. 已补 Board 写回并发控制。
3. 已补 WebSocket turn lifecycle。
4. 已强化后台 compression 与工具观测。
5. 已收紧 API schema。

## 验收记录

2026-05-16：

1. `python -m pytest tests` 通过，结果为 19 passed。
2. Board version 冲突测试通过，旧回合不会覆盖较新 Board。
3. 后台 product compression 失败保护测试通过，session 主结果保留。
4. Learning Events JSON 序列化测试通过，证据引用可进入 Board。
5. API schema 兼容测试通过，旧 payload 额外字段不破坏调用。

## 维护规则

1. 每完成一个阶段，同步更新本文档的验收状态。
2. 文档中只写已确认事实和明确计划。
3. 如果遇到依赖或外部服务不确定，写成“待确认：缺少的具体信息”，并在确认后替换为结论。
4. 正式笔记写入前后都检查是否包含未完成占位符、损坏字符或成片乱码。
