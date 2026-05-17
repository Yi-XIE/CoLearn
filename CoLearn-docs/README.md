# CoLearn Docs

This folder keeps the documents for the current CoLearn mainline.

## What to read

- `02-Architecture`: current runtime, state, and writeback facts
- `03-Learning-Knowledge/LightRAG-background-knowledge-state-machine.md`: knowledge base strategy and state-machine integration
- `04-Claude-Handoffs`: handoff notes for collaborators
- `05-Nanobot-v0.2`: runtime adoption status and remaining cleanup

## Current Mainline

- `webui + runtime_v2 + slim config` is the default path.
- `LearningState` is part of the turn writeback chain.
- `LightRAG` and `memory` are the default learning tools.

## Maintenance Rules

- Keep documents aligned with the current mainline.
- Do not rewrite finished plans as finished facts.
- Keep UTF-8 clean and avoid damaged text or placeholders in formal docs.
