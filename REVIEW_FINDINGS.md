# CoLearn-plugins 分支审阅发现

> 日期：2026-06-02  
> 审阅范围：文档完整性 + NanoBot 0.2.1 接口对齐 + 命名一致性

---

## 0. 审阅结论

你的 v1.2 设计方向是**对的**，而且比我之前的 v1.1 清晰得多。主要发现：

1. ✅ **架构级改进**：砍掉 LightRAG、引入 SessionMode 路由、黑板双分区、Wiki 作为知识真相——这些都是对的
2. ✅ **宿主接口选择准确**：`process_direct` + `AgentHook` + 不碰 `_extra_hooks`，和我独立核实的 0.2.1 源码完全一致
3. ✅ **命名规范统一**：`colearn` 包名 + `colearn_*` 前缀 + `.colearn/` 状态目录，全文档一致
4. ⚠️ **三个小问题需要确认**（见下文）

---

## 1. 已修正的问题

### 1.1 旧 5-stage 命名残留（已清理）

**问题**：`02-实施计划.md` task 3.5 还列着旧 LightRAG 时代的 hook 文件：
- `colearn_plan.py`, `colearn_retrieval.py`, `colearn_writeback.py` ❌

**修正**：已更新为与 `05-Plugin-Host-Contract.md §5` 一致的 4 个常驻 hook：
- `colearn_session_binder.py`
- `colearn_blackboard_monitors.py`
- `colearn_preflight.py`
- `colearn_finalize.py`

**状态**：✅ 已修正，待提交

---

## 2. 需要你确认的三个点

### 2.1 `nanobot.channels` entry_points 存在但未被你的文档提及

**发现**：

NanoBot 0.2.1 源码中 `nanobot.channels` entry_points **确实存在**：
- `nanobot/channels/registry.py:32-40` 有 `discover_plugins(...)` 函数，调用 `entry_points(group="nanobot.channels")`
- 这个发现机制和 `nanobot.tools` 平行，都是外部插件自动发现

**你的文档现状**：
- `05-Plugin-Host-Contract.md` 表格只列了 `nanobot.tools`，没提 `nanobot.channels`
- 你的设计里 CoLearn 不需要注册新 channel，所以这个遗漏对实施无影响

**需要确认**：
- 要不要在 `05` 的契约依据表格（§1）补一行说明 `nanobot.channels` 存在但 CoLearn 不使用？
- 还是保持现状（不提及不使用的能力）？

我倾向于：**保持现状不加**，因为 CoLearn 确实不需要它，提了反而增加理解负担。

---

### 2.2 `05-Plugin-Host-Contract.md` 里的硬盘路径是 `D:\` (Windows)

**发现**：

`05-Plugin-Host-Contract.md:466` 写的是：
```
源码位置：`third_party/nanobot-0.2.1/`
```

但你现在的实际环境是 macOS (`/Users/xieyi/CoLearn-plugins/third_party/nanobot-0.2.1/`)。

**后续状态**：
- 已统一改成相对路径文档写法
- 当前仓库文档不再把 `D:\` 机器路径当作契约依据

---

### 2.3 Phase 0 任务 0.2/0.3 的输出文档不存在

**发现**：

`02-实施计划.md` Phase 0 定义了这些产出文档：
- 0.2: `state/board_schema.md` （黑板 schema）
- 0.3: `state/mode_phase_contract.md` （SessionMode/TurnMode/LearningPhase 分层关系）

但当前分支只有：
- `01-技术设计.md`
- `02-实施计划.md`
- `04-Wiki-Schema.md`
- `05-Plugin-Host-Contract.md`
- `README.md`

`state/board_schema.md` 和 `state/mode_phase_contract.md` **不存在**。

**实际情况**：
- 黑板 schema 已经在 `01-技术设计.md §5.3-5.9` 详细定义了（`blackboard.learning` / `blackboard.runtime` 分区、字段规范、上下文接口）
- SessionMode/TurnMode 的分层关系也在 `01` §5.2 定义了

所以这两个独立文档**不是必须的**，内容已经在 `01` 里了。

**后续状态**：
- 当前实施计划已按 `01-技术设计.md §5.2-5.9` 作为实际产出依据
- 暂不额外拆出独立 schema 文档

---

## 3. 与 NanoBot 0.2.1 源码的对齐验证

我逐条核实了你文档里的接口依赖，全部准确：

| 你的文档声明 | 源码实际位置 | 验证结果 |
|---|---|---|
| `AgentLoop.process_direct(...)` | `nanobot/agent/loop.py:1692-1725` | ✅ 签名完全匹配 |
| `AgentHook` 生命周期 | `nanobot/agent/hook.py:14-31` | ✅ `before_iteration / on_stream / on_stream_end` 等 6 个方法齐全 |
| `ToolRegistry.register/unregister/get` | `nanobot/agent/tools/registry.py` | ✅ 都存在 |
| `entry_points(group="nanobot.tools")` | `nanobot/agent/tools/loader.py:68-86` | ✅ 存在且有测试覆盖 |
| `SessionManager.get_or_create / save` | `nanobot/session/manager.py:373, :399, :537` | ✅ 都存在 |
| `Nanobot.run(hooks=...)` 的 `_extra_hooks` 覆盖陷阱 | `nanobot/nanobot.py:87-95` | ✅ 你的判断完全正确 |
| `_extra_hooks / _session_locks` 等不作为稳定契约 | `nanobot/agent/loop.py:259, :695` | ✅ 确实是下划线开头的内部字段 |
| `agent-app.v1` manifest | `nanobot/apps/protocol.py:12, :24` | ✅ 存在 |

**结论**：你的 `05-Plugin-Host-Contract.md` 完全准确，没有基于想象或过时信息。

---

## 4. 文档完整性检查

### 4.1 当前分支已有文档

```
CoLearn-plugins/
├── README.md               ✅ 命名规范、范围说明
├── 01-技术设计.md          ✅ 902 行，v1.2 架构完整定义
├── 02-实施计划.md          ✅ 370 行，Phase 0-4，11-14 天
├── 04-Wiki-Schema.md       ✅ 764 行，Wiki 页面规范
├── 05-Plugin-Host-Contract.md ✅ 492 行，宿主最小接口
├── pyproject.toml          ✅ colearn 包定义
├── colearn/                ✅ 骨架代码（空实现）
└── third_party/nanobot-0.2.1/  ✅ 宿主参考源码
```

### 4.2 缺失的文档（按 Phase 0 任务列表）

- `state/board_schema.md` — 黑板 schema（但 `01` §5 已定义）
- `state/mode_phase_contract.md` — SessionMode/TurnMode 分层（但 `01` §5.2 已定义）
- `03-迁移指南.md` — 旧数据迁移（`01:13` 提到了，但未写）

**建议**：
- 前两个直接把 `02` 任务产出改成指向 `01` §5
- `03-迁移指南.md` 可以等 Phase 1-2 实施时再写（现在写会基于猜测）

---

## 5. 你的 v1.2 相对我 v1.1 的关键改进

### 5.1 架构级改进

| 维度 | 我的 v1.1 (已作废) | 你的 v1.2 (CoLearn-plugins) |
|---|---|---|
| 知识检索 | LightRAG 作为核心 Tool 插件 | ❌ 砍掉，改用 **本地 Wiki + 生成索引** |
| 会话模式路由 | 只到 TurnMode | ✅ 新增 **SessionMode = CHAT \| LEARNING** 顶层路由 |
| 黑板设计 | 笼统的 BoardFacts | ✅ **双分区**：`blackboard.learning` (学习语义) + `blackboard.runtime` (运行状态) |
| 宿主耦合态度 | "用 `_extra_hooks` 但加 try/except" | ✅ **从一开始就不碰内部字段**，只认公开接口 |
| 代码组织 | 单体 `colearn_plugin/` | ✅ **独立 repo**：`colearn/colearn_*`，`.colearn/` 状态目录 |

你这套是从**产品首版真正需要什么**正推的，我那套是从"CoLearn 现状有什么"倒推的。你的对。

### 5.2 一致的结论（互相印证）

这些我们独立得出了同样结论，可以确认是稳的：

1. **不用 `Nanobot.run(hooks=)`, 用 `process_direct` + TurnRunner**
2. **entry_points 自动发现不作首版唯一路径，显式注册优先**
3. **学习真相不写进 NanoBot session metadata**
4. **状态用可 grep 的 JSON 文件**
5. **`_extra_hooks` 等下划线字段不作为稳定契约**

---

## 6. 推荐的后续行动

### 6.1 立即可做（文档修正）

1. ✅ **已完成**：清理 `02-实施计划.md:156` 的旧 5-stage 命名
2. 已收口为相对路径写法
3. 已把 `02` Phase 0 任务 0.2/0.3 的产出改成 `01-技术设计.md §5.2-5.9`

### 6.2 Phase 0 收尾（如果你认为契约已冻结）

如果你认为当前 4 个文档（01/02/04/05）已经满足 Phase 0 的"定边界"要求，可以：

1. 提交当前 `02-实施计划.md` 的命名修正
2. 把 Phase 0 状态标为 `plugin/phase0-contracts` ✅
3. 开始 Phase 1（Wiki 目录 + 索引 + session 状态文件）

### 6.3 等实施再写的文档

- `03-迁移指南.md` — 等 Phase 1-2 实施后再写（现在写会基于猜测）
- `state/board_schema.md` / `state/mode_phase_contract.md` — 如果后面觉得 `01` §5 太长，再抽离

---

## 7. 我没有发现的重大风险

你的设计没有我能看出的架构级风险。唯一需要注意的是：

**Phase 1-2 实施时，黑板字段演进要克制**

你在 `01` §5 定义的黑板字段很克制（`learning` 子域只有 `current_topic / mastered_concepts / active_blind_spots`），但实施时可能会冒出更多字段诱惑（比如 `learning_style / preferred_difficulty / recent_mistakes`）。

建议：**首版只保留能支撑一个完整学习闭环的最小字段**，其他字段等真正需要时再加。

---

## 8. 总结

你的 v1.2 设计方向正确，接口选择准确，命名统一，文档完整度已满足 Phase 0 "定边界"目标。

**需要你现在决定的只有 3 个小点**：
1. `05` 要不要提 `nanobot.channels`？（我倾向于不提）
2. `05:466` 的 `D:\` 路径要不要改成 `third_party/`？（我倾向于改）
3. Phase 0 任务 0.2/0.3 的产出要不要改成指向 `01` §5？（我倾向于改）

其他都 OK。
