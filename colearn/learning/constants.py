"""Central constants for the learning domain — replaces scattered magic strings."""

from __future__ import annotations

from enum import StrEnum


class LearningPhase(StrEnum):
    INTAKE = "intake"
    DIAGNOSE = "diagnose"
    READY = "ready"
    REFLECT = "reflect"
    RECALL = "recall"


class TurnMode(StrEnum):
    LEARN = "LEARN"
    CHECK = "CHECK"
    PAUSED = "PAUSED"


class CognitiveLoad(StrEnum):
    NORMAL = "NORMAL"
    HIGH = "HIGH"


class BlockerType(StrEnum):
    CONCEPT_MISUNDERSTANDING = "CONCEPT_MISUNDERSTANDING"


class NodeStatus(StrEnum):
    PENDING = "pending"
    CURRENT = "current"
    COMPLETED = "completed"


class LearningEventType(StrEnum):
    NODE_COMPLETED = "NODE_COMPLETED"
    NODE_STARTED = "NODE_STARTED"
    BLOCKER_FOUND = "BLOCKER_FOUND"
    EVIDENCE_ATTACHED = "EVIDENCE_ATTACHED"
    CONTINUATION_UPDATED = "CONTINUATION_UPDATED"
    SESSION_REFLECTED = "SESSION_REFLECTED"
    RECALL_SCHEDULED = "RECALL_SCHEDULED"
    RECALL_COMPLETED = "RECALL_COMPLETED"
    INTAKE_COMPLETED = "INTAKE_COMPLETED"
    DIAGNOSE_COMPLETED = "DIAGNOSE_COMPLETED"


class StreamEventType(StrEnum):
    CONTENT_DELTA = "content_delta"
    REASONING_DELTA = "reasoning_delta"
    REASONING_END = "reasoning_end"
    STREAM_END = "stream_end"
    TOOL_CALL = "tool_call"
    TOOL_EVENT = "tool_event"
