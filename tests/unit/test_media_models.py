"""Unit tests for Pydantic model validators in the domain layer."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from modelark_mcp.domain.media import AudioReference, MediaSource, MediaSourceKind


class TestMediaSource:
    """Tests for the MediaSource model."""

    def test_url_source_valid(self) -> None:
        src = MediaSource(kind=MediaSourceKind.url, url="https://example.com/img.png")
        assert src.kind == MediaSourceKind.url
        assert src.url == "https://example.com/img.png"

    def test_base64_source_valid(self) -> None:
        src = MediaSource(kind=MediaSourceKind.base64, data="aGVsbG8=")
        assert src.kind == MediaSourceKind.base64
        assert src.data == "aGVsbG8="

    def test_media_category_is_not_client_input(self) -> None:
        schema = MediaSource.model_json_schema()
        assert "media_category" not in schema["properties"]

    def test_url_source_missing_url_raises(self) -> None:
        with pytest.raises(ValidationError, match="url is required"):
            MediaSource(kind=MediaSourceKind.url)

    def test_base64_source_missing_data_raises(self) -> None:
        with pytest.raises(ValidationError, match="data is required"):
            MediaSource(kind=MediaSourceKind.base64)

    def test_url_source_with_data_raises(self) -> None:
        with pytest.raises(ValidationError, match="data must not be set"):
            MediaSource(kind=MediaSourceKind.url, url="https://example.com/img.png", data="aGk=")

    def test_base64_source_with_url_raises(self) -> None:
        with pytest.raises(ValidationError, match="url must not be set"):
            MediaSource(
                kind=MediaSourceKind.base64,
                data="aGk=",
                url="https://example.com/img.png",
            )


class TestAudioReference:
    """Tests for the AudioReference model."""

    def test_speaker_valid(self) -> None:
        ref = AudioReference(kind="speaker", speaker_id="voice_001")
        assert ref.kind == "speaker"
        assert ref.speaker_id == "voice_001"

    def test_url_valid(self) -> None:
        ref = AudioReference(kind="url", url="https://example.com/audio.wav")
        assert ref.kind == "url"
        assert ref.url == "https://example.com/audio.wav"

    def test_base64_valid(self) -> None:
        ref = AudioReference(kind="base64", data="aGVsbG8=")
        assert ref.kind == "base64"
        assert ref.data == "aGVsbG8="

    def test_speaker_missing_id_raises(self) -> None:
        with pytest.raises(ValidationError, match="speaker_id is required"):
            AudioReference(kind="speaker")

    def test_speaker_with_url_raises(self) -> None:
        with pytest.raises(ValidationError, match="url/data must not be set"):
            AudioReference(kind="speaker", speaker_id="v1", url="https://x.com/a.wav")

    def test_url_with_speaker_raises(self) -> None:
        with pytest.raises(ValidationError, match="speaker_id/data must not be set"):
            AudioReference(kind="url", url="https://x.com/a.wav", speaker_id="v1")
