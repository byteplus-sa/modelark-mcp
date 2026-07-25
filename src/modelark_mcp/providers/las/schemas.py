"""LAS ASR provider schemas (speech-to-text).

Provider DTOs for the BytePlus LAS ASR API — ``POST /api/v1/submit`` and
``POST /api/v1/poll``.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LasAudioInput(BaseModel):
    """Audio input for LAS ASR submit."""

    url: str
    format: str


class LasAsrRequestConfig(BaseModel):
    """Request configuration toggles for LAS ASR."""

    model_config = ConfigDict(extra="allow")

    model_name: str = "bigmodel"
    enable_punc: bool | None = None
    enable_itn: bool | None = None
    enable_ddc: bool | None = None
    enable_speaker_info: bool | None = None
    enable_channel_split: bool | None = None
    enable_lid: bool | None = None
    show_utterances: bool | None = None
    show_words: bool | None = None
    show_speech_rate: bool | None = None
    show_volume: bool | None = None


class LasAsrSubmitData(BaseModel):
    """The ``data`` object in the submit request."""

    audio: LasAudioInput
    request: LasAsrRequestConfig
    resource: str | None = None


class LasAsrSubmitRequest(BaseModel):
    """Full submit request body."""

    operator_id: str = "las_asr_pro"
    operator_version: str = "v1"
    data: LasAsrSubmitData


class LasTaskMetadata(BaseModel):
    """Metadata returned by submit and poll."""

    model_config = ConfigDict(extra="allow")

    task_id: str
    task_status: str
    business_code: str = "0"
    error_msg: str = ""
    request_id: str | None = None


class LasAsrSubmitResponse(BaseModel):
    """Response from ``POST /api/v1/submit``."""

    metadata: LasTaskMetadata


class LasAsrWord(BaseModel):
    """A single word with timing and confidence."""

    model_config = ConfigDict(extra="allow")

    text: str = ""
    confidence: float | None = None
    start_time: int | None = None
    end_time: int | None = None


class LasAsrUtterance(BaseModel):
    """An utterance segment with timing, words, and speaker metadata."""

    model_config = ConfigDict(extra="allow")

    text: str = ""
    start_time: int | None = None
    end_time: int | None = None
    words: list[LasAsrWord] = Field(default_factory=list)
    additions: dict[str, Any] | None = None


class LasAsrResult(BaseModel):
    """The ``data.result`` object in the poll response."""

    model_config = ConfigDict(extra="allow")

    text: str = ""
    utterances: list[LasAsrUtterance] = Field(default_factory=list)
    additions: dict[str, Any] | None = None


class LasAsrAudioInfo(BaseModel):
    """Audio metadata in poll response."""

    model_config = ConfigDict(extra="allow")

    duration: int | None = None


class LasAsrPollData(BaseModel):
    """The ``data`` object in the poll response."""

    model_config = ConfigDict(extra="allow")

    audio_info: LasAsrAudioInfo | None = None
    result: LasAsrResult | None = None


class LasAsrPollResponse(BaseModel):
    """Full poll response."""

    metadata: LasTaskMetadata
    data: LasAsrPollData | None = None
