# CoLearn Wiki Schema
> 版本：v0.1  
> 日期：2026-06-02  
> 状态：Phase 0 页面规范冻结稿  
> 适用范围：CoLearn v1 的 K12 AI / STEAM 课程知识底座

## 0. 文档定位

这份文档定义 CoLearn 本地课程 Wiki 的页面规范，用来同时服务两类角色：

1. 内容同学：知道每类页面该写什么
2. 工程同学：知道 frontmatter、引用关系、索引生成该怎么解析

本规范服务于 `01-技术设计.md` 与 `02-实施计划.md` 已经确认的路线：

- CoLearn v1 的知识真相采用本地 `Wiki`
- 不引入 `LightRAG`
- 查询方式采用 `Wiki + 本地索引`
- Wiki 独立于 NanoBot 宿主存在

---

## 1. 设计目标

Wiki 页面规范需要同时满足四件事：

1. **可审阅**：教研和产品可以直接读 Markdown
2. **可索引**：工程可以稳定抽取结构化字段
3. **可引用**：概念、路径、实验、题目之间能通过稳定 ID 互链
4. **可演进**：首版字段小而稳，后续可以增加派生索引，不反复改页面

首版明确不追求：

1. 超大而全的课程本体
2. 复杂的嵌套 YAML 结构
3. 依赖外部向量库的知识组织方式

---

## 2. 目录结构

CoLearn v1 的内容源目录采用：

```text
knowledge/
  wiki/
    concepts/
    paths/
    experiments/
    question-banks/
    glossary/
  generated/
    wiki_index.json
    wiki_link_graph.json
    wiki_search_index.json
```

说明：

- `knowledge/wiki/` 是人工维护的知识真相
- `knowledge/generated/` 是由索引器生成的派生文件
- 后续如果运行时需要把索引镜像到 `.colearn/`，不改变本页面规范

### 2.1 子目录职责

| 目录 | 用途 |
|---|---|
| `concepts/` | 单一知识概念页，是 CoLearn 学习推进的主节点 |
| `paths/` | 学习路径页，定义概念的推荐学习顺序 |
| `experiments/` | 实验、观察、动手活动页 |
| `question-banks/` | 题库页，承载可复用题目条目 |
| `glossary/` | 术语表与速查页 |

---

## 3. 总体建模原则

### 3.1 一页只承载一种主要语义

- 概念页讲“一个概念”
- 路径页讲“怎么学一串概念”
- 实验页讲“做什么活动观察什么现象”
- 题库页讲“围绕哪些概念出哪些题”

不要把“课程介绍 + 概念解释 + 路径 + 练习”全塞进同一页。

### 3.2 frontmatter 管机器，正文管人

- frontmatter 是索引、过滤、链接的结构化真相
- 正文是给学生、老师、教研阅读的自然语言内容

首版禁止把大段教学正文塞进 frontmatter。

### 3.3 文件名不是主键，`id` 才是主键

- 文件名用于组织与人工查找
- `id` 用于程序引用与跨页连接
- 标题可以改，文件名可以迁移，`id` 一旦发布后尽量不变

### 3.4 引用统一用 ID，不用文件路径

例如：

- `prerequisites`
- `experiment_refs`
- `question_refs`
- `path_refs`

都写稳定 ID，不写相对路径。

### 3.5 首版字段保持小而稳

只保留真正参与下列能力的字段：

1. 页面查找
2. 概念过滤
3. 学习路径推进
4. 黑板写回
5. 图谱构建

---

## 4. 命名与 ID 规范

### 4.1 文件名规范

- 文件名统一使用 ASCII
- 采用 `kebab-case`
- 扩展名统一为 `.md`

示例：

- `what-is-a-model.md`
- `ml-foundation-path.md`
- `pendulum-observation.md`
- `ml-beginner-checks.md`

### 4.2 页面 ID 规范

推荐采用“类型语义 + 学科 + 节点语义”的点分结构。

| 页面类型 | 推荐 ID 形态 | 示例 |
|---|---|---|
| 概念页 | `domain.topic.level` | `ml.model.basic` |
| 路径页 | `path.domain.topic.level` | `path.ai.ml.foundation` |
| 实验页 | `exp.domain.topic.name` | `exp.physics.motion.pendulum` |
| 题库页 | `qbank.domain.topic.level` | `qbank.ai.ml.beginner` |
| 题目条目 | `qb.domain.topic.level.nn` | `qb.ai.ml.beginner.01` |
| 术语表页 | `glossary.domain.scope` | `glossary.ai.core` |

说明：

- `concept` 页面不强制在 ID 前面加 `concept.`
- `question_refs` 引用的是**题目条目 ID**，不是题库页 ID
- `source_refs` 首版可以引用外部 source registry 的稳定 ID

### 4.3 控制词建议

#### `page_type`

- `concept`
- `path`
- `experiment`
- `question_bank`
- `glossary`

#### `domain`

首版建议控制在下面几个值：

- `ai`
- `ml`
- `dl`
- `physics`
- `engineering`
- `science`
- `math`

#### `difficulty`

- `beginner`
- `intermediate`
- `advanced`

#### `grade_band`

首版建议使用：

- `10-12`
- `13-15`
- `16-18`

首版主范围是 `10-12` 与 `13-15`，`16-18` 作为兼容扩展保留。

---

## 5. 通用 frontmatter 规范

所有 Wiki 页面都使用 Markdown + YAML frontmatter。

### 5.1 通用必填字段

```yaml
id: ml.model.basic
page_type: concept
title: 什么是模型
grade_band: [10-12, 13-15]
domain: ml
difficulty: beginner
updated_at: 2026-06-02
```

### 5.2 通用可选字段

```yaml
aliases:
  - 模型
summary: 用一句话说明本页讲什么
tags:
  - ai
  - pattern
status: active
source_refs:
  - source/course-ai-week1
```

### 5.3 字段说明

| 字段 | 是否必填 | 说明 |
|---|---|---|
| `id` | 是 | 页面稳定主键 |
| `page_type` | 是 | 页面类型 |
| `title` | 是 | 页面标题 |
| `grade_band` | 是 | 适用年龄段，可多选 |
| `domain` | 是 | 所属学科域 |
| `difficulty` | 是 | 难度级别 |
| `updated_at` | 是 | 页面最后内容更新时间，格式 `YYYY-MM-DD` |
| `aliases` | 否 | 同义词、口语说法、别名 |
| `summary` | 否 | 一句话摘要，供列表页或搜索摘要使用 |
| `tags` | 否 | 补充标签，避免替代 `domain` |
| `status` | 否 | 建议值 `draft` / `active` / `archived` |
| `source_refs` | 否 | 来源引用 ID 列表 |

### 5.4 通用约束

1. frontmatter 只允许使用 YAML 基本类型：字符串、数组、布尔、数字
2. 不在 frontmatter 中放多段正文
3. `updated_at` 统一使用 `YYYY-MM-DD`
4. `id` 全局唯一
5. `aliases` 不应包含和 `title` 完全相同的重复值

---

## 6. 各页面类型 Schema

## 6.1 概念页 `concept`

### frontmatter

```yaml
id: ml.model.basic
page_type: concept
title: 什么是模型
aliases:
  - 模型
grade_band: [10-12, 13-15]
domain: ml
difficulty: beginner
prerequisites:
  - ml.data.basic
  - ml.pattern.basic
learning_objectives:
  - 知道模型是“从例子里总结规律”的工具
misconceptions:
  - 模型不是“把答案背下来”
experiment_refs:
  - exp.ai.sorting.rules
question_refs:
  - qb.ai.ml.beginner.01
path_refs:
  - path.ai.ml.foundation
source_refs:
  - source/course-ai-week1
updated_at: 2026-06-02
```

### 字段说明

| 字段 | 是否必填 | 说明 |
|---|---|---|
| `prerequisites` | 否 | 概念先修节点 ID 列表 |
| `learning_objectives` | 否 | 本页希望学生学会什么 |
| `misconceptions` | 否 | 常见误区摘要，供检索和黑板使用 |
| `experiment_refs` | 否 | 相关实验页 ID |
| `question_refs` | 否 | 相关题目条目 ID |
| `path_refs` | 否 | 相关学习路径页 ID |

### 正文固定段落

- `## 适合学生的解释`
- `## 先修知识`
- `## 常见误区`
- `## 例子`
- `## 动手活动`
- `## 进阶连接`

### 编写要求

1. 一页只讲一个稳定概念
2. 解释优先从现象、例子、任务出发
3. 误区写“学生容易怎样理解错”，不要写成责备口吻
4. 公式和专业术语要服务解释，不要先于解释出现

## 6.2 路径页 `path`

### frontmatter

```yaml
id: path.ai.ml.foundation
page_type: path
title: 机器学习入门路径
grade_band: [10-12, 13-15]
domain: ai
difficulty: beginner
entry_concepts:
  - ml.data.basic
  - ml.pattern.basic
ordered_concepts:
  - ml.data.basic
  - ml.pattern.basic
  - ml.model.basic
  - ml.training.basic
checkpoint_question_refs:
  - qb.ai.ml.beginner.01
  - qb.ai.ml.beginner.02
source_refs:
  - source/course-ai-week1
updated_at: 2026-06-02
```

### 字段说明

| 字段 | 是否必填 | 说明 |
|---|---|---|
| `entry_concepts` | 否 | 路径开始前建议已具备的节点 |
| `ordered_concepts` | 是 | 推荐学习顺序中的概念节点 |
| `checkpoint_question_refs` | 否 | 路径中的检查点题目 ID |

### 正文固定段落

- `## 这条路径适合谁`
- `## 学习目标`
- `## 开始前你最好会什么`
- `## 学习步骤`
- `## 检查点`
- `## 完成标志`

### 编写要求

1. 路径页负责“串联节点”，不重复展开所有概念正文
2. `ordered_concepts` 应保持可执行，不宜过长
3. 首版一条路径建议控制在 `4-8` 个核心概念节点

## 6.3 实验页 `experiment`

### frontmatter

```yaml
id: exp.physics.motion.pendulum
page_type: experiment
title: 摆锤观察实验
grade_band: [10-12, 13-15]
domain: physics
difficulty: beginner
concept_refs:
  - physics.gravity.basic
  - physics.period.basic
materials:
  - 细绳
  - 小重物
  - 尺子
duration_minutes: 15
safety_level: low
source_refs:
  - source/science-lab-week2
updated_at: 2026-06-02
```

### 字段说明

| 字段 | 是否必填 | 说明 |
|---|---|---|
| `concept_refs` | 是 | 该实验关联的概念节点 |
| `materials` | 否 | 所需材料 |
| `duration_minutes` | 否 | 预计时长 |
| `safety_level` | 否 | 建议值 `low` / `medium` / `high` |

### 正文固定段落

- `## 你会观察到什么`
- `## 材料`
- `## 步骤`
- `## 安全提醒`
- `## 记录方式`
- `## 现象解释`
- `## 延伸问题`

### 编写要求

1. 实验页讲“可以做的活动”，不只讲原理
2. 首版优先低门槛、低风险、教室可复现的活动
3. 安全提醒明确写出，不能省略

## 6.4 题库页 `question_bank`

### frontmatter

```yaml
id: qbank.ai.ml.beginner
page_type: question_bank
title: 机器学习入门检查题
grade_band: [10-12, 13-15]
domain: ml
difficulty: beginner
concept_refs:
  - ml.data.basic
  - ml.model.basic
question_count: 6
source_refs:
  - source/course-ai-week1
updated_at: 2026-06-02
```

### 字段说明

| 字段 | 是否必填 | 说明 |
|---|---|---|
| `concept_refs` | 否 | 本页题目主要覆盖的概念节点 |
| `question_count` | 否 | 题目总数，供索引快速展示 |

### 正文固定结构

题库页正文采用“三级标题 = 单题条目”的结构，每题必须带稳定题目 ID。

示例：

```markdown
## 使用说明

适合在“什么是模型”学习后做 3-5 题快速检查。

### qb.ai.ml.beginner.01

- type: single_choice
- concept_refs: [ml.model.basic]
- answer: B
- difficulty: beginner

题干：下面哪一句最接近“模型”的意思？

- A. 把答案全部记住的表格
- B. 从许多例子里总结规律的方法
- C. 一个固定不变的机器零件
- D. 一张课程海报

解析：模型的关键是“从例子中发现规律”，不是死记答案。

### qb.ai.ml.beginner.02

- type: short_answer
- concept_refs: [ml.data.basic, ml.model.basic]
- answer: 开放答案
- difficulty: beginner

题干：为什么模型离不开数据？请用自己的话回答。

解析：题目重点是让学生把“数据提供例子，模型总结规律”说清楚。
```

### 题目条目规则

每道题至少包含：

- 题目 ID
- `type`
- `concept_refs`
- `difficulty`
- 题干
- 解析

推荐题型值：

- `single_choice`
- `multiple_choice`
- `short_answer`
- `true_false`
- `sorting`

### 编写要求

1. `question_refs` 始终引用题目条目 ID，例如 `qb.ai.ml.beginner.01`
2. 不要求每道题拆成单独文件
3. 题库页正文结构必须稳定，方便索引器抽取条目级数据

## 6.5 术语表页 `glossary`

### frontmatter

```yaml
id: glossary.ai.core
page_type: glossary
title: AI 核心术语表
grade_band: [10-12, 13-15]
domain: ai
difficulty: beginner
updated_at: 2026-06-02
```

### 正文固定结构

建议按术语分段：

```markdown
## 模型

一句话解释。

## 数据

一句话解释。
```

### 编写要求

1. 术语表页用于速查，不替代概念页
2. 一条术语定义尽量控制在 `1-3` 句
3. 如某术语已成长为完整概念，应拆出 `concept` 页面

---

## 7. 正文写作规范

### 7.1 面向 K12 的表达原则

1. 优先具体例子，再讲抽象定义
2. 段落短，小标题清楚
3. 尽量使用学生能观察到、能操作到的场景
4. 不用论文口吻，不堆术语
5. 避免“看起来正确但学生无法行动”的空泛表达

### 7.2 概念粒度原则

适合拆成独立 `concept` 页的内容：

- 数据
- 模式
- 模型
- 训练
- 重力
- 力和运动

不适合塞成单一概念页的内容：

- 机器学习完整入门课程总览
- 一整章所有内容混写
- “人工智能全部知识”

### 7.3 误区写法

建议写法：

- “学生容易把模型理解成……”
- “学生可能会误以为……”

不建议写法：

- “学生就是不懂……”
- “这个错误非常低级……”

---

## 8. 索引与查询约束

本页面规范要直接支持下面三类生成文件：

### 8.1 `wiki_index.json`

最小目标：

- 页面基本元数据
- 页面类型
- 标题与别名
- 年龄段、学科、难度
- 关键引用字段

### 8.2 `wiki_link_graph.json`

最小目标：

- `prerequisites`
- `experiment_refs`
- `question_refs`
- `path_refs`
- `concept_refs`
- `ordered_concepts`

可用于：

- 学习路径展开
- 图谱节点渲染
- 黑板当前节点周边扩展

### 8.3 `wiki_search_index.json`

最小目标：

- `title`
- `aliases`
- `summary`
- 主要小标题
- 局部正文摘要

### 8.4 查询策略对 Schema 的要求

当前查询策略为：

1. frontmatter 过滤
2. 标题 / alias / 关键词检索
3. link graph 扩展
4. 必要时局部全文搜索

因此本 Schema 必须保证：

1. 关键筛选信息都在 frontmatter
2. 正文段落标题稳定可抽取
3. 引用字段语义清楚，不混用

---

## 9. 校验规则

在索引构建阶段，建议对每个页面执行下面的校验：

1. `id` 非空且全局唯一
2. `page_type` 合法
3. `grade_band` 至少有一个值
4. `updated_at` 符合日期格式
5. 所有引用字段中的 ID 都能被解析或被白名单 source registry 接受
6. 概念页包含规定的正文段落
7. 路径页存在 `ordered_concepts`
8. 实验页存在 `concept_refs`
9. 题库页中的题目条目 ID 不重复

---

## 10. 最小样例

## 10.1 概念页样例

```markdown
---
id: ml.model.basic
page_type: concept
title: 什么是模型
aliases:
  - 模型
grade_band: [10-12, 13-15]
domain: ml
difficulty: beginner
prerequisites:
  - ml.data.basic
  - ml.pattern.basic
learning_objectives:
  - 知道模型是“从例子里总结规律”的工具
misconceptions:
  - 模型不是“把答案背下来”
experiment_refs:
  - exp.ai.sorting.rules
question_refs:
  - qb.ai.ml.beginner.01
path_refs:
  - path.ai.ml.foundation
updated_at: 2026-06-02
---

## 适合学生的解释

模型像是在很多例子里找规律的“总结器”。

## 先修知识

先知道什么是数据，什么是规律。

## 常见误区

学生容易把模型理解成把答案都记住的盒子。

## 例子

看很多水果图片后，试着总结“苹果大概长什么样”。

## 动手活动

把不同颜色和形状的卡片分组，再总结你的分类规则。

## 进阶连接

后面可以继续看训练、测试和泛化。
```

## 10.2 路径页样例

```markdown
---
id: path.ai.ml.foundation
page_type: path
title: 机器学习入门路径
grade_band: [10-12, 13-15]
domain: ai
difficulty: beginner
ordered_concepts:
  - ml.data.basic
  - ml.pattern.basic
  - ml.model.basic
  - ml.training.basic
updated_at: 2026-06-02
---

## 这条路径适合谁

适合第一次系统接触机器学习的学生。

## 学习目标

知道数据、规律、模型、训练之间的基本关系。

## 开始前你最好会什么

能理解“分类”和“找共同点”。

## 学习步骤

按 `ordered_concepts` 的顺序学习。

## 检查点

能回答“模型为什么离不开数据”。

## 完成标志

能用自己的话把机器学习入门流程讲出来。
```

---

## 11. 落地结论

CoLearn v1 的 Wiki 规范，核心就是三句话：

1. **内容真相放 Markdown 页面里**
2. **结构真相放 frontmatter 里**
3. **连接真相放稳定 ID 和引用字段里**

这份 Schema 定下来后，后面的 `WikiIndexBuilder`、`WikiQueryService`、图谱构建、黑板节点推进，就都能围绕同一套页面语义工作。
