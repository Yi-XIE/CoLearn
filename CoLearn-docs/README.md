# CoLearn Docs

This folder keeps the documents for the current CoLearn mainline.

## What to read

- `02-Architecture`: current runtime, state, and writeback facts
- `02-Architecture/CoLearn-LightRAG-学习状态机瘦身评估.md`: single source of truth for the current Learning Mode slimming plan, including LightRAG, PlanStage, LearningBoard, and web search
- `03-Learning-Knowledge/LightRAG-background-knowledge-state-machine.md`: compatibility stub that points back to the main architecture doc
- `04-Claude-Handoffs`: handoff notes for collaborators
- `05-Nanobot-v0.2`: runtime adoption status and remaining cleanup

## Current Mainline

- `webui + runtime_v2 + slim config` is the default path.
- `LearningState` is part of the turn writeback chain.
- `memory` is the default learning tool, and `LightRAG` is enabled on demand.

## Maintenance Rules

- Keep documents aligned with the current mainline.
- Do not rewrite finished plans as finished facts.
- Keep UTF-8 clean and avoid damaged text or placeholders in formal docs.
