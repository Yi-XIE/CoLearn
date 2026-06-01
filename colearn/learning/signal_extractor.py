"""Heuristic learning-signal extraction from final turn text.

When the LLM doesn't emit structured `learning_events` in its raw payload, the
harness still needs to know whether the student understood, got blocked, or asked
for more — otherwise the state machine goes blind. This module provides cheap
pattern-based extraction that runs as a fallback signal source.

Signals extracted (best-effort, conservative):
- understood_concept: "理解了X" / "I understand X" / "搞清楚了X"
- still_blocked: "还是不懂X" / "I'm confused about X" / "不明白X"
- asked_clarification: explicit question patterns ending in 吗/？/?
"""

from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

from colearn.learning.events import MemoryEventKind


# Capture group naming convention: (?P<concept>...) for the topic the student
# understood / is blocked on. Patterns prefer Chinese first (primary user base)
# but accept English as a fallback. Each pattern is anchored at sentence-ish
# boundaries to avoid greedy matches across multiple sentences.
_UNDERSTOOD_PATTERNS = [
    re.compile(r"(?:已经|现在|刚刚)?(?:理解|掌握|学会|搞清楚|搞懂|明白)了?\s*(?P<concept>[^。！\n]{1,50})"),
    re.compile(r"(?:I|I'?ve)\s+(?:understand|understood|got|learned)\s+(?P<concept>[^.!\n]{1,80})", re.IGNORECASE),
]

_BLOCKED_PATTERNS = [
    re.compile(r"(?:还是|依然|仍然|怎么|为什么)?(?:不懂|不明白|搞不清|搞不懂|疑惑|困惑)\s*(?P<concept>[^。！？\n]{1,50})"),
    re.compile(r"(?:I'?m|I am)\s+(?:confused|stuck|lost)\s+(?:about|on|with)\s+(?P<concept>[^.!?\n]{1,80})", re.IGNORECASE),
    re.compile(r"(?:don'?t|do not|can'?t|cannot)\s+(?:understand|get)\s+(?P<concept>[^.!?\n]{1,80})", re.IGNORECASE),
]

# Bare keyword markers used as a coarse fallback when no concept-bearing pattern
# matches but the text still clearly signals a state. Chinese-first, English
# fallback — mirrors the product's default language. These power the board state
# machine (turn-mode transitions), which previously hard-coded English-only
# markers and so went blind on Chinese turns.
_UNDERSTOOD_MARKERS = (
    "理解了", "懂了", "明白了", "学会了", "掌握了", "搞清楚了", "搞懂了", "会了", "清楚了",
    "understand", "understood", "got it", "makes sense", "i see",
)
_BLOCKED_MARKERS = (
    "不懂", "不明白", "没懂", "没听懂", "搞不清", "搞不懂", "不会", "不太懂", "疑惑", "困惑", "卡住", "听不懂",
    "confused", "stuck", "unclear", "unsure", "uncertain", "lost", "don't understand", "do not understand",
)
# Explicit node-completion markers (a node/topic is done, not merely understood).
# Kept distinct from understood-markers so callers can require a stronger signal
# before marking a plan node complete.
_COMPLETION_MARKERS = (
    "完成了", "讲完了", "学完了", "结束了", "通过了", "已完成", "搞定了", "过关了",
    "completed", "done", "finished", "resolved", "mastered",
)


def detect_understood(text: str) -> bool:
    """True if the text signals the student understood something (bilingual)."""
    return _matches_any(text, _UNDERSTOOD_MARKERS) or _matches_patterns(text, _UNDERSTOOD_PATTERNS)


def detect_blocked(text: str) -> bool:
    """True if the text signals the student is blocked/confused (bilingual)."""
    return _matches_any(text, _BLOCKED_MARKERS) or _matches_patterns(text, _BLOCKED_PATTERNS)


def detect_completion(text: str) -> bool:
    """True if the text signals a node/topic was completed (bilingual)."""
    return _matches_any(text, _COMPLETION_MARKERS)


def extract_blocked_concept(text: str) -> str:
    """Return the concept the student is blocked on, or "" if none parseable."""
    for pattern in _BLOCKED_PATTERNS:
        match = pattern.search(text or "")
        if match:
            concept = _clean_concept(match.group("concept"))
            if concept:
                return concept
    return ""


def extract_understood_concepts(text: str) -> list[str]:
    """Return distinct concepts the student reported understanding."""
    concepts: list[str] = []
    seen: set[str] = set()
    for pattern in _UNDERSTOOD_PATTERNS:
        for match in pattern.finditer(text or ""):
            concept = _clean_concept(match.group("concept"))
            if concept and concept.lower() not in seen:
                seen.add(concept.lower())
                concepts.append(concept)
    return concepts


def _matches_any(text: str, markers: tuple[str, ...]) -> bool:
    if not text:
        return False
    lowered = text.lower()
    return any(marker in lowered for marker in markers)


def _matches_patterns(text: str, patterns: list[re.Pattern[str]]) -> bool:
    if not text:
        return False
    return any(pattern.search(text) for pattern in patterns)


def extract_learning_signals(final_text: str) -> list[dict[str, Any]]:
    """Return a list of MemoryEvent-shaped dicts extracted from final_text.

    Each event has: event_id, kind, payload (concept, source, raw_match).
    Empty list if no signals match. Caller merges with payload-supplied events
    (LLM-emitted ones take precedence on duplicates).
    """
    if not final_text or not final_text.strip():
        return []

    events: list[dict[str, Any]] = []
    seen_concepts: set[tuple[str, str]] = set()

    for pattern in _UNDERSTOOD_PATTERNS:
        for match in pattern.finditer(final_text):
            concept = _clean_concept(match.group("concept"))
            if not concept:
                continue
            key = ("understood_concept", concept.lower())
            if key in seen_concepts:
                continue
            seen_concepts.add(key)
            events.append(_make_event(MemoryEventKind.UNDERSTOOD_CONCEPT, concept, match.group(0)))

    for pattern in _BLOCKED_PATTERNS:
        for match in pattern.finditer(final_text):
            concept = _clean_concept(match.group("concept"))
            if not concept:
                continue
            key = ("still_blocked", concept.lower())
            if key in seen_concepts:
                continue
            seen_concepts.add(key)
            events.append(_make_event(MemoryEventKind.STILL_BLOCKED, concept, match.group(0)))

    return events


def _clean_concept(raw: str) -> str:
    text = (raw or "").strip()
    text = text.strip("，,.;:：")
    text = " ".join(text.split())
    if len(text) < 2:
        return ""
    return text


def _make_event(kind: str, concept: str, raw_match: str) -> dict[str, Any]:
    return {
        "event_id": str(uuid4()),
        "kind": kind,
        "payload": {
            "concept": concept,
            "source": "extracted_heuristic",
            "raw_match": raw_match[:200],
        },
    }
