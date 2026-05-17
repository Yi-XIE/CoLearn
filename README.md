# CoLearn

CoLearn is a learning workspace built around `webui + runtime_v2 + slim config`.

## Current Mainline

- Project and session management
- Knowledge Garden
- Memory
- Skills
- Settings
- `LearningState` writeback loop
- `LightRAG` and memory tools

The mainline is now `webui + runtime_v2 + slim config`.

## Key Entry Points

- Backend API: `colearn.api.app:app`
- Runtime layer: `colearn.runtime_v2`
- Default config: `.colearn/nanobot-v0.2-slim.config.json`
- Recommended gateway: `scripts/start-colearn-v2-gateway.ps1`

## Notes

- The product UI is backed by real CoLearn data.
- `LearningState` is no longer prompt-only; it now participates in turn writeback.
- Old docs are frozen as history; new work follows the mainline above.
