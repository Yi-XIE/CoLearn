# CoLearn Docs

This folder keeps the documents for the current CoLearn mainline.

## What to read

- `02-Architecture/CoLearn-顶层组装路径.md` — current top-level assembly: entry points, mainline modules
- `02-Architecture/CoLearn-LearningState-协议.md` — the learning state protocol: LearningPhase + TurnMode, BoardFacts / TurnPolicy / LearningEvent, plan & board structures
- `02-Architecture/CoLearn-学习循环实施手册.md` — the single-turn pipeline (stages), what's wired, what's not
- `02-Architecture/CoLearn-后端代码补全计划.md` — backend completion record: API router split, state stores, current boundaries
- `02-Architecture/CoLearn-个人开发维护手册.md` — day-to-day dev commands (server, webui, tests, reset-state)
- `02-Architecture/CoLearn-LightRAG-学习状态机瘦身评估.md` — the slimming plan and its current progress (LightRAG, dual-mode, plan/board, phases)
- `02-Architecture/CoLearn 产品架构图.drawio` + `assets/` — architecture diagram source and exports
- `03-Learning-Knowledge/LightRAG-background-knowledge-state-machine.md` — compatibility stub pointing back to the slimming doc
- `05-Nanobot-v0.2/CoLearn-v0.2-未完成能力总览.md` — nanobot native capability adoption status (5 of 7 integrated)
- `05-Nanobot-v0.2/CoLearn-学习闭环版本设计.md` — the learning-closure product vision (kept as a north star; see header for how it maps to current code)

## Current Mainline

- `webui + runtime_v2 + slim config` is the default path.
- Unified local server: `python -m colearn.server` (single process, auto-spawns LightRAG).
- `LearningState` is part of the turn writeback chain; dual-mode (Chat/Learning) and five Learning Phases are in the main pipeline.
- `memory` and `LightRAG` are the default learning tools; `web_search` is an on-demand fallback.

## Maintenance Rules

- Keep documents aligned with the current mainline.
- Do not rewrite finished plans as finished facts.
- Keep UTF-8 clean and avoid damaged text or placeholders in formal docs.
- When code changes the protocol or pipeline, update the docs in this folder first.
