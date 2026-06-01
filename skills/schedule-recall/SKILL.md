---
name: schedule-recall
description: 召回调度——session 结束时决定下次复习什么、什么时候提醒用户回来，用户下次进来时展示复习引导。
always: false
---

# Schedule Recall

## When to Use

- After session-reflect completes (as part of session end flow)
- User returns after 24+ hours (display recall prompt)
- BoardFacts.learning_phase == "recall"

## How to Apply

### At Session End (Schedule)

Based on the reflect episode, determine what to review next:

1. **Identify weakest concepts** — from episode.concepts_blocked + low mastery items
2. **Apply simplified spacing rule**:
   - First review: 24 hours after learning
   - Second review: 3 days after first review
   - Third review: 7 days after second review
3. **Write recall record**:
   ```json
   {
     "next_recall_at": "2026-05-31T10:00:00Z",
     "recall_items": [
       {"concept": "斜面分力方向", "priority": "high", "last_seen": "2026-05-30"},
       {"concept": "牛顿第二定律应用", "priority": "medium", "last_seen": "2026-05-30"}
     ],
     "recall_strategy": "2 quick questions then continue new material",
     "scheduled_from_session": "session_id"
   }
   ```

### At Session Start (Recall Display)

When user returns and a recall is due:

1. **Check if recall is due** — compare now vs next_recall_at
2. **Present recall prompt**:
   ```
   👋 欢迎回来！上次你学了 [topics]。
   有一个地方我们还没完全搞定：[blocked concept]
   先来 2 道快速复习题热热身？
   ```
3. **Run 2-3 recall questions** using socratic-questioning or deliberate-practice skill
4. **Update mastery** based on recall performance
5. **Clear or reschedule** the recall item

## Integration

- Recall records stored in session metadata (next_recall field)
- PreflightStage checks for due recalls on session start
- Frontend displays recall banner when recall is pending

## Tone

- Welcoming on return ("欢迎回来！")
- Brief recall (2-3 questions max, not a full quiz)
- Transition smoothly to new material after recall
