---
# 通用必填字段
id: ml.model.basic                    # 页面稳定主键，全局唯一
page_type: concept                     # 页面类型：concept
title: 什么是模型                      # 页面标题
grade_band: [10-12, 13-15]            # 适用年龄段，可多选
domain: ml                             # 所属学科域：ai/ml/dl/physics/engineering/science/math
difficulty: beginner                   # 难度级别：beginner/intermediate/advanced
updated_at: 2026-06-02                # 页面最后更新时间 YYYY-MM-DD

# 通用可选字段
aliases:                               # 同义词、口语说法、别名
  - 模型
  - AI模型
summary: 用一句话说明模型是什么       # 一句话摘要
tags:                                  # 补充标签
  - ai
  - pattern
status: active                         # draft/active/archived
source_refs:                           # 来源引用 ID
  - source/course-ai-week1

# 概念页专属字段
prerequisites:                         # 概念先修节点 ID 列表
  - ml.data.basic
  - ml.pattern.basic
learning_objectives:                   # 本页希望学生学会什么
  - 知道模型是"从例子里总结规律"的工具
  - 理解模型和"背答案"的区别
misconceptions:                        # 常见误区摘要
  - 模型不是"把答案背下来"
  - 模型不是"记住所有训练数据"
experiment_refs:                       # 相关实验页 ID
  - exp.ai.sorting.rules
question_refs:                         # 相关题目条目 ID
  - qb.ai.ml.beginner.01
  - qb.ai.ml.beginner.02
path_refs:                             # 相关学习路径页 ID
  - path.ai.ml.foundation
---

## 适合学生的解释

（用简单的语言解释这个概念，从现象、例子、任务出发）

机器学习中的"模型"就像是一个能从例子里学会规律的工具。

## 先修知识

在学习这个概念之前，你最好已经了解：
- 什么是数据（ml.data.basic）
- 什么是模式识别（ml.pattern.basic）

## 常见误区

**误区1：模型是把答案背下来**
- 很多同学以为模型是"记住"所有训练数据的答案
- 实际上，模型是学习数据中的规律

**误区2：模型能100%准确**
- 模型学到的是"大概率的规律"，不是绝对真理

## 例子

**例子1：天气预报模型**
- 输入：过去100天的温度、湿度、气压数据
- 模型学到的规律："气压突然下降 + 湿度上升 → 可能下雨"

## 动手活动

推荐实验：
- [卡片分类游戏](exp.ai.sorting.rules)

## 进阶连接

学完这个概念后，你可以继续学习：
- 模型是怎么训练的？（ml.training.basic）
