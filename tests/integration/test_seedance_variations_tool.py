"""Integration tests for the ``seedance_create_task_variations`` tool."""

from __future__ import annotations

from typing import Any

import pytest

from modelark_mcp.domain.errors import NormalizedProviderError, ProviderError
from modelark_mcp.providers.modelark.seedance import SeedanceService
from modelark_mcp.test_utils import FakeContext
from modelark_mcp.tools.seedance_create_task import SeedanceVideoInput
from modelark_mcp.tools.seedance_create_task_variations import (
    SeedanceVariationsInput,
    SeedanceVariationsOutput,
    seedance_create_task_variations,
)


def _patch_seedance_by_prompt(
    monkeypatch: pytest.MonkeyPatch,
    responses_by_prompt: dict[str, dict[str, str] | Exception],
) -> None:
    """Mock SeedanceService.create_task to return different results based on the prompt."""

    async def mock_create(self: SeedanceService, request: Any) -> tuple[str, str | None]:
        prompt = ""
        for item in request.content:
            if item.type == "text" and item.text:
                prompt = item.text
                break
        response = responses_by_prompt.get(prompt)
        if isinstance(response, Exception):
            raise response
        return response["task_id"], response.get("request_id")

    monkeypatch.setattr(SeedanceService, "create_task", mock_create)

    async def mock_close(self: SeedanceService) -> None:
        pass

    monkeypatch.setattr(SeedanceService, "close", mock_close)


class TestSeedanceVariationsTool:
    """Integration tests for seedance_create_task_variations."""

    async def test_three_tasks_all_succeed(
        self,
        test_env: None,
        fake_ctx: FakeContext,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _patch_seedance_by_prompt(
            monkeypatch,
            {
                "a cat": {"task_id": "task-1", "request_id": "req-1"},
                "a dog": {"task_id": "task-2", "request_id": "req-2"},
                "a bird": {"task_id": "task-3", "request_id": "req-3"},
            },
        )

        result = await seedance_create_task_variations(
            SeedanceVariationsInput(
                variation_prompts=["a cat", "a dog", "a bird"],
                variations=3,
                videos=[SeedanceVideoInput(url="https://cdn.example.com/v.mp4")],
            ),
            fake_ctx,
        )

        assert isinstance(result, SeedanceVariationsOutput)
        assert result.summary.total == 3
        assert result.summary.succeeded == 3
        assert result.summary.failed == 0
        assert result.summary.variations[0].task_id == "task-1"
        assert result.summary.variations[1].task_id == "task-2"
        assert result.summary.variations[2].task_id == "task-3"
        assert result.recommended_poll_after_ms == 5000

    async def test_partial_failure(
        self,
        test_env: None,
        fake_ctx: FakeContext,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _patch_seedance_by_prompt(
            monkeypatch,
            {
                "good": {"task_id": "task-1"},
                "bad": ProviderError(
                    NormalizedProviderError(
                        provider="modelark",
                        operation="create_task",
                        http_status=400,
                        code="INVALID_PARAM",
                        message="bad",
                        retryable=False,
                    )
                ),
            },
        )

        result = await seedance_create_task_variations(
            SeedanceVariationsInput(
                variation_prompts=["good", "bad", "good"],
                variations=3,
                videos=[SeedanceVideoInput(url="https://cdn.example.com/v.mp4")],
            ),
            fake_ctx,
        )

        assert result.summary.succeeded == 2
        assert result.summary.failed == 1
        assert result.summary.variations[1].error is not None
        assert result.summary.variations[1].task_id is None

    async def test_no_prompt_raises(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="Either prompt or variation_prompts"):
            SeedanceVariationsInput(
                variations=2,
                videos=[SeedanceVideoInput(url="https://cdn.example.com/v.mp4")],
            )

    async def test_no_media_raises(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="At least one media"):
            SeedanceVariationsInput(prompt="test", variations=1)

    async def test_too_many_variations_raises(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            SeedanceVariationsInput(
                prompt="test",
                variations=6,
                videos=[SeedanceVideoInput(url="https://cdn.example.com/v.mp4")],
            )

    async def test_inherited_validators_fire(self) -> None:
        """Verify that SeedanceCreateTaskInput validators are inherited."""
        from pydantic import ValidationError

        # Too many reference videos
        videos = [SeedanceVideoInput(url=f"https://cdn.example.com/v{i}.mp4") for i in range(4)]
        with pytest.raises(ValidationError, match="Too many reference videos"):
            SeedanceVariationsInput(prompt="test", variations=1, videos=videos)
