---
name: deliberate-practice
description: 刻意练习——当学生已经理解概念但需要巩固和自动化时，设计针对性练习：分解子技能、即时反馈、间隔重复、逐步提高难度。适合 EXPLORE（扩展应用）和 VERIFY（巩固检验）场景，mastery_level 0.4+ 时效果最好。
always: false
---

# Deliberate Practice

## When to Use

- Student understands the concept (mastery_level >= 0.4) but hasn't automated it
- No critical blockers — understanding is in place, fluency is not
- Turn mode: EXPLORE (apply in new contexts) or VERIFY (consolidate)
- Goal: move from "I understand" to "I can do it reliably"

## How to Apply

1. **Decompose the skill** into sub-components the student can practice independently.
   - "矩阵乘法" → (1) 识别维度兼容性 (2) 逐元素计算 (3) 验证结果维度

2. **Design a focused drill** targeting the weakest sub-component.
   - Start just above current ability level (zone of proximal development)
   - One variable at a time — don't combine difficulties

3. **Provide immediate feedback** after each attempt.
   - Show correct answer + where the student diverged
   - "你在第二步把行列搞反了——注意是第 i 行乘第 j 列"

4. **Vary the context** to prevent pattern-matching without understanding.
   - Same concept, different numbers / dimensions / notation
   - Transfer: "现在用同样的方法算一个 3×2 乘 2×4 的情况"

5. **Space repetitions** — revisit after delay to strengthen long-term retention.
   - Flag for review in next session (via memory_events)
   - "我们下次回来再做两道类似的题，看看还记不记得"

## Practice Design Template

```
Skill: [target sub-skill]
Difficulty: [current level → target level]
Format: [calculation / proof / explanation / application]
Constraints: [time limit / no calculator / from memory]
Success criteria: [3 correct in a row / explain why / spot the error]
Feedback: [immediate correction + one-sentence explanation]
```

## Example Dialogue

```
Tutor: 你已经理解了行列式的定义。现在来练习计算——先从 2×2 开始。
Tutor: 计算 det([[3,1],[2,4]])。
Student: 3×4 - 1×2 = 10。
Tutor: 正确！现在试试 det([[5,-2],[3,1]])。
Student: 5×1 - (-2)×3 = 5+6 = 11。
Tutor: 完美。注意你处理负号很流畅。升级到 3×3——用余子式展开。
```

## Complements

- Use after **feynman-technique** confirms understanding
- If practice reveals a deeper gap → fall back to **socratic-questioning**
- Pairs with spaced repetition (memory_events flag for future review)
