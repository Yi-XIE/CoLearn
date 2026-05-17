# CoLearn runtime_v2

`runtime_v2` is the main runtime wrapper for CoLearn on top of `nanobot v0.2`.

## Responsibilities

1. Read the slim config.
2. Assemble the learning prompt.
3. Register CoLearn tools.
4. Normalize turn results.
5. Produce learning closure and LearningState writeback.

## Current Boundary

- `nanobot` keeps the loop, session, goal, stream, WebUI, and gateway.
- CoLearn owns learning, retrieval, knowledge, and project semantics.
- `runtime_v2` is the only active runtime wrapper.

## Current Status

- Main executor migration is complete.
- Prompt assembly is complete.
- Tool registration is complete.
- Result bridge is complete.
- Learning closure is complete.
- LearningState writeback is complete.
- `memory` and `LightRAG` are enabled by default.
- WebUI now uses the `runtime_v2 + slim config` mainline.

## Entry Points

- `colearn.runtime_v2.profile`
- `colearn.runtime_v2.executor`
- `colearn.runtime_v2.prompting`
- `colearn.runtime_v2.tooling`
- `colearn.runtime_v2.result_bridge`
- `colearn.runtime_v2.learning_closure`
