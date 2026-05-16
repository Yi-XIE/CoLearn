# CoLearn 基于 nanobot v0.2.0 的核心替换判断

这份文档回答一个很直接的问题：

**我们是不是可以不做零碎迁移，而是直接以 `nanobot v0.2.0` 作为新的运行时核心，再把 CoLearn 的学习产品层压上去。**

当前结论是：

**可以，而且这条路比“继续维护现有前端套壳 + 自己补齐一套 agent core”更顺。**

但这不是整仓照搬。更准确地说，这是一次**有边界的底座替换**：

- 用 `nanobot v0.2.0` 接管 agent runtime、session loop、provider 编排、WebUI 主界面和打包链路
- 保留 CoLearn 的学习产品定义、知识库组织、项目语义和 LearningState
- 丢掉上游和 CoLearn 里暂时都不服务于当前产品目标的部分

---

## 1. 总判断

如果目标是尽快把 CoLearn 做成一个：

- 前后端一体
- 支持持续目标推进
- 有成熟聊天工作台
- 有更稳的 provider 兜底
- 后续容易打包和交付

那么最优路线已经不是“慢慢把我们当前代码迁到上游思路”，而是：

**直接以 `third_party/nanobot-0.2.0/nanobot-0.2.0` 为新的核心参考实现，逐步让 CoLearn 的主链运行在这套 core 上。**

这会比继续扩写我们当前的自研 runtime 更省力，原因有三点：

1. `nanobot v0.2.0` 已经把 agent loop、goal persistence、provider fallback、WebUI、wheel 打包链路串成一体了。
2. CoLearn 当前最缺的，刚好就是这几个“系统级骨架”，而不是再多一个页面或多一个接口。
3. CoLearn 自己真正有产品价值的部分，本来就不是聊天框本身，而是学习流程、知识组织、学习状态和任务编排。

所以这次不是“我们要不要投降上游”，而是：

**把通用 agent 基建交给更成熟的底座，把 CoLearn 的精力重新集中到学习产品层。**

---

## 2. 直接用

这一组建议直接吸收，不要自己再造一份。

### 2.1 WebUI 主界面与前端工程结构

来源：

- [webui](D:/Colearn-nightly/third_party/nanobot-0.2.0/nanobot-0.2.0/webui)
- [vite.config.ts](D:/Colearn-nightly/third_party/nanobot-0.2.0/nanobot-0.2.0/webui/vite.config.ts)
- [webui/README.md](D:/Colearn-nightly/third_party/nanobot-0.2.0/nanobot-0.2.0/webui/README.md)

建议：

- 直接把 nanobot 的 `webui/` 视为 CoLearn 后续的主工作台前端。
- 现有 `web/` 不再作为长期主线，只保留为过渡参考或临时功能承载。
- 前端主界面的聊天、会话列表、设置面板、流式渲染、goal 展示，全部优先基于 nanobot WebUI 改。

原因：

- 它已经是面向运行时工作台设计的，不是普通网站壳子。
- 它天然和持续目标、流式推理、会话上下文、设置与 provider 配合得更紧。
- 它已经被纳入 wheel 打包链，不需要我们长期背两套前端结构。

### 2.2 Agent runtime 主骨架

来源：

- [loop.py](D:/Colearn-nightly/third_party/nanobot-0.2.0/nanobot-0.2.0/nanobot/agent/loop.py)
- [runner.py](D:/Colearn-nightly/third_party/nanobot-0.2.0/nanobot-0.2.0/nanobot/agent/runner.py)

建议：

- 直接采用 nanobot 的 loop 架构作为新的主执行骨架。
- `AgentLoop.from_config()`、状态机式 `_process_message`、turn 生命周期划分，都应该成为 CoLearn runtime 的默认组织方式。

原因：

- 它已经把恢复、压缩、命令、构建、运行、保存、响应拆成稳定阶段。
- 这比我们继续在当前 `app.py + orchestrator` 上堆条件分支更健康。
- 后续接多目标推进、压缩摘要、失败恢复都会轻松很多。

### 2.3 持续目标机制

来源：

- [builtin.py](D:/Colearn-nightly/third_party/nanobot-0.2.0/nanobot-0.2.0/nanobot/command/builtin.py)
- [long_task.py](D:/Colearn-nightly/third_party/nanobot-0.2.0/nanobot-0.2.0/nanobot/agent/tools/long_task.py)
- [goal_state.py](D:/Colearn-nightly/third_party/nanobot-0.2.0/nanobot-0.2.0/nanobot/session/goal_state.py)

建议：

- 直接采用这套 goal persistence 机制。
- CoLearn 的“当前学习目标”“主任务”“长期推进事项”都应落在这套机制上，而不是另起一套自定义持久目标协议。

原因：

- 它已经解决了压缩、长工具链、模型遗忘、超时延长、前端状态同步这些细节。
- 这是 CoLearn 做“持续学习推进”最需要的基础能力。

### 2.4 Provider fallback 与模型预设

来源：

- [fallback_provider.py](D:/Colearn-nightly/third_party/nanobot-0.2.0/nanobot-0.2.0/nanobot/providers/fallback_provider.py)
- [schema.py](D:/Colearn-nightly/third_party/nanobot-0.2.0/nanobot-0.2.0/nanobot/config/schema.py)

建议：

- 直接采用 `fallback_models` 和模型预设切换方案。
- CoLearn 后面不要自己重写一套 provider 容错层，直接把学习产品配置映射到这套能力上。

原因：

- 真实可用的 agent 系统离不开 provider 兜底。
- 这部分价值在稳定性，不在定制差异。

### 2.5 WebUI 打包进 wheel 的发布方式

来源：

- [hatch_build.py](D:/Colearn-nightly/third_party/nanobot-0.2.0/nanobot-0.2.0/hatch_build.py)
- [pyproject.toml](D:/Colearn-nightly/third_party/nanobot-0.2.0/nanobot-0.2.0/pyproject.toml)

建议：

- 直接借用这套打包思路。
- CoLearn 后续应该走“安装后直接启动工作台”的交付方式，不再长期维持“前端单独运行、后端单独运行、手动配环境”的主路径。

---

## 3. 保留但要改

这一组很值钱，但不能原样照搬。要让它们服务 CoLearn 的学习产品目标。

### 3.1 Session 语义

上游默认语义是“聊天线程”。

CoLearn 需要的是：

- 学习项目
- 学习目标
- 资料库 / source library
- 会话线程
- 任务推进记录

建议：

- 保留 nanobot 的 session 存储与线程组织方式。
- 但要在上层增加 CoLearn 的项目语义映射。
- 一个学习项目可以包含一个或多个聊天线程；goal_state 要和项目主目标关联，而不是只停留在聊天标题层。

### 3.2 WebUI 信息架构

nanobot WebUI 现在很强，但它还是偏“通用个人 agent 工作台”。

CoLearn 需要补进来的不是更多聊天功能，而是学习结构：

- 项目目标
- 知识来源
- 学习状态
- 学习循环节点
- 产出物

建议：

- 保留 WebUI 壳、消息流、设置、侧栏基础结构。
- 在其上扩展 CoLearn 视图，而不是整套推倒重写。
- `Chat` 仍然是主界面，但左侧信息架构要逐步转成“项目 / 资料 / 会话 / 目标”。

### 3.3 Tool 插件架构

来源：

- [loader.py](D:/Colearn-nightly/third_party/nanobot-0.2.0/nanobot-0.2.0/nanobot/agent/tools/loader.py)

建议：

- 保留其自描述工具与插件发现机制。
- 但 CoLearn 的工具集合要以学习任务为中心重新分层。

可保留的方向：

- 通用文件读取
- 网页获取
- 图像生成接口位
- MCP / 外部资源接入方式

要新增的方向：

- 学习计划生成
- 知识点梳理
- 资料入库与检索
- 学具 / 教学产物生成

### 3.4 Auth / bootstrap / settings 协议

nanobot WebUI 依赖自己的 bootstrap、settings、auth 结构。

建议：

- 协议层尽量向 nanobot 靠拢。
- 但设置页里的配置项，要换成 CoLearn 真正在用的 provider、知识库、教学功能配置。

也就是说，保留协议壳，替换业务内容。

---

## 4. 先不要

这一组先不要带进主链，避免项目一下子变重。

### 4.1 多渠道桥接

先不要接管这些为主目标：

- Feishu
- Matrix
- Telegram
- WeCom
- WhatsApp
- DingTalk

原因：

- 这些是 nanobot 作为通用 agent 平台的扩展面。
- CoLearn 当前最重要的是本地工作台和学习闭环，不是消息平台分发。

### 4.2 与当前产品无关的配对 / 审批外延

比如：

- 聊天原生配对
- 私信审批
- 各类频道准入控制

这类机制可以留作以后平台化再看，当前不应拖慢主线。

### 4.3 全量 provider 面铺开

上游加了很多 provider，这很好，但 CoLearn 首期不需要全吃下。

建议只先保留：

- OpenAI 兼容链
- Anthropic 兼容链
- 你当前已经在本地跑通的主 provider
- fallback_models 机制本身

其余 provider 先保留接口位，不做首批产品承诺。

### 4.4 通用个人 agent 品牌内容

nanobot 的很多文案、命令、产品语义是“个人 agent”。

CoLearn 不应该继承这层品牌表达。

我们要保留底层机制，换掉上层叙事。

---

## 5. CoLearn 自己必须保留的东西

底座可以换，产品灵魂不能丢。

这几块应该保留，并迁到新核心上层：

- [LearningState 协议](D:/Colearn-nightly/CoLearn-docs/02-Architecture/CoLearn-LearningState-%E5%8D%8F%E8%AE%AE.md)
- `colearn/learning/*`
- `colearn/app/learning_orchestrator.py`
- `colearn/services` 中与项目、知识库、学习流程直接相关的部分
- 资料库与知识源的产品定义
- 学习循环与学习产出物结构

一句话说：

**runtime 用 nanobot，learning 用 CoLearn。**

---

## 6. 推荐落地方式

### 第一阶段：把 nanobot v0.2.0 变成运行主干

目标：

- 起 nanobot WebUI
- 起 nanobot runtime
- 用最小适配让 CoLearn 的登录、会话、消息流先跑起来

这阶段不追求功能全，只追求主链顺。

### 第二阶段：把 CoLearn 产品语义压上去

目标：

- 把项目 / 知识库 / 学习目标映射进 session 与 goal
- 把 LearningState 注入 runtime context
- 把知识库检索与学习工具接进新 tool 架构

### 第三阶段：逐步淘汰旧壳

目标：

- `web/` 退为过渡代码
- 新主界面完全切到 nanobot WebUI 改造版
- 发布与启动链统一到单一主路径

---

## 7. 最后的判断

如果我们继续维持当前路线，后面会一直重复做这几件辛苦但不构成产品护城河的事：

- 继续补聊天工作台
- 继续补 agent loop
- 继续补 provider 容错
- 继续补发布打包链
- 继续补持续目标机制

这些事 nanobot v0.2.0 已经做到了一个足够高的水位。

所以更值得的选择是：

**把 CoLearn 直接换到 nanobot v0.2.0 这个核心上，再围绕学习产品去雕。**

待确认：真正执行替换时，第一批要落地的是“保留现有 `colearn/` 包名并内嵌 nanobot core”，还是“先单独起一条 `nanobot-core` 主运行线，再把 CoLearn 业务逐步并过去”。这会影响目录策略，但不影响总方向。
