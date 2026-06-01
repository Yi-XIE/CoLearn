# CoLearn 学习闭环版本设计

> **实现现状（2026-05-30）**
>
> 这份文档是学习闭环的**产品愿景**，保留作为方向参考。实际落地时结构与命名做了收敛，与本文不完全一致：
>
> | 本文设想 | 实际落地 |
> |---|---|
> | `LearningMap` / `LearningMapNode` | `LearningPlan` / `LearningPlanNode`（`colearn/learning/state.py`），由 `PlanStage` 生成 |
> | `ConceptCard` | 暂未独立建模；概念掌握度落在 `StudentSnapshot.mastery_level` + `MasteryProgress` 组件 |
> | `StudyContinuity` | 拆成 session 上的 `continuation` / `next_recall` / `profile` 字段 + `schedule-recall` 技能 |
> | “开始学习这个资料库”入口 | 由双模式开关（Chat/Learning）+ 学习意图检测进入 Learning Mode |
> | 每轮课后沉淀 | `REFLECT` phase + `session-reflect` 技能 + `SessionSummaryCard` 组件 |
> | 下次继续入口 | `RECALL` phase + `next_recall` + 前端召回引导 |
>
> 也就是说“持续陪学”的主体验已经通过 **双模式 + 五段 Learning Phase + 黑板计划 + 配套 skills** 实现，只是没有按本文的 `LearningMap / ConceptCard / StudyContinuity` 三结构原样落地。详见 `02-Architecture/CoLearn-LearningState-协议.md`。
>
> 本文以下内容是当初的设计意图，作为后续打磨“资料库级学习地图 / 概念卡复习”的北极星保留。

---

## 一句话目标

下一阶段不再优先扩散功能，而是把知识库、记忆、技能、检索和学习状态收束到一条主路径里：

> 资料进入 CoLearn 后，系统自动把它变成一个可继续学习的项目。

这个版本的重点不是让用户看到“这里有很多功能”，而是让用户形成一个稳定感受：

> 我把资料交给 CoLearn，它真的会陪我学，记得我学到哪里，并帮我形成下一次可以继续的结构。

## 产品判断

CoLearn 当前已经有知识库、对话、记忆、技能、检索和学习状态等能力，但这些能力如果只是并排存在，用户会感觉它是一个“带知识库的聊天工具”。

下一阶段要做的事情，是把这些能力组织成一个学习闭环：

1. 资料进入系统。
2. 系统生成学习地图。
3. 用户围绕资料进入学习对话。
4. 每轮对话后自动沉淀学习结果。
5. 下次回来时，系统能明确接住上次的进度，并给出下一步。

这样 CoLearn 的产品辨识度才会真正立起来：它不是只回答问题，而是持续陪用户学习一组资料。

## 第一版体验路径

### 1. 选择资料库

用户进入知识花园后，不只是看到文件、图谱和知识条目，还能看到一个清晰入口：

```txt
开始学习这个资料库
```

这个入口的含义是：把当前资料库从“可检索内容”提升为“可持续学习项目”。

第一版不需要支持复杂的多库组合，可以先限定为：

- 一个知识库
- 一个学习地图
- 一个学习会话
- 一个课后沉淀面板

先让闭环跑通，再扩展资料类型、图谱表达和学习策略。

### 2. 生成学习地图

CoLearn 自动从资料库中提炼一份 `LearningMap`，让用户知道这组资料可以怎样学。

学习地图第一版需要包含：

- 核心概念
- 推荐学习顺序
- 已掌握区域
- 待理解区域
- 易混淆区域
- 关键资料引用

学习地图不应该只是静态目录。它应该成为后续学习对话、复习卡片和继续建议的共同依据。

### 3. 进入学习对话

用户从学习地图进入对话后，对话不再是普通问答，而是“带证据的学习对话”。

第一版要求：

- 回答尽量带来源依据。
- 界面能显示“引用了哪些资料”。
- 用户可以展开看到“这句话来自哪个片段”。
- 如果没有足够证据，回答要明确说明依据不足。

这一步的关键体验是让用户感觉：CoLearn 不是在泛泛聊天，而是真的陪自己读资料。

### 4. 每轮学习后自动沉淀

每轮学习结束后，系统自动生成一次学习沉淀。

沉淀内容包括：

- 今日学到了什么
- 新概念卡
- 待复习问题
- 薄弱点
- 下次继续建议

这部分不应该要求用户手动整理。用户只负责学习，CoLearn 负责把学习过程变成可继续的结构。

### 5. 下次回来继续

用户下次回到首页或资料库页时，CoLearn 应直接显示继续学习所需的信息：

- 上次学到哪里
- 建议下一步
- 待复习卡片
- 可以继续的学习任务

这一步决定了产品是否真正形成“持续陪学”的感觉。如果用户每次回来都要重新解释自己学到哪里，闭环就断了。

## 三个关键界面

### 知识库学习首页

这是资料库进入学习状态后的主入口。

页面应展示：

- 学习地图
- 当前进度
- 推荐下一步
- 待复习概念卡
- 最近一次学习总结
- 进入学习对话的入口

这个页面不应该做成普通文件列表的增强版，而应该是“这个资料库现在学到什么状态”的总览。

### 带证据的学习对话

这是用户实际学习发生的地方。

界面重点：

- 主对话区域保持轻量，不被引用信息压垮。
- 回答旁边或回答下方可以展开证据来源。
- 证据来源能回到资料片段。
- 对话过程中可以看到当前学习目标或当前概念节点。

第一版可以先实现“回答引用列表 + 片段展开”，不必一开始就做复杂的逐句引用图谱。

### 课后沉淀面板

这是每轮对话结束后的学习整理区。

面板展示：

- 本轮学习总结
- 新增概念卡
- 复习题
- 薄弱点
- 下次计划

它的定位不是报告页，而是下一次学习的准备材料。

## 三个后台结构

### LearningMap

`LearningMap` 是资料库级学习地图。

建议第一版字段：

```ts
interface LearningMap {
  id: string;
  knowledgeBaseId: string;
  title: string;
  summary: string;
  nodes: LearningMapNode[];
  recommendedOrder: string[];
  confusingAreas: ConfusingArea[];
  sourceRefs: SourceRef[];
  createdAt: string;
  updatedAt: string;
}
```

`LearningMapNode` 可以包含：

```ts
interface LearningMapNode {
  id: string;
  title: string;
  description: string;
  status: "new" | "learning" | "understood" | "weak";
  prerequisites: string[];
  sourceRefs: SourceRef[];
}
```

第一版不需要追求图谱很漂亮，重点是学习顺序和节点状态能驱动对话。

### ConceptCard

`ConceptCard` 是可复习的概念卡。

建议第一版字段：

```ts
interface ConceptCard {
  id: string;
  knowledgeBaseId: string;
  learningMapNodeId?: string;
  title: string;
  explanation: string;
  examples: string[];
  reviewQuestions: string[];
  mastery: "new" | "reviewing" | "stable" | "weak";
  sourceRefs: SourceRef[];
  createdAt: string;
  updatedAt: string;
}
```

概念卡的来源可以是：

- 学习地图生成时预生成。
- 对话结束后从本轮学习中抽取。
- 用户明确要求保存某个概念。

MVP 阶段优先支持前两种。

### StudyContinuity

`StudyContinuity` 记录“学到哪、下一步做什么”。

建议第一版字段：

```ts
interface StudyContinuity {
  id: string;
  knowledgeBaseId: string;
  sessionId?: string;
  currentNodeId?: string;
  lastStudiedAt: string;
  lastSummary: string;
  weakPoints: string[];
  nextSuggestion: string;
  pendingReviewCardIds: string[];
  recentSourceRefs: SourceRef[];
}
```

这是闭环里最重要的持久化结构之一。它让首页和资料库页能直接接住用户，而不是让用户重新开始。

## SourceRef 的统一意义

无论是学习地图、对话回答、概念卡还是课后沉淀，都需要能指回资料依据。

建议统一一个轻量结构：

```ts
interface SourceRef {
  sourceId: string;
  title: string;
  chunkId?: string;
  quote?: string;
  locator?: string;
  relevance?: number;
}
```

第一版可以先保证：

- 能展示资料标题。
- 能展示片段摘要或短引用。
- 能回到对应资料片段。

不要一开始就把证据系统做成过重的引用管理器。

## MVP 范围

第一版只做一个小但完整的闭环：

```txt
一个知识库
一个学习地图
一个学习会话
一个课后沉淀面板
一次可继续的下次入口
```

明确暂缓：

- 多知识库联合学习
- 复杂知识图谱编辑
- 多种资料类型的完整适配
- 很复杂的 spaced repetition 算法
- 自动生成完整课程体系
- 多 agent 学习策略编排

这些都可以后续做，但第一版必须先验证“持续陪学”的主体验。

## 建议落地顺序

### 第一阶段：闭环骨架

目标：让用户能从资料库启动学习，并看到学习地图。

要做：

- 知识库页增加“开始学习这个资料库”入口。
- 后端生成并保存 `LearningMap`。
- 前端显示学习地图、推荐顺序和当前状态。

验收标准：

- 一个资料库可以生成一张学习地图。
- 用户能从学习地图进入学习对话。

### 第二阶段：证据对话

目标：让学习对话稳定使用资料依据。

要做：

- 对话请求携带当前 `knowledgeBaseId` 和 `learningMapNodeId`。
- 检索结果进入回答上下文。
- assistant 回答输出 source refs。
- 前端展示引用来源。

验收标准：

- 回答能看到引用了哪些资料。
- 引用能展开到片段级信息。
- 依据不足时能明确说明。

### 第三阶段：课后沉淀

目标：每轮学习结束后自动生成可复用学习资产。

要做：

- turn end 后生成本轮 summary。
- 抽取 `ConceptCard`。
- 生成 review questions。
- 更新 weak points。
- 写入 `StudyContinuity`。

验收标准：

- 一轮对话结束后出现课后沉淀面板。
- 下次回到资料库页能看到上次总结和下一步建议。

### 第四阶段：继续学习入口

目标：让用户回来时不用重新组织上下文。

要做：

- 首页或资料库页展示 `StudyContinuity`。
- 提供“继续上次学习”入口。
- 自动带入上次节点、薄弱点和待复习卡片。

验收标准：

- 用户可以一键继续上次学习。
- 对话知道上次学到哪里。

## 和现有能力的关系

这不是新增一个孤立模块，而是重新组织现有能力：

- 知识库负责资料存储和检索。
- Retrieval 负责给回答提供依据。
- LearningState 负责学习状态和回合策略。
- Memory 负责跨会话保留长期信息。
- Skills 负责调用学习工具。
- WebUI 负责把闭环体验呈现给用户。

下一阶段的关键不是堆更多功能，而是让这些能力在一个用户路径里互相接住。

## 风险与边界

### 风险一：学习地图质量不稳定

第一版不应该要求学习地图一次生成就完美。可以允许它是可增量修正的：

- 先生成粗地图。
- 对话中更新节点状态。
- 课后沉淀时补充概念卡和薄弱点。

### 风险二：引用体验过重

引用来源如果占据太多界面，会打断学习节奏。

第一版应该保持主回答清爽，把证据放在可展开区域里。

### 风险三：沉淀内容太泛

课后沉淀如果只是“今天学习了很多内容”，价值会很低。

生成时要尽量结构化：

- 学到了什么概念
- 哪些地方还不稳
- 下次先做什么
- 哪些卡片需要复习

### 风险四：状态结构过早复杂化

不要一开始就把学习地图、概念卡、记忆、复习系统设计得过度完整。

MVP 只需要足够支撑一条闭环路径，后面再逐步收紧协议。

## 最小成功标准

这个版本可以用一个简单标准判断是否成立：

> 用户上传或选择一组资料后，CoLearn 能生成学习地图；用户可以进入带来源依据的学习对话；对话结束后自动形成概念卡、薄弱点和下次建议；用户下次回来可以直接继续。

如果这条路径顺畅，CoLearn 就会从“有知识库的聊天工具”，向“能持续陪学的资料学习系统”迈出关键一步。
