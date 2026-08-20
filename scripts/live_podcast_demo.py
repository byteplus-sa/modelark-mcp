"""Live Seed Audio podcast demo — 2-host Filipino podcast on Pax Silica.

Generates a ~60-second conversational podcast with a male and female Filipino
host discussing the Philippines' Pax Silica initiative, using only verified
publicly-reported facts. Run:

    uv run python scripts/live_podcast_demo.py
"""

from __future__ import annotations

import asyncio
import base64
from pathlib import Path

from fastmcp import Client

from modelark_mcp.config.env import get_settings
from modelark_mcp.config.model_capabilities import refresh_capability_registry

OUTFILE = Path("out/pax_silica_podcast.mp3")

PODCAST_PROMPT = (
    "In a casual podcast studio with soft ambient background music and a "
    "relaxed, warm atmosphere. Two Filipino hosts are recording an episode. "
    "The male host (warm baritone, Filipino English accent, relaxed and "
    "conversational, friendly and engaging) speaks first in a welcoming tone: "
    '"Welcome back to the show! So, have you been following this Pax Silica '
    'development?" '
    "The female host (bright and articulate, Filipino English accent, warm and "
    "enthusiastic, slightly more animated) responds: "
    '"Oh yeah, it is a big deal. It is a US-led coalition to secure supply '
    "chains for semiconductors, AI, and critical minerals. They launched it "
    'back in December twenty twenty-five in Washington." '
    "Male host nods and continues: "
    '"Right. And the Philippines officially joined in April twenty twenty-six '
    "as the thirteenth signatory. Trade Undersecretary Ceferino Rodolfo signed "
    'the declaration." '
    "Female host adds with interest: "
    '"The headline is the site — a four-thousand-acre zone in New Clark City, '
    "Tarlac. They are calling it the first AI-native industrial acceleration "
    'hub." '
    "Male host: "
    '"BCDA says it could generate over one hundred thirty thousand high-quality '
    "jobs. Finance Secretary Frederick Go even called it a generational "
    'project." '
    "Female host, now more measured: "
    '"But there is pushback. People are worried about environmental impact, '
    "land use, and whether we will end up in a subordinate role, just exporting "
    'raw materials." '
    "Male host, thoughtfully: "
    '"Exactly. Massive potential, but real questions about sovereignty and who '
    'actually benefits." '
    "Female host, wrapping up: "
    '"Definitely one to watch closely."'
)


async def main() -> None:
    settings = get_settings()
    if not settings.has_seed_audio:
        raise SystemExit("BYTEPLUS_SEED_SPEECH_API_KEY is not configured in .env")

    refresh_capability_registry()

    from modelark_mcp.server import create_server

    mcp = create_server(settings)
    OUTFILE.parent.mkdir(parents=True, exist_ok=True)

    print(f"Prompt length: {len(PODCAST_PROMPT)} chars (max 3000)")
    print("Calling seed_audio_generate...\n")

    async with Client(mcp) as client:
        result = await client.call_tool(
            "seed_audio_generate",
            {
                "input": {
                    "text_prompt": PODCAST_PROMPT,
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

    async with Client(mcp) as client:
        content = await client.read_resource(artifact_uri)

    blob = content[0].blob
    audio_bytes = base64.b64decode(blob) if isinstance(blob, str) else blob
    OUTFILE.write_bytes(audio_bytes)
    print(f"\nSaved audio to {OUTFILE.resolve()} ({len(audio_bytes):,} bytes)")


if __name__ == "__main__":
    asyncio.run(main())
