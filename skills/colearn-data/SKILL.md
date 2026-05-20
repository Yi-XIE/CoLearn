---
name: colearn-data
description: Access CoLearn learning state (projects, sessions, memory, retrieval)
always: true
---

# CoLearn Data Access

Use `exec` to query CoLearn learning state when you need project context, memory, or session info.

## Commands

```bash
python -m colearn.cli list_projects
python -m colearn.cli list_sessions --project_id <id>
python -m colearn.cli search_memory --query "关键词" [--session_id <id>] [--project_id <id>] [--limit 5]
python -m colearn.cli retrieve --project_id <id> --query "问题" [--session_id <id>]
```

## When to use

- `search_memory`: find past learning events (what the student understood, got stuck on, reviewed)
- `retrieve`: get relevant source material for answering a question
- `list_projects` / `list_sessions`: rarely needed, only when you need to discover IDs

## Output

All commands output JSON to stdout. Parse the result directly.

## Notes

- Most retrieval context is already injected into your prompt automatically by the harness. Only use `retrieve` if you need additional context beyond what's provided.
- `search_memory` is useful when the student references something from a past session.
