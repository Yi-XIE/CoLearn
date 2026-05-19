"""Prompt template for deriving a fresh BoardFacts snapshot from event stream."""

from __future__ import annotations

import json
from typing import Any


BOARD_CONSOLIDATION_SYSTEM = """你是一个学习状态分析器。你的任务是根据学生最近的学习事件流，推断出一份准确的"学习状态快照"。

输出必须是严格的 JSON，遵循指定 schema。如果某个字段无法从事件中可靠推断，保留上一次快照的对应值。
"""


BOARD_CONSOLIDATION_USER_TEMPLATE = """## 学习项目
{project_summary}

## 上一次学习状态快照（可能已过时）
```json
{current_board_json}
```

## 最近 {event_count} 条学习事件（按时间顺序）
{events_formatted}

## 输出要求
请输出一份 JSON 学习状态快照，schema 如下：

```json
{{
  "current_turn_mode": "EXPLORE | ANCHOR | CORRECTION | VERIFY | PAUSED",
  "mastery_level": 0.0-1.0,
  "cognitive_load": "LOW | NORMAL | HIGH",
  "active_node_id": "学生当前关注的概念 id（短小标识符）",
  "active_node_label": "概念的可读标签",
  "critical_blockers": [
    {{"id": "b1", "type": "CONCEPT_MISUNDERSTANDING", "desc": "具体描述学生卡在哪里"}}
  ],
  "unverified_gaps": ["学生还未掌握但未明确表述困惑的子概念"],
  "next_prompt_hint": "下一轮该聚焦的方向（一句话）"
}}
```

## 推断规则
- mastery_level: 综合 understood_concept 数 vs still_blocked 数；初学者 0.0-0.3；中级 0.4-0.7；熟练 0.8-1.0
- cognitive_load: 最近 3 轮里 still_blocked 信号密集 → HIGH；交替 understood/blocked → NORMAL；连续 understood → LOW
- current_turn_mode:
  * 学生有强烈困惑（≥1 critical_blocker）→ CORRECTION
  * 学生刚理解某概念，需要练习巩固 → VERIFY
  * 学生缺基础（≥2 unverified_gaps）→ ANCHOR
  * 学生流畅探索新内容 → EXPLORE
- critical_blockers: 从 still_blocked 事件中提取，去重，最多 3 条
- 仅输出 JSON，不要任何 markdown 标记或解释文字
"""


def format_event_for_prompt(event: Any) -> str:
    """Compact one-line representation of a MemoryEvent for the prompt."""
    kind = getattr(event, "kind", None) or (event.get("kind") if isinstance(event, dict) else "event")
    payload = getattr(event, "payload", None) or (event.get("payload") if isinstance(event, dict) else {}) or {}

    summary_parts = []
    if "concept" in payload:
        summary_parts.append(f"concept={payload['concept']}")
    if "summary" in payload:
        summary_parts.append(f"summary={str(payload['summary'])[:80]}")
    if "final_text" in payload:
        summary_parts.append(f"text={str(payload['final_text'])[:80]}")
    if "turn_mode" in payload:
        summary_parts.append(f"mode={payload['turn_mode']}")
    if "patch_keys" in payload:
        summary_parts.append(f"patch=[{','.join(payload['patch_keys'][:5])}]")

    detail = "; ".join(summary_parts) if summary_parts else json.dumps(payload, ensure_ascii=False)[:120]
    return f"- [{kind}] {detail}"


def build_consolidation_user_prompt(
    *,
    project_summary: str,
    current_board: dict[str, Any],
    events: list[Any],
) -> str:
    events_formatted = "\n".join(format_event_for_prompt(e) for e in events) or "(no events)"
    return BOARD_CONSOLIDATION_USER_TEMPLATE.format(
        project_summary=project_summary,
        current_board_json=json.dumps(current_board, ensure_ascii=False, indent=2),
        event_count=len(events),
        events_formatted=events_formatted,
    )
