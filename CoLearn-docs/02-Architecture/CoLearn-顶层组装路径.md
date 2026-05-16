# CoLearn 顶层组装路径

日期：2026-05-16  
归属架构层：02-Architecture / 顶层组装路径

替代关系：
- 本文档替代 `D:\CoLearn-release\CoLearn-docs\02-Architecture\CoLearn-组装执行路径.md`
- 学习状态细则以 [CoLearn-LearningState-协议.md](D:/Colearn-nightly/CoLearn-docs/02-Architecture/CoLearn-LearningState-%E5%8D%8F%E8%AE%AE.md) 为准

## 文档角色

这份文档只回答一件事：

**CoLearn 的顶层主链应该怎么收口。**

它不是实现细节文档，也不负责列施工步骤。施工顺序看
[CoLearn-学习循环实施手册.md](D:/Colearn-nightly/CoLearn-docs/02-Architecture/CoLearn-%E5%AD%A6%E4%B9%A0%E5%BE%AA%E7%8E%AF%E5%AE%9E%E6%96%BD%E6%89%8B%E5%86%8C.md)。

## 顶层结论

CoLearn 的主链不该是传统流水线长鞭。

顶层只保留三步：

`装配核心上下文 -> 丢给 nanobot 跑 ReAct 循环 -> 把结果流式返回`

其他动作全部归到下面两类：

1. 折叠进装配阶段的轻量动作  
   例如会话读取、Learning Board 读取、运行时截断。
2. 从主路剥离出去的异步动作  
   例如学习摘要、长期记忆沉淀、复盘整理。

## 核心架构

CoLearn 的目标架构是：

1. **产品壳**
   - 前端和 API 继续暴露 CoLearn 语义
   - `chat / knowledge / memory / sessions / settings` 仍然是产品入口
2. **Learning Board**
   - 持久化学习看板
   - 记录当前状态、主目标、下一动作、已完成、未完成、阻塞项
3. **nanobot runtime**
   - 唯一执行 loop
   - 真正跑的是一个极简 ReAct 循环
4. **工具箱**
   - Memory tool
   - LightRAG tool
   - 其他后续学习工具
5. **压缩层**
   - runtime compression
   - product compression

一句话概括：

**CoLearn 用 Learning Board 约束回合边界，用 nanobot 跑唯一 ReAct 循环，用工具箱按需取资料。**

这里的学习闭环口径，与 [CoLearn-LearningState-协议.md](D:/Colearn-nightly/CoLearn-docs/02-Architecture/CoLearn-LearningState-%E5%8D%8F%E8%AE%AE.md) 保持一致：

- `Learning Board` 只保存事实
- `policy()` 只产出当轮投影
- `after_turn()` 只提取事件并回写事实

## 主链重定义

旧式表达：

`project -> source -> anchor -> retrieval bundle -> turn -> review -> memory`

不再作为顶层主链表达。

新的顶层表达只有：

### 1. 装配核心上下文

只装这一轮必须知道的最小信息：

- `project`
- `session`
- `Learning Board`
- 最近必要 history
- continuation
- 轻量 runtime compression 结果
- policy 边界

这里的重点是：

- **不默认前置检索**
- **不默认前置 LightRAG**
- **不默认前置产品压缩**

### 2. nanobot 跑 ReAct 循环

nanobot 在这一轮里自己判断：

- 直接回答够不够
- 要不要查 Memory
- 要不要调 LightRAG
- 要不要继续追问用户

所以：

- `LightRAG` 不是每轮固定前置步骤
- `Memory` 也不是每轮固定前置步骤
- 它们都只是工具

### 3. 结果流式返回

用户感知到的主路只应该是：

- 输入发出
- 回答开始流出
- 回合结束

同步主路只做必要写回：

- session 基本结果
- board 最小 patch

重量级整理动作留到后台。

## LightRAG 的定位修正

这是本轮最关键的架构纠偏。

LightRAG 不再定义为：

- 每轮必经的前置检索层

LightRAG 应定义为：

- **nanobot 工具箱里的一个 retrieval tool**

也就是：

```text
用户提问
  -> nanobot 读取当前上下文
  -> 判断是否需要外部资料
  -> 需要时主动调用 LightRAG
  -> 拿到 observation 后继续 ReAct
```

这意味着：

1. 没有检索需求的轮次，不应该为 LightRAG 付额外延迟
2. 有检索需求的轮次，由 agent 在循环内自主决定调用时机
3. LightRAG 对 CoLearn 来说是能力，不是主路关卡

## Policy 的定位修正

`policy()` 不是什么重规划器。

它只是：

**基于 Learning Board 的轻量规则拦截器。**

职责只有三件事：

1. 读取当前 Learning Board
2. 决定这一轮有哪些边界
3. 给 nanobot 的 ReAct 循环加约束

例子：

- 当前处于 `REVIEW`，禁止直接给答案，必须反问
- 当前 `ANCHORING` 未完成，禁止进入深学习解释
- 当前资料未就绪，允许先澄清，不允许假装引用资料

所以 `policy()` 管的是：

- 权限
- 约束
- 边界

它不负责：

- 重规划整条学习路径
- 决定每一步要不要查工具
- 替代 nanobot 做推理

它产出的不是长期状态真相，而是当轮 `turn_mode`、边界、工具权限和回复契约。

## Compression 分层

Compression 必须分成两层。

### runtime compression

这是运行时压缩。

目标：

- 防止 prompt 超长
- 防止窗口爆掉
- 保证这一轮能发给模型

它属于装配阶段的一部分，而且必须很快。

它处理的对象包括：

- history
- retrieval 内容
- tool result
- 长文档片段
- session summary

它只管容量，不管学习流程。

### product compression

这是产品压缩。

目标：

- 生成学习摘要
- 生成 continuation
- 生成 review summary
- 沉淀长期记忆

它不应该阻塞用户这一轮回复。

它必须放到：

- 后台 worker
- 或者回合结束后的异步任务

它只管产品表达，不管 token 预算。

## Learning Board 与 ReAct 的关系

固定关系如下：

```text
Learning Board
  -> policy() 读取边界
  -> 装配最小上下文
  -> nanobot 跑单轮 ReAct
  -> after_turn() 提取 learning events
  -> reducer / patcher 最小写回 board
  -> 后台异步做 review / memory / summary
```

这里没有第二条 agent loop。

Learning Board 是外部看板，nanobot 是唯一执行 loop。

## 成功判断

这条顶层路径成立，必须同时满足：

1. 顶层主链被收成三步，而不是串行长鞭
2. nanobot 是唯一执行 loop，并且跑 ReAct
3. LightRAG 是工具，不是每轮前置关卡
4. runtime compression 在主路里，但足够轻
5. product compression 在主路外异步执行
6. Learning Board 负责边界和下一动作，不负责代替 agent 推理
