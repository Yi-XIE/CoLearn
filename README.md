# CoLearn Nightly

CoLearn Nightly 是 CoLearn 当前可持续打磨的工作仓库。

这个仓库的目标很明确：把学习主链、知识库、记忆、检索、前端壳和本地联调能力收敛到一个可以持续验证、持续补强的 nightly 版本里。

当前主线已经具备：

- Python FastAPI 后端
- WebSocket 学习回合主链
- Next.js 前端工作台
- 本地知识库与文件预览链路
- 轻量认证接口
- Playwright / node / pytest 三类回归入口

## Repository Layout

- `colearn/`
  - 后端主代码
- `tests/`
  - 后端测试
- `web/`
  - Next.js 前端
- `CoLearn-docs/`
  - 架构、维护、交接文档
- `third_party/nanobot-core/`
  - 裁剪后的 nanobot core vendor snapshot
- `.colearn/state/`
  - 本地运行状态目录

## Current Status

截至当前版本，仓库已经完成一轮前后端联调对齐，重点补齐了前端已调用但后端之前缺失的接口：

- `auth/status`
- `auth/login`
- `auth/register`
- `auth/is_first_user`
- `auth/logout`
- `knowledge/tasks/{task_id}/stream`
- `knowledge/{name}/progress/ws`
- `knowledge/{name}/files/{file_path}`
- `settings/tests/{service}/{run_id}/events`

当前更适合继续做的事，不是重新搭骨架，而是：

1. 在稳定机器上跑真实联调
2. 用 Playwright 固化 live flows
3. 再补 task 状态真实性与体验收口

## Local Setup

### Python

建议使用虚拟环境：

```powershell
cd D:\Colearn-nightly
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install fastapi uvicorn httpx anyio pytest pydantic python-multipart
```

### Node

```powershell
cd D:\Colearn-nightly\web
npm install
npx playwright install
```

## Run Locally

### Start Backend

```powershell
cd D:\Colearn-nightly
python -m uvicorn colearn.api.app:app --host 127.0.0.1 --port 8001
```

### Start Frontend

```powershell
cd D:\Colearn-nightly\web
$env:NEXT_PUBLIC_API_BASE='http://127.0.0.1:8001'
$env:NEXT_PUBLIC_AUTH_ENABLED='true'
npm run dev -- --hostname 127.0.0.1 --port 3000
```

前端默认打开地址：

- [http://127.0.0.1:3000](http://127.0.0.1:3000)

## Test Commands

### Backend

```powershell
cd D:\Colearn-nightly
pytest tests\test_api_app.py
```

或完整回归：

```powershell
cd D:\Colearn-nightly
python -m pytest tests
```

### Frontend Node Tests

```powershell
cd D:\Colearn-nightly\web
npm run test:node
```

### Playwright Audit

```powershell
cd D:\Colearn-nightly\web
npm run audit
```

### Playwright Live Integration Smoke

```powershell
cd D:\Colearn-nightly\web
npm run audit:live
```

`audit:live` 主要覆盖：

- 认证
- Knowledge 新建与上传
- 文件出现与预览链路
- Settings diagnostics 点击流

## Docs Guide

优先阅读这些文档：

- [CoLearn-docs/README.md](D:/Colearn-nightly/CoLearn-docs/README.md)
- [CoLearn-顶层组装路径.md](D:/Colearn-nightly/CoLearn-docs/02-Architecture/CoLearn-%E9%A1%B6%E5%B1%82%E7%BB%84%E8%A3%85%E8%B7%AF%E5%BE%84.md)
- [CoLearn-LearningState-协议.md](D:/Colearn-nightly/CoLearn-docs/02-Architecture/CoLearn-LearningState-%E5%8D%8F%E8%AE%AE.md)
- [CoLearn-学习循环实施手册.md](D:/Colearn-nightly/CoLearn-docs/02-Architecture/CoLearn-%E5%AD%A6%E4%B9%A0%E5%BE%AA%E7%8E%AF%E5%AE%9E%E6%96%BD%E6%89%8B%E5%86%8C.md)
- [CoLearn-后端代码补全计划.md](D:/Colearn-nightly/CoLearn-docs/02-Architecture/CoLearn-%E5%90%8E%E7%AB%AF%E4%BB%A3%E7%A0%81%E8%A1%A5%E5%85%A8%E8%AE%A1%E5%88%92.md)
- [CoLearn-Claude-联调补强交接说明.md](D:/Colearn-nightly/CoLearn-docs/04-Claude-Handoffs/CoLearn-Claude-%E8%81%94%E8%B0%83%E8%A1%A5%E5%BC%BA%E4%BA%A4%E6%8E%A5%E8%AF%B4%E6%98%8E.md)

## Local State and Generated Artifacts

这些目录属于本地运行产物，不应提交到 git：

- `.colearn/state/`
- `.colearn/test-state/`
- `.colearn/pytest-cache/`
- `web/test-results/`
- `web/playwright-report/`
- `web/.next/`
- `web/dist/`

## Notes

- 当前仓库优先服务 CoLearn 主线，不再维护 donor 项目叙事。
- 当前认证是本地联调用轻量实现，不是生产级安全方案。
- 当前知识库任务系统是联调型实现，优先保证真实页面可操作与协议稳定。
