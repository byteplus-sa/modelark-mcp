"""Integration tests for the ``speech_to_text_get_result`` tool handler.

Exercises the full path: ownership check → provider poll (mocked) →
provider→domain mapping → structured output.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastmcp.tools import ToolResult

from modelark_mcp.domain.errors import NormalizedProviderError, ProviderError
from modelark_mcp.domain.transcription import AsrTaskStatus
from modelark_mcp.providers.las.asr import LasAsrService
from modelark_mcp.providers.las.schemas import (
    LasAsrAudioInfo,
    LasAsrPollData,
    LasAsrPollResponse,
    LasAsrResult,
    LasAsrSubmitResponse,
    LasAsrUtterance,
    LasAsrWord,
    LasTaskMetadata,
)
from modelark_mcp.tools.speech_to_text_create_task import (
    SpeechToTextCreateTaskInput,
    speech_to_text_create_task,
)
from modelark_mcp.tools.speech_to_text_get_result import (
    SpeechToTextGetResultInput,
    SpeechToTextGetResultOutput,
    speech_to_text_get_result,
)
from tests.fixtures.fake_context import FakeContext


def _mock_poll_response(
    *,
    task_id: str = "task-test-123",
    task_status: str = "COMPLETED",
    business_code: str = "0",
    error_msg: str = "",
    request_id: str = "req-test-123",
    result: LasAsrResult | None = None,
    audio_info: LasAsrAudioInfo | None = None,
) -> LasAsrPollResponse:
    data = None
    if result is not None or audio_info is not None:
        data = LasAsrPollData(result=result, audio_info=audio_info)
    return LasAsrPollResponse(
        metadata=LasTaskMetadata(
            task_id=task_id,
            task_status=task_status,
            business_code=business_code,
            error_msg=error_msg,
            request_id=request_id,
        ),
        data=data,
    )


def _patch_las_poll(
    monkeypatch: pytest.MonkeyPatch,
    response: LasAsrPollResponse,
) -> None:
    """Patch LasAsrService.poll to return a fixed response."""

    async def mock_poll(
        self: LasAsrService,
        task_id: str,
        operator_id: str = "las_asr_pro",
        operator_version: str = "v1",
    ) -> tuple[LasAsrPollResponse, str | None]:
        return response, response.metadata.request_id

    monkeypatch.setattr(LasAsrService, "poll", mock_poll)


async def _create_owned_task(
    fake_ctx: FakeContext,
    monkeypatch: pytest.MonkeyPatch,
    task_id: str = "task-test-123",
) -> str:
    """Create a task so ownership is recorded, then return its ID."""

    async def mock_submit(
        self: LasAsrService,
        request: Any,
    ) -> tuple[LasAsrSubmitResponse, str | None]:
        response = LasAsrSubmitResponse(
            metadata=LasTaskMetadata(
                task_id=task_id,
                task_status="PENDING",
                business_code="0",
                error_msg="",
                request_id="req-submit",
            )
        )
        return response, "req-submit"

    monkeypatch.setattr(LasAsrService, "submit", mock_submit)
    result = await speech_to_text_create_task(
        SpeechToTextCreateTaskInput(
            audio={
                "audio_url": "https://example.com/audio.wav",
                "audio_format": "wav",
            }
        ),
        fake_ctx,
    )
    assert isinstance(result, type(None)) or result.task_id == task_id  # type: ignore
    return task_id


class TestSpeechToTextGetResult:
    """Full-path integration tests for speech_to_text_get_result."""

    async def test_pending_result(
        self,
        test_env: None,
        fake_ctx: FakeContext,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        task_id = await _create_owned_task(fake_ctx, monkeypatch)

        _patch_las_poll(
            monkeypatch,
            _mock_poll_response(
                task_id=task_id,
                task_status="PENDING",
                request_id="req-poll",
            ),
        )

        result = await speech_to_text_get_result(
            SpeechToTextGetResultInput(task_id=task_id),
            fake_ctx,
        )

        assert isinstance(result, SpeechToTextGetResultOutput)
        assert result.status == AsrTaskStatus.PENDING
        assert result.result is None
        assert result.error is None
        assert result.request_id == "req-poll"

    async def test_completed_result_with_utterances(
        self,
        test_env: None,
        fake_ctx: FakeContext,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        task_id = await _create_owned_task(fake_ctx, monkeypatch)

        result_obj = LasAsrResult(
            text="Hello world.",
            utterances=[
                LasAsrUtterance(
                    text="Hello world.",
                    start_time=0,
                    end_time=2000,
                    words=[
                        LasAsrWord(text="Hello", confidence=0.98, start_time=0, end_time=1000),
                        LasAsrWord(text="world.", confidence=0.95, start_time=1000, end_time=2000),
                    ],
                    additions={"speaker_id": "spk_0", "channel_id": "1"},
                )
            ],
        )
        _patch_las_poll(
            monkeypatch,
            _mock_poll_response(
                task_id=task_id,
                task_status="COMPLETED",
                result=result_obj,
                audio_info=LasAsrAudioInfo(duration=3575),
            ),
        )

        result = await speech_to_text_get_result(
            SpeechToTextGetResultInput(task_id=task_id),
            fake_ctx,
        )

        assert isinstance(result, SpeechToTextGetResultOutput)
        assert result.status == AsrTaskStatus.COMPLETED
        assert result.result is not None
        assert result.result.text == "Hello world."
        assert result.result.duration_ms == 3575
        assert len(result.result.utterances) == 1
        u = result.result.utterances[0]
        assert u.text == "Hello world."
        assert u.start_time_ms == 0
        assert u.end_time_ms == 2000
        assert u.speaker_id == "spk_0"
        assert u.channel_id == "1"
        assert len(u.words) == 2
        assert u.words[0].text == "Hello"
        assert u.words[0].confidence == 0.98

    async def test_completed_result_with_speakers(
        self,
        test_env: None,
        fake_ctx: FakeContext,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        await _create_owned_task(fake_ctx, monkeypatch, task_id="task-speaker-123")

        result_obj = LasAsrResult(
            text="Hello. Goodbye.",
            utterances=[
                LasAsrUtterance(
                    text="Hello.",
                    start_time=0,
                    end_time=1000,
                    additions={"speaker_id": "spk_0"},
                ),
                LasAsrUtterance(
                    text="Goodbye.",
                    start_time=1000,
                    end_time=2000,
                    additions={"speaker_id": "spk_1"},
                ),
            ],
        )
        _patch_las_poll(
            monkeypatch,
            _mock_poll_response(
                task_id="task-speaker-123",
                task_status="COMPLETED",
                result=result_obj,
            ),
        )

        result = await speech_to_text_get_result(
            SpeechToTextGetResultInput(task_id="task-speaker-123"),
            fake_ctx,
        )

        assert isinstance(result, SpeechToTextGetResultOutput)
        assert result.status == AsrTaskStatus.COMPLETED
        assert result.result is not None
        assert len(result.result.utterances) == 2
        assert result.result.utterances[0].speaker_id == "spk_0"
        assert result.result.utterances[1].speaker_id == "spk_1"

    async def test_failed_result(
        self,
        test_env: None,
        fake_ctx: FakeContext,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        await _create_owned_task(fake_ctx, monkeypatch, task_id="task-failed-123")

        _patch_las_poll(
            monkeypatch,
            _mock_poll_response(
                task_id="task-failed-123",
                task_status="FAILED",
                business_code="5001",
                error_msg="Audio processing failed",
            ),
        )

        result = await speech_to_text_get_result(
            SpeechToTextGetResultInput(task_id="task-failed-123"),
            fake_ctx,
        )

        assert isinstance(result, SpeechToTextGetResultOutput)
        assert result.status == AsrTaskStatus.FAILED
        assert result.result is None
        assert "Audio processing failed" in (result.error or "")

    async def test_provider_error_propagates(
        self,
        test_env: None,
        fake_ctx: FakeContext,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        await _create_owned_task(fake_ctx, monkeypatch, task_id="task-err-123")

        async def mock_poll(
            self: LasAsrService,
            task_id: str,
            operator_id: str = "las_asr_pro",
            operator_version: str = "v1",
        ) -> tuple[LasAsrPollResponse, str | None]:
            raise ProviderError(
                NormalizedProviderError(
                    provider="las",
                    operation="poll_asr_task",
                    http_status=404,
                    code="TASK_NOT_FOUND",
                    message="Task not found",
                    retryable=False,
                )
            )

        monkeypatch.setattr(LasAsrService, "poll", mock_poll)

        result = await speech_to_text_get_result(
            SpeechToTextGetResultInput(task_id="task-err-123"),
            fake_ctx,
        )
        assert isinstance(result, ToolResult)
        assert result.is_error
        text = result.content[0].text
        assert "las poll_asr_task failed" in text
        assert "code=TASK_NOT_FOUND" in text
