"""Environment configuration for the ModelArk Seed MCP server.

Loads custom environment variables (provider credentials, model bindings,
artifact storage, transport settings) via Pydantic Settings. FastMCP's own
settings (log level, etc.) are handled separately by FastMCP.

Provider credentials are startup configuration only and never tool arguments.
If a credential is absent, the server must not register that product's tool set.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment / .env file.

    Uses ``validation_alias`` (not ``alias``) for environment variable name
    overrides so that field names are preserved for serialization and code
    access. See https://pydantic.dev/docs/validation/latest/concepts/pydantic_settings/.

    ``secrets_dir`` points to ``/run/secrets`` (Docker / Kubernetes) and
    emits a warning when the directory does not exist. Individual fields can
    also be overridden by placing a file named after the field (or its
    validation alias) in the secrets directory.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        validate_default=True,
        secrets_dir="/run/secrets",
    )

    # --- Provider credentials ------------------------------------------------

    modelark_api_key: str = Field(default="", validation_alias="BYTEPLUS_MODELARK_API_KEY")
    seed_audio_api_key: str = Field(default="", validation_alias="BYTEPLUS_SEED_AUDIO_API_KEY")

    # --- Provider base URLs --------------------------------------------------

    modelark_base_url: str = Field(
        default="https://ark.ap-southeast.bytepluses.com/api/v3",
        validation_alias="BYTEPLUS_MODELARK_BASE_URL",
    )
    seed_audio_base_url: str = Field(
        default="https://voice.ap-southeast-1.bytepluses.com",
        validation_alias="BYTEPLUS_SEED_AUDIO_BASE_URL",
    )

    # --- Model bindings ------------------------------------------------------

    seedream_default_model: str = Field(
        default="dola-seedream-5-0-pro-260628",
        validation_alias="SEEDREAM_DEFAULT_MODEL",
    )
    seedance_default_model: str = Field(
        default="dreamina-seedance-2-0-260128",
        validation_alias="SEEDANCE_DEFAULT_MODEL",
    )

    # --- MCP transport -------------------------------------------------------

    mcp_transport: str = Field(
        default="stdio",
        validation_alias=AliasChoices("MCP_TRANSPORT", "FASTMCP_TRANSPORT"),
    )
    mcp_host: str = Field(
        default="127.0.0.1",
        validation_alias=AliasChoices("MCP_HOST", "FASTMCP_HOST"),
    )
    mcp_port: int = Field(
        default=3000,
        validation_alias=AliasChoices("MCP_PORT", "FASTMCP_PORT"),
    )
    mcp_allowed_origins: str = Field(default="", validation_alias="MCP_ALLOWED_ORIGINS")

    # --- Artifact persistence ------------------------------------------------

    artifact_backend: str = Field(default="filesystem", validation_alias="ARTIFACT_BACKEND")
    artifact_dir: str = Field(default=".artifacts", validation_alias="ARTIFACT_DIR")
    artifact_ttl_seconds: int = Field(default=604800, validation_alias="ARTIFACT_TTL_SECONDS")
    mcp_inline_media_max_bytes: int = Field(
        default=8388608, validation_alias="MCP_INLINE_MEDIA_MAX_BYTES"
    )

    # --- HTTP timeouts (milliseconds) ---------------------------------------

    connect_timeout_ms: int = Field(default=10000, validation_alias="BYTEPLUS_CONNECT_TIMEOUT_MS")
    request_timeout_ms: int = Field(default=300000, validation_alias="BYTEPLUS_REQUEST_TIMEOUT_MS")

    # --- Convenience flags ---------------------------------------------------

    @property
    def has_modelark(self) -> bool:
        """Whether ModelArk credentials are configured (Seedream + Seedance)."""
        return bool(self.modelark_api_key)

    @property
    def has_seed_audio(self) -> bool:
        """Whether Seed Audio credentials are configured."""
        return bool(self.seed_audio_api_key)

    @property
    def allowed_origins(self) -> list[str]:
        """Parse the comma-separated allowed origins list."""
        if not self.mcp_allowed_origins:
            return []
        return [origin.strip() for origin in self.mcp_allowed_origins.split(",") if origin.strip()]

    @field_validator("mcp_transport")
    @classmethod
    def validate_transport(cls, v: str) -> str:
        allowed = {"stdio", "http"}
        if v not in allowed:
            raise ValueError(f"MCP_TRANSPORT must be one of {allowed}, got '{v}'")
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()


def validate() -> None:
    """Validate required environment variables at startup.

    Called by ``make check-env``.  Raises if essential configuration is
    missing or invalid.  Provider credentials are optional (the server
    degrades gracefully by not registering tools for absent credentials),
    but base URLs and model bindings must be syntactically valid.
    """
    settings = get_settings()
    assert settings.modelark_base_url.startswith("https://"), (
        "BYTEPLUS_MODELARK_BASE_URL must use HTTPS"
    )
    assert settings.seed_audio_base_url.startswith("https://"), (
        "BYTEPLUS_SEED_AUDIO_BASE_URL must use HTTPS"
    )
    assert settings.artifact_ttl_seconds > 0, "ARTIFACT_TTL_SECONDS must be positive"
    assert settings.mcp_inline_media_max_bytes > 0, "MCP_INLINE_MEDIA_MAX_BYTES must be positive"
