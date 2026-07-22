"""Shared helpers for parallel variation generation.

Provides ``generate_seeds``, ``resolve_prompts``, and ``gather_with_timeout``
used by the variation tool handlers.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Sequence
from typing import Any


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
        return [random.randint(0, 2147483647) for _ in range(count)]
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
    coros: Sequence[Any],
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
