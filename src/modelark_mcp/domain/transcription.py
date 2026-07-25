"""Provider-agnostic transcription result models.

These types are used in STT tool output and are independent of the underlying
ASR provider (LAS ASR). Timestamps are in milliseconds (integer), matching the
LAS ASR response contract.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class TranscriptionWord(BaseModel):
    """A single word with timing and confidence."""

    text: str = ""
    confidence: float | None = Field(default=None, description="Recognition confidence (0.0-1.0).")
    start_time_ms: int | None = Field(default=None, description="Start time in milliseconds.")
    end_time_ms: int | None = Field(default=None, description="End time in milliseconds.")


class TranscriptionUtterance(BaseModel):
    """An utterance segment with timing, words, and speaker metadata."""

    text: str = ""
    start_time_ms: int | None = Field(default=None, description="Start time in milliseconds.")
    end_time_ms: int | None = Field(default=None, description="End time in milliseconds.")
    words: list[TranscriptionWord] = Field(default_factory=list)
    speaker_id: str | None = Field(
        default=None, description="Speaker label if diarization is enabled."
    )
    channel_id: str | None = Field(
        default=None, description="Audio channel identifier if channel split is enabled."
    )


class TranscriptionResult(BaseModel):
    """Full transcription result returned by speech_to_text_get_result."""

    text: str
    utterances: list[TranscriptionUtterance] = Field(default_factory=list)
    duration_ms: int | None = Field(
        default=None, description="Total audio duration in milliseconds."
    )


class AsrTaskStatus(StrEnum):
    """Lifecycle states for an ASR transcription task."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    COMPLETED = "completed"
    FAILED = "failed"
