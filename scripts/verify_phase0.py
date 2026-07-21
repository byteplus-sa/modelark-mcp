"""Phase 0: Account and contract verification.

Run with: uv run python scripts/verify_phase0.py

Performs minimal billable calls to confirm:
1. ModelArk Bearer auth works (Seedream + Seedance).
2. Seed Speech X-Api-Key auth works (Seed Audio).
3. The configured model IDs are accepted.
4. Response shapes match our Pydantic schemas.

All responses are redacted — no media URLs, Base64, or credentials are printed.
Only the structural fields needed for verification are shown.

Cost: one image generation (~$0.02), one audio generation (~$0.003/min trial),
one Seedance task (queued, immediately cancelled to avoid video cost).
"""

from __future__ import annotations

import asyncio
import sys
import traceback
from typing import Any

import truststore

truststore.inject_into_ssl()

from modelark_mcp.config.env import get_settings  # noqa: E402
from modelark_mcp.config.model_capabilities import get_capability_registry  # noqa: E402
from modelark_mcp.providers.modelark.client import ModelArkGateway  # noqa: E402
from modelark_mcp.providers.modelark.schemas import (  # noqa: E402
    SeedanceContentItem,
    SeedanceCreateProviderRequest,
)
from modelark_mcp.providers.modelark.seedance import SeedanceService  # noqa: E402
from modelark_mcp.providers.modelark.seedream import SeedreamService  # noqa: E402
from modelark_mcp.providers.seed_speech.client import SeedSpeechGateway  # noqa: E402
from modelark_mcp.providers.seed_speech.schemas import SeedAudioProviderRequest  # noqa: E402
from modelark_mcp.providers.seed_speech.seed_audio import SeedAudioService  # noqa: E402


def _redact(obj: Any) -> Any:
    """Remove sensitive fields from a dict for safe printing."""
    if isinstance(obj, dict):
        return {
            k: "[REDACTED]"
            if k.lower() in ("audio", "url", "b64_json", "video_url", "last_frame_url")
            else _redact(v)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_redact(i) for i in obj]
    return obj


async def verify_seedream() -> bool:
    """Verify Seedream image generation with a minimal text-to-image call."""
    print("\n=== Seedream (Image Generation) ===")
    settings = get_settings()
    registry = get_capability_registry()
    caps = registry.get_image_capabilities()
    print(f"Model: {caps.model_id}")
    print(f"Family: {caps.family.value}")
    print(f"Max references: {caps.max_references}")
    print(f"Supports batch: {caps.supports_batch}")

    gateway = ModelArkGateway(
        api_key=settings.modelark_api_key,
        base_url=settings.modelark_base_url,
    )
    service = SeedreamService(gateway=gateway)

    request = SeedreamService.build_request(
        model=caps.model_id,
        prompt="A small red circle on white background",
        size="1024x1024",
        response_format="url",
    )
    print(f"Request model: {request.model}")
    print(f"Request stream: {request.stream}")

    try:
        response, request_id = await service.generate(request)
        print(f"✓ Request ID: {request_id}")
        print(f"✓ Created: {response.created}")
        print(f"✓ Images returned: {len(response.data)}")
        print(f"✓ Redacted response: {_redact(response.model_dump())}")
        return True
    except Exception as exc:
        print(f"✗ FAILED: {exc}")
        return False
    finally:
        await service.close()


async def verify_seedance() -> bool:
    """Verify Seedance task creation + immediate cancellation."""
    print("\n=== Seedance (Video Generation) ===")
    settings = get_settings()
    registry = get_capability_registry()
    caps = registry.get_video_capabilities()
    print(f"Model: {caps.model_id}")
    print(f"Family: {caps.family.value}")
    print(f"Resolutions: {caps.supported_resolutions}")

    gateway = ModelArkGateway(
        api_key=settings.modelark_api_key,
        base_url=settings.modelark_base_url,
    )
    service = SeedanceService(gateway=gateway)

    # Build a minimal task with a text prompt + a reference image URL.
    content = [
        SeedanceContentItem(type="text", text="A cat walking"),
    ]
    request = SeedanceCreateProviderRequest(
        model=caps.model_id,
        content=content,
        resolution="480p",
        duration=-1,
    )

    try:
        task_id, request_id = await service.create_task(request)
        print(f"✓ Task ID: {task_id}")
        print(f"✓ Request ID: {request_id}")

        # Immediately retrieve to confirm it's queued.
        task, _ = await service.get_task(task_id)
        print(f"✓ Task status: {task.status}")
        print(f"✓ Task model: {task.model}")

        # Cancel it immediately to avoid video generation cost.
        if task.status == "queued":
            try:
                await service.delete_task(task_id)
                print("✓ Task cancelled (queued → cancelled)")
            except Exception as exc:
                print(f"⚠ Cancel failed (may have already started): {exc}")
        else:
            print(f"⚠ Task was not queued (status={task.status}), skipping cancel")

        return True
    except Exception as exc:
        print(f"✗ FAILED: {exc}")
        traceback.print_exc()
        return False
    finally:
        await service.close()


async def verify_seed_audio() -> bool:
    """Verify Seed Audio with a minimal text-only generation."""
    print("\n=== Seed Audio (Speech) ===")
    settings = get_settings()
    print(f"Base URL: {settings.seed_audio_base_url}")

    gateway = SeedSpeechGateway(
        api_key=settings.seed_audio_api_key,
        base_url=settings.seed_audio_base_url,
    )
    service = SeedAudioService(gateway=gateway)

    request = SeedAudioProviderRequest(
        model="seed-audio-1.0",
        text_prompt="Hello, this is a test.",
    )
    print(f"Request model: {request.model}")
    print(f"Request text_prompt length: {len(request.text_prompt)}")

    try:
        response, log_id = await service.generate(request)
        print(f"✓ Log ID: {log_id}")
        print(f"✓ Code: {response.code}")
        print(f"✓ Message: {response.message}")
        print(f"✓ Duration: {response.duration}")
        print(f"✓ Billing duration: {response.original_duration}")
        print(f"✓ Has audio data: {bool(response.audio)}")
        print(f"✓ Has URL: {bool(response.url)}")
        print(f"✓ Has subtitle: {response.subtitle is not None}")
        return True
    except Exception as exc:
        print(f"✗ FAILED: {exc}")
        traceback.print_exc()
        return False
    finally:
        await service.close()


async def main() -> int:
    print("=" * 60)
    print("Phase 0: Account and Contract Verification")
    print("=" * 60)

    settings = get_settings()
    print(f"\nModelArk base URL: {settings.modelark_base_url}")
    print(f"Seed Audio base URL: {settings.seed_audio_base_url}")
    print(f"ModelArk key present: {settings.has_modelark}")
    print(f"Seed Audio key present: {settings.has_seed_audio}")

    if not settings.has_modelark:
        print("\n✗ BYTEPLUS_MODELARK_API_KEY not set. Skipping ModelArk tests.")
    if not settings.has_seed_audio:
        print("\n✗ BYTEPLUS_SEED_AUDIO_API_KEY not set. Skipping Seed Audio test.")

    results: list[tuple[str, bool]] = []

    if settings.has_modelark:
        results.append(("Seedream", await verify_seedream()))
        results.append(("Seedance", await verify_seedance()))
    if settings.has_seed_audio:
        results.append(("Seed Audio", await verify_seed_audio()))

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    for name, ok in results:
        status = "✓ PASS" if ok else "✗ FAIL"
        print(f"  {name}: {status}")

    return 0 if all(ok for _, ok in results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
