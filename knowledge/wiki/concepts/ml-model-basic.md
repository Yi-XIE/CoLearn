---
id: ml.model.basic
page_type: concept
title: 什么是模型
aliases:
  - 模型
  - AI模型
grade_band: [10-12, 13-15]
domain: ml
difficulty: beginner
prerequisites:
  - ml.data.basic
  - ml.pattern.basic
learning_objectives:
  - 知道模型是"从例子里总结规律"的工具
  - 理解模型和"背答案"的区别
misconceptions:
  - 模型是"把答案背下来"
  - 模型能100%准确
experiment_refs:
  - exp.ai.sorting.rules
question_refs:
  - qb.ai.ml.beginner.01
path_refs:
  - path.ai.ml.foundation
updated_at: 2026-06-02
---

## 适合学生的解释

机器学习中的"模型"就像是一个能从例子里学会规律的工具。

想象你教小朋友认水果：给他看几个苹果、几个香蕉，他就能学会"圆的红的可能是苹果，长的黄的可能是香蕉"。模型也是这样工作的。

## 先修知识

在学习这个概念之前，你最好已经了解：
- 什么是数据（ml.data.basic）
- 什么是模式（ml.pattern.basic）

## 常见误区

**误区1：模型是把答案背下来**
- 很多同学以为模型是"记住"所有训练数据
- 实际上，模型是学习数据中的规律

**误区2：模型能100%准确**
- 模型学到的是"大概率的规律"，不是绝对真理
- 就像人类也会判断错，模型也可能出错

## 例子

**例子1：天气预报模型**
- 输入：过去100天的温度、湿度、气压数据
- 模型学到的规律："气压突然下降 + 湿度上升 → 可能下雨"

**例子2：垃圾邮件识别模型**
- 输入：1000封垃圾邮件和1000封正常邮件
- 模型学到的规律："包含'中奖''免费'等词 + 很多感叹号 → 可能是垃圾邮件"

## 动手活动

推荐实验：卡片分类游戏（exp.ai.sorting.rules）

## 进阶连接

学完这个概念后，你可以继续学习：
- 模型是怎么训练的？（ml.training.basic）
