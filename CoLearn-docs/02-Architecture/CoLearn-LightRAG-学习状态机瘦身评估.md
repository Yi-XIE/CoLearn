# CoLearn LightRAG 与学习状态机瘦身评估

更新时间：2026-05-23

这份文档记录当前 CoLearn 主线里 `LightRAG` 和学习状态机的真实接法，说明它们为什么会显得重，以及可以如何分模式、删减或简化。这里的目标不是把学习能力砍薄，而是把它改成“计划驱动、黑板记录、按需进入”的形态。

目标不是否定这套设计，而是把几个问题讲清楚：

- 现在到底有哪些层在工作
- 重量主要压在哪些地方
- 哪些重量是产品价值，哪些重量是阶段性过度设计
- 如果要改轻，最稳的切法是什么

## 1. 结论先行

当前主线里，真正偏重的不是 `nanobot` 本体，而是 CoLearn 在它上面叠的学习编排层。

现在的系统已经不只是“带一点学习增强的聊天 bot”，而是一个默认把每轮对话都放进学习状态机处理的运行时。`LightRAG` 只是其中最显眼的重组件之一，不是唯一的重来源。

当前最值得做的事情不是继续给状态机加规则，而是先把运行模式切开：

- `Chat Mode`
  - 普通聊天默认走这里
  - 不启用学习状态机主链
  - 不启用 retrieval planning
  - 不显示学习证据 UI
- `Learning Mode`
  - 明确进入学习任务时才启用
  - 先生成学习计划，再打开 `board / turn_mode / blocker / gap / retrieval / writeback`

在 `Learning Mode` 里，建议把学习主链理解成：

- `Plan`
  - 先生成由浅到深的学习计划
  - 明确本轮在讲哪个知识点、下一轮补哪个知识点
- `Board`
  - 像黑板一样记录学习目标、节点状态、证据、异议、待补项
- `Learn / Check`
  - 按计划讲解、复习、核对、出题
- `Writeback`
  - 把这轮学到了什么、没完成什么、用户提出了什么异议写回黑板

如果短期不想切两套模式，也至少要把当前学习模式本身继续瘦一轮，把“每轮必跑”的东西减少。

## 2. 当前 LightRAG 的真实定位

当前 `LightRAG` 在主线里的定位，不是一个独立知识库页，也不是一个偶尔调用的搜索工具，而是学习回合里的背景知识支持层。

相关代码：

- `colearn/retrieval/service.py`
- `colearn/runtime_v2/tooling.py`
- `colearn/app/stages/retrieval.py`

当前已经落地的关键事实：

- `LightRAG` 已改成按需启用，不再是默认常驻工具。
- 默认 provider 已切到 `local`，不再依赖独立 `LightRAG server`。
- 只有符合策略条件的回合才会把 `lightrag` 放进 `enabled_tools`。
- 普通聊天回合已经不再显示“本轮依据”支持卡。

这说明 `LightRAG` 的直接重量已经降了一部分，但学习编排主链本身仍然偏重。

## 3. 当前学习状态机的真实运行链路

### 3.1 核心数据结构

学习状态的核心定义在 `colearn/learning/state.py`：

- `BoardFacts`
  - `current_progress`
  - `student_snapshot`
  - `gaps_and_blockers`
  - `continuation`
  - `evidence_refs`
- `LearningPlan`
  - `goal`
  - `plan_nodes`
  - `current_node_id`
  - `pending_checks`
  - `review_queue`
- `TurnPolicy`
  - `turn_mode`
  - `model_preset`
  - `restrictions`
  - `allowed_tools`
  - `enabled_tools`
- `LearningEvent`
  - 把回合结果转成后续可写回事件

这意味着每一轮都不是简单的“用户消息 -> LLM 回复”，而是“当前学习计划 / 黑板状态 -> 回合策略 -> 回合结果 -> 黑板更新”。

### 3.2 五段式主链

当前主链由 `LearningOrchestrator` 串起来，见 `colearn/app/learning_orchestrator.py`。

顺序如下：

1. `PreflightStage`
   - 取 `session / project`
   - 生成 `board`
   - 生成 `snapshot`
   - 跑 `source_preflight`
2. `PlanStage`
   - 根据用户目标生成由浅到深的学习计划
   - 识别当前知识点、后续知识点、待复习点、待检查点
   - 把计划写入黑板
3. `RetrievalStage`
   - 构建 `retrieval_focus`
   - 构建 `retrieval_reason`
   - 构建 `retrieval_query_context`
   - 预取 `retrieval_bundle`
   - 按计划节点补资料
   - 必要时触发 `web search`
   - 生成 `prompt_support_bundle`
4. `ExecuteStage`
   - 根据 `board` 和 `plan` 算 `turn_policy`
   - 组装 `LearningTurnRequest`
   - 调用 `nanobot`
5. `FinalizeStage`
   - 把 retrieval 结果整理成 `hits / misses / evidence_map`
   - 标准化 `LearningTurnResult`
6. `WritebackStage`
   - 持久化 `board_patch`
   - 更新学习计划节点状态
   - 写回“已讲 / 已检查 / 未完成 / 新异议 / 待补资料”
   - 写入 `memory_events / learning_events`
   - 更新 session/project
   - 触发 compact / consolidate / derive

这条链路意味着，真正进入学习模式后，系统不是单轮问答，而是围绕一个计划和一块持续更新的黑板来推进学习。

### 3.3 当前 turn mode 语义

当前 `turn_mode` 由 `colearn/learning/board_hooks.py` 和 `colearn/learning/turn_hooks.py` 共同驱动，主要模式包括：

- `ANCHOR`
- `CORRECTION`
- `VERIFY`
- `EXPLORE`
- `PAUSED`

这套模式本身没有错，但它的当前用法偏重：

- 模式判断是默认存在的
- 模式会驱动工具、preset、retrieval、writeback
- 模式还会向 UI 和 session 结构继续外溢

## 4. 当前到底重在哪里

### 4.1 不是 LightRAG 单独重，而是整条学习主链都重

`LightRAG` 现在已经按需启用，但 `RetrievalStage` 仍然是每轮必跑。

在 `colearn/app/stages/retrieval.py` 里，即使本轮没有真正启用 `lightrag`，系统仍然会先做这些动作：

- 生成 `retrieval_focus`
- 生成 `retrieval_reason`
- 生成 `retrieval_query_context`
- 生成 `parallel_support` 查询列表
- 组装 `prompt_support_bundle`

也就是说，LightRAG 工具开关变轻了，但 retrieval planning 这层还在默认运行。

### 4.2 每轮都要先被解释成学习回合

当前系统里，用户消息不是先判断“这是普通聊天还是学习任务”，而是直接进入学习状态机，再被分到某个 `turn_mode`。

这会带来两个结果：

- 普通聊天也会被附加学习语义
- 产品会越来越像“学习操作系统”，而不是“轻量聊天助手”

### 4.3 状态写回链过厚

`WritebackStage` 现在不只是保存对话结果，还会做：

- `board_version` 冲突保护
- `board_patch` 持久化
- `memory_events` 写入
- `learning_events` 写入
- `BOARD_PATCH_APPLIED` 事件写入
- 自动 compact
- dream consolidation
- board snapshot derivation

这些能力单看都合理，但叠在每轮主链里就很重。

### 4.4 检索元数据有重复包装

当前 retrieval 信息会在多处传递：

- `TurnContext.retrieval_*`
- `request.metadata["retrieval"]`
- 兼容字段
  - `retrieval_focus`
  - `retrieval_query_context`
  - `retrieval_reason`
  - `prefetched_references`
  - `prompt_support_bundle`
- `runtime_v2.retrieval`

这会提高维护成本，也让“明明没查资料，系统却一直在带着检索语义”这类问题更容易出现。

### 4.5 UI 会继承后端重量

虽然普通聊天那张“本轮依据”卡已经修掉，但前端仍然依赖完整的学习支持结构：

- `prompt_support_bundle`
- `retrieval_hits`
- `retrieval_misses`
- `retrieval_evidence_map`
- `continuation_retrieval_hint`

这意味着只要后端继续默认产出这些结构，前端就会继续被学习模式牵着走。

## 5. 当前哪些重量是值得保留的

不是所有重量都该删。

建议保留的部分：

- `BoardFacts` 作为学习线程的最小长期状态
- `turn_mode` 作为学习场景下的最小控制语义
- `memory` 工具
- `LightRAG` 的按需检索能力
- `LearningEvent` 作为学习写回的统一格式

这些是学习产品真正有差异化价值的部分。

## 6. 当前哪些重量最适合先砍

最适合先砍的不是功能，而是“默认每轮都跑”的编排厚度。

优先级从高到低如下：

1. 普通聊天仍走完整学习状态机
2. `RetrievalStage` 默认每轮必跑
3. `WritebackStage` 默认每轮都做重型后处理
4. retrieval metadata 重复包装
5. 五个 `turn_mode` 的全量语义默认生效

## 7. 新版瘦身方案

当前文档只保留一个新版方案，不再并列维护多个互相竞争的方案。这个方案由四个部分组成：

1. 双模式前端开关
2. 黑板计划
3. 三状态学习状态机
4. Agent 的边界护栏

### 7.1 双模式前端开关

目标：把普通聊天和学习任务明确切开，让学习能力只在需要时展开。

核心规则：

- 默认走 `Chat Mode`
- 用户可以在输入卡里一键打开 `Learning Mode`
- nanobot 识别到明确学习意图时，也可以自主切到 `Learning Mode`
- 一旦进入 `Learning Mode`，前端必须明确提示用户当前已进入学习模式

`Chat Mode` 只保留：

- session messages
- 基础 `memory`
- 必要的 continuation

`Chat Mode` 默认不做：

- `BoardFacts`
- `LearningPlan`
- `turn_mode`
- `RetrievalStage`
- 学习证据 UI

### 7.2 黑板计划

目标：Learning Mode 不是一轮一轮临时发挥，而是围绕一个持续更新的黑板推进。

黑板里至少要有：

- 当前学习目标
- 学习计划节点
- 当前节点
- 已讲节点
- 待复习节点
- 待检查节点
- blocker / 异议
- evidence / 来源
- continuation

推荐链路：

1. 进入 `Learning Mode`
2. 复用 nanobot 原生 `long_task` 记录线程级长期目标
3. 用 `PlanStage` 生成由浅到深的学习计划
4. 把计划写入黑板
5. 根据当前节点准备资料，优先用 `LightRAG`，必要时补 `web search`
6. 讲解、复习、核对、出题
7. 把结果继续写回黑板

这里的原则是：

- 线程级长期目标优先复用 nanobot 原生能力
- 学习内部节点、待办、异议和证据由 CoLearn 黑板维护
- 不为长期目标再重复造一套独立线程任务系统

#### 原生复用哪些

这一层优先复用 nanobot 已有能力：

- `long_task`
  - 记录线程级长期学习目标
- `complete_goal`
  - 关闭或收口当前长期目标
- `/goal`
  - 作为进入长期目标的命令入口
- `goal_state`
  - 复用现有 session metadata 和前端展示
- `web_search`
  - 作为外部公开资料搜索工具
- `web_fetch`
  - 作为具体页面内容读取工具

原生 `plan` 当前只体现为 prompt / quick action 层的交互习惯，不等于结构化学习计划系统。

#### 自己维护哪些

这一层由 CoLearn 自己维护：

- `LearningPlan`
  - 学习节点列表
  - 当前节点
  - review queue
  - pending checks
- `LearningBoard`
  - 已讲 / 待复习 / 待检查
  - blocker / 异议
  - evidence / 来源
  - continuation
- `LEARN / CHECK / PAUSED`
  - 学习过程里的最小状态机
- `PlanStage`
  - 把用户目标展开成由浅到深的学习计划
- `board_patch / plan_patch / writeback`
  - 负责把学习过程正式写回主链

#### 当前不复用的能力

当前没有发现 nanobot 原生提供这些结构化能力，因此不应误判为“已经有现成轮子”：

- 结构化 todo list 数据模型
- 学习节点级状态流转
- 黑板式 blocker / evidence / objection 面板
- 原生 Gantt / timeline 学习计划面板

### 7.3 三状态学习状态机

目标：保留必要学习语义，同时把状态机收成最小可用集合。

只保留三个状态：

- `LEARN`
  - 负责基础讲解、背景介绍、展开理解
- `CHECK`
  - 负责复习、核对、纠错、验证、出题
- `PAUSED`
  - 负责退出学习主链，不继续跑学习编排

状态流转规则：

- 进入学习模式后，默认从 `LEARN` 开始
- 当前节点讲完、用户提出质疑、或系统判断理解不稳时，进入 `CHECK`
- `CHECK` 通过后回到下一个 `LEARN`
- 用户暂停、退出或切回普通聊天时，进入 `PAUSED`

这个三态不再扩回 `ANCHOR / CORRECTION / VERIFY / EXPLORE / PAUSED` 五态，除非后面证明三态不够。

### 7.4 Agent 的边界护栏

目标：把高变化决策交给 Agent，但不让 Agent 把系统带回失控复杂度。

Agent 负责：

- 判断是否进入学习模式
- 生成或更新学习计划
- 决定当前轮是 `LEARN` 还是 `CHECK`
- 决定是否需要 `LightRAG`
- 决定是否需要补 `web search`
- 根据用户反馈调整讲解顺序和计划重点

状态机和黑板负责：

- 保存当前模式
- 保存当前黑板真相
- 控制最小流转规则
- 承接 `board_patch` / `plan_patch`

护栏规则：

- `PlanStage` 不默认每轮都跑，只在首次进入、主题明显变化、或连续卡住时运行
- `web search` 不默认开，只在 `LightRAG` 不足、用户明确要外部来源、或确实需要公开资料时兜底
- `CHECK` 不默认每轮触发，只在节点讲完、用户质疑、或系统判断理解不稳时触发
- Agent 不直接随意改黑板成品，只提交 patch，由主链落盘
- `WritebackStage` 同步只保留最小必要字段，重型后处理异步化

## 8. 实施顺序

### 8.1 第一阶段：切双模式

优先文件：

- `colearn/app/learning_orchestrator.py`
- 线程/会话入口相关 API
- WebUI 对线程模式的入口和展示

动作：

- 增加前端学习模式开关
- 增加线程级模式字段
- 为普通聊天引入轻链路
- 进入学习模式后向前端发出明确状态提示

### 8.2 第二阶段：引入黑板计划

优先文件：

- `colearn/learning/state.py`
- `colearn/app/stages/plan.py` 或等价位置
- `colearn/app/stages/writeback.py`

动作：

- 增加 `LearningPlan`
- 明确 `LearningBoard` 的最小字段
- 接入 nanobot 原生 `long_task / complete_goal / goal_state`
- 复用 nanobot 原生 `web_search / web_fetch`
- 让学习计划和黑板成为学习主链的统一入口

### 8.3 第三阶段：收口成三状态

优先文件：

- `colearn/learning/board_hooks.py`
- `colearn/learning/turn_hooks.py`
- `colearn/app/stages/execute.py`

动作：

- 把五态语义收口为 `LEARN / CHECK / PAUSED`
- 明确状态流转条件
- 调整 `RetrievalStage` 和 `ExecuteStage` 对三态的依赖

### 8.4 第四阶段：加 Agent 护栏

优先文件：

- `colearn/app/stages/retrieval.py`
- `colearn/app/stages/writeback.py`
- `colearn/runtime_v2/tooling.py`

动作：

- 把 `RetrievalStage` 改成条件执行
- 把 `web search` 改成兜底补给层
- 限制 `PlanStage` 的触发频率
- 限制 `CHECK` 的触发频率
- 把重型 writeback 后移

## 13. 最终判断

当前主线的真实问题不是“LightRAG 太重所以不该存在”，而是：

- 学习状态机默认吞掉了所有对话
- retrieval planning 默认进入每轮主链
- 写回和后处理默认挂在每轮执行后
- Learning Mode 的开启方式需要从默认常驻改成可见、可切换、可识别意图的入口

所以真正该收的不是某一个工具，而是默认运行边界。

一句话总结：

`LightRAG` 适合保留为按需能力，学习状态机只在 Learning Mode 里启用；Learning Mode 先出计划，再围绕黑板推进学习，按需调用 `LightRAG` 和 `web search` 补资料，普通聊天则保持轻链路。
