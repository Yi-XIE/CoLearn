# nanobot v0.2.0 源码对照报告

本文基于本地已落盘源码：

- `D:\Colearn-nightly\third_party\nanobot-0.2.0\nanobot-0.2.0`

目标不是做 release 摘要，而是回答一个更实际的问题：

**哪些要素可以直接拿来给 CoLearn 用，哪些适合低成本适配，哪些只适合借设计。**

## 结论先行

`nanobot v0.2.0` 里，最值得 CoLearn 直接吸收的不是某个单点功能，而是三套已经成型的结构：

1. WebUI 打包进 wheel 的发布方式
2. 持续目标 `/goal -> long_task -> complete_goal` 的状态链
3. Agent loop 的函数式状态机骨架

此外，provider fallback、模型 preset、工具插件化、WebSocket + REST 复用网关，也都已经成熟到可以实地借用。

如果按优先级排，建议 CoLearn 这样拿：

1. 先拿 WebUI 打包与网关挂载方案
2. 再拿持续目标状态链
3. 然后对照 Agent loop 状态机
4. 最后再挑 provider fallback 和工具插件化

## A. 可直接拿来用

### A1. WebUI 打包进 wheel

源码入口：

- [hatch_build.py](D:/Colearn-nightly/third_party/nanobot-0.2.0/nanobot-0.2.0/hatch_build.py)
- [pyproject.toml](D:/Colearn-nightly/third_party/nanobot-0.2.0/nanobot-0.2.0/pyproject.toml)
- [vite.config.ts](D:/Colearn-nightly/third_party/nanobot-0.2.0/nanobot-0.2.0/webui/vite.config.ts)
- [webui/README.md](D:/Colearn-nightly/third_party/nanobot-0.2.0/nanobot-0.2.0/webui/README.md)

它已经把整条链走通了：

- 构建时自动跑 `webui` 的 `install + build`
- 输出目录固定写到 `nanobot/web/dist`
- wheel / sdist 显式 include `nanobot/web/dist/**/*`
- editable install 跳过打包，继续走前端本地开发模式
- `bun` 不在时自动退回 `npm`

这部分对 CoLearn 的价值非常直接，因为我们现在已经有：

- 后端：[app.py](D:/Colearn-nightly/colearn/api/app.py)
- 前端：`D:\Colearn-nightly\web`

可以直接借的要素：

- `build hook` 思路
- `dist` 目录进 wheel 的打包规则
- editable 模式和正式打包模式分流
- `bun -> npm` 回退逻辑

建议：

- 这部分优先直接抄设计，保留结构，少改名字。
- CoLearn 后面可以做自己的 `hatch_build.py` 或等价构建钩子。

### A2. 持续目标状态链

源码入口：

- [nanobot/command/builtin.py](D:/Colearn-nightly/third_party/nanobot-0.2.0/nanobot-0.2.0/nanobot/command/builtin.py)
- [long_task.py](D:/Colearn-nightly/third_party/nanobot-0.2.0/nanobot-0.2.0/nanobot/agent/tools/long_task.py)
- [goal_state.py](D:/Colearn-nightly/third_party/nanobot-0.2.0/nanobot-0.2.0/nanobot/session/goal_state.py)

这条链已经非常完整：

- `/goal` 只是命令入口
- 真正的状态写入发生在 `long_task`
- 结束通过 `complete_goal`
- 状态存进 session metadata
- 每轮都镜像进 runtime context
- WebSocket 还能单独发 `goal_state` / `goal_status`
- 活动目标存在时会放宽 wall timeout

这套机制和 CoLearn 的主线一致，因为我们本来就有：

- `LearningState`
- 项目 goal
- 会话
- 统一 WS

可以直接拿的要素：

- `goal_state` 这个元数据层
- `active/completed` 这类目标生命周期
- “每轮镜像进 runtime context”的机制
- “有目标时延长超时”的策略
- WebSocket 推送目标状态的事件模型

建议：

- 不要直接照搬名字到产品层，但底层协议可以几乎原样借。
- CoLearn 可以保留学习语义，比如把 `long_task` 映射成 `learning_goal` 或 `active_goal`。

### A3. Provider fallback

源码入口：

- [fallback_provider.py](D:/Colearn-nightly/third_party/nanobot-0.2.0/nanobot-0.2.0/nanobot/providers/fallback_provider.py)
- [config/schema.py](D:/Colearn-nightly/third_party/nanobot-0.2.0/nanobot-0.2.0/nanobot/config/schema.py)

这块已经不是“将来可以做”，而是一个很成熟的最小成品：

- 只在可重试错误上 fallback
- 已经开始流式输出时不再切换，避免重复内容
- 主 provider 连续失败会熔断
- fallback 支持不同 provider、不同 model、不同 generation 配置

可以直接拿的要素：

- fallback 判定规则
- circuit breaker 思路
- “流式已出 token 就不切换”的边界
- 配置层定义 `fallback_models`

对 CoLearn 的直接作用：

- settings diagnostics
- 统一 WS 聊天链路
- 后续多 provider 真实上线稳定性

## B. 低成本适配后可用

### B1. Agent loop 的函数式状态机骨架

源码入口：

- [loop.py](D:/Colearn-nightly/third_party/nanobot-0.2.0/nanobot-0.2.0/nanobot/agent/loop.py)

这版 loop 最值得看的不是每个细节，而是它已经明确变成了状态机：

- `TurnState`
- `_TRANSITIONS`
- `_state_restore`
- `_state_compact`
- `_state_command`
- `_state_build`
- `_state_run`
- `_state_save`
- `_state_respond`

这对 CoLearn 特别有启发，因为我们当前 [app.py](D:/Colearn-nightly/colearn/api/app.py) 和运行链已经有统一 WS，但状态分层还没有像这个 loop 一样收得这么清楚。

为什么说“低成本适配”，不是“直接拿”：

- nanobot 的 loop 强绑定它自己的 session、tool、bus、channel 体系
- CoLearn 目前的学习态、知识库态、项目态是另一套产品结构

建议的拿法：

- 先借状态机形状，不直接搬内部实现
- 先把 CoLearn 当前 turn 流程映射成：
  - restore
  - compact
  - build
  - run
  - save
  - respond
- 再逐步把当前散在逻辑往这些阶段收

### B2. 工具插件架构

源码入口：

- [loader.py](D:/Colearn-nightly/third_party/nanobot-0.2.0/nanobot-0.2.0/nanobot/agent/tools/loader.py)

这个 loader 已经具备两层发现机制：

- 包内自动扫描
- 外部 entry points 插件

它的优点是：

- 工具自描述
- 注册集中
- 内建工具和外部插件都能并存
- 有 collision 处理

对 CoLearn 来说适配成本不高，但当前不是第一优先，因为我们现在还没有把 CoLearn 组织成“开放工具平台”。

建议：

- 先把这个 loader 当未来形态参考
- 真要落地时，可以先只做“包内自动发现”，不用一步上 entry points

### B3. WebUI 网关代理方式

源码入口：

- [vite.config.ts](D:/Colearn-nightly/third_party/nanobot-0.2.0/nanobot-0.2.0/webui/vite.config.ts)
- `nanobot/channels/websocket.py`

这条线的特点是：

- Vite dev server 代理 `/api`、`/webui`、`/auth`
- WebSocket 走 `/` 升级
- 生产态直接由同一个 gateway 提供静态资源和 API

对 CoLearn 来说，这比我们现在的 `web` + `api` 分离式开发更进一步。

可以低成本适配的要素：

- dev proxy 约定
- 生产态网关统一提供静态文件 + API
- `bootstrap` 接口先拿 token，再拉起 WS

但不能直接照抄：

- nanobot 的前端协议、会话 surface、auth 方式与 CoLearn 不同

## C. 只适合借设计，不适合直接搬

### C1. 整个 WebUI 前端

虽然 `webui/` 已经完整存在，但不建议直接全量替换 CoLearn 的 [web](D:/Colearn-nightly/web)。

原因：

- CoLearn 已经有自己的学习工作台结构
- nanobot WebUI 面向的是个人 AI agent 通用聊天表面
- CoLearn 的知识库、项目、学习状态、记忆面板都已经有自己的产品语言

建议：

- 借“发布方式”和“网关接法”
- 借 auth/bootstrap/streaming 的组织方式
- 不直接整体替换前端

### C2. `/goal` 的命令式产品表面

命令本身很好，但 CoLearn 不一定要把学习目标暴露成命令。

更适合的做法可能是：

- UI 上的“持续目标”开关
- 项目或会话级目标卡片
- 学习回合里自动提升成 active goal

所以：

- 底层状态链能借
- 产品入口不一定照搬 `/goal`

### C3. 全量 provider 面

nanobot 的 provider 覆盖面很宽，还带很多渠道集成。CoLearn 当前不需要把整套 provider surface 全搬进来。

该借的是：

- fallback 机制
- provider capability 声明
- preset 切换思路

不急着借的是：

- 所有 provider 实现
- 所有 OAuth / channel / bridge 能力

## D. 与 CoLearn 当前代码的直接映射

### D1. 最适合先动的区域

CoLearn 当前这几个位置最适合承接：

- 后端 API 主入口：[app.py](D:/Colearn-nightly/colearn/api/app.py)
- 后端状态服务：[state.py](D:/Colearn-nightly/colearn/api/state.py)
- 学习状态：[state.py](D:/Colearn-nightly/colearn/learning/state.py)
- 前端工作台：[web](D:/Colearn-nightly/web)

### D2. 立即可做的小迁移

1. 为 CoLearn 增加“持续目标状态”协议层  
落点：`colearn/api/state.py` 或 `colearn/learning/`

2. 在统一 WS 里加 `goal_status` / `goal_state` 事件  
落点：[app.py](D:/Colearn-nightly/colearn/api/app.py)

3. 为未来一体化打包准备前端 `dist` 进入 Python 包的路径  
落点：项目根构建配置

4. 把当前 turn 执行链整理成显式阶段  
落点：runtime / orchestrator 相关模块

### D3. 可以晚一点再动的

- 工具 entry-point 插件化
- 全量 provider 迁移
- 图像生成完整产品化
- 直接替换前端

## E. 能直接拿来用的一切要素清单

下面这份是最实用的清单。

### 可以直接拿

- `hatch_build.py` 的 WebUI 打包机制
- `pyproject.toml` 中 `nanobot/web/dist/**/*` 的 wheel / sdist include 规则
- `long_task` / `complete_goal` 这套 session metadata 协议
- `goal_state_runtime_lines()` 的“每轮注入上下文”机制
- `runner_wall_llm_timeout_s()` 的“活动目标延长超时”策略
- `FallbackProvider` 的 request-scoped failover 逻辑
- `fallback_models` 的配置形状

### 可以低成本适配

- `AgentLoop` 的状态机骨架
- Tool loader 的自动发现机制
- WebUI dev proxy 和生产态统一 gateway 方式
- `ModelPresetConfig` 与运行时 preset 切换思路
- `goal_status` WebSocket 事件模型

### 只借设计

- 完整 WebUI 前端实现
- `/goal` 的命令式产品入口
- 全量 provider / channel / OAuth 面

## F. 建议的下一步

如果我们准备开始真正“拿代码过来用”，最合理的顺序是：

1. 先做一轮 WebUI 打包方案迁移设计。
2. 再把持续目标状态链接到 CoLearn 的统一 WS。
3. 然后单独开一轮 Agent loop 对照重构。

不要一上来大规模替换 CoLearn 前端或把 nanobot 全量并进主链。最值钱的是它已经打磨好的机制，不是整仓搬家。
