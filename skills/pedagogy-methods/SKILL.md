---
name: pedagogy-methods
description: 教学法选择与落地技能。Use when CoLearn needs to design lessons, learning activities, projects, assessments, tutoring flows, AI learning companions, teacher aids, or curriculum plans using evidence-informed pedagogy; trigger for 教学法、教案、课程设计、学习活动、项目式学习、探究式学习、显性教学、差异化、UDL、形成性评价、元认知、协作学习、翻转课堂、检索练习、间隔复习、脚手架.
---

# Pedagogy Methods

## Core Workflow

1. Clarify the learning job:
   - 学习目标：知识、技能、迁移、态度中的哪一种为主。
   - 学习者：年龄段、先验知识、动机、特殊支持需求。
   - 场景约束：课堂/线上/混合、时长、人数、工具、评价要求。
   - 产品形态：教案、AI tutor、任务卡、项目制课程、练习系统、教师备课助手。

2. Select a primary method and supporting methods:
   - For new or difficult knowledge, prefer explicit instruction, worked examples, scaffolding, retrieval practice.
   - For transfer, authenticity, and motivation, consider PBL, problem-based learning, inquiry, case-based learning.
   - For broad access and learner variability, add UDL and differentiation.
   - For durable learning, add spaced practice, interleaving, formative assessment, metacognition.
   - For social knowledge construction, add collaborative learning with clear roles and accountability.

3. Convert the method into product behavior:
   - Define learner actions, teacher/AI actions, artifacts produced, feedback loops, and evidence of learning.
   - Include a minimum viable classroom version and an AI-native enhancement.
   - Avoid vague labels such as "use PBL"; specify launch question, inquiry cycle, checkpoints, critique, and final product.

4. Validate the design:
   - Check cognitive load: do novices receive enough modeling and practice before open-ended work.
   - Check assessment alignment: every task should generate evidence tied to the learning goal.
   - Check inclusion: provide multiple ways to access content, express understanding, and stay engaged.
   - Check operational feasibility: teacher preparation, class time, grouping, rubrics, and tool dependencies.

## Reference Selection

- Use `references/method-cards.md` for concise cards of common pedagogy methods and when to use them.
- Use `references/selection-matrix.md` when choosing or combining methods for a specific learning goal.
- Use `references/product-patterns.md` when translating pedagogy into CoLearn product features.
- Use `references/sources.md` when citations, evidence notes, or source links are needed.

Load only the reference file needed for the current task.

## Output Standards

Prefer concrete artifacts:
- Lesson flow with timed phases.
- AI tutor behavior script.
- Teacher facilitation notes.
- Student task cards.
- Rubric or formative assessment checklist.
- Product requirement snippets for learning features.

For every recommended method, state:
- Why this method fits the learning job.
- How it appears in learner-facing experience.
- What evidence shows the learner is progressing.
- What risk to watch for and how to mitigate it.

Do not output unfinished placeholder tokens. If information is missing, write `待确认：` followed by the specific missing information.
