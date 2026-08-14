"""Shared output types for VOD AI MediaKit tools."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class VodArtifactPersistenceIssue(BaseModel):
    """Safe explanation for a provider success that was not persisted."""

    code: Literal[
        "untrusted_output_host",
        "output_too_large",
        "invalid_output_mime",
        "source_expired",
        "download_failed",
        "storage_failed",
    ] = Field(description="Stable persistence failure category.")
    message: str = Field(description="Credential- and URL-safe persistence failure message.")
    retryable: bool = Field(description="Whether persistence may succeed if attempted again later.")
    artifact_limit_bytes: int = Field(
        description="Maximum video size accepted by the durable artifact policy, in bytes."
    )
