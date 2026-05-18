# CoLearn Docs

This folder keeps the documents for the current CoLearn mainline.

## What to read

- `02-Architecture/CoLearn-顶层组装路径-已完成.md`: current runtime entrypoints and main assembly path
- `02-Architecture/CoLearn-LearningState-协议.md`: current learning state, turn policy, and writeback protocol
- `03-Learning-Knowledge/LightRAG-background-knowledge-state-machine.md`: knowledge base strategy and state-machine integration
- `05-Nanobot-v0.2`: nanobot v0.2 adoption status and remaining engineering boundaries

## Current Mainline

- `webui + runtime_v2 + slim config` is the default path.
- `LearningState` is part of the turn writeback chain.
- `LightRAG` and `memory` are the default learning tools.
- `colearn.paths` owns repo, state, and nanobot workspace path resolution.
- Nanobot runtime streaming, model presets, Dream memory consolidation, session compact, MCP, and lightweight `parallel_support` are connected.

## Maintenance Rules

- Keep documents aligned with the current mainline.
- Remove finished handoff or implementation-plan notes once their useful facts have moved into the current architecture docs.
- Keep UTF-8 clean and avoid damaged text or placeholders in formal docs.
