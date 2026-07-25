---
name: subagent-workflows
description: Orchestrate Codex subagent workflows for complex repository or workspace tasks. Use when Codex should consider breaking down a task and delegating independent work to subagents, including codebase exploration, multi-area implementation, parallel review, debugging, custom agents, or batch fan-out.
---

# Subagent Workflows

Use this skill to coordinate Codex subagents while keeping the supervisor agent responsible for scope, integration, validation, and final reporting.

## Delegation Decision

- Codex may decide to use subagents without a separate user request when the task is complex, parallelizable, and benefits from independent context.
- Prefer subagents for independent codebase exploration, multi-surface reviews, disjoint implementation slices, UI reproduction plus code tracing, or many similar row/item checks.
- Keep work local when the task is small, sequential, tightly coupled, urgent on the critical path, or likely to cost more to coordinate than to complete directly.
- Do not spawn multiple agents for the same question or create parallel work that will overwrite the same files.
- If you choose not to spawn subagents for a substantial task, note the reason briefly in your working summary or final response.

## Supervisor Workflow

1. Ground the task before delegation:
   - Read applicable repository instruction files, including `AGENTS.md` and relevant nested instructions when present, plus current version-control status and task-specific docs/specs/plans.
   - Identify the concrete output the user expects: code change, review report, plan, issue, diagnosis, or batch result.
   - Decide the immediate critical-path task the supervisor should do locally.

2. Split only independent work:
   - Delegate bounded sidecar tasks that can run in parallel without blocking the supervisor's next local step.
   - Avoid duplicate prompts across agents.
   - Keep each agent's scope narrow enough that its output can be reviewed quickly.
   - For implementation workers, assign disjoint file or module ownership.

3. Choose agent roles:
   - Use `explorer` for read-only codebase mapping, API tracing, risk discovery, or evidence gathering.
   - Use `worker` for targeted implementation or test fixes with a clear write scope.
   - Use `default` for mixed analysis when no narrower role fits.
   - Use custom agents only when the active Codex runtime exposes them and the role is reusable enough to justify the extra configuration.

4. Write delegation prompts precisely:
   - Include the resolved repository or workspace path, branch/context when relevant, relevant files, task boundaries, expected output, and validation expectations.
   - Tell source-editing workers they are not alone in the codebase, must not revert others' work, and must list changed files.
   - Tell read-only agents not to edit files, commit, push, resolve GitHub threads, or mutate external systems.
   - Ask for concise final reports that include evidence, commands run, changed paths, blockers, and residual risk.

5. Keep the supervisor productive:
   - After spawning, continue non-overlapping local work instead of waiting by default.
   - Wait only when the next supervisor step needs the subagent result.
   - Do not redo delegated work locally while the agent is running.
   - Close completed agents once their output has been reviewed and no follow-up is needed.
   - Use the active runtime's exposed controls for spawning, steering or messaging, waiting, interrupting, and closing agents. Check the available tool names instead of assuming a particular client version.

6. Integrate results:
   - Read every subagent result critically against current code or artifacts and applicable repository rules.
   - Apply or merge only valid changes; reject stale, duplicated, unsafe, or out-of-scope suggestions.
   - Run the strongest practical validation for the integrated result.
   - Finalize with what was delegated, what came back, what changed, validation, and remaining risks.

## Sandbox And Approvals

- Assume subagents inherit the supervisor's current sandbox and approval policy.
- Do not ask a subagent to bypass approvals, write outside its allowed scope, or mutate external systems beyond the user's request.
- If a subagent hits an approval or sandbox blocker, surface the specific blocker to the supervisor and decide whether the supervisor should request approval, narrow the task, or continue locally.
- Prefer read-only sandboxing for custom explorers, reviewers, docs researchers, and QA agents.

## Common Patterns

Use `references/prompt-templates.md` from this skill's directory for ready-to-adapt prompts for explorers, workers, reviewers, and browser/debugging agents.

Use `references/custom-agents.md` from this skill's directory when a recurring role would benefit from a custom subagent TOML file or tuned model/sandbox defaults.

## Batch Fan-Out

If the active Codex runtime exposes a batch fan-out tool such as `spawn_agents_on_csv` and the task naturally maps to many independent rows, create the required tabular input with one row per independent item. Give workers a strict instruction template and require exactly one structured result per row. Keep batch workers read-only unless each row has an isolated write target.

Do not simulate an unavailable batch-agent tool with ad hoc shell scripts. If batch fan-out is unavailable, say so and fall back to explicit spawned agents or a local loop only when the user accepts that tradeoff.
