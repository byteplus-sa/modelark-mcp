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


class TestS3Config:
    """Tests for S3 object storage configuration."""

    def test_has_s3_false_when_empty(self) -> None:
        settings = Settings(_env_file=None)
        assert not settings.has_s3

    def test_has_s3_true_when_set(self) -> None:
        settings = Settings(
            _env_file=None,
            S3_ACCESS_KEY="ak-test",
            S3_SECRET_KEY="sk-test",  # pragma: allowlist secret
            S3_BUCKET="test-bucket",
            OBJECT_STORAGE_BACKEND="s3",
        )
        assert settings.has_s3

    def test_object_storage_backend_defaults_to_tos(self) -> None:
        settings = Settings(_env_file=None)
        assert settings.object_storage_backend == "tos"

    def test_has_object_storage_reflects_selected_backend(self) -> None:
        settings = Settings(
            _env_file=None,
            S3_ACCESS_KEY="ak",
            S3_SECRET_KEY="sk",  # pragma: allowlist secret
            S3_BUCKET="bucket",
            OBJECT_STORAGE_BACKEND="s3",
        )
        assert settings.has_object_storage is True

        settings_tos = Settings(
            _env_file=None,
            TOS_ACCESS_KEY="ak",
            TOS_SECRET_KEY="sk",  # pragma: allowlist secret
            TOS_BUCKET="bucket",
            TOS_ENDPOINT="tos-test.example.com",
        )
        assert settings_tos.has_object_storage is True

    def test_presign_ttl_seconds_returns_selected_backend_ttl(self) -> None:
        settings = Settings(
            _env_file=None,
            S3_ACCESS_KEY="ak",
            S3_SECRET_KEY="sk",  # pragma: allowlist secret
            S3_BUCKET="bucket",
            S3_PRESIGN_TTL_SECONDS=3600,
            OBJECT_STORAGE_BACKEND="s3",
        )
        assert settings.presign_ttl_seconds == 3600

    def test_s3_ak_sk_must_both_be_set(self) -> None:
        with pytest.raises(ValueError, match="S3_ACCESS_KEY and S3_SECRET_KEY"):
            Settings(_env_file=None, S3_ACCESS_KEY="ak")

    def test_backend_s3_requires_credentials(self) -> None:
        with pytest.raises(ValueError, match="OBJECT_STORAGE_BACKEND=s3 requires"):
            Settings(_env_file=None, OBJECT_STORAGE_BACKEND="s3")

    def test_backend_tos_with_s3_creds_missing_tos_raises_guidance(self) -> None:
        with pytest.raises(ValueError, match="OBJECT_STORAGE_BACKEND=tos but TOS credentials"):
            Settings(
                _env_file=None,
                S3_ACCESS_KEY="ak",
                S3_SECRET_KEY="sk",  # pragma: allowlist secret
                S3_BUCKET="bucket",
                OBJECT_STORAGE_BACKEND="tos",
            )
