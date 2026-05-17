# LightRAG 作为背景知识库的状态机协同方案

这份文档说明 `LightRAG` 在 CoLearn 主线里的定位，以及它如何和外层学习状态机配合。目标不是“能查资料”，而是“在学习过程中持续补资料、补证据、补连续性”。

## 1. 定位

`LightRAG` 不是独立检索页，也不是一次性搜索工具。

它是学习者的背景知识库，负责在完整学习循环里提供可用材料：

- 给当前学习节点补背景
- 给 blocker 补证据和反例
- 给解释、验证、纠错补参考资料
- 维持多轮学习之间的知识连续性

## 2. 职责分工

外层状态机负责判断“系统现在该怎么学”。

`LightRAG` 负责回答“这一步学习应该用什么资料支撑”。

稳定分工如下：

- `LearningState`：记录进度、blocker、continuation、evidence
- 外层状态机：决定 `ANCHOR / CORRECTION / VERIFY / EXPLORE / PAUSED`
- `LightRAG`：提供检索结果、证据支撑和知识补给

## 3. 当前接入现状

当前主线里，`LightRAG` 已接到这些模块：

- `colearn/retrieval/service.py`
  - 同步项目资料
  - 把检索结果整理成 `retrieval_bundle`
- `colearn/app/source_preflight.py`
  - 回合前检查资料准备状态
  - 记录同步和索引状态
- `colearn/runtime_v2/tooling.py`
  - 注册 `lightrag` 工具
  - 允许 agent 在回合中主动查资料
- `colearn/learning/state_hooks.py`
  - 把 `lightrag` 作为 `EXPLORE` 模式下的默认工具之一
  - 把工具命中转成 evidence 类型学习事件
- `colearn/runtime_v2/prompting.py`
  - 把资料准备状态和同步状态注入 prompt

现在它已经“接上了”，但还没有完全变成状态机驱动的常驻知识层。

## 4. 目标运行方式

`LightRAG` 应该像一个始终在线的背景支持层，围绕学习状态持续供给知识。

### 4.1 回合前

先根据这些输入形成最小检索焦点：

- `active_node_id`
- `turn_mode`
- `critical_blockers`
- `unverified_gaps`

输出一小组候选资料，先放进 request metadata，不一定全部塞进 prompt。

建议回合前要做的事：

1. 读取当前 board 和 state。
2. 根据 turn mode 生成 retrieval focus。
3. 结合 blocker / node 预取资料。
4. 把预取结果写入 request metadata。
5. 把资料准备状态写入 prompt 可见范围。

### 4.2 回合中

检索目标要跟模式绑定：

- `ANCHOR`
  - 基础定义
  - 先修知识
  - 概念图谱
- `CORRECTION`
  - 反例
  - 纠错证据
  - 概念对照
- `VERIFY`
  - 步骤核验
  - 有来源支撑的推理
  - 公式或结论依据
- `EXPLORE`
  - 深一点的说明
  - 相关例子
  - 当前节点资料

建议回合中要做的事：

1. 根据 turn mode 决定默认检索目标。
2. 根据 blocker / node 过滤资料范围。
3. 在回答前或工具调用时注入检索结果。
4. 如果检索结果支持纠错或验证，优先转成 evidence。

### 4.3 回合后

只要本轮用了 `lightrag`，至少要写回：

- 命中的 `source_refs`
- 命中的 `chunk_ids`
- 这些资料支持的是哪个 node 或 blocker
- 这些支撑是否推动了 `NODE_COMPLETED`、`BLOCKER_FOUND` 或 `EVIDENCE_ATTACHED`

建议回合后要做的事：

1. 汇总命中资料。
2. 标注资料支持的学习目标。
3. 写回 LearningState。
4. 更新 continuation 提示。
5. 把本轮检索结果作为下一轮的知识上下文候选。

## 5. 具体执行步骤

这是最适合直接照着做的一版。

### 第一步：回合前取状态

从 session / project 取出：

- `board`
- `state_projection`
- `turn_policy`
- `continuation_prompt`
- `source_profile`

### 第二步：生成检索焦点

根据当前状态生成 `retrieval_focus`：

- `turn_mode == ANCHOR` 时，查基础概念和先修知识
- `turn_mode == CORRECTION` 时，查反例、纠错和对照
- `turn_mode == VERIFY` 时，查步骤、来源和推理依据
- `turn_mode == EXPLORE` 时，查当前节点的扩展材料

### 第三步：预取资料

调用 `RetrievalService` 或 `lightrag` 相关能力，拿到：

- 命中的文本
- 命中的 chunk
- 命中的 source ref
- 检索状态和 warning

### 第四步：写入 request metadata

把检索结果和状态写进 metadata，至少包括：

- `source_readiness`
- `retrieval_focus`
- `retrieval_reason`
- `prefetched_references`
- `source_profile`

### 第五步：进入模型回合

把检索结果按 turn mode 轻量注入 prompt。

原则：

- 不要把全部资料无差别塞进 prompt
- 优先放当前 node、当前 blocker、当前 verification 需要的证据
- 如果资料很多，只放摘要和最相关片段

### 第六步：识别学习事件

把工具事件、source refs、final text、user message 结合起来，生成学习事件。

优先级建议：

1. 工具事件
2. source refs
3. 结构化状态信号
4. 最后才看 final text 关键词

### 第七步：回写 LearningState

把本轮结果写回：

- board facts
- evidence refs
- continuation
- warnings
- last turn result

### 第八步：为下一轮准备上下文

把这轮的检索支持结果存下来，下一轮继续用。

## 6. 建议的字段

### Request 侧

- `prefetched_references`
  - 本轮提前查到的资料候选
- `retrieval_focus`
  - 本轮优先查什么
- `retrieval_reason`
  - 为什么要查这些资料

### Result 侧

- `retrieval_hits`
  - 实际命中的资料
- `retrieval_misses`
  - 没查到或没命中的部分
- `retrieval_evidence_map`
  - 资料和 node / blocker / gap 的映射

### Writeback 侧

- `knowledge_support_summary`
  - 本轮资料支撑摘要
- `blocker_support_refs`
  - 哪些资料支撑了哪些 blocker
- `continuation_retrieval_hint`
  - 下一轮建议继续查什么

## 7. 状态机协同规则

建议固定成下面这些规则。

1. `turn_mode` 决定默认检索目标。
2. `critical_blockers` 决定是否必须优先查证据。
3. `active_node_id` 决定资料过滤范围。
4. `evidence_refs` 进入下一轮 continuation 上下文。
5. `source_readiness` 决定检索失败是否写成 warning。

## 8. 最小可实施方案

如果要先落地一个可用版本，建议按这个顺序：

1. 先把 `source_profile` 和 `source_readiness` 固定进 request metadata。
2. 再根据 `turn_mode` 生成 `retrieval_focus`。
3. 然后在 `EXPLORE`、`VERIFY`、`CORRECTION` 三种模式里接上检索。
4. 接着把命中的 evidence 写回 `LearningState`。
5. 最后再补 `retrieval_evidence_map` 和 `continuation_retrieval_hint`。

先不要做得太散，先保证这条链是闭环的。

## 9. 验收标准

可以用下面这些标准判断是否做成了。

- 能从状态机直接看出当前回合该查什么
- 能从回合结果里看出检索结果支撑了哪个 node / blocker
- 能从 `last_turn_result` 里读到本轮的资料支持信息
- 多轮学习时，下一轮能延续上一轮的知识上下文
- `LightRAG` 不再只是“能调用的工具”，而是“状态机驱动的知识供给层”

## 10. 结论

在 CoLearn 里，`LightRAG` 应该被看作学习者的背景知识库。

它不是单次回答问题的工具，而是围绕当前学习状态持续补资料、补证据、补连续性。

当前主线已经接通可用闭环，下一步要做的是把它推进成真正由状态机驱动的常驻知识支持层。
