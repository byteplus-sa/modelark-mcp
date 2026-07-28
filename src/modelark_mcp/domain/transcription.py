"""Provider-agnostic transcription result models.

These types are used in STT tool output and are independent of the underlying
ASR provider (Seed Speech ASR). Timestamps are in milliseconds (integer).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class TranscriptionWord(BaseModel):
    """A single word with timing and confidence."""

    text: str = Field("", description="Word text.")
    confidence: float | None = Field(default=None, description="Recognition confidence (0.0-1.0).")
    start_time_ms: int | None = Field(default=None, description="Start time in milliseconds.")
    end_time_ms: int | None = Field(default=None, description="End time in milliseconds.")


class TranscriptionUtterance(BaseModel):
    """An utterance segment with timing, words, and speaker metadata."""

    text: str = Field("", description="Utterance text.")
    start_time_ms: int | None = Field(default=None, description="Start time in milliseconds.")
    end_time_ms: int | None = Field(default=None, description="End time in milliseconds.")
    words: list[TranscriptionWord] = Field(
        default_factory=list, description="Word-level detail within this utterance."
    )
    speaker_id: str | None = Field(
        default=None, description="Speaker label if diarization is enabled."
    )
    channel_id: str | None = Field(
        default=None, description="Audio channel identifier if channel split is enabled."
    )


class TranscriptionResult(BaseModel):
    """Full transcription result returned by the speech_to_text tool."""

    text: str = Field(..., description="Full transcript text.")
    utterances: list[TranscriptionUtterance] = Field(
        default_factory=list, description="Utterance-level segments with timestamps."
    )
    duration_ms: int | None = Field(
        default=None, description="Total audio duration in milliseconds."
    )
