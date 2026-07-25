---
name: github-pr-qa
description: Launch and manage an independent read-only QA subagent for GitHub pull requests. Use when opening, updating, or finalizing a PR and the supervisor should require a separate exact-head QA review before triaging findings, applying valid fixes, refreshing PR evidence, and reporting readiness.
---

# GitHub PR QA

Use this skill when a supervisor is creating, updating, or finalizing a GitHub pull request and an independent QA review is required before the PR is treated as ready.

This skill defines the complete orchestration and review protocol: delegate an independent review, receive the result, triage and fix valid issues, refresh PR evidence, and verify the final PR head.

## Ground Rules

- Use a subagent when the user explicitly asks for an agent/subagent QA review, the current PR-opening request clearly includes that expectation, or the calling workflow requires QA by default.
- The QA subagent is read-only for source code: no source edits, no commits, no pushes, no branch rewrites, and no GitHub thread resolution.
- The QA subagent must follow this skill's bundled `references/review-protocol.md` and stay grounded in applicable repository instructions, live PR metadata/diff, touched code, tests, docs, and specs.
- The supervisor owns all follow-up work: triage findings, decide what is valid, implement fixes, update tests/docs/PR text, refresh PR diagrams, push changes, and verify CI.
- The QA subagent never posts public PR comments. The supervisor may post approved, comment-ready findings only when the user explicitly asks for public comments.
- Preserve unrelated dirty checkout state. If the PR work cannot be isolated safely in the current checkout, use a clean sibling worktree for supervisor-side fixes.

## Supervisor Workflow

1. Prepare the PR context:
   - Confirm the PR URL, PR number, base branch, head branch, head SHA, draft/readiness state, and remote repository.
   - Confirm the latest intended changes are committed and pushed before asking QA to review.
   - Capture validation already run, known limitations, current PR body diagrams, and any areas that need special attention.

2. Spawn the QA subagent:
   - Use a read-only reviewer role such as an explorer-style subagent when available.
   - Pass the exact repository, PR URL/number/head SHA, and verified local checkout or worktree context.
   - Resolve `references/review-protocol.md` from this skill's directory and pass that path to the QA subagent. If the subagent cannot access the path, include the reference contents in its prompt.
   - Tell the QA subagent to read all repository instruction files that govern changed paths, including `AGENTS.md` and nested instructions when present.
   - Ask for actionable findings only, ordered by severity, with file/line evidence and suggested verification.

3. Continue only after QA returns:
   - Read each finding critically against the PR diff and current code.
   - Classify each as `fix`, `already addressed`, `invalid`, `question`, or `defer`.
   - Fix valid actionable issues in the supervisor workspace, not in the subagent workspace.
   - If a finding needs product direction or changes scope materially, stop and ask the user instead of guessing.

4. Update the PR:
   - Commit and push only when the user explicitly authorized publication or an already-authorized calling workflow assigned the PR update. A PR's existence alone is not authorization to mutate its branch.
   - Update the PR body or summary when the fix changes behavior, validation, screenshots, docs, known limitations, sequence flow, or architecture.
   - Keep diagrams, screenshots, checklists, linked documentation, and other PR evidence aligned with the pushed head when they are present or required by repository policy. If a linked issue is the canonical implementation description, update its affected evidence too or report why it could not be changed.
   - Re-run the smallest relevant local validation and then check the live required GitHub check/status evidence for the pushed head, including GitHub Actions when applicable.
   - If the QA pass caused material follow-up changes, consider running one more focused QA pass on the updated head.

## QA Review Protocol

Before spawning the QA reviewer, read `references/review-protocol.md` from this skill's directory. It defines the live PR snapshot, exact-head local view, review objectives, validation, report rounds, mandatory finding structure, agent-ready fix prompts, approval gate, disclosure text, and final head recheck.

The reviewer remains read-only for source and external state. Report only evidence-backed issues caused or exposed by the PR; a clear review with no actionable findings is valid.

## QA Subagent Prompt Template

Use this shape when delegating:

```text
You are the independent QA agent for this pull request.

Review this PR as a read-only exact-head QA pass:
- Repository: <REPOSITORY>
- PR URL: <PR_URL>
- PR number: <PR_NUMBER>
- Base branch: <BASE_BRANCH>
- Head branch: <HEAD_BRANCH>
- Head SHA: <HEAD_SHA>
- Verified local checkout/worktree: <LOCAL_CONTEXT>
- Review protocol: <RESOLVED_REVIEW_PROTOCOL_PATH_OR_INCLUDED_TEXT>
- Supervisor validation already run: <VALIDATION>
- Current PR body evidence status: <DIAGRAM_SCREENSHOT_DOC_STATUS>
- Areas needing extra attention: <FOCUS_AREAS>

Before reviewing, read and follow the supplied review protocol and every repository instruction file that governs changed paths, including AGENTS.md and nested instructions when present. Inspect the live PR metadata/diff and verify the local context matches the supplied head SHA. Ground findings in the repository's domain and data invariants, module or service boundaries, typed contracts, security/privacy rules, frontend and backend conventions, testability, CI expectations, DRY/KISS/SOLID, and requested scope.

Do not edit source files. Do not commit, push, rewrite history, resolve GitHub threads, or post public PR comments.

Return a concise QA report to the supervisor with:
- Verdict: clear, changes requested, or blocked
- Findings ordered by severity, each with file/line evidence, impact, suggested fix, and suggested verification
- Whether the PR body diagrams, screenshots, documentation, and other required evidence match the current head, or why they are not applicable
- Validation commands run and results
- Remaining risk or unanswered questions

For each issue or blocking question, include severity, file/line evidence, trigger, impact, suggested fix, suggested verification, and an implementation prompt with files, exact change, constraints, acceptance criteria, and verification.

Write one markdown review artifact for this round at the user- or repository-specified path, or `pr-reviews/<PR_ID>-<ROUND_NUM>-review.md` by default. Include its path and paste the complete finding summary in your final response so the supervisor can act without relying on subagent workspace files.
```

## QA Focus Areas

Prioritize defects that could ship broken behavior or violate repo standards:

- Incorrect behavior relative to the PR description, specs, or existing code paths.
- Authentication, authorization, tenant or data scoping, ownership, or privacy leaks.
- Coupling one domain or feature to another domain's lifecycle, routes, jobs, persistence, or UI state without an explicit product decision.
- Cross-module or cross-service imports, dependency leakage, or schema ownership violations.
- Missing migrations, unsafe migration assumptions, or environment/docs drift.
- Frontend route, state, accessibility, responsiveness, or design-system regressions.
- Backend API, service, persistence-layer, or worker boundary violations, weak typing, or unsafe logging.
- Missing tests for meaningful behavior changes, especially public routes, auth flows, background jobs, integrations, or shared utilities.
- CI path-filter or validation gaps that could make a green PR misleading.
- Missing or stale PR evidence when the change affects meaningful runtime flow, architecture, data boundaries, deployment behavior, integrations, or user-visible behavior.

Avoid noise:

- Do not report style preferences unless they hide a real maintainability or correctness issue.
- Do not request broad refactors when a narrow fix is enough.
- Do not duplicate findings already acknowledged by the supervisor unless the code still violates them.

## Supervisor Output

When reporting back to the user after a QA pass, include:

- PR reviewed and head SHA.
- QA verdict and valid issues found.
- Fixes made, skipped findings, and rationale for any invalid/deferred findings.
- Files changed by the supervisor.
- PR body evidence updates made or explicitly deemed not applicable.
- Local validation and live CI status.
- Remaining blockers, risks, or follow-up work.
