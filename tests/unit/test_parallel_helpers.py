"""Unit tests for parallel generation helpers."""

from __future__ import annotations

import asyncio

import pytest

from modelark_mcp.tools._parallel import gather_with_timeout, generate_seeds, resolve_prompts


class TestGenerateSeeds:
    """Tests for generate_seeds."""

    def test_none_returns_none_list(self) -> None:
        seeds = generate_seeds(None, 3)
        assert seeds == [None, None, None]

    def test_minus_one_returns_random_seeds(self) -> None:
        seeds = generate_seeds(-1, 3)
        assert len(seeds) == 3
        assert all(s is not None and 0 <= s <= 2147483647 for s in seeds)

    def test_minus_one_seeds_are_distinct(self) -> None:
        seeds = generate_seeds(-1, 10)
        assert len(set(seeds)) > 1

    def test_deterministic_sequence(self) -> None:
        seeds = generate_seeds(42, 3)
        assert seeds == [42, 43, 44]

    def test_overflow_wraps_with_modulo(self) -> None:
        seeds = generate_seeds(2147483647, 3)
        assert seeds == [2147483647, 0, 1]

    def test_single_variation(self) -> None:
        seeds = generate_seeds(100, 1)
        assert seeds == [100]

    def test_zero_count(self) -> None:
        seeds = generate_seeds(42, 0)
        assert seeds == []


class TestResolvePrompts:
    """Tests for resolve_prompts."""

    def test_base_prompt_repeated(self) -> None:
        prompts = resolve_prompts("hello", None, 3)
        assert prompts == ["hello", "hello", "hello"]

    def test_variation_prompts_used(self) -> None:
        prompts = resolve_prompts(None, ["a", "b", "c"], 3)
        assert prompts == ["a", "b", "c"]

    def test_variation_prompts_override_base(self) -> None:
        prompts = resolve_prompts("base", ["x", "y"], 2)
        assert prompts == ["x", "y"]

    def test_no_prompt_raises(self) -> None:
        with pytest.raises(ValueError, match="Either base_prompt or variation_prompts"):
            resolve_prompts(None, None, 3)


class TestGatherWithTimeout:
    """Tests for gather_with_timeout."""

    async def test_all_succeed(self) -> None:
        async def coro(i: int) -> int:
            return i * 2

        coros = [coro(i) for i in range(3)]
        results = await gather_with_timeout(coros, timeout=10.0)
        assert results == [0, 2, 4]

    async def test_one_times_out(self) -> None:
        async def fast(i: int) -> int:
            return i

        async def slow() -> int:
            await asyncio.sleep(100)
            return 999

        coros = [fast(1), slow(), fast(3)]
        results = await gather_with_timeout(coros, timeout=0.1)
        assert results[0] == 1
        assert isinstance(results[1], asyncio.TimeoutError)
        assert results[2] == 3

    async def test_exception_caught(self) -> None:
        async def good() -> int:
            return 42

        async def bad() -> int:
            raise ValueError("boom")

        coros = [good(), bad(), good()]
        results = await gather_with_timeout(coros, timeout=10.0)
        assert results[0] == 42
        assert isinstance(results[1], ValueError)
        assert results[2] == 42

    async def test_empty_list(self) -> None:
        results = await gather_with_timeout([], timeout=10.0)
        assert results == []
