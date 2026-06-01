# CoLearn v0.2 nanobot 原生能力接入总览

这份文档记录 CoLearn 对 nanobot 原生能力的接入情况。原计划列了 7 项，其中前 5 项已接入主线，后 2 项仍未接入。

## 接入状态一览

| # | 能力 | 状态 | 落点 |
|---|---|---|---|
| 1 | AgentHook 流式 | ✅ 已接入 | `colearn/runtime_v2/executor.py` `_StreamHook` |
| 2 | Model Presets 自动切换 | ✅ 已接入 | `executor._apply_model_preset` + `board_hooks.resolve_model_preset` |
| 3 | ContextBuilder 复用 | ✅ 已接入 | `colearn/runtime_v2/prompting.py` |
| 4 | Session AutoCompact | ✅ 已接入 | `WritebackStage` + `stages/utils.build_compaction_summary` |
| 5 | Dream 后台合并 | ✅ 已接入 | `WritebackStage._maybe_consolidate_memory` |
| 6 | SubagentManager 并行化 | ⏳ 未接入 | 当前仅 `RetrievalStage` 的轻量 `parallel_support` |
| 7 | MCP 工具接入 | ⏳ 未接入 | slim config `mcpServers` 为空 |

---

## 1. AgentHook 流式 — ✅ 已接入

`executor.py` 定义了 `_StreamHook(AgentHook)`，实现 `on_stream` / `on_stream_end`，把 runtime 的 delta、reasoning、tool call 实时写入 CoLearn 的 stream event channel，并在 `bot.run(..., hooks=[self._StreamHook(emit_stream_event)])` 时传入。前端看到的是真实运行时流，而不是事后合成。

## 2. Model Presets 自动切换 — ✅ 已接入

`board_hooks.resolve_model_preset(turn_mode)` 把 `turn_mode` 映射成 preset，写进 `TurnPolicy.model_preset` 与 `LearningTurnRequest`。`executor._apply_model_preset()` 在跑 turn 前调用 `loop.set_model_preset()`，并对 preset 缺失 / runtime 不支持 / 应用失败的情况写 `_runtime_warnings` 兜底，不中断回合。

## 3. ContextBuilder 复用 — ✅ 已接入

`prompting.py` 用 `ContextBuilder(workspace).build_system_prompt()` 生成基础 system prompt，再叠加 CoLearn 学习上下文。identity / memory 等不再由 CoLearn 手搓整套模板。workspace 下的 `COLEARN.md` 也参与基础 prompt。

## 4. Session AutoCompact — ✅ 已接入

`WritebackStage` 按 `SESSION_AUTOCOMPACT_MAX_MESSAGES` / `SESSION_AUTOCOMPACT_KEEP_TAIL` 阈值触发压缩，旧消息用 `build_compaction_summary()` 收成摘要，保留尾部若干条，避免长会话顶到 context 上限。阈值来自 `colearn/config/defaults.py`。

## 5. Dream 后台合并 — ✅ 已接入

`WritebackStage._maybe_consolidate_memory()` 取 nanobot loop 上的 `dream`，按 `DREAM_CONSOLIDATION_EVENT_INTERVAL` 间隔调用 `dream.run()` 做长期记忆合并。同时 `BoardSnapshotDeriver` 按 `BOARD_DERIVATION_EVENT_INTERVAL` 间隔重推 BoardFacts。Chat Mode 不调度这些学习型后处理。

---

## 6. SubagentManager 并行化 — ⏳ 未接入

### 现状

当前并行能力只体现为 `RetrievalStage` 的轻量 `parallel_support`（一组检索查询的并行 dispatch），没有真正派生独立子 agent。并行验证、独立 review agent 仍未接。

### 接入方向

先把 `parallel_support` 升级为基于 nanobot `SubagentManager` 的并行检索 / 验证，再考虑把 review validator 或 web search 拆成子 agent，主 agent 只负责汇总。这属于中期优化，不在当前主链。

## 7. MCP 工具接入 — ⏳ 未接入

### 现状

工具仍是硬编码注册（`memory` / `lightrag` / `web_search`，见 `colearn/runtime_v2/tooling.py`），slim config 的 `tools.mcpServers` 为空。

### 接入方向

在 slim config 声明 MCP server，在 `tooling.py` 保留 registry 接口，再补一个 `colearn/mcp_server.py` 暴露项目查询 / 知识检索 / 外部扩展能力。新增工具不再依赖改代码注册。

---

## 后续优先级

剩余两项中，`SubagentManager` 优先级高于 `MCP`：前者能直接降低检索 / 验证延迟并支持多角度 review，后者更偏生态扩展，可在工具需求明确后再做。
