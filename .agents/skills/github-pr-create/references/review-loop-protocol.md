# Pull Request Create Review-Loop Protocol

Use this protocol for each read-only review round inside the create-and-converge loop. The supervisor starts the review subagent and the CI watch concurrently so CI run time overlaps with review time. Complete the round's review artifact before reporting back to the supervisor.

## 1. CI Watch (Parallel with Review)

The supervisor starts the CI watch concurrently with the code-review subagent so CI run time overlaps with review time instead of serializing them. The code-review subagent reviews immediately; it does not wait for or poll CI.

The supervisor polls required checks:

```
gh pr checks <PR_NUMBER> --json name,state,conclusion,link --required
```

- `CI_POLL_INTERVAL_SECONDS` defaults to `60`. Sleep between polls; do not busy-spin.
- `CI_MAX_WAIT_SECONDS` defaults to `900` (15 minutes). Cap the wait so the loop stays bounded.
- A required check is terminal when `state` is `COMPLETED`; it is green only when `conclusion` is `SUCCESS`. Treat `NEUTRAL`/`SKIPPED` as non-blocking only if the repository treats them as passing.
- Terminal outcomes the supervisor merges with the review verdict:
  - All required checks green → the merged verdict is the review's verdict.
  - Any required check failed (`FAILURE`, `CANCELLED`, `TIMED_OUT`, etc.) → merged `changes requested`; the failing checks are lead findings the supervisor fixes (build/test failures), regardless of the review verdict.
  - Checks still in-progress after `CI_MAX_WAIT_SECONDS` → merged `blocked`; list the pending check names. Even a `clear` review cannot be trusted while CI is unresolved.
- If the review subagent finishes before CI, the supervisor continues polling until CI is terminal or the cap is hit, then merges. If CI finishes first, the supervisor awaits the review, then merges.
- Confirm the head SHA matches the one the supervisor captured for this round before trusting the check results. Checks from a different SHA are not evidence for this round.

`gh pr checks --watch` is an alternative that blocks until checks complete, but it has no cap. Prefer manual polling with `sleep` so the cap is enforced. The code-review subagent does not perform the CI watch; it reviews code immediately and in parallel.

## 2. Capture the Live Snapshot

Collect the PR URL, number, title, body, author, draft state, base and head branches, exact head SHA, changed files, diff, commit list, checks, mergeability, review decision, and unresolved feedback when available. Treat PR reads as costly: fetch metadata and diff together when supported. Refresh drift-prone state when the head changed since the last round or the initial result was incomplete.

Confirm the head SHA matches the one the supervisor supplied for this round. If it changed, refresh the affected analysis or mark the round stale and stop.

## 3. Establish the Exact-Head View

- Verify the local checkout or isolated worktree matches the recorded head SHA.
- Preserve dirty or unrelated work; never switch, reset, clean, or overwrite a user's checkout.
- For fork PRs, resolve the head repository explicitly.
- If no exact-head local view is available, review the live diff and accessible repository context, then state the limitation.
- Reconfirm the head SHA before finalizing.

## 4. Review in Repository Context

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

Do not report style-only preferences, pre-existing problems not exposed by the PR, speculative risks without a plausible trigger, or duplicates of findings the supervisor already resolved in earlier rounds.

## 5. Validate Read-Only

- Discover commands from repository instructions, manifests, task runners, and CI.
- Run the narrowest relevant checks first and expand according to risk.
- Do not modify source, install dependencies, commit, push, or mutate external state.
- Separate local command results from live GitHub check status.
- Explain whether failures come from the PR, base branch, or environment.

## 6. Write One Report per Round

Use the user or repository path when supplied; otherwise write `pr-reviews/<PR_ID>-<ROUND_NUM>-review.md`. Never overwrite another round.

Record the PR and exact head SHA, the round number, scope and limitations, verdict, findings, questions, validation, earlier-round findings inspected, and residual risks. The supervisor records CI status separately and merges it with this report.

### Verdict Semantics

The reviewer's verdict covers code findings only. The supervisor merges it with CI status (green / failed / pending-cap) to form the merged verdict:

- `clear` — no actionable code findings. The supervisor makes the merged verdict `clear` only when CI is also green; the loop then ends.
- `changes requested` — at least one actionable code finding. The supervisor triages, fixes valid items, pushes, and starts the next round. The supervisor may also turn a `clear` review into merged `changes requested` when CI failed.
- `blocked` — a blocker the supervisor cannot resolve without the user. The supervisor also sets merged `blocked` when required CI checks are still pending after `CI_MAX_WAIT_SECONDS`.

A round with only invalid, already-addressed, or deferred code findings is `clear` for code-review purposes; the merged verdict still requires green CI.

### Finding Structure

For every issue or blocking question, include:

- Severity and concise title
- Repository-relative file and line/symbol evidence
- Trigger or execution path
- Concrete impact
- Suggested fix
- Suggested verification
- **Prompt for AI Agents** with files, exact change, constraints, acceptance criteria, and verification

A no-findings round must still state what was inspected, validation performed, and residual gaps. Never invent a finding.

## 7. Read-Only Boundary

The reviewer must never post public feedback, edit source, commit, push, rewrite history, or resolve GitHub threads. The reviewer does not perform the CI watch; it reviews code immediately while the supervisor polls CI in parallel. Writing the report does not authorize the supervisor to post it. Public comments require explicit user approval and a head recheck before posting.
