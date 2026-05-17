# CoLearn v0.2 未完成能力总览

这份文档只记录当前还没接入、但仍值得继续做的能力。每一项都按「现状 / nanobot 提供的能力 / 接入方案 / 收益」展开。

## 1. AgentHook 流式接入

### 现状

CoLearn 现在在 `colearn/runtime_v2/executor.py` 里直接调用 `bot.run()`，之前没有把自定义 hook 传进去。前端能看到的 thinking、tool_call、result 事件，主要是 `colearn/api/app.py` 里对 `result.stream_events` 的二次拼装，不是 LLM 运行时真正吐出来的流式事件。

### nanobot 提供的能力

nanobot 的 `AgentHook` 已经把完整的 turn 生命周期暴露出来了，包括 `before_iteration`、`on_stream`、`before_execute_tools`、`on_stream_end`、`after_iteration`。它还内置了 `AgentProgressHook`，能把 runner 层事件适配成前端可消费的 progress 流。

### 接入方案

这一项基本只动 1 个文件：`colearn/runtime_v2/executor.py`。当前已经开始实施，下一步就是把这条流接到 `app.py` 的 websocket / SSE 输出里。

做法是自定义一个 `CoLearnStreamHook(AgentHook)`，把 runner 的 delta、tool call、reasoning 直接写入 CoLearn 的 stream event channel，再把这个 hook 传给 `bot.run(..., hooks=[hook])`。

```python
from nanobot.agent.hook import AgentHook

class CoLearnStreamHook(AgentHook):
    def __init__(self, emit):
        self.emit = emit

    async def on_stream(self, ctx, delta: str):
        self.emit({"type": "thinking", "content": delta})

    async def before_execute_tools(self, ctx):
        for tool_call in ctx.tool_calls:
            self.emit({
                "type": "tool_call",
                "tool_name": tool_call.name,
                "args": tool_call.arguments,
            })
```

然后 `executor.py` 里把 `hooks=[CoLearnStreamHook(...)]` 传下去，`app.py` 里现有的 `_prepare_runtime_stream_events()` 可以逐步退成兜底逻辑。

### 收益

- 前端看到的是真实运行时流，不是事后合成结果。
- tool call、reasoning、stream_end 的时序会更准。
- `app.py` 里的后处理逻辑可以明显变薄。

## 2. Model Presets 自动切换

### 现状

CoLearn 现在的模型选择基本是静态的，来自 `slim config` 和运行配置。虽然 `turn_mode` 已经在 `colearn/learning/state_hooks.py` 里算出来了，但它还没有真正驱动 runtime 自动切 preset。当前已经开始把 `turn_mode -> model_preset` 的链路打通。

### nanobot 提供的能力

nanobot 的 `AgentLoop` 原生支持 `set_model_preset(name)`，切的是当前运行中的 provider snapshot，不需要重启，也不会影响正在跑的 turn。相关 preset 定义来自 `nanobot/config/schema.py` 的 `model_presets`，并由 `nanobot/agent/model_presets.py` 负责解析和归一化。

### 接入方案

这项也尽量只动 2 个文件：

- `colearn/learning/state_hooks.py`
- `colearn/runtime_v2/executor.py`

在 `state_hooks.py` 里，把 `turn_mode` 映射成 `model_preset`，然后穿进 `LearningTurnRequest`：

```python
def resolve_model_preset(turn_mode: str) -> str | None:
    return {
        "EXPLORE": "explore",
        "ANCHOR": "deep",
        "CORRECTION": "deep",
        "VERIFY": "deep",
    }.get(turn_mode)
```

然后把这个值放进 `TurnPolicy` 或 `LearningTurnRequest`。

在 `executor.py` 里，拿到 request 后先设 preset，再跑 turn：

```python
if request.model_preset:
    bot._loop.set_model_preset(request.model_preset)
result = await bot.run(prompt, session_key=..., hooks=[...])
```

配套上，`slim config` 里补一个 `modelPresets` 段即可，CoLearn 不需要改整个模型体系。

当前这条链路已经开始实施，接下来主要是把 `modelPresets` 配置和 runtime 的默认 preset 名称对齐。

### 收益

- `turn_mode` 可以直接驱动模型强弱切换。
- 探索用快模型，锚定 / 纠错 / 校验用强模型，成本更可控。
- 不用改配置文件重启，交互会顺很多。

## 3. ContextBuilder + SkillsLoader 复用

### 现状

CoLearn 现在在 `colearn/runtime_v2/prompting.py` 里自己拼 prompt，身份、工具说明、skills、记忆、上下文结构都要手工维护。

### nanobot 提供的能力

nanobot 的 `ContextBuilder.build_system_prompt()` 会自动组合 identity、SOUL.md、USER.md、TOOLS.md、skills 和 memory；`SkillsLoader` 还能自动扫描 workspace 和内置 skills 目录，把 `SKILL.md` 注入到系统 prompt。

### 接入方案

主要改 `colearn/runtime_v2/prompting.py`。

先用 nanobot 的 `ContextBuilder` 生成基础 system prompt，再叠加 CoLearn 的学习上下文：

```python
from nanobot.agent.context import ContextBuilder

def build_turn_prompt(request, workspace):
    base = ContextBuilder(workspace).build_system_prompt()
    learning_lines = [
        f"Project: {request.project_title}",
        f"Turn mode: {request.turn_mode}",
        ...
    ]
    return base + "\n\n## Learning Context\n" + "\n".join(learning_lines)
```

如果后续要让 CoLearn 也吃自己的说明文件，可以在 workspace 里补一份 `COLEARN.md`，不需要再手搓整套 prompt 模板。

### 收益

- prompt 结构更统一。
- identity、skills、memory 不用 CoLearn 自己重复维护。
- 后续接 skill 或改说明文件，成本更低。

## 4. SubagentManager 并行化

### 现状

CoLearn 现在还是串行执行：先跑主 LLM，再按需调用 `memory`、`lightrag` 等工具。并行检索、并行验证、独立 review agent 都还没正式接上。

### nanobot 提供的能力

nanobot 的 `SubagentManager` 可以派生独立子 agent，每个子 agent 都能有自己的 provider、model、tool registry 和 `max_iterations`。它适合做并行检索、并行验证、后台追问这类任务。

### 接入方案

这项更像中期优化，建议先把它落在 `colearn/app/learning_orchestrator.py` 或工具层封装里，而不是直接塞进主 prompt 流程。

一个比较稳的切法是先把 `lightrag` 扩成并行检索工具，再考虑真正引入子 agent：

```python
async def execute(self, questions: list[str]):
    async with asyncio.TaskGroup() as tg:
        tasks = [tg.create_task(retrieve_one(q)) for q in questions[:3]]
    return [t.result() for t in tasks]
```

如果要更彻底，再把 review validator 或 web search 拆成子 agent，让主 agent 只负责汇总结果。

### 收益

- 检索和验证可以并行，延迟更低。
- 后续能自然支持多角度 review。
- 主 agent 负担更小，推理路径也更清楚。

## 5. Dream 后台合并

### 现状

CoLearn 的 `EventMemoryStore` 现在是 append-only，只会往里加 turn 事件，不会自动把多轮记忆压缩、归纳成长期 profile。

### nanobot 提供的能力

nanobot 的 `Dream` 能定期读取 MEMORY.md，把零散记忆合并成更稳定的结构化总结。它更适合做长期记忆、阶段性画像和历史压缩。

### 接入方案

这项可以先不直接抄 nanobot 的 cron，而是在 `colearn/app/learning_orchestrator.py` 里加一个轻量触发：

```python
if len(self.memory_store.list_events()) % 20 == 0:
    summary = self._dream_consolidate()
    self.memory_store.write_profile(summary)
```

如果后面要更标准化，再考虑把 `EventMemoryStore` 对接到类似 `Dream` 的合并器。

### 收益

- 长期记忆不会无限膨胀。
- 学习者画像更稳定。
- 后续检索会更像“提炼后的经验”，而不是原始流水账。

## 6. Session AutoCompact

### 现状

当前 `LearningSession.messages` 会持续增长，没有自动压缩机制。现在主要靠 `continuation_prompt` 和 writeback 维持上下文，但长会话还是会越来越长。

### nanobot 提供的能力

nanobot 的 `AutoCompact` 会在会话超过阈值后自动压缩历史消息，把旧上下文替换成摘要，避免 context window 被撑爆。

### 接入方案

这项适合放在 `colearn/app/learning_orchestrator.py`。

可以先做一个很轻的版本，只压缩旧消息的一半：

```python
if len(session.messages) > MAX_HISTORY_MESSAGES:
    old = session.messages[: len(session.messages) // 2]
    summary = self._compact_messages(old)
    session.messages = [{"role": "system", "content": summary}] + session.messages[len(session.messages)//2:]
```

后面如果要更完整，再考虑接 nanobot 的 consolidator 逻辑。

### 收益

- 长会话更稳，不容易顶到 context 上限。
- token 成本更可控。
- 用户不会因为历史太长而明显变慢。

## 7. MCP 工具接入

### 现状

CoLearn 现在的工具是硬编码的，主要是 `memory` 和 `lightrag`。新增工具就要改代码注册，扩展性还不够好。

### nanobot 提供的能力

nanobot 的工具系统原生支持 MCP server 动态接入，能把外部工具按协议注册进 registry，后续 agent 就能直接调用。

### 接入方案

建议先在 `slim config` 里声明 MCP server，再在 `colearn/runtime_v2/tooling.py` 里保留 registry 接口。

```json
{
  "tools": {
    "mcpServers": {
      "colearn-ext": {
        "command": "python",
        "args": ["-m", "colearn.mcp_server"]
      }
    }
  }
}
```

然后再补一个 `colearn/mcp_server.py`，把项目查询、知识检索、外部扩展能力暴露出去。

### 收益

- 工具扩展不再依赖硬编码注册。
- 第三方能力可以按协议接入。
- 后续补知识源、图表、辅助验证工具会更顺。

## 接入优先级

1. `AgentHook`
1. `Model Presets`
1. `ContextBuilder + SkillsLoader`
1. `Session AutoCompact`
1. `Dream`
1. `SubagentManager`
1. `MCP`
