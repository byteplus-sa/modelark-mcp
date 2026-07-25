# Custom Agents Reference

Use this reference when a recurring subagent role would benefit from custom TOML configuration, tuned model defaults, nickname candidates, or a stricter sandbox.

## Placement

- Personal custom agents: `~/.codex/agents/<agent-name>.toml`
- Project-scoped custom agents: `.codex/agents/<agent-name>.toml`
- Match the filename to the `name` field when practical, but Codex identifies the agent by `name`.

Do not add custom agents just because a task is complex. Prefer built-in `explorer`, `worker`, and `default` unless a reusable role would reduce ambiguity or improve safety.

These are Codex configuration locations, not paths tied to a particular repository or user. If the active client uses a configured Codex home or managed configuration, resolve the corresponding personal agents directory from that environment. Verify evolving fields against the current [Codex subagent documentation](https://learn.chatgpt.com/docs/agent-configuration/subagents).

## Required Fields

```toml
name = "agent_name"
description = "Human-facing guidance for when to use this agent."
developer_instructions = """
Core behavior rules for the spawned agent.
"""
```

## Useful Optional Fields

```toml
nickname_candidates = ["Atlas", "Delta", "Echo"]
sandbox_mode = "read-only"
```

Other supported optional fields include `model` and `model_reasoning_effort`. Omit optional fields to inherit from the parent session. Pin a model or reasoning effort only after confirming it is available in the active runtime. Set `sandbox_mode = "read-only"` for reviewers, explorers, and documentation researchers unless the user explicitly wants that custom agent to edit files.

## Read-Only Reviewer Example

```toml
name = "project_reviewer"
description = "Read-only reviewer focused on correctness, security, domain invariants, and missing tests."
sandbox_mode = "read-only"
developer_instructions = """
Review code like an owner.
Prioritize correctness, security and privacy, domain invariants, behavior regressions, architectural boundaries, and missing test coverage.
Lead with concrete findings and file evidence.
Do not edit files, commit, push, resolve review threads, or post public comments.
"""
nickname_candidates = ["Atlas", "Delta", "Echo"]
```

## Focused Worker Example

```toml
name = "project_worker"
description = "Implementation worker for small tasks with explicit file ownership."
developer_instructions = """
Implement only the assigned task and owned files.
Preserve unrelated local changes.
Do not revert work by others.
Follow all applicable repository instruction files.
Return changed files, validation, blockers, and remaining risk.
"""
nickname_candidates = ["Builder", "Fixer", "Tester"]
```

## Project Config

Project-wide agent limits can live in `.codex/config.toml`:

```toml
[agents]
max_concurrent_threads_per_session = 6
```

Leave the concurrency limit unset when the runtime should choose its default. Keep delegation shallow unless the user deliberately wants recursive fan-out; deeper delegation increases cost, latency, and predictability risk.
