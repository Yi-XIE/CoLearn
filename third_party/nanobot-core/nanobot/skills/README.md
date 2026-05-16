# nanobot Skills

This directory contains built-in skills carried with the vendored nanobot snapshot.

Inside CoLearn, these files are reference material first. They are not the primary extension surface for the current CoLearn product workflow.

## Skill Format

Each skill is a directory containing a `SKILL.md` file with:

- YAML frontmatter
- a short description
- Markdown instructions for the agent

When a skill references large local documentation or logs, prefer narrowing the search space first instead of loading everything at once.

## Attribution

These skills are adapted from [OpenClaw](https://github.com/openclaw/openclaw)'s skill system.

The skill format and metadata structure follow OpenClaw's conventions to preserve compatibility with the upstream vendor snapshot.

## Available Skills In This Snapshot

| Skill | Description |
|-------|-------------|
| `github` | Interact with GitHub using the `gh` CLI |
| `weather` | Get weather information |
| `summarize` | Summarize URLs, files, and videos |
| `tmux` | Remote-control tmux sessions |
| `clawhub` | Search and install skills from a registry |
| `skill-creator` | Create new skills |

## CoLearn Boundary

These vendor skills are not the main source of truth for CoLearn's current local workflow.

For CoLearn-specific architecture, maintenance, and handoff context, prefer:

- `CoLearn-docs/README.md`
- `CoLearn-docs/02-Architecture/*`
- `CoLearn-docs/04-Claude-Handoffs/*`
