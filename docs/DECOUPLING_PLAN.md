# CoLearn → nanobot 插件化解耦方案

> 设计目标：将 CoLearn 的学习逻辑作为 nanobot 的专业插件模块，降低耦合度，提升可维护性

## 当前架构分析

### CoLearn 核心模块（104 个 Python 文件）

```
colearn/
├── learning/          # 学习状态机、事件、hooks（18 个文件）
├── runtime_v2/        # nanobot 执行器封装（14 个文件）
├── app/               # 5-stage pipeline 编排（8 个文件）
├── sessions/          # 会话管理
├── projects/          # 项目管理
├── memory/            # 记忆存储
├── knowledge/         # 知识库
├── retrieval/         # LightRAG 检索
└── api/               # FastAPI 接口（14 个文件）
```

### 当前与 nanobot 的耦合点

1. **直接导入 nanobot 模块**（10+ 处）：
   - `nanobot.agent.hook.AgentHook` - 用于流式输出
   - `nanobot.nanobot.Nanobot` - 核心 bot 实例
   - `nanobot.agent.tools.base.Tool` - 工具注册
   - `nanobot.config.loader.load_config` - 配置加载
   - `nanobot.session.goal_state` - 目标状态管理

2. **NanobotTurnExecutor 封装**：
   - 位置：`colearn/runtime_v2/executor.py`
   - 职责：包装 nanobot 的 agent loop，注入 CoLearn 工具和 hooks
   - 问题：紧耦合，难以独立测试

3. **5-Stage Pipeline**：
   - `PreflightStage` → 准备 session/board/profile
   - `PlanStage` → 生成学习计划
   - `RetrievalStage` → LightRAG 检索
   - `ExecuteStage` → **调用 nanobot agent loop**
   - `FinalizeStage` → 归一化结果
   - `WritebackStage` → 持久化状态

   **问题**：pipeline 与 nanobot 的集成点只在 ExecuteStage，但整个 orchestrator 依赖 nanobot 的配置和会话管理。

## nanobot v0.2.1 扩展机制

### 1. AgentHook 生命周期钩子

```python
class AgentHook:
    async def before_iteration(self, context: AgentHookContext) -> None
    async def on_stream(self, context: AgentHookContext, delta: str) -> None
    async def on_stream_end(self, context: AgentHookContext, *, resuming: bool) -> None
    async def before_execute_tools(self, context: AgentHookContext) -> None
    async def emit_reasoning(self, reasoning_content: str | None) -> None
    async def emit_reasoning_end(self) -> None
    async def after_iteration(self, context: AgentHookContext) -> None
    def finalize_content(self, context: AgentHookContext, content: str | None) -> str | None
```

**AgentHookContext** 包含：
- `iteration`, `messages`, `response`, `usage`
- `tool_calls`, `tool_results`, `tool_events`
- `final_content`, `stop_reason`, `error`

### 2. MCP (Model Context Protocol)

- 支持多个 MCP 服务器
- MCP resources & prompts 作为工具暴露
- CLI Apps + MCP 统一扩展接口

### 3. Skills 系统

- 可插拔的技能模块
- ClawHub 技能市场
- `disabled_skills` 配置控制

### 4. Channel Plugins

- 多渠道支持（WebUI, Telegram, Slack, Discord, Email）
- 可扩展的消息路由

### 5. Provider 系统

- 添加新 LLM provider 只需 2 步
- 支持 fallback 和 model routing

## 插件化架构设计

### 核心思路

**将 CoLearn 的 5-stage pipeline 映射到 nanobot 的 hook 系统**，而不是包装整个 nanobot。

```
┌─────────────────────────────────────────────────────────┐
│                    nanobot Core                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │         Agent Loop (不修改)                      │   │
│  │  messages → LLM → tools → response              │   │
│  └─────────────────────────────────────────────────┘   │
│                        ↓ hooks                          │
│  ┌─────────────────────────────────────────────────┐   │
│  │      CoLearn Learning Plugin (新增)              │   │
│  │  ┌─────────────────────────────────────────┐    │   │
│  │  │ LearningHook (extends AgentHook)        │    │   │
│  │  │  - before_iteration → Preflight + Plan  │    │   │
│  │  │  - before_execute_tools → Retrieval     │    │   │
│  │  │  - after_iteration → Finalize + Write   │    │   │
│  │  └─────────────────────────────────────────┘    │   │
│  │  ┌─────────────────────────────────────────┐    │   │
│  │  │ Learning Tools (MCP/Skills)             │    │   │
│  │  │  - learning_event_tool                  │    │   │
│  │  │  - mastery_update_tool                  │    │   │
│  │  │  - lightrag_search_tool                 │    │   │
│  │  └─────────────────────────────────────────┘    │   │
│  │  ┌─────────────────────────────────────────┐    │   │
│  │  │ Learning State Manager                  │    │   │
│  │  │  - LearningSession                      │    │   │
│  │  │  - BoardFacts                           │    │   │
│  │  │  - mastery tracking                     │    │   │
│  │  └─────────────────────────────────────────┘    │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

### 插件接口设计

#### 1. LearningHook (核心 Hook)

```python
# colearn_plugin/hooks/learning_hook.py

from nanobot.agent.hook import AgentHook, AgentHookContext
from colearn_plugin.state import LearningStateManager
from colearn_plugin.stages import PreflightStage, PlanStage, RetrievalStage, FinalizeStage

class LearningHook(AgentHook):
    """CoLearn 学习逻辑的 nanobot hook 实现"""
    
    def __init__(self, state_manager: LearningStateManager):
        super().__init__()
        self.state = state_manager
        self.preflight = PreflightStage(state_manager)
        self.plan = PlanStage(state_manager)
        self.retrieval = RetrievalStage(state_manager)
        self.finalize = FinalizeStage(state_manager)
    
    async def before_iteration(self, context: AgentHookContext) -> None:
        """在每次 LLM 调用前执行 Preflight + Plan"""
        if context.iteration == 0:
            # 第一次迭代：执行 preflight 和 plan
            await self.preflight.run(context)
            await self.plan.run(context)
            
            # 将学习计划注入到 messages
            if self.state.current_plan:
                context.messages.append({
                    "role": "system",
                    "content": f"学习计划：{self.state.current_plan}"
                })
    
    async def before_execute_tools(self, context: AgentHookContext) -> None:
        """在工具执行前进行知识检索"""
        await self.retrieval.run(context)
        
        # 将检索结果注入到 tool context
        if self.state.retrieval_results:
            # nanobot 会将这些结果传递给工具
            context.tool_events.append({
                "type": "retrieval",
                "data": self.state.retrieval_results
            })
    
    async def after_iteration(self, context: AgentHookContext) -> None:
        """在每次迭代后执行 Finalize + Writeback"""
        await self.finalize.run(context)
        
        # 更新学习状态
        if context.final_content:
            await self.state.update_from_response(
                content=context.final_content,
                tool_calls=context.tool_calls,
                tool_results=context.tool_results
            )
    
    def finalize_content(self, context: AgentHookContext, content: str | None) -> str | None:
        """最终内容处理：添加学习反馈"""
        if not content:
            return content
        
        # 添加 mastery 进度提示
        if self.state.mastery_updated:
            feedback = f"\n\n📊 掌握度更新：{self.state.current_mastery}"
            return content + feedback
        
        return content
```

#### 2. Learning State Manager (状态管理)

```python
# colearn_plugin/state/manager.py

from dataclasses import dataclass, field
from typing import Any

@dataclass
class LearningStateManager:
    """管理学习会话状态，独立于 nanobot 的会话系统"""
    
    session_id: str
    project_id: str
    
    # Learning-specific state
    current_phase: str = "READY"  # INTAKE, DIAGNOSE, PLAN, LEARN, CHECK, REFLECT, RECALL
    current_plan: dict[str, Any] | None = None
    board: dict[str, Any] = field(default_factory=dict)
    mastery: dict[str, float] = field(default_factory=dict)
    blockers: list[str] = field(default_factory=list)
    
    # Retrieval state
    retrieval_results: list[dict[str, Any]] = field(default_factory=list)
    
    # Flags
    mastery_updated: bool = False
    
    @property
    def current_mastery(self) -> str:
        """返回当前掌握度的可读字符串"""
        if not self.mastery:
            return "暂无数据"
        return ", ".join(f"{k}: {v:.0%}" for k, v in self.mastery.items())
    
    async def update_from_response(
        self, 
        content: str, 
        tool_calls: list, 
        tool_results: list
    ) -> None:
        """从 LLM 响应中提取学习事件并更新状态"""
        # 检测学习信号
        from colearn_plugin.learning.signal_extractor import extract_learning_signals
        
        signals = extract_learning_signals(content)
        
        if "understood" in signals:
            # 更新 mastery
            self.mastery_updated = True
            # ... 更新逻辑
        
        if "blocker" in signals:
            self.blockers.append(signals["blocker"])
```

#### 3. Learning Tools (MCP/Skills)

```python
# colearn_plugin/tools/learning_event_tool.py

from nanobot.agent.tools.base import Tool, tool_parameters

@tool_parameters(
    name="learning_event",
    description="记录学习事件（理解、困惑、完成）",
    parameters={
        "type": "object",
        "properties": {
            "event_type": {
                "type": "string",
                "enum": ["understood", "confused", "completed"],
                "description": "事件类型"
            },
            "content": {
                "type": "string",
                "description": "事件内容"
            },
            "node_id": {
                "type": "string",
                "description": "知识节点 ID（可选）"
            }
        },
        "required": ["event_type", "content"]
    }
)
class LearningEventTool(Tool):
    """学习事件记录工具"""
    
    def __init__(self, state_manager: LearningStateManager):
        super().__init__()
        self.state = state_manager
    
    async def execute(self, event_type: str, content: str, node_id: str = None) -> dict:
        """执行学习事件记录"""
        
        if event_type == "understood":
            # 更新 mastery
            if node_id:
                current = self.state.mastery.get(node_id, 0.0)
                self.state.mastery[node_id] = min(1.0, current + 0.2)
                self.state.mastery_updated = True
            
            return {
                "success": True,
                "message": f"已记录理解事件：{content}",
                "mastery": self.state.mastery.get(node_id, 0.0) if node_id else None
            }
        
        elif event_type == "confused":
            # 添加 blocker
            self.state.blockers.append(content)
            return {
                "success": True,
                "message": f"已记录困惑点：{content}",
                "blockers": self.state.blockers
            }
        
        elif event_type == "completed":
            # 标记节点完成
            if node_id:
                self.state.mastery[node_id] = 1.0
                self.state.mastery_updated = True
            
            return {
                "success": True,
                "message": f"已标记完成：{content}"
            }
        
        return {"success": False, "message": "未知事件类型"}
```

#### 4. Plugin Registration (插件注册)

```python
# colearn_plugin/__init__.py

from nanobot.agent.hook import CompositeHook
from colearn_plugin.hooks.learning_hook import LearningHook
from colearn_plugin.state.manager import LearningStateManager
from colearn_plugin.tools import LearningEventTool, MasteryUpdateTool, LightRAGSearchTool

class CoLearnPlugin:
    """CoLearn 学习插件的主入口"""
    
    def __init__(self, config: dict):
        self.config = config
        self.state_manager = None
        self.hook = None
        self.tools = []
    
    def initialize(self, session_id: str, project_id: str) -> None:
        """初始化插件状态"""
        self.state_manager = LearningStateManager(
            session_id=session_id,
            project_id=project_id
        )
        
        self.hook = LearningHook(self.state_manager)
        
        self.tools = [
            LearningEventTool(self.state_manager),
            MasteryUpdateTool(self.state_manager),
            LightRAGSearchTool(self.state_manager),
        ]
    
    def get_hook(self) -> LearningHook:
        """返回 hook 实例供 nanobot 注册"""
        return self.hook
    
    def get_tools(self) -> list:
        """返回工具列表供 nanobot 注册"""
        return self.tools


# 在 nanobot 配置中注册插件
def register_colearn_plugin(nanobot_instance, session_id: str, project_id: str):
    """将 CoLearn 插件注册到 nanobot 实例"""
    
    plugin = CoLearnPlugin(config={})
    plugin.initialize(session_id, project_id)
    
    # 注册 hook
    if hasattr(nanobot_instance, 'hooks'):
        nanobot_instance.hooks.append(plugin.get_hook())
    
    # 注册工具
    for tool in plugin.get_tools():
        nanobot_instance.register_tool(tool)
    
    return plugin
```

### 配置集成

```json
// .colearn/nanobot-with-learning-plugin.config.json
{
  "model": "deepseek-chat",
  "provider": "deepseek",
  "plugins": [
    {
      "name": "colearn_learning",
      "module": "colearn_plugin",
      "enabled": true,
      "config": {
        "lightrag_url": "http://localhost:9621",
        "mastery_threshold": 0.8,
        "auto_recall_days": 7
      }
    }
  ],
  "hooks": [
    "colearn_plugin.hooks.learning_hook.LearningHook"
  ],
  "tools": [
    "colearn_plugin.tools.learning_event_tool.LearningEventTool",
    "colearn_plugin.tools.mastery_update_tool.MasteryUpdateTool",
    "colearn_plugin.tools.lightrag_search_tool.LightRAGSearchTool"
  ]
}
```

## 迁移路径

### Phase 1: 接口提取（1-2 天）

**目标**：定义清晰的插件接口，不破坏现有功能

- [ ] 创建 `colearn_plugin/` 目录结构
- [ ] 定义 `LearningHook` 接口
- [ ] 定义 `LearningStateManager` 接口
- [ ] 定义工具接口（`LearningEventTool` 等）
- [ ] 编写接口文档和示例

**风险**：低 - 只是定义接口，不修改现有代码

### Phase 2: 并行实现（3-5 天）

**目标**：实现插件版本，与现有系统并行运行

- [ ] 实现 `LearningHook` 的 5-stage 逻辑
  - [ ] `before_iteration` → Preflight + Plan
  - [ ] `before_execute_tools` → Retrieval
  - [ ] `after_iteration` → Finalize + Writeback
- [ ] 实现 `LearningStateManager`
  - [ ] 会话状态管理
  - [ ] mastery tracking
  - [ ] blocker 管理
- [ ] 实现学习工具
  - [ ] `LearningEventTool`
  - [ ] `MasteryUpdateTool`
  - [ ] `LightRAGSearchTool`
- [ ] 添加配置加载逻辑
- [ ] 编写单元测试

**风险**：中 - 需要确保插件版本与现有逻辑一致

### Phase 3: 集成测试（2-3 天）

**目标**：验证插件版本功能完整性

- [ ] 创建测试环境（独立的 nanobot 实例 + CoLearn 插件）
- [ ] 端到端测试
  - [ ] INTAKE 流程
  - [ ] DIAGNOSE 流程
  - [ ] LEARN/CHECK 循环
  - [ ] REFLECT 流程
  - [ ] RECALL 流程
- [ ] 性能对比测试
- [ ] 修复发现的问题

**风险**：中 - 可能发现边缘情况和兼容性问题

### Phase 4: 渐进式迁移（3-5 天）

**目标**：逐步将流量切换到插件版本

- [ ] 添加特性开关（feature flag）
  ```python
  USE_PLUGIN_MODE = os.getenv("COLEARN_USE_PLUGIN", "false") == "true"
  ```
- [ ] 10% 流量切换到插件模式
- [ ] 监控和对比结果
- [ ] 50% 流量切换
- [ ] 100% 流量切换
- [ ] 移除旧代码路径

**风险**：中 - 需要仔细监控，确保无回归

### Phase 5: 清理和优化（2-3 天）

**目标**：移除旧耦合代码，优化插件性能

- [ ] 删除 `colearn/runtime_v2/executor.py` 中的 nanobot 封装
- [ ] 删除 `colearn/app/learning_orchestrator.py` 中的 5-stage pipeline
- [ ] 简化 `colearn/nanobot_bootstrap.py`
- [ ] 更新文档
- [ ] 性能优化
  - [ ] 减少状态序列化开销
  - [ ] 优化 hook 调用频率
  - [ ] 缓存检索结果

**风险**：低 - 此时插件已稳定运行

## 关键挑战与解决方案

### 挑战 1: 状态管理

**问题**：CoLearn 有复杂的学习状态（LearningSession, BoardFacts, mastery），如何在插件中管理？

**解决方案**：
- 使用 `LearningStateManager` 作为状态容器
- 状态持久化到独立的存储（JSON/SQLite）
- 通过 hook context 传递必要的状态引用
- 避免在 nanobot 的 session 中存储 CoLearn 特定状态

### 挑战 2: 5-Stage Pipeline 映射

**问题**：CoLearn 的 5-stage pipeline 如何映射到 nanobot 的 hook 生命周期？

**解决方案**：
```
CoLearn Stage          →  nanobot Hook
─────────────────────────────────────────────
PreflightStage         →  before_iteration (iteration == 0)
PlanStage              →  before_iteration (iteration == 0)
RetrievalStage         →  before_execute_tools
ExecuteStage           →  (nanobot 原生 agent loop)
FinalizeStage          →  after_iteration
WritebackStage         →  after_iteration
```

### 挑战 3: 工具注册

**问题**：CoLearn 有自定义工具（learning_event, lightrag_search），如何注册到 nanobot？

**解决方案**：
- 使用 nanobot 的 `Tool` 基类
- 通过 `@tool_parameters` 装饰器定义工具元数据
- 在插件初始化时注册到 nanobot 实例
- 工具可以访问 `LearningStateManager` 来更新状态

### 挑战 4: 流式输出

**问题**：CoLearn 需要流式输出学习进度，如何与 nanobot 的流式系统集成？

**解决方案**：
- 实现 `wants_streaming() -> True`
- 在 `on_stream()` 中处理流式内容
- 在 `on_stream_end()` 中发送学习事件
- 使用 `emit_reasoning()` 发送思考过程

### 挑战 5: 向后兼容

**问题**：如何确保迁移过程中不破坏现有功能？

**解决方案**：
- 使用特性开关（feature flag）
- 并行运行新旧两套系统
- 渐进式流量切换（10% → 50% → 100%）
- 保留旧代码直到插件版本完全稳定

## 预期收益

### 1. 降低耦合度
- CoLearn 逻辑与 nanobot 核心解耦
- 可以独立升级 nanobot 版本
- 插件可以在其他 nanobot 项目中复用

### 2. 提升可测试性
- 插件可以独立测试
- Mock nanobot hook context 更容易
- 单元测试覆盖率提升

### 3. 简化代码结构
- 移除 `NanobotTurnExecutor` 封装层
- 移除 `LearningOrchestrator` 的复杂编排逻辑
- 代码行数预计减少 20-30%

### 4. 提升扩展性
- 可以轻松添加新的学习阶段
- 可以插拔不同的检索后端（LightRAG → 其他）
- 可以支持多种学习模式（自适应、协作等）

### 5. 对齐 nanobot 生态
- 利用 nanobot 的 MCP 集成
- 利用 nanobot 的多渠道支持
- 利用 nanobot 的 provider 系统

## 时间估算

| 阶段 | 工作量 | 风险 |
|------|--------|------|
| Phase 1: 接口提取 | 1-2 天 | 低 |
| Phase 2: 并行实现 | 3-5 天 | 中 |
| Phase 3: 集成测试 | 2-3 天 | 中 |
| Phase 4: 渐进式迁移 | 3-5 天 | 中 |
| Phase 5: 清理和优化 | 2-3 天 | 低 |
| **总计** | **11-18 天** | **中** |

## 下一步行动

1. **Review 这个方案**：与团队讨论，确认方向
2. **创建 POC**：实现一个最小的 `LearningHook` 原型
3. **验证可行性**：在测试环境中运行 POC
4. **启动 Phase 1**：开始接口提取工作

---

**作者**: Claude (Kiro)  
**日期**: 2026-06-01  
**版本**: v1.0
