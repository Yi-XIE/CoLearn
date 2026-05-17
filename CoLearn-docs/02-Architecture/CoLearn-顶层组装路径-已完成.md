# CoLearn 顶层组装路径

这份文档只记录当前代码主线，避免把历史计划写成已经落地的事实。

## 当前主线

- `webui + runtime_v2 + slim config` 是默认主线。
- 后端 API 入口是 `colearn.api.app:app`。
- 单轮学习主链由 `colearn/app/learning_orchestrator.py` 组装。
- `runtime_v2` 负责 prompt、tool、result bridge、learning closure。
- `LearningState` 已进入回合写回链路，核心协议是 `BoardFacts -> TurnPolicy -> LearningEvent`。
- `LightRAG` 和 `memory` 是默认学习工具；其中 `LightRAG` 同时参与回合前预取和回合中工具调用。

## 顶层运行链路

1. `webui` 是当前可运行前端包，覆盖 Chat、Knowledge Garden、Memory、Skills、Settings。
2. WebUI 通过 nanobot gateway 获取 bootstrap、WebSocket token、会话与基础设置能力，同时调用 CoLearn `/api/v1/*` 产品接口。
3. `/api/v1/ws` 收到 `message` 或 `start_turn` 后，创建或恢复 session，写入 `active_turn_id`，发出 `session` 与 `stage_start` 事件。
4. `LearningOrchestrator.run_turn()` 读取 session / project，执行 source readiness preflight，构建 Learning Board 和 State Snapshot。
5. orchestrator 根据 Board 生成 `retrieval_focus` 和 `retrieval_reason`，调用 `RetrievalService.build_bundle()` 做回合前预取，并把 `prefetched_references` 写入 request metadata。
6. `TurnPolicy` 决定本轮 mode、model preset、restriction、enabled tools。
7. `NanobotTurnExecutor` 用 `runtime_v2/prompting.py` 组装 prompt，注册 `memory` / `lightrag` 工具，运行 nanobot v0.2。
8. `learning_closure` 与 `result_bridge` 规范化结果，补齐 `runtime_v2.board_summary`、`runtime_v2.turn_envelope`、`runtime_v2.retrieval`。
9. `_write_back()` 更新 session、project、memory，并把 `board_patch`、`retrieval_hits`、`retrieval_misses`、`retrieval_evidence_map`、`knowledge_support_summary` 写入 `last_turn_result`。
10. 后台 product compression 只补写 review、continuation 和 product compression 状态，不直接覆盖主链整对象。

## 当前默认入口

- 后端 API：`uvicorn colearn.api.app:app --reload --host 127.0.0.1 --port 8000`
- nanobot gateway：`scripts/start-colearn-v2-gateway.ps1`
- slim config：`.colearn/nanobot-v0.2-slim.config.json`
- 前端开发：`cd webui && npm run dev`
- 前端测试：`cd webui && npm run test`
- 前端构建：`cd webui && npm run build`

## 已完成

- WebUI 主入口已收敛到 `webui`，旧 `web/` 目录不是当前运行目标。
- 旧 `colearn/runtime/*` 主逻辑已移除，当前 runtime wrapper 是 `colearn/runtime_v2/*`。
- Session / Project / Memory 通过 `JsonStateStore` 落盘。
- `LearningState` 已接入主链写回。
- source readiness 已进入 request metadata 和 prompt。
- `retrieval_focus`、`prefetch_bundle`、`prefetched_references` 已进入回合前链路。
- retrieval 支撑信息已写入 `runtime_v2.retrieval` 和 `session.last_turn_result`。

## 当前边界

- `retrieval_bundle` 现在承载回合前预取结果，但还没有演进成严格的 `prompt_support_bundle` 选择器。
- `lightrag` 工具返回结构化 evidence，但回写侧当前主要基于回合前 `prefetched_references` 建立 evidence map。
- `TurnPolicy` 只在 `EXPLORE` 模式默认开启 `lightrag` 工具；回合前 prefetch 不受这个工具开关限制。
- 认证、knowledge task、settings diagnostics 是本地联调用轻量实现，不是生产级平台能力。
- API 仍在单文件 `colearn/api/app.py` 内，router 拆分尚未开始。
