# CoLearn Vendor Snapshot: nanobot core

This directory contains a pruned vendor snapshot derived from [HKUDS/nanobot](https://github.com/HKUDS/nanobot).

Purpose:

- keep a small, inspectable agent runtime inside CoLearn
- preserve the reusable nanobot core pieces we want to study and adapt
- avoid bringing chat channels, gateway, WebUI, and other broad product surfaces into CoLearn

Kept on purpose:

- `nanobot/agent/*`
- `nanobot/session/*`
- `nanobot/bus/*`
- `nanobot/providers/*`
- `nanobot/config/*`
- `nanobot/utils/*`
- `nanobot/templates/*`
- `nanobot/skills/*`

Trimmed or intentionally not wired as the main path:

- no `api/`
- no `cli/`
- no `channels/`
- no `webui/`
- no `bridge/`
- no upstream `tests/`
- command surface reduced to minimal local control commands
- default tool registration reduced to a small core set

How to read this snapshot:

- treat it as a reference runtime, not as CoLearn's final product architecture
- CoLearn learning states should stay in `deeptutor/learning/state_machine.py`
- this vendor snapshot is mainly for the lower-level agent turn loop, memory, session, and prompt/context assembly

Next intended integration points:

- `deeptutor/services/session/*`
- `deeptutor/memory/*`
- `deeptutor/integrations/lightrag_client.py`
- `deeptutor/learning/*`

Upstream license:

- see `LICENSE.nanobot`
