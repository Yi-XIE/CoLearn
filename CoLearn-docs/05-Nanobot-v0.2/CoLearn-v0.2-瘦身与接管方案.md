# CoLearn-v0.2 瘦身与接管方案

这份文档基于一个新的实施判断：

**与其先把 CoLearn 现有后端适配成 nanobot WebUI 的协议形状，不如直接把 `nanobot v0.2.0` 作为主运行线，先做减法，再把 CoLearn 的核心能力接进去。**

也就是说，路线从：

- 先保 CoLearn 现有前后端壳
- 再补 nanobot WebUI 兼容层

切换成：

- 先清掉 `nanobot v0.2.0` 里当前不需要的面
- 直接以它为主运行底座
- 优先把 `LightRAG` 和 CoLearn 学习能力接进去
- `LearningState` 先轻接，状态机后接

这条路的优点很明确：

1. 少一层协议桥接
2. 少一套长期过渡壳
3. 更早站到真正的新底座上
4. 更快让 CoLearn 的知识与学习能力发力

---

## 1. 总体策略

CoLearn-v0.2 现在采用下面这条主线：

**nanobot 做 runtime，CoLearn 做 learning。**

但执行顺序调整为：

1. 先瘦身
2. 再接管
3. 先接知识和检索
4. 再接深层状态机

换句话说：

**先让它成为一个更像 CoLearn 的 nanobot，再让它逐步长成完整的 CoLearn。**

---

## 2. 第一阶段的目标

这一阶段不追求所有产品能力一起落地，只追求一条很清楚的主链：

1. `nanobot v0.2.0` 跑起来
2. WebUI 保留并可直接使用
3. 非核心外围模块先收掉
4. `LightRAG` 接到这套 agent runtime 上
5. 能围绕知识库和检索完成一轮真实对话

做到这里，就已经完成了“底座切换”。

---

## 3. 先清掉什么

这里的“清掉”不一定是马上物理删除，也可以先做：

- 禁用
- 不接入
- 不暴露到配置和 UI
- 从默认启动路径里移开

原则是：**不让它们进入第一阶段主链。**

### 3.1 多渠道桥接

第一批先排除：

- `channels/feishu`
- `channels/matrix`
- `channels/telegram`
- `channels/wecom`
- `channels/whatsapp`
- `channels/dingtalk`
- 以及围绕这些渠道的配套恢复、媒体、群聊线程逻辑

原因：

- CoLearn 当前是本地工作台产品，不是渠道机器人平台
- 这些模块体量大、分支多、测试多，但对当前主目标没有直接收益

建议动作：

- 启动配置里不启用这些 channel
- UI 和 settings 不暴露这些入口
- 文档里明确标记为“暂不接入”

### 3.2 与当前产品无关的配对 / 审批能力

先不纳入主链：

- 聊天原生配对
- 私信审批
- 渠道身份准入

原因：

- 这是平台化能力，不是学习产品主链
- 会分散我们对项目 / 资料 / 学习状态的聚焦

### 3.3 不必要的 provider 面

第一阶段不需要把上游所有 provider 都背进来。

建议保留：

- 当前你本地已经在用、已经跑通的主 provider
- OpenAI 兼容链
- `fallback_models` 机制本身

建议暂缓：

- AWS Bedrock Converse
- NVIDIA NIM
- LongCat
- Atomic Chat
- MiMo
- 以及我们当前没有实际配置、没有实际使用场景的 provider

原因：

- 这些能力以后可以慢慢恢复
- 现在先追求一条最短、最稳、最能交付的运行链

### 3.4 与学习主链无关的命令和 UI 面

建议先收掉或隐藏：

- 不服务学习推进的 slash commands
- 与 CoLearn 目标无关的品牌文案
- 过于通用的个人 agent 引导内容

原因：

- CoLearn 不需要继承 nanobot 的全部人格和叙事
- 先让 UI 聚焦在学习目标、资料、知识和任务推进

---

## 4. 要保留什么

这一组是 CoLearn-v0.2 的底座核心，应该完整保留。

### 4.1 WebUI

保留：

- `webui/`
- 现有聊天壳
- session list
- settings 结构
- 流式展示
- sustained goal 展示

原因：

- 这已经是成熟的工作台外壳
- 没必要再花一次时间自己重新做

### 4.2 Agent loop

保留：

- `AgentLoop.from_config()`
- `_process_message` 状态机组织
- turn 生命周期
- compaction / restore / save / respond 的阶段划分

原因：

- 这是 `v0.2.0` 最有含金量的核心骨架之一

### 4.3 session / goal / stream 模型

保留：

- session 管理方式
- `goal_state`
- `goal_status`
- WebSocket 事件模型
- 与 WebUI 配套的线程视图结构

原因：

- 这部分已经把“持续目标 agent”做通了
- CoLearn 后面正好需要它

### 4.4 packaging 和启动链路

保留：

- WebUI 打进 wheel 的思路
- 统一 gateway / frontend 的启动路径

原因：

- 这是未来交付体验的一部分
- 比“前端一个命令、后端一个命令、再配一堆环境变量”更适合产品化

---

## 5. CoLearn 第一批接管点

这一轮不贪多，优先接最能体现 CoLearn 价值的东西。

### 5.1 LightRAG

这是第一优先级。

原因：

- 它能最直接体现 CoLearn 的知识底盘
- 它比先深改状态机更快产出价值
- 它能立刻让对话不只是聊天，而是“带知识检索的学习对话”

建议接入方式：

1. 先把 `LightRAG` 作为 nanobot tool 接入
2. 让 agent 能在回合中调用检索
3. 让 WebUI 对话能消费检索结果
4. 把 source / knowledge library 的组织逐步挂到这条工具链上

第一阶段不追求：

- 完整知识库管理后台
- 复杂文件同步
- 多种 RAG provider 抽象

先追求：

- 检索能用
- 返回可读
- 能真实辅助学习回合

### 5.2 CoLearn 项目语义

第二优先级。

建议先轻接：

- 项目标题
- 当前学习目标
- source library 关联

先不要一开始就把完整 project management 全压进去。

做法：

- 先把这些信息挂到 session metadata / goal metadata
- 让 UI 先能展示
- 后面再逐步长成完整项目结构

### 5.3 LearningState

第三优先级，但采用“轻接入”策略。

这轮先接：

- `BoardFacts` 的运行时投影
- 关键学习状态摘要注入 runtime context

先不急着全接：

- `TurnPolicy` 的完整状态投影
- `LearningEvent` 的全量闭环写回
- CoLearn 自己再造一层 loop 状态机

原因：

- `v0.2.0` 自己已经有比较成熟的 loop 骨架
- 现在更重要的是验证这套骨架能否承载 CoLearn 的学习上下文

可以把这一步理解为：

**先把 LearningState 当作 agent 的学习记忆层，而不是立刻把它变成新的总控状态机。**

---

## 6. 实施顺序

## 阶段 A：建立瘦身分支

建议新分支：

- `rebase/nanobot-v0.2-slim`

目标：

- 把这条线和现有 CoLearn 主线隔开
- 专门用于“v0.2 瘦身 + 接管”

交付物：

- 分支建立
- 文档路径固定

## 阶段 B：瘦身 nanobot

目标：

- 先让运行面变轻

动作：

1. 关闭不需要的 channel
2. 收掉无关 provider 暴露
3. 精简 settings 中当前不用的配置项
4. 隐藏无关 slash commands 和文案

交付物：

- 一个更聚焦本地工作台的 `v0.2` 运行面

## 阶段 C：接 LightRAG

目标：

- 让知识和检索先进主链

动作：

1. 梳理 CoLearn 现有 `LightRAG` 入口
2. 封装为 nanobot tool
3. 让 runtime 能调用
4. 让 WebUI 对话能看到结果

交付物：

- 一条可工作的知识检索对话链

## 阶段 D：接 CoLearn 项目语义

目标：

- 让 CoLearn 开始有自己的产品结构

动作：

1. 给 session 加 project / source / objective 元数据
2. 把 goal_state 和学习目标挂钩
3. 把 WebUI 侧栏逐步改成 CoLearn 视角

交付物：

- 不再只是通用 agent，而是开始像 CoLearn

## 阶段 E：轻接 LearningState

目标：

- 让学习状态开始影响 runtime

动作：

1. 注入 `BoardFacts`
2. 加入最小学习策略提示
3. 回合结束时做最小状态更新

交付物：

- 学习状态进入主回路

## 阶段 F：再判断状态机深接

目标：

- 决定是否要把 CoLearn 状态机进一步压进 loop

这一步不预设答案，要看前面两件事：

1. `v0.2` loop 是否已经足够承载 CoLearn
2. `LearningState` 轻接入后是否已经达到可用水位

如果足够，就少改。
如果不够，再深接。

---

## 7. 代码层面的接管建议

### 7.1 第一批直接操作的对象

建议优先研究并修改：

- `third_party/nanobot-0.2.0/nanobot-0.2.0/nanobot/agent/*`
- `third_party/nanobot-0.2.0/nanobot-0.2.0/nanobot/session/*`
- `third_party/nanobot-0.2.0/nanobot-0.2.0/nanobot/providers/*`
- `third_party/nanobot-0.2.0/nanobot-0.2.0/webui/*`

### 7.2 第一批从 CoLearn 接过去的能力

建议优先抽：

- `colearn/retrieval/*`
- `colearn/knowledge/*`
- `colearn/sources/*`
- `colearn/learning/state.py`

### 7.3 这一轮先不碰太深的地方

先别急着大动：

- `colearn/api/app.py` 现有整套接口面
- 旧 `web/` 里已有的大量页面逻辑
- 现有自定义统一 WS 协议

原因：

- 这条线已经不是“继续补旧链”
- 现在要避免一边保旧系统，一边改新系统，最后两边都很重

---

## 8. 风险与防守

### 8.1 风险：瘦身不彻底

问题：

- 表面上说不需要，实际上配置、UI、依赖、命令还都在

处理：

- 明确以“默认启动路径里是否出现”为标准

### 8.2 风险：LightRAG 接入位置不对

问题：

- 如果把它接成很外层的旁路功能，后面还得重接

处理：

- 一开始就按 tool / retrieval 能力接入主回合

### 8.3 风险：状态机接太早

问题：

- 容易把 `v0.2.0` 已经成熟的 loop 重新打散

处理：

- 先轻接 LearningState
- 延后深度状态机改造

---

## 9. 当前建议的开工顺序

如果现在就开始干，我建议顺序是：

1. 建 `rebase/nanobot-v0.2-slim` 分支
2. 列清单：哪些 channel / provider / 命令先关掉
3. 跑通最小 `v0.2` 主线
4. 接 `LightRAG`
5. 验证知识检索对话
6. 再把 CoLearn 项目语义压进去
7. 最后再决定状态机深接范围

---

## 10. 结论

这条路线的本质是：

**先把一个成熟的 agent 底盘改瘦、改准，再把 CoLearn 最有价值的能力嫁接进去。**

相比“先维护旧壳，再做 WebUI 协议桥接”，这条路更直接，也更接近最终形态。

当前判断是：

**先瘦身 `v0.2`，先接 `LightRAG`，状态机后接，是更省力也更靠谱的顺序。**
