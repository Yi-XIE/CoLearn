# CoLearn 插件化迁移指南

> 配套：[PLUGIN_TECHNICAL_DESIGN.md](./PLUGIN_TECHNICAL_DESIGN.md) / [PLUGIN_IMPLEMENTATION_PLAN.md](./PLUGIN_IMPLEMENTATION_PLAN.md)
>
> 本文档面向**开发者**，描述实施过程中"该做什么 / 怎么验证 / 出问题怎么回滚"。

## 0. 迁移前检查表

实施前确认：

- [ ] 已切到 `插件尝试` 分支（`git branch --show-current` 应输出"插件尝试"）
- [ ] 已读完 [PLUGIN_TECHNICAL_DESIGN.md](./PLUGIN_TECHNICAL_DESIGN.md) §1-3
- [ ] 已读完 [POC_CONTEXTVAR_RESULT.md](./POC_CONTEXTVAR_RESULT.md) 理解 ContextVar 机制
- [ ] 已读完 [COUPLING_EVIDENCE.md](./COUPLING_EVIDENCE.md) 理解当前 10 处耦合
- [ ] 当前 baseline commit 是 `3d8166b`（运行 `git log --oneline | grep baseline`）

## 1. 代码迁移路径表

每个旧文件对应到新插件包的什么位置：

### 1.1 完全迁移（从 `colearn/` 移到 `colearn_plugin/`）

| 旧路径 | 新路径 | Phase |
|---|---|---|
| `colearn/runtime_v2/executor.py` | **删除**（拆解到多个新文件） | 4 |
| `colearn/runtime_v2/tooling.py:ColearnLightRAGTool` | `colearn_plugin/tools/lightrag_query.py` | 2 |
| `colearn/runtime_v2/tooling.py:ColearnMemoryTool` | `colearn_plugin/tools/memory.py` | 3 |
| `colearn/runtime_v2/tooling.py:ColearnWebSearchTool` | `colearn_plugin/tools/web_search.py` | 3 |
| `colearn/runtime_v2/learning_event_tool.py` | `colearn_plugin/tools/learning_event.py` | 3 |
| `colearn/runtime_v2/prompting.py` | `colearn_plugin/pipeline/prompting.py`（去掉对 nanobot ContextBuilder 依赖） | 3 |
| `colearn/runtime_v2/result_bridge.py` | 拆为 `colearn_plugin/adapters/run_result.py` + `colearn_plugin/pipeline/finalize.py` | 3 |
| `colearn/app/stages/preflight.py` | `colearn_plugin/pipeline/preflight.py` | 3 |
| `colearn/app/stages/plan.py` | `colearn_plugin/pipeline/plan.py` | 3 |
| `colearn/app/stages/retrieval.py` | `colearn_plugin/pipeline/retrieval.py` | 3 |
| `colearn/app/stages/finalize.py` | `colearn_plugin/pipeline/finalize.py` | 3 |
| `colearn/app/stages/writeback.py` | `colearn_plugin/pipeline/writeback.py` | 3 |
| `colearn/app/stages/context.py` | `colearn_plugin/pipeline/turn_context.py` | 3 |
| `colearn/app/background_finalizer.py` | `colearn_plugin/runtime/background_finalizer.py` | 3 |
| `colearn/learning/board_hooks.py` | `colearn_plugin/pipeline/learning_logic/board.py` | 3 |
| `colearn/learning/state_hooks.py` | `colearn_plugin/pipeline/learning_logic/state_machine.py` | 3 |
| `colearn/learning/turn_hooks.py` | `colearn_plugin/pipeline/learning_logic/turn_policy.py` | 3 |
| `colearn/learning/retrieval_hooks.py` | `colearn_plugin/pipeline/learning_logic/retrieval_strategy.py` | 3 |
| `colearn/learning/signal_extractor.py` | `colearn_plugin/pipeline/learning_logic/signal_extractor.py` | 3 |

### 1.2 保留在 CoLearn 主仓（数据层与 API 层）

| 路径 | 处理 | 说明 |
|---|---|---|
| `colearn/learning/state.py` | **保留**，插件 re-export | dataclass 定义，避免双源 schema 漂移 |
| `colearn/learning/events.py` | 保留 | 事件类型定义 |
| `colearn/learning/constants.py` | 保留 | 常量 |
| `colearn/sessions/`、`colearn/projects/`、`colearn/memory/`、`colearn/knowledge/` | 保留 | 数据层，被 API 直接使用 |
| `colearn/api/` | 改造但保留 | HTTP 路由层；改为通过 `plugin.get_state_manager()` 读写 |
| `colearn/server.py` | 改造 | 启动时 `CoLearnPlugin.discover_and_install(bot)` |
| `colearn/cli.py` | 改造 | 同 server.py |
| `colearn/storage/` | 保留 | JsonStateStore 仍被 API 用 |
| `colearn/retrieval/` | 大部分保留 | LightRAG 客户端逻辑迁移到插件，service 层保留 |
| `colearn/nanobot_bootstrap.py` | **删除** | 不再需要；插件由 nanobot 自己加载 |

### 1.3 完全删除

| 路径 | 理由 |
|---|---|
| `colearn/runtime_v2/executor.py` | 整个 NanobotTurnExecutor 由插件 hook 取代 |
| `colearn/runtime_v2/profile.py` | nanobot config 路径管理，迁移到插件 |
| `colearn/runtime_v2/context_bridge.py` | ContextVar 由插件统管 |
| `colearn/runtime_v2/learning_closure.py` | 拆到 finalize hook 内 |
| `colearn/runtime_v2/tool_adapters.py` | 工具迁出后无用 |
| `colearn/app/learning_orchestrator.py` | 改为 thin facade 或直接删除（取决于 4.3 任务结论） |
| `colearn/app/source_preflight.py` | 迁到插件 preflight stage |

---

## 2. CoLearn 主仓改造点

### 2.1 server.py 改造

**当前**（伪代码）：
```python
from colearn.runtime_v2.executor import NanobotTurnExecutor

class Server:
    def __init__(self):
        self.executor = NanobotTurnExecutor(workspace=...)
        # ... 各种服务装配

    async def handle_turn(self, request):
        return await self.executor.run_turn_async(request=request)
```

**改造后**：
```python
from nanobot.nanobot import Nanobot
from colearn_plugin import CoLearnPlugin

class Server:
    def __init__(self):
        self.bot = Nanobot.from_config(
            config_path=Path(".colearn/nanobot-with-plugin.config.json"),
            workspace=...,
        )
        # 自动发现并安装插件（包括 CoLearnPlugin）
        self.plugins = CoLearnPlugin.discover_and_install(self.bot)
        self.colearn_plugin = next(p for p in self.plugins if isinstance(p, CoLearnPlugin))

    async def handle_turn(self, request):
        # 把 session_id 写入 ContextVar（SessionBinder 也会兜底，但最早 set 最稳）
        from colearn_plugin.context import set_session_id
        set_session_id(request.session_id)
        result = await self.bot.run(
            request.user_message,
            session_key=request.session_id,
        )
        return self.colearn_plugin.get_state_manager().load_session(
            request.session_id
        ).last_turn_result

    async def shutdown(self):
        for p in self.plugins:
            p.shutdown()
```

### 2.2 API 层改造

**当前**（伪代码）：
```python
# colearn/api/sessions.py
from colearn.sessions.store import SessionStore

@router.get("/sessions/{sid}")
async def get_session(sid: str):
    return SessionStore().load(sid)
```

**改造后**：
```python
# colearn/api/sessions.py
from colearn.api.deps import get_state_manager  # 从 server 注入

@router.get("/sessions/{sid}")
async def get_session(sid: str, sm = Depends(get_state_manager)):
    return await sm.load_session(sid)
```

`get_state_manager()` 返回 `colearn_plugin.state.LearningStateManager`，与旧 `SessionStore` API 兼容（dataclass 字段一致）。

### 2.3 配置文件

新建 `.colearn/nanobot-with-plugin.config.json`：

```json
{
  "model": "deepseek-chat",
  "providers": {
    "deepseek": {"api_key_env": "DEEPSEEK_API_KEY"}
  },
  "tools": {
    "lightrag": {
      "base_url": "http://localhost:9621",
      "api_key": "",
      "timeout_seconds": 30,
      "default_mode": "mix",
      "default_top_k": 5
    }
  },
  "plugins": {
    "colearn": {
      "state_dir": "~/.colearn/state",
      "session_max_idle_seconds": 1800,
      "use_dispatch_wrapper": false
    }
  }
}
```

旧 `nanobot-v0.2-slim.config.json` 在 Phase 4 完成后废弃。

---

## 3. 数据迁移

### 3.1 旧数据格式

CoLearn 当前的状态存储位置（在 [colearn/storage/](../colearn/storage/) 目录管理下）：

```
.colearn/
├── sessions.json             # 所有 session 的 list
├── projects/
│   └── <project_id>.json     # 每个 project 一个文件
└── memory/
    └── events.jsonl          # 事件流
```

### 3.2 新数据格式

```
~/.colearn/state/             # 默认插件 state_dir
├── index.json                # 全局索引
├── sessions/
│   └── <session_id>.json     # 拆分后每个 session 一个文件
└── projects/
    └── <project_id>.json
```

### 3.3 迁移脚本

```bash
# 安装插件包
pip install -e ./colearn_plugin

# 试运行（不写盘，只打印将做什么）
python -m colearn_plugin.migrate \
    --legacy-dir .colearn \
    --new-dir ~/.colearn/state \
    --dry-run

# 正式迁移
python -m colearn_plugin.migrate \
    --legacy-dir .colearn \
    --new-dir ~/.colearn/state

# 验证
python -m colearn_plugin.migrate verify \
    --legacy-dir .colearn \
    --new-dir ~/.colearn/state
# 应输出：OK: 12 sessions, 3 projects, hashes match
```

### 3.4 兼容期双写（可选）

`PluginSettings.legacy_compat=True`（默认 False）时，`StateManager.save_session()` 同时写新格式和旧 `sessions.json`，便于回滚到 Phase 4 之前。两到三个版本后关闭。

---

## 4. 测试验证矩阵

每个 Phase 完成后必须跑通的测试：

### Phase 1
```bash
pytest colearn_plugin/tests/test_context.py -v
pytest colearn_plugin/tests/test_session_binder.py -v
pytest colearn_plugin/tests/test_state_manager.py -v
```
所有用例通过 + ContextVar 50 并发隔离测试无串号。

### Phase 2
```bash
pytest colearn_plugin/tests/test_lightrag_tool.py -v
pytest colearn_plugin/tests/integration/test_lightrag_via_nanobot.py -v
```
真 nanobot bot 上 LLM 能调到 `lightrag_query` 工具。

### Phase 3
```bash
pytest colearn_plugin/tests/test_pipeline_stages.py -v
pytest colearn_plugin/tests/test_hooks_pipeline.py -v
pytest colearn_plugin/tests/test_learning_logic_parity.py -v   # 关键
```
**parity 测试**：插件版 hook 函数与原版逐字段输出一致。

### Phase 4
```bash
# 全仓库不应再 import nanobot
grep -r "^from nanobot\|^import nanobot" colearn/ tests/
# 期望输出：空（或仅在 colearn_plugin/ 包内）

# 完整 turn 端到端
pytest tests/integration/test_full_turn.py -v
pytest tests/integration/test_concurrent_sessions.py -v

# 数据迁移
python -m colearn_plugin.migrate verify --legacy-dir .colearn --new-dir ~/.colearn/state
```

### Phase 5
```bash
pytest -q
pytest --cov=colearn_plugin --cov-report=term-missing
# coverage ≥ 85%

# E2E（需手动跑，需要真 LightRAG + DeepSeek API）
python tests/live_smoke_plugin.py
# 期望：退出码 0，16 项 capability 全 pass
```

---

## 5. 常见问题与排错

### Q1: hook 内 `get_session_id()` 返回 `None`

可能原因：
- `SessionBinder` 没有放在 `_extra_hooks[0]` 位置 → 检查 `plugin.install()` 顺序
- `bot.run()` 调用前没 set ContextVar，且 spec.session_key 也为空 → 检查 server.py 是否传了 `session_key`
- nanobot 升级后 hook 不再在同一 task → 启用 `PluginSettings.use_dispatch_wrapper=True`

排查：
```python
import logging
logging.getLogger("colearn_plugin.session_binder").setLevel(logging.DEBUG)
# 查看 SessionBinder 启动时的日志
```

### Q2: Tool 注册失败 `nanobot.tools` entry_point not found

确认：
```bash
python -c "from importlib.metadata import entry_points; print(list(entry_points(group='nanobot.tools')))"
# 应输出包含 LightRAGQueryTool
```

如果为空：
- 重新 `pip install -e ./colearn-plugin`
- 检查 pyproject.toml `[project.entry-points]` 章节拼写

### Q3: 状态文件冲突（concurrent write）

排查：
```bash
ls ~/.colearn/state/sessions/*.tmp.* 2>/dev/null
# 如有残留 .tmp 文件，说明上次写入崩溃；正常情况下原子写应该清理掉
```

恢复：
- 如有 `.corrupt-<ts>` 备份文件，可手动恢复
- LearningStateManager 加载失败会自动从默认值重建，并打 ERROR 日志

### Q4: nanobot 升级后插件失败

排查清单：
- 看 [COUPLING_EVIDENCE.md](./COUPLING_EVIDENCE.md) 列的 10 处耦合，对应到 `colearn_plugin/adapters/` 检查 adapter 是否需要更新
- 跑 `pytest colearn_plugin/tests/test_hooks_pipeline.py -v` 看哪个 hook 失败
- 查 nanobot CHANGELOG，对照本插件 `pyproject.toml` 的 `nanobot >= X.Y.Z` 版本约束

修复策略：
- 99% 情况只需改 `colearn_plugin/adapters/<某个>.py`
- 极端情况（hook 调用不再在同 task）启用 `dispatch_wrapper`

---

## 6. 回滚操作

### 单 phase 回滚

```bash
# 例：Phase 4 出问题，回到 Phase 3 末
git reset --hard plugin/phase3-state
```

### 完全回滚（撤销整个插件化）

```bash
git reset --hard 3d8166b  # baseline commit
# 删除已建插件包（不影响主仓）
rm -rf colearn_plugin/
```

### 临时降级（不改代码）

```bash
# 关闭单个插件
export COLEARN_DISABLED_PLUGINS=lightrag

# 整体回到旧路径（仅 Phase 4 之前可用）
export COLEARN_PLUGIN_ARCH=off
```

---

## 7. 验收标准（每个 phase 完成的判断标准）

| Phase | 验收标准 |
|---|---|
| 1 | `colearn_plugin/` 可 pip 安装；ContextVar 50 并发隔离测试通过；LearningStateManager 端到端 load/save/reload 通过 |
| 2 | LightRAG 通过 entry_points 自动发现；真 nanobot bot 上 LLM 能调到 `lightrag_query` |
| 3 | 5-stage pipeline 在插件内独立运行；学习逻辑 parity 测试 100% 通过 |
| 4 | 主仓 `grep "import nanobot"` = 0；完整 turn 端到端跑通；数据迁移成功 |
| 5 | 所有测试通过；coverage ≥ 85%；5 篇文档完成；live smoke 退出码 0 |

每个 phase 验收完打 git tag。

---

## 接下来

→ 实施时按 [PLUGIN_IMPLEMENTATION_PLAN.md](./PLUGIN_IMPLEMENTATION_PLAN.md) 走 Phase 1.1
