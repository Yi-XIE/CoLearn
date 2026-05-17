# LightRAG 作为背景知识库的状态机协同方案

这份文档说明 `LightRAG` 在 CoLearn 主线里的定位，以及它如何和外层学习状态机配合。目标不是“能查资料”，而是“在学习过程中持续补资料、补证据、补连续性”。

## 实施状态

- 已落地：回合前 `retrieval_focus` 生成、`prefetched_references` 注入、回写阶段 `retrieval_hits` / `retrieval_misses` / `retrieval_evidence_map` 归档。
- 已落地：`learning_orchestrator`、`state_hooks`、`runtime_v2/prompting.py`、`runtime_v2/result_bridge.py` 已接入该链路。
- ~~待继续：把 `retrieval_evidence_map` 进一步细化到 chunk / node / blocker 的结构化支撑关系，并补更强的命中去重与排序策略。~~ 已完成：`retrieval_evidence_map` item 已带 `target_type`、`target_id`、`support_reason`、`confidence`，并按目标和 chunk 回写。
- ~~下一步重点：补 `prompt_support_bundle` 选择器，让进入 prompt 的资料从“预取数量提示”升级成“按学习状态筛过的少量证据片段”。~~ 已完成：已新增规则选择器，prompt 注入 `prompt_support_bundle`。
- ~~产品闭环重点：让前端能看见本轮资料依据、资料支撑了哪个学习节点、哪些 blocker 还缺证据。~~ 已完成：学习页已增加本轮依据面板，展示来源、支撑目标、资料缺口和下一轮检索提示。

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
- `runtime_v2/prompting`：把筛选后的 `prompt_support_bundle` 注入本轮学习上下文
- `webui`：把资料依据、支撑关系和资料缺口变成用户可感知的学习反馈

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

当前最需要补强的不是“能不能检索”，而是“检索结果能不能稳定进入学习闭环”：

- 回合前：每种 `turn_mode` 都可以做轻量预取。
- 回合中：是否允许 agent 主动调用 `lightrag`，由 `TurnPolicy` 控制。
- 回合后：资料必须能追溯到具体 node、blocker、gap 或 chunk。
- 前端侧：用户要能看见本轮参考依据和仍缺资料的地方。

## 4. 总体运行方式

`LightRAG` 应该像一个始终在线的背景支持层，围绕学习状态持续供给知识。

### 4.1 回合前

先根据这些输入形成最小检索焦点：

- `active_node_id`
- `turn_mode`
- `critical_blockers`
- `unverified_gaps`

输出一小组候选资料，先放进 request metadata，不一定全部塞进 prompt。

### 4.2 回合中

检索目标跟模式绑定：

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

### 4.3 回合后

只要本轮用了 `lightrag`，至少要写回：

- 命中的 `source_refs`
- 命中的 `chunk_ids`
- 这些资料支持的是哪个 node 或 blocker
- 这些支撑是否推动了 `NODE_COMPLETED`、`BLOCKER_FOUND` 或 `EVIDENCE_ATTACHED`

## 5. 资料进入 Prompt 的组装规则

这是把方案推进到可以直接编码的关键部分。

### 5.1 两层结构

不要把检索命中的资料直接全部塞进 prompt。先把资料分成两层：

- `prefetch pool`
  - 回合前预取的全部候选资料
  - 通常保留 4 到 8 条
  - 放在 metadata 里，供选择器使用
- `prompt support bundle`
  - 真正进入 prompt 的资料片段
  - 通常保留 2 到 4 条
  - 必须是按 `turn_mode` 筛过、压缩过、去重过的结果

这两层的目的不同：

- `prefetch pool` 解决“本轮有哪些资料可能有用”
- `prompt support bundle` 解决“本轮 prompt 里最该放哪几条”

### 5.2 先做分类，再做选择

每条命中资料在进入 `prefetch pool` 后，先补一个 `support_type`。建议分类如下：

- `definition`
- `prerequisite`
- `example`
- `counterexample`
- `procedure`
- `reference`
- `extension`
- `comparison`

如果底层检索结果没有现成标签，先用轻规则补：

- 含“定义”“概念”“本质”优先标成 `definition`
- 含“例如”“例子”“案例”优先标成 `example`
- 含“反例”“误区”“常见错误”优先标成 `counterexample`
- 含“步骤”“证明”“推导”“做法”优先标成 `procedure`
- 含“来源”“依据”“定理”“文献”优先标成 `reference`
- 含“延伸”“拓展”“进一步”优先标成 `extension`
- 含“区别”“对比”“比较”优先标成 `comparison`

先分类，再按模式打分，不要直接拿检索排序结果塞进 prompt。

### 5.3 基础过滤规则

任何模式下，进入 `prompt support bundle` 之前先做一轮统一过滤：

1. 去重
   - 同一 `source_ref + chunk_id` 只保留一条
   - 同一资料里语义高度重复的片段只保留一条
2. 相关性过滤
   - 优先保留命中当前 `active_node_id` 的资料
   - 其次保留命中当前 blocker / gap 的资料
3. 长度压缩
   - 原始 chunk 不直接进 prompt
   - 先压成 80 到 180 字的摘要片段
4. 噪声过滤
   - 删除目录、导航、版权、无关前言
   - 删除和当前模式无关的大段背景说明

### 5.4 统一预算

建议固定一个可编码的预算，避免 prompt 体积飘掉：

- `prefetch pool`：最多 5 条
- `prompt support bundle`：默认 3 条，最多 4 条
- 每条 prompt 片段：80 到 180 字摘要
- 引用信息：每条都附 `source_ref` 和 `chunk_id`

如果资料很多，不要多放条数，优先压缩摘要。

### 5.5 不同 turn_mode 下的片段组装规则

这是核心规则。

#### `ANCHOR`

目标：先把概念站稳，不追求资料丰富度。

如果预取了 5 条资料，进入 prompt 的优先顺序应该是：

1. 最高优先：`definition`
2. 第二优先：`prerequisite`
3. 第三优先：`example`
4. 低优先：`extension`

推荐组装：

- 1 条定义片段
- 1 条先修知识片段
- 视情况补 1 条非常短的例子

不该优先放的内容：

- 长案例
- 大段拓展讨论
- 复杂反例

适合的 prompt 结构：

- `核心定义`
- `先修提醒`
- `最短例子`

#### `CORRECTION`

目标：纠错，不是扩展。

如果预取了 5 条资料，进入 prompt 的优先顺序应该是：

1. 最高优先：`counterexample`
2. 第二优先：`comparison`
3. 第三优先：`definition`
4. 低优先：`extension`

推荐组装：

- 1 条反例
- 1 条正确概念对照
- 1 条定义澄清

不该优先放的内容：

- 漫长背景
- 无关例题
- 纯扩展阅读

适合的 prompt 结构：

- `错误点对应的反例`
- `正确概念对照`
- `一句定义澄清`

#### `VERIFY`

目标：验证步骤或论证，不是重讲概念。

如果预取了 5 条资料，进入 prompt 的优先顺序应该是：

1. 最高优先：`procedure`
2. 第二优先：`reference`
3. 第三优先：`definition`
4. 低优先：`example`

推荐组装：

- 1 条步骤说明
- 1 条来源依据
- 视情况补 1 条定义约束

不该优先放的内容：

- 漫长例子
- 大段拓展阅读
- 和验证无关的概念背景

适合的 prompt 结构：

- `核验步骤`
- `来源依据`
- `必要定义边界`

#### `EXPLORE`

目标：在不丢掉主线的前提下，往前推进理解。

如果预取了 5 条资料，进入 prompt 的优先顺序应该是：

1. 最高优先：`example`
2. 第二优先：`extension`
3. 第三优先：`comparison`
4. 低优先：`definition`

推荐组装：

- 1 条当前节点相关例子
- 1 条延伸说明
- 1 条相邻概念或方法对比

不该优先放的内容：

- 重复定义
- 纯术语解释
- 和当前节点距离太远的材料

适合的 prompt 结构：

- `当前节点例子`
- `延伸说明`
- `相关对比`

### 5.6 模式内降级规则

如果某个模式缺少理想类型，按这个顺序降级：

- `ANCHOR`
  - `definition -> prerequisite -> example -> reference`
- `CORRECTION`
  - `counterexample -> comparison -> definition -> reference`
- `VERIFY`
  - `procedure -> reference -> definition -> example`
- `EXPLORE`
  - `example -> extension -> comparison -> definition`

这样在检索质量不稳定时，组装逻辑仍然可预测。

### 5.7 片段摘要规则

进入 prompt 的不是原始 chunk，而是摘要片段。摘要要遵守：

- 一条只表达一个知识点
- 优先保留能直接服务当前模式的信息
- 附带来源标记
- 不要把原文大段照搬

建议格式：

```text
[definition] 线性变换的复合对应矩阵乘法，顺序影响结果。（source: note.md#c12）
[example] 先旋转再投影，和先投影再旋转的结果不同。（source: example.md#c04）
```

### 5.8 不进 Prompt 的资料怎么处理

没有进入 prompt 的资料不要丢掉，它们仍然有价值。

建议处理方式：

- 保留在 `prefetched_references`
- 保留在 `retrieval_hits`
- 如果本轮没用到，但和 continuation 有关，写进 `continuation_retrieval_hint`

这样 agent 后续还可以继续调用，而不是每轮重新检索。

## 6. 具体执行步骤

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
- `turn_mode == EXPLORE` 时，查当前节点的扩展材料和例子

### 第三步：预取资料

调用 `RetrievalService` 或 `lightrag` 相关能力，拿到：

- 命中的文本
- 命中的 chunk
- 命中的 `source_ref`
- 检索状态和 warning

### 第四步：分类和筛选

把预取结果先分类成 `support_type`，再按当前 `turn_mode` 选出 `prompt support bundle`。

建议新增一个选择函数，职责单一：

- 输入：`prefetch pool`、`turn_mode`、`active_node_id`、`blockers`
- 输出：`prompt_support_bundle`

建议实现落点：

- `colearn/runtime_v2/prompting.py` 附近新增一个选择器
- 或在 `colearn/app/learning_orchestrator.py` 里生成 metadata，再交给 prompting 使用

### 第五步：写入 request metadata

至少写入这些字段：

- `source_readiness`
- `retrieval_focus`
- `retrieval_reason`
- `prefetched_references`
- `prompt_support_bundle`
- `source_profile`

### 第六步：进入模型回合

把 `prompt_support_bundle` 注入 prompt。

原则：

- 每个模式只放少量高价值片段
- 摘要优先，原文次之
- 每条必须可追溯到 `source_ref`

### 第七步：识别学习事件

把工具事件、source refs、final text、user message 结合起来，生成学习事件。

优先级建议：

1. 工具事件
2. source refs
3. 结构化状态信号
4. 最后才看 final text 关键词

### 第八步：回写 LearningState

把本轮结果写回：

- board facts
- evidence refs
- continuation
- warnings
- last turn result

### 第九步：为下一轮准备上下文

把这轮的检索支持结果存下来，下一轮继续用。

## 7. 建议字段

### Request 侧

- `prefetched_references`
  - 本轮提前查到的资料候选
- `retrieval_focus`
  - 本轮优先查什么
- `retrieval_reason`
  - 为什么要查这些资料
- `prompt_support_bundle`
  - 真正进入 prompt 的片段集合

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

## 8. 状态机协同规则

建议固定成下面这些规则：

1. `turn_mode` 决定默认检索目标。
2. 回合前预取不被 `allowed_tools` 限制，回合中主动工具调用才由 `TurnPolicy` 限制。
3. `critical_blockers` 决定是否必须优先查反例、纠错证据和概念对照。
4. `unverified_gaps` 决定是否必须优先查步骤、依据和验证边界。
5. `active_node_id` 决定资料过滤范围。
6. `prompt_support_bundle` 决定真正进入 prompt 的资料片段。
7. `evidence_refs` 进入下一轮 continuation 上下文。
8. `source_readiness` 决定检索失败是否写成 warning。
9. `retrieval_evidence_map` 要能被前端消费，用来展示资料支撑关系。

## 9. 产品闭环推进方案

下一步要把这条链从“后端检索链路”推进成“用户能感知、系统能学习、下一轮能延续”的产品闭环。

### 9.1 第一优先级：补 `prompt_support_bundle`

当前已有 `prefetched_references`，但 prompt 里还不应该只知道“预取了几条资料”。需要新增一个选择层：

- ~~输入：`prefetched_references`、`retrieval_focus`、`turn_mode`、`active_node_id`、`critical_blockers`、`unverified_gaps`~~
- ~~输出：`prompt_support_bundle`~~
- ~~每条输出包含：`support_type`、`summary`、`source_ref`、`chunk_id`、`support_target`、`score`~~

建议先把选择器做成纯函数，放在 `colearn/runtime_v2/prompting.py` 附近，后续如果规则变复杂，再迁到独立的 retrieval support 模块。

### 9.2 第二优先级：细化证据映射

`retrieval_evidence_map` 不能只把同一批资料挂到所有目标上。更好的结构是每条资料只声明它真实支撑的对象：

- ~~`target_type`~~
  - `node`
  - `blocker`
  - `gap`
  - `chunk`
- ~~`target_id`~~
  - 对应 `active_node_id`、`blocker.id`、gap id 或 `chunk_id`
- ~~`support_type`~~
  - 对应定义、例子、反例、步骤、依据、对比等
- ~~`support_reason`~~
  - 一句话说明这条资料为什么支撑这个目标
- ~~`confidence`~~
  - 轻量分数，先用规则生成即可

这样前端和回写层才能区分“这条资料解释了当前节点”和“这条资料证明了某个 blocker 已经被处理”。

### 9.3 第三优先级：让前端看见本轮依据

知识库能力要被用户感知，建议在学习页增加一个轻量区域，不做成独立检索页：

- ~~本轮参考依据~~
  - 展示进入 `prompt_support_bundle` 的 2 到 4 条资料
  - 每条显示来源、类型和对应学习目标
- ~~资料支撑关系~~
  - 显示资料支撑了当前 node、哪个 blocker 或哪个 gap
- ~~资料缺口~~
  - 当 `retrieval_misses` 非空时，提示当前缺少哪类资料
- ~~下一轮检索提示~~
  - 从 `continuation_retrieval_hint` 里展示下一轮建议继续查什么

这个 UI 不需要打断学习主流程，只要让学习者知道“这轮解释是有依据的”，就能明显增强信任感。

### 9.4 第四优先级：把 query 从模式词升级成状态感知 query

当前 `retrieval_focus.default_query` 可以先保留，但真实检索 query 应该逐步拼入学习现场信息：

- ~~`active_node_label`~~
- ~~用户本轮问题~~
- ~~当前 `critical_blockers` 的描述~~
- ~~当前 `unverified_gaps`~~
- ~~上一轮 `continuation_prompt`~~
- ~~已有 `evidence_refs`~~

建议先生成结构化 `retrieval_query_context`，再把它压成检索 query。这样后面无论接 LightRAG、并行检索还是其他知识源，都不用重新拆状态。

### 9.5 第五优先级：保留工具权限的产品边界

回合前预取和回合中工具调用要分开看：

- ~~回合前预取是系统准备动作，`ANCHOR / CORRECTION / VERIFY / EXPLORE` 都可以执行。~~
- ~~回合中主动调用 `lightrag` 是 agent 行为，仍由 `TurnPolicy.allowed_tools` 控制。~~
- ~~`CORRECTION` 和 `VERIFY` 模式即使不允许 agent 自由探索，也应该能拿到回合前筛好的证据。~~

这个边界可以避免纠错和验证阶段缺证据，也能防止 agent 在需要收束的模式里跑偏。

## 10. 最小可实施方案

如果要先落地一个可用版本，建议按这个顺序：

1. ~~固定 `source_profile` 和 `source_readiness` 进入 request metadata。~~
2. ~~增加 `retrieval_focus`。~~
3. ~~增加 `support_type` 分类。~~
4. ~~增加 `prompt_support_bundle` 选择器。~~
5. ~~让 prompt 注入从“直接塞检索结果”变成“塞模式筛过的片段”。~~
6. ~~把 evidence 和 node / blocker 的关系写回。~~
7. ~~最后补 `retrieval_evidence_map` 和 `continuation_retrieval_hint`。~~

产品闭环版本建议继续补这几步：

1. ~~让 `prompt_support_bundle` 出现在 `LearningTurnRequest.metadata`、`runtime_v2.retrieval` 和 `last_turn_result`。~~
2. ~~让 `retrieval_evidence_map` 的 item 带 `target_type`、`target_id`、`support_reason` 和 `confidence`。~~
3. ~~让 `retrieval_query_context` 同时保留结构化字段和最终 query。~~
4. ~~让前端学习页展示本轮参考依据、资料支撑关系和资料缺口。~~
5. ~~给 `ANCHOR / CORRECTION / VERIFY / EXPLORE` 各补一个 prompt bundle 选择测试。~~

## 11. 验收标准

可以用下面这些标准判断是否做成了：

- ~~能从状态机直接看出当前回合该查什么~~
- ~~能从回合结果里看出检索结果支撑了哪个 node / blocker~~
- ~~能从 `last_turn_result` 里读到本轮知识支持信息~~
- ~~多轮学习时，下一轮能延续上一轮的知识上下文~~
- ~~`ANCHOR` 和 `EXPLORE` 模式命中同样数量资料时，进 prompt 的片段类型不同~~
- ~~`CORRECTION` 和 `VERIFY` 即使不开放自由探索工具，也能拿到回合前筛好的证据~~
- ~~前端能展示本轮参考依据、支撑目标和资料缺口~~
- ~~没有命中资料时，系统能写出可解释的 `retrieval_misses`~~
- ~~`LightRAG` 不再只是“能调用的工具”，而是“状态机驱动的知识供给层”~~

## 12. 结论

在 CoLearn 里，`LightRAG` 应该被看作学习者的背景知识库。

它不是单次回答问题的工具，而是围绕当前学习状态持续补资料、补证据、补连续性。

当前主线已经接通可用闭环，下一步要做的是把它推进成真正由状态机驱动、能被前端感知、能持续回写学习事实的常驻知识支持层。
