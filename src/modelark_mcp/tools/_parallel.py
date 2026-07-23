"""Shared helpers for parallel variation generation.

Provides ``generate_seeds``, ``resolve_prompts``, ``gather_with_timeout``,
``run_variation_batch``, and ``DEFAULT_MAX_CONCURRENT`` used by the
variation tool handlers.
"""

from __future__ import annotations

import asyncio
import secrets
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from modelark_mcp.domain.models import VariationError, VariationResult, VariationSummary
from modelark_mcp.tools._cost import DEFAULT_MAX_CONCURRENT


def generate_seeds(base_seed: int | None, count: int) -> list[int | None]:
    """Generate distinct seeds for each variation.

    - ``base_seed=None`` → ``[None] * count`` (provider randomizes; seed
      is not recorded in VariationResult).
    - ``base_seed=-1`` → random seeds for each variation (client picks;
      recorded for reproducibility).
    - ``base_seed=N`` → ``[N, N+1, N+2, ...]`` (deterministic sequence,
      wrapped modulo 2147483648 to stay within the API's valid range).
    """
    if base_seed is None:
        return [None] * count
    if base_seed == -1:
        return [secrets.randbelow(2147483648) for _ in range(count)]
    return [(base_seed + i) % 2147483648 for i in range(count)]


def resolve_prompts(
    base_prompt: str | None,
    variation_prompts: list[str] | None,
    count: int,
) -> list[str]:
    """Resolve the prompt for each variation.

    If ``variation_prompts`` is provided, it must have ``count`` entries.
    Otherwise, ``base_prompt`` is used for all variations.
    """
    if variation_prompts:
        return list(variation_prompts)
    if base_prompt is None:
        raise ValueError("Either base_prompt or variation_prompts must be provided.")
    return [base_prompt] * count


async def gather_with_timeout(
    coros: Sequence[Awaitable[Any]],
    timeout: float,
) -> list[Any]:
    """Run N coroutines in parallel with a per-coroutine timeout.

    Wraps each coroutine in ``asyncio.wait_for``. Collects all results
    (including exceptions and timeouts) via ``asyncio.gather`` with
    ``return_exceptions=True``.
    """
    timed_coros = [asyncio.wait_for(coro, timeout=timeout) for coro in coros]
    results = await asyncio.gather(*timed_coros, return_exceptions=True)
    return list(results)


async def run_variation_batch(
    count: int,
    timeout: float,
    factory: Callable[[int], Awaitable[VariationResult]],
    *,
    max_concurrent: int = DEFAULT_MAX_CONCURRENT,
) -> VariationSummary:
    """Run a batch of variation coroutines with bounded concurrency and timeout.

    Args:
        count: Number of variations to generate.
        timeout: Per-coroutine timeout in seconds.
        factory: Callable(index) -> coroutine that produces a VariationResult.
        max_concurrent: Maximum concurrent provider calls.

    Returns:
        VariationSummary with succeeded/failed counts and per-variation results.
    """
    limiter = asyncio.Semaphore(max_concurrent)

    async def _guarded(idx: int) -> VariationResult:
        async with limiter:
            return await factory(idx)

    coros = [_guarded(i) for i in range(count)]
    results = await gather_with_timeout(coros, timeout=timeout)

    variation_results: list[VariationResult] = []
    for i, result in enumerate(results):
        if isinstance(result, asyncio.TimeoutError):
            variation_results.append(
                VariationResult(
                    index=i,
                    error=VariationError(code="TIMEOUT", message=f"Variation {i} timed out"),
                )
            )
        elif isinstance(result, Exception):
            variation_results.append(
                VariationResult(
                    index=i,
                    error=VariationError(code="GATHER_ERROR", message=str(result)),
                )
            )
        else:
            variation_results.append(result)

    succeeded = sum(1 for r in variation_results if r.artifact is not None or r.task_id is not None)
    failed = count - succeeded

    return VariationSummary(
        total=count,
        succeeded=succeeded,
        failed=failed,
        variations=variation_results,
    )
