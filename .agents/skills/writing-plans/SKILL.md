---
name: writing-plans
description: Use when creating an implementation plan for a software repository from a user request, product spec, design mockup, technical proposal, bug, or multi-step change before touching code. The workflow requires repository research first, concrete implementation details, conflict-aware parallelization analysis, and an independent plan-review subagent when subagents are permitted.
---

# Writing Plans

Use this skill to create implementation plans that are specific enough for another agent or engineer to execute without rediscovering the system.

**Announce at start:** "I'm using the writing-plans skill to create the implementation plan."

## Core Contract

- Research before planning. Read the user request, applicable repository instruction files, relevant documentation and specs, existing plans, and live code paths before writing the plan.
- For frontend or UI work, read the repository's design guidance, such as `DESIGN.md`, before planning visual, layout, component, or copy changes.
- If library behavior is unclear, use Context7 or the active documentation/search tools before deciding on APIs. Cite external sources in the final explanation when used.
- Save plans to `plans/PLAN_<NAME>.md` unless the user or repository instructions require another path. Use uppercase `PLAN_`, a short descriptive slug, and `.md`.
- Plans must include actual implementation details: code structures, API signatures, schemas, models, service boundaries, file organization, feature flags, validation commands, and documentation updates.
- When evaluating delegation opportunities, defining parallel worker lanes, or implementing a plan with subagents, apply the delegation and parallelization rules in this skill.
- When a plan includes subagent lanes or the user asks to implement one, read `references/subagent-execution.md` from this skill's directory for the complete supervisor, worker-prompt, sandbox, integration, and handoff contract.
- For pre-launch or explicitly forward-only projects, do not add migration bridges, backwards-compatibility shims, or speculative features unless the user asks.
- Do not include commit steps unless the user explicitly asked for commits or repository instructions require them.

## Planning Workflow

1. **Ground the request**
   - Restate the user-visible goal and the exact output expected.
   - Identify the owning deployable or boundary: application, package, service, worker, infrastructure stack, docs/specs, or another isolated area.
   - Check whether the request affects workspace invariants, module independence, auth, data ownership, integrations, deployment, or user-visible UI.

2. **Map the current system**
   - List the concrete files and modules inspected.
   - Trace existing endpoint -> service -> repository flows, component/data flows, jobs, migrations, or infrastructure stacks as relevant.
   - Prefer existing patterns and local helpers over new abstractions.

3. **Design the implementation**
   - Specify new or changed files and each file's responsibility.
   - Define interfaces precisely: functions, classes, props, API routes, language-specific types, database columns, feature flags, environment variables, and error shapes.
   - Include logging, security/privacy constraints, and failure handling where relevant.
   - Include tests and validation that match the risk of the change.

4. **Analyze parallelization**
   - Apply the parallelization rules below before deciding whether implementation can be split across subagents.
   - Before finalizing the plan, check where implementation can be accelerated with subagents.
   - Only propose true parallel workers for independent lanes with disjoint write sets.
   - If a lane has overlapping files or unstable contracts, sequence it explicitly and name the main-agent integration owner instead of calling it parallel.
   - Do not split tightly coupled edits across agents just to create parallelism.
   - If no safe parallelism exists, say so in the plan and explain the conflict risk.

5. **Write the plan**
   - Use checkbox tasks that can be executed and verified.
   - Include at least one Mermaid diagram for meaningful architecture, request flow, state, data, sequencing, or ownership. Skip diagrams only when they would be decorative.
   - Ensure every task can be completed from the plan plus the referenced files.

6. **Review with a subagent**
   - When subagents are permitted by the active runtime and user instructions, spawn a read-only reviewer using this skill's `plan-document-reviewer-prompt.md`.
   - Give the reviewer the plan path, original request/spec paths, and relevant context. Do not leak your intended fixes or ask for confirmation bias.
   - Wait for the reviewer before finalizing. Refine the plan for every valid blocking issue.
   - If the reviewer returns `Needs Revision` and the fixes materially change implementation structure, parallel lanes, validation, or architecture, send the revised plan back for one more read-only review when possible.
   - If subagents are unavailable or not permitted, run the same review locally and explicitly note that no subagent review was performed.

7. **Second-pass review**
   - Reread the final plan against the request, repository rules, inspected code, and reviewer findings.
   - Fix placeholders, missing edge cases, stale docs/spec assumptions, unsafe coupling, unclear ownership, or weak validation before reporting completion.

## Required Plan Shape

````markdown
# [Feature Name] Implementation Plan

**Goal:** [One sentence describing what this builds or changes.]

**Source Context:**
- User request: [short summary or source path]
- Docs/specs read: [`path`], [`path`]
- Code inspected: [`path`], [`path`]

**Architecture Decision:** [2-4 sentences explaining the selected approach and why it fits current repository boundaries.]

**Parallelization Summary:** [Can implementation be split across subagents? If yes, summarize lanes. If no, explain why.]

```mermaid
[diagram that clarifies the implementation]
```

## File Ownership

| Path | Owner | Responsibility | Notes |
| --- | --- | --- | --- |
| `repository/relative/path` | Main agent or Worker A | What changes here | Dependencies/conflicts |

## Implementation Tasks

### Task 1: [Specific Unit]

**Files:** `repository/relative/path`, `repository/relative/test/path`

**Depends on:** None or Task N

**Can run in parallel with:** Task N or "No, shares `path` with Task N"

- [ ] Step 1: [Specific implementation action with concrete details.]
- [ ] Step 2: [Specific test or validation action with exact command.]

## Parallel Subagent Execution Plan

| Lane | Agent Role | Write Scope | Task(s) | Can Start After | Conflict Guard |
| --- | --- | --- | --- | --- | --- |
| Worker A | `worker` | `repository/relative/path/**` | Task 1 | Immediately | Must not edit `other/path` |

**Implementation handoff:** When the user asks to implement this plan and subagents are permitted, the main agent must recheck the current repository state and lane assumptions, spawn only lanes with stable inputs and disjoint write scopes, tell workers to preserve concurrent changes and stay inside their assigned scope, sequence overlapping or contract-changing work, and retain ownership of integration, conflict resolution, full validation, and final reporting.

## Validation

- `command`: expected signal

## Documentation And Follow-Up

- Docs/specs to update:
- Known risks or non-blocking follow-up:
````

## Implementation Detail Standard

A plan step is not actionable unless it names the exact code surface and the intended shape of the change. Include examples where useful, but avoid pretending every line of production code can be known before implementation.

Plan failures:

- `TBD`, `TODO`, `fill in later`, or vague "handle edge cases" text.
- "Write tests" without naming the specific test file, scenario, and assertion intent.
- New API, service, model, flag, environment variable, route, or component names that are never defined.
- Parallel worker lanes that write the same files without an explicit integration owner and ordering.
- Commit, push, PR, or GitHub thread-resolution steps unless the user asked for them.

## Parallelization Rules

- Use this section as the source of truth for delegation decisions, worker prompt structure, supervisor responsibilities, sandbox/approval handling, and integration of subagent results.
- Use subagents for speed only when work can be split by ownership, not by wishful sequencing.
- If the user later asks to implement the plan, re-check the current worktree and then use the safe parallel lanes by default when subagents are permitted. Do not collapse back to sequential implementation unless the lane assumptions are stale or unsafe.
- Good worker lanes: backend schema/service tests vs frontend UI wiring; docs/spec updates vs code implementation; isolated provider adapter vs independent UI copy; infrastructure documentation vs service unit tests.
- Bad worker lanes: two agents editing the same component; one agent changing API contracts while another guesses consumer types; migrations split from models/repositories that must be edited together.
- The main agent owns final integration, conflict resolution, validation, and final reporting.
- Worker prompts must say the worker is not alone in the codebase, must not revert others' changes, must stay inside the assigned write scope, and must list changed files.
- Use `references/subagent-execution.md` for the complete execution lifecycle and ready-to-adapt worker prompt.

## Reviewer Dispatch Template

Use `plan-document-reviewer-prompt.md` from this skill's directory when spawning the plan-reviewer subagent. The reviewer must be read-only and should return `Approved` or `Needs Revision`. Blocking issues determine the status; brief advisory notes are optional and do not change an `Approved` verdict.

## Final Response

Report:

- Plan path.
- Whether a subagent reviewed it.
- Valid reviewer findings that were applied.
- Validation performed on the plan artifact.
- Any remaining risks, follow-up, or missing validation.
