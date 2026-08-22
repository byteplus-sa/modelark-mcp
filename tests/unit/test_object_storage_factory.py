"""Unit tests for the object-storage gateway factory."""

from __future__ import annotations

import pytest

from modelark_mcp.config.env import Settings
from modelark_mcp.providers.object_storage import make_object_storage_gateway
from modelark_mcp.providers.s3.client import S3Gateway
from modelark_mcp.providers.tos.client import TosGateway


def _tos_settings() -> Settings:
    return Settings(
        _env_file=None,
        TOS_ACCESS_KEY="ak-tos",
        TOS_SECRET_KEY="sk-tos",  # pragma: allowlist secret
        TOS_BUCKET="tos-bucket",
        OBJECT_STORAGE_BACKEND="tos",
    )


def _s3_settings() -> Settings:
    return Settings(
        _env_file=None,
        S3_ACCESS_KEY="ak-s3",
        S3_SECRET_KEY="sk-s3",  # pragma: allowlist secret
        S3_BUCKET="s3-bucket",
        OBJECT_STORAGE_BACKEND="s3",
    )


class TestMakeObjectStorageGateway:
    def test_tos_backend_returns_tos_gateway(self) -> None:
        gateway = make_object_storage_gateway(_tos_settings())
        assert isinstance(gateway, TosGateway)

    def test_s3_backend_returns_s3_gateway(self) -> None:
        gateway = make_object_storage_gateway(_s3_settings())
        assert isinstance(gateway, S3Gateway)

    def test_tos_backend_without_credentials_raises(self) -> None:
        settings = Settings(_env_file=None, OBJECT_STORAGE_BACKEND="tos")
        with pytest.raises(ValueError, match="TOS credentials are not configured"):
            make_object_storage_gateway(settings)

    def test_s3_backend_without_credentials_raises(self) -> None:
        settings = _s3_settings().model_copy(
            update={"s3_access_key": "", "s3_secret_key": "", "s3_bucket": ""}
        )
        with pytest.raises(ValueError, match="S3 credentials are not configured"):
            make_object_storage_gateway(settings)
