---
name: profile-intake
description: 新用户引导——首次进入学习模式时，通过 5 个简短问题收集用户画像（年龄/年级、兴趣方向、时间预算、背景知识、学习偏好），为后续个性化教学提供基础数据。
always: false
---

# Profile Intake

## When to Use

- First time a user enters learning mode (no existing profile)
- User explicitly asks to update their profile
- BoardFacts.learning_phase == "intake"

## How to Apply

Run a **conversational intake** — not a form. Ask one question at a time, adapt based on answers. Keep it warm and brief (under 2 minutes total).

### Question Sequence

1. **Grade/Age** — "你现在几年级？（或者你大概多大？）"
   - Determines language complexity and example selection
   - Accept fuzzy answers ("初中" → grade 7-9 range)

2. **Subject Interest** — "你最想学什么？可以是一个学科、一个具体问题、或者一本书。"
   - Seeds the first learning plan
   - If vague, offer 3 suggestions based on grade level

3. **Time Budget** — "你每周大概能花多少时间学习？（比如每天 20 分钟，或者周末集中 2 小时）"
   - Determines session pacing and plan granularity
   - Default: 30 min/day if user is unsure

4. **Prior Knowledge** — "关于 [subject from Q2]，你已经知道些什么？学过哪些相关的东西？"
   - Seeds initial mastery estimate (before formal diagnose phase)
   - Accept "nothing" as valid answer

5. **Learning Style** — "你喜欢怎么学？比如：看例子、做题、听讲解、自己探索？"
   - Influences skill selection (socratic vs feynman vs deliberate-practice)
   - Map to preference tags: examples / exercises / explanation / exploration

## Output Format

After collecting answers, synthesize into a structured profile:

```json
{
  "grade_level": "初二",
  "age_range": "13-14",
  "primary_interest": "物理-力学",
  "time_budget_weekly_minutes": 150,
  "prior_knowledge": "知道牛顿三定律的名字，但不太理解应用",
  "learning_style_preferences": ["examples", "exercises"],
  "intake_completed_at": "2026-05-30T10:00:00Z"
}
```

## Tone

- Friendly, not clinical
- Use age-appropriate language (detected from Q1 answer)
- If user seems impatient, compress remaining questions into one
- End with encouragement: "好的，我对你有了基本了解。接下来我们开始吧！"

## Integration

- Write profile to MemoryDocStateService "profile" document
- Set BoardFacts.learning_phase = "ready" after completion
- Trigger diagnose phase if user provided a specific subject interest
