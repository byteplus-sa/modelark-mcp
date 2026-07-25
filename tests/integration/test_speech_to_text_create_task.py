"""Integration tests for the ``speech_to_text_create_task`` tool handler.

Exercises the full path: input validation → audio URL resolution → provider
call (mocked) → task ownership → structured output.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastmcp.tools import ToolResult

from modelark_mcp.domain.errors import NormalizedProviderError, ProviderError
from modelark_mcp.providers.las.asr import LasAsrService
from modelark_mcp.providers.las.schemas import LasAsrSubmitResponse, LasTaskMetadata
from modelark_mcp.tools.speech_to_text_create_task import (
    SpeechToTextCreateTaskInput,
    SpeechToTextCreateTaskOutput,
    speech_to_text_create_task,
)
from tests.fixtures.fake_context import FakeContext


def _patch_las_service(
    monkeypatch: pytest.MonkeyPatch,
    *,
    task_id: str = "task-test-123",
    task_status: str = "PENDING",
    request_id: str = "req-test-123",
) -> None:
    """Patch LasAsrService.submit to return a fixed response."""

    async def mock_submit(
        self: LasAsrService,
        request: Any,
    ) -> tuple[LasAsrSubmitResponse, str | None]:
        response = LasAsrSubmitResponse(
            metadata=LasTaskMetadata(
                task_id=task_id,
                task_status=task_status,
                business_code="0",
                error_msg="",
                request_id=request_id,
            )
        )
        return response, request_id

    monkeypatch.setattr(LasAsrService, "submit", mock_submit)


class TestSpeechToTextCreateTask:
    """Full-path integration tests for speech_to_text_create_task."""

    async def test_url_input_submit(
        self,
        test_env: None,
        fake_ctx: FakeContext,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _patch_las_service(monkeypatch)

        result = await speech_to_text_create_task(
            SpeechToTextCreateTaskInput(
                audio={
                    "audio_url": "https://example.com/audio.wav",
                    "audio_format": "wav",
                }
            ),
            fake_ctx,
        )

        assert isinstance(result, SpeechToTextCreateTaskOutput)
        assert result.task_id == "task-test-123"
        assert result.status == "queued"
        assert result.recommended_poll_after_ms == 3000

    async def test_progress_reporting(
        self,
        test_env: None,
        fake_ctx: FakeContext,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _patch_las_service(monkeypatch)

        await speech_to_text_create_task(
            SpeechToTextCreateTaskInput(
                audio={
                    "audio_url": "https://example.com/audio.wav",
                    "audio_format": "wav",
                }
            ),
            fake_ctx,
        )

        progresses = [p for p, _ in fake_ctx.progress_reports]
        assert 10 in progresses
        assert 30 in progresses
        assert 50 in progresses
        assert 100 in progresses

    async def test_task_ownership_recorded(
        self,
        test_env: None,
        fake_ctx: FakeContext,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _patch_las_service(monkeypatch, task_id="task-owned-123")

        result = await speech_to_text_create_task(
            SpeechToTextCreateTaskInput(
                audio={
                    "audio_url": "https://example.com/audio.wav",
                    "audio_format": "wav",
                }
            ),
            fake_ctx,
        )

        assert isinstance(result, SpeechToTextCreateTaskOutput)
        runtime = fake_ctx.lifespan_context["runtime"]
        owner_ids = await runtime.ownership_store.list_task_ids(
            type("Owner", (), {"principal_id": "local", "tenant_id": "local", "is_local": True})()
        )
        assert "task-owned-123" in owner_ids

    async def test_provider_error_propagates(
        self,
        test_env: None,
        fake_ctx: FakeContext,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        async def mock_submit(
            self: LasAsrService,
            request: Any,
        ) -> tuple[LasAsrSubmitResponse, str | None]:
            raise ProviderError(
                NormalizedProviderError(
                    provider="las",
                    operation="submit_asr_task",
                    http_status=400,
                    code="INVALID_FORMAT",
                    message="Unsupported audio format",
                    retryable=False,
                )
            )

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
        assert isinstance(result, ToolResult)
        assert result.is_error
        text = result.content[0].text
        assert "las submit_asr_task failed" in text
        assert "code=INVALID_FORMAT" in text

    async def test_base64_input_requires_tos(
        self,
        test_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("TOS_ACCESS_KEY", raising=False)
        monkeypatch.delenv("TOS_SECRET_KEY", raising=False)
        monkeypatch.delenv("TOS_BUCKET", raising=False)
        from modelark_mcp.config.env import get_settings

        get_settings.cache_clear()

        fake_ctx = FakeContext(lifespan_context={"runtime": {}})
        with pytest.raises(ValueError, match="TOS credentials"):
            await speech_to_text_create_task(
                SpeechToTextCreateTaskInput(
                    audio={
                        "audio_data": "aGVsbG8=",
                        "audio_format": "wav",
                    }
                ),
                fake_ctx,
            )

    async def test_exactly_one_input_required(
        self,
        test_env: None,
        fake_ctx: FakeContext,
    ) -> None:
        with pytest.raises(ValueError, match="Provide exactly one"):
            await speech_to_text_create_task(
                SpeechToTextCreateTaskInput(
                    audio={
                        "audio_url": "https://example.com/audio.wav",
                        "audio_data": "aGVsbG8=",
                        "audio_format": "wav",
                    }
                ),
                fake_ctx,
            )
