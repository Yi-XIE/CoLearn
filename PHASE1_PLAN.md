# Phase 1 实施计划：知识底座与状态地基

> 日期：2026-06-02  
> 预计工期：2 天  
> 当前状态：Phase 0 完成，Phase 1 准备开工

---

## 0. 当前状态

### 已完成 ✅
- Phase 0 契约冻结（01/02/04/05 文档齐全）
- 骨架代码结构已建立（`colearn/` 包结构）
- NanoBot 0.2.1 参考源码已入库
- 文档一致性已修正并提交

### 待实施 ⏳
- **所有** Phase 1 代码（Wiki 基础设施 + 状态管理）
- 当前 `colearn/` 下所有 `.py` 文件都是空实现

---

## 1. Phase 1 目标

建立两个核心底座：

1. **知识底座**：本地 Wiki 文件 + 索引 + 查询服务
2. **状态地基**：session.json 结构 + 黑板双分区 + 持久化

**不做的事（留给 Phase 2-3）**：
- ❌ 不实现学习逻辑（SessionMode/TurnMode 路由）
- ❌ 不实现 NanoBot 适配层
- ❌ 不实现 hooks 或 tools
- ❌ 不实现黑板写回逻辑

---

## 2. 实施策略：3 个 Workflow 并行加速

### Workflow 1: 基础设施（1.1-1.3 + 1.5）
**并行任务**：
- Agent 1: 创建目录结构 + 5 个模板（1.1 + 1.2）
- Agent 2: 实现 WikiIndexBuilder（1.3）
- Agent 3: 实现 SessionStore（1.5）

**预计时间**：15-20 分钟

### Workflow 2: 样例内容（1.6）
**并行任务**：
- Agent 1: AI 路径 4 个概念页
- Agent 2: 物理路径 4 个概念页
- Agent 3: paths + experiments + question-banks

**预计时间**：15-20 分钟

### Workflow 3: 查询服务 + 测试（1.4 + 1.7）
**并行任务**：
- Agent 1: 实现 WikiQueryService（1.4）
- Agent 2: 写 test_wiki_index.py + test_wiki_query.py
- Agent 3: 写 test_state_store.py

**预计时间**：10-15 分钟

**总预计时间**：40-55 分钟（串行需要 2-3 小时）

---

## 3. Phase 1 完成验收标准

### 测试通过
```bash
$ pytest tests/
tests/test_wiki_index.py::test_parse_all_samples         PASSED
tests/test_wiki_index.py::test_generate_index            PASSED
tests/test_wiki_query.py::test_get_by_id                 PASSED
tests/test_wiki_query.py::test_expand_prerequisites      PASSED
tests/test_state_store.py::test_create_session           PASSED
tests/test_state_store.py::test_atomic_write             PASSED
==================== 10 passed ====================
```

### 代码结构
- `colearn/colearn_wiki/` 完整实现（parser + indexer + query）
- `colearn/colearn_state/` 完整实现（models + store）
- `knowledge/wiki/` 8-12 个样例页 + 5 个模板
- `tests/` 3 个测试文件，覆盖核心逻辑

---

详见本文件末尾的完整任务分解。
