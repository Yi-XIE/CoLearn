# CoLearn LearningState 协议

## 文档目的

这份文档描述当前代码中的 Learning State 协议，以及它们在运行时和持久化层之间的映射关系。

对应实现主要在：

- `colearn/learning/constants.py`（枚举常量）
- `colearn/learning/state.py`（数据结构）
- `colearn/learning/state_hooks.py`（构建 board / snapshot）
- `colearn/learning/board_hooks.py`（turn mode / phase 流转、after_turn）
- `colearn/learning/turn_hooks.py`（按 phase 分发 TurnPolicy）
- `colearn/app/learning_orchestrator.py` 与 `colearn/app/stages/*`（主链装配）

## 两个正交维度：Phase 与 TurnMode

当前学习状态由两个正交维度描述：

- `LearningPhase`：会话当前处在学习闭环的哪个阶段（粗粒度）
- `TurnMode`：单轮回合的执行模式（细粒度）

### LearningPhase

定义在 `constants.py` 的 `LearningPhase`：

- `INTAKE` — 新用户首次进入学习模式、且无 profile 时，先做画像采集
- `DIAGNOSE` — 出诊断题评估基线掌握度，只问不教
- `READY` — 正常学习主链（讲解 / 复习 / 出题）
- `REFLECT` — 会话收尾，生成总结并安排下次召回
- `RECALL` — 用户回访且召回到期时，先复习旧知识点

phase 的判定在 `PreflightStage._resolve_learning_phase()`：

- 非 learning 模式 → `READY`
- learning 模式、无 profile 且本会话还没有消息 → `INTAKE`
- 召回到期且本会话还没有消息 → `RECALL`
- 用户消息命中结束关键词（“结束 / done / stop” 等）→ `REFLECT`
- 其余 → 沿用 session 上记录的 `learning_phase`，默认 `READY`

phase 的自动收尾在 `board_hooks.after_turn()`：当 `learning_plan` 全部节点完成且当前 phase 为 `READY` 时，自动切到 `REFLECT`。

### TurnMode

定义在 `constants.py` 的 `TurnMode`，当前允许：

- `LEARN`
- `CHECK`
- `PAUSED`

归一化逻辑在 `normalize_turn_mode()`，未知值回退为 `LEARN`；Chat Mode 会话固定为 `PAUSED`。

## 三层结构

在上述两个维度之下，协议仍然是三层：

1. `BoardFacts` — 跨回合持久事实
2. `TurnPolicy` — 每轮重新计算的策略投影
3. `LearningEvent` — 回合结束后驱动 Board 更新的事件

## BoardFacts

### 当前字段

`BoardFacts`（`state.py`）当前字段：

- `project_id`
- `session_id`
- `current_turn_mode`（`TurnMode`）
- `learning_phase`（`LearningPhase`，默认 `READY`）
- `board_version`
- `updated_at`
- `current_progress`
- `student_snapshot`
- `gaps_and_blockers`
- `continuation`
- `evidence_refs`
- `learning_plan`
- `learning_board`

### 嵌套结构

`current_progress`（`ProgressFacts`）：`active_node_id`、`active_node_label`、`completed_node_ids`、`path_node_ids`。

`student_snapshot`（`StudentSnapshot`）：`mastery_level`、`cognitive_load`、`last_user_intent_raw`。

`gaps_and_blockers`（`GapsAndBlockers`）：`critical_blockers`（`Blocker` 列表）、`unverified_gaps`。

`continuation`（`ContinuationFacts`）：`next_prompt_hint`、`last_completed_turn_id`。

`evidence_refs` 是 `list[dict[str, Any]]`，用于保留 source / tool / chunk 级证据引用。

### LearningPlan 与 LearningBoard

这两块是双模式瘦身后新增的学习结构（`state.py`）：

`LearningPlan`：

- `goal`
- `plan_nodes`（`LearningPlanNode` 列表，每个含 `id / label / status / depth / summary`）
- `current_node_id`
- `review_queue`
- `pending_checks`

`LearningBoard`：

- `current_progress`
- `completed_nodes`
- `blockers`
- `objections`
- `evidence_refs`
- `continuation`

`BoardFacts.__post_init__` 会在缺失时从旧字段（`current_progress` / `gaps_and_blockers` / `evidence_refs` / `continuation`）派生出 `learning_plan` 和 `learning_board`，因此能兼容没有这两块的历史会话。

### 当前事实源

运行时以 session 上的 `board_facts` 为主要事实源，project 上的 `board_facts` 是镜像副本。

组装顺序（`build_learning_board`）：

1. 优先读取 `session.board_facts`
2. 否则回退到 `project.board_facts`
3. 都没有时，从 project anchor / latest review / source refs 推导一个初始 Board

### 当前持久化形态

`BoardFacts` 在运行时是 dataclass，持久化时转成字典落盘（`colearn.storage.records`）。Board 的类型边界还没有完全收紧到单一表示形式。

## TurnPolicy

### 作用

`TurnPolicy` 基于当前 Board、当前 phase 和用户输入即时计算，不持久化为长期事实。

### 当前字段

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

`turn_hooks.policy()` 先按 `learning_phase` 分发：

- `INTAKE` → `LEARN`，限制 `do_not_teach_content` / `ask_one_question_at_a_time`，只开 `memory`
- `REFLECT` → `LEARN`，限制 `do_not_introduce_new_topic`，只开 `memory`
- `RECALL` → `CHECK`，限制 `limit_to_3_questions`，开 `memory + lightrag`
- `DIAGNOSE` → `CHECK`，限制 `do_not_teach_yet` / `ask_progressively_harder`，只开 `memory`
- `READY`（默认）→ 走轻量规则计算 turn mode

`READY` 下的轻量规则：

- 有 critical blockers 或 unverified gaps 时进入 `CHECK`
- 其他学习回合进入 `LEARN`
- `model_preset` 由 `resolve_model_preset(turn_mode)` 给出（`LEARN`/`CHECK` 映射到不同 preset）

工具开放规则（`READY`）：

- `memory` 默认可用
- `lightrag` 在 `LEARN`、或 `CHECK` 需要证据、或用户消息命中来源类关键词时按需开启（`_needs_lightrag`）
- `web_search` / `web_fetch` 在用户命中“最新 / 外部资料”类关键词、或检索给出 `external_web_fallback` 建议时兜底开启（`_needs_web_tools`）

### metadata 的当前用途

`READY` 下 `TurnPolicy.metadata` 会写入 `board_version`、`blocker_count`、`lightrag_enabled`、`web_search_enabled`、`learning_phase`；各 phase 分支会写入对应的 `learning_phase` 标记。

`before_turn()` 会把策略信息复制到 `LearningTurnRequest.metadata` 供 executor prompt 读取，包括 `turn_mode_before`、`board_version_before`、`active_node_id_before`、`policy_restrictions`、`model_preset`、`source_readiness_before` 等。

## LearningStateSnapshot

`LearningStateSnapshot` 是更轻的视图，字段：`turn_mode`、`active_node_id`、`active_node_label`、`mastery_level`、`cognitive_load`、`blockers`。它服务于运行时请求构建，不承担独立持久化职责。

## LearningEvent

### 当前事件类型

`LearningEventType`（`constants.py`）：

- `NODE_COMPLETED` / `NODE_STARTED`
- `BLOCKER_FOUND`
- `EVIDENCE_ATTACHED`
- `CONTINUATION_UPDATED`
- `SESSION_REFLECTED`
- `RECALL_SCHEDULED` / `RECALL_COMPLETED`
- `INTAKE_COMPLETED` / `DIAGNOSE_COMPLETED`

### 事件来源

事件抽取仍以启发式规则为主（`signal_extractor.py`），不是独立 agent loop：从 `final_text` 识别完成态、从 `user_message` 识别 blocker、从 `source_references` 和 `tool_events` 附加 evidence。此外 `BoardSnapshotDeriver` 会按间隔用 LLM 重推 BoardFacts，修正回合级 patch 的偏差。

### 事件对 Board 的影响

`apply_events()` 会：`NODE_COMPLETED` 追加到 `completed_node_ids`；`CONTINUATION_UPDATED` 更新 continuation；`BLOCKER_FOUND` 追加到 `critical_blockers`；`EVIDENCE_ATTACHED` 追加到 `evidence_refs`。每次 `apply_events()` 生成新的 `BoardFacts`：`board_version` 加一，`updated_at` 刷新为 UTC 时间。

## after_turn 产物

`after_turn_payload()` 当前会产出：`review_summary`、`continuation_prompt`、`review_to_persist`、`turn_mode_after`、`turn_mode_before`、`board_after`、`learning_events`、`board_patch`、`plan_patch`、`learning_board`、`continuation_retrieval_hint`、`memory_events`。

其中 `board_patch` 是 WebSocket 和前端可消费的最小增量块，包含 `current_turn_mode`、`board_version`、`updated_at`、`continuation`、`current_progress`、`student_snapshot`、`gaps_and_blockers`、`evidence_refs`、`learning_plan`、`learning_board`。

## Session 持久化的相关字段

`LearningSession`（`colearn/sessions/store.py`）上与学习状态相关的字段：

- `mode`（`chat` / `learning`）
- `turn_mode`（默认 `PAUSED`）
- `learning_phase`（默认 `ready`）
- `profile`（intake 采集到的用户画像）
- `next_recall`（schedule-recall 写入的下次召回计划）
- `board_facts`、`board_version`、`continuation_prompt`、`created_at`、`updated_at`

## 与 LearningTurnRequest 的关系

`LearningTurnRequest` 仍是 runtime 唯一请求契约，携带 `board_facts`、`turn_policy`、`state_projection`、`source_references`、`memory_references`、`enabled_tools`、`model_preset`、`metadata`。

需要注意：

- `retrieval_bundle` 字段仍存在于 contract 中
- 主链以 tool-mode retrieval 为主，不会在回合开始前把真实 retrieval 文本强塞进 request
- source readiness 通过 `metadata["source_profile"]` 进入 prompt

## 当前边界与已知限制

### 已接入的能力

- 事件抽取：除启发式兜底外，`BoardSnapshotDeriver` 已按间隔用 LLM 重推 BoardFacts
- `board_version` stale write 保护：`WritebackStage` 在冲突时跳过写入并记录 warning
- Session AutoCompact、Dream 后台合并、AgentHook 真流式、Model Preset 切换均已接入
- 双模式（Chat / Learning）与五段 Learning Phase 已进入主链

### 仍然存在的边界

- `parallel_support` 仍是轻量并行检索闭环，尚未替换为 nanobot `SubagentManager`
- `BoardFacts` 运行时是 dataclass、持久化为 dict，类型边界未完全收紧
- 模型最终回答中的逐条引用尚未反写成完整引用图
- `retrieval_bundle` 仍保留在 request contract 中
- knowledge / settings 仍是本地联调级轻量实现，不是生产级平台能力

这份文档记录的是当前协议事实。后续如果解决上述任一边界，应同步更新本文档。
