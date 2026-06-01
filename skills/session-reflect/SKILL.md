---
name: session-reflect
description: 学习总结——session 结束时（用户主动结束或里程碑达成），生成结构化的本次学习总结，包含学了什么、卡在哪、下次该学什么，写入长期记忆。
always: false
---

# Session Reflect

## When to Use

- User explicitly ends a learning session ("结束"、"今天就到这"、"done"、"stop")
- A learning plan milestone is reached (NODE_COMPLETED on last planned node)
- Session message count exceeds threshold without prior reflect
- BoardFacts.learning_phase == "reflect"

## How to Apply

Generate a **structured episode summary** by scanning the session's learning events and messages.

### Steps

1. **Scan session events** — collect all LearningEvents from this session:
   - NODE_COMPLETED events → topics covered
   - BLOCKER_FOUND events → sticking points
   - EVIDENCE_ATTACHED events → sources used
   - Turn mode transitions → learning rhythm

2. **Identify key outcomes**:
   - Concepts understood (from signal_extractor UNDERSTOOD_CONCEPT)
   - Concepts still blocked (from STILL_BLOCKED signals)
   - Mastery changes (compare start vs end StudentSnapshot)

3. **Generate user-facing summary** (in user's language):
   ```
   📚 今天的学习总结：
   - 学了：[topic 1]、[topic 2]
   - 掌握了：[concept A]（从不懂到理解）
   - 还需要巩固：[concept B]（明天复习）
   - 用时：约 [N] 分钟
   ```

4. **Generate structured episode** for persistence:
   ```json
   {
     "episode_id": "ep_xxx",
     "session_id": "...",
     "completed_at": "2026-05-30T10:30:00Z",
     "duration_minutes": 25,
     "topics_covered": ["牛顿第二定律", "力的分解"],
     "concepts_mastered": ["F=ma 的含义"],
     "concepts_blocked": ["斜面分力方向"],
     "mastery_delta": {"physics_mechanics": 0.15},
     "next_focus": "斜面分力方向 — 需要更多例子",
     "mood_signal": "engaged"
   }
   ```

5. **Write to memory**:
   - Append episode to MemoryDocStateService "summary" document
   - Emit SESSION_REFLECTED memory event
   - Update StudentSnapshot.mastery_level if changed

## Tone

- Celebratory for progress ("不错！今天搞定了两个知识点")
- Honest about gaps ("有一个地方还没完全通，明天我们再看看")
- Forward-looking ("下次我们从 X 开始")

## Output

Present the summary to the user as a formatted message, then persist the structured episode silently.
