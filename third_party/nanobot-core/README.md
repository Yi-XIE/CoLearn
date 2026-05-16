# CoLearn Vendor Snapshot: nanobot core

This directory contains a pruned vendor snapshot derived from [HKUDS/nanobot](https://github.com/HKUDS/nanobot).

Its role inside CoLearn is intentionally narrow:

- keep a small, inspectable agent runtime in-repo
- preserve reusable lower-level turn-loop pieces
- avoid dragging broad upstream product surfaces into CoLearn

## Kept On Purpose

- `nanobot/agent/*`
- `nanobot/session/*`
- `nanobot/bus/*`
- `nanobot/providers/*`
- `nanobot/config/*`
- `nanobot/utils/*`
- `nanobot/templates/*`
- `nanobot/skills/*`

## Trimmed Or Not Wired As Main Path

- no upstream `api/`
- no upstream `cli/`
- no `channels/`
- no `webui/`
- no broad bridge / gateway surfaces
- no upstream `tests/`
- command surface reduced to minimal local control commands
- default tool registration reduced to a small core set

## How To Read This Snapshot

Treat this directory as a reference runtime, not as CoLearn's final product architecture.

The current CoLearn mainline lives in:

- `colearn/api/*`
- `colearn/app/*`
- `colearn/learning/*`
- `colearn/runtime/*`
- `colearn/memory/*`
- `colearn/retrieval/*`

This vendor snapshot is mainly useful for:

- lower-level agent turn loop ideas
- memory and session runtime patterns
- prompt / context assembly references
- provider integration references

## Important Boundary

Do not re-center the product around upstream nanobot structure.

CoLearn now has its own mainline architecture and its own docs under:

- `CoLearn-docs/02-Architecture`

Use this vendor snapshot as a source of implementation material, not as the product truth.

## Upstream License

See `LICENSE.nanobot`.
