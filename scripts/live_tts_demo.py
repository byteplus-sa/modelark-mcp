"""Live Seed Audio (TTS) smoke test through the full MCP protocol surface.

Connects the FastMCP in-memory client to a real server instance reading
credentials from .env, calls ``seed_audio_generate``, persists the audio
artifact, and writes it to disk so the output can be played back.

Run:
    uv run python scripts/live_tts_demo.py
"""

from __future__ import annotations

import asyncio
import base64
from pathlib import Path

from fastmcp import Client

from modelark_mcp.config.env import get_settings
from modelark_mcp.config.model_capabilities import refresh_capability_registry

OUTFILE = Path("out/live_tts_demo.mp3")

TLDR_PROMPT = (
    "Here is a thirty-second TLDR on the Philippines' upcoming Pax Silica "
    "Project. Pax Silica is an emerging initiative focused on developing "
    "the country's silica resources and domestic processing capabilities. "
    "It aims to create jobs, attract investment, and strengthen the "
    "Philippines' position in the global silica supply chain. The project "
    "is expected to support local manufacturing and technology industries. "
    "Watch this space as more details are announced."
)


async def main() -> None:
    settings = get_settings()
    if not settings.has_seed_audio:
        raise SystemExit("BYTEPLUS_SEED_AUDIO_API_KEY is not configured in .env")

    refresh_capability_registry()

    from modelark_mcp.server import create_server

    mcp = create_server(settings)
    OUTFILE.parent.mkdir(parents=True, exist_ok=True)

    async with Client(mcp) as client:
        result = await client.call_tool(
            "seed_audio_generate",
            {
                "input": {
                    "text_prompt": TLDR_PROMPT,
                    "output": {"format": "mp3", "sample_rate": 48000},
                    "watermark": {},
                    "persist": True,
                }
            },
        )

    if result.is_error:
        raise SystemExit(f"Tool returned an error: {result.content[0].text}")

    data = result.structured_content
    provider = str(data.get("provider", ""))
    model_name = str(data.get("model", ""))
    duration = float(data.get("duration_seconds", 0))
    artifact = data.get("artifact", {})
    artifact_uri = str(artifact.get("uri", ""))
    artifact_media_type = str(artifact.get("media_type", ""))
    artifact_bytes = int(artifact.get("bytes", 0))
    print("=== seed_audio_generate result ===")
    print(f"provider           : {provider}")
    print(f"model              : {model_name}")
    print(f"duration_seconds   : {duration}")
    print(f"artifact.uri       : {artifact_uri}")
    print(f"artifact.media_type: {artifact_media_type}")
    print(f"artifact.bytes     : {artifact_bytes}")

    # Fetch the persisted bytes via the MCP resource and write to disk.
    async with Client(mcp) as client:
        content = await client.read_resource(artifact_uri)

    blob = content[0].blob
    audio_bytes = base64.b64decode(blob) if isinstance(blob, str) else blob
    OUTFILE.write_bytes(audio_bytes)
    print(f"\nSaved audio to {OUTFILE.resolve()} ({len(audio_bytes):,} bytes)")


if __name__ == "__main__":
    asyncio.run(main())
