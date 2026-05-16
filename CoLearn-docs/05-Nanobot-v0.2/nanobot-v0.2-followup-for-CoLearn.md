# CoLearn 对 nanobot v0.2.0 的跟进建议

本文记录 CoLearn 面向 `nanobot v0.2.0` 的跟进重点。目标不是追热点，而是判断哪些代码和架构变化值得我们拿来用，哪些只需要预留位置。

当前判断基于 `nanobot` 主线的公开更新信号：

- `chore(release): bundle webui into wheel and prep 0.2.0`
- 跨多轮持续推进目标
- 基于 `gpt-image-2` 的图像生成链路
- WebUI 打进 wheel
- 新 provider 与自动兜底
- Agent loop 重构

## 总体判断

`nanobot v0.2.0` 的意义不是单个功能变强，而是产品形态变得更完整。

它正在从“可编程 agent runtime”进一步走向“可开箱使用的个人 AI Agent 产品底座”。这和 CoLearn 当前方向高度相关：我们也在从局部联调、前端外壳、后端主链，走向一个更一体、更能持续推进学习目标的工作台。

CoLearn 不应该简单同步所有能力。更合理的策略是：

1. 优先吸收 WebUI 一体化的发布方式。
2. 重点研究多目标推进和 Agent loop 的状态组织方式。
3. provider fallback 作为稳定性能力纳入中期计划。
4. 图像生成只保留教学接口位，当前不做完整产品化。

## 1. WebUI 一体化

### 为什么重要

`nanobot v0.2.0` 把 WebUI 打进 wheel，这代表它不再把前端当作独立 demo，而是作为产品交付的一部分。

这对 CoLearn 很关键。我们现在有 `web/` 前端和 `colearn/api` 后端，已经能联调，但交付形态仍偏“两个服务并排跑”。如果 nanobot 的 WebUI 打包方式成熟，我们可以直接借它的方式，把 CoLearn 从“前端套壳”推进到“安装后可直接打开的学习工作台”。

### CoLearn 应该跟进什么

- 分析 nanobot wheel 中 WebUI 的目录组织、构建产物放置方式、静态文件服务方式。
- 判断 CoLearn 是否可以把 `web` build 产物挂到 FastAPI 静态路由下。
- 保留独立开发模式，但增加一体化运行模式。
- 明确本地开发、联调、打包发布三种启动路径。

### 建议的第一步

拿到 `nanobot v0.2.0` 代码后，优先看这些区域：

- `pyproject.toml`
- package data / wheel include 配置
- WebUI build 输出目录
- 后端静态文件路由
- CLI 启动入口

### CoLearn 侧落点

中期目标可以定义为：

```text
python -m colearn
```

或：

```text
colearn
```

启动后同时提供 API 和前端页面。

## 2. 多目标推进

### 为什么重要

CoLearn 的核心不是聊天，而是学习推进。多目标推进和我们的 LearningState、项目、会话、记忆、资料源天然贴合。

如果 nanobot v0.2.0 已经把“跨多轮持续推进目标”作为明确能力，我们应该研究它如何表达目标、如何切分任务、如何在多轮中判断继续、暂停、完成或改道。

### CoLearn 应该跟进什么

- 把单轮 `LearningState` 扩展成可挂载多个目标的结构。
- 为每个目标保存状态：`pending`、`active`、`blocked`、`completed`、`archived`。
- 让学习会话可以同时承载主目标和支线目标。
- 让记忆与资料源能绑定到具体目标，而不是只绑定到整个会话。

### 暂不急着做什么

暂时不要把 CoLearn 做成泛任务管理器。

多目标推进应该服务学习，而不是把产品带偏成 Todo 工具。目标应该围绕学习任务、资料理解、项目推进、课程设计等场景。

### CoLearn 侧建议结构

可以先设计一个轻量协议：

```text
LearningGoal
- id
- title
- status
- parent_goal_id
- evidence_refs
- memory_refs
- source_refs
- next_action
```

后续再决定是否正式落库。

## 3. Agent Loop 重构

### 为什么重要

Agent loop 是系统的心脏。它决定一轮任务如何开始、上下文如何进入、工具如何执行、结果如何回写、下一轮如何接上。

`nanobot v0.2.0` 的 loop 重构值得认真对照，尤其是它刚修过 `runtime context injection` 的重复注入问题。这说明它正在整理上下文进入 loop 的时机和边界。

### CoLearn 应该重点看什么

- loop 是否拆分成 plan / act / observe / respond / persist 等阶段。
- runtime context 在什么时候注入。
- 工具结果如何回到模型上下文。
- 多轮 drain 或 stream 过程中如何避免重复上下文。
- 中途失败后如何恢复。
- 状态写回是否发生在统一位置。

### CoLearn 当前风险

我们现在已经有学习状态、记忆、source readiness、WebSocket 主链。随着能力继续增加，最容易出问题的是：

- 上下文重复注入
- 工具结果和学习状态写回分散
- 一轮执行中途失败后状态不一致
- 前端看到的状态和后端真实状态不同步

所以这次跟进 nanobot loop，不只是为了升级能力，也是为了提前避免 CoLearn 后面长复杂后的结构债。

### CoLearn 侧建议

先做一份 loop 对照表：

```text
nanobot v0.2 loop 阶段
CoLearn 当前对应模块
是否已有
是否需要迁移
风险备注
```

这份表完成后，再决定是否改代码。

## 4. Provider 与自动兜底

### 为什么重要

新增 provider 和自动兜底说明 nanobot 在补真实可用性。对 CoLearn 来说，这会影响设置页诊断、模型选择、失败恢复和教学场景稳定性。

### CoLearn 应该跟进什么

- settings diagnostics 不只测试单个 provider，还能测试 fallback 链。
- provider 能力要显式声明，例如：文本、工具调用、图像生成、thinking control。
- 失败时返回可解释的错误，而不是让前端卡住。
- 未来支持“首选模型 + 备用模型”的配置。

### 暂定优先级

provider fallback 值得做，但不应该抢在 WebUI 一体化和 Agent loop 对照之前。

## 5. 图像生成接口预留

### 为什么现在不做完整功能

图像生成对 CoLearn 很有价值，尤其是教学图、学具草图、课程讲解图、概念可视化。但当前主线更重要的是学习闭环、WebUI 一体化和 loop 稳定。

所以现在不急着做完整图像生成产品功能。

### 但应该先留接口

建议预留一个能力边界：

```text
TeachingImageGeneration
- prompt
- learning_context
- source_refs
- style_intent
- output_asset
- provenance
```

它可以先不接真实模型，只定义接口和未来位置。

### 未来教学场景

后续可以支持：

- 课程概念图
- 学具结构草图
- 实验步骤图
- 板书辅助图
- 学习卡片配图

这部分一旦接入，不应该只是“生成图片”按钮，而应该被学习状态和资料源驱动。

## 代码拿取与使用边界

等 `nanobot v0.2.0` 代码稳定后，CoLearn 可以按以下顺序拿代码：

1. 先拉取上游代码，保留独立对照分支。
2. 只读分析 WebUI 打包、loop、provider 三块。
3. 把可直接复用的代码隔离到 `third_party/nanobot-core` 或新的 vendor 目录。
4. 不直接覆盖 CoLearn 当前主链。
5. 先做文档对照，再做小范围代码迁移。

建议分支名：

```text
sync/nanobot-v0.2-analysis
```

建议本地目录：

```text
third_party/nanobot-v0.2
```

## 第一轮执行清单

拿到代码后，第一轮只做分析，不急着合并：

1. 记录 WebUI wheel 打包方式。
2. 画出 nanobot v0.2 Agent loop 阶段图。
3. 找出多目标推进的数据结构和状态流。
4. 标出 provider fallback 的入口和错误处理方式。
5. 写 CoLearn 迁移建议，不直接动主链。

## 当前结论

CoLearn 应该跟进 `nanobot v0.2.0`，但跟进方式要克制。

最值得立刻研究的是 WebUI 一体化和 Agent loop 重构。多目标推进要提前设计协议。图像生成要留接口，但先不做产品化。

这次更新对 CoLearn 是一次很好的外部参照：它证明个人 AI Agent 正在从能力展示走向可交付产品，而 CoLearn 可以沿着学习工作台的方向，把这条路走得更具体。
