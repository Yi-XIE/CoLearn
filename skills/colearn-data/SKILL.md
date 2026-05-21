---
name: colearn-data
description: Access CoLearn learning state (current session, board, memory, retrieval, concepts)
always: true
---

# CoLearn Data Access

The harness sets `COLEARN_SESSION_ID` for you each turn — most commands work without arguments.

## Quick start

```bash
python -m colearn.cli get_current        # everything you need: session, board, recent messages
python -m colearn.cli list_signals       # what the harness observed (understood/blocked concepts)
```

## All commands

```bash
python -m colearn.cli get_current
python -m colearn.cli list_signals [--session_id <id>] [--limit 10]
python -m colearn.cli get_board [--session_id <id>]
python -m colearn.cli get_session_detail [--session_id <id>] [--messages 5]
python -m colearn.cli search_memory --query "关键词" [--session_id <id>] [--limit 5]
python -m colearn.cli retrieve --project_id <id> --query "问题"
python -m colearn.cli list_concepts --project_id <id>
python -m colearn.cli list_projects
python -m colearn.cli list_sessions [--project_id <id>]
```

## When to use

- **`get_current`**: at the start of complex turns to refresh your understanding of where the student is.
- **`list_signals`**: when you want to know what the harness detected over recent turns (e.g., "did I observe the student understanding X yet?").
- `get_board`: focused board facts query (turn_mode, mastery, blockers, progress).
- `get_session_detail`: review recent conversation + full board.
- `search_memory`: find specific past learning events by keyword.
- `retrieve`: fetch additional knowledge context beyond what's already injected.
- `list_concepts`: see what concepts exist in the knowledge base.

## Output

JSON to stdout. Errors include `{"error": "..."}` with a human-readable detail.

## Notes

- Most context is injected into your prompt automatically. Use these tools when you need to verify or fetch extra detail.
- `get_current` is your one-stop check — prefer it over discovering session_id manually.
