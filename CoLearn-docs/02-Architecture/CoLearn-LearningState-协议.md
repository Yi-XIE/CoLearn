# CoLearn LearningState 协议

## 文档目的

这份文档描述当前代码里的 Learning State 三层协议，以及它们在运行时和持久化层之间的映射关系。对应实现主要在：

- `colearn/learning/state.py`
- `colearn/learning/state_hooks.py`
- `colearn/app/learning_orchestrator.py`

## 三层结构

当前协议仍然是三层：

1. `BoardFacts`
2. `TurnPolicy`
3. `LearningEvent`

其中：

- `BoardFacts` 是跨回合持久事实
- `TurnPolicy` 是每轮重新计算的策略投影
- `LearningEvent` 是回合结束后驱动 Board 更新的事件

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

`continuation` 当前包含：

- `next_prompt_hint`
- `last_completed_turn_id`

`evidence_refs` 当前是 `list[dict[str, Any]]`，用于保留 source / tool / chunk 级证据引用。

### 当前事实源

当前运行时以 session 上的 `board_facts` 为主要事实源，project 上的 `board_facts` 是镜像副本。构板顺序是：

1. 优先读取 `session.board_facts`
2. 否则回退到 `project.board_facts`
3. 如果都没有，再从 project anchor / latest review / source refs 推导一个初始 Board

### 当前持久化形态

`BoardFacts` 在运行时是 dataclass，但当前持久化时仍会转成字典落盘。也就是说，Board 的类型边界还没有完全收紧到单一表示形式。

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

当前 `policy()` 采用轻量规则：

- `PAUSED` 保持暂停
- 没有 active node 时进入 `ANCHOR`
- 有 critical blockers 时进入 `CORRECTION`
- 有 unverified gaps 时进入 `VERIFY`
- 其他情况进入 `EXPLORE`

工具开放规则当前是：

- `memory` 默认可用
- `lightrag` 仅在 `EXPLORE` 时开启

### metadata 的当前用途

当前 `TurnPolicy.metadata` 会写入：

- `board_version`
- `blocker_count`

同时，`before_turn()` 会把部分策略信息复制到 `LearningTurnRequest.metadata`，用于 executor prompt 侧读取：

- `turn_mode_before`
- `policy_restrictions`

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
- 从 `source_references` 和 `tool_events` 中附加 evidence

### 事件对 Board 的影响

`apply_events()` 当前会做以下变更：

- `NODE_COMPLETED` 追加到 `completed_node_ids`
- `CONTINUATION_UPDATED` 更新 continuation
- `BLOCKER_FOUND` 追加到 `critical_blockers`
- `EVIDENCE_ATTACHED` 追加到 `evidence_refs`

每次 `apply_events()` 都会生成一个新的 `BoardFacts`：

- `board_version` 加一
- `updated_at` 刷新为 UTC 时间

## after_turn 产物

`after_turn_payload()` 当前会产出：

- `review_summary`
- `continuation_prompt`
- `review_to_persist`
- `turn_mode_after`
- `board_after`
- `learning_events`
- `board_patch`
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

## 与 LearningTurnRequest 的关系

当前 `LearningTurnRequest` 仍是 runtime 唯一请求契约。它会携带：

- `board_facts`
- `turn_policy`
- `state_projection`
- `source_references`
- `memory_references`
- `enabled_tools`
- `metadata`

需要注意：

- `retrieval_bundle` 字段仍然存在于 contract 中
- orchestrator 当前不会在回合开始前把真实 retrieval 文本塞进 request
- source readiness 会通过 `metadata["source_profile"]` 进入 prompt

## 当前边界与已知限制

截至当前代码，Learning State 协议有几个明确边界：

- Session 是 Board 的事实主源，project 是镜像
- 事件抽取仍是轻量启发式，不是完整状态机
- `BoardFacts` 的运行时类型和持久化类型仍是双重表示
- `board_version` 具备 stale write 保护，但不是严格的 compare-and-swap 协议

这份文档记录的是现在的协议真相，后续如果要推进强类型 Board 存储、严格版本写入或 retrieval contract 收紧，应同步更新本文件。
