# CoLearn

CoLearn is Yi's learning companion runtime.

- Keep turns grounded in the current board, continuation prompt, and source profile.
- Prefer explicit, structured updates over implicit assumptions.
- Preserve `continuation_prompt` and recent learning context across long sessions.
- Emit stream events early when they are available, not only at turn end.
- Consolidate long-term memory into stable summaries and profile facts.

