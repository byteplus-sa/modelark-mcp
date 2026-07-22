"""Live smoke test: generate image, audio, and video variations in parallel.

Run with: uv run python scripts/live_smoke_test_variations.py

Exercises the three parallel variation tools:
1. Seedream — 3 image variations with distinct seeds
2. Seed Audio — 3 audio variations
3. Seedance — 2 video task variations

All artifacts are saved locally in .artifacts/.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import truststore

truststore.inject_into_ssl()

from modelark_mcp.config.env import get_settings  # noqa: E402
from modelark_mcp.server import get_artifact_store  # noqa: E402
from modelark_mcp.test_utils import FakeContext  # noqa: E402
from modelark_mcp.tools.seed_audio_generate_variations import (  # noqa: E402
    SeedAudioVariationsInput,
    seed_audio_generate_variations,
)
from modelark_mcp.tools.seedance_create_task import SeedanceImageInput  # noqa: E402
from modelark_mcp.tools.seedance_create_task_variations import (  # noqa: E402
    SeedanceVariationsInput,
    seedance_create_task_variations,
)
from modelark_mcp.tools.seedream_generate_image_variations import (  # noqa: E402
    SeedreamVariationsInput,
    seedream_generate_image_variations,
)

ARTIFACTS_DIR = Path(".artifacts")


def header(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}\n")


async def test_image_variations() -> None:
    header("Seedream: 3 Image Variations (seeds 42, 43, 44)")
    ctx = FakeContext()

    result = await seedream_generate_image_variations(
        SeedreamVariationsInput(
            prompt="A beautiful mountain landscape, digital art",
            variations=3,
            base_seed=42,
            size="1024x1024",
            response_format="url",
            persist=True,
        ),
        ctx,
    )

    print(f"  Total: {result.summary.total}")
    print(f"  Succeeded: {result.summary.succeeded}")
    print(f"  Failed: {result.summary.failed}")

    store = get_artifact_store()
    for v in result.summary.variations:
        if v.artifact:
            stored = await store.get(v.artifact.id)
            path = ARTIFACTS_DIR / f"variation_image_seed{v.seed}.jpeg"
            path.write_bytes(stored.data)
            print(f"  [{v.index}] seed={v.seed} → {path} ({len(stored.data):,} bytes)")
        elif v.error:
            print(f"  [{v.index}] seed={v.seed} ERROR: {v.error['code']}: {v.error['message']}")


async def test_audio_variations() -> None:
    header("Seed Audio: 3 Audio Variations")
    ctx = FakeContext()

    result = await seed_audio_generate_variations(
        SeedAudioVariationsInput(
            text_prompt="Hello, this is a parallel variation test of the Seed Audio MCP tool.",
            variations=3,
        ),
        ctx,
    )

    print(f"  Total: {result.summary.total}")
    print(f"  Succeeded: {result.summary.succeeded}")
    print(f"  Failed: {result.summary.failed}")

    store = get_artifact_store()
    for v in result.summary.variations:
        if v.artifact:
            stored = await store.get(v.artifact.id)
            path = ARTIFACTS_DIR / f"variation_audio_{v.index}.wav"
            path.write_bytes(stored.data)
            print(f"  [{v.index}] → {path} ({len(stored.data):,} bytes)")
        elif v.error:
            print(f"  [{v.index}] ERROR: {v.error['code']}: {v.error['message']}")


async def test_seedance_variations() -> None:
    header("Seedance: 2 Video Task Variations")
    ctx = FakeContext()

    # Use a minimal 1x1 red PNG as reference image
    red_pixel = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="

    result = await seedance_create_task_variations(
        SeedanceVariationsInput(
            variation_prompts=[
                "A cat walks forward slowly through a garden",
                "A cat looks around curiously, then jumps playfully",
            ],
            variations=2,
            images=[
                SeedanceImageInput(
                    kind="base64", data=red_pixel, mime_type="image/png", role="reference_image"
                )
            ],
            resolution="480p",
            duration=5,
        ),
        ctx,
    )

    print(f"  Total: {result.summary.total}")
    print(f"  Succeeded: {result.summary.succeeded}")
    print(f"  Failed: {result.summary.failed}")
    for v in result.summary.variations:
        if v.task_id:
            print(f"  [{v.index}] task_id={v.task_id}")
        elif v.error:
            print(f"  [{v.index}] ERROR: {v.error['code']}: {v.error['message']}")


async def main() -> int:
    header("ModelArk Seed MCP — Live Variation Smoke Test")

    settings = get_settings()
    print(f"  ModelArk configured: {settings.has_modelark}")
    print(f"  Seed Audio configured: {settings.has_seed_audio}")

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    await test_image_variations()
    await test_audio_variations()
    await test_seedance_variations()

    header("Done")
    print("  Artifacts in .artifacts/:")
    for path in sorted(ARTIFACTS_DIR.glob("variation_*")):
        size_kb = path.stat().st_size / 1024
        print(f"    {path.name} ({size_kb:.1f} KB)")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
