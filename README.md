# CoLearn Plugins

CoLearn is a NanoBot-oriented learning plugin demo. This repository packages:

- a standalone `colearn` plugin runtime
- NanoBot host wiring for hooks, commands, thread-side CoLearn UI, and read-only Apps UI
- `.colearn/` session state and wiki-backed learning context
- a vendored NanoBot reference snapshot in `third_party/nanobot-0.2.1/`

## Demo Scope

This branch targets a working demo, not a finished product:

- NanoBot and CoLearn can start together
- `/learn` can create or continue a learning session
- `/colearn` can show the current blackboard snapshot
- LEARNING mode injects CoLearn context into the real model request path
- turn end performs minimal blackboard writeback
- WebUI thread view can show a read-only CoLearn side panel
- WebUI Apps can show a read-only CoLearn entry
- CoLearn exposes read-only host APIs for blackboard, graph, and session state

The primary user path is now the chat thread itself. Apps remains a secondary discovery entry.

CoLearn remains the source of truth for learning data:

- knowledge truth: `.colearn/wiki/`
- learning truth: `.colearn/state/sessions/`

## Install

From the repo root:

```bash
pip install -e .
```

For tests:

```bash
pip install -e ".[dev]"
```

For WebUI development inside the vendored NanoBot snapshot:

```bash
cd third_party/nanobot-0.2.1/webui
npm ci
```

## Required Runtime Config

CoLearn runs on top of NanoBot, so you still need a valid NanoBot config file.

Default path:

```text
~/.nanobot/config.json
```

Minimum things that must be configured:

- a valid `provider`
- a valid `model`
- the matching API key or provider auth

If these are missing, WebUI may still boot, but actual learning turns will not complete.

## Build Wiki Index

If you change content under `knowledge/wiki/`, rebuild the generated index:

```bash
python -m colearn.colearn_wiki.colearn_indexer
```

Generated files land in:

```text
knowledge/generated/
```

## Recommended Start Commands

### WebUI

```bash
python run_colearn.py webui --port 8080
```

This is the main demo entry. It starts NanoBot WebUI with CoLearn auto-mounted.

### HTTP API

```bash
python run_colearn.py serve --port 8765
```

### Single Turn

```bash
python run_colearn.py run --message "I want to learn machine learning" --session user-42
```

### Interactive Session

```bash
python run_colearn.py chat --session user-42
```

## What To Verify

After `python run_colearn.py webui --port 8080`:

1. open NanoBot WebUI
2. open the command palette or type commands directly
3. verify `/learn` and `/colearn` are available
4. run `/learn linear algebra basics`
5. click the `CoLearn` button near the thread composer
6. verify the CoLearn panel opens on the right side in the same thread page
7. confirm the thread area and CoLearn panel are shown side by side
8. open Settings > Apps
9. verify the CoLearn app card is visible

## Host Endpoints

CoLearn adds these read-only APIs through the NanoBot host surface:

- `/api/v1/colearn/blackboard/current`
- `/api/v1/colearn/graph/current`
- `/api/v1/colearn/session/current`
- `/api/settings/colearn-apps`

## Commands

CoLearn currently exposes two host-level commands:

- `/learn <goal>`
- `/colearn`

`/learn` is the formal learning-mode entry.

`/colearn` is read-only and does not switch mode by itself.

## Current Frontend Shape

- the primary CoLearn entry is inside the chat thread
- the thread page can open a right-side CoLearn panel without leaving the conversation
- the thread content and CoLearn panel render side by side at about `6:4`
- `Settings > Apps` remains a secondary discovery and read-only entry

## Current Integration Shape

- CoLearn hooks are installed into NanoBot at runtime
- NanoBot remains the execution host
- CoLearn-specific host coupling is kept in `colearn_*` adapters and minimal host glue
- the vendored NanoBot snapshot includes only the minimal demo host wiring needed for Apps and command exposure

## Test Commands

Repo tests:

```bash
pytest -q
```

Focused plugin and host tests:

```bash
pytest -q tests/test_plugin_smoke.py tests/test_colearn_api.py tests/test_state_store.py tests/test_runtime_integration.py tests/test_plugin_host_smoke.py tests/test_colearn_command.py
```

Vendored NanoBot integration tests:

```bash
set PYTHONPATH=D:\CoLearn-plugins;D:\CoLearn-plugins\third_party\nanobot-0.2.1
python -m pytest -q third_party/nanobot-0.2.1/tests/agent/test_runner_hooks.py third_party/nanobot-0.2.1/tests/command/test_model_command.py third_party/nanobot-0.2.1/tests/channels/test_websocket_channel.py third_party/nanobot-0.2.1/tests/channels/test_websocket_http_routes.py
```

WebUI tests:

```bash
cd third_party/nanobot-0.2.1/webui
npm test -- --run src/tests/api.test.ts src/tests/settings-view.test.tsx
npm run build
```
