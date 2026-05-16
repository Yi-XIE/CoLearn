# CoLearn 学习循环实施手册

日期：2026-05-16  
归属架构层：02-Architecture / 学习循环实施手册

## 文档角色

这份文档是施工手册。

它把 [CoLearn-顶层组装路径.md](D:/Colearn-nightly/CoLearn-docs/02-Architecture/CoLearn-%E9%A1%B6%E5%B1%82%E7%BB%84%E8%A3%85%E8%B7%AF%E5%BE%84.md) 变成可执行的后端组装顺序。

## 当前总原则

后端主链按下面的形状组装：

`装配核心上下文 -> nanobot 跑 ReAct -> 结果返回 -> 异步整理`

这里的重点是：

1. 主路尽量短
2. LightRAG 不前置
3. Product Compression 不上主路
4. Learning Board 只管状态边界和下一动作

## 当前 Lane

- `Current Lane`: Backend Build Mode
- `Goal`: 先把后端学习闭环做成 ReAct 主链，再接前端
- `Now`: 收紧工具接线、状态拦截、异步整理

## 施工原则

### 1. 只有一条执行 loop

唯一执行 loop 永远是 nanobot。

CoLearn 不再额外造“决策 loop”。

### 2. LightRAG 是工具，不是前置层

实现上不要再做：

- 每轮先检索
- 再拼 retrieval bundle
- 再进入 nanobot

正确方式是：

- 把 LightRAG 暴露成 nanobot 可调用 tool
- nanobot 在 ReAct 里自己判断何时调用

### 3. Learning Board 是外部看板

Learning Board 负责：

- 当前状态
- 当前目标
- 下一动作
- 限制条件

不负责：

- 替 agent 做工具选择
- 替 agent 做回合内推理

### 4. Compression 分层

`runtime compression`
- 留在主路
- 极轻量
- 只做 token 容量治理

`product compression`
- 放到后台
- 生成 summary / continuation / review / memory projection

## 当前目标链

当前应该落成的后端链是：

1. 读取 `project / session / Learning Board`
2. 跑 `policy()`，产出本轮边界
3. 做最小 context assembly
4. 做 runtime compression
5. 调 nanobot 单轮执行
6. 流式返回主结果
7. 最小同步写回 `session / board`
8. 异步执行 `review / product compression / memory`

## 分阶段实施

### 阶段 A：收紧 Contract

目标：

- ~~稳定 `LearningTurnRequest`~~
- ~~稳定 `LearningTurnResult`~~
- ~~稳定 `BoardPatch`~~

验收：

1. runtime 入口只吃 `LearningTurnRequest`
2. runtime 出口只吐 `LearningTurnResult`
3. 同步结果和异步结果边界清楚

### 阶段 B：落稳 Learning Board

目标：

- ~~`project / session` 能稳定挂 `Learning Board`~~
- ~~当前状态、下一动作、限制条件可以持久化~~

建议字段：

- `current_state`
- `current_goal`
- `next_action`
- `completed_steps`
- `pending_steps`
- `blocked_steps`
- `continuation_prompt`
- `latest_review`

验收：

1. agent 每轮都能稳定读到 board
2. 回合结束能稳定写回最小 patch

### 阶段 C：把 Policy 收成拦截器

目标：

- ~~`policy()` 不做大规划~~
- ~~只输出本轮约束~~

建议输出：

- `suggested_state`
- `main_goal`
- `next_action`
- `tool_hints`
- `restrictions`
- `warnings`

验收：

1. 当前状态不同，回合规则不同
2. `policy()` 不直接触发检索
3. `policy()` 不直接生成答案

### 阶段 D：把工具箱接进 nanobot

目标：

- ~~Memory 变成 tool~~
- ~~LightRAG 变成 tool~~
- ~~其他 retrieval 能力也走 tool registry~~

实现要求：

1. tool 调用发生在 ReAct 循环里
2. tool 的 observation 回到 nanobot 当前回合
3. 工具层失败时，主链仍可退化继续

验收：

1. 无需检索的问题不会调用 LightRAG
2. 需要资料的问题能在回合内调用 LightRAG
3. Memory 与 LightRAG 可以分别调用

### 阶段 E：接 runtime compression

目标：

- ~~在进入模型前做上下文容量治理~~

负责内容：

- history 截断
- retrieval 片段裁剪
- tool result 压缩
- 长文本裁剪

验收：

1. 长上下文不会直接爆窗
2. 压缩动作毫秒级
3. 压缩不改 Learning Board 的产品含义

### 阶段 F：异步化 Product Compression

目标：

- ~~让摘要、复盘、长期记忆沉淀全部脱离主路~~

建议异步任务：

- `review summary`
- `continuation update`
- `board enrichment`
- `memory projection`

验收：

1. 用户回复不等待这些动作
2. 异步结果最终能回写 project/session/memory

### 阶段 G：最后再接前端

目标：

- 用已经跑通的后端闭环去接 `chat / memory / knowledge`

验收：

1. 前端展示的状态来自 Learning Board
2. 前端看到的回答是 nanobot 主路结果
3. 前端看到的摘要和复盘来自异步整理结果

## 当前代码改造方向

结合当前 nightly 代码，接下来应该往这几个点收：

1. ~~[D:/Colearn-nightly/colearn/app/learning_orchestrator.py](D:/Colearn-nightly/colearn/app/learning_orchestrator.py)  
   从“前置 retrieval orchestration”改成“最小上下文装配 + tool-ready turn orchestration”。~~

2. ~~[D:/Colearn-nightly/colearn/retrieval/adapters/lightrag.py](D:/Colearn-nightly/colearn/retrieval/adapters/lightrag.py)  
   保留 adapter，但角色改成 tool backend，而不是主路固定前置服务。~~

3. ~~[D:/Colearn-nightly/colearn/learning/state_hooks.py](D:/Colearn-nightly/colearn/learning/state_hooks.py)  
   `policy()` 收成轻量规则拦截器。~~

4. ~~`product compression`  
   从同步主链里拆出去，变成后台任务。~~

## 最小闭环判断

当下面 5 条成立，就说明后端最小闭环成立：

1. 用户输入能直接进入 nanobot 单轮 ReAct
2. agent 在回合里可按需调用 Memory / LightRAG
3. 主结果能立即流式返回
4. Learning Board 能同步写回最小状态
5. review / memory / summary 在后台异步落库
