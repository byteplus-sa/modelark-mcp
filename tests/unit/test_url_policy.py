"""Unit tests for URL security policy (SSRF prevention)."""

from __future__ import annotations

import pytest

from modelark_mcp.security.url_policy import (
    UrlValidationError,
    validate_url,
    validate_url_syntax,
)


class TestUrlValidation:
    """Tests for the URL SSRF policy."""

    def test_https_url_accepted(self) -> None:
        result = validate_url(
            "https://example.com/image.png",
            resolver=lambda _host, _port: ("93.184.216.34",),
        )
        assert result.hostname == "example.com"
        assert str(result.addresses[0]) == "93.184.216.34"

    def test_http_url_rejected(self) -> None:
        with pytest.raises(UrlValidationError, match="HTTP URLs are not allowed"):
            validate_url("http://example.com/image.png")

    def test_http_url_allowed_with_flag(self) -> None:
        validate_url(
            "http://example.com/image.png",
            allow_http=True,
            resolver=lambda _host, _port: ("93.184.216.34",),
        )

    def test_file_scheme_rejected(self) -> None:
        with pytest.raises(UrlValidationError, match="scheme"):
            validate_url("file:///etc/passwd")

    def test_missing_hostname_rejected(self) -> None:
        with pytest.raises(UrlValidationError, match="hostname"):
            validate_url("https://")

    def test_aws_metadata_host_blocked(self) -> None:
        with pytest.raises(UrlValidationError, match="blocked"):
            validate_url("https://169.254.169.254/latest/meta-data/")

    def test_gcp_metadata_host_blocked(self) -> None:
        with pytest.raises(UrlValidationError, match="blocked"):
            validate_url("https://metadata.google.internal/computeMetadata/v1/")

    def test_loopback_ip_blocked(self) -> None:
        with pytest.raises(UrlValidationError, match="blocked IP"):
            validate_url("https://127.0.0.1/image.png")

    def test_private_ip_blocked(self) -> None:
        with pytest.raises(UrlValidationError, match="blocked IP"):
            validate_url("https://10.0.0.1/image.png")

    def test_link_local_blocked(self) -> None:
        with pytest.raises(UrlValidationError, match="blocked IP"):
            validate_url("https://169.254.1.1/image.png")

    def test_multicast_blocked(self) -> None:
        with pytest.raises(UrlValidationError, match="blocked IP"):
            validate_url("https://224.0.0.1/image.png")

    def test_mixed_public_and_private_dns_is_rejected(self) -> None:
        with pytest.raises(UrlValidationError, match="blocked IP"):
            validate_url(
                "https://example.com/image.png",
                resolver=lambda _host, _port: ("93.184.216.34", "10.0.0.1"),
            )

    def test_embedded_credentials_are_rejected(self) -> None:
        with pytest.raises(UrlValidationError, match="Credentials"):
            validate_url_syntax("https://user:password@example.com/image.png")

    def test_empty_resolution_is_rejected(self) -> None:
        with pytest.raises(UrlValidationError, match="did not resolve"):
            validate_url(
                "https://example.com/image.png",
                resolver=lambda _host, _port: (),
            )

    def test_ipv4_mapped_private_ipv6_is_rejected(self) -> None:
        with pytest.raises(UrlValidationError, match="blocked IP"):
            validate_url("https://[::ffff:127.0.0.1]/image.png")
