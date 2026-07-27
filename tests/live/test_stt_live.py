"""Live test for speech_to_text with a real sample file.

Requires a valid SEED_SPEECH_ASR_API_KEY in .env and an audio file
at sample/mix_s01_v03.wav. Uses the FastMCP in-memory client transport.

Run with:
    uv run pytest tests/live/test_stt_live.py -v -s --force-enable-socket
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastmcp import Client

from modelark_mcp.config.env import get_settings

SAMPLE_WAV = Path(__file__).resolve().parents[2] / "sample" / "mix_s01_v03.wav"


@pytest.fixture
def live_server(monkeypatch: pytest.MonkeyPatch) -> object:
    """Create a server reading real .env credentials."""
    from modelark_mcp.server import create_server

    get_settings.cache_clear()
    yield SimpleNamespace(mcp=create_server(get_settings()))
    get_settings.cache_clear()


class TestSpeechToTextLive:
    async def test_transcribe_sample_wav(self, live_server: object, socket_enabled: None) -> None:
        if not SAMPLE_WAV.is_file():
            pytest.skip(f"Sample audio not found: {SAMPLE_WAV}")

        mcp = live_server.mcp

        async with Client(mcp) as client:
            result = await client.call_tool(
                "speech_to_text",
                {
                    "input": {
                        "audio": {
                            "audio_file_path": str(SAMPLE_WAV),
                            "audio_format": "wav",
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

        print("\n=== Transcription Result ===")
        print(f"Text: {text}")
        print(f"Utterances: {len(utterances)}")
        for i, u in enumerate(utterances):
            print(f"\n  Utterance {i}: {u['text']}")
            print(f"    Time: {u.get('start_time_ms')}-{u.get('end_time_ms')}ms")
            words = u.get("words", [])
            if words:
                print(f"    Words: {len(words)}")
                for w in words[:5]:
                    print(f"      '{w['text']}' ({w.get('confidence', 'N/A')})")
                if len(words) > 5:
                    print(f"      ... and {len(words) - 5} more")

        assert len(text) > 0, "Expected non-empty transcription"
