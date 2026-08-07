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
COST_PER_VIDEO_TASK_2_5 = 0.35
COST_PER_STT_SECOND = 0.0006
COST_UNDERSTANDING_INPUT_PER_MTOK = 0.50
COST_UNDERSTANDING_OUTPUT_PER_MTOK = 3.00

# Default max concurrent provider calls.
DEFAULT_MAX_CONCURRENT = 5

# Model-specific cost overrides for video tasks.
_VIDEO_COST_OVERRIDES: dict[str, float] = {}


def register_video_cost_override(model_id: str, cost_per_task: float) -> None:
    """Register a model-specific cost-per-task override for video generation."""
    _VIDEO_COST_OVERRIDES[model_id] = cost_per_task


def _video_cost_for_model(model_id: str | None) -> float:
    """Return the cost-per-task for a given video model, or the default."""
    if model_id and model_id in _VIDEO_COST_OVERRIDES:
        return _VIDEO_COST_OVERRIDES[model_id]
    if model_id and "seedance-2-5" in model_id:
        return COST_PER_VIDEO_TASK_2_5
    return COST_PER_VIDEO_TASK


def estimate_cost(
    *,
    product: str,
    variations: int,
    duration_seconds: float = 0.0,
    prompt_tokens: int | None = None,
    max_tokens: int | None = None,
    model_id: str | None = None,
) -> float:
    """Estimate the cost of a parallel generation batch.

    Args:
        product: "image", "audio", "video", "stt", or "understanding".
        variations: Number of variations.
        duration_seconds: Expected output duration (audio only).
        prompt_tokens: Estimated input tokens (understanding only).
        max_tokens: Maximum output tokens (understanding only).
        model_id: Model ID for model-specific pricing (video only).

    Returns:
        Estimated cost in USD.
    """
    if product == "image":
        return round(variations * COST_PER_IMAGE, 2)
    if product == "audio":
        return round(variations * max(duration_seconds, 10) * COST_PER_AUDIO_SECOND, 2)
    if product == "video":
        return round(variations * _video_cost_for_model(model_id), 2)
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
    model_id: str | None = None,
) -> float:
    """Log a cost estimate before dispatching a batch."""
    cost = estimate_cost(
        product=product,
        variations=variations,
        duration_seconds=duration_seconds,
        prompt_tokens=prompt_tokens,
        max_tokens=max_tokens,
        model_id=model_id,
    )
    log_info(
        "cost_estimate",
        product=product,
        variations=variations,
        estimated_cost_usd=cost,
    )
    return cost
