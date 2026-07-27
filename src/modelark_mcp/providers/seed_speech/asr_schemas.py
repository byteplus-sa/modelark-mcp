"""Seed Speech ASR provider schemas (STT).

Provider DTOs for the WS config payload and the server response. All models
allow extra fields so forward-compatible server additions do not break parsing.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class AsrAudioConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    format: str
    rate: int = 16000
    bits: int = 16
    channel: int = 1
    language: str = "en-US"


class AsrRequestConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    model_name: str = "bigmodel"
    enable_punc: bool | None = None
    enable_itn: bool | None = None
    result_type: str = "full"
    show_utterances: bool | None = None


class AsrFullClientRequest(BaseModel):
    """The config JSON sent as the full client request."""

    user: dict[str, str] = Field(default_factory=lambda: {"uid": "modelark-mcp"})
    audio: AsrAudioConfig
    request: AsrRequestConfig
    workflow: str = "audio_in,resample,partition,vad,fe,decode,itn,nlu_ddc,nlu_punctuate"


class AsrWord(BaseModel):
    model_config = ConfigDict(extra="allow")
    text: str = ""
    start_time: int | None = None
    end_time: int | None = None
    confidence: float | None = None


class AsrUtterance(BaseModel):
    model_config = ConfigDict(extra="allow")
    text: str = ""
    start_time: int | None = None
    end_time: int | None = None
    definite: bool | None = None
    words: list[AsrWord] = Field(default_factory=list)


class AsrResult(BaseModel):
    model_config = ConfigDict(extra="allow")
    text: str = ""
    utterances: list[AsrUtterance] = Field(default_factory=list)


class AsrServerResponse(BaseModel):
    """Parsed full server response."""

    code: int = 1000
    message: str = ""
    result: AsrResult | None = None
