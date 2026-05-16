# Pruning Notes

This snapshot was reduced for CoLearn on branch `codex/nanobot-core`.

What was removed at the repository boundary:

- `api`
- `cli`
- `channels`
- `webui`
- `bridge`
- upstream `tests`

What was reduced inside the kept runtime:

- `python -m nanobot` entrypoint disabled for this snapshot
- built-in commands reduced to:
  - `/stop`
  - `/status`
  - `/new`
  - `/history`
  - `/dream`
  - `/help`
- default tools reduced to:
  - `read_file`
  - `write_file`
  - `edit_file`
  - `list_dir`
  - `message`

What still exists but is not the preferred CoLearn path:

- `cron`
- `heartbeat`
- `pairing`
- provider variants not yet selected by CoLearn
- memory Dream logic in original nanobot form

Why those modules were not fully deleted:

- some config and runtime types still reference them
- keeping them avoids breaking imports while we study and adapt the core loop

CoLearn-specific guidance:

- do not reuse nanobot product semantics directly
- keep CoLearn learning lifecycle in `deeptutor/learning/state_machine.py`
- treat this snapshot as a runtime substrate for turn execution, not as the product shell
