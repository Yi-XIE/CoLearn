# CoLearn 顶层组装路径

这份文档只记录当前主线。

## 当前主线

- `webui + runtime_v2 + slim config` 是默认主线。
- 统一本地服务入口是 `python -m colearn.server`（单进程单端口，自动拉起 LightRAG）。
- `runtime_v2` 负责 prompt、tool、result bridge、learning closure。
- `LightRAG` 和 `memory` 是默认学习工具，`web_search` 按需兜底。
- `LearningState` 已进入回写链路；双模式与五段 Learning Phase 已进入主链。

## 关键入口

- 后端 API：`colearn.api.app:app`（薄装配层，挂载 `colearn/api/routes/*` 与 `ws_handler`）
- 运行时层：`colearn.runtime_v2`
- 学习主链：`colearn.app.learning_orchestrator` + `colearn.app.stages.*`
- 学习状态：`colearn.learning.*`（`constants` / `state` / `state_hooks` / `board_hooks` / `turn_hooks`）
- 默认配置：`.colearn/nanobot-v0.2-slim.config.json`
- 前端：`webui/`（Vite + React + Vitest）

## 已完成

- WebUI 主导航接入真实数据。
- 旧 `web/`（Next.js）前端树已删除，前端只剩 `webui/`。
- 旧 `colearn/runtime/*` 主逻辑已删除。
- `colearn/api/app.py` 已拆成多 router 装配层。
- 早期本地 `auth` 接口已从主线移除。

## 当前边界

- 主线继续围绕 `colearn/app/learning_orchestrator.py`、`colearn/app/stages/*`、`colearn/runtime_v2/*`、`webui/src/*` 展开。
- 文档不再保留旧线推进计划。
