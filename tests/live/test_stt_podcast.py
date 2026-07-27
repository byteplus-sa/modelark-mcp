"""Live test for speech_to_text with the podcast sample file.

Requires a valid SEED_SPEECH_ASR_API_KEY in .env and an audio file
at out/pax_silica_podcast.mp3. Uses the FastMCP in-memory client transport.

Run with:
    uv run pytest tests/live/test_stt_podcast.py -v -s --force-enable-socket
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastmcp import Client

from modelark_mcp.config.env import get_settings

SAMPLE_MP3 = Path(__file__).resolve().parents[2] / "out" / "pax_silica_podcast.mp3"
OUTPUT_FILE = Path(__file__).resolve().parents[2] / "out" / "pax_silica_podcast_transcription.json"


@pytest.fixture
def live_server(monkeypatch: pytest.MonkeyPatch) -> object:
    """Create a server reading real .env credentials."""
    from modelark_mcp.server import create_server

    get_settings.cache_clear()
    yield SimpleNamespace(mcp=create_server(get_settings()))
    get_settings.cache_clear()


class TestSpeechToTextPodcastLive:
    async def test_transcribe_podcast_mp3(self, live_server: object, socket_enabled: None) -> None:
        if not SAMPLE_MP3.is_file():
            pytest.skip(f"Sample audio not found: {SAMPLE_MP3}")

        mcp = live_server.mcp

        async with Client(mcp) as client:
            result = await client.call_tool(
                "speech_to_text",
                {
                    "input": {
                        "audio": {
                            "audio_file_path": str(SAMPLE_MP3),
                            "audio_format": "mp3",
                        }
                    }
                },
            )

        assert not result.is_error, f"Tool error: {result.content}"
        content = result.structured_content
        assert content is not None, "No structured content returned"

        transcription = content["result"]
        text = transcription.get("text", "")
        utterances = transcription.get("utterances", [])

        print("\n=== Podcast Transcription Result ===")
        print(f"Text length: {len(text)} chars")
        print(f"Utterances: {len(utterances)}")
        for i, u in enumerate(utterances):
            print(f"\n  Utterance {i}: {u['text'][:120]}...")
            print(f"    Time: {u.get('start_time_ms')}-{u.get('end_time_ms')}ms")
            words = u.get("words", [])
            if words:
                print(f"    Words: {len(words)}")

        print("\n=== Full Text (first 500 chars) ===")
        print(text[:500])
        if len(text) > 500:
            print(f"... ({len(text) - 500} more chars)")

        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_FILE.write_text(
            json.dumps(content, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"\n=== Result persisted to {OUTPUT_FILE} ===")

        assert len(text) > 0, "Expected non-empty transcription"
