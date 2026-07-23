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
import base64
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

import truststore

truststore.inject_into_ssl()

from _smoke_context import SmokeContext, require_tool_success  # noqa: E402

from modelark_mcp.config.env import get_settings  # noqa: E402
from modelark_mcp.runtime import close_runtime_services, create_runtime_services  # noqa: E402
from modelark_mcp.tools.seed_audio_generate_variations import (  # noqa: E402
    SeedAudioVariationsInput,
    seed_audio_generate_variations,
)
from modelark_mcp.tools.seedance_create_task import SeedanceImageInput  # noqa: E402
from modelark_mcp.tools.seedance_create_task_variations import (  # noqa: E402
    SeedanceVariationsInput,
    seedance_create_task_variations,
)
from modelark_mcp.tools.seedance_get_task import (  # noqa: E402
    SeedanceGetTaskInput,
    seedance_get_task,
)
from modelark_mcp.tools.seedance_list_tasks import (  # noqa: E402
    SeedanceListTasksInput,
    seedance_list_tasks,
)
from modelark_mcp.tools.seedream_generate_image_variations import (  # noqa: E402
    SeedreamVariationsInput,
    seedream_generate_image_variations,
)

if TYPE_CHECKING:
    from modelark_mcp.artifacts.store import ArtifactStore
    from modelark_mcp.domain.artifacts import ArtifactRef
    from modelark_mcp.runtime import RuntimeServices

ARTIFACTS_DIR = Path(".artifacts")


def header(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}\n")


async def test_image_variations(
    ctx: SmokeContext, store: ArtifactStore
) -> tuple[bool, ArtifactRef | None]:
    header("Seedream: 3 Image Variations (seeds 42, 43, 44)")
    result = require_tool_success(
        await seedream_generate_image_variations(
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
    )

    print(f"  Total: {result.summary.total}")
    print(f"  Succeeded: {result.summary.succeeded}")
    print(f"  Failed: {result.summary.failed}")

    all_verified = result.summary.failed == 0
    reference_image: ArtifactRef | None = None
    for v in result.summary.variations:
        if v.artifact:
            stored = await store.get(v.artifact.id)
            reference_image = reference_image or v.artifact
            path = ARTIFACTS_DIR / f"variation_image_seed{v.seed}.jpeg"
            path.write_bytes(stored.data)
            print(f"  [{v.index}] seed={v.seed} → {path} ({len(stored.data):,} bytes)")
        elif v.error:
            print(f"  [{v.index}] seed={v.seed} ERROR: {v.error.code}: {v.error.message}")
            all_verified = False
    return all_verified, reference_image


async def test_audio_variations(ctx: SmokeContext, store: ArtifactStore) -> bool:
    header("Seed Audio: 3 Audio Variations")
    result = require_tool_success(
        await seed_audio_generate_variations(
            SeedAudioVariationsInput(
                text_prompt="Hello, this is a parallel variation test of the Seed Audio MCP tool.",
                variations=3,
            ),
            ctx,
        )
    )

    print(f"  Total: {result.summary.total}")
    print(f"  Succeeded: {result.summary.succeeded}")
    print(f"  Failed: {result.summary.failed}")

    all_verified = result.summary.failed == 0
    for v in result.summary.variations:
        if v.artifact:
            stored = await store.get(v.artifact.id)
            path = ARTIFACTS_DIR / f"variation_audio_{v.index}.wav"
            path.write_bytes(stored.data)
            print(f"  [{v.index}] → {path} ({len(stored.data):,} bytes)")
        elif v.error:
            print(f"  [{v.index}] ERROR: {v.error.code}: {v.error.message}")
            all_verified = False
    return all_verified


async def test_seedance_variations(
    ctx: SmokeContext,
    runtime: RuntimeServices,
    reference_image: ArtifactRef,
) -> bool:
    header("Seedance: 2 Video Task Variations")
    reference_data = await runtime.artifact_store.get(reference_image.id)
    reference_b64 = base64.b64encode(reference_data.data).decode("ascii")

    result = require_tool_success(
        await seedance_create_task_variations(
            SeedanceVariationsInput(
                variation_prompts=[
                    "A cat walks forward slowly through a garden",
                    "A cat looks around curiously, then jumps playfully",
                ],
                variations=2,
                images=[
                    SeedanceImageInput(
                        kind="base64",
                        data=reference_b64,
                        mime_type=reference_data.mime_type,
                        role="reference_image",
                    )
                ],
                resolution="480p",
                duration=5,
            ),
            ctx,
        )
    )

    print(f"  Total: {result.summary.total}")
    print(f"  Succeeded: {result.summary.succeeded}")
    print(f"  Failed: {result.summary.failed}")
    all_verified = result.summary.failed == 0
    task_ids: list[str] = []
    for v in result.summary.variations:
        if v.task_id:
            print(f"  [{v.index}] task_id={v.task_id}")
            task_ids.append(v.task_id)
        elif v.error:
            print(f"  [{v.index}] ERROR: {v.error.code}: {v.error.message}")
            all_verified = False

    if not task_ids:
        return False

    listed = require_tool_success(
        await seedance_list_tasks(SeedanceListTasksInput(task_ids=task_ids), ctx)
    )
    listed_ids = {task.task_id for task in listed.tasks}
    if listed_ids != set(task_ids):
        print(f"  List verification failed: expected {task_ids}, got {sorted(listed_ids)}")
        return False
    print(f"  Listed all {len(listed_ids)} created tasks")

    pending = set(task_ids)
    deadline = time.monotonic() + 300
    while pending and time.monotonic() < deadline:
        for task_id in list(pending):
            task = require_tool_success(
                await seedance_get_task(
                    SeedanceGetTaskInput(task_id=task_id, persist_output=True), ctx
                )
            )
            print(f"  Task {task_id}: {task.status}")
            if task.status in {"queued", "running"}:
                continue
            pending.remove(task_id)
            if task.status != "succeeded" or task.video is None:
                print(f"  Task {task_id} failed: {task.error}")
                all_verified = False
                continue
            stored = await runtime.artifact_store.get(task.video.id)
            output_path = ARTIFACTS_DIR / f"variation_video_{task_id}.mp4"
            output_path.write_bytes(stored.data)
            print(
                f"  Task {task_id}: video persisted to {output_path} ({len(stored.data):,} bytes)"
            )
        if pending:
            await asyncio.sleep(10)

    if pending:
        print(f"  Timed out waiting for tasks: {sorted(pending)}")
        all_verified = False
    return all_verified


async def main() -> int:
    header("ModelArk Seed MCP — Live Variation Smoke Test")

    settings = get_settings()
    print(f"  ModelArk configured: {settings.has_modelark}")
    print(f"  Seed Audio configured: {settings.has_seed_audio}")

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    runtime = await create_runtime_services(settings)
    ctx = SmokeContext(lifespan_context={"runtime": runtime})
    try:
        image_ok, reference_image = await test_image_variations(ctx, runtime.artifact_store)
        audio_ok = await test_audio_variations(ctx, runtime.artifact_store)
        seedance_ok = (
            await test_seedance_variations(ctx, runtime, reference_image)
            if reference_image is not None
            else False
        )
    finally:
        await close_runtime_services(runtime)

    header("Done")
    print("  Artifacts in .artifacts/:")
    for path in sorted(ARTIFACTS_DIR.glob("variation_*")):
        size_kb = path.stat().st_size / 1024
        print(f"    {path.name} ({size_kb:.1f} KB)")

    return 0 if image_ok and audio_ok and seedance_ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
