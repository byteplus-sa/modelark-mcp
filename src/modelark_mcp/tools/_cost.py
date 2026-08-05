"""Cost estimation and rate limiting for parallel generation.

Provides cost estimation constants and logging for billable operations.
Rate limiting is handled via ``asyncio.Semaphore`` directly in each
variation tool handler.
"""

from __future__ import annotations

from modelark_mcp.observability.logger import info as log_info

# Provider cost estimates (USD per unit).
COST_PER_IMAGE = 0.03
COST_PER_AUDIO_SECOND = 0.0031
COST_PER_VIDEO_TASK = 0.07
COST_PER_STT_SECOND = 0.0006
COST_UNDERSTANDING_INPUT_PER_MTOK = 0.50
COST_UNDERSTANDING_OUTPUT_PER_MTOK = 3.00

# Default max concurrent provider calls.
DEFAULT_MAX_CONCURRENT = 5


def estimate_cost(
    *,
    product: str,
    variations: int,
    duration_seconds: float = 0.0,
    prompt_tokens: int | None = None,
    max_tokens: int | None = None,
) -> float:
    """Estimate the cost of a parallel generation batch.

    Args:
        product: "image", "audio", "video", "stt", or "understanding".
        variations: Number of variations.
        duration_seconds: Expected output duration (audio only).
        prompt_tokens: Estimated input tokens (understanding only).
        max_tokens: Maximum output tokens (understanding only).

    Returns:
        Estimated cost in USD.
    """
    if product == "image":
        return round(variations * COST_PER_IMAGE, 2)
    if product == "audio":
        return round(variations * max(duration_seconds, 10) * COST_PER_AUDIO_SECOND, 2)
    if product == "video":
        return round(variations * COST_PER_VIDEO_TASK, 2)
    if product == "stt":
        return round(variations * max(duration_seconds, 10) * COST_PER_STT_SECOND, 2)
    if product == "understanding":
        out = (max_tokens or 0) / 1_000_000 * COST_UNDERSTANDING_OUTPUT_PER_MTOK
        inp = (prompt_tokens or 0) / 1_000_000 * COST_UNDERSTANDING_INPUT_PER_MTOK
        return round(variations * (inp + out), 4)
    return 0.0


def log_cost_estimate(
    *,
    product: str,
    variations: int,
    duration_seconds: float = 0.0,
    prompt_tokens: int | None = None,
    max_tokens: int | None = None,
) -> float:
    """Log a cost estimate before dispatching a batch."""
    cost = estimate_cost(
        product=product,
        variations=variations,
        duration_seconds=duration_seconds,
        prompt_tokens=prompt_tokens,
        max_tokens=max_tokens,
    )
    log_info(
        "cost_estimate",
        product=product,
        variations=variations,
        estimated_cost_usd=cost,
    )
    return cost
