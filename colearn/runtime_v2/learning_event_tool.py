"""Learning event reporting tool for structured signal extraction."""

from __future__ import annotations


def emit_learning_events(events: list[dict]) -> str:
    """Report learning state changes observed during this turn.

    The model calls this tool to report significant learning events such as:
    - Student understood a concept (NODE_COMPLETED)
    - Student started learning a new node (NODE_STARTED)
    - Student encountered a blocker (BLOCKER_FOUND)
    - A blocker was resolved (BLOCKER_RESOLVED)
    - Evidence was attached (EVIDENCE_ATTACHED)

    Args:
        events: List of learning events, each with 'type' and 'payload' fields.

    Returns:
        Confirmation message.
    """
    return f"已记录 {len(events)} 个学习事件"


# JSON Schema for the tool
LEARNING_EVENT_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "events": {
            "type": "array",
            "description": "List of learning events to report",
            "items": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": [
                            "NODE_COMPLETED",
                            "NODE_STARTED",
                            "BLOCKER_FOUND",
                            "BLOCKER_RESOLVED",
                            "EVIDENCE_ATTACHED",
                            "CONTINUATION_UPDATED",
                        ],
                        "description": "Type of learning event",
                    },
                    "payload": {
                        "type": "object",
                        "description": "Event-specific data",
                        "properties": {
                            "node_id": {"type": "string", "description": "Node identifier"},
                            "node_label": {"type": "string", "description": "Node label"},
                            "id": {"type": "string", "description": "Blocker identifier"},
                            "type": {"type": "string", "description": "Blocker type"},
                            "desc": {"type": "string", "description": "Blocker description"},
                            "source_ref": {"type": "string", "description": "Source reference"},
                            "tool_name": {"type": "string", "description": "Tool name"},
                            "chunk_id": {"type": "string", "description": "Chunk identifier"},
                            "next_prompt_hint": {"type": "string", "description": "Next prompt hint"},
                        },
                    },
                },
                "required": ["type", "payload"],
            },
        },
    },
    "required": ["events"],
}
