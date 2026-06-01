# CoLearn 插件化可行性评估

## 你的目标

> 把 LightRAG 和学习状态都变成插件，给 nanobot 用。这样不管 nanobot 怎么升级，插件都可以继续使用。

## 可行性分析

### ✅ 可行的部分

#### 1. LightRAG 作为插件 - **高度可行**

**理由**：
- LightRAG 本质上是一个**检索工具**，与 nanobot 核心逻辑无关
- nanobot 已有完善的 **Tool 系统**和 **MCP 集成**
- CoLearn 当前的 `ColearnLightRAGTool` 已经实现了 `Tool` 接口

**实现方式**：
```python
# 方式 1: 作为 nanobot Tool
class LightRAGTool(Tool):
    name = "lightrag_search"
    description = "搜索学习资料"
    
    async def execute(self, query: str) -> dict:
        # 调用 LightRAG API
        return results

# 方式 2: 作为 MCP Server
# 启动独立的 LightRAG MCP 服务器
# nanobot 通过 MCP 协议连接
```

**优势**：
- ✅ 完全解耦：LightRAG 可以独立升级
- ✅ 可复用：其他 nanobot 项目也能用
- ✅ 标准化：遵循 nanobot 的 Tool/MCP 协议
- ✅ 零风险：不依赖 nanobot 内部 API

**工作量**：1-2 天

---

#### 2. 学习状态作为插件 - **部分可行，有挑战**

**理由**：
- 学习状态（LearningSession, mastery, blockers）是 **CoLearn 特有的业务逻辑**
- nanobot 的 hook 系统**可以**支持自定义状态管理
- 但需要解决**状态持久化**和**跨 turn 传递**的问题

**挑战点**：

##### 挑战 A: 状态存储位置

**问题**：学习状态存在哪里？

| 方案 | 优点 | 缺点 | 可行性 |
|------|------|------|--------|
| **nanobot session metadata** | 与 nanobot 会话绑定 | 耦合到 nanobot 内部结构 | ⚠️ 中 |
| **独立存储（JSON/SQLite）** | 完全解耦 | 需要自己管理会话映射 | ✅ 高 |
| **MCP Resources** | 标准化接口 | 需要额外的 MCP 服务器 | ✅ 高 |

**推荐**：**独立存储** - 用 `LearningStateManager` 管理自己的状态文件。

##### 挑战 B: 跨 turn 状态传递

**问题**：如何在多个 turn 之间保持学习状态？

```python
# Turn 1: 用户说"我想学牛顿定律"
# → 创建 LearningSession, phase=PLAN
# → 生成学习计划

# Turn 2: 用户说"第一步是什么？"
# → 需要读取 Turn 1 的 LearningSession
# → 需要知道当前 phase 和 plan
```

**nanobot 提供的机制**：
- `session_key` - 会话隔离
- `session.metadata` - 存储自定义数据（但这是私有 API）
- Hook 的 `context.messages` - 可以读取历史消息

**解决方案**：
```python
class LearningHook(AgentHook):
    def __init__(self, state_manager: LearningStateManager):
        self.state = state_manager
    
    async def before_iteration(self, context: AgentHookContext) -> None:
        # 从 context 中提取 session_id
        session_id = self._extract_session_id(context)
        
        # 从独立存储加载学习状态
        learning_session = await self.state.load_session(session_id)
        
        # 根据状态决定行为
        if learning_session.phase == "PLAN":
            # 注入学习计划到 prompt
            context.messages.append({
                "role": "system",
                "content": f"学习计划：{learning_session.plan}"
            })
```

**问题**：如何从 `AgentHookContext` 中提取 `session_id`？

**答案**：nanobot 的 `bot.run(prompt, session_key=...)` 会传递 session_key，但 `AgentHookContext` **不直接暴露** session_key。

**Workaround**：
1. 在 `context.messages` 中查找特殊标记
2. 或者在 plugin 初始化时注入 session_id
3. 或者使用 `ContextVar` 在 thread-local 存储

##### 挑战 C: 5-Stage Pipeline 映射

**问题**：CoLearn 的 5-stage pipeline 如何映射到 nanobot hooks？

```
CoLearn 当前架构：
┌─────────────────────────────────────────────┐
│ LearningOrchestrator.run_turn()             │
│  ├─ PreflightStage  (准备 session/board)    │
│  ├─ PlanStage       (生成学习计划)          │
│  ├─ RetrievalStage  (LightRAG 检索)         │
│  ├─ ExecuteStage    (调用 nanobot)          │
│  ├─ FinalizeStage   (归一化结果)            │
│  └─ WritebackStage  (持久化状态)            │
└─────────────────────────────────────────────┘

nanobot hook 生命周期：
┌─────────────────────────────────────────────┐
│ bot.run(prompt, session_key, hooks)         │
│  ├─ before_iteration  (第 1 次迭代前)       │
│  ├─ [LLM 调用]                              │
│  ├─ on_stream        (流式输出)             │
│  ├─ before_execute_tools (工具执行前)       │
│  ├─ [工具执行]                              │
│  ├─ after_iteration  (迭代后)               │
│  └─ finalize_content (最终内容处理)         │
└─────────────────────────────────────────────┘
```

**映射方案**：

| CoLearn Stage | nanobot Hook | 可行性 | 问题 |
|---------------|--------------|--------|------|
| PreflightStage | `before_iteration` (iteration==0) | ✅ | 需要在第一次迭代时执行 |
| PlanStage | `before_iteration` (iteration==0) | ✅ | 同上 |
| RetrievalStage | `before_iteration` | ⚠️ | **在 LLM 调用前检索，但此时还不知道 LLM 会问什么** |
| ExecuteStage | (nanobot 原生) | ✅ | 无需映射 |
| FinalizeStage | `after_iteration` | ✅ | 可以在迭代后处理 |
| WritebackStage | `finalize_content` | ⚠️ | **这个 hook 是同步的，不适合做 I/O** |

**关键问题**：
1. **RetrievalStage 时机不对**：CoLearn 在 LLM 调用前就检索，但此时还不知道 LLM 会生成什么内容。理想情况下应该在 `before_execute_tools` 时检索（当 LLM 决定调用工具时）。

2. **WritebackStage 是异步的**：CoLearn 的 `WritebackStage` 需要写文件、更新数据库，但 `finalize_content` 是同步方法。

**解决方案**：
- RetrievalStage → 改为在 `before_execute_tools` 时触发，或者提前检索并缓存
- WritebackStage → 使用 `after_iteration`（异步），或者启动后台任务

---

### ⚠️ 风险评估

#### 风险 1: nanobot Hook API 变更

**风险等级**：中

**描述**：nanobot 的 `AgentHook` 接口可能在未来版本中变更（添加/删除/重命名方法）。

**影响**：插件需要适配新接口。

**缓解措施**：
- 使用 **Adapter 模式**包装 `AgentHook`，隔离变更
- 监控 nanobot 的 CHANGELOG，及时适配
- 编写兼容性测试，检测 API 变更

#### 风险 2: session_key 传递问题

**风险等级**：高

**描述**：`AgentHookContext` 不直接暴露 `session_key`，插件难以关联学习状态。

**影响**：无法跨 turn 保持学习状态。

**缓解措施**：
- **方案 A**：在 `context.messages` 中注入特殊标记（如 `{"role": "system", "content": "SESSION_ID:xxx"}`）
- **方案 B**：使用 `ContextVar` 在 thread-local 存储 session_id
- **方案 C**：向 nanobot 提交 PR，在 `AgentHookContext` 中添加 `session_key` 字段

#### 风险 3: 状态一致性

**风险等级**：中

**描述**：学习状态存储在独立文件中，可能与 nanobot 的会话状态不同步。

**影响**：用户在 nanobot 中删除会话，但学习状态仍然存在。

**缓解措施**：
- 定期清理孤儿状态
- 提供 `colearn cleanup` 命令
- 在 plugin 初始化时检查状态一致性

#### 风险 4: 性能开销

**风险等级**：低

**描述**：每次 turn 都需要加载/保存学习状态，可能增加延迟。

**影响**：用户体验下降。

**缓解措施**：
- 使用内存缓存（LRU cache）
- 异步写入（不阻塞响应）
- 批量更新（多个 turn 合并一次写入）

---

### 📊 方案对比

#### 方案 A: 完全插件化（你的目标）

**架构**：
```
nanobot (核心)
  ├─ CoLearn Plugin
  │   ├─ LearningHook (5-stage pipeline)
  │   ├─ LearningStateManager (独立存储)
  │   └─ LightRAGTool (检索工具)
  └─ 其他插件...
```

**优点**：
- ✅ 完全解耦，nanobot 升级不影响 CoLearn
- ✅ 可复用，其他项目也能用
- ✅ 清晰的边界

**缺点**：
- ⚠️ 需要解决 session_key 传递问题
- ⚠️ 状态管理复杂度增加
- ⚠️ 需要适配 nanobot hook 生命周期

**工作量**：10-15 天

**推荐度**：⭐⭐⭐⭐ (如果能解决 session_key 问题)

---

#### 方案 B: 混合模式（部分插件化）

**架构**：
```
CoLearn (主项目)
  ├─ LearningOrchestrator (保留)
  ├─ 5-Stage Pipeline (保留)
  └─ nanobot (作为执行引擎)
       ├─ LightRAGTool (插件)
       └─ 其他工具...
```

**优点**：
- ✅ 风险低，只需插件化 LightRAG
- ✅ 保留现有架构，改动小
- ✅ 状态管理不变

**缺点**：
- ❌ 仍然耦合到 nanobot 的 `bot.run()` 接口
- ❌ nanobot 升级可能影响 `NanobotTurnExecutor`

**工作量**：3-5 天

**推荐度**：⭐⭐⭐ (保守方案)

---

#### 方案 C: Fork nanobot（不推荐）

**架构**：
```
CoLearn-nanobot (fork)
  ├─ 添加 session_key 到 AgentHookContext
  ├─ 添加 LearningSession 支持
  └─ 其他定制...
```

**优点**：
- ✅ 完全控制，想改什么改什么

**缺点**：
- ❌ 无法跟进 nanobot 上游更新
- ❌ 维护成本极高
- ❌ 失去社区支持

**工作量**：持续维护

**推荐度**：⭐ (不推荐)

---

## 我的建议

### 🎯 推荐方案：**渐进式插件化**

**第一步**（1-2 天）：**LightRAG 插件化**
- 将 `ColearnLightRAGTool` 改为独立的 nanobot Tool
- 或者启动 LightRAG MCP Server
- **零风险**，立即见效

**第二步**（3-5 天）：**提取学习状态接口**
- 创建 `LearningStateManager` 独立管理状态
- 不依赖 nanobot 的 session metadata
- 保留现有的 `LearningOrchestrator`

**第三步**（5-7 天）：**实现 LearningHook**
- 将 5-stage pipeline 映射到 nanobot hooks
- 解决 session_key 传递问题（使用 ContextVar 或特殊标记）
- 并行运行，用 feature flag 切换

**第四步**（2-3 天）：**测试和验证**
- 端到端测试
- 性能对比
- 逐步切换流量

**总工作量**：11-17 天

---

## 关键决策点

### 决策 1: session_key 如何传递？

**选项 A**: 在 `context.messages` 中注入特殊标记
```python
# 在 bot.run() 前注入
messages.insert(0, {
    "role": "system", 
    "content": f"[COLEARN_SESSION:{session_id}]"
})

# 在 hook 中提取
def _extract_session_id(self, context):
    for msg in context.messages:
        if msg["role"] == "system" and "[COLEARN_SESSION:" in msg["content"]:
            return msg["content"].split(":")[1].rstrip("]")
```

**选项 B**: 使用 ContextVar
```python
from contextvars import ContextVar

_session_id_var = ContextVar("colearn_session_id")

# 在 bot.run() 前设置
_session_id_var.set(session_id)

# 在 hook 中读取
session_id = _session_id_var.get()
```

**选项 C**: 向 nanobot 提交 PR
```python
# 修改 nanobot 的 AgentHookContext
@dataclass
class AgentHookContext:
    session_key: str | None = None  # 新增字段
    # ... 其他字段
```

**我的推荐**：**选项 B (ContextVar)** - 最干净，不污染 messages，不依赖 nanobot 修改。

---

### 决策 2: 状态存储在哪里？

**选项 A**: 独立 JSON 文件
```
.colearn/
  sessions/
    session_123.json
    session_456.json
  projects/
    project_abc.json
```

**选项 B**: SQLite 数据库
```
.colearn/state.db
  - sessions 表
  - projects 表
  - learning_events 表
```

**选项 C**: MCP Resources
```
启动 CoLearn MCP Server
暴露 sessions/projects 作为 MCP Resources
nanobot 通过 MCP 协议访问
```

**我的推荐**：**选项 A (JSON)** - 简单、可读、易调试。后续可以升级到 SQLite。

---

## 总结

### ✅ 可行性结论

**LightRAG 插件化**：✅ **高度可行**，零风险，立即开始。

**学习状态插件化**：⚠️ **可行但有挑战**，需要解决：
1. session_key 传递问题（用 ContextVar）
2. 5-stage pipeline 映射（调整时机）
3. 状态持久化（独立存储）

### 🎯 行动计划

**Week 1**:
- [ ] LightRAG 插件化（1-2 天）
- [ ] 提取 LearningStateManager（2-3 天）

**Week 2**:
- [ ] 实现 LearningHook（3-5 天）
- [ ] 解决 session_key 传递（1 天）

**Week 3**:
- [ ] 测试和验证（2-3 天）
- [ ] 文档和迁移指南（1-2 天）

### 🚨 关键风险

1. **session_key 传递** - 如果 ContextVar 不工作，需要 fallback 方案
2. **nanobot hook 变更** - 需要持续监控上游更新
3. **性能开销** - 需要 benchmark 验证

---

**下一步**：你想先从哪个开始？

1. **快速验证**：先做 LightRAG 插件化，验证 Tool 系统是否满足需求
2. **深入设计**：先解决 session_key 传递问题，写个 POC
3. **全面规划**：我帮你写详细的技术设计文档

你的选择？
