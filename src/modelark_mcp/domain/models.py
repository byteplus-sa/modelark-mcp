"""Shared domain models used across tool input/output contracts.

These types are used in multiple tool output models. Tool-specific input
models live alongside their tool handlers in ``tools/``.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from modelark_mcp.domain.artifacts import ArtifactRef


class Subtitle(BaseModel):
    """Timestamped subtitle data for Seed Audio output."""

    utterances: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Utterance-level subtitle entries with timestamps.",
    )
    words: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Word-level subtitle entries with timestamps.",
    )


class SeedreamItemError(BaseModel):
    """Error for a single failed image in a batch generation."""

    index: int = Field(..., description="0-based index of the failed image.")
    code: str | None = Field(default=None, description="Provider error code.")
    message: str = Field(..., description="Error description.")


class SeedreamUsage(BaseModel):
    """Usage information for a Seedream image generation call."""

    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class SeedanceTaskUsage(BaseModel):
    """Usage/billing information for a completed Seedance task."""

    completion_tokens: int | None = Field(default=None, description="Total tokens consumed.")
    prompt_tokens: int | None = Field(default=None, description="Prompt tokens consumed.")


class SeedanceTaskSummary(BaseModel):
    """Summary of a Seedance task for list results."""

    task_id: str
    model: str
    status: str
    created_at: str
    updated_at: str


class VariationResult(BaseModel):
    """Result of a single variation within a parallel generation."""

    index: int = Field(..., description="0-based variation index.")
    seed: int | None = Field(None, description="Seed used (if applicable).")
    artifact: ArtifactRef | None = Field(None, description="Generated artifact (None if failed).")
    task_id: str | None = Field(None, description="Task ID for async results (Seedance only).")
    error: dict[str, Any] | None = Field(None, description="Error if this variation failed.")
    request_id: str | None = None
    provider_log_id: str | None = None


class VariationSummary(BaseModel):
    """Aggregate result of a parallel generation."""

    total: int = Field(..., description="Total variations requested.")
    succeeded: int = Field(..., description="Variations that produced output.")
    failed: int = Field(..., description="Variations that failed.")
    variations: list[VariationResult] = Field(default_factory=list)
