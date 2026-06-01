# CoLearn Plugins

This repository contains the standalone CoLearn plugin runtime and the NanoBot host adapter.

## Scope

- CoLearn plugin core
- NanoBot adapter
- Blackboard and session state integration
- Wiki-backed learning flow
- Slash command and UI extension contracts
- NanoBot reference snapshot under `third_party/nanobot-0.2.1/`

## Naming

- Brand Name: `CoLearn`
- Package Name: `colearn`
- Plugin Name: `colearn`
- File/Dir Prefix: `colearn_*`
- State Dir: `.colearn/`

## Current Status

This repository is being extracted from the main CoLearn product line so the plugin can evolve as an independent deliverable while still targeting NanoBot as the first and only host.

## Third-party Reference

`third_party/nanobot-0.2.1/` is a checked-in host reference snapshot for interface lookup and integration validation.

- Treat it as read-only reference code.
- Keep CoLearn plugin implementation under `colearn/`.
