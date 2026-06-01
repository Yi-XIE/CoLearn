---
name: colearn-data
description: Access CoLearn learning state (current session, board, memory, retrieval, concepts)
always: true
---

# CoLearn Data Access

Access CoLearn learning state via CLI commands. Most commands require explicit `--session_id` parameter.

## Quick start

```bash
python -m colearn.cli get_current --session_id <id>        # everything you need: session, board, recent messages
python -m colearn.cli list_signals --session_id <id>       # what the harness observed (understood/blocked concepts)
```

## Command groups

```bash
# Primary
python -m colearn.cli get_current --session_id <id>
python -m colearn.cli list_signals --session_id <id> [--limit 10]
python -m colearn.cli get_board --session_id <id>
python -m colearn.cli get_session_detail --session_id <id> [--messages 5]

# Diagnostics
python -m colearn.cli search_memory --query "关键词" [--session_id <id>] [--limit 5]
python -m colearn.cli retrieve --project_id <id> --query "问题"
python -m colearn.cli list_concepts --project_id <id>

# Dev/debug only
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
- `list_projects` / `list_sessions`: dev/debug inventory commands, useful when you are diagnosing state layout rather than understanding the current learning turn.

## Output

JSON to stdout. Errors include `{"error": "..."}` with a human-readable detail.

## Notes

- Most context is injected into your prompt automatically. Use these tools when you need to verify or fetch extra detail.
- `get_current` is your one-stop check — pass the session_id from the injected context.
