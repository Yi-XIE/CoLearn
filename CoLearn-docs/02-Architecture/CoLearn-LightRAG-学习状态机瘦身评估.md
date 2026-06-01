# CoLearn LightRAG 与学习状态机瘦身评估

更新时间：2026-05-30

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

## 2. 当前现状结论

这一段只保留会影响新版方案的结论，不继续展开旧链路细节，避免把历史实现方式重新固化成后续设计前提。

当前需要记住的结论只有这些：

- `LightRAG` 的合理定位是学习过程中的背景知识支持层，不是独立页面，也不是普通聊天默认常驻工具。
- 当前真正偏重的来源，不是某一个工具，而是学习编排主链过早、过厚地介入了所有对话。
- 普通聊天和学习任务的边界还不够清楚，所以系统会把太多普通对话解释成学习回合。
- 线程级长期目标和外部检索已经有 nanobot 原生能力可复用，不需要重复造轮子。
- 学习内部的计划、黑板、节点状态、异议、证据，当前仍然需要 CoLearn 自己维护。

## 3. 当前最重的地方

现阶段最影响系统轻重的，不是功能数量，而是默认运行边界。主要问题集中在：

- 普通聊天仍然容易被带进学习语义。
- retrieval planning 仍然倾向于在主链里提前发生。
- writeback 同步路径仍然偏厚。
- retrieval 元数据和 UI 依赖面偏宽。
- Agent 如果没有护栏，会把新的复杂度重新带回来。

## 4. 哪些能力值得保留

新版方案里，建议明确保留这些能力：

- `Chat Mode / Learning Mode` 的双模式边界
- `LightRAG` 的按需检索能力
- nanobot 原生 `long_task / complete_goal / goal_state`
- nanobot 原生 `web_search / web_fetch`
- CoLearn 自己的 `LearningPlan / LearningBoard`
- `LEARN / CHECK / PAUSED` 三状态学习状态机
- 最小必要的 evidence、continuation 和 writeback

这些能力构成的是“轻入口 + 强学习”的骨架，不建议再回到“默认所有对话都走完整学习链”的做法。

## 5. 哪些重量应该先砍

优先砍掉的是默认主链上的厚度，而不是学习能力本身：

1. 普通聊天默认进入学习主链
2. retrieval 默认每轮提前展开
3. 重型 writeback 默认同步执行
4. retrieval 元数据重复暴露
5. 没有触发条件和护栏的 Agent 自主决策

## 6. 文档约束

为了避免旧实现细节影响后续 Agent 思考，这份文档从这里开始只保留：

- 影响设计边界的结论
- 必须复用的原生能力
- 必须自维护的学习结构
- 新版方案和实施顺序

不再继续展开旧版链路的逐段实现说明，除非后面某个开发任务确实需要单独补专题文档。
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

这个三态不再扩回更细的历史状态集合，除非后面证明三态不够。

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

## 12. Coding Plan

下面这份计划是后续施工的唯一编码清单。目标不是一次性做完所有增强，而是先把新版学习模式骨架搭稳，再逐步补齐。

### 12.0 当前施工进度

更新于 2026-05-30。

瘦身方案（双模式 + 黑板计划 + 三状态 + Agent 护栏）已全部落地，并在三态学习状态机之上又叠了一层粗粒度的 **Learning Phase**，把学习闭环补成了“进来 → 摸底 → 学 → 收尾 → 回访”的完整路径。

已落地：

- **双模式入口**：session/project 支持 `chat` 与 `learning`，普通聊天默认轻链路，Learning Mode 可由前端开关或明确学习意图（`PreflightStage` 关键词检测）进入。
- **黑板计划**：`LearningPlan`、`LearningBoard`、`LearningPlanNode` 已进入 `BoardFacts`，并兼容旧会话字段自动派生。`PlanStage` 首次进入或换题时生成计划（有 LightRAG 时按课程结构生成，否则四步模板），已有计划不每轮重算，并按 mastery 跳过已掌握节点。
- **三状态学习状态机**：Learning Mode 从 `LEARN` 开始，普通聊天为 `PAUSED`，检查/纠错收口到 `CHECK`，旧五态只在读取历史会话时归一化。
- **retrieval 护栏**：首次学习取证，已有 evidence 的 `LEARN` 后续轮跳过预取；`web_search / web_fetch` 作兜底层按需启用。
- **writeback 与后处理收口**：Chat Mode 不调度学习型后台压缩、dream consolidation 和 board derivation；Learning Mode 保留必要异步后处理与 stale write 防护。
- **nanobot 原生能力**：`long_task / complete_goal / goal_state` 长期目标生命周期、`AgentHook` 真流式、`set_model_preset`、`ContextBuilder`、`AutoCompact`、`Dream` 均已接入。
- **前端黑板展示**：Learning support 侧栏消费 `learning_plan` 与 `learning_board`，并有 `ModeIndicator` / `MasteryProgress` / `PlanConfirmCard` / `SessionSummaryCard` / `IntakeQuestionnaireCard` 等组件。

#### Learning Phase 层（三态之上的新增）

在 `LEARN / CHECK / PAUSED` 之上，`colearn/learning/constants.py` 定义了 `LearningPhase`，由 `PreflightStage._resolve_learning_phase()` 判定、`turn_hooks.policy()` 分发：

- `INTAKE` — 新用户无 profile 时先做画像采集（`skills/profile-intake`）
- `DIAGNOSE` — 出诊断题评估基线，只问不教
- `READY` — 正常学习主链（默认）
- `REFLECT` — 会话收尾生成总结（`skills/session-reflect`），计划全部完成时自动触发
- `RECALL` — 用户回访且召回到期时先复习（`skills/schedule-recall`）

配套技能目录（`skills/`）：`profile-intake`、`session-reflect`、`schedule-recall`、`web-search`，以及教学法技能 `pedagogy-methods` / `socratic-questioning` / `feynman-technique` / `deliberate-practice`。

当前状态：

- 瘦身方案本身已收口；本轮在其上补完了 Learning Phase 闭环与配套 skills。
- 下方 7~13 节是设计依据与实施顺序的原始记录，保留作为背景，不再逐条对照当前代码。

### 12.1 总目标

完成一个新的 Learning Mode 主链，使其满足以下条件：

- 普通聊天默认不进入学习主链
- 用户可在前端一键进入 Learning Mode
- nanobot 可在明确学习意图下自主切入 Learning Mode
- 线程级长期目标复用 nanobot 原生 `long_task / complete_goal / goal_state`
- 学习内部计划和黑板由 CoLearn 自己维护
- 学习状态机收口为 `LEARN / CHECK / PAUSED`
- `LightRAG` 保留为按需背景知识能力
- `web_search / web_fetch` 作为外部资料补给层按需触发
- Agent 决策必须有明确边界护栏

### 12.2 交付范围

本轮编码范围必须覆盖：

- 前端学习模式开关与状态提示
- 后端线程模式识别与路由
- Learning Mode 主链的最小可运行版本
- `LearningPlan` 与 `LearningBoard` 的最小数据结构
- nanobot 原生 `long_task` 集成
- `LEARN / CHECK / PAUSED` 三状态流转
- 按需 `LightRAG` 与按需 `web_search`
- writeback 最小化与异步后处理边界
- 基础测试、回归测试、前端显示验证

本轮不要求交付：

- 原生 Gantt / timeline 面板
- 完整的学习统计报表
- 复杂多课程管理
- 自动知识图谱可视化

### 12.3 Phase 1：双模式入口与线程模式

目标：先把 Chat Mode 和 Learning Mode 真正切开。

后端任务：

- 在线程或 session 级别增加 `mode` 字段，至少支持 `chat` 和 `learning`
- 增加统一入口判断逻辑：收到请求时先判断当前线程模式
- 补一个明确学习意图检测层，用于触发自动切入 Learning Mode
- 保证自动切入发生时会产出可供前端消费的状态信号
- 普通聊天线程默认不构建学习主链上下文

前端任务：

- 在输入卡中增加“学习模式”一键开关
- 增加当前线程模式显示
- Learning Mode 进入时显示清晰提示，不要隐式切换
- 支持用户手动退出 Learning Mode 回到 Chat Mode
- 保证切换后 UI 不残留旧的学习证据面板状态

验收标准：

- 普通聊天线程不进入学习主链
- 用户手动开关 Learning Mode 生效
- Agent 自动切换 Learning Mode 时前端可见
- 切回 Chat Mode 后学习 UI 收起

### 12.4 Phase 2：接入 nanobot 原生 Goal 能力

目标：不自造线程级长期目标系统，直接复用 nanobot 原生能力。

任务：

- 在进入 Learning Mode 且用户目标明确时，调用 nanobot 原生 `long_task`
- 学习结束、取消、话题切换时，正确调用 `complete_goal`
- 把 `goal_state` 纳入 CoLearn 的线程状态读取层
- 前端显示当前长期学习目标摘要
- 处理已有 active goal 时的替换和收口逻辑
- 确保 Learning Mode 不会重复注册多个冲突目标

验收标准：

- 一个学习线程同一时间只有一个 active goal
- goal 能跨 turn 保持可见
- complete/cancel/supersede 三类结束路径都能正确落盘

### 12.5 Phase 3：LearningPlan 与 LearningBoard 最小模型

目标：建立学习内部结构，但只保留最小必要字段。

建议最小数据结构：

- `LearningPlan`
  - `goal`
  - `plan_nodes`
  - `current_node_id`
  - `review_queue`
  - `pending_checks`
- `LearningBoard`
  - `current_progress`
  - `completed_nodes`
  - `blockers`
  - `objections`
  - `evidence_refs`
  - `continuation`

任务：

- 在 `colearn/learning/state.py` 中增加或收口以上结构
- 定义 plan node 的最小 schema，避免后期随手塞字段
- 明确哪些字段是 session 主事实，哪些字段是 result 衍生块
- 定义 `board_patch` 和 `plan_patch` 的最小增量格式
- 保证这些结构对前端是稳定可消费的

验收标准：

- 学习计划可以表示“要学什么、现在学到哪”
- 黑板可以表示“讲过什么、卡住什么、下一步是什么”
- patch 结构可单独写回，不需要整块覆盖

### 12.6 Phase 4：PlanStage

目标：让学习任务先产出计划，再开始讲解。

任务：

- 新增 `PlanStage`，位置可在 `PreflightStage` 之后
- 只有在这些情况下运行 `PlanStage`：
  - 首次进入 Learning Mode
  - 学习主题明显变化
  - 连续卡住，需要重排计划
- 生成由浅到深的 plan node 列表
- 标记当前节点、后续节点、待复习节点、待检查节点
- 计划生成后立即写入 `LearningPlan` 与 `LearningBoard`
- 计划不允许每轮全量重算，除非满足重排条件

验收标准：

- 用户说“我想学一个决策树”时能先得到结构化计划
- 非必要情况下不会每轮重做计划
- 用户提出新异议后可以局部调整计划

### 12.7 Phase 5：三状态学习状态机

目标：把旧五态收口为 `LEARN / CHECK / PAUSED`。

任务：

- 在 `board_hooks` / `turn_hooks` 中实现三态判定
- 明确 `LEARN -> CHECK` 的触发条件：
  - 当前节点讲完
  - 用户提出质疑
  - 系统判断理解不稳
- 明确 `CHECK -> LEARN` 的回切条件：
  - 当前检查通过
  - 当前节点完成，切到下一个节点
- 明确进入 `PAUSED` 的条件：
  - 用户暂停
  - 用户退出学习模式
  - 线程切回普通聊天
- 清理旧五态在新主链中的默认依赖

验收标准：

- 当前学习回合总能落到三态之一
- 不再要求所有旧五态语义继续默认生效
- 前端能够正确显示当前三态

### 12.8 Phase 6：RetrievalStage 收口

目标：把检索改成按需发生，而不是主链默认全开。

任务：

- 先判定当前状态和当前节点，再决定是否做 retrieval
- 优先使用 `LightRAG` 提供背景材料和证据
- 只有在这些情况下补 `web_search / web_fetch`：
  - `LightRAG` 不足
  - 用户明确要外部来源
  - 当前节点需要公开资料或最新资料
- 把 retrieval 元数据收口到单一主入口，避免多处重复镜像
- 不需要 retrieval 的回合返回最小 context

验收标准：

- 普通聊天不触发 Learning retrieval
- Learning Mode 里 retrieval 只在有需要时触发
- `web_search` 成为兜底层而不是默认层

### 12.9 Phase 7：Writeback 最小化

目标：让同步主链只承担最小必要写回。

任务：

- 同步写回只保留：
  - session messages
  - final_text
  - 最小 continuation
  - `board_patch`
  - `plan_patch`
  - 最小 evidence refs
- 把这些后处理后移或异步化：
  - consolidation
  - derivation
  - compression
  - 非关键事件归档
- 保留 stale write 防护
- 保证 patch 写回失败时不会把整块状态冲掉

验收标准：

- 学习线程同步延迟明显下降
- patch 写回比全量覆盖更稳定
- 后处理失败不影响主链结果可见性

### 12.10 Phase 8：前端黑板与学习展示

目标：让用户能看见计划、进度和当前状态，但不做过重 UI。

任务：

- 增加 Learning Mode 状态条
- 增加黑板最小展示区，显示：
  - 当前目标
  - 当前节点
  - 已讲节点
  - 待检查节点
  - blocker / 异议
- 增加 goal_state 摘要展示
- 区分 Chat Mode 与 Learning Mode 的面板差异
- 不实现复杂 Gantt，避免 UI 先走太远

验收标准：

- 用户能一眼知道当前是不是学习模式
- 用户能一眼知道现在学到哪
- 用户能一眼知道下一步是讲解还是检查

### 12.11 Phase 9：测试与回归

后端测试：

- 模式切换测试
- `long_task / complete_goal` 集成测试
- `LearningPlan / LearningBoard` patch 测试
- 三状态流转测试
- 条件 retrieval 测试
- writeback 最小化测试
- HTTP pause 完成 native goal 测试
- WebSocket cancel 完成 native goal 测试
- WebSocket `execute_turn` 输出 `goal_state` 帧测试
- 话题切换触发 replan 与新 native goal 同步测试

前端测试：

- 输入卡 Learning Mode 开关测试
- goal_state 展示测试
- 黑板面板展示测试
- 模式切换后 UI 收敛测试

人工验证：

- “我想学一个决策树”完整走通一遍
- 普通聊天线程不误入学习模式
- 用户中途质疑、暂停、退出、换题都能正确收口

### 12.12 实施纪律

- 不额外新造线程级任务系统
- 不把 `web_search` 做成默认常驻
- 不把黑板做成大而全的课程系统
- 不在本轮实现原生 Gantt 替代品
- 每完成一个 Phase 都要补测试和文档回写
- 如果中途发现字段膨胀，优先收口 schema 再继续功能开发

## 13. 最终判断

当前主线的真实问题不是“LightRAG 太重所以不该存在”，而是：

- 学习状态机默认吞掉了所有对话
- retrieval planning 默认进入每轮主链
- 写回和后处理默认挂在每轮执行后
- Learning Mode 的开启方式需要从默认常驻改成可见、可切换、可识别意图的入口

所以真正该收的不是某一个工具，而是默认运行边界。

一句话总结：

`LightRAG` 适合保留为按需能力，学习状态机只在 Learning Mode 里启用；Learning Mode 先出计划，再围绕黑板推进学习，按需调用 `LightRAG` 和 `web search` 补资料，普通聊天则保持轻链路。
