"""Unit tests for environment configuration."""

from __future__ import annotations

import pytest

from modelark_mcp.config.env import Settings


class TestSettings:
    """Tests for the Settings model."""

    def test_defaults(self) -> None:
        settings = Settings()
        assert settings.modelark_base_url == "https://ark.ap-southeast.bytepluses.com/api/v3"
        assert settings.seed_audio_base_url == "https://voice.ap-southeast-1.bytepluses.com"
        assert settings.mcp_transport == "stdio"
        assert settings.mcp_host == "127.0.0.1"
        assert settings.mcp_port == 3000
        assert settings.artifact_backend == "filesystem"
        assert settings.artifact_ttl_seconds == 604800
        assert settings.mcp_inline_media_max_bytes == 8388608

    def test_has_modelark_false_when_empty(self) -> None:
        settings = Settings(_env_file=None)
        assert not settings.has_modelark

    def test_has_modelark_true_when_set(self) -> None:
        settings = Settings(_env_file=None, BYTEPLUS_MODELARK_API_KEY="sk-test")
        assert settings.has_modelark

    def test_has_seed_audio_false_when_empty(self) -> None:
        settings = Settings(_env_file=None)
        assert not settings.has_seed_audio

    def test_has_seed_audio_true_when_set(self) -> None:
        settings = Settings(_env_file=None, BYTEPLUS_SEED_AUDIO_API_KEY="sk-test")
        assert settings.has_seed_audio

    def test_allowed_origins_empty(self) -> None:
        settings = Settings(_env_file=None)
        assert settings.allowed_origins == []

    def test_allowed_origins_parsed(self) -> None:
        settings = Settings(_env_file=None, MCP_ALLOWED_ORIGINS="https://a.com,https://b.com")
        assert settings.allowed_origins == ["https://a.com", "https://b.com"]

    def test_invalid_transport_raises(self) -> None:
        with pytest.raises(ValueError):
            Settings(_env_file=None, MCP_TRANSPORT="invalid")

    def test_non_loopback_http_requires_jwt(self) -> None:
        with pytest.raises(ValueError, match="requires MCP_AUTH_MODE=jwt"):
            Settings(_env_file=None, MCP_TRANSPORT="http", MCP_HOST="0.0.0.0")

    def test_jwt_requires_verifier_configuration(self) -> None:
        with pytest.raises(ValueError, match="JWT auth requires"):
            Settings(_env_file=None, MCP_AUTH_MODE="jwt")

    def test_timeout_defaults(self) -> None:
        settings = Settings(_env_file=None)
        assert settings.connect_timeout_ms == 10000
        assert settings.request_timeout_ms == 600000

    def test_model_bindings(self) -> None:
        settings = Settings(
            _env_file=None,
            SEEDREAM_DEFAULT_MODEL="custom-model",
            SEEDANCE_DEFAULT_MODEL="custom-video",
            SEEDREAM_MODEL_FAMILY="lite",
            SEEDANCE_MODEL_FAMILY="fast",
        )
        assert settings.seedream_default_model == "custom-model"
        assert settings.seedance_default_model == "custom-video"

    def test_custom_model_requires_explicit_family(self) -> None:
        with pytest.raises(ValueError, match="custom SEEDREAM_DEFAULT_MODEL"):
            Settings(_env_file=None, SEEDREAM_DEFAULT_MODEL="custom-model")

    def test_json_model_bindings_are_explicit(self) -> None:
        settings = Settings(
            _env_file=None,
            SEEDREAM_DEFAULT_MODEL="image-a",
            SEEDREAM_MODEL_BINDINGS=[{"model_id": "image-a", "family": "4x"}],
            SEEDANCE_DEFAULT_MODEL="video-a",
            SEEDANCE_MODEL_BINDINGS=[{"model_id": "video-a", "family": "mini"}],
        )
        assert settings.seedream_model_bindings[0].family == "4x"
        assert settings.seedance_model_bindings[0].family == "mini"
