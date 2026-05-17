# CoLearn 个人开发维护手册

## 目标

这份手册只服务个人开发和 nightly 打磨，关注的是每天怎么更轻松地启动、测试、清状态、定位后续拆分顺序，不讨论企业级治理。

## 每天开发的固定入口

后端：

```bash
python -m pytest tests
python -m colearn.devtools reset-state --dry-run
python -m colearn.devtools reset-state
uvicorn colearn.api.app:app --reload --host 127.0.0.1 --port 8000
```

nanobot gateway：

```powershell
$env:COLEARN_NANOBOT_TOKEN_ISSUE_SECRET="local-dev-secret"
.\scripts\start-colearn-v2-gateway.ps1
```

前端：

```bash
cd webui
npm run dev
npm run test
npm run build
npm run lint
```

## 当前目录事实

- `webui/` 是当前可运行前端包。
- `web/` 不是当前运行目标，里面没有前端 package 入口。
- `colearn/runtime_v2/` 是当前 runtime wrapper。
- `colearn/runtime/` 已不存在。
- `.colearn/nanobot-v0.2-slim.config.json` 是当前 slim config。
- `scripts/start-colearn-v2-gateway.ps1` 是当前推荐 gateway 启动脚本。

## 本地状态约定

默认本地状态和测试产物集中在这些位置，和 `colearn.devtools.DEFAULT_RESET_PATHS` 保持一致：

- `.colearn/state/`
- `.colearn/test-state/`
- `.colearn/pytest-cache/`
- `.colearn/tmp/`
- `.colearn/logs/`
- `.colearn/nanobot-workspace/`
- `.colearn/webui/`
- `.colearn/test-results/`
- `.colearn/playwright-report/`

`.env` 默认视为个人配置，不参与常规 reset，只有显式带 `--include-env` 才清理。

## 文档更新自检

写入正式文档后，至少做一次临时全文搜索，检查未完成占位符、替换字符和明显编码损坏。占位符样例不要写进正式笔记正文，避免文档自检时命中自身。

如果是大幅更新架构文档，再顺手检查最近改动：

```bash
git diff -- CoLearn-docs\02-Architecture
```

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
- retrieval 链路改动要同步更新 LearningState 协议和学习循环手册
- 任何正式文档都不保留编码损坏或未完成占位
