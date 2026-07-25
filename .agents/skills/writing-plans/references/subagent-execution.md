# Subagent Execution Reference

Read this reference when a plan includes parallel worker lanes or when the user asks to implement such a plan.

## Supervisor Responsibilities

- Recheck the request, plan, repository instructions, worktree state, and lane assumptions before spawning.
- Keep the immediate critical-path and integration work with the supervisor.
- Spawn only independent lanes with stable inputs and disjoint write scopes.
- Do not delegate the same question to multiple workers unless independent redundancy is an explicit review strategy.
- Keep ownership of contract decisions, conflict resolution, full validation, and final reporting.

## Execution Lifecycle

1. Resolve the repository or workspace path and current branch, head, or task context.
2. Verify that every planned file still exists or is still intended to be new.
3. Confirm each lane's dependencies, write scope, forbidden scope, expected output, and validation.
4. Spawn lanes that can begin immediately. Continue non-overlapping supervisor work rather than waiting by default.
5. Wait only when the next integration step depends on a worker result.
6. Review every returned result against current code, repository rules, and the plan. Reject stale, duplicated, unsafe, or out-of-scope work.
7. Integrate valid changes in dependency order. Do not allow one worker to silently redefine a contract another lane consumes.
8. Run focused checks for each lane, followed by the strongest practical integrated validation.
9. Report delegated lanes, accepted and rejected results, changed files, validation, blockers, and residual risk.

## Worker Prompt Template

```text
You are an implementation worker in a shared repository or workspace.

Task: <bounded implementation outcome>
Repository or workspace: <resolved path>
Branch or task context: <context>
Owned files/modules: <disjoint write scope>
Forbidden scope: <paths or systems the worker must not change>
Depends on: <stable contract, task, or none>
Expected output: <code, tests, docs, or analysis>
Validation: <repository-derived commands and expected signals>

Read every repository instruction file that governs your scope.
You are not alone in the codebase. Preserve unrelated changes, do not revert or overwrite work by others, and do not edit outside your owned scope.
Do not commit, push, deploy, resolve review threads, or mutate external systems unless the user explicitly authorized that action and the supervisor assigned it.

Return:
- Files changed
- What changed and why
- Validation run and results
- Assumptions or contract decisions
- Blockers, skipped work, and remaining risk
```

## Sandbox and Approval Handling

- Assume workers inherit the current runtime's sandbox and approval policy unless the runtime explicitly says otherwise.
- Never ask a worker to bypass an approval, expand permissions, or write outside its assigned scope.
- If a worker is blocked, have it return the exact operation, target, and reason. The supervisor decides whether to request approval, narrow the lane, or continue locally.
- Prefer read-only workers for exploration, review, documentation research, and evidence gathering.

## Conflict Guards

- Sequence lanes that edit the same file, migration chain, schema, public contract, generated artifact, or shared configuration.
- Establish shared contracts before spawning their consumers.
- If a supposedly independent lane discovers a contract change, stop that lane and return the decision to the supervisor before dependent work continues.
