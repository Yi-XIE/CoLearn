# CoLearn 个人开发维护手册

## 目标

这份手册只服务个人开发和 nightly 打磨，关注的是每天怎么更轻松地启动、测试、清状态、定位后续拆分顺序，不讨论企业级治理。

## 每天开发的固定入口

- 后端测试：`python -m pytest tests`
- 本地状态预览：`python -m colearn.devtools reset-state --dry-run`
- 本地状态清理：`python -m colearn.devtools reset-state`
- 后端启动：`uvicorn colearn.api.app:app --reload --host 127.0.0.1 --port 8000`
- 前端启动：`cd web && npm run dev`
- 前端 node tests：`cd web && npm run test:node`
- 前端 audit：`cd web && npm run audit`

## 本地状态约定

默认本地状态和测试产物集中在这些位置：

- `.colearn/state/`
- `.colearn/test-state/`
- `.colearn/pytest-cache/`
- `.colearn/test-results/`
- `.colearn/playwright-report/`

`.env` 默认视为个人配置，不参与常规 reset，只有显式带 `--include-env` 才清理。

## 后续 router 拆分顺序

为了减少 `colearn/api/app.py` 的维护压力，后续拆分顺序固定为：

1. `auth`
2. `settings`
3. `memory`
4. `knowledge`
5. `sessions/projects`
6. `ws`

当前第一批真正适合拆的是：

- `auth`
- `settings`
- `memory`

当前先不动的部分：

- WebSocket turn lifecycle
- orchestrator 相关主链
- session / project 与 chat 主路径

## 维护原则

- 先保证启动、测试、状态清理入口稳定
- 再做低耦合 router 拆分
- 学习主链相关改动先更文档，再动代码
- 任何正式文档都不保留乱码或未完成占位
