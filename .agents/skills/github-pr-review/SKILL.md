---
name: github-pr-review
description: Review GitHub pull requests end-to-end and produce a single markdown review report with inline-comment-ready findings, including AI-agent implementation prompts. Use when the user asks for a GitHub PR review, review of a locally checked-out branch with a resolvable GitHub PR, or structured PR feedback.
---

# GitHub PR Review

## Scope

- Perform a full pull request review using live PR metadata/diff and a local repository view that matches the exact PR head.
- Produce structured findings in a single markdown review file per round.
- Prepare inline-comment-ready feedback with suggested fixes and a required **Prompt for AI Agents** section per issue or question.

## Inputs to Collect

- `PR_LINK` (required)
- `PR_ID` (required before writing the report)
- `ROUND_NUM` (required before writing the report)

Derive `PR_ID` from the PR link when possible. If `ROUND_NUM` is not provided, infer the next unused round from existing review files or start at `1`.

## Procedure

1. Read applicable repository instruction files and inspect the current worktree state.
2. Read PR metadata and diff from GitHub in one initial read when the available tooling supports it, and record the exact head SHA. Treat PR reads as costly; fetch the full diff again only when the head changed or the first response was incomplete.
3. Confirm that the local checkout or isolated worktree matches the recorded PR head SHA. Do not assume the PR branch is already checked out, and do not disturb unrelated local changes.
4. Inspect the local repository and run relevant validation commands as needed, such as tests, lint, or type checks, without modifying source files.
5. Perform a full review focusing on correctness, maintainability, repository conventions, and DRY/KISS/SOLID.
6. Write all findings to a single markdown file at:
   - `pr-reviews/{{PR_ID}}-{{ROUND_NUM}}-review.md`
7. If additional rounds are requested, create a new file for each round:
   - `pr-reviews/{{PR_ID}}-{{ROUND_NUM}}-review.md`
8. Before adding inline comments to the PR, ensure the full review has already been written to the markdown file.
9. Do not add inline PR comments yet; wait for explicit user approval of the markdown review file first.
10. For each issue or question, include:
    - Issue or question title
    - Description
    - Suggested fix or requested clarification
    - **Prompt for AI Agents** section in the required format
11. Add this disclosure sentence to each inline PR comment:
    - "Reviewed with the help of an AI Agent. Please validate recommendations"
12. Immediately before finalizing the report, perform the smallest available live check of the current PR head SHA. If it changed, refresh the affected analysis and report against the new head or mark the report stale and do not post feedback from it.

## Required Operating Constraints

- Do not modify source code files.
- Do not commit, push, or rewrite git history.
- Do not switch, reset, clean, or overwrite a user's dirty checkout.
- Do not interact with external systems beyond reading the PR and using local repository tooling until the user approves posting review feedback.
- Treat the exact PR head SHA as the reviewed version and record it in the report.
- Treat PR reads as costly: fetch metadata and diff together when the available tooling supports it.

## Review Objectives

1. **Correctness and Bugs**
   - Does the code do what the PR description claims?
   - Are there logic errors, edge cases, missing checks, or regression risks?

2. **Readability and Maintainability**
   - Is the code easy to understand?
   - Are names clear and consistent?
   - Is there unnecessary complexity or duplication?

3. **Repository Conventions**
   - Does the change follow the repository's naming, file structure, error handling, logging, and testing patterns?
   - Are there established helpers that should be reused?
   - Does formatting and linting align with existing configuration?

4. **Best Practices**
   - Avoid duplication and keep logic centralized where appropriate (DRY).
   - Keep changes simple and avoid over-engineering (KISS).
   - Preserve clear separation of concerns and focused interfaces (SOLID where applicable).
   - Watch for unnecessary dependencies, hidden side effects, and premature abstraction.

## Review Template Requirements

For every issue or question, include a **Prompt for AI Agents** section with:

- Files to change using repository-relative paths
- Exact change to make (replace/add/remove)
- Constraints (no new dependencies, keep API stable, preserve behavior as required)
- Acceptance criteria
- Suggested verification (commands/tests)

Write only evidence-backed findings caused or exposed by the PR. A review with no actionable findings is valid; do not invent issues to populate the report.

## Canonical Prompt (Verbatim)

`````md
github pr review

You are an automated Pull Request Review Agent.

## Goal

Review the pull request thoroughly using:

- The live PR metadata and diff at: {{PR_LINK}}
- A local checkout or isolated worktree verified to match the PR's exact head SHA

Then write all comments and findings into a **single markdown file**:
`pr-reviews/{{PR_ID}}-{{ROUND_NUM}}-review.md`

If you conduct additional review rounds, create a new review file for each round:
`pr-reviews/{{PR_ID}}-{{ROUND_NUM}}-review.md`

## Capabilities and Tools

Use the repository and GitHub tools available in the current runtime. You may:

- Read files from the local repository.
- Run repository-provided validation commands.
- Inspect PR metadata, description, comments, changed files, and diff.
- Write the markdown review file.

Do **not**:

- Modify source code files.
- Commit, push, or change git history.
- Disturb unrelated local work.
- Post inline comments before the user approves the markdown review.
- Interact with unrelated external systems.

## Review Objectives

Review:

1. Correctness, bugs, edge cases, and regression risk.
2. Readability, maintainability, naming, complexity, and duplication.
3. Repository conventions for structure, errors, logging, formatting, and tests.
4. DRY, KISS, and SOLID principles where applicable.

Before adding any inline comments to the PR, complete the full review and write every finding into the markdown file.

When the user approves posting feedback, use the available pending-review or inline-comment capability. Each comment must include an issue title, description, suggested fix, and **Prompt for AI Agents** section.

Include this sentence in each inline comment:
"Reviewed with the help of an AI Agent. Please validate recommendations".

**Prompt for AI Agents format:**

- Files to change using repository-relative paths
- Exact change to make
- Constraints
- Acceptance criteria
- Suggested verification

Example:

<example>

**Issue: Missing data validation**

This line sets `data.user` without checking whether `data.authenticated` is true, unlike the previous behavior. This could set an invalid user state.

**Suggested fix:**

```typescript
if (retryResp.ok) {
    const data = await retryResp.json();
    if (data.authenticated && data.user) {
        setUser(data.user);
        return;
    }
}
```

**Prompt for AI Agents:**

- Files: `src/auth/useAuth.ts`
- Change: Guard `setUser(data.user)` behind `data.authenticated && data.user` checks.
- Constraints: No new dependencies. Keep return flow identical.
- Acceptance criteria: `setUser` is only called when authenticated; unauthenticated responses do not mutate user state.
- Verify: Run the repository's relevant tests and confirm the auth flow still works.

</example>

For questions, use the same structure:

<example>

**Question: Removed router navigation on error**

The previous implementation redirected after an error, but the PR removes that behavior. Is the removal intentional, or should the redirect remain?

**Prompt for AI Agents:**

- Files: `src/pages/Login.tsx`
- Change: Restore the redirect or document the intended new error behavior after product intent is confirmed.
- Constraints: Keep UX consistent with product intent; no unrelated refactors.
- Acceptance criteria: Error handling behavior is explicit in code.
- Verify: Exercise the relevant error path or run its tests.

</example>

Treat PR reads as costly. Fetch metadata and diff together in the initial read when supported. Before finalizing, perform a lightweight live head-SHA recheck; fetch the full diff again only if the head changed or required data was unavailable.

Add this sentence to each inline PR comment:
"Reviewed with the help of an AI Agent. Please validate recommendations".
`````

## Example

- User asks: "Review this PR and provide actionable inline feedback using our markdown output format."
- Agent:
  1. Reads PR metadata and diff together.
  2. Verifies and analyzes a local view at the exact PR head.
  3. Runs relevant checks.
  4. Writes `pr-reviews/<PR_ID>-<ROUND_NUM>-review.md`.
  5. Waits for user approval.
  6. Adds approved inline comments derived from the review, with required AI-agent prompts and disclosure.
