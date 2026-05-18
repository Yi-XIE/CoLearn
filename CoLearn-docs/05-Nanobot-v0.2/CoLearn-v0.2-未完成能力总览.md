# CoLearn v0.2 Nanobot 能力状态

这份文档记录 CoLearn 当前采用 nanobot v0.2 的能力状态。它不再作为历史缺口清单使用；已经落地的能力写为当前事实，仍保留的边界写在最后。

## 当前已接入能力

### 1. AgentHook 真流式

CoLearn 的 `NanobotTurnExecutor` 已经使用继承自 `nanobot.agent.hook.AgentHook` 的 stream hook。hook 会声明 `wants_streaming() -> True`，并把 runtime 中的 content delta、reasoning delta、reasoning end、stream end、tool call 和 tool event 写入 CoLearn stream event。

WebSocket turn 执行现在会在后台线程运行 orchestrator，主协程通过线程安全队列实时发送 runtime event。最终结果阶段只补发未实时发送的 fallback event，避免重复。

### 2. Model Presets 自动切换

`TurnPolicy` 会按 turn mode 选择 model preset：

- `EXPLORE` -> `explore`
- `ANCHOR` / `CORRECTION` / `VERIFY` -> `deep`
- `PAUSED` -> 不设置

slim config 已定义 `explore` 和 `deep`，当前都使用 DeepSeek provider 和 `${DEEPSEEK_MODEL}`，只调整 temperature。executor 在设置 preset 前会检查可用 preset；缺失时写 runtime warning，并降级到 `default` 或跳过，不让 turn 崩掉。

### 3. ContextBuilder + SkillsLoader

runtime prompt 由 nanobot `ContextBuilder(workspace).build_system_prompt(skill_names=..., channel="colearn")` 生成基础系统提示。CoLearn 再追加学习上下文，包括项目、turn mode、policy、retrieval focus、prompt support bundle 和用户消息。

WebSocket 的 `skills` 字段已经透传到 `LearningTurnRequest.requested_skills`，最终交给 `ContextBuilder` 加载对应 skills。`COLEARN.md` 会先从 nanobot workspace 读取，缺失时 fallback 到 repo root。

### 4. Lightweight parallel_support

本轮仍不接真正的 `SubagentManager`。当前采用轻量并行检索闭环：从 `retrieval_query_context.final_query`、critical blocker、unverified gap 中取最多 3 个去重 query，并行调用 `RetrievalService.async_build_bundle_for_source_refs()`。

结果写入 `runtime_v2.parallel_support`，并参与 `prompt_support_bundle` 合并。代码边界保留为 `parallel_support`，后续可替换为真正的 `SubagentManager`。

### 5. Dream 后台合并

每轮 writeback 后，CoLearn 会把 turn 摘要追加到 nanobot memory history。达到触发间隔后，优先调用 nanobot Dream 的 `run()` 做长期记忆合并；成功后读取 `MEMORY.md` 摘要并写入 CoLearn `EventMemoryStore` 的 `profile_consolidated` 事件。

Dream 失败不会阻断主 turn，会写 warning 和 `profile_consolidation_failed`。如果 runtime 中没有可用 Dream，则保留旧的 deterministic consolidation 作为兜底。

### 6. Session AutoCompact

长会话超过阈值后，会优先调用 nanobot consolidator 的 `archive(old_messages)` 生成摘要；失败时使用 deterministic summary。压缩后的 system message 带结构化 metadata：

- `colearn_compacted=true`
- `compacted_count`
- `compaction_source`

重复 compact 时只保留一个 compacted system summary，并保留最近 12 条消息。

### 7. MCP 只读工具

slim config 已声明 `colearn-ext` MCP server，命令为 `python -m colearn.mcp_server`。该 server 暴露只读工具：

- `list_projects`
- `get_project`
- `list_sessions`
- `search_memory`
- `retrieve_project_context`

MCP server 使用统一 path helpers 读取 repo `.colearn/state` 和 repo workspace，避免启动 cwd 改变状态源。工具保持只读，不通过 MCP 修改 CoLearn 状态。

## 运行路径约定

CoLearn 通过 `colearn.paths` 统一解析路径：

- repo root：优先 `COLEARN_REPO_ROOT`，否则从 Python 包路径推导
- JSON state root：优先 `COLEARN_STATE_ROOT`，否则 `.colearn/state`
- nanobot workspace：优先 `COLEARN_NANOBOT_WORKSPACE`，否则 `.colearn/nanobot-workspace`
- env file：repo root 下的 `.env`

`scripts/start-colearn-v2-gateway.ps1` 会显式设置这些环境变量，让 gateway 和 MCP 子进程使用同一套状态源。

## 仍保留的边界

- 真正的 nanobot `SubagentManager` 未接入；当前只有 `parallel_support` 轻量闭环。
- LearningState 事件抽取仍是启发式规则，不是独立状态机或 review agent。
- `BoardFacts` 在运行时和持久化层仍是双重表示。
- `board_version` 有 stale write 保护，但不是严格 compare-and-swap。
- `retrieval_evidence_map` 已经目标化，但尚未把模型最终回答中的逐条引用反写成完整引用图。
- 认证、knowledge task、settings diagnostics 仍是本地联调用轻量实现，不是生产级平台能力。

## 当前维护规则

- 这份文档只记录当前事实和仍存在的工程边界。
- 已落地能力不要再写成待接入。
- 如果后续接入真正 `SubagentManager`、强类型 Board 存储、严格版本写入或完整引用图，需要同步更新本文档和顶层组装路径文档。
