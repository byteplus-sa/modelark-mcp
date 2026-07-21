"""``seedance_cancel_or_delete_task`` tool — cancel or delete a Seedance task.

The handler first retrieves the task, compares current and expected
status, enforces cancel-only-for-queued and delete-only-for-terminal
states, then calls DELETE. Registered with ``destructiveHint=True`` and
clear tool text describing the record-deletion behavior.

DELETE semantics (per official docs):
- ``queued``: cancel and transition to ``cancelled``
- ``running``: cannot cancel or delete
- ``succeeded``, ``failed``, ``expired``: delete the task record
- ``cancelled``: cannot delete
"""

from __future__ import annotations

from typing import Literal

from fastmcp import Context
from pydantic import BaseModel, Field, model_validator

from modelark_mcp.domain.errors import ProviderError
from modelark_mcp.observability.logger import warning as log_warning
from modelark_mcp.providers.modelark.seedance import SeedanceService

# States where each mode is valid.
_CANCELABLE_STATES: frozenset[str] = frozenset({"queued"})
_DELETABLE_STATES: frozenset[str] = frozenset({"succeeded", "failed", "expired"})


class SeedanceCancelOrDeleteInput(BaseModel):
    """Input model for ``seedance_cancel_or_delete_task``."""

    task_id: str
    mode: Literal["cancel", "delete"]
    expected_status: Literal["queued", "succeeded", "failed", "expired"] = Field(
        ...,
        description=(
            "The caller's expected current status. The handler verifies "
            "this matches the actual status before issuing DELETE, "
            "preventing accidental cancellation or deletion."
        ),
    )
    confirm: Literal[True] = True

    @model_validator(mode="after")
    def validate_mode_status_consistency(self) -> SeedanceCancelOrDeleteInput:
        """Ensure the mode is valid for the expected status."""
        if self.mode == "cancel" and self.expected_status not in _CANCELABLE_STATES:
            raise ValueError(
                f"Cancel mode requires the task to be in 'queued' state, "
                f"but expected_status is '{self.expected_status}'. "
                f"Use mode='delete' for terminal states."
            )
        if self.mode == "delete" and self.expected_status not in _DELETABLE_STATES:
            raise ValueError(
                f"Delete mode requires the task to be in a terminal state "
                f"(succeeded, failed, expired), but expected_status is "
                f"'{self.expected_status}'. Use mode='cancel' for queued tasks."
            )
        return self


class SeedanceCancelOrDeleteOutput(BaseModel):
    """Output model for ``seedance_cancel_or_delete_task``."""

    task_id: str
    mode: Literal["cancel", "delete"]
    previous_status: str
    message: str


async def seedance_cancel_or_delete_task(
    input: SeedanceCancelOrDeleteInput, ctx: Context
) -> SeedanceCancelOrDeleteOutput:
    """Cancel (queued) or delete (terminal) a Seedance video generation task.

    .. warning::

        This is a destructive operation.

        - **cancel**: Stops a queued task. The task transitions to
          ``cancelled`` and cannot be resumed.
        - **delete**: Permanently removes the task record for a completed,
          failed, or expired task. The generated video (if any) is no
          longer retrievable via the task API.

    The handler first fetches the current task state and rejects the
    operation if the actual status does not match ``expected_status``.
    This prevents accidental cancellation of a running task or deletion
    of a task that is still queued.
    """
    await ctx.info(
        f"Seedance {input.mode} task {input.task_id} (expected_status={input.expected_status})"
    )
    await ctx.report_progress(progress=20, total=100)

    service = SeedanceService()

    # 1. Fetch current state.
    try:
        task, _ = await service.get_task(input.task_id)
    except ProviderError as exc:
        await ctx.error(f"Failed to fetch task state: {exc.message}")
        raise
    finally:
        await service.close()

    await ctx.report_progress(progress=40, total=100)

    actual_status = task.status
    if actual_status != input.expected_status:
        raise ValueError(
            f"Task '{input.task_id}' has status '{actual_status}', "
            f"but expected '{input.expected_status}'. "
            f"Refusing to {input.mode} to prevent unintended action. "
            f"Re-fetch the task and update expected_status."
        )

    # 2. Enforce mode/state rules.
    if input.mode == "cancel" and actual_status not in _CANCELABLE_STATES:
        raise ValueError(
            f"Cannot cancel task in '{actual_status}' state. "
            f"Cancel is only allowed for 'queued' tasks."
        )
    if input.mode == "delete" and actual_status not in _DELETABLE_STATES:
        raise ValueError(
            f"Cannot delete task in '{actual_status}' state. "
            f"Delete is only allowed for terminal states "
            f"(succeeded, failed, expired). "
            f"Running tasks cannot be cancelled or deleted; cancelled tasks cannot be deleted."
        )

    await ctx.report_progress(progress=60, total=100)

    # 3. Issue DELETE.
    service = SeedanceService()
    try:
        request_id = await service.delete_task(input.task_id)
    except ProviderError as exc:
        await ctx.error(f"DELETE failed: {exc.message}")
        raise
    finally:
        await service.close()

    await ctx.report_progress(progress=100, total=100)

    message = (
        f"Task '{input.task_id}' has been {'cancelled' if input.mode == 'cancel' else 'deleted'}."
    )
    log_warning(
        "seedance_task_destructive_action",
        task_id=input.task_id,
        mode=input.mode,
        previous_status=actual_status,
        request_id=request_id,
    )

    return SeedanceCancelOrDeleteOutput(
        task_id=input.task_id,
        mode=input.mode,
        previous_status=actual_status,
        message=message,
    )


# Tool annotation constants — camelCase per MCP specification.
TOOL_ANNOTATIONS = {
    "readOnlyHint": False,
    "destructiveHint": True,
    "idempotentHint": False,
    "openWorldHint": True,
}
