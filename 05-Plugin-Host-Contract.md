# CoLearn Plugin Host Contract

版本：v0.2 Demo  
宿主基线：NanoBot `v0.2.1` 本地快照  
日期：2026-06-04  
状态：Demo 期务实契约

## 1. 文档定位

这份文档描述的是 CoLearn 在当前 NanoBot 宿主上的最小可用接入契约。

它不宣称 NanoBot 已经提供了一套长期稳定、公开承诺的通用插件平台，而是明确：

- 当前 Demo 真实依赖了哪些宿主接线
- 哪些能力属于稳定方向
- 哪些能力仍是 `v0.2.1` 的务实 fallback

本轮目标是“宿主真实链路可用”，不是“一个只能被外层适配层手动调用的库”。

## 2. 真相边界

CoLearn 的状态真相保留在 `.colearn/`：

- 课程知识真相：`.colearn/wiki/`
- 学习状态真相：`.colearn/state/sessions/<session>/session.json`

NanoBot 继续承担宿主执行层：

- turn 调度
- 模型调用
- WebUI 网关
- slash command 路由
- 线程页与 Apps 页承载

## 3. 当前已落地的宿主接入面

### 3.1 Turn 执行

CoLearn 依赖 NanoBot 的真实 runner / loop 链路。

当前已落地并通过测试验证：

- LEARNING 模式下的 CoLearn system context 会进入真实模型请求
- hook 执行发生在本轮 `messages_for_model` 计算之前
- 普通 CHAT session 不注入学习上下文

这意味着学习模式不再停留在“把上下文挂到对象上，但本轮请求没真正带上”的伪接线状态。

### 3.2 Hook 生命周期

当前 CoLearn hook 顺序为：

1. `SessionBinderHook`
2. `CoLearnPreflightHook`
3. `BlackboardMonitorHook`
4. `CoLearnFinalizeHook`

职责分工：

- `SessionBinderHook`：绑定当前 CoLearn session
- `CoLearnPreflightHook`：判断 `SessionMode / TurnMode`，并在 `LEARNING` 时注入学习上下文
- `BlackboardMonitorHook`：更新 `blackboard.runtime`
- `CoLearnFinalizeHook`：执行最小写回，不承担重型学习状态推理

### 3.3 命令入口

本轮 Demo 已接入 NanoBot 原生命令体系：

- `/learn`
- `/colearn`

它们会同时出现在：

- NanoBot WebUI command palette
- NanoBot slash dispatch 路由

行为定义：

- `/learn <goal>`：正式学习入口，负责创建或继续当前 session，并切到学习模式
- `/colearn`：只读看板入口，展示当前 blackboard snapshot

### 3.4 只读 HTTP 数据面

宿主当前暴露：

- `GET /api/v1/colearn/blackboard/current`
- `GET /api/v1/colearn/graph/current`
- `GET /api/v1/colearn/session/current`
- `GET /api/settings/colearn-apps`

约束：

- 复用 NanoBot 当前 WebUI / HTTP 鉴权
- 没有 active session、没有 goal、没有 active node 时返回稳定空态
- 不额外引入新安全模型

### 3.5 前端承载

当前前端是务实双轨：

1. `Settings > Apps` 中存在 CoLearn 只读条目，承担发现和演示入口
2. 聊天线程页中存在 CoLearn 主入口，承担真实使用路径

当前线程内行为：

- `ThreadComposer` 附近有 `CoLearn` 按钮
- 打开后不是覆盖式抽屉，而是线程页右侧并排栏
- 线程主区与 CoLearn 栏按约 `6:4` 分栏
- 右栏承载只读学习摘要、黑板状态与图谱摘要

这意味着前端主入口已经从“只在 Apps 页里打开”迁移到“在真实聊天路径里同屏查看”。

## 4. Demo 期稳定项与 fallback

### 4.1 稳定方向

下面这些属于后续也应尽量保持的契约方向：

- CoLearn 真相保留在 `.colearn/`
- NanoBot 负责宿主执行能力
- `/learn` 是正式学习入口
- `/colearn` 是只读查看入口
- 学习上下文通过真实模型请求链注入
- 宿主只读 API 供 WebUI / Apps 使用
- 聊天线程页是 CoLearn 的主交互路径

### 4.2 v0.2.1 务实 fallback

下面这些是本次 Demo 可接受，但不应描述成长期平台承诺的部分：

- 通过宿主内部 runtime payload 暴露 CoLearn plugin / session_store / wiki_service
- 对 vendored `third_party/nanobot-0.2.1` 做最小宿主补线
- Apps 页为 CoLearn 增加专用只读数据面
- 运行时通过 `enable_for_nanobot()` patch `AgentLoop.from_config()`

## 5. 当前限制

本轮仍是 Demo 完整版，不是产品完整形态。

已知边界：

- WebUI 当前只做只读展示，不做图谱编辑
- 不做 thread toolbar、多容器切换、图谱拖拽编辑
- blackboard writeback 仍是最小可判定规则，不是重型学习事件抽取器
- 宿主耦合仍依赖 NanoBot 当前内部结构，未来版本升级仍需要 `colearn_*` 适配层吸收变化

## 6. 对外表述建议

当前可以准确描述为：

1. CoLearn 可以和 NanoBot 一起启动
2. CoLearn 可以作为宿主内建接线插件一起响应
3. `/learn` 和 `/colearn` 已进入真实宿主命令链
4. LEARNING 学习上下文会进入真实模型请求
5. 聊天线程页可同屏打开 CoLearn 右侧只读栏
6. Apps 页可作为 CoLearn 的次入口与演示入口

当前不建议描述为：

1. NanoBot 已拥有稳定通用插件平台
2. CoLearn 已具备完整交互式教学系统 UI
3. 宿主接线已经完全脱离内部结构依赖
