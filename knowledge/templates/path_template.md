---
# 通用必填字段
id: path.ai.ml.foundation              # 路径页 ID 格式：path.domain.topic.level
page_type: path                         # 页面类型：path
title: 机器学习入门路径                 # 页面标题
grade_band: [10-12, 13-15]             # 适用年龄段
domain: ai                              # 所属学科域
difficulty: beginner                    # 难度级别
updated_at: 2026-06-02                 # 更新时间

# 通用可选字段
summary: 从零开始学习机器学习的基础概念
status: active
source_refs:
  - source/course-ai-week1

# 路径页专属字段
entry_concepts:                         # 路径开始前建议已具备的节点（可选）
  - math.basic.arithmetic
ordered_concepts:                       # 推荐学习顺序中的概念节点（必填）
  - ml.data.basic
  - ml.pattern.basic
  - ml.model.basic
  - ml.training.basic
checkpoint_question_refs:               # 路径中的检查点题目 ID（可选）
  - qb.ai.ml.beginner.01
  - qb.ai.ml.beginner.02
---

## 这条路径适合谁

这条路径适合：
- 10-15岁的学生，对AI和机器学习感兴趣
- 没有编程基础也可以学习
- 希望通过例子和动手活动理解机器学习原理

## 学习目标

完成这条路径后，你将能够：
- 理解什么是机器学习，它和普通程序有什么不同
- 知道机器学习的基本流程：数据 → 训练 → 模型 → 预测
- 能用简单的语言向别人解释机器学习的工作原理

## 开始前你最好会什么

- 基本的数学运算（加减乘除）
- 能够观察和比较事物的规律
- 没有其他硬性要求

## 学习步骤

### 第1步：什么是数据（ml.data.basic）
了解机器学习的"食材"——数据。
- 预计时间：20分钟
- 动手活动：收集身边的数据

### 第2步：什么是模式（ml.pattern.basic）
学习如何从数据中发现规律。
- 预计时间：30分钟
- 动手活动：找出图片中的共同特征

### 第3步：什么是模型（ml.model.basic）
理解模型是如何学习规律的。
- 预计时间：25分钟
- 动手活动：卡片分类游戏

### 第4步：什么是训练（ml.training.basic）
学习模型是怎么从数据中学习的。
- 预计时间：30分钟
- 动手活动：调整参数游戏

## 检查点

在以下节点完成后，建议做对应的检查题：
- 完成"什么是模型"后 → 做题 qb.ai.ml.beginner.01
- 完成"什么是训练"后 → 做题 qb.ai.ml.beginner.02

## 完成标志

当你能够：
- 向朋友解释"机器学习是怎么工作的"
- 举出3个生活中机器学习的例子
- 理解模型、训练、预测这三个概念的关系

恭喜你完成了机器学习入门路径！
