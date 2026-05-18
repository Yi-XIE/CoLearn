# CoLearn LearningState 协议

## 文档目的

这份文档描述当前代码中的 Learning State 三层协议，以及它们和 retrieval、runtime_v2、持久化层之间的映射关系。

对应实现主要在：

- `colearn/learning/state.py`
- `colearn/learning/state_hooks.py`
- `colearn/learning/turn_contract.py`
- `colearn/learning/response_contract.py`
- `colearn/app/learning_orchestrator.py`
- `colearn/runtime_v2/result_bridge.py`

## 三层结构

当前协议仍然是三层：

1. `BoardFacts`
2. `TurnPolicy`
3. `LearningEvent`

其中：

- `BoardFacts` 是跨回合持久事实。
- `TurnPolicy` 是每轮重新计算的策略投影。
- `LearningEvent` 是回合结束后驱动 Board 更新的事件。

Retrieval 现在不是第四层状态，而是围绕 Board 派生的一组支持信息：`retrieval_focus`、`retrieval_reason`、`retrieval_query_context`、`prefetched_references`、`parallel_support`、`prompt_support_bundle`、`retrieval_evidence_map`。

## BoardFacts

### 当前字段

`BoardFacts` 当前字段如下：

- `project_id`
- `session_id`
- `current_turn_mode`
- `board_version`
- `updated_at`
- `current_progress`
- `student_snapshot`
- `gaps_and_blockers`
- `continuation`
- `evidence_refs`

### 嵌套结构

`current_progress` 当前包含：

- `active_node_id`
- `active_node_label`
- `completed_node_ids`
- `path_node_ids`

`student_snapshot` 当前包含：

- `mastery_level`
- `cognitive_load`
- `last_user_intent_raw`

`gaps_and_blockers` 当前包含：

- `critical_blockers`
- `unverified_gaps`

`critical_blockers` 使用 `Blocker`，字段是：

- `id`
- `type`
- `desc`

`continuation` 当前包含：

- `next_prompt_hint`
- `last_completed_turn_id`

`evidence_refs` 当前是 `list[dict[str, Any]]`，用于保留 source / tool / chunk 级证据引用。

### 当前事实源

当前运行时以 session 上的 `board_facts` 为主要事实源，project 上的 `board_facts` 是镜像副本。

组装顺序是：

1. 优先读取 `session.board_facts`
2. 否则回退到 `project.board_facts`
3. 如果都没有，再从 project anchor / latest review / source refs 推导一个初始 Board

### 当前持久化形态

`BoardFacts` 在运行时是 dataclass，但持久化时仍会转成字典落盘。

也就是说，Board 的类型边界还没有完全收紧到单一表示形式。

## TurnMode

当前允许的 turn mode 是：

- `ANCHOR`
- `CORRECTION`
- `VERIFY`
- `EXPLORE`
- `PAUSED`

归一化逻辑在 `_normalize_turn_mode()` 中，未知值会回退为 `EXPLORE`。

## TurnPolicy

### 作用

`TurnPolicy` 是基于当前 Board 和用户输入即时计算出的回合策略，不持久化为长期事实。

### 当前字段

当前字段包括：

- `turn_mode`
- `model_preset`
- `main_goal`
- `restrictions`
- `allowed_tools`
- `enabled_tools`
- `review_focus`
- `reply_contract`
- `warnings`
- `continuation_prompt`
- `metadata`

### 当前策略规则

当前 `determine_turn_mode()` 的顺序是：

1. `PAUSED` 保持暂停
2. 已经处在 `ANCHOR`、`CORRECTION`、`VERIFY` 时保持当前模式
3. 没有 active node 时进入 `ANCHOR`
4. 有 critical blockers 时进入 `CORRECTION`
5. 有 unverified gaps 时进入 `VERIFY`
6. 其他情况进入 `EXPLORE`

工具开放规则当前是：

- `memory` 默认可用
- `lightrag` 仅在 `EXPLORE` 时作为工具开启

需要区分：回合前 retrieval prefetch 是 orchestrator 主链动作，不受 `enabled_tools` 中是否包含 `lightrag` 影响。

### model_preset

`resolve_model_preset()` 当前规则是：

- `EXPLORE` -> `explore`
- `ANCHOR` / `CORRECTION` / `VERIFY` -> `deep`
- `PAUSED` -> 不设置

`before_turn()` 会把该值写入 request metadata，`NanobotTurnExecutor` 在运行前通过 nanobot loop 设置 preset。

### metadata 的当前用途

`TurnPolicy.metadata` 会写入：

- `board_version`
- `blocker_count`

`before_turn()` 会把更多运行态信息复制到 `LearningTurnRequest.metadata`：

- `turn_mode_before`
- `board_version_before`
- `active_node_id_before`
- `active_node_label_before`
- `continuation_prompt_before`
- `allowed_tools_before`
- `enabled_tools_before`
- `source_readiness_before`
- `policy_restrictions`
- `model_preset`

## Retrieval 协同字段

当前 retrieval 协同由 `state_hooks.py` 和 orchestrator 共同完成。

### retrieval_focus

`build_retrieval_focus()` 从 Board 派生本轮检索焦点，当前包含：

- `turn_mode`
- `active_node_id`
- `active_node_label`
- `critical_blockers`
- `unverified_gaps`
- `evidence_refs`
- `default_query`
- `scope`

`default_query` 按模式生成：

- `ANCHOR`：基础定义、前置知识、关键概念
- `CORRECTION`：反例、纠错证据、概念对照
- `VERIFY`：步骤核验、来源依据、推理链
- `EXPLORE`：当前节点扩展资料、相关例子、延伸理解
- `PAUSED`：当前学习节点背景资料

### retrieval_reason

`build_retrieval_reason()` 解释为什么要检索。它优先看 blocker，其次看 turn mode 和 source readiness。

### prefetch_bundle

orchestrator 会调用 `RetrievalService.build_bundle()` 做回合前预取，并把结果放到：

- `LearningTurnRequest.retrieval_bundle`
- `LearningTurnRequest.metadata["prefetched_references"]`
- `project.retrieval_profile["prefetch_bundle"]`

### prompt_support_bundle

orchestrator 会把回合前预取和 `parallel_support` 的资料合并成 `prompt_support_bundle`。该 bundle 会按 turn mode、support type、目标对象和轻量分数筛选，最多把少量资料片段注入 prompt，并写入 `runtime_v2.retrieval` 与 `last_turn_result`。

### retrieval_evidence_map

`build_retrieval_evidence_map()` 当前基于 `prompt_support_bundle` 建立映射：

- active node id -> evidence refs
- blocker id -> evidence refs
- `chunk:{chunk_id}` -> evidence refs

每条 evidence 会带 `target_type`、`target_id`、`support_reason` 和 `confidence`，并按 `source_ref / chunk_id / support_type` 去重排序。

## LearningStateSnapshot

`LearningStateSnapshot` 是一个更轻的视图，当前主要字段有：

- `turn_mode`
- `active_node_id`
- `active_node_label`
- `mastery_level`
- `cognitive_load`
- `blockers`

它服务于运行时请求构建，不承担独立持久化职责。

## LearningEvent

### 当前事件类型

当前实现里会产出以下事件：

- `CONTINUATION_UPDATED`
- `NODE_COMPLETED`
- `NODE_STARTED`
- `BLOCKER_FOUND`
- `EVIDENCE_ATTACHED`

### 事件来源

当前事件抽取仍是启发式规则，不是独立 agent loop：

- 从 `final_text` 中识别完成态
- 从 `user_message` 中识别 blocker
- 从 `source_references` 中附加 evidence
- 如果工具事件中出现 `lightrag`，并且当前有 active node，会把它视为 `NODE_COMPLETED` 信号

### 事件对 Board 的影响

`apply_events()` 当前会做以下变更：

- `NODE_COMPLETED` 追加到 `completed_node_ids`
- `CONTINUATION_UPDATED` 更新 continuation
- `BLOCKER_FOUND` 追加到 `critical_blockers`
- `EVIDENCE_ATTACHED` 追加到 `evidence_refs`

每次 `apply_events()` 都会生成一个新的 `BoardFacts`：

- `board_version` 加一
- `updated_at` 刷新为 UTC 时间
- `current_turn_mode` 由 `resolve_turn_mode_after()` 根据事件和更新后的 Board 再计算一次

## after_turn 产物

`after_turn_payload()` 当前会产出：

- `review_summary`
- `continuation_prompt`
- `review_to_persist`
- `turn_mode_after`
- `turn_mode_before`
- `board_after`
- `learning_events`
- `board_patch`
- `retrieval_hits`
- `retrieval_misses`
- `retrieval_evidence_map`
- `knowledge_support_summary`
- `blocker_support_refs`
- `continuation_retrieval_hint`
- `writeback_envelope`
- `memory_events`

其中 `board_patch` 是当前 WebSocket 和前端可消费的最小增量块，包含：

- `current_turn_mode`
- `board_version`
- `updated_at`
- `continuation`
- `current_progress`
- `student_snapshot`
- `gaps_and_blockers`
- `evidence_refs`

`writeback_envelope` 当前包含：

- `turn_mode_before`
- `turn_mode_after`
- `base_board_version`
- `resolved_board_version`
- `event_types`

## 与 LearningTurnRequest 的关系

当前 `LearningTurnRequest` 仍是 runtime 唯一请求契约。它会携带：

- `board_facts`
- `turn_policy`
- `state_projection`
- `source_references`
- `memory_references`
- `retrieval_bundle`
- `enabled_tools`
- `metadata`

当前 metadata 的关键字段包括：

- `turn_id`
- `source_profile`
- `retrieval_focus`
- `retrieval_reason`
- `prefetched_references`
- `parallel_support`
- `prompt_support_bundle`
- `workspace`
- `before_turn()` 补入的 turn envelope 字段

## 与 LearningTurnResult 的关系

`LearningTurnResult` 会保留：

- `board_before`
- `board_after`
- `learning_events`
- `board_patch`
- `memory_events`
- `tool_events`
- `stream_events`
- `retrieval_bundle`
- `raw_learning_result`
- `metadata`

`result_bridge` 会把以下 runtime_v2 摘要写入 `raw_learning_result` 和 `metadata`：

- `runtime_v2.board_summary`
- `runtime_v2.turn_envelope`
- `runtime_v2.retrieval`

orchestrator 在写回前会补齐 `runtime_v2.retrieval` 中的：

- `prefetched_references`
- `parallel_support`
- `prompt_support_bundle`
- `retrieval_focus`
- `retrieval_reason`
- `retrieval_hits`
- `retrieval_misses`
- `retrieval_evidence_map`
- `knowledge_support_summary`
- `blocker_support_refs`
- `continuation_retrieval_hint`

## 当前边界与已知限制

截至当前代码，Learning State 协议有几个明确边界：

- Session 是 Board 的事实主源，project 是镜像。
- 事件抽取仍是轻量启发式，不是完整状态机。
- `BoardFacts` 的运行时类型和持久化类型仍是双重表示。
- `board_version` 具备 stale write 保护，但不是严格 compare-and-swap 协议。
- `prompt_support_bundle` 已经进入 prompt 和前端，但模型最终回答中的逐条引用还没有反写成完整引用图。
- `retrieval_evidence_map` 当前主要由回合前资料和并行检索结果推导，尚未合并模型实际引用轨迹。
- `lightrag` 工具默认只在 `EXPLORE` 中启用，但回合前预取会在所有模式尝试运行。

这份文档记录的是当前协议事实。后续如果推进强类型 Board 存储、严格版本写入、真实 SubagentManager 或完整 retrieval evidence 图谱，应同步更新本文档。
