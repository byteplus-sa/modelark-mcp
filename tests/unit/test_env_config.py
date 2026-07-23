"""Unit tests for validate() and get_settings() in environment configuration."""

from __future__ import annotations

import pytest

from modelark_mcp.config.env import Settings, get_settings, validate


@pytest.fixture
def clean_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BYTEPLUS_MODELARK_API_KEY", "sk-test-modelark")
    monkeypatch.setenv("BYTEPLUS_SEED_AUDIO_API_KEY", "sk-test-speech")
    monkeypatch.setenv("BYTEPLUS_MODELARK_BASE_URL", "https://ark.test.example.com/api/v3")
    monkeypatch.setenv("BYTEPLUS_SEED_AUDIO_BASE_URL", "https://voice.test.example.com")
    monkeypatch.setenv("ARTIFACT_TTL_SECONDS", "3600")
    monkeypatch.setenv("MCP_INLINE_MEDIA_MAX_BYTES", "8388608")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class TestValidate:
    """Tests for the validate() function."""

    def test_validate_passes_with_https_urls(self, clean_settings: None) -> None:
        validate()

    def test_validate_passes_with_default_urls(self, monkeypatch: pytest.MonkeyPatch) -> None:
        get_settings.cache_clear()
        monkeypatch.delenv("BYTEPLUS_MODELARK_BASE_URL", raising=False)
        monkeypatch.delenv("BYTEPLUS_SEED_AUDIO_BASE_URL", raising=False)
        validate()
        get_settings.cache_clear()

    def test_validate_rejects_non_https_modelark_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BYTEPLUS_MODELARK_BASE_URL", "http://ark.example.com/api/v3")
        monkeypatch.setenv("BYTEPLUS_SEED_AUDIO_BASE_URL", "https://voice.example.com")
        monkeypatch.setenv("ARTIFACT_TTL_SECONDS", "3600")
        monkeypatch.setenv("MCP_INLINE_MEDIA_MAX_BYTES", "8388608")
        get_settings.cache_clear()
        with pytest.raises(ValueError, match="BYTEPLUS_MODELARK_BASE_URL must use HTTPS"):
            validate()
        get_settings.cache_clear()

    def test_validate_rejects_non_https_seed_audio_url(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("BYTEPLUS_MODELARK_BASE_URL", "https://ark.example.com/api/v3")
        monkeypatch.setenv("BYTEPLUS_SEED_AUDIO_BASE_URL", "http://voice.example.com")
        monkeypatch.setenv("ARTIFACT_TTL_SECONDS", "3600")
        monkeypatch.setenv("MCP_INLINE_MEDIA_MAX_BYTES", "8388608")
        get_settings.cache_clear()
        with pytest.raises(ValueError, match="BYTEPLUS_SEED_AUDIO_BASE_URL must use HTTPS"):
            validate()
        get_settings.cache_clear()

    def test_validate_rejects_zero_ttl(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BYTEPLUS_MODELARK_BASE_URL", "https://ark.example.com/api/v3")
        monkeypatch.setenv("BYTEPLUS_SEED_AUDIO_BASE_URL", "https://voice.example.com")
        monkeypatch.setenv("ARTIFACT_TTL_SECONDS", "0")
        monkeypatch.setenv("MCP_INLINE_MEDIA_MAX_BYTES", "8388608")
        get_settings.cache_clear()
        with pytest.raises(ValueError, match="ARTIFACT_TTL_SECONDS must be positive"):
            validate()
        get_settings.cache_clear()

    def test_validate_rejects_negative_ttl(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BYTEPLUS_MODELARK_BASE_URL", "https://ark.example.com/api/v3")
        monkeypatch.setenv("BYTEPLUS_SEED_AUDIO_BASE_URL", "https://voice.example.com")
        monkeypatch.setenv("ARTIFACT_TTL_SECONDS", "-1")
        monkeypatch.setenv("MCP_INLINE_MEDIA_MAX_BYTES", "8388608")
        get_settings.cache_clear()
        with pytest.raises(ValueError, match="ARTIFACT_TTL_SECONDS must be positive"):
            validate()
        get_settings.cache_clear()

    def test_validate_rejects_zero_media_max_bytes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BYTEPLUS_MODELARK_BASE_URL", "https://ark.example.com/api/v3")
        monkeypatch.setenv("BYTEPLUS_SEED_AUDIO_BASE_URL", "https://voice.example.com")
        monkeypatch.setenv("ARTIFACT_TTL_SECONDS", "3600")
        monkeypatch.setenv("MCP_INLINE_MEDIA_MAX_BYTES", "0")
        get_settings.cache_clear()
        with pytest.raises(ValueError, match="MCP_INLINE_MEDIA_MAX_BYTES must be positive"):
            validate()
        get_settings.cache_clear()

    def test_validate_rejects_negative_media_max_bytes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("BYTEPLUS_MODELARK_BASE_URL", "https://ark.example.com/api/v3")
        monkeypatch.setenv("BYTEPLUS_SEED_AUDIO_BASE_URL", "https://voice.example.com")
        monkeypatch.setenv("ARTIFACT_TTL_SECONDS", "3600")
        monkeypatch.setenv("MCP_INLINE_MEDIA_MAX_BYTES", "-100")
        get_settings.cache_clear()
        with pytest.raises(ValueError, match="MCP_INLINE_MEDIA_MAX_BYTES must be positive"):
            validate()
        get_settings.cache_clear()


class TestGetSettingsCaching:
    """Tests for get_settings() lru_cache behavior."""

    def test_returns_same_instance(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BYTEPLUS_MODELARK_API_KEY", "sk-test")
        get_settings.cache_clear()
        first = get_settings()
        second = get_settings()
        assert first is second
        get_settings.cache_clear()

    def test_returns_new_instance_after_cache_clear(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BYTEPLUS_MODELARK_API_KEY", "sk-test-1")
        get_settings.cache_clear()
        first = get_settings()
        get_settings.cache_clear()
        monkeypatch.setenv("BYTEPLUS_MODELARK_API_KEY", "sk-test-2")
        second = get_settings()
        assert first is not second
        assert first.modelark_api_key == "sk-test-1"  # pragma: allowlist secret
        assert second.modelark_api_key == "sk-test-2"  # pragma: allowlist secret
        get_settings.cache_clear()

    def test_cache_returns_same_instance_even_after_env_change(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("BYTEPLUS_MODELARK_API_KEY", "sk-test-1")
        get_settings.cache_clear()
        first = get_settings()
        monkeypatch.setenv("BYTEPLUS_MODELARK_API_KEY", "sk-test-2")
        second = get_settings()
        assert first is second
        get_settings.cache_clear()


class TestSettingsFromEnv:
    """Tests for Settings loading from environment variables."""

    def test_api_key_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BYTEPLUS_MODELARK_API_KEY", "sk-from-env")
        settings = Settings(_env_file=None)
        assert settings.modelark_api_key == "sk-from-env"  # pragma: allowlist secret

    def test_seed_audio_api_key_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BYTEPLUS_SEED_AUDIO_API_KEY", "sk-audio-env")
        settings = Settings(_env_file=None)
        assert settings.seed_audio_api_key == "sk-audio-env"  # pragma: allowlist secret

    def test_transport_http_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_TRANSPORT", "http")
        settings = Settings(_env_file=None)
        assert settings.mcp_transport == "http"

    def test_transport_stdio_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_TRANSPORT", "stdio")
        settings = Settings(_env_file=None)
        assert settings.mcp_transport == "stdio"

    def test_port_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_PORT", "8080")
        settings = Settings(_env_file=None)
        assert settings.mcp_port == 8080

    def test_host_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_HOST", "0.0.0.0")
        settings = Settings(_env_file=None)
        assert settings.mcp_host == "0.0.0.0"

    def test_fastmcp_alias_for_transport(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FASTMCP_TRANSPORT", "http")
        settings = Settings(_env_file=None)
        assert settings.mcp_transport == "http"

    def test_fastmcp_alias_for_host(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FASTMCP_HOST", "192.168.1.1")
        settings = Settings(_env_file=None)
        assert settings.mcp_host == "192.168.1.1"

    def test_fastmcp_alias_for_port(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FASTMCP_PORT", "9000")
        settings = Settings(_env_file=None)
        assert settings.mcp_port == 9000

    def test_allowed_origins_with_whitespace(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_ALLOWED_ORIGINS", " https://a.com , https://b.com ")
        settings = Settings(_env_file=None)
        assert settings.allowed_origins == ["https://a.com", "https://b.com"]

    def test_allowed_origins_single_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_ALLOWED_ORIGINS", "https://only.com")
        settings = Settings(_env_file=None)
        assert settings.allowed_origins == ["https://only.com"]

    def test_artifact_dir_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ARTIFACT_DIR", "/tmp/custom-artifacts")
        settings = Settings(_env_file=None)
        assert settings.artifact_dir == "/tmp/custom-artifacts"

    def test_connect_timeout_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BYTEPLUS_CONNECT_TIMEOUT_MS", "5000")
        settings = Settings(_env_file=None)
        assert settings.connect_timeout_ms == 5000

    def test_request_timeout_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BYTEPLUS_REQUEST_TIMEOUT_MS", "60000")
        settings = Settings(_env_file=None)
        assert settings.request_timeout_ms == 60000

    def test_base_url_overrides_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BYTEPLUS_MODELARK_BASE_URL", "https://custom.ark.com/api/v3")
        settings = Settings(_env_file=None)
        assert settings.modelark_base_url == "https://custom.ark.com/api/v3"
