"""Tests for safe provider retry behavior."""

from __future__ import annotations

import pytest

from modelark_mcp.domain.errors import NormalizedProviderError, ProviderError
from modelark_mcp.providers.retry import RetryPolicy, call_with_retry


def _error(
    *,
    retryable: bool = True,
    ambiguous: bool = False,
    retry_after: float | None = None,
) -> ProviderError:
    return ProviderError(
        NormalizedProviderError(
            provider="modelark",
            operation="generate_image",
            code="TRANSIENT",
            message="try again",
            retryable=retryable,
            ambiguous_completion=ambiguous,
            retry_after_seconds=retry_after,
        )
    )


async def test_retries_retryable_non_ambiguous_error() -> None:
    attempts = 0
    delays: list[float] = []

    async def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise _error()
        return "ok"

    async def sleep(delay: float) -> None:
        delays.append(delay)

    result = await call_with_retry(
        operation,
        policy=RetryPolicy(base_delay_seconds=1, jitter_ratio=0),
        sleep=sleep,
    )

    assert result == "ok"
    assert attempts == 3
    assert delays == [1, 2]


async def test_honors_retry_after() -> None:
    attempts = 0
    delays: list[float] = []

    async def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise _error(retry_after=3.5)
        return "ok"

    async def sleep(delay: float) -> None:
        delays.append(delay)

    await call_with_retry(operation, sleep=sleep)
    assert delays == [3.5]


@pytest.mark.parametrize(
    ("retryable", "ambiguous"),
    [(False, False), (True, True)],
)
async def test_never_retries_unsafe_error(
    retryable: bool,
    ambiguous: bool,
) -> None:
    attempts = 0

    async def operation() -> str:
        nonlocal attempts
        attempts += 1
        raise _error(retryable=retryable, ambiguous=ambiguous)

    with pytest.raises(ProviderError):
        await call_with_retry(operation)
    assert attempts == 1
