# CoLearn Nightly

这个仓库是 Yi 的 CoLearn 独立工作区，目标是把学习主链、检索、记忆、知识库和前端壳稳定在一个可持续打磨的 nightly 版本里。

## 目录

- `colearn/`：后端主代码
- `tests/`：后端测试
- `web/`：Next.js 前端
- `CoLearn-docs/`：架构与维护文档
- `.colearn/state/`：本地运行状态
- `third_party/nanobot-core/`：裁剪后的 nanobot core

## 常用命令

### 后端

- 跑后端测试：
  `python -m pytest tests`
- 当前基线：
  `32 passed`
- 清本地状态预览：
  `python -m colearn.devtools reset-state --dry-run`
- 清本地状态：
  `python -m colearn.devtools reset-state`
- 启动后端 API：
  `uvicorn colearn.api.app:app --reload --host 127.0.0.1 --port 8000`

### 前端

- 安装依赖：
  `cd web`
  `npm install`
- 启动开发服务器：
  `npm run dev`
- 跑前端 node tests：
  `npm run test:node`
- 跑 UI audit：
  `npm run audit`
- 构建：
  `npm run build`

## 本地状态

默认本地状态会写到这些位置：

- `.colearn/state/`
- `.colearn/test-state/`
- `.colearn/pytest-cache/`
- `web/test-results/`
- `web/playwright-report/`

这些目录都属于本地调试产物，不应该进入 git。

## 常见问题

### 为什么 `pytest` 可能报临时目录权限问题

在当前 Windows 环境里，`tmp_path` 相关测试有时需要更高权限访问系统临时目录。代码本身如果没有失败，可以用已授权的方式重跑：

`python -m pytest tests`

### 为什么 git status 里会出现前端报告目录

旧的 `.gitignore` 没有完整覆盖 Playwright 产物。当前仓库已经补齐对 `web/playwright-report/`、`web/test-results/`、`web/dist/` 的忽略。

### 从哪里看当前后端架构

优先看这些文档：

- `CoLearn-docs/02-Architecture/CoLearn-顶层组装路径.md`
- `CoLearn-docs/02-Architecture/CoLearn-LearningState-协议.md`
- `CoLearn-docs/02-Architecture/CoLearn-学习循环实施手册.md`
- `CoLearn-docs/02-Architecture/CoLearn-后端代码补全计划.md`
