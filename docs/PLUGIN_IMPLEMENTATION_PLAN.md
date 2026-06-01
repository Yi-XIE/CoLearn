# CoLearn 插件化实施计划

> 配套文档：[PLUGIN_TECHNICAL_DESIGN.md](./PLUGIN_TECHNICAL_DESIGN.md)
> 总工作量：**13 个工作日**，5 个阶段
> 策略：**直接替换**（不做并行运行/feature flag）

## 路线图概览

```
Phase 1 (2d)  基础设施: 插件骨架 + ContextVar + 状态管理器
   │
Phase 2 (3d)  LightRAG 插件化: Tool + 配置 + 子进程托管迁移
   │
Phase 3 (4d)  学习状态插件化: Hook 实现 + 5-stage 迁移
   │
Phase 4 (2d)  集成: nanobot 安装 + CoLearn 主仓改造
   │
Phase 5 (2d)  测试 + 文档: 完整测试矩阵 + 5 篇文档 + README
```

每个 phase 末尾打一个 git tag (`plugin/phase1-infra` 等)，单独可回退。

---

## Phase 1 — 基础设施（2 天）

**目标**：插件包骨架 + ContextVar 机制 + 状态管理器，**不修改任何 nanobot/CoLearn 现有代码**。

### Tasks

| # | 任务 | 创建文件 | 测试标准 |
|---|---|---|---|
| 1.1 | 建插件包骨架 | `colearn_plugin/{__init__.py, plugin.py, config/{defaults.py, settings.py}, pyproject.toml, README.md}` | `pip install -e ./colearn_plugin` 成功 |
| 1.2 | 实现 ContextVar 模块 | `colearn_plugin/context.py` | `tests/test_context.py`：50 个 asyncio.gather 并发 + nested set/reset 隔离正确 |
| 1.3 | 实现 SessionBinder | `colearn_plugin/hooks/session_binder.py` | `tests/test_session_binder.py`：从 spec.session_key / messages metadata 三段降级提取 |
| 1.4 | 实现 LearningStateManager | `colearn_plugin/state/{manager.py, store.py, models.py, records.py, cache.py, migrations/v0_to_v1.py}` | `tests/test_state_manager.py`：原子写、并发读写、损坏文件恢复 |
| 1.5 | 实现 PluginSettings + 默认配置 | `colearn_plugin/config/settings.py` | `tests/test_settings.py`：env / 文件 / 默认值优先级 |

### Deliverables

- `colearn_plugin/` 完整骨架，pip 可安装
- ContextVar 在 `gather` / `TaskGroup` / `to_thread` 下并发隔离测试通过
- LearningStateManager 端到端 load → save → reload 等价

### Risks

- ContextVar 在 `run_in_executor` 中需显式 `copy_context().run()`——已在 §3.4 兜底方案文档化
- pyproject.toml 的 entry_points 暂不注册（避免 nanobot 启动时被自动发现失败干扰），Phase 4 再开

### Tag

`plugin/phase1-infra`

---

## Phase 2 — LightRAG 插件化（3 天）

**目标**：把 `ColearnLightRAGTool` 改造成独立的 nanobot Tool 插件，验证 entry_points 自动发现可行。

### Tasks

| # | 任务 | 创建/修改文件 | 测试标准 |
|---|---|---|---|
| 2.1 | 实现 LightRAGQueryTool | 创建：`colearn_plugin/tools/lightrag_query.py` + `tests/test_lightrag_tool.py` | mock httpx，验证 query/mode/top_k 参数正确传递；retry/backoff 触发；4xx 立即失败 |
| 2.2 | 实现 LightRAGConfig | 创建：`colearn_plugin/tools/__init__.py`（暴露 entry_point） | 从 nanobot config / env 读取 base_url, api_key, timeout |
| 2.3 | 启用 entry_points 注册 | 修改：`colearn_plugin/pyproject.toml` 加 `[project.entry-points."nanobot.tools"]` | 在临时 nanobot bot 上 discover_and_install，工具可被 LLM 调用 |
| 2.4 | 子进程托管迁移 | 创建：`colearn_plugin/tools/lightrag_lifecycle.py`（封装 `_try_spawn_lightrag` 逻辑） | mock subprocess：端口已占用→跳过；启动失败→插件 status=degraded 但不抛 |
| 2.5 | 集成测试 | `tests/integration/test_lightrag_via_nanobot.py` | 真 nanobot bot + mock LightRAG server，端到端 LLM tool call 成功 |

### Deliverables

- `LightRAGQueryTool` 通过 entry_points 被 nanobot 自动加载
- 子进程托管不再依赖 `colearn/server.py` 内的 `_try_spawn_lightrag`
- 旧 `ColearnLightRAGTool` 暂留（Phase 4 删除）

### Risks

- LightRAG 子进程启动失败的语义需要明确：插件 degraded 还是 startup 失败？决策：**degraded** + warning，与现有 RetrievalService 三段降级一致
- `nanobot 0.2.1` 的 `Tool` 基类签名（`config_cls` / `enabled` / `create` 方法）需在写代码前实测一遍——预留半天 buffer

### Tag

`plugin/phase2-lightrag`

---

## Phase 3 — 学习状态插件化（4 天）

**目标**：把 5-stage pipeline 和学习 hooks 迁移到 `colearn_plugin/`，hook 通过 ContextVar 工作。

### Tasks

| # | 任务 | 创建/修改文件 | 测试标准 |
|---|---|---|---|
| 3.1 | 迁移 5 个 Stage | 复制：`colearn/app/stages/{preflight,plan,retrieval,finalize,writeback}.py` → `colearn_plugin/pipeline/`<br>修改：去除对 colearn 反向依赖，改用构造期注入 | `tests/test_pipeline_stages.py`：每个 stage 独立 mock 输入输出，与原版字段一致 |
| 3.2 | 实现 PipelineOrchestrator | 创建：`colearn_plugin/pipeline/orchestrator.py` + `turn_context.py` | `tests/test_orchestrator.py`：5 stage 串联，TurnContext 跨 stage 传递正确 |
| 3.3 | 实现 5 个 Hook | 创建：`colearn_plugin/hooks/{preflight,plan,retrieval,finalize,writeback,stream_bridge}.py`<br>修改：`colearn_plugin/hooks/__init__.py` 加 `build_hooks()` factory | `tests/test_hooks_pipeline.py`：mock AgentHookContext，hook 顺序正确，幂等（iteration>0 不重跑） |
| 3.4 | 迁移学习状态机 | 复制：`colearn/learning/{board_hooks,state_hooks,turn_hooks,retrieval_hooks,signal_extractor}.py` → `colearn_plugin/pipeline/learning_logic/`<br>纯函数，无外部状态依赖 | `tests/test_learning_logic_parity.py`：插件函数调用 vs 旧函数调用，输出逐字段相等 |
| 3.5 | 实现 BackgroundTurnFinalizer | 创建：`colearn_plugin/runtime/background_finalizer.py` | `tests/test_background_finalizer.py`：schedule 不阻塞、并发去重、shutdown 等待完成 |
| 3.6 | StreamBridgeHook | 创建：`colearn_plugin/hooks/stream_bridge.py` | mock emit 函数，验证 nanobot delta → CoLearn StreamEventType 转换正确 |

### Deliverables

- 5-stage pipeline 完整运行在插件内，不依赖 `colearn/app/`
- 学习状态机 hooks 迁移完成，旧 `colearn/learning/*_hooks.py` 改为 thin re-export
- ContextVar → TurnContext → Stage 完整链路打通

### Risks

- **迁移面广**：`turn_hooks.policy` 涉及 5 个 LearningPhase 分支，**必须先建 parity 测试再重构**，避免行为漂移
- EventMemoryStore 写入收敛会改变事件时序，关注 `BLOCKER_RESOLVED` 在同 turn 内的顺序

### Tag

`plugin/phase3-state`

---

## Phase 4 — 集成（2 天）

**目标**：CoLearn 主仓改造，去掉 `import nanobot.*`，通过插件接入；nanobot 启动时 discover_and_install。

### Tasks

| # | 任务 | 创建/修改文件 | 测试标准 |
|---|---|---|---|
| 4.1 | CoLearn 主仓接入 | 修改：`colearn/server.py` 用 `CoLearnPlugin.discover_and_install(bot)` 替代 `NanobotTurnExecutor`<br>修改：`colearn/api/` HTTP 层改为通过 `plugin.get_state_manager()` 读写 | `tests/test_server_with_plugin.py`：startup → install → 一个 turn 端到端跑通 |
| 4.2 | 删除 NanobotTurnExecutor | 删除：`colearn/runtime_v2/{executor.py, tooling.py, prompting.py, result_bridge.py, learning_event_tool.py, learning_closure.py, tool_adapters.py, profile.py, context_bridge.py}` | `pytest tests/` 全绿（旧 test 同步迁移或删除） |
| 4.3 | 删除迁移过的 Stage 旧实现 | 删除：`colearn/app/stages/` 内已迁移文件<br>简化：`colearn/app/learning_orchestrator.py` 改为 thin facade | `tests/test_learning_orchestrator.py` 调整后通过 |
| 4.4 | 删除迁移过的学习 hooks | 删除：`colearn/learning/{board_hooks,state_hooks,turn_hooks,retrieval_hooks}.py`（如果已经 re-export 完成）<br>保留：`colearn/learning/state.py`（dataclass 定义） | 全仓库 `grep "from nanobot"` 应为 0（或仅出现在插件包） |
| 4.5 | nanobot config 集成 | 创建：`.colearn/nanobot-with-plugin.config.json`（注册 colearn 插件 + lightrag 工具） | nanobot 启动日志显示 `Loaded plugin: colearn`，`Registered tool: lightrag_query` |
| 4.6 | 数据迁移脚本 | 创建：`colearn_plugin/state/migrations/from_legacy.py` + CLI `python -m colearn_plugin.migrate` | 旧 sessions.json + projects 状态 → 新 per-file 格式，hash 校验一致 |

### Deliverables

- CoLearn 主仓 `grep "import nanobot"` = 0
- `colearn/runtime_v2/` 整个目录删除
- 启动 `python -m colearn.server`，自动加载 colearn-plugin，端到端 turn 跑通
- 旧数据迁移脚本可用

### Risks

- **删除的范围大**：建议每个 4.2/4.3/4.4 任务单独 commit，方便单步回退
- 主仓 API 层改造可能漏点：用 `grep -r "session_store\." colearn/api/` 找全所有读写位置

### Tag

`plugin/phase4-integrated`

---

## Phase 5 — 测试和文档（2 天）

### Tasks

| # | 任务 | 创建文件 | 测试标准 |
|---|---|---|---|
| 5.1 | 完整 unit 测试矩阵 | `tests/test_context.py`, `test_session_binder.py`, `test_state_manager.py`, `test_hooks_pipeline.py`, `test_lightrag_tool.py`, `test_pipeline_stages.py` | `pytest -q` 全绿，coverage `colearn_plugin/*` ≥ 85% |
| 5.2 | 集成测试 | `tests/integration/test_full_turn.py`, `test_concurrent_sessions.py`, `test_plugin_discovery.py` | 真 nanobot + mock LightRAG，10 个并发 session，状态隔离 |
| 5.3 | E2E live smoke | `tests/live_smoke_plugin.py`：真 LightRAG + DeepSeek，跑 intake→plan→teach→reflect | 退出码 0，输出 16 项 capability 验证报告 |
| 5.4 | 写技术文档 | 更新 `docs/PLUGIN_TECHNICAL_DESIGN.md` 与实施一致<br>新增 `colearn-plugin/README.md`（详细使用文档）<br>新增 `docs/PLUGIN_MIGRATION_GUIDE.md` | markdown lint 通过；架构图与代码 import 链一致 |
| 5.5 | 更新 PROGRESS.md | 添加"插件化迁移"章节 | 列出每个插件状态 + 入口文件 + 回滚 commit hash |
| 5.6 | 写 README | `colearn-plugin/README.md`（含安装、配置、示例、故障排查） | 按 README 一步步走，外部用户能用 |

### Deliverables

- 测试覆盖率 ≥ 85%，CI 全绿
- 5 篇文档：技术设计、实施计划、迁移指南、架构 README、插件作者指南
- PROGRESS.md 同步

### Tag

`plugin/phase5-released`

---

## 测试策略

### Unit Tests（每个 phase 贴近代码）

- `test_context.py`: ContextVar 在 50 个 asyncio.gather 并发下隔离 + nested bind/reset
- `test_session_binder.py`: 三段降级（spec / messages / None）
- `test_state_manager.py`: 原子写、并发缓存、损坏恢复、schema migration
- `test_hooks_pipeline.py`: 5-stage hook 顺序、幂等（iteration>0 不重跑）
- `test_lightrag_tool.py`: mock httpx，retry/backoff、4xx/5xx 区分
- `test_pipeline_stages.py`: 每个 stage 独立测，与旧版字段 parity

### Integration Tests（Phase 4 起）

- `test_full_turn.py`: 真 nanobot + mock LightRAG，单 turn 端到端
- `test_concurrent_sessions.py`: asyncio.gather 10 个并发 session，状态隔离
- `test_plugin_discovery.py`: entry_points 自动发现，错误版本拒绝
- `test_lightrag_via_nanobot.py`: LLM 调 lightrag_query，结果注入消息流

### E2E Tests（Phase 5）

- `tests/live_smoke_plugin.py`: 真 LightRAG + 真 DeepSeek
  - intake：用户说"我想学牛顿定律"
  - plan：从 LightRAG 拉课程结构
  - teach：1 个学习节点
  - check：出 1 道题
  - reflect：生成总结
  - 校验 16 项 LearningSession 字段都被写入

### Parity Tests（Phase 3 关键）

- `test_learning_logic_parity.py`: 插件版函数调用 vs 旧版函数调用，10 组 fixtures，输出逐字段相等

---

## 回滚计划

### 分阶段 git tag

每个 phase 落 tag：
- `plugin/phase1-infra` — Phase 1 末
- `plugin/phase2-lightrag`
- `plugin/phase3-state`
- `plugin/phase4-integrated`
- `plugin/phase5-released`

任何 phase 失败 → `git reset --hard plugin/phase{N-1}` 回到上一阶段。

### 兼容期降级开关

环境变量：
- `COLEARN_DISABLED_PLUGINS=lightrag,learning_state` — 临时关闭单个插件
- `COLEARN_PLUGIN_ARCH=off` — 整体关闭插件，走旧路径（Phase 4 删除前可用）

LightRAG 子进程启动失败 → 自动 fallback `NoOpLightRAGClient` + 警告，turn 不中断。

LearningStatePlugin 失败 → server 启动失败（关键插件不允许 silent fallback）。

### 数据回滚

- `.colearn/state/` 是新增目录，回滚直接删除
- 旧 `sessions.json` / `projects.json` 在 Phase 4.6 迁移时**保留为只读 fallback**，迁移成功后两个版本再删
- 迁移脚本提供 `--dry-run` 和反向导出（`export-legacy`）

### 监控

上线后 7 天观察：
- turn 失败率
- 检索 fallback 率
- session.last_turn_result 写入率

任一指标相对基线劣化 >5% → 立即 `git revert` 到 `plugin/phase4-integrated` 之前的 baseline commit。

---

## 关键决策点

### D1: 外部包 vs 内部子包？
→ **外部独立包** `colearn-plugin`。理由见技术设计 §1。

### D2: LightRAG 走 Tool 还是 MCP server？
→ **Tool**（hybrid 方案）。MCP server 模板预留。

### D3: 状态存储用 JSON 还是 SQLite？
→ **JSON**（per-session/project 单文件）。简单、可读、可 grep。性能瓶颈再升 SQLite。

### D4: 直接替换 vs 并行运行？
→ **直接替换**（用户决定）。每个 phase tag 独立可回退。

### D5: 是否在 Phase 1 就启用 entry_points？
→ **不启用**。Phase 4 才启用，避免 Phase 1-3 期间影响 nanobot 启动。

---

## 时间表汇总

| Phase | 工作量 | 风险 | 关键里程碑 |
|---|---|---|---|
| 1. 基础设施 | 2 天 | 低 | 插件骨架 + ContextVar 测试通过 |
| 2. LightRAG | 3 天 | 中 | LightRAG 通过 entry_points 被加载 |
| 3. 学习状态 | 4 天 | **高** | 5-stage 在插件内独立运行，parity 测试全绿 |
| 4. 集成 | 2 天 | 中 | CoLearn 主仓 `grep nanobot` = 0 |
| 5. 测试文档 | 2 天 | 低 | coverage ≥ 85%，5 篇文档完成 |
| **合计** | **13 天** | — | nanobot 升级影响半径限于插件包 |

---

## 接下来

→ 等待用户审阅本计划  
→ 通过后从 Phase 1 任务 1.1 开始
