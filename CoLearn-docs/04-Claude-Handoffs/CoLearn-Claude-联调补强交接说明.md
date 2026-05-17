# CoLearn Claude 联调补强交接说明

## 1. 这份文档给谁看

这份文档写给后续在另一台机器上使用 Claude 接手 CoLearn 联调补强工作的同学。

目标不是从零理解项目，而是尽快进入高价值区域：

1. 先把当前已经补齐的链路接住
2. 再把真实页面联调跑通
3. 最后补自动化和体验收口

## 1.1 代码同步约束

Claude 接手时，不要基于手工拷贝目录或旧本地副本开工。

要求：

1. 先通过远端仓库拉取最新代码
2. 确认接手机器上的分支、提交和当前主线一致
3. 再开始安装依赖、启动服务和补联调

建议顺序：

```powershell
git fetch --all
git status
git pull
```

如果 Claude 使用的是单独工作目录或新的机器，也建议先重新 clone，再按本文档继续。

## 2. 当前已经完成的内容

本轮已经完成一版后端补齐，重点是把前端已经在调用、但后端之前缺失的接口补上。

已补齐能力：

1. 认证接口
   - `GET /api/v1/auth/status`
   - `POST /api/v1/auth/login`
   - `POST /api/v1/auth/register`
   - `GET /api/v1/auth/is_first_user`
   - `POST /api/v1/auth/logout`

2. 知识库任务与文件接口
   - `GET /api/v1/knowledge/tasks/{task_id}/stream`
   - `WS /api/v1/knowledge/{name}/progress/ws`
   - `GET /api/v1/knowledge/{name}/files/{file_path}`
   - `POST /api/v1/knowledge/create`
   - `POST /api/v1/knowledge/{name}/upload`
   - `POST /api/v1/knowledge/{name}/reindex`

3. Settings diagnostics 事件流
   - `GET /api/v1/settings/tests/{service}/{run_id}/events`

4. 自动化回归
   - `pytest tests/test_api_app.py` 已通过
   - `npm run test:node` 已通过

主要改动集中在：

- `colearn/api/app.py`
- `colearn/api/state.py`
- `colearn/api/schemas.py`
- `tests/test_api_app.py`

## 3. 当前真实联调的状态判断

### 已确认

1. 代码层面的接口缺口已经补上
2. 前端现有调用路径与后端已有路由已经基本对齐
3. Playwright live 联调脚本已经补了一版

相关文件：

- `webui` 的联调审计与样本数据

### 还没有完全收口的地方

当前未完成的不是协议设计，而是真实环境联调闭环。

主要卡点：

1. 当前 Codex 工作环境里前后端进程不稳定常驻
   - 后端 `127.0.0.1:8001` 有时会被环境回收
   - 前端 `127.0.0.1:3000` 有时会被环境回收

2. 所以 Playwright live 脚本已经能开始执行，但真实失败点来自服务未常驻，而不是脚本逻辑本身

3. 这意味着后续工作重点应该放在另一台机器上的稳定联调环境，不要在当前环境里过度排查服务常驻问题

## 4. 希望 Claude 重点发力的区域

### A. 先跑通真实页面联调

优先级最高。

目标不是先重构，而是先确认用户真的能在页面上完成以下动作：

1. 注册
2. 登录
3. 打开 Knowledge 页面
4. 新建 source library
5. 上传首个文件
6. 在 Files 标签里看到文件
7. 预览该文件
8. 在 Index versions 标签触发 reindex
9. 在 Settings 页面点击 `Run test`
10. 看到 diagnostics 日志流和完成态

建议动作：

1. 在稳定机器上常驻启动前后端
2. 先手工点一遍
3. 再跑 `npm run audit:live`
4. 根据真实 DOM 和文案微调 Playwright 脚本

### B. 把 Playwright live 脚本拆细

当前 live 脚本是一条串行大流程，适合冒烟，但不利于定位。

建议拆成 3 组：

1. `auth-live.audit.ts`
   - 注册
   - 登录态检查
   - 登出

2. `knowledge-live.audit.ts`
   - 新建知识库
   - 上传文件
   - 文件列表
   - 文件预览
   - reindex

3. `settings-live.audit.ts`
   - 打开 settings
   - 点击 `Run test`
   - 验证事件流

拆分目的：

1. 失败点更清楚
2. 可以只重跑某一类问题
3. 后续 CI 更容易接

### C. 提升知识库任务状态的真实性

当前知识库任务系统是为了联调完整性做的轻量实现，已经可用，但还比较薄。

希望补强的方向：

1. 让 `create / upload / reindex` 的状态更接近真实异步任务
2. 统一 `queued | running | completed | failed`
3. SSE 日志内容更稳定
4. WebSocket progress 在任务期间有更连续的反馈
5. reindex 失败时给出更明确错误语义

注意：

当前目标仍然是“联调可消费”，不是立刻做完整任务系统基础设施。

### D. 文件预览链路做一次真实检查

需要重点看：

1. txt / md 预览是否正常
2. pdf iframe 是否能正常加载
3. 文件路径编码是否在中文、空格、子目录场景下稳定
4. 404 文件预览时前端是否优雅失败，而不是卡死

### E. 认证体验收口

当前认证是本地轻量实现，足够联调，但需要补一轮体验验证：

1. 前端打开后是否会正确读取登录态
2. 未登录情况下 401 跳转 `/login` 是否真的存在页面闭环
3. 登出后是否回到可预期页面
4. 首用户 admin 逻辑是否符合实际预期

待确认：当前前端是否已经存在完整可用的 `/login` 页面。如果没有，需要优先补页面，而不是继续扩展后端认证语义。

## 5. 不希望 Claude 花太多力气的地方

这些地方先别重投入，除非真实联调证明它们已经变成阻塞项。

1. 不要先做大规模重构
   - 尤其不要重写 `projects / sessions / ws` 主干
   - 这条链路当前测试是绿的，优先保持稳定

2. 不要先引入正式生产级认证方案
   - 例如 OAuth、JWT 刷新体系、多角色权限模型
   - 当前阶段只需要本地联调闭环

3. 不要先把知识库任务系统做成重量级后台基础设施
   - 当前更需要真实页面可操作，而不是平台化抽象

4. 不要大改前端接口命名
   - 当前前端调用路径就是合同来源
   - 优先维持前端 contract，后端适配它

5. 不要把注意力放在 donor 项目叙事或历史迁移说明上
   - 本轮只围绕 CoLearn 当前主线

## 6. 建议的工作顺序

### 第一阶段：稳定环境

1. 在接手机器上确认 Python、Node、Playwright 可用
2. 后端固定跑在 `127.0.0.1:8001`
3. 前端固定跑在 `127.0.0.1:3000`
4. `NEXT_PUBLIC_API_BASE=http://127.0.0.1:8001`
5. `NEXT_PUBLIC_AUTH_ENABLED=true`

## 6.1 Claude 接手时建议先安装的依赖

当前仓库里没有现成的 `requirements.txt` 或 `pyproject.toml` 作为 Python 环境真源，所以请直接按下面这组最小依赖安装。

### Python 侧

建议先创建虚拟环境，然后安装：

```powershell
cd D:\Colearn-nightly
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install fastapi uvicorn httpx anyio pytest pydantic python-multipart
```

说明：

1. `fastapi`
   - 后端 HTTP / WebSocket 入口
2. `uvicorn`
   - 本地启动后端
3. `httpx`
   - 后端测试和接口串联
4. `anyio`
   - 异步测试依赖
5. `pytest`
   - Python 测试
6. `pydantic`
   - schema 模型
7. `python-multipart`
   - 知识库上传接口依赖，缺它时 `Form` / `UploadFile` 相关接口容易直接起不来

如果 Claude 在接手时发现还缺别的 Python 包，再以真实报错为准增补，但不要先盲目大装。

### Node / 前端侧

```powershell
cd D:\Colearn-nightly\web
npm install
npx playwright install
```

说明：

1. `npm install`
   - 安装 Next.js、React、Playwright test runner 和现有前端依赖
2. `npx playwright install`
   - 安装浏览器内核，不装的话 live audit 很可能跑不起来

如果是 CI 或更干净的机器，也可以用：

```powershell
cd D:\Colearn-nightly\web
npm ci
npx playwright install
```

### Claude 接手第一步检查单

建议 Claude 拿到机器后先做这一组检查，再开始改代码：

1. `python -m uvicorn colearn.api.app:app --host 127.0.0.1 --port 8001`
   - 能否正常启动
2. `pytest tests\test_api_app.py`
   - 是否全绿
3. `cd web && npm run test:node`
   - 是否全绿
4. `cd web && npm run dev -- --hostname 127.0.0.1 --port 3000`
   - 前端是否能打开
5. `cd web && npm run audit:live`
   - live 冒烟会卡在哪一步

### 第二阶段：手工联调

按页面真实点一遍：

1. 首页
2. Knowledge
3. Settings
4. 登录态跳转

记录：

1. 哪一步真实能通
2. 哪一步是 DOM 文案变化
3. 哪一步是接口协议还不够
4. 哪一步是前端页面缺失

### 第三阶段：补 Playwright

1. 修 live audit
2. 拆分成多条测试
3. 让每条失败信息更聚焦

### 第四阶段：补后端真实性

只在真实联调已经基本打通之后，再补：

1. task 状态细化
2. progress 连续反馈
3. 文件预览边角
4. auth 页面闭环

## 7. 推荐本机联调命令

后端：

```powershell
cd D:\Colearn-nightly
python -m uvicorn colearn.api.app:app --host 127.0.0.1 --port 8001
```

前端：

```powershell
cd D:\Colearn-nightly\web
$env:NEXT_PUBLIC_API_BASE='http://127.0.0.1:8001'
$env:NEXT_PUBLIC_AUTH_ENABLED='true'
npm run dev -- --hostname 127.0.0.1 --port 3000
```

Node 测试：

```powershell
cd D:\Colearn-nightly\web
npm run test:node
```

后端测试：

```powershell
cd D:\Colearn-nightly
pytest tests\test_api_app.py
```

Playwright live 冒烟：

```powershell
cd D:\Colearn-nightly\web
npm run audit:live
```

## 8. 联调验收口径

Claude 接手后，建议把“完成”定义成下面这个口径，而不是只看单测是否通过。

### 最低验收

1. `pytest tests/test_api_app.py` 通过
2. `npm run test:node` 通过
3. 可以真实创建知识库并上传文本文件
4. 可以在 Files 中看到并打开文件
5. `Run test` 能产生日志并完成

### 理想验收

1. Playwright live 脚本稳定通过
2. auth / knowledge / settings 三条 live 用例拆分完成
3. 失败信息足够明确，便于后续维护

## 9. 交接结论

当前状态不需要再做一轮“找缺什么接口”的分析了。

后续接手最应该做的是：

1. 在稳定机器上把真实联调跑通
2. 用 Playwright 固化真实页面路径
3. 只围绕真实阻塞点补后端和页面

一句话总结：

先联通，后打磨；先真实点击，后补抽象；先补闭环，别急着重构。
