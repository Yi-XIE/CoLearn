# CoLearn Plugin Host Contract

版本：v0.2 Demo  
宿主基线：NanoBot `v0.2.1` 本地快照  
日期：2026-06-03  
状态：Demo 期务实契约

## 1. 文档定位

这份文档描述的是 CoLearn 在当前 NanoBot 宿主上的最小可用接入契约。

它不是在宣称 NanoBot 已经提供了一个长期稳定、公开承诺的通用插件平台，而是在明确：

- 当前 Demo 已经真实依赖了哪些宿主入口
- 哪些能力属于稳定方向
- 哪些能力属于 `v0.2.1` 的务实 fallback

本轮目标是“宿主真实链路可用”。

## 2. 真相边界

CoLearn 的状态真相仍然留在 `.colearn/`：

- 课程知识真相：`.colearn/wiki/`
- 学习状态真相：`.colearn/state/sessions/<session>/session.json`

NanoBot 继续承担宿主执行层：

- turn 调度
- 模型调用
- WebUI 网关
- slash command 路由
- 设置页与 Apps 页承载

## 3. 当前已落地的宿主接入面

### 3.1 Turn 执行

CoLearn 依赖 NanoBot 的真实 agent runner / loop 链路。

本轮已经确认：

- LEARNING 模式下的 CoLearn system context 会进入真实模型请求消息列表
- hook 执行发生在本轮 `messages_for_model` 计算之前
- hook 上下文已正式带上：
  - `session_key`
  - `session_id`
  - `channel`
  - `chat_id`
  - `user_id`

这保证了学习模式不再停留在“把上下文挂到对象上，但本轮请求没用到”的伪接线状态。

### 3.2 Hook 生命周期

CoLearn 当前依赖 NanoBot 的 hook 生命周期，并按下面顺序接线：

1. `SessionBinderHook`
2. `CoLearnPreflightHook`
3. `BlackboardMonitorHook`
4. `CoLearnFinalizeHook`

其中职责固定为：

- `SessionBinderHook`：绑定当前 CoLearn session
- `CoLearnPreflightHook`：判断 `SessionMode / TurnMode`，并在 `LEARNING` 时注入学习上下文
- `BlackboardMonitorHook`：更新 `blackboard.runtime`
- `CoLearnFinalizeHook`：执行最小写回，不承担学习真相推理主职责

### 3.3 命令入口

本轮 Demo 已经走入 NanoBot 原生命令体系：

- `/learn`
- `/colearn`

它们会同时出现在：

- NanoBot WebUI command palette
- NanoBot slash dispatch 路由

行为定义：

- `/learn <goal>`：正式学习入口，负责创建或继续当前学习 session，并切到学习模式
- `/colearn`：只读看板入口，展示当前 blackboard snapshot

### 3.4 只读 HTTP 数据面

宿主侧已暴露：

- `GET /api/v1/colearn/blackboard/current`
- `GET /api/v1/colearn/graph/current`
- `GET /api/v1/colearn/session/current`
- `GET /api/settings/colearn-apps`

约束：

- 沿用 NanoBot 现有 WebUI / HTTP 鉴权
- 无 active session、无 goal、无 active node 时返回稳定空态
- 不单独引入新安全模型

### 3.5 Apps 页接线

由于 NanoBot 当前 Apps 页主要面向 `cli_apps / mcp_presets`，本轮允许最小宿主扩展。

已经采用的策略：

- 不把 CoLearn 伪装成 CLI app
- 不重写成通用插件框架
- 只新增一个最小 CoLearn app 数据源
- Apps 页只承诺只读展示

Demo 范围内已达成：

- Apps 页能看到 CoLearn
- 可以展开 CoLearn 只读详情
- 可以看到黑板与图谱摘要

## 4. Demo 期稳定项与 fallback

### 4.1 稳定方向

下面这些属于后续也应尽量保持的契约方向：

- CoLearn 真相保留在 `.colearn/`
- NanoBot 负责执行宿主能力
- `/learn` 作为正式学习入口
- `/colearn` 作为只读投影入口
- 学习上下文通过真实模型请求链注入
- 宿主只读 API 供 WebUI / Apps 使用

### 4.2 v0.2.1 务实 fallback

下面这些是本次 Demo 可以接受，但不应被表述成长期稳定平台承诺的部分：

- 通过宿主内部 runtime payload 暴露 CoLearn plugin / session_store / wiki_service
- 对 vendored `third_party/nanobot-0.2.1` 做最小宿主补线
- Apps 页为 CoLearn 增加专用只读数据面
- 运行时安装通过 `enable_for_nanobot()` patch `AgentLoop.from_config()`

## 5. 当前限制

本轮仍然是 Demo 完整版，不是产品完整版。

已知边界：

- WebUI 目前只做只读展示，不做图谱编辑
- 不做 thread toolbar / modal / 多容器切换
- blackboard writeback 目前是最小可判定规则，不是重型学习事件抽取器
- 宿主耦合依然依赖 NanoBot 当前内部结构，后续版本漂移仍需 `colearn_*` 适配层吸收

## 6. 对外陈述建议

当前可以对外准确描述为：

1. CoLearn 能和 NanoBot 一起启动
2. CoLearn 能作为宿主内建接线插件一起响应
3. `/learn` 和 `/colearn` 都在真实宿主命令链路里
4. LEARNING 学习上下文会进入真实模型请求
5. Apps 页能展示 CoLearn 的只读卡片和详情

当前不建议描述为：

1. NanoBot 已拥有完整稳定的通用插件平台
2. CoLearn 已具备完整交互式教学系统 UI
3. 宿主接线已经脱离内部结构依赖
