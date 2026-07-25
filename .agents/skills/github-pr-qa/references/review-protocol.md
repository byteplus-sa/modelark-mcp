# Pull Request QA Review Protocol

Use this protocol for the independent read-only QA pass. Complete the review artifact before any public review action.

## 1. Capture the Live Snapshot

Collect the PR URL, number, title, body, author, draft state, base and head branches, exact base and head SHAs, changed files, diff, commit list, checks, mergeability, review decision, and unresolved feedback when available.

Treat PR reads as costly: fetch metadata and diff together when supported. Refresh drift-prone state when the head changes or the initial result is incomplete.

Assess whether the PR description matches the code, validation, risk, rollout, migration, screenshots, diagrams, and linked documentation. Treat documentation gaps as blocking only when they create a real implementation, review, release, or safety risk.

## 2. Establish the Exact-Head View

- Verify the local checkout or isolated worktree matches the recorded head SHA.
- Preserve dirty or unrelated work; never switch, reset, clean, or overwrite a user's checkout.
- For fork PRs, resolve the head repository explicitly.
- If no exact-head local view is available, review the live diff and accessible repository context, then state the limitation.
- Reconfirm the head SHA before finalizing. Refresh affected analysis or mark the report stale if it changed.

## 3. Review in Repository Context

Read applicable repository instructions and inspect materially changed files with their callers, tests, fixtures, schemas, migrations, configuration, generated artifacts, documentation, and surrounding control/data flow.

Prioritize:

1. Correctness, edge cases, and regressions.
2. Security, privacy, authorization, secrets, and trust boundaries.
3. Data integrity, concurrency, transactions, idempotency, and migrations.
4. Public APIs, schemas, protocols, and compatibility.
5. Error handling, retries, cleanup, and partial failures.
6. Performance and resource usage when impact is concrete.
7. Deployment, configuration, observability, and recovery.
8. Missing or misleading test coverage and PR evidence.
9. Maintainability issues with a specific defect risk.

Do not report style-only preferences, pre-existing problems not exposed by the PR, speculative risks without a plausible trigger, or duplicates of active unresolved feedback.

## 4. Validate Read-Only

- Discover commands from repository instructions, manifests, task runners, and CI.
- Run the narrowest relevant checks first and expand according to risk.
- Do not modify source, install dependencies, commit, push, or mutate external state.
- Separate local command results from live GitHub check status.
- Explain whether failures come from the PR, base branch, or environment.

## 5. Write One Report per Round

Use the user or repository path when supplied; otherwise write `pr-reviews/<PR_ID>-<ROUND_NUM>-review.md`. Start at round `1` or infer the next unused round. Never overwrite another round.

Record the PR and exact head SHA, scope/limitations, verdict, PR-description assessment, findings, questions, validation, existing feedback inspected, and residual risks.

For every issue or blocking question, include:

- Severity and concise title
- Repository-relative file and line/symbol evidence
- Trigger or execution path
- Concrete impact
- Suggested fix
- Suggested verification
- **Prompt for AI Agents** with files, exact change, constraints, acceptance criteria, and verification

A no-findings report must still state what was inspected, validation performed, and residual gaps. Never invent a finding.

## 6. Supervisor-Only Approval Gate for Public Feedback

The QA subagent must never post public feedback. Writing the report does not authorize the supervisor to post it. The supervisor must wait for explicit user approval before adding inline comments or submitting a review.

When the supervisor is approved to post:

- Reconfirm the head SHA and map comments to the current diff.
- Avoid duplicate unresolved feedback.
- Put feedback that cannot be anchored accurately in the review summary.
- Include the finding title, description, suggested fix, and **Prompt for AI Agents**.
- Add: "Reviewed with the help of an AI Agent. Please validate recommendations"
- Do not resolve other reviewers' threads or choose approval versus changes-requested status without authorization.

Report exactly what was posted and anything that could not be placed.
