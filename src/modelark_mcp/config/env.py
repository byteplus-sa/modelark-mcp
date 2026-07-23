"""Environment configuration for the ModelArk Seed MCP server.

Loads custom environment variables (provider credentials, model bindings,
artifact storage, transport settings) via Pydantic Settings. FastMCP's own
settings (log level, etc.) are handled separately by FastMCP.

Provider credentials are startup configuration only and never tool arguments.
If a credential is absent, the server must not register that product's tool set.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import AliasChoices, BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class SeedreamFamily(StrEnum):
    PRO = "pro"
    LITE = "lite"
    V4X = "4x"


class SeedanceFamily(StrEnum):
    STANDARD = "standard"
    FAST = "fast"
    MINI = "mini"


class AuthMode(StrEnum):
    LOCAL = "local"
    JWT = "jwt"


class ImageModelBinding(BaseModel):
    model_id: str = Field(min_length=1)
    family: SeedreamFamily


class VideoModelBinding(BaseModel):
    model_id: str = Field(min_length=1)
    family: SeedanceFamily


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
        secrets_dir="/run/secrets" if Path("/run/secrets").is_dir() else None,
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
    seedream_model_family: str = Field(
        default="",
        validation_alias="SEEDREAM_MODEL_FAMILY",
        description="Explicit family: 'pro', 'lite', or '4x'. Empty = infer from model ID.",
    )
    seedance_model_family: str = Field(
        default="",
        validation_alias="SEEDANCE_MODEL_FAMILY",
        description="Explicit family: 'standard', 'fast', or 'mini'. Empty = infer.",
    )
    seedream_model_bindings: list[ImageModelBinding] = Field(
        default_factory=list,
        validation_alias="SEEDREAM_MODEL_BINDINGS",
    )
    seedance_model_bindings: list[VideoModelBinding] = Field(
        default_factory=list,
        validation_alias="SEEDANCE_MODEL_BINDINGS",
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
        ge=1,
        le=65535,
        validation_alias=AliasChoices("MCP_PORT", "FASTMCP_PORT"),
    )
    mcp_allowed_origins: str = Field(default="", validation_alias="MCP_ALLOWED_ORIGINS")
    mcp_allowed_hosts: str = Field(
        default="127.0.0.1,localhost,[::1]",
        validation_alias="MCP_ALLOWED_HOSTS",
    )
    mcp_auth_mode: AuthMode = Field(default=AuthMode.LOCAL, validation_alias="MCP_AUTH_MODE")
    mcp_jwt_jwks_uri: str | None = Field(default=None, validation_alias="MCP_JWT_JWKS_URI")
    mcp_jwt_issuer: str | None = Field(default=None, validation_alias="MCP_JWT_ISSUER")
    mcp_jwt_audience: str | None = Field(default=None, validation_alias="MCP_JWT_AUDIENCE")
    mcp_tenant_claim: str = Field(
        default="tenant_id",
        min_length=1,
        validation_alias="MCP_TENANT_CLAIM",
    )

    # --- Artifact persistence ------------------------------------------------

    artifact_backend: Literal["filesystem"] = Field(
        default="filesystem", validation_alias="ARTIFACT_BACKEND"
    )
    artifact_dir: str = Field(default=".artifacts", validation_alias="ARTIFACT_DIR")
    artifact_ttl_seconds: int = Field(default=604800, validation_alias="ARTIFACT_TTL_SECONDS")
    mcp_inline_media_max_bytes: int = Field(
        default=8388608, validation_alias="MCP_INLINE_MEDIA_MAX_BYTES"
    )
    mcp_http_max_body_bytes: int = Field(
        default=10_485_760,
        ge=1,
        validation_alias="MCP_HTTP_MAX_BODY_BYTES",
    )

    # --- TOS object storage -------------------------------------------------

    tos_access_key: str = Field(default="", validation_alias="TOS_ACCESS_KEY")
    tos_secret_key: str = Field(default="", validation_alias="TOS_SECRET_KEY")
    tos_security_token: str = Field(default="", validation_alias="TOS_SECURITY_TOKEN")
    tos_bucket: str = Field(default="", validation_alias="TOS_BUCKET")
    tos_region: str = Field(default="ap-southeast-1", validation_alias="TOS_REGION")
    tos_endpoint: str = Field(
        default="tos-ap-southeast-1.bytepluses.com",
        validation_alias="TOS_ENDPOINT",
    )
    tos_presign_ttl_seconds: int = Field(
        default=86400,
        ge=60,
        le=604800,
        validation_alias="TOS_PRESIGN_TTL_SECONDS",
    )

    # --- HTTP timeouts (milliseconds) ---------------------------------------

    connect_timeout_ms: int = Field(default=10000, validation_alias="BYTEPLUS_CONNECT_TIMEOUT_MS")
    request_timeout_ms: int = Field(default=300000, validation_alias="BYTEPLUS_REQUEST_TIMEOUT_MS")

    # --- Runtime policy -----------------------------------------------------

    provider_max_concurrency: int = Field(
        default=5,
        ge=1,
        validation_alias="PROVIDER_MAX_CONCURRENCY",
    )
    principal_max_concurrency: int = Field(
        default=3,
        ge=1,
        validation_alias="PRINCIPAL_MAX_CONCURRENCY",
    )
    daily_budget_usd: float = Field(
        default=0.0,
        ge=0,
        validation_alias="DAILY_BUDGET_USD",
        description="Per-principal UTC daily limit. Zero records usage without blocking.",
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO",
        validation_alias="MODELARK_LOG_LEVEL",
    )

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
    def has_tos(self) -> bool:
        """Whether TOS object storage credentials are configured."""
        return bool(self.tos_access_key and self.tos_secret_key and self.tos_bucket)

    @property
    def allowed_origins(self) -> list[str]:
        """Parse the comma-separated allowed origins list."""
        if not self.mcp_allowed_origins:
            return []
        return [origin.strip() for origin in self.mcp_allowed_origins.split(",") if origin.strip()]

    @property
    def allowed_hosts(self) -> list[str]:
        return [host.strip() for host in self.mcp_allowed_hosts.split(",") if host.strip()]

    @field_validator("mcp_transport")
    @classmethod
    def validate_transport(cls, v: str) -> str:
        allowed = {"stdio", "http"}
        if v not in allowed:
            raise ValueError(f"MCP_TRANSPORT must be one of {allowed}, got '{v}'")
        return v

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value

    @field_validator("modelark_base_url", "seed_audio_base_url")
    @classmethod
    def validate_provider_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.hostname:
            variable = (
                "BYTEPLUS_MODELARK_BASE_URL"
                if "ark" in value.lower()
                else "BYTEPLUS_SEED_AUDIO_BASE_URL"
            )
            raise ValueError(f"{variable} must use HTTPS and include a host")
        if parsed.username or parsed.password:
            raise ValueError("Provider base URLs must not contain credentials")
        return value.rstrip("/")

    @model_validator(mode="after")
    def validate_model_bindings(self) -> Settings:
        """Resolve compatibility settings without model-ID string inference."""
        if not self.seedream_model_bindings:
            family = self.seedream_model_family.strip().lower()
            if not family:
                if self.seedream_default_model == "dola-seedream-5-0-pro-260628":
                    family = SeedreamFamily.PRO
                else:
                    raise ValueError(
                        "A custom SEEDREAM_DEFAULT_MODEL requires "
                        "SEEDREAM_MODEL_FAMILY or SEEDREAM_MODEL_BINDINGS."
                    )
            self.seedream_model_bindings = [
                ImageModelBinding(
                    model_id=self.seedream_default_model,
                    family=SeedreamFamily(family),
                )
            ]

        if not self.seedance_model_bindings:
            family = self.seedance_model_family.strip().lower()
            if not family:
                if self.seedance_default_model == "dreamina-seedance-2-0-260128":
                    family = SeedanceFamily.STANDARD
                else:
                    raise ValueError(
                        "A custom SEEDANCE_DEFAULT_MODEL requires "
                        "SEEDANCE_MODEL_FAMILY or SEEDANCE_MODEL_BINDINGS."
                    )
            self.seedance_model_bindings = [
                VideoModelBinding(
                    model_id=self.seedance_default_model,
                    family=SeedanceFamily(family),
                )
            ]

        for label, bindings, default_model in (
            ("Seedream", self.seedream_model_bindings, self.seedream_default_model),
            ("Seedance", self.seedance_model_bindings, self.seedance_default_model),
        ):
            ids = [binding.model_id for binding in bindings]
            if len(ids) != len(set(ids)):
                raise ValueError(f"{label} model bindings contain duplicate IDs.")
            if default_model not in ids:
                raise ValueError(
                    f"{label} default model '{default_model}' is missing from its bindings."
                )
        if self.artifact_ttl_seconds <= 0:
            raise ValueError("ARTIFACT_TTL_SECONDS must be positive")
        if self.mcp_inline_media_max_bytes <= 0:
            raise ValueError("MCP_INLINE_MEDIA_MAX_BYTES must be positive")
        if self.connect_timeout_ms <= 0 or self.request_timeout_ms <= 0:
            raise ValueError("Provider timeouts must be positive")
        for origin in self.allowed_origins:
            parsed = urlsplit(origin)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                raise ValueError(f"Invalid MCP allowed origin: '{origin}'")
        if self.mcp_auth_mode is AuthMode.JWT:
            missing = [
                name
                for name, value in (
                    ("MCP_JWT_JWKS_URI", self.mcp_jwt_jwks_uri),
                    ("MCP_JWT_ISSUER", self.mcp_jwt_issuer),
                    ("MCP_JWT_AUDIENCE", self.mcp_jwt_audience),
                )
                if not value
            ]
            if missing:
                raise ValueError(f"JWT auth requires: {', '.join(missing)}")
            parsed_jwks = urlsplit(self.mcp_jwt_jwks_uri or "")
            if parsed_jwks.scheme != "https" or not parsed_jwks.hostname:
                raise ValueError("MCP_JWT_JWKS_URI must be an HTTPS URL")
        if (
            self.mcp_transport == "http"
            and self.mcp_auth_mode is AuthMode.LOCAL
            and self.mcp_host not in {"127.0.0.1", "::1", "localhost"}
        ):
            raise ValueError("HTTP on a non-loopback host requires MCP_AUTH_MODE=jwt.")
        if bool(self.tos_access_key) != bool(self.tos_secret_key):
            raise ValueError("TOS_ACCESS_KEY and TOS_SECRET_KEY must both be set or both be empty.")
        if self.tos_access_key and not self.tos_endpoint:
            raise ValueError("TOS_ENDPOINT is required when TOS credentials are set.")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()


def refresh_settings() -> Settings:
    """Force-reload settings from environment (e.g. after config change)."""
    get_settings.cache_clear()
    return get_settings()


def validate() -> None:
    """Validate required environment variables at startup.

    Called by ``make check-env``.  Raises if essential configuration is
    missing or invalid.  Provider credentials are optional (the server
    degrades gracefully by not registering tools for absent credentials),
    but base URLs and model bindings must be syntactically valid.
    """
    settings = get_settings()
    if not settings.modelark_base_url.startswith("https://"):
        raise ValueError("BYTEPLUS_MODELARK_BASE_URL must use HTTPS")
    if not settings.seed_audio_base_url.startswith("https://"):
        raise ValueError("BYTEPLUS_SEED_AUDIO_BASE_URL must use HTTPS")
    if settings.artifact_ttl_seconds <= 0:
        raise ValueError("ARTIFACT_TTL_SECONDS must be positive")
    if settings.mcp_inline_media_max_bytes <= 0:
        raise ValueError("MCP_INLINE_MEDIA_MAX_BYTES must be positive")
