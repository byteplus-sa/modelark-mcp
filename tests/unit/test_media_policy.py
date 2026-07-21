"""Unit tests for media policy (MIME and size validation)."""

from __future__ import annotations

import base64

import pytest

from modelark_mcp.security.media_policy import (
    MediaValidationError,
    check_base64_size,
    decode_base64_safely,
    validate_audio_mime,
    validate_image_mime,
    validate_video_mime,
)


class TestMimeValidation:
    """Tests for MIME type validation."""

    def test_valid_audio_mime_wav(self) -> None:
        validate_audio_mime("audio/wav")

    def test_valid_audio_mime_mp3(self) -> None:
        validate_audio_mime("audio/mp3")

    def test_invalid_audio_mime_rejected(self) -> None:
        with pytest.raises(MediaValidationError, match="not allowed"):
            validate_audio_mime("audio/flac")

    def test_valid_image_mime_png(self) -> None:
        validate_image_mime("image/png")

    def test_valid_image_mime_jpeg(self) -> None:
        validate_image_mime("image/jpeg")

    def test_invalid_image_mime_rejected(self) -> None:
        with pytest.raises(MediaValidationError, match="not allowed"):
            validate_image_mime("image/gif")

    def test_valid_video_mime_mp4(self) -> None:
        validate_video_mime("video/mp4")

    def test_invalid_video_mime_rejected(self) -> None:
        with pytest.raises(MediaValidationError, match="not allowed"):
            validate_video_mime("video/avi")

    def test_none_mime_passes(self) -> None:
        validate_audio_mime(None)
        validate_image_mime(None)
        validate_video_mime(None)

    def test_mime_with_parameters_stripped(self) -> None:
        validate_audio_mime("audio/wav;rate=44100")


class TestBase64SizeCheck:
    """Tests for Base64 size estimation."""

    def test_small_data_passes(self) -> None:
        data = base64.b64encode(b"hello").decode()
        size = check_base64_size(data, max_bytes=1024)
        assert size == 5  # "hello" is 5 bytes

    def test_large_data_rejected(self) -> None:
        raw = b"x" * 2048
        data = base64.b64encode(raw).decode()
        with pytest.raises(MediaValidationError, match="exceeds limit"):
            check_base64_size(data, max_bytes=1024)

    def test_decode_safely_returns_bytes(self) -> None:
        raw = b"hello world"
        data = base64.b64encode(raw).decode()
        decoded = decode_base64_safely(data, max_bytes=1024)
        assert decoded == raw

    def test_decode_invalid_base64_rejected(self) -> None:
        with pytest.raises(MediaValidationError, match="Invalid Base64"):
            decode_base64_safely("not-valid-base64!!!", max_bytes=1024)
