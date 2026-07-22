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

# Default max concurrent provider calls.
DEFAULT_MAX_CONCURRENT = 5


def estimate_cost(
    *,
    product: str,
    variations: int,
    duration_seconds: float = 0.0,
) -> float:
    """Estimate the cost of a parallel generation batch.

    Args:
        product: "image", "audio", or "video".
        variations: Number of variations.
        duration_seconds: Expected output duration (audio only).

    Returns:
        Estimated cost in USD.
    """
    if product == "image":
        return round(variations * COST_PER_IMAGE, 2)
    if product == "audio":
        return round(variations * max(duration_seconds, 10) * COST_PER_AUDIO_SECOND, 2)
    if product == "video":
        return round(variations * COST_PER_VIDEO_TASK, 2)
    return 0.0


def log_cost_estimate(
    *,
    product: str,
    variations: int,
    duration_seconds: float = 0.0,
) -> float:
    """Log a cost estimate before dispatching a batch."""
    cost = estimate_cost(
        product=product,
        variations=variations,
        duration_seconds=duration_seconds,
    )
    log_info(
        "cost_estimate",
        product=product,
        variations=variations,
        estimated_cost_usd=cost,
    )
    return cost
