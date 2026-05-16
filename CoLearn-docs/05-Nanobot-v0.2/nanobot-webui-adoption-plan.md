# CoLearn 直接采用 nanobot WebUI 的接入方案

本文确认一个明确决策：

**CoLearn 后续前端主基座，不再以当前 `web/` 为长期唯一方向，而是直接采用 `nanobot v0.2.0` 的 `webui/` 作为主前端基础。**

这不是“参考一下设计”，而是：

- 前端优先复用 `nanobot/webui`
- CoLearn 后端去适配必要协议
- 现有 `web/` 作为过渡层和功能参照

## 1. 为什么直接用它

这次不是单纯因为它好看，而是因为它已经把几个最难的前端结构问题做成了：

- WebUI 已经能打进 wheel
- 开发态和发布态路径清楚
- WebSocket + REST 共用一个 gateway
- 聊天主界面、会话列表、设置页、BYOK、流式推理展示都已经成型
- 目标状态 `goal_status` 和 `goal_state` 已经进了前端状态流

对 CoLearn 来说，这相当于有人已经把“一个个人 AI 工作台前端”最重的那一半打磨完了。

## 2. 这意味着什么

### 不是整仓替换

我们不是把 CoLearn 的产品定义也替换成 nanobot。

我们要做的是：

- 采用 nanobot 的 WebUI 作为前端壳和主交互骨架
- 把 CoLearn 的学习工作流、项目、知识库、LearningState、记忆结构接进去

### 不是保留双主线太久

当前 `web/` 还会继续存在一段时间，但它更适合承担两个角色：

- 过渡期联调与功能验证
- CoLearn 专属页面结构的参照来源

长期看，主前端应该收敛到一套，而不是两套。

## 3. 代码事实

### nanobot WebUI 已经是可用产品壳

关键入口：

- [App.tsx](D:/Colearn-nightly/third_party/nanobot-0.2.0/nanobot-0.2.0/webui/src/App.tsx)
- [api.ts](D:/Colearn-nightly/third_party/nanobot-0.2.0/nanobot-0.2.0/webui/src/lib/api.ts)
- [bootstrap.ts](D:/Colearn-nightly/third_party/nanobot-0.2.0/nanobot-0.2.0/webui/src/lib/bootstrap.ts)
- [useNanobotStream.ts](D:/Colearn-nightly/third_party/nanobot-0.2.0/nanobot-0.2.0/webui/src/hooks/useNanobotStream.ts)
- [useSessions.ts](D:/Colearn-nightly/third_party/nanobot-0.2.0/nanobot-0.2.0/webui/src/hooks/useSessions.ts)
- [SettingsView.tsx](D:/Colearn-nightly/third_party/nanobot-0.2.0/nanobot-0.2.0/webui/src/components/settings/SettingsView.tsx)

### 它当前依赖的后端协议

它主要依赖这些面：

- `/webui/bootstrap`
- `/api/sessions`
- `/api/sessions/{key}/webui-thread`
- `/api/settings`
- `/api/settings/update`
- `/api/settings/provider/update`
- `/api/settings/web-search/update`
- WebSocket 流式事件
- `goal_status`
- `goal_state`
- `auth`

### CoLearn 现在已有的协议面

CoLearn 当前已有：

- [app.py](D:/Colearn-nightly/colearn/api/app.py)
- `/api/v1/projects`
- `/api/v1/sessions`
- `/api/v1/ws`
- `/api/v1/auth/*`
- `/api/v1/knowledge/*`
- `/api/v1/settings/tests/*`

这说明一个现实：

**我们不是没有后端，而是协议形状不同。**

## 4. 接入策略

### 方案原则

前端不大改，后端做适配层。

也就是说，我们优先保住 nanobot WebUI 这些成熟部分：

- 会话列表
- 聊天线程壳
- 流式内容处理
- 推理内容显示
- 设置页基本框架
- bootstrap + auth 流

然后让 CoLearn 后端补这些适配能力：

- nanobot 风格的 session 列表响应
- webui-thread 历史快照响应
- bootstrap 入口
- settings 响应形状
- goal 状态事件

### 不建议的路线

不建议直接把 nanobot WebUI 全面改成调用 CoLearn 当前所有 `/api/v1/*`。

原因是那会让我们一边改前端，一边改协议，一边保留旧页面，最后变成双倍工作量。

更好的路线是：

- 用 nanobot WebUI 期待的协议面作为目标
- CoLearn 后端向这个目标靠拢

## 5. 能直接保留的前端部分

这些基本可以直接保留：

- `App.tsx` 的壳结构
- `useNanobotStream.ts` 的流式处理主逻辑
- 会话列表与分组 UI
- 设置页主框架
- auth/bootstrap 体验
- `goal_status` 的运行态展示
- 图片预览与流内附件展示链

## 6. 必须由 CoLearn 替换或扩展的部分

### 会话模型

nanobot 的会话键是 `websocket:chat-x` 风格。

CoLearn 有自己的：

- `project_id`
- `session_id`
- `LearningState`
- `knowledge_bases`

所以我们需要一个适配层，把 CoLearn session 映射成 WebUI 能理解的会话摘要。

### 历史线程快照

nanobot WebUI 依赖 `/api/sessions/{key}/webui-thread`。

CoLearn 当前还没有这条现成路由，所以我们需要补：

- 消息历史
- 推理内容
- tool/use 状态
- 附件和知识引用
- 当前活动目标状态

### 设置页内容

nanobot 的 Settings 更偏 provider / BYOK / web search。

CoLearn 需要的 Settings 还包括：

- 联调测试事件流
- 学习模式相关配置
- 知识库 / retrieval 相关项

所以 settings 框架可保留，内容要重组。

### 知识库与项目空间

nanobot WebUI 默认是“聊天为中心”。

CoLearn 还有：

- 项目
- source library
- knowledge files
- learning review

这些需要作为新视图或侧栏能力加回去，而不是指望 nanobot 原生已经有。

## 7. 推荐实施顺序

### 第一阶段：跑通壳

目标：

- 把 nanobot `webui/` 单独跑起来
- 先让它能连上 CoLearn 后端
- 至少显示 auth、session list、chat thread 壳

需要做：

- 新建 CoLearn 兼容 bootstrap 接口
- 新建 CoLearn 兼容 session list 接口
- 新建 CoLearn 兼容 webui-thread 接口

### 第二阶段：接通主聊天链

目标：

- WebUI 能通过 CoLearn WS 收发消息
- 推理流和内容流能正确渲染
- goal 状态事件能显示

需要做：

- 统一 WS 事件形状适配
- 历史回放和实时流合并
- 目标状态同步

### 第三阶段：把 CoLearn 特性放回去

目标：

- 项目
- 知识库
- LearningState
- 记忆面板

这些能力重新作为 CoLearn 专属层进入主前端。

### 第四阶段：一体化打包

目标：

- 前端 build 产物进入 Python 包
- FastAPI 或网关统一静态托管
- `pip install` 后即可直接开工作台

## 8. 当前建议

这条路线我支持，而且建议尽快开始。

不是因为它省事，而是因为它更接近我们真正想要的形态：一个一体化、可发布、可持续推进学习任务的工作台。

当前最合适的下一步不是讨论“要不要”，而是直接开始：

1. 建一条 `nanobot-webui-adapt` 工作线
2. 先跑通 bootstrap + sessions + thread snapshot
3. 让 WebUI 和 CoLearn WS 第一次真正握手

## 9. 一句话判断

**我们应该直接用 nanobot 的 WebUI，但产品灵魂仍然是 CoLearn。**
