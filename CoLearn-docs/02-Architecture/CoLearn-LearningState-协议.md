# CoLearn LearningState 协议

日期：2026-05-16  
归属架构层：02-Architecture / LearningState 协议

## 目标

CoLearn 的 LearningState 不再是一个单独的持久化状态值，而是由三层组成：

1. `Learning Board`：唯一事实来源，只保存事实
2. `Turn Policy`：每轮开始时计算出的临时投影
3. `Learning Events`：每轮结束后提取的结构化事件

核心原则：

- Board 只记事实，不记策略
- Policy 只管当轮边界，不管长期真相
- Events 只负责回写事实，不直接代表最终状态
- 唯一执行 loop 是 nanobot

## 总体流程

```text
Learning Board
  -> policy() 读取 board facts
  -> before_turn() 注入 board facts + turn policy
  -> nanobot 执行单轮 ReAct
  -> after_turn() 提取 learning events
  -> reducer / patcher 更新 Learning Board
```

## 三层模型

### 1. Board Facts

Board Facts 描述的是持久化事实，回答这些问题：

- 学习进行到哪里了
- 已经完成了什么
- 当前卡点是什么
- 下一轮决策依赖哪些客观事实

当前代码里的核心字段：

- `project_id`
- `session_id`
- `board_version`
- `updated_at`
- `current_progress`
- `student_snapshot`
- `gaps_and_blockers`
- `continuation`
- `evidence_refs`

`current_progress` 里保存路径与完成节点；`student_snapshot` 保存最近学习快照；`gaps_and_blockers` 保存 blocker 和未验证 gap；`continuation` 保存跨回合续接信息。

### 2. Turn Policy

`policy(board)` 是每轮开始前的轻量规则翻译器，输出的是当轮投影，不是长期状态。

当前代码里的核心输出：

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

推荐的 `turn_mode` 仍然保持四类：

- `ANCHOR`
- `CORRECTION`
- `VERIFY`
- `EXPLORE`

### 3. Learning Events

`after_turn()` 从 `user input + tool outputs + final response` 中提取事件，再用 reducer 更新 Board。

当前事件类型以这些为主：

- `CONTINUATION_UPDATED`
- `NODE_STARTED`
- `NODE_COMPLETED`
- `BLOCKER_FOUND`

事件不是 Board 本体，只是 Board 的输入。

## 代码对照

当前实现已经接上的关键入口：

- `colearn.learning.state`：定义 `BoardFacts`、`TurnPolicy`、`LearningEvent`
- `colearn.learning.state_hooks`：定义 `extract_board_facts()`、`policy()`、`build_turn_context()`、`after_turn()`、兼容入口 `before_turn()` 和 `after_turn_payload()`
- `colearn.runtime.context_bridge`：把学习上下文装进 `LearningTurnRequest`
- `colearn.runtime.turn_executor`：消费 turn request 并调用 nanobot
- `colearn.app.learning_orchestrator`：串起读板、投影、执行、回写
- `colearn.compression.product`：负责异步的 review / continuation / board patch 产出

## 约束

- `policy()` 不做大规划
- `policy()` 不直接生成答案
- `before_turn()` 只做上下文装配与边界注入
- `after_turn()` 只提取事件并更新 Board
- `product compression` 放在主链路之外
- `LightRAG` 是工具，不是默认前置层

## 现状判断

这一版协议的目标不是再造一个状态机，而是把 LearningState 统一成一条可执行闭环：

1. Board 作为事实源
2. Policy 作为当轮投影
3. nanobot 作为唯一执行器
4. Events 作为回写输入
5. 异步压缩负责 review / continuation / memory projection

如果后续要继续演进，优先补的是：

- Board 的并发写回控制
- 事件更细粒度的抽取
- 前端对 Board 状态的展示
- 更稳定的 review / continuation 结构化产物
