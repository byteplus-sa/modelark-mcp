"""Unit tests for media policy (MIME, size, and duration validation)."""

from __future__ import annotations

import base64
import struct

import pytest

from modelark_mcp.security.media_policy import (
    MediaValidationError,
    check_audio_duration_from_base64,
    check_base64_size,
    decode_base64_safely,
    validate_audio_mime,
    validate_image_mime,
    validate_video_mime,
)


def _make_wav_bytes(
    duration_seconds: float,
    sample_rate: int = 8000,
    channels: int = 1,
    bits_per_sample: int = 16,
) -> bytes:
    """Build a minimal PCM WAV file with the given duration."""
    byte_rate = sample_rate * channels * bits_per_sample // 8
    block_align = channels * bits_per_sample // 8
    num_frames = int(duration_seconds * sample_rate)
    data_size = num_frames * block_align

    header = b"RIFF"
    header += struct.pack("<I", 36 + data_size)
    header += b"WAVE"
    header += b"fmt "
    header += struct.pack("<I", 16)
    header += struct.pack("<H", 1)
    header += struct.pack("<H", channels)
    header += struct.pack("<I", sample_rate)
    header += struct.pack("<I", byte_rate)
    header += struct.pack("<H", block_align)
    header += struct.pack("<H", bits_per_sample)
    header += b"data"
    header += struct.pack("<I", data_size)
    header += b"\x00" * data_size
    return header


def _make_wav_base64(duration_seconds: float, **kwargs: int) -> str:
    return base64.b64encode(_make_wav_bytes(duration_seconds, **kwargs)).decode()


class TestMimeValidation:
    """Tests for MIME type validation."""

    def test_valid_audio_mime_wav(self) -> None:
        validate_audio_mime("audio/wav")

    def test_valid_audio_mime_mp3(self) -> None:
        validate_audio_mime("audio/mp3")

    def test_invalid_audio_mime_rejected(self) -> None:
        with pytest.raises(MediaValidationError, match="not allowed"):
            validate_audio_mime("audio/aiff")

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


class TestAudioDurationCheck:
    """Tests for WAV duration preflight via check_audio_duration_from_base64."""

    def test_short_wav_passes(self) -> None:
        data = _make_wav_base64(5.0)
        duration = check_audio_duration_from_base64(data, max_seconds=30)
        assert duration is not None
        assert 4.9 <= duration <= 5.1

    def test_exactly_at_limit_passes(self) -> None:
        data = _make_wav_base64(30.0)
        duration = check_audio_duration_from_base64(data, max_seconds=30)
        assert duration is not None
        assert 29.9 <= duration <= 30.1

    def test_over_limit_rejected(self) -> None:
        data = _make_wav_base64(35.0)
        with pytest.raises(MediaValidationError, match=r"duration.*exceeds limit"):
            check_audio_duration_from_base64(data, max_seconds=30)

    def test_non_wav_returns_none(self) -> None:
        raw = b"ID3\x03\x00" + b"\x00" * 200
        data = base64.b64encode(raw).decode()
        duration = check_audio_duration_from_base64(data, max_seconds=30)
        assert duration is None

    def test_random_bytes_returns_none(self) -> None:
        raw = b"\x00" * 100
        data = base64.b64encode(raw).decode()
        duration = check_audio_duration_from_base64(data, max_seconds=30)
        assert duration is None

    def test_truncated_wav_returns_none(self) -> None:
        raw = b"RIFF\x00\x00\x00\x00WAVE"
        data = base64.b64encode(raw).decode()
        duration = check_audio_duration_from_base64(data, max_seconds=30)
        assert duration is None

    def test_invalid_base64_rejected(self) -> None:
        with pytest.raises(MediaValidationError, match="Invalid Base64"):
            check_audio_duration_from_base64("not-base64!!!", max_seconds=30)

    def test_stereo_wav_duration_correct(self) -> None:
        data = _make_wav_base64(10.0, channels=2)
        duration = check_audio_duration_from_base64(data, max_seconds=30)
        assert duration is not None
        assert 9.9 <= duration <= 10.1
