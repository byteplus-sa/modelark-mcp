"""Normalized provider error model.

Provider validation, moderation, access, quota, and execution failures are
returned as tool results with ``isError: true``, structured content, and a
concise correction path. This model captures the normalized error shape
that all provider gateways produce.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ProviderName = Literal["modelark", "seed-speech"]


class NormalizedProviderError(BaseModel):
    """Provider error normalized to a stable, cross-product shape."""

    provider: ProviderName = Field(..., description="Which provider produced the error.")
    operation: str = Field(..., description="Logical operation name (e.g. 'create_task').")
    http_status: int | None = Field(
        default=None, description="HTTP status code if the error was HTTP-based."
    )
    code: str | None = Field(
        default=None,
        description="Provider-specific error code, if available.",
    )
    message: str = Field(
        ..., description="Human-readable error description with a correction path."
    )
    request_id: str | None = Field(
        default=None,
        description="Provider request ID for reconciliation (Seed Audio X-Api-Request-Id or ModelArk request ID).",
    )
    retryable: bool = Field(..., description="Whether the operation can be safely retried.")
    ambiguous_completion: bool | None = Field(
        default=None,
        description="True if a mutation timed out after dispatch — the billable operation may have succeeded.",
    )
