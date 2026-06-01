# CoLearn 个人开发维护手册

## 目标

这份手册只服务个人开发和 nightly 打磨，关注的是每天怎么更轻松地启动、测试、清状态，不讨论企业级治理。

## 每天开发的固定入口

后端 / 统一服务：

- 后端测试：`python -m pytest tests`
- 统一本地服务（单进程单端口，默认 8001，会自动拉起 LightRAG）：
  `python -m colearn.server --port 8001`
- 只起 FastAPI、不拉 LightRAG：`python -m colearn.server --port 8001 --skip-lightrag`
- 纯 API（调试用，不含 LightRAG 自动启动）：
  `uvicorn colearn.api.app:app --reload --host 127.0.0.1 --port 8001`
- 本地状态预览：`python -m colearn.devtools reset-state --dry-run`
- 本地状态清理：`python -m colearn.devtools reset-state`

前端（`webui/`，Vite + React + Vitest）：

- 安装依赖：`cd webui && pnpm install`
- 前端启动：`cd webui && pnpm dev`
- 前端测试：`cd webui && pnpm test`
- 前端构建：`cd webui && pnpm build`
- 前端 lint：`cd webui && pnpm lint`

> 说明：旧的 Next.js `web/` 前端树已删除，现在前端只有 `webui/`。

## 本地状态约定

默认本地状态和测试产物集中在 `.colearn/` 下：

- `.colearn/state/`：session / project / memory / settings 等运行态 JSON
- `.colearn/test-state/`：测试用隔离状态
- `.colearn/nanobot-workspace/`：nanobot runtime workspace
- `.colearn/lightrag-store/`：LightRAG 本地存储与日志
- `.colearn/knowledge/`：知识库 source library
- `.colearn/tmp/`：临时产物

`.env` 默认视为个人配置，不参与常规 reset，只有显式带 `--include-env` 才清理。

## 配置入口

- 默认 nanobot 配置：`.colearn/nanobot-v0.2-slim.config.json`
- LightRAG 启动配置：`.colearn/lightrag.json`
- Provider key（如 `DEEPSEEK_API_KEY`、Brave Search key）写入 `.env`，
  `server.py` 启动时会从 `.env` 与 settings 状态同步进运行时环境变量。

## router 拆分现状

`colearn/api/app.py` 已经从单文件巨石收成薄装配层，只负责 include 各 router：

- `colearn/api/routes/health.py`
- `colearn/api/routes/settings.py`
- `colearn/api/routes/skills.py`
- `colearn/api/routes/memory.py`
- `colearn/api/routes/projects.py`
- `colearn/api/routes/sessions.py`
- `colearn/api/routes/knowledge.py`
- `colearn/api/ws_handler.py`（WebSocket，内部委托 `colearn/api/ws/*`）

也就是说历史手册里“后续 router 拆分顺序”这件事已经基本落地。早期联调阶段的本地 `auth` 接口当前已从主线移除，不再是独立待拆项。

## 维护原则

- 先保证启动、测试、状态清理入口稳定
- 学习主链相关改动先更文档，再动代码
- 任何正式文档都不保留乱码或未完成占位
